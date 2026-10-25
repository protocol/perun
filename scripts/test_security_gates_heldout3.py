#!/usr/bin/env python3
"""Pins the out-of-sample held-out-3 secret scores (docs/bench/security-gates-heldout3-1024): union gate, banlist only, gitleaks only.

A moved number means a rule edit changed behavior on a corpus meant to stay out of sample: re-score, update RESULTS.md and the pins deliberately.
Offline.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "docs/bench/security-gates-heldout3-1024"
frozen = (H / "SHA256-frozen.txt").read_text().splitlines()
assert hashlib.sha256("".join(l + "\n" for l in frozen[:2]).encode()).hexdigest() == "441e83437b2742171d6159454555b431bcc7e1fd8e1378d16e362023e8954ee6", "preregistered hash list drifted"
r = subprocess.run([sys.executable, "-I", str(H / "score.py")], capture_output=True, text=True, cwd=ROOT)
assert r.returncode == 0, r.stdout + r.stderr
for want in ("union: recall 54/60  FP 16/60", "banlist: recall 41/60  FP 12/60", "gitleaks: recall 47/60  FP 8/60"):
    assert want in r.stdout, (want, r.stdout)
print("held-out-3 security gates pins: ok")
