#!/usr/bin/env python3
"""Pins held-out-15 (docs/bench/security-gates-heldout15-1025): preregistered hashes, the BLIND guard rows recorded in README.md, the live rival scores,
and the live in-sample guard score since wave 11 (60/60 blocked, 0/60 benign blocked). A moved number means a rule edit changed a scored corpus: re-score,
record it in README.md and update the pins deliberately. Offline; commands are only classified."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout15-1025"

fz = (H / "SHA256-frozen.txt").read_text()
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-15 corpus drifted: {name}"
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert led["ts"] == "2026-10-25T12:59:59Z" and led["event"] == "preregistered"
assert hashlib.sha256((H / "SHA256-frozen.txt").read_bytes()).hexdigest() == led["sha256"], "held-out-15 ledger hash drifted"

R = (H / "README.md").read_text()
for want in ("blocked 59 of 60 dangerous commands and flagged 2 of 60 benign", "safety-net subset blocked 16 of 60 (2 unported rows, 2 benign flagged)", "hooks-mastery rules 11 of 60 (7 benign flagged)", "prereg/heldout15 at 52d29c108"):
    assert want in R, f"missing from README.md: {want}"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun and "false positives: []" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 11/60  FP 7/60", "safety-net (ported subset): blocked 16/60 (2 unported)  FP 2/60"):
    assert want in riv, (want, riv)
print("held-out-15 security gates pins: ok")
