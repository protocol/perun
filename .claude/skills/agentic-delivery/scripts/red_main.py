#!/usr/bin/env python3
"""red_main.py — green-main alarm: every red test on the default branch needs a fix or an owner within 1h.

WHY: a red main with no owner is nobody's job, and every PR behind it inherits the noise. The rule (see
references/red-gate-triage.md "Green main has one owner"): one reserved slot owns red main; each red test gets a fix PR or
a named owner within RED_GRACE_H (1h). This check makes the rule measurable.

Input: a JSON list of red tests, `--file` (default .claude/red-main.json): [{"id": "test name", "since": "2026-01-02T03:04:05+00:00",
"owner": "lane-a", "fix": "PR 12"}]. `owner`/`fix` may be absent or empty. `since` is ISO-8601 (naive = UTC) or epoch seconds.
Output: `reds=N uncovered=U oldest_h=H` (uncovered = no owner and no fix, older than the grace) plus one `UNCOVERED id age_h` per row.
Thresholds (policy keys, default 0 = off; CLI --max-uncovered / --max-age-h override): `red_uncovered_max` alarms at U >= that,
`red_oldest_h` alarms when the oldest red is >= that many hours old (covered or not). Exit 1 on an alarm, 2 on bad input
(fail closed), 0 otherwise, and a missing file only while no threshold is set (with one, exit 2). Side effects: none (read-only). `--now EPOCH` pins the clock.
"""
import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
RED_GRACE_H = 1.0


def epoch(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    d = datetime.datetime.fromisoformat(v)
    return (d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)).timestamp()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", default=".claude/red-main.json")
    ap.add_argument("--max-uncovered", type=int)
    ap.add_argument("--max-age-h", type=float)
    ap.add_argument("--now", type=float)
    a = ap.parse_args(argv)
    try:
        import perun_policy
        pol = perun_policy.load()
        mu = pol["red_uncovered_max"] if a.max_uncovered is None else a.max_uncovered
        ma = pol["red_oldest_h"] if a.max_age_h is None else a.max_age_h
        if not os.path.exists(a.file) and (mu or ma):  # alarm on + no list = cannot tell green from unrecorded: fail closed
            print(f"red_main: {a.file} missing while an alarm threshold is set; create it (an empty list means green)", file=sys.stderr)
            return 2
        rows = json.load(open(a.file)) if os.path.exists(a.file) else []
        now = time.time() if a.now is None else a.now
        ages = [(r["id"], (now - epoch(r["since"])) / 3600, bool(r.get("owner") or r.get("fix"))) for r in rows]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"red_main: bad input: {e}", file=sys.stderr)
        return 2
    unc = [(i, h) for i, h, cov in ages if not cov and h > RED_GRACE_H]
    oldest = max((h for _, h, _ in ages), default=0.0)
    print(f"reds={len(ages)} uncovered={len(unc)} oldest_h={oldest:.1f}")
    for i, h in unc:
        print(f"UNCOVERED {i} {h:.1f}h")
    return 1 if (mu and len(unc) >= mu) or (ma and oldest >= ma) else 0


if __name__ == "__main__":
    sys.exit(main())
