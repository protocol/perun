#!/usr/bin/env python3
"""Pins the held-out-5 BLIND guard row (50/60 blocked, 4/60 benign blocked at 879a0c13a, before the wave-3 fixes) as recorded
in the ledger and RESULTS.md. The live 59/60 score is in-sample (see test_security_gates_heldout5.py). Offline."""
import json, pathlib

H = pathlib.Path(__file__).resolve().parent.parent / "docs/bench/security-gates-heldout5-1025"
ev = [json.loads(l) for l in (H / "ledger.jsonl").read_text().splitlines()]
assert any("guard 50/60 blocked FP 4/60" in e.get("text", "") for e in ev), "blind row missing from the ledger"
assert "| Perun guard, post-review (blind) | 50 | 4 |" in (H / "RESULTS.md").read_text(), "blind row missing from RESULTS.md"
assert "in-sample" in (H / "RESULTS.md").read_text()
print("held-out-5 blind row pins: ok")
