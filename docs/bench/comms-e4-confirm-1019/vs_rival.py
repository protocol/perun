#!/usr/bin/env python3
"""Descriptive, gates nothing: E4 minus RIVAL (humanizer) paired accuracy, real-fab rate and words from per_scenario_held.json; writes report_vs_rival.txt. usage: vs_rival.py"""
import json, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabjudge as f  # noqa: E402

if __name__ == "__main__":
    S = json.loads((f.D / "per_scenario_held.json").read_text())
    col = lambda a, k: [r[k] for r in S[a]]
    out = f"E4 - RIVAL n={len(S['E4'])}: " + " | ".join(f"{k} {m:+.3f} 95% CI [{lo:+.3f}, {hi:+.3f}]" for k in ("acc", "real_fab", "words") for m, lo, hi in [f.b.paired(col("E4", k), col("RIVAL", k))])
    print(out)
    (f.D / "report_vs_rival.txt").write_text(out + "\n")
