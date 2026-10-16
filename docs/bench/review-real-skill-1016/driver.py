#!/usr/bin/env python3
"""Real-skill vs toolkit review bench. usage: driver.py run|verify|report [PRIOR_OUTPUTS_DIR]
Arms: REAL = bench_corpus.PERUN prompt + the repo's actual deep-code-review skill copied into the workspace;
TK = Anthropic pr-review-toolkit code-reviewer as --system-prompt (tk_system.txt). Same model, same PRODUCER request,
same 22 cases (ids.txt), same Opus judge/VERIFY and scorer as the earlier compact-mode (CF) bench. Hard cap CAP USD via total_cost_usd."""
import concurrent.futures as cf, json, random, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / ".claude/skills/deep-code-review/scripts"))
import bench_corpus as bc  # noqa: E402
import score_review as sr  # noqa: E402

CORPUS = ROOT / "scripts/eval-fixtures/bench/train"
SKILL = ROOT / ".claude/skills/deep-code-review"
CAP, JOBS = 8.0, 4
RESERVE = {"claude-sonnet-5-5": 0.60, "claude-opus-5-5": 1.00}
IDS = (D / "ids.txt").read_text().split()
TK = (D / "tk_system.txt").read_text()
BASE = ["-p", "--setting-sources", "project,local", "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"]
TOOLS = ["--tools", "Read,Grep,Glob", "--allowedTools", "Read", "Grep", "Glob"]
LOCK = threading.Lock(); INFLIGHT = {"n": 0.0}


class Cap(Exception): pass


def spent():
    p = D / "ledger.jsonl"
    return sum(json.loads(l)["cost"] for l in p.read_text().splitlines()) if p.exists() else 0.0


def call(prompt, cwd, model, system, tag):
    """One claude -p call; cost ledgered; cap checked with in-flight reserve before the call. -> (text, err, turns)"""
    r = RESERVE[model]
    with LOCK:
        if spent() + INFLIGHT["n"] + r > CAP:
            raise Cap(f"cap ${CAP} would be exceeded: spent {spent():.3f}")
        INFLIGHT["n"] += r
    cost, txt, err, turns, t = 0.0, "", "", None, time.time()
    try:
        cmd = ["claude", BASE[0], "--model", model, *BASE[1:], *TOOLS] + (["--system-prompt", system] if system else [])
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=1500)
        try:
            j = json.loads(p.stdout)
            txt, cost, turns = j.get("result") or "", float(j.get("total_cost_usd") or 0), j.get("num_turns")
            err = "claude error" if (j.get("is_error") or p.returncode) else "" if txt.strip() else "empty output"
        except ValueError:
            err = f"exit {p.returncode}, unparsable"
    except (subprocess.TimeoutExpired, OSError) as e:
        err = type(e).__name__
    finally:
        with LOCK:
            INFLIGHT["n"] -= r
            with open(D / "ledger.jsonl", "a") as f:
                f.write(json.dumps(dict(tag=tag, model=model, cost=cost, sec=round(time.time() - t, 1), turns=turns, err=err)) + "\n")
    return txt, err, turns


def ws(cid, arm=None):
    w = Path(tempfile.mkdtemp(prefix="bench-"))
    shutil.copy(CORPUS / cid / "change.patch", w)
    if arm == "REAL":
        shutil.copytree(SKILL, w / ".claude/skills/deep-code-review")
    return w


def review(cid, arm):
    p = D / "outputs" / arm / f"{cid}.json"
    if p.exists() and not json.loads(p.read_text()).get("error"):
        return cid, "cached"
    p.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (1, 2):
        w = ws(cid, arm)
        try:
            txt, err, turns = call(bc.PERUN if arm == "REAL" else bc.PRODUCER, w, "claude-sonnet-5-5", TK if arm == "TK" else None, f"review/{arm}/{cid}/{attempt}")
        finally:
            shutil.rmtree(w, ignore_errors=True)
        f = None if err else bc.parse_array(txt)
        err = err or ("" if f is not None else "no JSON array in output")
        rec = dict(id=cid, arm=arm, findings=f or [], error=err, attempts=attempt, turns=turns)
        p.write_text(json.dumps(rec, indent=1))
        if not err:
            break
    return cid, rec["error"] or len(rec["findings"])


def verify(cid, arm):
    p = D / "outputs" / arm / f"{cid}.json"
    rec = json.loads(p.read_text())
    if rec.get("error") or "verdicts" in rec and not rec.get("verify_error"):
        return cid, "skip"
    truth = json.loads((CORPUS / cid / "ground-truth.json").read_text())
    rec["matched"] = [bool(sr.score(truth, [f])["hit"]) for f in rec["findings"]]
    rec["verdicts"] = {}; rec["verify_error"] = ""
    un = [(i, f) for i, f in enumerate(rec["findings"]) if not rec["matched"][i]]
    for attempt in (1, 2):
        if not un:
            break
        w = ws(cid)
        try:
            bug = "; ".join(b["bug"] for b in truth["bugs"])
            listing = "\n".join(f"{i}. [{f.get('file')}:{f.get('line')}] {f.get('text')}" for i, f in un)
            txt, err, _ = call(bc.VERIFY.format(bug=bug, findings=listing), w, "claude-opus-5-5", None, f"verify/{arm}/{cid}/{attempt}")
        finally:
            shutil.rmtree(w, ignore_errors=True)
        vs = None if err else bc.parse_array(txt, "verdict")
        rec["verify_error"] = err or ("" if vs is not None else "no JSON array in verifier output")
        rec["verdicts"] = {str(v.get("i")): {"verdict": v.get("verdict"), "reason": v.get("reason")} for v in vs or []}
        if not rec["verify_error"]:
            break
    p.write_text(json.dumps(rec, indent=1))
    return cid, rec["verify_error"] or len(un)


def stage(fn):
    try:
        with cf.ThreadPoolExecutor(JOBS) as ex:
            for r in ex.map(lambda ca: fn(*ca), [(c, a) for c in IDS for a in ("REAL", "TK")]):
                print(*r, f"spent={spent():.3f}", flush=True)
    except Cap as e:
        print("CAP STOP:", e, flush=True); (D / "INCOMPLETE").write_text(str(e))


def tally(rec, truth):
    """Same crediting as the earlier bench: good = strict match or judge real/gt_same; one bug per case, gt_same credits it."""
    vd = rec["verdicts"]; un = [i for i, m in enumerate(rec["matched"]) if not m]
    gts = any(vd.get(str(i), {}).get("verdict") == "gt_same" for i in un)
    good = sum(rec["matched"]) + sum(vd.get(str(i), {}).get("verdict") in ("real", "gt_same") for i in un)
    n_hit = len(sr.score(truth, rec["findings"])["hit"]); nb = len(truth["bugs"])
    return dict(n=len(rec["findings"]), good=good, bugs=nb, cred=nb if gts else n_hit)


def loadt(arm, cid, root=None):
    p = (root or D / "outputs") / arm / f"{cid}.json"
    if not p.exists(): return None
    rec = json.loads(p.read_text())
    if rec.get("error") or rec.get("verify_error") or "verdicts" not in rec: return None
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


def boot1(rows, B=10000, seed=1):
    rng = random.Random(seed); n = len(rows); ds = [[], [], []]
    for _ in range(B):
        s = stats([rows[rng.randrange(n)] for _ in range(n)])
        for k in range(3): ds[k].append(s[k])
    return [dict(v=round(stats(rows)[k], 3), ci=ci(ds[k], B)) for k in range(3)]


def report(prior):
    names = ("precision", "recall", "f1")
    rows, drops = [], []
    for c in IDS:
        a, b = loadt("REAL", c), loadt("TK", c)
        (rows.append((a, b)) if a and b else drops.append(c))
    A, T = [r[0] for r in rows], [r[1] for r in rows]
    out = dict(n=len(rows), dropped=drops, spend=round(spent(), 3), incomplete=(D / "INCOMPLETE").exists())
    for nm, X in (("REAL", A), ("TK", T)):
        b1 = boot1(X)
        out[nm] = dict(findings=sum(r["n"] for r in X), good=sum(r["good"] for r in X), cred=sum(r["cred"] for r in X), bugs=sum(r["bugs"] for r in X), **{names[k]: b1[k] for k in range(3)})
    out["REAL_minus_TK"] = dict(zip(names, boot(A, T)))
    led = [json.loads(l) for l in (D / "ledger.jsonl").read_text().splitlines()]
    out["cost"] = {}
    for kind, tag in (("REAL", "review/REAL"), ("TK", "review/TK"), ("judge", "verify/")):
        c = [x for x in led if x["tag"].startswith(tag)]; out["cost"][kind] = dict(calls=len(c), total=round(sum(x["cost"] for x in c), 3))
    for k in ("REAL", "TK"):
        ok = sorted(D.glob(f"outputs/{k}/*.json")); okc = [x["cost"] for x in led if x["tag"].startswith(f"review/{k}/") and not x["err"]]
        out["cost"][k]["per_review_mean_ok_calls"] = round(sum(okc) / max(1, len(okc)), 4)
        out["cost"][k]["turns_avg"] = round(sum((json.loads(f.read_text()).get("turns") or 0) for f in ok) / max(1, len(ok)), 1)
    if prior:  # earlier compact-mode (CF) and toolkit outputs, same cases, context only (no new spend)
        ctx = {}
        for nm in ("CF", "TK"):
            X = [t for c in IDS for t in [loadt(nm, c, Path(prior))] if t]
            b1 = boot1(X); ctx[nm] = dict(n=len(X), **{names[k]: b1[k] for k in range(3)})
        out["prior_run_same_cases"] = ctx
    (D / "results.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "run": stage(review)
    elif c == "verify": stage(verify)
    elif c == "report": report(sys.argv[2] if len(sys.argv) > 2 else None)
