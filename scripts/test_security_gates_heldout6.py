#!/usr/bin/env python3
"""Pins held-out-6 (docs/bench/security-gates-heldout6-1025), blind for the guard: preregistered hashes and the scores
(guard 45/60 blocked, 2/60 benign blocked; rivals). A moved number means a rule edit changed an out-of-sample corpus:
re-score, record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout6-1025"

fz = (H / "SHA256-frozen.txt").read_text()
assert hashlib.sha256(fz.encode()).hexdigest() == "952c219348eb4cd2e8080ec1558604786bcfc44b53b06e48120d9ca46441b367", "preregistered hash list drifted"
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-6 corpus drifted: {name}"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 45/60  FP 2/60" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 15/60  FP 8/60", "safety-net (ported subset): blocked 11/60 (1 unported)  FP 2/60"):
    assert want in riv, (want, riv)
print("held-out-6 security gates pins: ok")
