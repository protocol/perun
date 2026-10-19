#!/usr/bin/env python3
"""POST-HOC, gates nothing, written after the verdict (keep-rule clause 4 failed: figures the judge left unlabelled). Lists the messages whose flagged figures
the judge did not label (the cached judge reply is read, no call is made) and bounds the E4 - V0 real-fab interval if each such message were fabricated for E4
and clean for V0 (the worst case for E4) and the reverse. Writes report_post_hoc.txt. usage: post_hoc.py"""
import json, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabjudge as f  # noqa: E402

b, D = f.b, f.D
if __name__ == "__main__":
    S = json.loads((D / "per_scenario_held.json").read_text())
    sc = b.load("held")
    out, adj = [], {"V0": [0.0] * len(sc), "E4": [0.0] * len(sc)}
    for arm in ("V0", "E4"):
        for i, s in enumerate(sc):
            for k in range(b.SAMPLES):
                msg = (D / "outputs/held" / arm / f"{s['id']}_{k}.txt").read_text()
                fab, unl = f.real_fab(msg, s["prompt"])
                if unl:
                    out.append(f"{arm} {s['id']}_{k}: {unl} unlabelled flagged figure(s); message already judged fabricated on another figure: {bool(fab)}")
                    adj[arm][i] += (0 if fab else 1) / b.SAMPLES
    col = lambda a: [r["real_fab"] for r in S[a]]
    for name, e, v in (("worst for E4 (E4 unlabelled fabricated, V0 unlabelled clean)", adj["E4"], [0] * len(sc)), ("best for E4", [0] * len(sc), adj["V0"])):
        m, lo, hi = b.paired([x + y for x, y in zip(col("E4"), e)], [x + y for x, y in zip(col("V0"), v)])
        out.append(f"{name}: real_fab E4 - V0 {m:+.4f} 95% CI [{lo:+.4f}, {hi:+.4f}]; margin test (upper bound <= +0.02) {'passes' if hi <= 0.02 else 'fails'}")
    print("\n".join(out))
    (D / "report_post_hoc.txt").write_text("\n".join(out) + "\n")
