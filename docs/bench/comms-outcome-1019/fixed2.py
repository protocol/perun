#!/usr/bin/env python3
"""Amendment A3 (AMENDMENT3.md): a gold `action` must be a step for the reader, not the drafting task.
usage: fixed2.py SPLIT [--drop | --fill N]   (audit.py's checks plus this one; audit.py and bench.py stay frozen)."""
import json, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixed  # noqa: F401  amendment A2
import audit
import bench as b

DRAFTING = re.compile(r"\b(draft|message to|email to)\b|\bsend\b[^.]*\b(message|email)\b", re.I)
_bad = audit.bad


def bad(sc):
    """audit.bad plus 'action' when the gold action describes writing or sending the message itself."""
    return _bad(sc) + (["action"] if DRAFTING.search(sc["action"]) else [])


audit.bad = bad  # audit.fill calls the module-level name

if __name__ == "__main__":
    split = sys.argv[1]
    if "--fill" in sys.argv:
        sys.exit(audit.fill(split, int(sys.argv[sys.argv.index("--fill") + 1])))
    S = b.load(split)
    fails = {s["id"]: bad(s) for s in S if bad(s)}
    print(f"{len(fails)}/{len(S)} fail", fails)
    if "--drop" in sys.argv:
        (b.D / f"scenarios_{split}.json").write_text(json.dumps([s for s in S if s["id"] not in fails], indent=1) + "\n")
