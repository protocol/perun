#!/usr/bin/env python3
"""Paid held-out confirmation (PREREGISTERED-V2.md). One claude -p review per (case, arm) on the 22 held-out cases, same model for all arms.
Arms: V2 = V2 skill body as --system-prompt (same harness as TK); V2s = V2 skill copy in the workspace, PERUN prompt (descriptive only);
BASE = unedited skill in the workspace, PERUN prompt; TK = rival system prompt. Hard cap CAP USD by ledger (reserve checked before each call),
abort at plan-quota utilization >= 0.8 or on a missing reading (fail closed). Judging is driver.py judge (free PCSS), keep rule is verdict().
usage: SKILL_DIR=<V2 skill copy> confirm.py run | judge | verdict"""
import concurrent.futures as cf, json, os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

import driver as d

D = d.D
OUT = D / "runs-claude"
LEDGER = D / "ledger.jsonl"
MODEL, CAP, RESERVE, QUOTA_STOP, JOBS = "claude-sonnet-5-5", 25.0, 0.30, 0.8, 2
ARMS = ("V2", "V2s", "BASE", "TK")
BASE_SKILL = d.ROOT / ".claude/skills/deep-code-review"
FLAGS = ["-p", "--setting-sources", "project,local", "--strict-mcp-config", "--no-session-persistence", "--output-format", "stream-json", "--verbose",
         "--tools", "Read,Grep,Glob", "--allowedTools", "Read", "Grep", "Glob", "--max-budget-usd", str(RESERVE)]
LOCK, ST = threading.Lock(), dict(inflight=0.0, util=0.0)


class Stop(Exception):
    pass


def spent():
    return sum(json.loads(l).get("cost", 0) for l in LEDGER.read_text().splitlines()) if LEDGER.exists() else 0.0


def call(prompt, cwd, system, tag):
    """One ledgered claude -p call -> (text, error, usage). Cap and quota are checked before the call; the quota reading must be present."""
    with LOCK:
        if ST["util"] >= QUOTA_STOP:
            raise Stop(f"plan quota utilization {ST['util']:.2f} >= {QUOTA_STOP}")
        if spent() + ST["inflight"] + RESERVE > CAP:
            raise Stop(f"cap ${CAP} would be exceeded: spent {spent():.3f}")
        ST["inflight"] += RESERVE
    txt, err, cost, use, util, seen, t = "", "", 0.0, {}, 0.0, False, time.time()
    try:
        p = subprocess.run(["claude", "--model", MODEL, *FLAGS] + (["--system-prompt", system] if system else []), input=prompt, capture_output=True, text=True, cwd=cwd, timeout=900)
        for line in p.stdout.splitlines():
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("type") == "rate_limit_event":
                ws = (j.get("rate_limit_info") or {}).get("unifiedWindows") or {}
                util, seen = max([util] + [float(v.get("utilization") or 0) for v in ws.values()]), seen or bool(ws)
            elif j.get("type") == "result":
                txt, cost, use = j.get("result") or "", float(j.get("total_cost_usd") or 0), dict(j.get("usage") or {}, turns=j.get("num_turns"))
                err = "claude error" if j.get("is_error") else "" if txt.strip() else "empty output"
        err = err or ("" if use else f"exit {p.returncode}, no result event")
    except subprocess.TimeoutExpired:
        cost, err = RESERVE, "timeout"  # unknown spend: charge the whole reserve
    finally:
        with LOCK:
            ST["inflight"] -= RESERVE
            if seen:
                ST["util"] = max(ST["util"], util)
            with open(LEDGER, "a") as f:
                f.write(json.dumps(dict(ts=int(time.time()), iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), event="call", tag=tag, model=MODEL, cost=cost, sec=round(time.time() - t, 1), util=util if seen else None, err=err)) + "\n")
    if not seen:
        raise Stop("no plan-quota utilization reading (fail closed)")
    return txt, err, use


def tokens(u):
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))


def review(cid, arm):
    p = OUT / arm / f"{cid}.json"
    if p.exists() and not json.loads(p.read_text()).get("error"):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    sysp = d.system_for(arm) if arm in ("V2", "TK") else None
    skill = {"V2s": d.SKILL, "BASE": BASE_SKILL}.get(arm)
    for attempt in (1, 2):
        w = Path(tempfile.mkdtemp(prefix="cbench-"))
        shutil.copy(d.CORPUS / cid / "change.patch", w)
        if skill:
            shutil.copytree(skill, w / ".claude/skills/deep-code-review")
        try:
            txt, err, use = call(d.bc.PRODUCER if sysp else d.bc.PERUN, w, sysp, f"{arm}/{cid}/{attempt}")
        finally:
            shutil.rmtree(w, ignore_errors=True)
        f = None if err else d.bc.parse_array(txt)
        err = err or ("" if f is not None else "no JSON array in output")
        rec = dict(id=cid, arm=arm, findings=f or [], error=err, attempts=attempt, turns=use.get("turns") or 0, tokens=tokens(use), usage=use)
        p.write_text(json.dumps(rec, indent=1))
        if not err:
            break


def run():
    d.OUT = OUT
    call("Be terse. Reply ok.", tempfile.gettempdir(), "You answer in one word.", "probe")  # quota probe before any real call
    def one(cid):
        for arm in ARMS:
            review(cid, arm)
        return cid
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for c in ex.map(one, d.SPLIT["heldout"]):
            print(c, f"spent {spent():.3f}", flush=True)


def judge():
    d.OUT = OUT
    for a in ARMS:
        d.stage(d.judge, a, d.SPLIT["heldout"])


def decide(f1, ratio):
    """f1 = dict(d=point, ci=[lo, hi]) of F1(V2)-F1(TK); ratio = tokens(V2)/tokens(TK). Rule A or rule B keeps, else revert."""
    a = f1["d"] >= 0 and f1["ci"][0] >= -0.05 and ratio <= 1.0
    b = f1["ci"][0] > 0 and ratio <= 2.0
    return dict(rule_A=a, rule_B=b, decision="keep" if a or b else "revert")


def verdict():
    """Keep rule (PREREGISTERED-V2.md): A = F1(V2)-F1(TK) point >= 0 and CI lower >= -0.05 and tokens(V2) <= tokens(TK); B = CI lower > 0 and tokens(V2) <= 2 x tokens(TK)."""
    d.OUT = OUT
    n = ("precision", "recall", "f1")
    rows = {a: {c: d.loadt(a, c) for c in d.SPLIT["heldout"]} for a in ARMS}
    H = [c for c in d.SPLIT["heldout"] if rows["V2"][c] and rows["TK"][c]]
    pick = lambda a, cs: [rows[a][c] for c in cs]  # noqa: E731
    mean = lambda X: round(sum(r["tokens"] for r in X) / max(1, len(X)), 1)  # noqa: E731
    out = dict(n=len(H), dropped_V2_TK=[c for c in d.SPLIT["heldout"] if c not in H], spent_usd=round(spent(), 4), arms={})
    for a in ARMS:
        cs = [c for c in H if rows[a][c]]
        out["arms"][a] = dict(n=len(cs), f1=round(d.stats(pick(a, cs))[2], 3), tokens=mean(pick(a, cs)), turns=round(sum(r["turns"] for r in pick(a, cs)) / max(1, len(cs)), 2),
                              minus_TK=dict(zip(n, d.boot(pick(a, cs), pick("TK", cs)))) if cs else None)
    f1 = out["arms"]["V2"]["minus_TK"]["f1"]; ratio = out["arms"]["V2"]["tokens"] / out["arms"]["TK"]["tokens"]
    out["keep"] = dict(token_ratio_V2_over_TK=round(ratio, 3), **decide(f1, ratio))
    (D / "results-heldout.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"run": run, "judge": judge, "verdict": verdict}[sys.argv[1]]()
