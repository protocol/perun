#!/usr/bin/env python3
"""Tests docs/bench/security-heldout-table-1026/results.py: the exact-statistics helpers, a fast sampled check, and (FULL=1) byte-identical regeneration.

Default: re-score two sampled corpora (one secrets, one guard) and require their rows to appear verbatim in table.md.
FULL=1: regenerate the whole table (about 4 minutes) and require it to equal table.md byte for byte.
The scoring needs the git history of the pinned commits; if it is missing (shallow clone) this exits 1, unless
HELDOUT_ALLOW_SKIP=1, which prints a loud SKIP and exits 0. Offline; temp dirs only.
"""
import importlib.util, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
T = ROOT / "docs/bench/security-heldout-table-1026"
spec = importlib.util.spec_from_file_location("results", T / "results.py")
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

lo, hi = r.cp(0, 10); assert lo == 0.0 and abs(hi - 0.3085) < 1e-3, (lo, hi)  # exact bound at 0, 1 - 0.025^(1/10)
lo, hi = r.cp(10, 10); assert hi == 1.0 and abs(lo - 0.6915) < 1e-3, (lo, hi)
lo, hi = r.cp(5, 10); assert abs(lo - 0.1871) < 1e-3 and abs(hi - 0.8129) < 1e-3, (lo, hi)  # textbook CP interval for 5 of 10
assert r.sign_p(0, 0) == 1.0 and r.sign_p(3, 3) == 1.0 and abs(r.sign_p(0, 5) - 0.0625) < 1e-12
assert r.pct(21, 30) == "70.0%" and r.fmt_p(1e-9) == "<0.0001"

missing = sorted({*r.BASE.values(), r.NOW} - {s for s in {*r.BASE.values(), r.NOW} if subprocess.run(
    ["git", "-C", str(ROOT), "cat-file", "-e", s + "^{commit}"], capture_output=True).returncode == 0})
if missing:
    msg = f"pinned commits not in this clone: {missing}; regeneration NOT checked"
    if os.environ.get("HELDOUT_ALLOW_SKIP") == "1": print("SKIP (HELDOUT_ALLOW_SKIP=1):", msg); sys.exit(0)
    sys.exit("FAIL: " + msg + " (fetch full history, or set HELDOUT_ALLOW_SKIP=1)")
run = lambda *a: subprocess.run([sys.executable, "-I", str(T / "results.py"), *a], capture_output=True, text=True)
table = (T / "table.md").read_text()
if os.environ.get("FULL") == "1":
    got = run(); assert got.returncode == 0, got.stderr
    assert got.stdout == table, "table.md is stale: rerun results.py > table.md"
else:
    got = run("secrets-heldout7-1025", "security-gates-heldout9-1025"); assert got.returncode == 0, got.stderr
    rows = got.stdout.splitlines(); assert len(rows) == 2, rows
    for row in rows: assert row in table.splitlines(), "table.md row is stale: " + row
print("ok")
