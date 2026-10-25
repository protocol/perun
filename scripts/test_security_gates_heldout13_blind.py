#!/usr/bin/env python3
"""Pins held-out-13 (docs/bench/security-gates-heldout13-1025): preregistered hashes, the BLIND guard rows recorded in RESULTS.md, the live rival scores,
and the live in-sample guard score since wave 10 (60/60 blocked, 0/60 benign blocked). A moved number means a rule edit changed a scored corpus: re-score,
record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout13-1025"

fz = (H / "SHA256-frozen.txt").read_text()
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-13 corpus drifted: {name}"
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert led["ts"] == "2026-10-25T10:15:24Z" and led["event"] == "preregistered"
assert hashlib.sha256((H / "SHA256-frozen.txt").read_bytes()).hexdigest() == led["sha256"], "held-out-13 ledger hash drifted"

R = (H / "RESULTS.md").read_text()
for row in ("| Perun guard, wave 9 36754bed0 (blind) | 54 | 1 |", "| Perun guard, main 8eb9fc0d5 (blind) | 47 | 3 |", "| Perun guard, wave 10 (in-sample) | 60 | 0 |",
            "| claude-code-safety-net (ported subset, 0 unported) | 11 | 2 |", "| hooks-mastery (ported) | 7 | 3 |"):
    assert row in R, f"row missing from RESULTS.md: {row}"
assert "In-sample since wave 10" in R and "prereg/heldout13" in R and "4cec71b8f" in R


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun and "false positives: []" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 7/60  FP 3/60", "safety-net (ported subset): blocked 11/60 (0 unported)  FP 2/60"):
    assert want in riv, (want, riv)
print("held-out-13 security gates pins: ok")
