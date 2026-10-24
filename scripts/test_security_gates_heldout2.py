#!/usr/bin/env python3
"""Pins the out-of-sample held-out-2 security-gates scores (docs/bench/security-gates-heldout2-1024) and its preregistered hashes.

Perun's rules were frozen before these rows were scored. A moved number means a rule or port edit changed
behavior on a corpus that is meant to stay out of sample: re-score, record it in RESULTS.md and update the pins deliberately.
Offline; commands are only classified.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout2-1024"

frozen = (H / "SHA256-frozen.txt").read_text().splitlines()
assert hashlib.sha256("".join(l + "\n" for l in frozen[:5]).encode()).hexdigest() == "bfe946c27191a7100010e878cad37fd4a1a6605170eaa77435c8d35b658c02eb", "preregistered hash list drifted"
# later lines for a path are disclosed amendments (see ledger.jsonl); the last one pins the file
for name, want in {name: want for want, name in (l.split() for l in frozen)}.items():
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-2 corpus drifted: {name}"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
for want in ("secret gate: recall 23/40  FP 2/40", "destructive guard: blocked 37/50  FP 4/50"):
    assert want in perun, (want, perun)
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("recall 26/40  FP 0/40", "hooks-mastery (ported): blocked 9/50  FP 5/50",
             "safety-net (ported subset): blocked 18/50 (1 unported)  FP 2/50"):
    assert want in riv, (want, riv)
print("held-out-2 security gates pins: ok")
