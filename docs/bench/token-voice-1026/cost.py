#!/usr/bin/env python3
"""Regenerate cost.json from runs.jsonl: per-arm total USD, output tokens and call count (offline, stdlib)."""
import json
from pathlib import Path

D = Path(__file__).resolve().parent
out = {}
for r in map(json.loads, (D / "runs.jsonl").read_text().splitlines()):
    a = out.setdefault(r["arm"], {"calls": 0, "output_tokens": 0, "cost_usd": 0.0})
    a["calls"] += 1
    a["output_tokens"] += r["completion_tokens"]
    a["cost_usd"] = round(a["cost_usd"] + r["cost_usd"], 6)
out["total_cost_usd"] = round(sum(v["cost_usd"] for v in out.values()), 6)
(D / "cost.json").write_text(json.dumps(out, indent=1) + "\n")
