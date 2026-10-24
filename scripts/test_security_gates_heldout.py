#!/usr/bin/env python3
"""Pins the held-out security-gates scores (docs/bench/security-gates-heldout-1024) and the preregistered corpus hashes.

The corpora were written before the rules or the first corpus were read. Scores pinned here are AFTER the gatefix2 rules were written against the misses, so this corpus is now in-sample (before: secret 21/30, guard 26/40; held-out-2 is the out-of-sample test). A moved
number means a rule or port edit changed held-out behavior: re-score, record it in the README, and update the pins
deliberately. Offline; commands are only classified.
"""
import hashlib, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout-1024"

# later lines for a path are disclosed amendments (see ledger.jsonl); the last one pins the file
pins = {name: want for want, name in (l.split() for l in (H / "SHA256-frozen.txt").read_text().splitlines())}
for name, want in pins.items():
    l = f"{want}  {name}"
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out corpus drifted: {name}"
    assert l in (H / "README.md").read_text(), f"README lacks frozen hash line: {name}"

import json
frozen_txt = (H / "SHA256-frozen.txt").read_text()
for e in map(json.loads, (H / "ledger.jsonl").read_text().splitlines()):
    assert e["event"] != "amendment" or e["sha256"] in frozen_txt, f"ledger amendment hash not in SHA256-frozen.txt: {e['sha256']}"

# markers-stripped content equals the preregistered corpus (markers were added to 3 rows after the prereg commit)
assert hashlib.sha256((H / "secret-leaks.txt").read_bytes().replace(b"@@", b"")).hexdigest() == "7c5309f21640db3a8a7eb77cb63f94e557d066ea8b7a8fb13d840d040f650cfd"


def run(*a):
    r = subprocess.run([sys.executable, "-I", *a, "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


perun = run(str(B / "security-gates-1024/score.py"))
for want in ("secret gate: recall 30/30  FP 2/30", "destructive guard: blocked 40/40  FP 3/40"):
    assert want in perun, (want, perun)
riv = run(str(B / "security-gates-1024/rivals/score_rivals.py"))
for want in ("recall 23/30  FP 0/30", "hooks-mastery (ported): blocked 9/40  FP 6/40",
             "safety-net (ported subset): blocked 17/40 (0 unported)  FP 2/40"):
    assert want in riv, (want, riv)
print("held-out security gates pins: ok")
