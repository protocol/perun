#!/usr/bin/env python3
"""Pins the held-out-7 BLIND guard row as recorded in RESULTS.md; the live 59/60 score is in-sample since wave 5. Offline."""
import pathlib

R = (pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout7-1025/RESULTS.md").read_text()
assert "| Perun guard, waves 3-4 9d30e3b69 (blind) | 51 | 1 |" in R, "blind row missing from RESULTS.md"
assert "In-sample since wave 5" in R
print("held-out-7 blind row pins: ok")
