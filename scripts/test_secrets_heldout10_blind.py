#!/usr/bin/env python3
"""Pins the secrets held-out-10 scores (docs/bench/secrets-heldout10-1025).

Blind rows (scored at 3d28f0966, before secrets wave 7: gate 56/60 leaks, 1/60 decoys; gitleaks 41/2) are pinned here; the corpus is in-sample after
wave 7. The live gate/gitleaks rows are recomputed by running the held-out-4 scorer on this corpus. A moved number means a rule edit changed behavior: update deliberately. Offline.
"""
import hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout10-1025"
BLIND = {"gate": (56, 1), "gitleaks": (41, 2)}
MISSED = ["L009", "L033", "L034", "L060"]
frozen = (H / "SHA256-frozen.txt").read_text()
assert json.loads((H / "ledger.jsonl").read_text().splitlines()[0])["sha256_frozen"] == hashlib.sha256(frozen.encode()).hexdigest(), "preregistered hash drifted"
assert len(frozen.splitlines()) == 2, "frozen pins are append-only: amend via ledger.jsonl"
assert BLIND["gate"][0] == 60 - len(MISSED)
src = (ROOT / "docs/bench/secrets-heldout4-1025/score.py").read_text().replace("D = pathlib.Path(__file__).resolve().parent", f"D = pathlib.Path({str(H)!r})")
g = {"__file__": str(ROOT / "docs/bench/secrets-heldout4-1025/score.py"), "__name__": "score10"}
exec(compile(src, "score10", "exec"), g)
assert not g["drift"](), g["drift"]()
s = g["scores"]()
lk, dc = s["secret-leaks.txt"], s["secret-decoys.txt"]
assert (len(lk["union"]), len(dc["union"])) == (59, 0), (lk["union"], dc["union"])  # in-sample after wave 7: only L009 stays missed (a letters-only password, no shape)
assert (len(lk["gitleaks"]), len(dc["gitleaks"])) == BLIND["gitleaks"], (len(lk["gitleaks"]), len(dc["gitleaks"]))
print("secrets held-out-10 pins: ok")
