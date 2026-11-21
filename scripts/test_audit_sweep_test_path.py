#!/usr/bin/env python3
"""Tests: audit_sweep and the hub's test-path hint. norm() strips the " [test-path]" suffix, so a hinted row keeps the fingerprint it had
before the hint and an untouched row's fingerprint is unchanged; rows hinted test-path are listed after every other row as one TESTPATH
count line per (tool, rule), and the state still keeps every row's fingerprint. AUDIT_SWEEP_PY=<path> tests another copy (used to prove
the cases fail before the change). No network; temp dirs are removed."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
S = os.environ.get("AUDIT_SWEEP_PY") or os.path.join(D, "audit_sweep.py")
sys.path.insert(0, D)
spec = importlib.util.spec_from_file_location("audit_sweep", S)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
ok = 0


def check(c, msg):
    global ok
    if not c:
        sys.exit(f"FAIL: {msg}")
    ok += 1


t = "python.lang.security.audit.eval-detected: eval"
check(a.norm(t + " [test-path]") == a.norm(t), "norm strips the [test-path] suffix")
check(a.norm(t + " [test-path] [corroborated by: bandit, semgrep]") == a.norm(t), "norm strips [test-path] next to [corroborated by: ...]")
row = {"tool": "semgrep", "rule": "eval-detected", "file": "tests/a.py", "text": t}
check(a.fingerprint("acme", dict(row, text=t + " [test-path]", hint="test-path")) == a.fingerprint("acme", row), "a hinted row keeps its pre-hint fingerprint")
want = hashlib.sha256("|".join(["acme", "semgrep", "eval-detected", "src/a.py", t]).encode()).hexdigest()
check(a.fingerprint("acme", dict(row, file="src/a.py")) == want, "an untouched row's fingerprint is unchanged")

ROWS = [{"tool": "semgrep", "rule": "eval-detected", "file": f"tests/{f}.py", "line": 1, "text": "eval-detected: eval [test-path]", "hint": "test-path"} for f in "ab"]
ROWS += [{"tool": "bandit", "rule": "B307", "file": "tests/c.py", "line": 2, "text": "B307: eval [test-path]", "hint": "test-path"},
         {"tool": "semgrep", "rule": "eval-detected", "file": "src/a.py", "line": 1, "text": "eval-detected: eval"}]
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "acme")
    os.makedirs(p)
    subprocess.run(["git", "-C", p, "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", p, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", "commit", "-q", "--allow-empty", "-m", "a"],
                   check=True, capture_output=True)
    with open(os.path.join(d, "checks.sh"), "w") as fh:
        fh.write(f"cat <<'J'\n{json.dumps(ROWS)}\nJ\n")
    st = os.path.join(d, "s.json")
    r = subprocess.run([sys.executable, S, "--local", p, "--state", st], capture_output=True, text=True, check=False,
                       env=dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(d, "checks.sh")))
    check(r.returncode == 0, f"sweep exit {r.returncode}: {r.stdout} {r.stderr}")
    out = [line.split("\t") for line in r.stdout.splitlines()[1:]]
    tp = [x for x in out if x[1] == "TESTPATH"]
    check(tp == [[p, "TESTPATH", "1 rows", "B307", "bandit", ""], [p, "TESTPATH", "2 rows", "eval-detected", "semgrep", ""]],
          f"one TESTPATH count line per (tool, rule): {tp}")
    check(out[-len(tp):] == tp, f"TESTPATH lines come after every other row: {out}")
    check([x[2] for x in out if x[1] == "first"] == ["src/a.py"], f"only the unhinted row is listed per row: {out}")
    with open(st) as fh:
        seen = set(json.load(fh)[hashlib.sha256(p.encode()).hexdigest()[:16]]["seen"])
    check({a.fingerprint(p, x) for x in ROWS} <= seen, "the state keeps every row's fingerprint, hinted ones included")
print(f"Tests: {ok}/{ok}")
