#!/usr/bin/env python3
"""Pins the secrets held-out-7 scores (docs/bench/secrets-heldout7-1025).

Blind rows (scored at 5c25b025b, before secrets wave 4: gate 53/60 leaks, 0/60 decoys; main 48/1; gitleaks 38/1) are pinned here; the corpus is in-sample after
wave 4. The live gate/gitleaks rows are recomputed by running the held-out-4 scorer on this corpus. A moved number means a rule edit changed behavior: update deliberately. Offline.
"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout7-1025"
BLIND = {"gate": (53, 0), "main": (48, 1), "gitleaks": (38, 1)}
MISSED = ["L013", "L031", "L043", "L046", "L047", "L048", "L058"]
frozen = (H / "SHA256-frozen.txt").read_text()
assert json.loads((H / "ledger.jsonl").read_text().splitlines()[0])["sha256"] == hashlib.sha256("".join(frozen.splitlines(True)[:2]).encode()).hexdigest(), "preregistered hash drifted"
assert BLIND["gate"][0] == 60 - len(MISSED)
src = (ROOT / "docs/bench/secrets-heldout4-1025/score.py").read_text().replace("D = pathlib.Path(__file__).resolve().parent", f"D = pathlib.Path({str(H)!r})")
g = {"__file__": str(ROOT / "docs/bench/secrets-heldout4-1025/score.py"), "__name__": "score7"}
exec(compile(src, "score7", "exec"), g)
assert not g["drift"](), g["drift"]()
s = g["scores"]()
lk, dc = s["secret-leaks.txt"], s["secret-decoys.txt"]
assert (len(lk["union"]), len(dc["union"])) == (59, 0), (lk["union"], dc["union"])  # in-sample after wave 4: only L013 stays missed
assert (len(lk["gitleaks"]), len(dc["gitleaks"])) == BLIND["gitleaks"], (len(lk["gitleaks"]), len(dc["gitleaks"]))
print("secrets held-out-7 pins: ok")
