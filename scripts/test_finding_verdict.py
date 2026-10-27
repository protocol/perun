#!/usr/bin/env python3
"""Tests for finding_verdict.py, its merge_findings hook and the security_verify fresh-verifier rule (plain asserts)."""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, SD)
import finding_verdict as fv, merge_findings as mf, security_verify as sv  # noqa: E402

OK = {"id": "F1", "verdict": "confirmed", "severity": "High", "demonstrated_impact": "High", "root_cause": "unescaped id",
      "observation": "GET /a?id=1' returns 500 and the SQL text", "fix": "bind the parameter", "hunter": "u1", "verifier": "u2",
      "rechecked_by": "lead", "evidence": ["a.py:1"], "snippet": "code line one"}


def errs(**kw):
    row = {**OK, **kw}
    for k in [k for k, v in kw.items() if v is None]:
        del row[k]
    return fv.check_row(row)


assert errs() == []
for k in ("root_cause", "observation", "fix", "severity", "demonstrated_impact", "hunter", "verifier", "rechecked_by"):
    assert errs(**{k: None}), k
    assert errs(**{k: "  "}), k
assert errs(severity="Critical") == ["severity exceeds demonstrated_impact"]
assert errs(severity="Low") == [], "below demonstrated impact is allowed"
assert errs(severity="Huge") and errs(demonstrated_impact="Huge")
assert errs(verifier="U1") == ["verifier must differ from hunter"], "case-insensitive"
assert errs(rechecked_by="u1") == ["rechecked_by must differ from hunter"]
assert errs(surprise=1) == ["unknown field: surprise"]
for bad in (["confirmed"], {"x": 1}, 7, None):
    assert fv.check_row({"verdict": bad}), bad
assert fv.check_row({"verdict": "bogus"}) and fv.check_row({"id": "x"}), "verdict required for check_row"

NV = {"id": "F2", "verdict": "needs_validation", "blockers": ["config unseen"], "validation_plan": "read prod.yaml"}
assert fv.check_row(NV) == []
assert fv.check_row({**NV, "blockers": []}) and fv.check_row({**NV, "blockers": "x"})
assert fv.check_row({k: v for k, v in NV.items() if k != "validation_plan"})
assert fv.check_row({**NV, "severity": "High"}) == ["needs_validation must not carry severity"]
assert fv.check_row({**NV, "demonstrated_impact": "High"})
RJ = {"id": "F3", "verdict": "rejected", "reject_reason": "guard at b.py:9"}
assert fv.check_row(RJ) == [] and fv.check_row({"id": "F3", "verdict": "rejected"})
assert fv.check_row({**RJ, "severity": "Low"})

# validate_rows: legacy rows skipped unless required; strengths never checked
legacy = {"id": "L", "severity": "High"}
assert fv.validate_rows([legacy, {"id": "S", "polarity": "strength"}]) == []
assert fv.validate_rows([legacy], require=True)
assert fv.validate_rows(["x"])[0]["error"] == "row is not an object"

# merge_findings: invalid and rejected verdict rows never rank; keys appear only when nonzero
with tempfile.TemporaryDirectory() as d:
    open(os.path.join(d, "a.py"), "w").write("code line one\n")
    bad = {**OK, "id": "B", "verifier": "u1"}
    res = mf.merge([OK, bad, {**RJ, "evidence": ["a.py:1"], "snippet": "code line one"}], root=d)
    assert [f["id"] for f in res["findings"]] == ["F1"], res
    assert res["dropped"]["invalid_verdict"] == 1 and res["dropped"]["rejected"] == 1
    assert res["verdict_errors"] == [{"id": "B", "error": "verifier must differ from hunter"}]
    clean = mf.merge([OK], root=d)
    assert "verdict_errors" not in clean and "invalid_verdict" not in clean["dropped"]
    nv = mf.merge([{**NV, "evidence": ["a.py:1"], "snippet": "code line one"}], root=d)
    assert nv["findings"] == [] and [f["id"] for f in nv["needs_validation"]] == ["F2"], "questions are never ranked"
    # polarity cannot dodge the gate: Gap / null / odd case still hit the verdict check, rejected never emitted
    rj = {**RJ, "evidence": ["a.py:1"], "snippet": "code line one"}
    for pol in ("Gap", None, " GAP "):
        r = mf.merge([{**rj, "polarity": pol}, {**OK, "id": "B2", "polarity": pol, "verifier": "u1"}], root=d)
        assert r["findings"] == [] and r["dropped"]["rejected"] == 1 and r["dropped"]["invalid_verdict"] == 1, (pol, r)
    # a malformed verdict never crashes the merge
    for v in (["confirmed"], {"a": 1}, None, 3):
        r = mf.merge([{**OK, "verdict": v}], root=d)
        assert r["findings"] == [] and r["dropped"]["invalid_verdict"] == 1, v
    # severity " critical " is normalized once: validated and ranked ahead of Medium
    both = mf.merge([{**OK, "id": "M", "severity": "Medium"}, {**OK, "id": "C", "severity": " critical ", "demonstrated_impact": "CRITICAL ", "evidence": ["a.py:1"], "mechanism": "other"}], root=d)
    assert [f["id"] for f in both["findings"]] == ["C", "M"], both

# CLI: exit 1 on error, 0 on ok, 2 on unreadable
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "f.json")
    run = lambda *a: subprocess.run([sys.executable, os.path.join(SD, "finding_verdict.py"), *a], capture_output=True, text=True)
    json.dump({"findings": [OK]}, open(p, "w"))
    assert run(p).returncode == 0
    json.dump({"findings": [{**OK, "severity": "Blocker"}]}, open(p, "w"))
    r = run(p)
    assert r.returncode == 1 and "exceeds" in r.stdout
    assert run(os.path.join(d, "nope.json")).returncode == 2 and run().returncode == 2

# security_verify: the finder cannot confirm its own claim
loc = {"source": "a.py:1", "sink": "b.py:2"}
ex, _ = sv.effective()
st = lambda row: sv.triage([row], ex)[0]["status"]
assert st({**loc, "hunter": "u1", "verifier": "U1"}) == "needs_validation"
assert st({**loc, "hunter": "u1", "verifier": "u2"}) == "confirmed"
for partial in (loc, {**loc, "hunter": "u1"}, {**loc, "verifier": "u2"}, {**loc, "hunter": " ", "verifier": " "}):
    assert st(partial) == "needs_validation", partial
idx = open(os.path.join(ROOT, "docs", "standards-index.md"), encoding="utf-8").read()
line = next(l for l in idx.splitlines() if "security-audit-skill" in l)
assert "MIT" not in line and "http" not in line, "peer entry: by name only, no license or URL claim"
print("test_finding_verdict: all passed")
