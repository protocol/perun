#!/usr/bin/env python3
"""admission_check.py — flag a per-PR admission config that omits a test class the batch (merge train) runs, and a stale spec-selection map.

WHY: admission that runs only typecheck + unit lets a PR in whose browser/e2e spec then refuses the whole batch. Every class that can
refuse the batch must also run, scoped to the affected specs, at admission. The map that picks those specs (changed path -> spec) rots
silently: a stale map under-selects and the gap only shows when the batch goes red, so it needs a named refresh owner and an age alarm.

Input: `--file` (default .claude/admission.json): {"batch_classes": ["typecheck","unit","e2e"], "admission_classes": ["typecheck","unit"],
"map_owner": "lane-or-person", "map_refreshed": "2026-01-02T03:04:05+00:00" (ISO, naive = UTC, or epoch seconds), "map_max_age_h": 168}.
Output: one `MISSING class` per batch class absent at admission, `MAP-NO-OWNER`, `MAP-STALE age_h` rows; exit 1 when any, 0 clean.
`--base REF` reads batch_classes from REF's copy of the file (git show), so a PR cannot drop a class by editing its own config; the train passes
origin/<base>. Fail closed: unreadable/missing file, a missing/ill-typed key, a non-string or blank map_owner, or a future map_refreshed exits 2
(an absent config is not a pass). train_land.sh runs this (exit 2 on rc != 0) whenever the base branch carries the file. Read-only. `--now EPOCH` pins the clock.
"""
import argparse
import datetime
import json
import subprocess
import sys
import time


def epoch(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    d = datetime.datetime.fromisoformat(v)
    return (d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)).timestamp()


def check(cfg, now):
    out = [f"MISSING {c}" for c in cfg["batch_classes"] if c not in cfg["admission_classes"]]
    if not isinstance(cfg["map_owner"], str) or not cfg["map_owner"].strip():
        out.append("MAP-NO-OWNER")
    age = (now - epoch(cfg["map_refreshed"])) / 3600
    if age < 0:
        raise ValueError("map_refreshed is in the future")
    if age > float(cfg["map_max_age_h"]):
        out.append(f"MAP-STALE {age:.1f}h > {cfg['map_max_age_h']}h")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", default=".claude/admission.json")
    ap.add_argument("--base")
    ap.add_argument("--now", type=float)
    a = ap.parse_args(argv)
    try:
        cfg = json.load(open(a.file))
        if a.base:  # trusted batch_classes: the base branch's copy, not the PR's
            cfg["batch_classes"] = json.loads(subprocess.run(["git", "show", f"{a.base}:{a.file}"], capture_output=True, text=True, check=True).stdout)["batch_classes"]
        if not all(isinstance(cfg[k], list) and cfg[k] for k in ("batch_classes", "admission_classes")):
            raise ValueError("batch_classes and admission_classes must be non-empty lists")
        rows = check(cfg, time.time() if a.now is None else a.now)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"admission_check: bad input: {e!r}", file=sys.stderr)
        return 2
    print("\n".join(rows) if rows else "admission ok")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
