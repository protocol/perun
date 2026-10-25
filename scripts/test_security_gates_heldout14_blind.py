#!/usr/bin/env python3
"""Pins held-out-14 (docs/bench/security-gates-heldout14-1025): preregistered hashes, the BLIND guard rows recorded in RESULTS.md, the live rival scores,
and the live in-sample guard score since wave 11 (60/60 blocked, 0/60 benign blocked). A moved number means a rule edit changed a scored corpus: re-score,
record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout14-1025"

fz = (H / "SHA256-frozen.txt").read_text()
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-14 corpus drifted: {name}"
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert led["ts"] == "2026-10-25T12:27:25Z" and led["event"] == "preregistered"
assert hashlib.sha256((H / "SHA256-frozen.txt").read_bytes()).hexdigest() == led["sha256"], "held-out-14 ledger hash drifted"

R = (H / "RESULTS.md").read_text()
for row in ("| Perun guard, wave 10 5adab34e4 (blind) | 54 | 0 |", "| Perun guard, main 7453990b1 (blind) | 53 | 1 |", "| Perun guard, wave 11 (in-sample) | 60 | 0 |",
            "| claude-code-safety-net (ported subset, 0 unported) | 17 | 0 |", "| hooks-mastery (ported) | 14 | 8 |"):
    assert row in R, f"row missing from RESULTS.md: {row}"
assert "In-sample since wave 11" in R and "prereg/heldout14" in R and "c19253607" in R


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun and "false positives: []" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 14/60  FP 8/60", "safety-net (ported subset): blocked 17/60 (0 unported)  FP 0/60"):
    assert want in riv, (want, riv)
print("held-out-14 security gates pins: ok")
