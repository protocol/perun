#!/usr/bin/env python3
"""Seeded security bench, Perun vs rival (same model, one claude -p call per diff, the diff inline in the prompt for both arms).
  PERUN = deep-code-review skill (repo HEAD) in the workspace; the prompt names the skill and lets it route (no forced reads, no script).
  RIVAL = prompt of anthropics/claude-code-security-review (rival_prompts.py, fetched 2026-10-23, upstream main 0c6a49f1).
Both arms get Read, Grep, Glob only. Reuses confirm.call (ledger, $ cap, plan-quota >= 0.8 stop from the previous call's reading, fail closed).
usage: run.py run SET [N] | run.py score SET    SET = tuned (scripts/eval-fixtures/security-seeded) | heldout (security-seeded-heldout, burned) | heldout2 (security-seeded-heldout2, blind)
Output: runs/SET/out/<ARM>/<id>.json ({file,line,cwe} list), runs/SET/raw/<ARM>/<id>.txt, ledger-1026.jsonl, usage-1026.jsonl (per-call tokens).
The 2026-10-26 first run (out/, raw/, ledger.jsonl) used the earlier prompt and is kept as recorded."""
import json, re, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/bench/review-cost-v2-1019"))
import confirm  # noqa: E402
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
from rival_prompts import get_security_audit_prompt  # noqa: E402

# CAP: $1.34 spent before heldout2 plus its own $5 cap.
confirm.CAP, confirm.LEDGER, confirm.RESERVE = 6.34, HERE / "ledger-1026.jsonl", 0.5
USAGE = HERE / "usage-1026.jsonl"
KEEP = ("turns", "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
confirm.FLAGS = ["-p", "--setting-sources", "project,local", "--strict-mcp-config", "--no-session-persistence", "--output-format", "stream-json",
                 "--verbose", "--max-budget-usd", str(confirm.RESERVE), "--tools", "Read,Grep,Glob", "--allowedTools", "Read", "Grep", "Glob"]
SETS = {"tuned": ROOT / "scripts/eval-fixtures/security-seeded", "heldout": ROOT / "scripts/eval-fixtures/security-seeded-heldout",
        "heldout2": ROOT / "scripts/eval-fixtures/security-seeded-heldout2"}
SKILL = ROOT / ".claude/skills/deep-code-review"
FMT = 'Final reply: ONLY a JSON array, one object per finding, {"file": "path", "line": <int new-file line>, "cwe": "CWE-<n>"}; [] if none.'
PERUN = "Security review of the diff below, using the deep-code-review skill at .claude/skills/deep-code-review (start with its SKILL.md). "
CWE = [("xxe", 611), ("xml", 611), ("prototype", 1321), ("certificate", 295), ("tls", 295), ("ssl", 295), ("random", 338),
       ("jwt", 347), ("signature", 347), ("mass_assign", 915), ("mass assign", 915), ("code_injection", 94), ("eval", 95), ("sql", 89), ("command", 78), ("xss", 79), ("ssrf", 918), ("traversal", 22), ("deserial", 502), ("pickle", 502), ("yaml", 502),
       ("redirect", 601), ("timing", 208), ("idor", 639), ("toctou", 367), ("race", 367), ("hardcoded", 798), ("secret", 798), ("crypto", 327),
       ("weak", 327), ("auth", 862)]


def rival_cwe(cat):
    c = (cat or "").lower()
    return next((f"CWE-{n}" for k, n in CWE if k in c), None)


def last_json(t, kind="[", typ=list):
    """Last top-level JSON value of type typ in t (prose may precede it); None if absent."""
    d, i = json.JSONDecoder(), 0
    last = None
    while (i := t.find(kind, i)) >= 0:
        try:
            v, j = d.raw_decode(t, i)
            last, i = (v if isinstance(v, typ) else last), j
        except ValueError:
            i += 1
    return last


def parse_perun(t):
    return last_json(t)


def parse_rival(t):
    o = last_json(t, "{", dict)
    if o is None:
        return None
    rows = o.get("findings", [])
    return [dict(file=r["file"], line=r["line"], cwe=rival_cwe(r.get("category"))) for r in rows]


assert parse_perun('prose [see x] more\n[{"file": "a", "line": 1, "cwe": "CWE-79"}]') == [{"file": "a", "line": 1, "cwe": "CWE-79"}]
assert parse_rival('x {y} {"findings": [{"file": "a", "line": 2, "category": "xss"}]}') == [dict(file="a", line=2, cwe="CWE-79")]
assert parse_perun("none") is None and parse_perun("[]") == []


def workspace(arm):
    w = Path(tempfile.mkdtemp(prefix="secbench-"))
    if arm == "PERUN":
        shutil.copytree(SKILL, w / ".claude/skills/deep-code-review")
    return w


def one(arm, s, i):
    base = HERE / "runs" / s
    out = base / "out" / arm / f"{i}.json"
    if out.exists():
        return
    patch = (SETS[s] / "diffs" / f"{i}.diff").read_text()
    files = re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)
    if arm == "PERUN":
        prompt = PERUN + FMT + "\n\n```diff\n" + patch + "```\n"
    else:  # neutral title: the fixture id names the class or says decoy, so it never reaches either arm
        pr = dict(number=1, title="change", user="dev", changed_files=len(files), additions=patch.count("\n+"), deletions=0,
                  files=[dict(filename=f) for f in files])
        prompt = get_security_audit_prompt(pr, patch)
    w = workspace(arm)
    try:
        txt, err, use = confirm.call(prompt, w, None, f"{s}/{arm}/{i}")
    finally:
        shutil.rmtree(w, ignore_errors=True)
    with open(USAGE, "a") as f:
        f.write(json.dumps(dict(tag=f"{s}/{arm}/{i}", **{k: use.get(k) for k in KEEP})) + "\n")
    (base / "raw" / arm).mkdir(parents=True, exist_ok=True)
    (base / "raw" / arm / f"{i}.txt").write_text(txt)
    try:
        rows = (parse_perun if arm == "PERUN" else parse_rival)(txt) if not err else None
    except (ValueError, KeyError, TypeError):
        rows = None
    if rows is None:
        print(f"{arm}/{i}: unparsable ({err or 'no JSON'}); left unscored", file=sys.stderr)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows))


def score(s):
    """Strict (file + line within 1 + CWE or equiv) and location-only (CWE ignored, which removes the rival keyword-map guess)."""
    import security_bench_score as sbs
    keys = json.loads((SETS[s] / "keys.json").read_text())
    res = {}
    for arm in ("PERUN", "RIVAL"):
        found = sbs.load(HERE / "runs" / s / "out" / arm, keys)
        res[arm] = dict(strict=sbs.score(keys, found), loc_only=sbs.score(keys, {i: [dict(f, cwe=None) for f in fs] for i, fs in found.items()}))
    return res


if __name__ == "__main__":
    mode, s = sys.argv[1], sys.argv[2]
    if mode == "score":
        print(json.dumps(score(s), indent=2))
        sys.exit(0)
    ids = sorted(p.stem for p in (SETS[s] / "diffs").glob("*.diff"))[: int(sys.argv[3]) if len(sys.argv) > 3 else None]
    try:
        for i in ids:
            for arm in ("PERUN", "RIVAL"):
                one(arm, s, i)
    except confirm.Stop as e:
        print("STOP:", e, file=sys.stderr)
        sys.exit(3)
