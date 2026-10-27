#!/usr/bin/env python3
"""coverage_ledger.py [--domains SPEC] <findings.json> — completeness check for a machine-report `coverage` map.

Purpose: the mechanical form of method.md's coverage ledger. Every assigned domain (default A-T and W; SPEC like `A-F,W`)
needs a row. `scanned` passes; `partial` and `not-scanned` need a non-empty `note` (why: declined or blocked);
`not-applicable` needs non-empty `probe` and `fact`. An optional `units` list (fan-out manifest rows: id, status, finder,
lead_read, note) follows the same rule: `scanned` needs a finder and lead_read true, any other status needs a note.
Any row that is not fully scanned makes the run incomplete, so the top-level `incomplete_reason` must then be non-empty
(a consumer must be able to tell a clean run from a partial one). Output: {"ok": bool, "errors": [str], "incomplete": bool}.
Exit 0 when ok, 1 on any error, 2 on unreadable input or a bad SPEC. Side effects: none (read-only).
"""
import json, re, sys

STATUS = ("scanned", "partial", "not-scanned", "not-applicable")


def _s(v):
    return isinstance(v, str) and bool(v.strip())


def parse_domains(spec):
    out = []
    for part in spec.split(","):
        m = re.fullmatch(r"([A-Z])(?:-([A-Z]))?", part.strip())
        if not m or (m[2] and m[2] < m[1]):
            raise ValueError(spec)
        out += [chr(c) for c in range(ord(m[1]), ord(m[2] or m[1]) + 1)]
    return out


def check(doc, domains):
    """Return (errors, incomplete) for a findings document and the list of assigned domain letters."""
    errs, incomplete = [], False
    cov, units = doc.get("coverage"), doc.get("units", [])
    if not isinstance(cov, dict):
        return ["coverage map missing"], True
    for d in domains:
        r = cov.get(d)
        if not isinstance(r, dict):
            errs.append(f"{d}: no coverage row")
            incomplete = True
            continue
        st = r.get("status")
        if st not in STATUS:
            errs.append(f"{d}: status must be one of {list(STATUS)}")
        elif st == "not-applicable" and not (_s(r.get("probe")) and _s(r.get("fact"))):
            errs.append(f"{d}: not-applicable needs probe and fact")
        elif st in ("partial", "not-scanned") and not _s(r.get("note")):
            errs.append(f"{d}: {st} needs a note saying why")
        incomplete = incomplete or st in ("partial", "not-scanned")
    if not isinstance(units, list):
        errs.append("units must be a list")
        incomplete, units = True, []
    for u in units:
        u = u if isinstance(u, dict) else {}
        uid, st = u.get("id", "?"), u.get("status")
        if st == "scanned":
            if not (_s(u.get("finder")) and u.get("lead_read") is True):
                errs.append(f"unit {uid}: scanned needs finder and lead_read true")
                incomplete = True
        else:
            incomplete = True
            if not _s(u.get("note")):
                errs.append(f"unit {uid}: {st or 'no status'} needs a note saying why")
    if incomplete and not _s(doc.get("incomplete_reason")):
        errs.append("incomplete run needs incomplete_reason")
    return errs, incomplete


def main(argv):
    args, spec = argv[1:], "A-T,W"
    if args[:1] == ["--domains"]:
        spec, args = (args[1:2] or [""])[0], args[2:]
    try:
        domains = parse_domains(spec)
        with open(args[0], encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or len(args) != 1:
            raise ValueError
    except (IndexError, OSError, ValueError, TypeError) as e:
        print(f"usage: coverage_ledger.py [--domains SPEC] <findings.json> ({type(e).__name__})", file=sys.stderr)
        return 2
    errs, inc = check(doc, domains)
    print(json.dumps({"ok": not errs, "errors": errs, "incomplete": inc}, indent=2))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
