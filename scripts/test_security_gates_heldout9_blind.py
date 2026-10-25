#!/usr/bin/env python3
"""Pins the held-out-9 BLIND guard rows as recorded in RESULTS.md; the live 60/60 score is in-sample since wave 6. Offline."""
import pathlib

R = (pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout9-1025/RESULTS.md").read_text()
for row in ("| Perun guard, #1993 rules 93b1dfa72 (blind) | 55 | 0 |", "| Perun guard, main before #1993 (blind) | 48 | 0 |"):
    assert row in R, f"blind row missing from RESULTS.md: {row}"
assert "In-sample since wave 6" in R
print("held-out-9 blind row pins: ok")
