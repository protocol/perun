#!/usr/bin/env python3
"""pregate_parity.py — may a faster checker run fail-fast before the authoritative gate?

Only after error parity is proven: on at least N (default 5) distinct past commits where the authoritative gate FAILED, the faster
checker failed too. `check <ledger.jsonl> [--min N]` reads one JSON object per line, {"sha", "gate_failed", "fast_failed"}, and exits 0
(prints "pregate allowed") only when parity holds; exit 1 names the reason. A commit where the gate failed and the fast checker passed
is a counterexample and blocks the pregate. Allowed means ORDER only: the fast checker may stop the run early on a red, a fast green never
skips the authoritative gate, and the gate stays the only thing that can pass a merge. Passing commits are ignored (no evidence of parity). `record` appends the gate-time observation (the project's gate wrapper calls it; this repo has no fast-checker caller of its own).
"""
import json
import sys


def verdict(rows, need=5):
    """(ok, reason) for ledger rows. Any row where the gate failed and the fast checker passed blocks, whatever came later."""
    bad = sorted({r.get("sha", "?") for r in rows if r.get("gate_failed") and not r.get("fast_failed")})
    seen = len({r.get("sha") for r in rows if r.get("gate_failed") and r.get("sha")})
    if bad:
        return False, f"fast checker missed {len(bad)} gate failure(s): {', '.join(s[:12] for s in bad)}"
    if seen < need:
        return False, f"parity unproven: {seen} of {need} failing commits recorded"
    return True, f"pregate allowed: fast checker matched {seen} failing commits; the authoritative gate still runs"


def record(ledger, sha, gate_failed, fast_failed):
    """Append one gate-time observation. Call it from the wrapper that runs both checkers on a commit (append-only, never rewritten)."""
    with open(ledger, "a") as f:
        f.write(json.dumps({"sha": sha, "gate_failed": gate_failed, "fast_failed": fast_failed}) + "\n")


def main(argv):
    if len(argv) == 6 and argv[1] == "record" and argv[4] in ("0", "1") and argv[5] in ("0", "1"):
        record(argv[2], argv[3], argv[4] == "1", argv[5] == "1")  # record <ledger> <sha> <gate_failed 0|1> <fast_failed 0|1>
        return 0
    if len(argv) < 3 or argv[1] != "check":
        print("usage: pregate_parity.py check <ledger.jsonl> [--min N] | record <ledger> <sha> <gate_failed 0|1> <fast_failed 0|1>", file=sys.stderr)
        return 2
    need = int(argv[argv.index("--min") + 1]) if "--min" in argv else 5
    try:
        with open(argv[2]) as f:
            rows = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError) as e:
        print(f"pregate unknown: {e}")
        return 2
    ok, why = verdict(rows, need)
    print(why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
