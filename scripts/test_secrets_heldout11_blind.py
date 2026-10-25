#!/usr/bin/env python3
"""Pins the secrets held-out-11 scores (docs/bench/secrets-heldout11-1025).

Blind rows (scored at a4be97b50, before secrets wave 8: gate 52/60 leaks, 0/60 decoys; gitleaks 43/3) are pinned here; the corpus is in-sample after
wave 8. The live gate/gitleaks rows are recomputed by running the held-out-4 scorer on this corpus. A moved number means a rule edit changed behavior: update deliberately. Offline.
"""
import hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout11-1025"
BLIND = {"gate": (52, 0), "gitleaks": (43, 3)}
MISSED = ["L012", "L040", "L043", "L046", "L055", "L056", "L058", "L059"]
frozen = (H / "SHA256-frozen.txt").read_text()
assert json.loads((H / "ledger.jsonl").read_text().splitlines()[0])["sha256_frozen"] == hashlib.sha256(frozen.encode()).hexdigest(), "preregistered hash drifted"
assert len(frozen.splitlines()) == 2, "frozen pins are append-only: amend via ledger.jsonl"
assert BLIND["gate"][0] == 60 - len(MISSED)
src = (ROOT / "docs/bench/secrets-heldout4-1025/score.py").read_text().replace("D = pathlib.Path(__file__).resolve().parent", f"D = pathlib.Path({str(H)!r})")
g = {"__file__": str(ROOT / "docs/bench/secrets-heldout4-1025/score.py"), "__name__": "score11"}
exec(compile(src, "score11", "exec"), g)
assert not g["drift"](), g["drift"]()
s = g["scores"]()
lk, dc = s["secret-leaks.txt"], s["secret-decoys.txt"]
assert (len(lk["union"]), len(dc["union"])) == (59, 0), (lk["union"], dc["union"])  # in-sample after wave 8: only L056 stays missed (a bare `pass =` key with letters only, no shape)
assert (len(lk["gitleaks"]), len(dc["gitleaks"])) == BLIND["gitleaks"], (len(lk["gitleaks"]), len(dc["gitleaks"]))
print("secrets held-out-11 pins: ok")
