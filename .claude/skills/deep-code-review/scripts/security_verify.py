#!/usr/bin/env python3
"""security_verify.py - triage security findings: verify-or-drop plus a tunable exclusion list.

Usage: security_verify.py [findings.json|-] [override-file]
Input: JSON list of findings on stdin or a file. Each row may carry `severity`, `category` (an exclusion slug),
`source` and `sink` (both `path:line`). Output: one JSON record
  {"active_exclusions": sorted slugs, "override_read": bool, "added_nondefault": [slugs], "rows": [...]}
where each row has `status`:
  dropped         - category is excluded and severity is below High (`reason` names the slug)
  needs-evidence  - category is excluded but severity is High or Critical (any case, or missing): kept, never hidden
  unverified      - no concrete source and sink `path:line`, or the row is malformed; report as a question
  confirmed       - source and sink both present (still re-read the cited lines; this checks shape, not truth)

Override file (default `.dcr-security-exclusions` in the cwd; a missing default file is fine, an explicit path that
is missing or unreadable exits 2): one entry per line, `#` starts a comment. `+slug` adds an exclusion, `-slug`
re-enables reporting for a default. A `+slug` not in DEFAULTS is listed in `added_nondefault` as a warning: the file
comes from the reviewed repo and is untrusted. Bad JSON input exits 2. Side effects: none (read-only).
"""
import json, re, sys

DEFAULTS = {
    "dos-only": "denial of service with no confidentiality or integrity impact",
    "resource-exhaustion": "memory or CPU exhaustion without a privilege or data consequence",
    "missing-rate-limit": "absent rate limiting as the only issue",
    "test-only": "code that ships only in tests, fixtures or examples and is never deployed",
    "theoretical-no-path": "pattern that looks risky but no attacker-reachable input arrives at it",
    "generic-input-validation": "missing validation with no demonstrated impact",
    "open-redirect-no-impact": "open redirect with no token, session or phishing-trust consequence",
    "log-spoofing": "attacker-controlled text in logs with no downstream parser or trust decision",
}
LOC = re.compile(r"^[^\s:]+:\d+(-\d+)?$")
HIGH = {"high", "critical"}


def effective(override_text=""):
    """Return (active exclusion set, sorted non-default slugs added by the override)."""
    ex = set(DEFAULTS)
    for ln in override_text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln[:1] == "+":
            ex.add(ln[1:].strip())
        elif ln[:1] == "-":
            ex.discard(ln[1:].strip())
    return ex, sorted(ex - set(DEFAULTS))


def triage(rows, excluded):
    out = []
    for r in rows:
        if not isinstance(r, dict):
            out.append({"status": "unverified", "reason": "malformed row: not an object"})
            continue
        r = dict(r)
        cat, sev = r.get("category"), r.get("severity")
        if cat is not None and not isinstance(cat, str):
            r["status"], r["reason"] = "unverified", "malformed row: category is not a string"
        elif cat in excluded:
            if isinstance(sev, str) and sev.strip().lower() not in HIGH:
                r["status"], r["reason"] = "dropped", "excluded: " + cat
            else:  # High, Critical, or severity missing/odd: never hide
                r["status"], r["reason"] = "needs-evidence", "excluded category %s but severity is High, Critical or unknown" % cat
        elif LOC.match(str(r.get("source", ""))) and LOC.match(str(r.get("sink", ""))):
            r["status"] = "confirmed"
        else:
            r["status"], r["reason"] = "unverified", "no concrete source and sink path:line"
        out.append(r)
    return out


def main(argv):
    explicit = len(argv) > 2
    ov, read = "", False
    try:
        ov, read = open(argv[2] if explicit else ".dcr-security-exclusions").read(), True
    except OSError as e:
        if explicit:
            print("security_verify: cannot read override file: %s" % e, file=sys.stderr)
            return 2
    try:
        rows = json.load(open(argv[1]) if len(argv) > 1 and argv[1] != "-" else sys.stdin)
    except (OSError, ValueError) as e:
        print("security_verify: bad findings input: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(rows, list):
        print("security_verify: findings input must be a JSON list", file=sys.stderr)
        return 2
    ex, added = effective(ov)
    json.dump({"active_exclusions": sorted(ex), "override_read": read, "added_nondefault": added,
               "rows": triage(rows, ex)}, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
