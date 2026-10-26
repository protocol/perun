#!/usr/bin/env python3
"""Tests docs/bench/security-heldout-table-1026/results.py: the exact-statistics helpers, and that table.md regenerates byte-identically.

The regeneration needs the git history of the pinned commits; without it (shallow clone) that one check is skipped, not faked.
Offline; temp dirs only.
"""
import importlib.util, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
T = ROOT / "docs/bench/security-heldout-table-1026"
spec = importlib.util.spec_from_file_location("results", T / "results.py")
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

lo, hi = r.cp(0, 10); assert lo == 0.0 and abs(hi - 0.3085) < 1e-3, (lo, hi)  # exact one-sided-at-0 bound, 1 - 0.025^(1/10)
lo, hi = r.cp(10, 10); assert hi == 1.0 and abs(lo - 0.6915) < 1e-3, (lo, hi)
lo, hi = r.cp(5, 10); assert abs(lo - 0.1871) < 1e-3 and abs(hi - 0.8129) < 1e-3, (lo, hi)  # textbook CP interval for 5 of 10
assert r.sign_p(0, 0) == 1.0 and r.sign_p(3, 3) == 1.0 and abs(r.sign_p(0, 5) - 0.0625) < 1e-12
assert r.pct(21, 30) == "70.0%"

missing = [s for s in {*r.BASE.values(), r.NOW} if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", s + "^{commit}"], capture_output=True).returncode]
if missing:
    print("SKIP regeneration: commits not in this clone:", sorted(missing))
else:
    got = subprocess.run([sys.executable, "-I", str(T / "results.py")], capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
    assert got.stdout == (T / "table.md").read_text(), "table.md is stale: rerun results.py > table.md"
print("ok")
