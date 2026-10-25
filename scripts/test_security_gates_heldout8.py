#!/usr/bin/env python3
"""Pins held-out-8 (docs/bench/security-gates-heldout8-1025): preregistered hashes and the scores (guard 60/60 blocked, 0/60 benign
blocked; rivals). IN-SAMPLE since wave 6; the blind rows are pinned in test_security_gates_heldout8_blind.py. A moved number means a
rule edit changed a scored corpus: re-score, record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout8-1025"

fz = (H / "SHA256-frozen.txt").read_text()
assert hashlib.sha256(fz.encode()).hexdigest() == "8c9ca4e3f3069cdea401ea3f87631e850ccb9089e4c1c1681f95ee1c32894c19", "preregistered hash list drifted"
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-8 corpus drifted: {name}"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 14/60  FP 7/60", "safety-net (ported subset): blocked 12/60 (2 unported)  FP 0/60"):
    assert want in riv, (want, riv)
print("held-out-8 security gates pins: ok")
