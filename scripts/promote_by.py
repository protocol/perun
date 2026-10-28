#!/usr/bin/env python3
"""promote_by.py - ratchet so a shadow (default-off) flag cannot stay in shadow forever.

Every policy key in perun_policy.py whose default is `shadow` needs a row in scripts/promote-by.tsv: `flag<TAB>YYYY-MM-DD<TAB>decision`.
`check(today)` returns problems: a shadow flag with no row, a malformed date, a row for a flag that is no longer shadow (delete it),
or a row past its date (promote it, or keep it by recording the decision and moving the date; a date more than 120 days out also fails, so "keep" cannot be forever).
Usage: promote_by.py [YYYY-MM-DD]  (default today, exit 1 on any problem). Side effects: none.
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".claude/skills/agentic-delivery/scripts"))
import perun_policy  # noqa: E402


def check(today, tsv=os.path.join(HERE, "promote-by.tsv")):
    rows = {}
    for l in __import__("pathlib").Path(tsv).read_text(encoding="utf-8").splitlines():  # missing file = fail closed (raises)
        if l.strip() and not l.startswith("#"):
            c = l.split("\t")
            rows[c[0]] = (c[1] if len(c) > 1 else "", c[2].strip() if len(c) > 2 else "")
    shadow = sorted(k for k, v in perun_policy.validate({}).items() if v == "shadow")
    bad = [f"{k}: shadow by default but has no promote-by row" for k in shadow if k not in rows]
    for k, (d, dec) in sorted(rows.items()):
        if k not in shadow:
            bad.append(f"{k}: row but the flag is not shadow by default; delete the row")
            continue
        try:
            due = datetime.date.fromisoformat(d)
        except ValueError:
            bad.append(f"{k}: bad promote-by date {d!r}")
            continue
        if due < today:
            bad.append(f"{k}: promote-by {d} is overdue (promote it, or record the decision and move the date)")
        elif (due - today).days > 120:
            bad.append(f"{k}: promote-by {d} is more than 120 days out")
        elif not dec and (due - today).days > 60:
            bad.append(f"{k}: a date more than 60 days out needs a recorded decision")
    return bad


if __name__ == "__main__":
    t = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.datetime.now(datetime.timezone.utc).date()
    p = check(t)
    print("\n".join("promote_by: " + x for x in p), file=sys.stderr)
    sys.exit(1 if p else 0)
