#!/usr/bin/env python3
"""Pins the held-out-6 BLIND guard row as recorded in RESULTS.md; the live 59/60 score is in-sample since wave 5. Offline."""
import pathlib

R = (pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout6-1025/RESULTS.md").read_text()
assert "| Perun guard, wave-3 post-review 7bd064ae5 (blind) | 45 | 2 |" in R, "blind row missing from RESULTS.md"
assert "In-sample since wave 5" in R
print("held-out-6 blind row pins: ok")
