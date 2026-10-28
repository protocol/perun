#!/usr/bin/env python3
"""prevention_lint.py FILE.md — every prevention/action item needs an owner, a tracking id and a verifiable end state.

WHY: "we will add monitoring" with no name, no ticket and no way to tell it is done is a wish. Reads each markdown table whose
header row has an `Owner` column, a tracking column (`Bug/issue`, `Ticket`, `Issue` or `Id`) and an end-state column (`Done when`,
`End state` or `Verify`). For every data row that has any text: Owner must be non-empty (not TBD/none/-), the tracking cell must
contain an id (`#123`, `ABC-123` or a URL), and the end-state cell must be non-empty (not TBD/none/-). Prints
`FAIL line N: <what is missing>` per defect and exits 1; exits 0 when every row passes; exits 2 when the file is unreadable or
has NO table with all three columns (fail closed: a plan without the columns is itself the defect). Blank template rows are skipped.
Side effects: none.
"""
import re
import sys

ID = re.compile(r"#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://\S+")
EMPTY = {"", "-", "tbd", "none", "n/a", "?"}


def col(header, *names):
    return next((i for i, h in enumerate(header) if re.sub(r"\s*\(.*\)", "", h).strip().lower() in names), None)


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def lint(text):
    """(defect lines, number of tables checked)."""
    bad, tables, hdr = [], 0, None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"):
            hdr = None
            continue
        c = cells(line)
        if hdr is None:
            o, t, e = col(c, "owner"), col(c, "bug/issue", "ticket", "issue", "id"), col(c, "done when", "end state", "verify")
            hdr = (o, t, e) if None not in (o, t, e) else False
            tables += bool(hdr)
            continue
        if hdr is False or all(set(x) <= set("-: ") for x in c) or not any(c):
            continue
        o, t, e = hdr
        for name, i, ok in (("owner", o, lambda v: v.lower() not in EMPTY), ("tracking id", t, lambda v: bool(ID.search(v))),
                            ("verifiable end state", e, lambda v: v.lower() not in EMPTY)):
            if i >= len(c) or not ok(c[i]):
                bad.append(f"FAIL line {n}: {name} missing")
    return bad, tables


def main(argv):
    if len(argv) != 1:
        print("usage: prevention_lint.py FILE.md", file=sys.stderr)
        return 2
    try:
        bad, tables = lint(open(argv[0], errors="replace").read())
    except OSError as e:
        print(f"prevention_lint: {e}", file=sys.stderr)
        return 2
    if not tables:
        print("FAIL: no table with Owner, tracking and end-state columns")
        return 2
    print("\n".join(bad) or "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
