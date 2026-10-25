#!/usr/bin/env python3
"""Pins the secrets held-out-4 scores (docs/bench/secrets-heldout4-1025).

Blind rows (47/60 before this change) are pinned as the documented table in RESULTS.md; the gitleaks and banlist columns and the in-sample
gate row (60/60, FP 1) are recomputed live by score.py. A moved number means a rule edit changed behavior: re-score and update RESULTS.md deliberately. Offline.
"""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/secrets-heldout4-1025"
frozen = (H / "SHA256-frozen.txt").read_text().splitlines()
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert hashlib.sha256("".join(l + "\n" for l in frozen[:2]).encode()).hexdigest() == led["sha256_frozen_txt"], "preregistered hash list drifted"
res = (H / "RESULTS.md").read_text()
for want in ("| Perun gate, before the precision review | f4e6b4bf3 | 47 | 0 |", "| Perun gate, after the precision review (base of this change) | 607661844 | 47 | 1 |",
             "| Perun gate, main | 8eb9fc0d5 | 47 | 4 |", "| gitleaks v8.30.1 (ported) | n/a | 43 | 2 |", "| Perun banlist only | n/a | 31 | 3 |"):
    assert want in res, want
r = subprocess.run([sys.executable, "-I", str(H / "score.py")], capture_output=True, text=True, cwd=ROOT)
assert r.returncode == 0, r.stdout + r.stderr
for want in ("union: recall 60/60  FP 1/60", "banlist: recall 31/60  FP 3/60", "gitleaks: recall 43/60  FP 2/60"):
    assert want in r.stdout, (want, r.stdout)
assert "false positives: ['D034']" in r.stdout
print("secrets held-out-4 pins: ok")
