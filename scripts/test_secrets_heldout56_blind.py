#!/usr/bin/env python3
"""Pins the secrets held-out-5 and -6 scores (docs/bench/secrets-heldout{5,6}-1025).

Blind rows are pinned as the documented tables in each RESULTS.md; the gitleaks and banlist columns and the in-sample gate row are recomputed live
by score.py. A moved number means a rule edit changed behavior: re-score and update RESULTS.md deliberately. Offline.
"""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLIND = {5: ("| Perun gate, wave 2 (base of this change) | 7c2c9dd66 | 27 | 1 |", "| Perun gate, precision review | 607661844 | 20 | 1 |",
             "| Perun gate, main | 8eb9fc0d5 | 34 | 3 |", "| gitleaks v8.30.1 (ported) | n/a | 23 | 3 |", "| Perun banlist only | n/a | 19 | 1 |"),
         6: ("| Perun gate (base of this change) | 33df1416f | 50 | 2 |", "| Perun gate, main | 7453990b1 | 45 | 7 |",
             "| gitleaks v8.30.1 (ported) | n/a | 40 | 3 |", "| Perun banlist only | n/a | 33 | 6 |")}
LIVE = {5: ("union: recall 44/60  FP 0/60", "banlist: recall 19/60  FP 1/60", "gitleaks: recall 23/60  FP 3/60"),
        6: ("union: recall 59/60  FP 0/60", "banlist: recall 33/60  FP 6/60", "gitleaks: recall 40/60  FP 3/60")}
for n in (5, 6):
    H = ROOT / f"docs/bench/secrets-heldout{n}-1025"
    led = [json.loads(l) for l in (H / "ledger.jsonl").read_text().splitlines()]
    frozen = (H / "SHA256-frozen.txt").read_text().splitlines()
    assert any(led[0]["sha256"] == hashlib.sha256("".join(l + "\n" for l in frozen[:k]).encode()).hexdigest() for k in range(1, len(frozen) + 1)), "preregistered hash drifted"
    res = (H / "RESULTS.md").read_text()
    for want in BLIND[n]:
        assert want in res, want
    r = subprocess.run([sys.executable, "-I", str(H / "score.py")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    for want in LIVE[n]:
        assert want in r.stdout, (n, want, r.stdout)
print("secrets held-out-5/6 pins: ok")
