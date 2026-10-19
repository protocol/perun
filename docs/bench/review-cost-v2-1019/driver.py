#!/usr/bin/env python3
"""Review-token parity bench (see PREREGISTERED.md, version 2). Both arms run on PCSS Qwen3.5-397B-A17B through a minimal
tool loop (read_file, grep, glob); judges are PCSS DeepSeek-V4-Flash with GLM-5.2 as fallback. No Claude call, no spend.
Scoring, crediting and the paired bootstrap are those of the earlier review-real-skill-1016-heldout driver.
usage: driver.py review ARM tune|heldout|all   (ARM = BASE | TK | any variant name; BASE/variants use the skill in the repo,
                                               set SKILL_DIR to point a run at another skill copy)
       driver.py judge ARM tune|heldout|all
       driver.py report ARM tune|heldout      (ARM vs TK)
       driver.py tokens ARM tune|heldout      (token decomposition)"""
import concurrent.futures as cf, json, os, random, re, shutil, sys, tempfile, time, urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / ".claude/skills/deep-code-review/scripts"))
import bench_corpus as bc  # noqa: E402
import score_review as sr  # noqa: E402

CORPUS = ROOT / "scripts/eval-fixtures/bench/train"
SKILL = Path(os.environ.get("SKILL_DIR") or ROOT / ".claude/skills/deep-code-review")
SPLIT = json.loads((D / "split.json").read_text())
SPLIT["all"] = SPLIT["tune"] + SPLIT["heldout"]
URL = "https://llm.hpc.psnc.pl/v1/chat/completions"
HOST, JUDGE, TIE = "Qwen3.5-397B-A17B", "DeepSeek-V4-Flash", "GLM-5.2"
JOBS, MAX_TURNS = 2, 12
OUT = D / "runs"
TK = (D / "tk_system.txt").read_text()


def system_for(arm):
    """TK: rival system prompt. V2*: SKILL_DIR/SKILL.md body (after the frontmatter) as the system prompt, no skill files, no reference loads. Else None (skill-in-workspace)."""
    if arm == "TK":
        return TK
    return (SKILL / "SKILL.md").read_text().split("\n---\n", 1)[1].strip() if arm.startswith("V2") else None
TOOLS = [{"type": "function", "function": {"name": n, "description": d, "parameters": {"type": "object", "properties": p, "required": r}}} for n, d, p, r in (
    ("read_file", "Read a text file in the workspace with line numbers.", {"path": {"type": "string"}, "offset": {"type": "integer", "description": "first line, 1-based"}, "limit": {"type": "integer", "description": "max lines, default 2000"}}, ["path"]),
    ("grep", "Regex search over workspace files; returns file:line:text (max 100).", {"pattern": {"type": "string"}, "path": {"type": "string"}}, ["pattern"]),
    ("glob", "List workspace files matching a glob pattern.", {"pattern": {"type": "string"}}, ["pattern"]))]


def key():
    for l in (Path.home() / "Desktop/deep-code-review/.env").read_text().splitlines():
        if l.removeprefix("export ").startswith("PCSS_KEY="):
            return l.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("PCSS_KEY missing")


def chat(model, messages, tools=None, max_tokens=8000):
    body = dict(model=model, temperature=0, max_tokens=max_tokens, messages=messages, **(dict(tools=tools) if tools else {}))
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(URL, json.dumps(body).encode(), {"Authorization": "Bearer " + key(), "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=900))
        except Exception as e:  # noqa: BLE001 - retried, then raised
            last = e; time.sleep(5 * (i + 1))
    raise last


def run_tool(w, name, a):
    """Execute one tool inside workspace w; paths confined to w. Returns text."""
    def safe(p):
        q = (w / (p or ".")).resolve()
        if w.resolve() not in (q, *q.parents):
            raise ValueError("path outside workspace")
        return q
    try:
        if name == "read_file":
            ls = safe(a["path"]).read_text(errors="replace").splitlines(); o = max(1, int(a.get("offset") or 1)); n = int(a.get("limit") or 2000)
            return "\n".join(f"{o + i:6d}\t{l}" for i, l in enumerate(ls[o - 1:o - 1 + n])) or "(empty)"
        if name == "grep":
            rx, out = re.compile(a["pattern"]), []
            for f in sorted(p for p in safe(a.get("path")).rglob("*") if p.is_file()) if safe(a.get("path")).is_dir() else [safe(a["path"])]:
                for i, l in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    if rx.search(l):
                        out.append(f"{f.relative_to(w)}:{i}:{l}")
            return "\n".join(out[:100]) or "(no matches)"
        if name == "glob":
            return "\n".join(str(p.relative_to(w)) for p in sorted(w.glob(a["pattern"])) if p.is_file())[:4000] or "(none)"
    except Exception as e:  # noqa: BLE001 - tool errors are model-visible
        return f"error: {e}"
    return "error: unknown tool"


def ws(cid, skill=False):
    w = Path(tempfile.mkdtemp(prefix="bench-"))
    shutil.copy(CORPUS / cid / "change.patch", w)
    if skill:
        shutil.copytree(SKILL, w / ".claude/skills/deep-code-review")
    return w


def agent(w, system, prompt):
    """Tool loop. -> (text, err, stats). stats: per-turn prompt tokens, completion tokens, tools called."""
    msgs = ([dict(role="system", content=system)] if system else []) + [dict(role="user", content=prompt)]
    st = dict(prompt=[], completion=0, tools=[]); txt = ""
    for turn in range(MAX_TURNS + 1):
        last = turn == MAX_TURNS
        if last:
            msgs.append(dict(role="user", content="Tool budget used up. Give your FINAL message now in the required format."))
        j = chat(HOST, msgs, None if last else TOOLS)
        u, m = j["usage"], j["choices"][0]["message"]
        st["prompt"].append(u["prompt_tokens"]); st["completion"] += u["completion_tokens"]
        calls = m.get("tool_calls") or []
        if not calls:
            return m.get("content") or "", "" if (m.get("content") or "").strip() else "empty output", st
        msgs.append(dict(role="assistant", content=m.get("content"), tool_calls=calls))
        for c in calls:
            try:
                a = json.loads(c["function"]["arguments"] or "{}")
            except ValueError:
                a = {}
            st["tools"].append([c["function"]["name"], str(a.get("path") or a.get("pattern"))[-60:]])
            msgs.append(dict(role="tool", tool_call_id=c["id"], content=run_tool(w, c["function"]["name"], a)))
    return "", "turn limit", st


def review(cid, arm):
    p = OUT / arm / f"{cid}.json"
    if p.exists() and not json.loads(p.read_text()).get("error"):
        return cid, "cached"
    p.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (1, 2):
        w = ws(cid, system_for(arm) is None)
        try:
            txt, err, st = agent(w, system_for(arm), bc.PRODUCER if system_for(arm) else bc.PERUN)
        except Exception as e:  # noqa: BLE001
            txt, err, st = "", type(e).__name__, dict(prompt=[], completion=0, tools=[])
        finally:
            shutil.rmtree(w, ignore_errors=True)
        f = None if err else bc.parse_array(txt)
        err = err or ("" if f is not None else "no JSON array in output")
        rec = dict(id=cid, arm=arm, findings=f or [], error=err, attempts=attempt, turns=len(st["prompt"]), tokens=sum(st["prompt"]) + st["completion"], **st)
        p.write_text(json.dumps(rec, indent=1))
        if not err:
            break
    return cid, rec["error"] or f"{len(rec['findings'])} findings, {rec['tokens']} tok"


def judge(cid, arm):
    """DeepSeek-V4-Flash judges every strict-unmatched finding (patch inlined, no tools); GLM-5.2 re-judges findings it left missing/unverifiable."""
    p = OUT / arm / f"{cid}.json"
    rec = json.loads(p.read_text())
    if rec.get("error") or "verdicts" in rec and not rec.get("verify_error"):
        return cid, "skip"
    truth = json.loads((CORPUS / cid / "ground-truth.json").read_text())
    rec["matched"] = [bool(sr.score(truth, [f])["hit"]) for f in rec["findings"]]
    un = [(i, f) for i, f in enumerate(rec["findings"]) if not rec["matched"][i]]
    bug, patch = "; ".join(b["bug"] for b in truth["bugs"]), (CORPUS / cid / "change.patch").read_text()
    rec["verdicts"] = {}; rec["verify_error"] = ""
    for model in (JUDGE, TIE):
        todo = [(i, f) for i, f in un if rec["verdicts"].get(str(i), {}).get("verdict") in (None, "unverifiable")]
        if not todo:
            break
        listing = "\n".join(f"{i}. [{f.get('file')}:{f.get('line')}] {f.get('text')}" for i, f in todo)
        prompt = bc.VERIFY.format(bug=bug, findings=listing) + "\n\nYou have no tools. The full change.patch (there is no ./context) follows.\n" + patch
        vs = None
        for _ in range(3):  # transient empty / unparsable replies are retried
            try:
                txt = (chat(model, [dict(role="user", content=prompt)], max_tokens=6000)["choices"][0]["message"].get("content") or "").split("</think>")[-1]
                vs = bc.parse_array(txt, "verdict")
            except Exception as e:  # noqa: BLE001
                vs, rec["verify_error"] = None, type(e).__name__
            if vs is not None:
                break
        if vs is None:
            rec["verify_error"] = rec["verify_error"] or f"{model}: no JSON array"
            continue
        rec["verify_error"] = ""
        for v in vs:
            if str(v.get("i")) in {str(i) for i, _ in todo}:
                rec["verdicts"][str(v["i"])] = dict(verdict=v.get("verdict"), reason=v.get("reason"), judge=model)
    if un and rec["verify_error"] == "" and any(str(i) not in rec["verdicts"] for i, _ in un):
        rec["verify_error"] = "missing verdicts"
    p.write_text(json.dumps(rec, indent=1))
    return cid, rec["verify_error"] or len(un)


def stage(fn, arm, ids):
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for r in ex.map(lambda c: fn(c, arm), ids):
            print(*r, flush=True)


def tally(rec, truth):
    """good = strict match or judge real/gt_same; one bug per case, gt_same credits it."""
    vd = rec["verdicts"]; un = [i for i, m in enumerate(rec["matched"]) if not m]
    gts = any(vd.get(str(i), {}).get("verdict") == "gt_same" for i in un)
    good = sum(rec["matched"]) + sum(vd.get(str(i), {}).get("verdict") in ("real", "gt_same") for i in un)
    n_hit = len(sr.score(truth, rec["findings"])["hit"]); nb = len(truth["bugs"])
    return dict(n=len(rec["findings"]), good=good, bugs=nb, cred=nb if gts else n_hit, tokens=rec["tokens"], turns=rec["turns"])


def loadt(arm, cid):
    p = OUT / arm / f"{cid}.json"
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("error") or rec.get("verify_error") or "verdicts" not in rec:
        return None
    return tally(rec, json.loads((CORPUS / cid / "ground-truth.json").read_text()))


def stats(rows):
    P = sum(r["good"] for r in rows) / max(1, sum(r["n"] for r in rows)); R = sum(r["cred"] for r in rows) / max(1, sum(r["bugs"] for r in rows))
    return P, R, (2 * P * R / (P + R) if P + R else 0.0)


def ci(xs, B):
    xs = sorted(xs); return [round(xs[int(.025 * B)], 3), round(xs[int(.975 * B) - 1], 3)]


def boot(a, b, B=10000, seed=1):
    """Paired case-level bootstrap of (a - b) for precision, recall, F1 (pooled ratios per resample), 95% percentile CI."""
    rng = random.Random(seed); n = len(a); ds = [[], [], []]
    for _ in range(B):
        ix = [rng.randrange(n) for _ in range(n)]
        sa, sb = stats([a[i] for i in ix]), stats([b[i] for i in ix])
        for k in range(3): ds[k].append(sa[k] - sb[k])
    full = [x - y for x, y in zip(stats(a), stats(b))]
    return [dict(d=round(full[k], 3), ci=ci(ds[k], B)) for k in range(3)]


def report(arm, half, base="BASE"):
    """ARM vs TK quality; ARM vs BASE tokens (same cases). Writes results-ARM-half.json."""
    names = ("precision", "recall", "f1")
    rows = [(c, loadt(arm, c), loadt("TK", c), loadt(base, c)) for c in SPLIT[half]]
    H = [(c, a, t, b) for c, a, t, b in rows if a and t]
    A, T = [x[1] for x in H], [x[2] for x in H]
    blk = lambda X: dict(zip(names, (round(v, 3) for v in stats(X))), findings=sum(r["n"] for r in X))  # noqa: E731
    mean = lambda X, k: round(sum(r[k] for r in X) / max(1, len(X)), 1)  # noqa: E731
    Bs = [x[3] for x in H if x[3]]
    out = dict(arm=arm, half=half, n=len(H), dropped=[c for c, a, t, b in rows if not (a and t)], ARM=blk(A), TK=blk(T), ARM_minus_TK=dict(zip(names, boot(A, T))),
               tokens=dict(arm_mean=mean(A, "tokens"), tk_mean=mean(T, "tokens"), base_mean=mean(Bs, "tokens") if Bs else None, base_n=len(Bs),
                           ratio_to_base=round(mean(A, "tokens") / mean(Bs, "tokens"), 3) if Bs else None, arm_turns=mean(A, "turns")))
    if base != arm and Bs and len(Bs) == len(H):
        out["BASE_minus_TK"] = dict(zip(names, boot(Bs, T)))
    (D / f"results-{arm}-{half}.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


def tokens(arm, half):
    """Decomposition: mean first-turn prompt, mean turns, mean sum prompt, mean completion, how many reviews read which tool targets."""
    recs = [json.loads(p.read_text()) for c in SPLIT[half] if (p := OUT / arm / f"{c}.json").exists()]
    recs = [r for r in recs if not r.get("error")]
    m = lambda xs: round(sum(xs) / max(1, len(xs)), 1)  # noqa: E731
    sk = [m([r["prompt"][i + 1] - r["prompt"][i] for i in range(len(r["prompt"]) - 1)][:1]) for r in recs if r["prompt"][1:]]
    out = dict(arm=arm, half=half, n=len(recs), first_turn_prompt=m([r["prompt"][0] for r in recs]), turns=m([r["turns"] for r in recs]),
               sum_prompt=m([sum(r["prompt"]) for r in recs]), completion=m([r["completion"] for r in recs]), tokens=m([r["tokens"] for r in recs]),
               first_growth=m(sk), reads=sorted({t[1] for r in recs for t in r["tools"] if t[0] == "read_file"})[:12])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    c, arm, half = sys.argv[1:4]
    if c == "report": report(arm, half)
    elif c == "tokens": tokens(arm, half)
    else: stage(dict(review=review, judge=judge)[c], arm, SPLIT[half])
