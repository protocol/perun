#!/usr/bin/env python3
"""Paid run of the frozen token-voice bench via `claude -p` (PCSS budget exhausted). Frozen files are untouched.

  run_claude.py [--samples K] [--jobs N] [--model M] [--cap USD]   resumes from runs.jsonl; stops at the spend cap.

Each call: replaced system prompt (frozen prompts/<arm>.txt), no tools, no settings/hooks/CLAUDE.md, no session persistence.
Adds `cost_usd` per record. Completion tokens = output_tokens from the CLI usage block.
"""
import argparse, concurrent.futures as cf, json, subprocess, sys, threading
from pathlib import Path
import bench as B

H, D = B.H, B.D


def call(model, system, user):
    p = subprocess.run(["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "", "--setting-sources", "",
                        "--no-session-persistence", "--output-format", "json", "--disable-slash-commands"],
                       input=user, capture_output=True, text=True, timeout=300, cwd="/tmp", env={**__import__("os").environ, "MAX_THINKING_TOKENS": "0"})
    j = json.loads(p.stdout)
    if j.get("is_error"):
        raise RuntimeError(str(j.get("result"))[:200])
    u = j["usage"]
    return j["result"], u["output_tokens"], u["input_tokens"] + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0), j["stop_reason"] if "stop_reason" in j else None, j["total_cost_usd"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--cap", type=float, default=15.0)
    a = ap.parse_args()
    sysm = {x: (D / "prompts" / f"{x}.txt").read_text() for x in B.ARMS}
    log = D / "runs.jsonl"
    done = {(r["arm"], r["id"], r["sample"]) for r in map(json.loads, log.read_text().splitlines())} if log.exists() else set()
    spent = sum(json.loads(l).get("cost_usd", 0) for l in log.read_text().splitlines()) if log.exists() else 0.0
    todo = [(x, t, k) for k in range(a.samples) for t in B.tasks() for x in B.ARMS if (x, t["id"], k) not in done]
    lock, st = threading.Lock(), {"spent": spent}

    def one(j):
        x, t, k = j
        if st["spent"] >= a.cap:
            return
        try:
            reply, ct, pt, fin, cost = call(a.model, sysm[x], H.user_prompt(t))
        except Exception as e:
            print(f"skip {x}/{t['id']}/{k}: {type(e).__name__} {e}", file=sys.stderr)
            return
        ok, why = H.run_hidden(H.extract_code(reply), t["test"])
        rec = {"arm": x, "id": t["id"], "sample": k, "pass": ok, "why": why, "completion_tokens": ct, "prompt_tokens": pt, "finish": fin, "cost_usd": cost, "reply": reply}
        with lock:
            st["spent"] += cost
            log.open("a").write(json.dumps(rec) + "\n")

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, todo))
    print(f"spent ${st['spent']:.4f} of cap ${a.cap}")


if __name__ == "__main__":
    main()
