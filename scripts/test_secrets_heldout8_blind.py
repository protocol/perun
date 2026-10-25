#!/usr/bin/env python3
"""Pins the secrets held-out-8 scores (docs/bench/secrets-heldout8-1025).

Blind rows (scored at 3888f5cde, before secrets wave 5: gate 48/60 leaks, 3/60 decoys; main 41/5; gitleaks 39/5) are pinned here; the corpus is in-sample after
wave 5. The live gate/gitleaks rows are recomputed by running the held-out-4 scorer on this corpus. A moved number means a rule edit changed behavior: update deliberately. Offline.
"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout8-1025"
BLIND = {"gate": (48, 3), "main": (41, 5), "gitleaks": (39, 5)}
MISSED = ["L004", "L008", "L019", "L021", "L028", "L030", "L035", "L040", "L041", "L054", "L057", "L060"]
frozen = (H / "SHA256-frozen.txt").read_text()
assert json.loads((H / "ledger.jsonl").read_text().splitlines()[0])["sha256"] == hashlib.sha256("".join(frozen.splitlines(True)[:2]).encode()).hexdigest(), "preregistered hash drifted"
lines = frozen.splitlines()  # append-only: lines 1-2 preregistered, line 3 is the amended secret-leaks.txt pin (ledger.jsonl amendment) and must match it
assert len(lines) == 3 and lines[2].endswith("  secret-leaks.txt") and json.loads((H / "ledger.jsonl").read_text().splitlines()[1])["sha256"] == lines[2].split()[0], "amended pin does not match ledger"
assert BLIND["gate"][0] == 60 - len(MISSED)
src = (ROOT / "docs/bench/secrets-heldout4-1025/score.py").read_text().replace("D = pathlib.Path(__file__).resolve().parent", f"D = pathlib.Path({str(H)!r})")
g = {"__file__": str(ROOT / "docs/bench/secrets-heldout4-1025/score.py"), "__name__": "score8"}
exec(compile(src, "score8", "exec"), g)
assert not g["drift"](), g["drift"]()
s = g["scores"]()
lk, dc = s["secret-leaks.txt"], s["secret-decoys.txt"]
assert (len(lk["union"]), len(dc["union"])) == (58, 0), (lk["union"], dc["union"])  # in-sample after wave 5: only L004 and L060 stay missed
assert (len(lk["gitleaks"]), len(dc["gitleaks"])) == BLIND["gitleaks"], (len(lk["gitleaks"]), len(dc["gitleaks"]))
print("secrets held-out-8 pins: ok")
