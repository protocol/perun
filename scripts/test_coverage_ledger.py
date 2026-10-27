#!/usr/bin/env python3
"""Tests for coverage_ledger.py (plain asserts; exits non-zero on failure)."""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, SD)
import coverage_ledger as cl  # noqa: E402

assert cl.parse_domains("A-C,W") == ["A", "B", "C", "W"] and len(cl.parse_domains("A-T,W")) == 21
for bad in ("C-A", "a", "", "A-"):
    try:
        cl.parse_domains(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

D = ["A", "B", "C"]
full = {"A": {"status": "scanned"}, "B": {"status": "not-applicable", "probe": "grep x", "fact": "0 matches"},
        "C": {"status": "scanned"}}
chk = lambda doc: cl.check(doc, D)
assert chk({"coverage": full}) == ([], False)
assert chk({}) == (["coverage map missing"], True)
e, inc = chk({"coverage": {k: v for k, v in full.items() if k != "C"}, "incomplete_reason": "x"})
assert e == ["C: no coverage row"] and inc
assert "B: not-applicable needs probe and fact" in chk({"coverage": {**full, "B": {"status": "not-applicable", "fact": "f"}}})[0]
assert "A: status must be one of ['scanned', 'partial', 'not-scanned', 'not-applicable']" in chk({"coverage": {**full, "A": {"status": "done"}}})[0]
# a declined/blocked domain needs a note, and an incomplete run needs a stated reason
part = {**full, "C": {"status": "not-scanned"}}
assert "C: not-scanned needs a note saying why" in chk({"coverage": part, "incomplete_reason": "r"})[0]
part["C"] = {"status": "partial", "note": "blocked: no creds"}
assert chk({"coverage": part}) == (["incomplete run needs incomplete_reason"], True)
assert chk({"coverage": part, "incomplete_reason": "creds blocked C"}) == ([], True)
assert chk({"coverage": part, "incomplete_reason": "  "})[0]
# fan-out units
u = lambda **kw: {"coverage": full, "units": [{"id": "u1", **kw}], "incomplete_reason": "r"}
assert chk(u(status="scanned", finder="f1", lead_read=True)) == ([], False)
assert chk(u(status="scanned", finder="f1", lead_read=False))[0] == ["unit u1: scanned needs finder and lead_read true"]
assert chk(u(status="stalled"))[0] == ["unit u1: stalled needs a note saying why"]
assert chk(u(status="stalled", note="finder never returned")) == ([], True)
assert chk({"coverage": full, "units": [{"id": "u1", "status": "stalled", "note": "n"}]})[0] == ["incomplete run needs incomplete_reason"]

for bad_units in ({"id": "u1"}, "x", 0, ""):
    assert chk({"coverage": full, "units": bad_units, "incomplete_reason": "r"})[0] == ["units must be a list"], bad_units

with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "f.json")
    run = lambda *a: subprocess.run([sys.executable, os.path.join(SD, "coverage_ledger.py"), *a], capture_output=True, text=True)
    json.dump({"coverage": full}, open(p, "w"))
    assert run("--domains", "A-C", p).returncode == 0
    assert run("--domains", "A-D", p).returncode == 1
    assert run(p).returncode == 1, "default A-T,W demands every row"
    assert run("--domains", "Z-A", p).returncode == 2 and run().returncode == 2 and run(os.path.join(d, "x")).returncode == 2
print("test_coverage_ledger: all passed")
