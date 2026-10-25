#!/usr/bin/env python3
"""Pins the held-out-8 BLIND guard rows as recorded in RESULTS.md; the live 60/60 score is in-sample since wave 6. Offline."""
import pathlib

R = (pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout8-1025/RESULTS.md").read_text()
for row in ("| Perun guard, wave-5 27d1c7d63 (blind) | 48 | 1 |", "| Perun guard, post-review a72cce0a9 | 49 | 1 |"):
    assert row in R, f"blind row missing from RESULTS.md: {row}"
assert "In-sample since wave 6" in R
print("held-out-8 blind row pins: ok")
