#!/usr/bin/env python3
"""Pins held-out-5 (docs/bench/security-gates-heldout5-1025), the guard row (in-sample after the wave-3 fixes; blind 50/60, FP 4/60
is in RESULTS.md): preregistered hashes and the scores (guard 59/60 blocked, 0/60 benign blocked; rivals). A moved number means a rule edit changed an out-of-sample
corpus: re-score, record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout5-1025"

fz = (H / "SHA256-frozen.txt").read_text()
assert hashlib.sha256(fz.encode()).hexdigest() == "f0fac027ce81bc55d42f5196f6c10b7a0a9786b2fdb731076ff93a838def2098", "preregistered hash list drifted"
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-5 corpus drifted: {name}"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun, perun  # wave 14 (`kubectl delete -f -` blocked) lifted 59/60 -> 60/60
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 8/60  FP 4/60", "safety-net (ported subset): blocked 20/60 (2 unported)  FP 2/60"):
    assert want in riv, (want, riv)
print("held-out-5 security gates pins: ok")
