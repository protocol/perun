#!/usr/bin/env python3
"""Pins the held-out-10 BLIND guard rows as recorded in RESULTS.md; the live 60/60 score is in-sample since wave 7. Offline."""
import pathlib

R = (pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout10-1025/RESULTS.md").read_text()
for row in ("| Perun guard, main (blind) | 44 | 6 |", "| Perun guard, wave 6 (blind) | 44 | 6 |"):
    assert row in R, f"blind row missing from RESULTS.md: {row}"
assert "| Perun guard, wave 7 (in-sample) | 60 | 1 |" in R
assert "In-sample since wave 7" in R
print("held-out-10 blind row pins: ok")
