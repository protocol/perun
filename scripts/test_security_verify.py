#!/usr/bin/env python3
"""Tests for security_verify.py (plain asserts; exits non-zero on failure)."""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, SD)
import security_verify as s  # noqa: E402

full = {"source": "app/views.py:10", "sink": "app/db.py:42"}
ex, _ = s.effective()


def st(row, e=ex):
    return s.triage([row], e)[0]["status"]


assert st(full) == "confirmed"
assert st({"source": "app/views.py:10"}) == "unverified", "missing sink"
assert st({"source": "a.py", "sink": "b.py:1"}) == "unverified", "no line number"
assert st({**full, "category": "dos-only", "severity": "Low"}) == "dropped"
assert st({"category": "sqli"}) == "unverified", "unlisted category is not dropped"
# High / Critical never dropped, any case; missing severity fails open to keep
for sev in ("High", "high", "CRITICAL", " Critical "):
    assert st({**full, "category": "dos-only", "severity": sev}) == "needs-evidence", sev
assert st({**full, "category": "dos-only"}) == "needs-evidence", "no severity kept"
# override: re-enable, and non-default + warning
ov, added = s.effective("# c\n-dos-only  # we care\n+internal-tool\n-nonexistent\n")
assert "dos-only" not in ov and "internal-tool" in ov and "test-only" in ov
assert added == ["internal-tool"], added
assert st({**full, "category": "dos-only", "severity": "Low"}, ov) == "confirmed"
assert st({"category": "internal-tool", "severity": "Low"}, ov) == "dropped"
assert st({"category": "internal-tool", "severity": "High"}, ov) == "needs-evidence", "+slug never hides High"
# malformed rows: no crash
bad = s.triage(["x", 3, None, {"category": ["a"]}, {"category": 5}], ex)
assert [r["status"] for r in bad] == ["unverified"] * 5 and all(r["reason"] for r in bad)

# CLI: record fields, missing default file ok, explicit missing path exits non-zero, bad JSON exits non-zero
exe = os.path.join(SD, "security_verify.py")


def run(args, inp):
    with tempfile.TemporaryDirectory() as t:
        return subprocess.run([sys.executable, exe] + args, input=inp, capture_output=True, text=True, cwd=t)


p = run(["-"], json.dumps([full]))
rec = json.loads(p.stdout)
assert p.returncode == 0 and set(rec) == {"active_exclusions", "override_read", "added_nondefault", "rows"}
assert rec["override_read"] is False and rec["added_nondefault"] == [] and rec["active_exclusions"] == sorted(s.DEFAULTS)
assert rec["rows"][0]["status"] == "confirmed"
assert run(["-", "/nonexistent/override"], "[]").returncode != 0, "explicit missing path"
bj = run(["-"], "{not json")
assert bj.returncode != 0 and "bad findings input" in bj.stderr
assert run(["-"], '{"a": 1}').returncode != 0, "non-list input"
with tempfile.TemporaryDirectory() as t:
    with open(os.path.join(t, ".dcr-security-exclusions"), "w") as fh:
        fh.write("+custom\n")
    p = subprocess.run([sys.executable, exe, "-"], input="[]", capture_output=True, text=True, cwd=t)
    rec = json.loads(p.stdout)
    assert rec["override_read"] is True and rec["added_nondefault"] == ["custom"]
print("ok")
