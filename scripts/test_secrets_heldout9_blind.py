#!/usr/bin/env python3
"""Pins the secrets held-out-9 scores (docs/bench/secrets-heldout9-1025).

Blind rows (scored at 2df6b5274, before secrets wave 6: gate 47/60 leaks, 1/60 decoys; gitleaks 35/1) are pinned here; the corpus is in-sample after
wave 6. The live gate/gitleaks rows are recomputed by running the held-out-4 scorer on this corpus. A moved number means a rule edit changed behavior: update deliberately. Offline.
"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout9-1025"
BLIND = {"gate": (47, 1), "gitleaks": (35, 1)}
MISSED = ["L010", "L023", "L029", "L038", "L044", "L046", "L047", "L050", "L051", "L052", "L055", "L056", "L057"]
frozen = (H / "SHA256-frozen.txt").read_text()
assert json.loads((H / "ledger.jsonl").read_text().splitlines()[0])["sha256"] == hashlib.sha256("".join(frozen.splitlines(True)[:2]).encode()).hexdigest(), "preregistered hash drifted"
assert len(frozen.splitlines()) == 2, "frozen pins are append-only: amend via ledger.jsonl"
assert BLIND["gate"][0] == 60 - len(MISSED)
src = (ROOT / "docs/bench/secrets-heldout4-1025/score.py").read_text().replace("D = pathlib.Path(__file__).resolve().parent", f"D = pathlib.Path({str(H)!r})")
g = {"__file__": str(ROOT / "docs/bench/secrets-heldout4-1025/score.py"), "__name__": "score9"}
exec(compile(src, "score9", "exec"), g)
assert not g["drift"](), g["drift"]()
s = g["scores"]()
lk, dc = s["secret-leaks.txt"], s["secret-decoys.txt"]
assert (len(lk["union"]), len(dc["union"])) == (57, 0), (lk["union"], dc["union"])  # in-sample after wave 6: only L029, L038 and L056 stay missed
assert (len(lk["gitleaks"]), len(dc["gitleaks"])) == BLIND["gitleaks"], (len(lk["gitleaks"]), len(dc["gitleaks"]))
print("secrets held-out-9 pins: ok")
