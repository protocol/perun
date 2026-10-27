#!/usr/bin/env python3
"""finding_verdict.py <findings.json>... — strict verdict gate for machine-report gap rows that carry a `verdict`.

Purpose: stop an unproven claim from reaching the report as a ranked finding. Rows without `verdict` are legacy rows and
are not checked (use `validate_rows` to require it). Rules per gap row (polarity absent or `gap`):
  confirmed        needs root_cause, observation (the observed result), fix (the remediation), severity, demonstrated_impact,
                   hunter, verifier and rechecked_by. verifier and rechecked_by must differ from hunter (the finder never
                   grades or finalizes its own claim). severity may not rank above demonstrated_impact. Only this verdict may
                   carry severity.
  needs_validation needs blockers (non-empty list) and validation_plan; no severity. It is a question: merge_findings.py lists it
                   under `needs_validation`, never in the ranked `findings`.
  rejected         needs reject_reason; no severity.
Any field outside FIELDS is an error; severity/demonstrated_impact must be Blocker|Critical|High|Medium|Low|Nit|Info.
Output: {"ok": bool, "errors": [{"id", "error"}]} on stdout. Exit 0 when ok, 1 on any error, 2 on unreadable input.
Side effects: none (read-only).
"""
import json, sys

RANK = {"blocker": -1, "critical": 0, "high": 1, "medium": 2, "low": 3, "nit": 4, "info": 4}
BASE = {"id", "title", "area", "tag", "polarity", "confidence", "confidence_score", "latent", "mechanism_unproven", "observation",
        "evidence", "snippet", "mechanism", "fix", "compounds", "prior_id", "prior_status", "resolves_with", "grounded", "ground_reason"}
EXTRA = {"verdict", "severity", "root_cause", "demonstrated_impact", "hunter", "verifier", "rechecked_by", "blockers",
         "validation_plan", "reject_reason"}
FIELDS = BASE | EXTRA
NEED = {
    "confirmed": ("root_cause", "observation", "fix", "severity", "demonstrated_impact", "hunter", "verifier", "rechecked_by"),
    "needs_validation": ("blockers", "validation_plan"),
    "rejected": ("reject_reason",),
}


def norm_sev(v):
    """Lowercase, stripped severity label (the one place every consumer normalizes it)."""
    return str(v).strip().lower() if isinstance(v, str) else ""


def _s(v):
    return isinstance(v, str) and bool(v.strip())


def _same(a, b):
    return _s(a) and _s(b) and a.strip().lower() == b.strip().lower()


def check_row(f):
    """Return the list of rule violations for one gap row that has a `verdict` key."""
    v, errs = f.get("verdict"), []
    if not isinstance(v, str) or v not in NEED:
        return [f"verdict must be one of {sorted(NEED)}"]
    errs += [f"unknown field: {k}" for k in sorted(set(f) - FIELDS)]
    for k in NEED[v]:
        val = f.get(k)
        if not (isinstance(val, list) and val and all(map(_s, val)) if k == "blockers" else _s(val)):
            errs.append(f"{v} requires {k}")
    if v != "confirmed" and "severity" in f:
        errs.append(f"{v} must not carry severity")
    if v != "confirmed" and f.get("demonstrated_impact") is not None:
        errs.append(f"{v} must not carry demonstrated_impact")
    if v == "confirmed":
        sev, imp = norm_sev(f.get("severity")), norm_sev(f.get("demonstrated_impact"))
        for k, x in (("severity", sev), ("demonstrated_impact", imp)):
            if f.get(k) is not None and x not in RANK:
                errs.append(f"{k} is not a known level")
        if sev in RANK and imp in RANK and RANK[sev] < RANK[imp]:
            errs.append("severity exceeds demonstrated_impact")
        for k in ("verifier", "rechecked_by"):
            if _same(f.get(k), f.get("hunter")):
                errs.append(f"{k} must differ from hunter")
    return errs


def norm_pol(f):
    """Normalized polarity: `strength` only when explicitly so; anything else (absent, null, odd case) is a gap."""
    p = f.get("polarity")
    return p.strip().lower() if isinstance(p, str) and p.strip().lower() == "strength" else "gap"


def validate_rows(rows, require=False):
    """Check gap rows; `require=True` also rejects gap rows with no `verdict`. Returns [{"id", "error"}]."""
    out = []
    for f in rows:
        if not isinstance(f, dict):
            out.append({"id": None, "error": "row is not an object"})
        elif norm_pol(f) != "strength" and ("verdict" in f or require):
            out += [{"id": f.get("id"), "error": e} for e in check_row(f)]
    return out


def main(argv):
    if len(argv) < 2:
        print("usage: finding_verdict.py <findings.json>...", file=sys.stderr)
        return 2
    try:
        rows = []
        for p in argv[1:]:
            with open(p, encoding="utf-8") as fh:
                rows += json.load(fh)["findings"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"finding_verdict: cannot read findings: {type(e).__name__}", file=sys.stderr)
        return 2
    errs = validate_rows(rows)
    print(json.dumps({"ok": not errs, "errors": errs}, indent=2))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
