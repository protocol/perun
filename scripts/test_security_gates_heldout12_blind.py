#!/usr/bin/env python3
"""Pins held-out-12 (docs/bench/security-gates-heldout12-1025): preregistered hashes, the BLIND guard rows recorded in RESULTS.md, the live rival scores,
and the live in-sample guard score since wave 9 (60/60 blocked, 0/60 benign blocked). A moved number means a rule edit changed a scored corpus: re-score,
record it in RESULTS.md and update the pins deliberately. Offline; commands are only classified."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout12-1025"

fz = (H / "SHA256-frozen.txt").read_text()
for l in fz.splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-12 corpus drifted: {name}"
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert led["ts"] == "2026-10-25T08:52:43Z" and led["event"] == "preregistered"
for n, h in led["sha256"].items():
    assert hashlib.sha256((H / n).read_bytes()).hexdigest() == h, f"held-out-12 ledger hash drifted: {n}"

R = (H / "RESULTS.md").read_text()
for row in ("| Perun guard, wave 8 pre-review b9aa22871 (blind) | 57 | 0 |", "| Perun guard, wave 8 post-review (blind) | 57 | 0 |",
            "| Perun guard, main 8eb9fc0d5 (blind) | 56 | 0 |", "| Perun guard, wave 9 (in-sample) | 60 | 0 |",
            "| claude-code-safety-net (ported subset, 1 row unported) | 12 | 3 |", "| hooks-mastery (ported) | 7 | 10 |"):
    assert row in R, f"row missing from RESULTS.md: {row}"
assert "In-sample since wave 9" in R and "prereg/heldout12" in R and "25c580ef8" in R


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
assert "destructive guard: blocked 60/60  FP 0/60" in perun and "false positives: []" in perun, perun
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("hooks-mastery (ported): blocked 7/60  FP 10/60", "safety-net (ported subset): blocked 12/60 (1 unported)  FP 3/60"):
    assert want in riv, (want, riv)
print("held-out-12 security gates pins: ok")
