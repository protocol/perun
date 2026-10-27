#!/usr/bin/env python3
"""merge_findings.py [--cap N] [--root DIR] [--ref REF] <findings.json>... — dedupe, rank and cap findings from one or more passes.

Purpose: cut review noise. Inputs are findings files; every gap row is re-checked here with finding_ground_check.check (any
caller-supplied `grounded` flag is overwritten, so it cannot bypass the gate; --root/--ref as there).
Steps: drop gap rows whose numeric `confidence_score` is below 80 (MIN_CONF; DIFF scope only: skipped when any input's top-level `scope` is FULL/FILE; `confidence: unverified` leads exempt; rows without one pass, and the string `confidence` tier is never read); drop ungrounded gap rows; dedupe by (file of first evidence, `mechanism`, falling back to the
normalized title, then the id) when first-evidence lines are within 10, keeping the highest-severity row
(the first on a tie) and unioning evidence; rank Blocker>Critical>High>Medium>Low>Nit/Info (stable); keep the top
--cap (default 20). Strength rows pass through uncapped. Output: {"findings": [...], "dropped":
{"low_confidence": n, "ungrounded": n, "duplicate": n, "over_cap": n}} on stdout. Gap rows that carry a `verdict` are first checked with finding_verdict.check_row: invalid rows (listed under `verdict_errors`) and `rejected` rows are dropped, `needs_validation` rows are listed under `needs_validation` and never ranked (counted under `dropped.invalid_verdict` / `dropped.rejected`, keys present only when nonzero). An empty `findings` list is a valid result:
a clean diff yields NONE. If an input carries a machine-report `coverage` map, a `not-applicable` row without non-empty `probe` (what was
searched) and `fact` (what fired) is prose-only: it is downgraded to `not-scanned` and listed under `na_flagged` in the output. Exit 0, or 2 on usage/unreadable input. Side effects: none.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finding_ground_check import check, parse  # noqa: E402
from finding_verdict import check_row, norm_pol, norm_sev  # noqa: E402

NEAR = 10  # same file+mechanism merges only when first-evidence lines are within this many lines
MIN_CONF = 80  # method.md anti-slop / compact-mode.md: report only findings scored >= 80 that this change causes a real failure
SEV = {"blocker": -1, "critical": 0, "high": 1, "medium": 2, "low": 3, "nit": 4, "info": 4}


def _sev(f):
    return SEV.get(norm_sev(f.get("severity")), 5)


def _key(f):
    p = parse((f.get("evidence") or [""])[0])
    mech = f.get("mechanism") or re.sub(r"\W+", " ", f.get("title", "")).strip() or "id:" + str(f.get("id"))
    return (p[0] if p else "", mech.lower()), (p[1] if p else 0)


def merge(rows, cap=20, root=".", ref=None, floor=True):
    drop = {"low_confidence": 0, "ungrounded": 0, "duplicate": 0, "over_cap": 0}
    strengths, best, bad, questions = [], {}, [], []
    for f in rows:
        if "verdict" in f and norm_pol(f) != "strength":  # opt-in strict verdict rows (finding_verdict.py); fail closed
            errs = check_row(f)
            if errs or f["verdict"] in ("rejected", "needs_validation"):
                k = "invalid_verdict" if errs else f["verdict"]
                if k == "needs_validation":
                    questions.append(f)
                else:
                    drop[k] = drop.get(k, 0) + 1
                bad += [{"id": f.get("id"), "error": e} for e in errs]
                continue
        elif f.get("polarity", "gap") != "gap":
            strengths.append(f)
            continue
        c = f.get("confidence_score")
        if floor and f.get("confidence") != "unverified" and isinstance(c, (int, float)) and not isinstance(c, bool) and c < MIN_CONF:
            drop["low_confidence"] += 1
            continue
        f["grounded"], f["ground_reason"] = check(f, root, ref)  # never trust a caller-supplied flag
        if not f["grounded"]:
            drop["ungrounded"] += 1
            continue
        k, line = _key(f)
        group = best.setdefault(k, [])
        i = next((i for i, (ln, _) in enumerate(group) if abs(ln - line) <= NEAR), None)
        if i is None:
            group.append((line, f))
            continue
        drop["duplicate"] += 1
        old = group[i][1]
        keep, other = (old, f) if _sev(old) <= _sev(f) else (f, old)
        keep["evidence"] = list(dict.fromkeys((keep.get("evidence") or []) + (other.get("evidence") or [])))
        group[i] = (line if keep is f else group[i][0], keep)
    ranked = sorted((f for g in best.values() for _, f in g), key=_sev)
    drop["over_cap"] = max(0, len(ranked) - cap)
    out = {"findings": ranked[:cap] + strengths, "dropped": drop}
    if bad:
        out["verdict_errors"] = bad
    if questions:
        out["needs_validation"] = questions
    return out


def na_gate(coverage):
    """Downgrade prose-only not-applicable coverage rows to not-scanned; return (coverage, flagged domains)."""
    out, flagged = {}, []
    for d, row in coverage.items():
        row = dict(row) if isinstance(row, dict) else {}
        if row.get("status") == "not-applicable" and not (str(row.get("probe", "")).strip() and str(row.get("fact", "")).strip()):
            row["status"] = "not-scanned"
            flagged.append(d)
        out[d] = row
    return out, flagged


def main(argv):
    args, cap, root, ref = argv[1:], 20, os.getcwd(), None
    while args[:1] in (["--cap"], ["--root"], ["--ref"]):
        try:
            v = args[1]
            if args[0] == "--cap":
                cap = int(v)
            elif args[0] == "--root":
                root = v
            else:
                ref = v
            args = args[2:]
        except (IndexError, ValueError):
            args = []
    if not args or cap < 0:
        print("usage: merge_findings.py [--cap N] [--root DIR] [--ref REF] <findings.json>...", file=sys.stderr)
        return 2
    try:
        rows, cov, floor = [], {}, True
        for p in args:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            floor = floor and str(d.get("scope") or "DIFF").upper().startswith("DIFF")  # FULL/FILE keep pre-existing findings
            rows += d["findings"]
            cov.update(d.get("coverage") or {})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"merge_findings: cannot read findings: {type(e).__name__}", file=sys.stderr)
        return 2
    out = merge(rows, cap, root, ref, floor)
    if cov:
        out["coverage"], out["na_flagged"] = na_gate(cov)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
