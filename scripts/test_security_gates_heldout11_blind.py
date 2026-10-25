#!/usr/bin/env python3
"""Pins held-out-11 (docs/bench/security-gates-heldout11-1025): preregistered hashes, the BLIND guard rows recorded in RESULTS.md, the live rival scores,
and the live in-sample guard score since wave 8 (60/60 blocked, 1/60 benign blocked: `git reset --hard HEAD`, deliberately blocked). A moved number means
a rule edit changed a scored corpus: re-score, record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified."""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout11-1025"

fz = (H / "SHA256-frozen.txt").read_text()
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-11 corpus drifted: {name}"

R = (H / "RESULTS.md").read_text()
for row in ("| Perun guard, pre-review (blind) | 57 | 2 |", "| Perun guard, main 8eb9fc0d5 (blind) | 57 | 3 |", "| Perun guard, wave 8 (in-sample) | 60 | 1 |",
            "| claude-code-safety-net (ported subset, 1 row unported) | 17 | 7 |", "| hooks-mastery (ported) | 9 | 6 |"):
    assert row in R, f"row missing from RESULTS.md: {row}"
assert "In-sample since wave 8" in R


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 1/60" in perun and "false positives: ['git reset --hard HEAD']" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 9/60  FP 6/60", "safety-net (ported subset): blocked 17/60 (1 unported)  FP 7/60"):
    assert want in riv, (want, riv)
print("held-out-11 security gates pins: ok")
