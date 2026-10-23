#!/usr/bin/env python3
"""Hidden-test outcome bench: does skill text as the system prompt make a model fix small Python bugs more often?

usage: hidden_test_bench.py validate                      (corpus check: buggy source fails, reference fix passes; offline)
       hidden_test_bench.py run [--model M] [--samples K] [--jobs N] [--limit T] [--split easy|hard|all] [--arms a,b] [--out DIR] [--cache DIR]
       hidden_test_bench.py report [--out DIR]            (offline; reads runs.jsonl, writes results.json)

Corpus: small self-written tickets in docs/bench/hidden-test-r2-1021/tickets/*.txt, 40 "easy" (part*.txt) and 23 "hard" (hard*.txt:
stateful, ordering, multi-bug and misleading tickets, calibrated so the no-skill arm lands near half). Each has a ticket, buggy src, a reference
fix and hidden pytest tests. The model sees only the ticket and the buggy src, never the tests. Arms differ only in the system
prompt: none, perun (agentic-delivery references/full-map.md + deep-code-review operating principles, definition of done and
testing-and-evals reference), perun-lean (only the build/verify gate rows and the root-cause/verify principles, extracted from
the same files), superpowers (test-driven-development + systematic-debugging), agent-skills (test-driven-development +
debugging-and-error-recovery). Rival texts are fetched at run time into --cache from a pinned commit and are never committed.
Score: the reply's final python block replaces src; the ticket passes iff all hidden tests pass. Per-ticket score = pass fraction
over K samples; CIs are 10,000-resample percentile bootstraps over tickets (seed 1), paired for differences. The model is a free
PCSS model (no paid call); the key comes from PCSS_KEY or the repo-root .env and is never printed. No tools, one turn.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rival_eval import PCSS, boot, load_key  # noqa: E402  (reuse the PCSS key loader and the bootstrap)

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs/bench/hidden-test-r2-1021"
SKILLS = Path(os.environ.get("HT_SKILLS") or ROOT / ".claude/skills")  # HT_SKILLS: read the skill text from another tree (e.g. an old commit)
MODEL = "Qwen3.5-397B-A17B"  # non-thinking mode, same generator as the other PCSS benches
ARMS = ("none", "perun", "perun-lean", "superpowers", "agent-skills")  # perun-core = perun minus the delivery and testing blocks (the bug-fix route)
BLOCKS = ("delivery", "principles", "dod", "testing")  # the four top-level pieces of the perun arm; "perun-no-<block>[+<block>]" drops those (ablation)
RIVALS = {
    "superpowers": ("obra/superpowers", ["skills/test-driven-development/SKILL.md", "skills/systematic-debugging/SKILL.md"]),
    "agent-skills": ("addyosmani/agent-skills", ["skills/test-driven-development/SKILL.md", "skills/debugging-and-error-recovery/SKILL.md"]),
}
BASE = ("You are a careful software engineer fixing a bug in a small Python module. You have no tools: you cannot run code, "
        "tests or commands, and you only see the text in this conversation.")
ASK = ("\n\nFix the bug. Reply with the complete corrected module in ONE final ```python block (the whole file, not a diff). "
       "Keep the public names and signatures. Use only the standard library and do not import os, sys, subprocess, shutil, "
       "socket or pathlib.")
UNSAFE = re.compile(r"^\s*(?:import|from)\s+(?:os|sys|subprocess|shutil|socket|pathlib|ctypes|importlib|builtins|pickle|urllib|http)\b"
                    r"|__import__|\bopen\s*\(|\bexec\s*\(|\beval\s*\(", re.M)
BLOCK = re.compile(r"```(?:python|py)[^\n]*\n(.*?)```", re.S | re.I)
GEN_TOKENS = 4000


# ---- corpus -----------------------------------------------------------------------------------------------------------
def load_tickets(d=D / "tickets"):
    """Parse tickets/*.txt (### id, then --- ticket|src|fix|test sections) -> list of dicts, in file order."""
    out = []
    for f in sorted(Path(d).glob("*.txt")):
        for chunk in re.split(r"^### ", f.read_text(), flags=re.M)[1:]:
            tid, _, body = chunk.partition("\n")
            parts = re.split(r"^--- (ticket|src|fix|test)\n", body, flags=re.M)
            sec = {parts[i]: parts[i + 1].strip("\n") + "\n" for i in range(1, len(parts), 2)}
            if set(sec) != {"ticket", "src", "fix", "test"}:
                raise ValueError(f"{tid}: sections {sorted(sec)}")
            out.append({"id": tid.strip(), "split": "hard" if f.name.startswith("hard") else "easy", **sec})
    ids = [t["id"] for t in out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate ticket ids")
    return out


# ---- scorer -----------------------------------------------------------------------------------------------------------
def extract_code(reply):
    """The last ```python block that is not a test file (no 'def test_' / 'import pytest'), or None."""
    blocks = [b for b in BLOCK.findall(reply or "") if "def test_" not in b and "import pytest" not in b]
    return blocks[-1].strip() + "\n" if blocks else None


def run_hidden(code, test_src, timeout=20):
    """Write code as mod.py next to the hidden tests and run pytest in a scrubbed env (no PCSS key, no network use expected).
    -> (passed, reason). Not passed: no code, unsafe construct, timeout, or a pytest failure. Side effect: temp dir, removed after."""
    if code is None:
        return False, "no-code"
    if UNSAFE.search(code):
        return False, "unsafe"
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "mod.py").write_text(code)
        (Path(td) / "test_hidden.py").write_text(test_src)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": td}
        try:
            r = subprocess.run([sys.executable, "-I", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "test_hidden.py"],
                               cwd=td, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "timeout"
    return (True, "pass") if r.returncode == 0 else (False, "tests-fail")


def validate(tickets, jobs=8):
    """Corpus health -> list of problems: every buggy src must FAIL its hidden tests and every reference fix must PASS."""
    def one(t):
        bug, _ = run_hidden(t["src"], t["test"])
        fix, why = run_hidden(t["fix"], t["test"])
        return [f"{t['id']}: buggy src passes the hidden tests" if bug else None, None if fix else f"{t['id']}: reference fix fails ({why})"]
    with cf.ThreadPoolExecutor(jobs) as ex:
        return [p for res in ex.map(one, tickets) for p in res if p]


# ---- arms -------------------------------------------------------------------------------------------------------------
def section(md, heading):
    """Text of the '## heading' section of md, up to the next '## ' heading. Raises ValueError if absent."""
    m = re.search(rf"^## {re.escape(heading)}.*?(?=^## |\Z)", md, re.S | re.M)
    if not m:
        raise ValueError(heading)
    return m.group(0).strip() + "\n"


def _dcr_map():
    """The file holding deep-code-review's principles and Definition of done: references/full-map.md, or SKILL.md in an older tree."""
    f = SKILLS / "deep-code-review/references/full-map.md"
    return f if f.exists() else SKILLS / "deep-code-review/SKILL.md"


def perun_text(skip=()):
    """The full perun arm; skip=(block, ...) from BLOCKS drops those pieces (ablation)."""
    dcr = _dcr_map().read_text()
    parts = {"delivery": (SKILLS / "agentic-delivery/references/full-map.md").read_text(), "principles": section(dcr, "Operating principles"),
             "dod": section(dcr, "Definition of done"), "testing": (SKILLS / "deep-code-review/references/testing-and-evals.md").read_text()}
    return "\n\n".join(v for k, v in parts.items() if k not in skip)


def perun_lean_text():
    """The smallest Perun text that still carries the build/verify/root-cause steps, cut from the same files perun_text() reads
    (nothing is rewritten): the G4/G5 gate rows, the missing-evidence rule, principles 1-3 and 9, and the change-approach rule.
    Raises ValueError if the source files no longer contain exactly those pieces."""
    gates = (SKILLS / "agentic-delivery/references/full-map.md").read_text()
    pick = lambda md, pat, fl=re.M: re.findall(pat, md, fl)  # noqa: E731
    rows = pick(gates, r"^\| Gate \| .*$|^\|---\|---\|---\|---\|$|^\| G[45] .*$")
    rule = pick(gates, r"^\*\*Missing evidence is.*?(?=\n\n)", re.M | re.S)
    retry = pick(gates, r"^- After two equivalent failures.*$")
    dcr = _dcr_map().read_text()
    principles = pick(section(dcr, "Operating principles"), r"^(?:1|2|3|9)\. \*\*.*?(?=^\d+\. \*\*|\Z)", re.M | re.S)
    if (len(rows), len(rule), len(principles), len(retry)) != (4, 1, 4, 1):
        raise ValueError("perun-lean sources changed")
    return "\n\n".join(["\n".join(rows)] + rule + [p.rstrip() for p in principles] + retry) + "\n"


def _get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hidden-test-bench"}), timeout=60).read().decode()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def rival_text(arm, cache):
    """Fetch the arm's public skill files at the upstream HEAD commit into cache (reused on later runs) -> (text, provenance)."""
    repo, paths = RIVALS[arm]
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    meta = cache / f"{arm}.json"
    if not meta.exists():
        sha = json.loads(_get(f"https://api.github.com/repos/{repo}/commits/HEAD"))["sha"]
        files = {p: _get(f"https://raw.githubusercontent.com/{repo}/{sha}/{p}") for p in paths}
        meta.write_text(json.dumps({"repo": repo, "commit": sha, "files": files}))
    m = json.loads(meta.read_text())
    prov = {"repo": m["repo"], "commit": m["commit"], "files": {p: hashlib.sha256(t.encode()).hexdigest() for p, t in m["files"].items()}}
    return "\n\n---\n\n".join(m["files"][p] for p in paths), prov


def arm_systems(cache, arms=ARMS):
    """-> ({arm: system prompt}, {arm: provenance}) for the given arms. The base line is shared; only the skill text differs."""
    systems, prov = {}, {}
    for arm in arms:
        if arm == "none":
            systems[arm], prov[arm] = BASE, {}
        elif arm in RIVALS:
            t, p = rival_text(arm, cache)
            systems[arm], prov[arm] = BASE + "\n\n" + t, p
        else:
            t = perun_text() if arm == "perun" else perun_text(("delivery", "testing")) if arm == "perun-core" else perun_text(tuple(arm[len("perun-no-"):].split("+"))) if arm.startswith("perun-no-") else perun_lean_text()
            systems[arm], prov[arm] = BASE + "\n\n" + t, {"sha256": hashlib.sha256(t.encode()).hexdigest()}
    return systems, prov


# ---- model ------------------------------------------------------------------------------------------------------------
def chat(model, system, user, temperature=0.7, tries=3, seed=None):
    """One PCSS completion -> (text, completion_tokens, prompt_tokens, finish_reason). RuntimeError after `tries` failures (type only, never the key)."""
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "max_tokens": GEN_TOKENS, "temperature": temperature, "chat_template_kwargs": {"enable_thinking": False},
                       **({} if seed is None else {"seed": seed})}).encode()
    err = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(PCSS + "/chat/completions", body, {"Authorization": "Bearer " + load_key(), "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=600))
            txt = re.sub(r"<think>.*?</think>", "", r["choices"][0]["message"]["content"] or "", flags=re.S).strip()
            if txt:
                u = r.get("usage") or {}
                return txt, u.get("completion_tokens", 0), u.get("prompt_tokens", 0), r["choices"][0].get("finish_reason")
            err = "empty output"
        except Exception as e:
            err = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{model}: {err}")


def user_prompt(t):
    return f"TICKET:\n{t['ticket']}\nSOURCE (mod.py):\n```python\n{t['src']}```{ASK}"


def run(args):
    tickets = [t for t in load_tickets() if args.split in ("all", t["split"])][:args.limit]
    arms = args.arms.split(",")
    systems, prov = arm_systems(args.cache, arms)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "runs.jsonl"
    done = {(r["arm"], r["id"], r["sample"]) for r in map(json.loads, log.read_text().splitlines())} if log.exists() else set()
    old = json.loads((out / "provenance.json").read_text()) if (out / "provenance.json").exists() else {}
    (out / "provenance.json").write_text(json.dumps({"model": args.model, "temperature": 0.7, "samples": args.samples, "seed": args.seed, "arms": {**old.get("arms", {}), **prov},
                                                      "tickets_sha256": hashlib.sha256("".join(t["ticket"] + t["src"] + t["test"] for t in load_tickets()).encode()).hexdigest(),
                                                      "system_chars": {**old.get("system_chars", {}), **{a: len(s) for a, s in systems.items()}}}, indent=1) + "\n")
    lock = threading.Lock()
    todo = [(a, t, k) for k in range(args.samples) for t in tickets for a in arms if (a, t["id"], k) not in done]
    print(f"{len(todo)} calls to make, {len(done)} cached", file=sys.stderr)

    def one(job):
        a, t, k = job
        try:
            reply, ctok, ptok, fin = chat(args.model, systems[a], user_prompt(t), seed=None if args.seed is None else args.seed + k)
        except RuntimeError as e:
            print(f"skip {a}/{t['id']}/{k}: {e}", file=sys.stderr)
            return
        ok, why = run_hidden(extract_code(reply), t["test"])
        rec = {"arm": a, "id": t["id"], "sample": k, "pass": ok, "why": why, "completion_tokens": ctok, "prompt_tokens": ptok, "finish": fin, "reply": reply}
        with lock:
            with log.open("a") as f:
                f.write(json.dumps(rec) + "\n")

    with cf.ThreadPoolExecutor(args.jobs) as ex:
        list(ex.map(one, todo))


# ---- report -----------------------------------------------------------------------------------------------------------
def mean(v):
    return sum(v) / len(v)


def report(recs, ids, arms=ARMS):
    """recs: run records. -> results dict: per-arm pass rate [CI], tokens, and paired differences. Raises ValueError on an incomplete grid."""
    cells = {}
    for r in recs:
        cells.setdefault((r["arm"], r["id"]), []).append(r)
    ks = {len(v) for v in cells.values()}
    missing = [(a, i) for a in arms for i in ids if (a, i) not in cells]
    if missing or len(ks) != 1:
        raise ValueError(f"incomplete grid: {len(missing)} missing cells, samples per cell {sorted(ks)}")
    per = {a: [mean([x["pass"] for x in cells[(a, i)]]) for i in ids] for a in arms}
    res = {"n_tickets": len(ids), "samples_per_ticket": ks.pop(), "bootstrap": "10000 resamples, seed 1, percentile, over tickets", "arms": {}, "paired": []}
    for a in arms:
        rs = [x for i in ids for x in cells[(a, i)]]
        lo, hi = boot(per[a])
        res["arms"][a] = {"pass_rate": mean(per[a]), "ci95": [lo, hi], "completion_tokens_per_ticket": mean([x["completion_tokens"] for x in rs]),
                          "prompt_tokens_per_ticket": mean([x["prompt_tokens"] for x in rs]), "truncated": sum(x["finish"] == "length" for x in rs),
                          "no_code": sum(x["why"] == "no-code" for x in rs), "unsafe": sum(x["why"] == "unsafe" for x in rs), "timeouts": sum(x["why"] == "timeout" for x in rs)}
    pairs = [(a, "none") for a in arms if a != "none"] + [(p, r) for p in ("perun", "perun-lean") for r in RIVALS] + [("perun-lean", "perun")] + [(a, "perun") for a in arms if a.startswith("perun-no-") or a == "perun-core"]
    for a, b in pairs:
        if a not in per or b not in per:
            continue
        diff = [x - y for x, y in zip(per[a], per[b])]
        lo, hi = (round(v, 9) for v in boot(diff))  # round away float noise so a bound of exactly 0 is not a win
        res["paired"].append({"a": a, "b": b, "diff": mean(diff), "ci95": [lo, hi], "verdict": "a better" if lo > 0 else "b better" if hi < 0 else "tie (CI includes 0)"})
    return res


def table(res):
    rows = ["| Arm | Hidden-test pass rate [95% CI] | Completion tokens per ticket | Prompt tokens per ticket |", "|---|---|---|---|"]
    for a, r in res["arms"].items():
        rows.append(f"| {a} | {r['pass_rate']:.3f} [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}] | {r['completion_tokens_per_ticket']:.0f} | {r['prompt_tokens_per_ticket']:.0f} |")
    rows += ["", "| A minus B (paired) | Difference [95% CI] | Verdict |", "|---|---|---|"]
    for p in res["paired"]:
        rows.append(f"| {p['a']} - {p['b']} | {p['diff']:+.3f} [{p['ci95'][0]:+.3f}, {p['ci95'][1]:+.3f}] | {p['verdict']} |")
    return "\n".join(rows) + "\n"


def do_report(args):
    out = Path(args.out)
    recs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
    tk = load_tickets()
    seen = {r["id"] for r in recs}
    arms = tuple(args.arms.split(","))
    res = {"model": json.loads((out / "provenance.json").read_text())["model"],
           "splits": {s: report(recs, [t["id"] for t in tk if t["split"] == s], arms) for s in ("easy", "hard") if any(t["id"] in seen and t["split"] == s for t in tk)}}
    (out / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    for s, r in res["splits"].items():
        print(f"## {s} split ({r['n_tickets']} tickets)\n\n{table(r)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    r = sub.add_parser("run")
    r.add_argument("--model", default=MODEL)
    r.add_argument("--samples", type=int, default=3)
    r.add_argument("--jobs", type=int, default=6)
    r.add_argument("--seed", type=int, default=None, help="sent to the API as seed+sample index when set (the pilot sent none)")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--split", default="all", choices=["easy", "hard", "all"])
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "hidden-test-bench-skills"))
    rp = sub.add_parser("report")
    rp.add_argument("--arms", default=",".join(ARMS))
    for s in (r, rp):
        s.add_argument("--out", default=str(D / "confirm"))
    a = p.parse_args(argv)
    if a.cmd == "validate":
        bad = validate(load_tickets())
        print("\n".join(bad) or f"corpus ok: {len(load_tickets())} tickets")
        return 1 if bad else 0
    if a.cmd == "report":
        return do_report(a)
    load_key()  # fail before any work when the key is missing
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
