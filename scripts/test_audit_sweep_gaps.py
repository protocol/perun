#!/usr/bin/env python3
"""Tests: a blocking not-checked row (a scanner timeout or crash) gets its own GAP row and exit 1, while a tool that is merely not
installed gives only a COVERAGE row and exit 0; a --full scan passes a --timeout above the hub's 60 s default; the core scanners the hub
skips without any row when missing are named in one COVERAGE row; a scanner that prints `[]` and then exits non-zero is an ERROR, never a
clean scan; review_checks.sh still runs pyflakes as a module on a Python that rejects -P (before 3.11). No network."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", ".claude", "skills", "deep-code-review", "scripts")
# fake review_checks.sh: logs its argv to $T/calls.log and prints $T/rows.json (T = the dir above the repo)
FAKE = '''import os, sys
a = sys.argv[1:]
t = os.path.dirname(a[a.index("--repo") + 1])
open(t + "/calls.log", "a").write(" ".join(a) + "\\n")
print(open(t + "/rows.json").read())
'''
# the hub's `have` skips these without a row when missing; ruff/pyflakes is fixed by either binary
CORE = {"shellcheck": ("shellcheck",), "semgrep": ("semgrep",), "trivy": ("trivy",), "osv-scanner": ("osv-scanner",),
        "ruff/pyflakes": ("ruff", "pyflakes")}
ok = 0


def check(c, m):
    global ok
    if not c:
        raise AssertionError(m)
    ok += 1


def nc(tool, m):
    return {"file": "", "line": 0, "rule": "not-checked", "text": "not-checked: " + m, "message": m, "tool": tool}


def sweep(rows, path=None, checks=None):
    """One `audit_sweep.py --local` run on a fresh one-commit repo whose fake scanner prints `rows` (or runs the `checks` shell body).
    Returns (exit code, TSV rows without the header, scanner argv lines, the repo's state entry or {})."""
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        with open(os.path.join(t, "fake.py"), "w") as fh:
            fh.write(FAKE)
        with open(os.path.join(t, "rows.json"), "w") as fh:
            json.dump(rows, fh)
        with open(os.path.join(t, "checks.sh"), "w") as fh:
            fh.write(checks or f'exec {sys.executable} {t}/fake.py "$@"\n')
        repo, state = os.path.join(t, "acme"), os.path.join(t, "s.json")
        os.makedirs(repo)
        for c in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "a"]):
            subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(t, "checks.sh"), PATH=path or os.environ["PATH"])
        r = subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", repo, "--state", state], capture_output=True, text=True, env=env)
        log = os.path.join(t, "calls.log")
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        st = list(json.load(open(state)).values()) if os.path.exists(state) else []
        return r.returncode, [l.split("\t") for l in r.stdout.splitlines()[1:]], calls, (st[0] if st else {})
    finally:
        shutil.rmtree(t, ignore_errors=True)


def test_blocking_gap_alerts():
    rc, rows, calls, st = sweep([nc("semgrep", "timeout 60s")])
    check(rc == 1 and [x[1:5] for x in rows if x[1] == "GAP"] == [["GAP", "", "1 not-checked: timeout 1", "semgrep"]] and "sha" not in st,
          f"a timed-out scanner must get its own GAP row, exit 1 and hold the sha: {rc} {rows} {st}")
    rc, rows, _, st = sweep([nc("shellcheck", "not installed")])
    check(rc == 0 and not [x for x in rows if x[1] == "GAP"] and st.get("sha"), f"a missing tool is no GAP and no alert: {rc} {rows}")
    c = calls[0].split()
    check("--full" in c and "--timeout" in c and int(c[c.index("--timeout") + 1]) > 60, f"--full must pass a timeout above 60 s: {calls}")


def test_missing_core_scanners_named():
    p = "/usr/bin:/bin"
    gone = [n for n, bins in CORE.items() if not any(shutil.which(b, path=p) for b in bins)]
    check(gone, f"some core scanner must be absent from {p}")
    rc, rows, _, _ = sweep([], path=p)
    got = [x for x in rows if x[1] == "COVERAGE" and x[3] == "not installed"]
    check(rc == 0 and len(got) == 1 and got[0][4] == " ".join(gone), f"one COVERAGE row must name {gone}: {rc} {rows}")


def test_valid_json_then_nonzero_exit_is_error():
    rc, rows, _, st = sweep([], checks="echo '[]'; exit 3\n")
    check(rc == 1 and rows and rows[0][1] == "ERROR" and not st.get("sha"), f"`[]` then exit 3 must be an ERROR: {rc} {rows} {st}")


def test_pyflakes_module_without_P():
    """A python3 that rejects -P (like 3.9) and a pyflakes module only on PYTHONPATH: the hub must still run pyflakes."""
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        b, lib, repo = (os.path.join(t, n) for n in ("bin", "lib", "repo"))
        os.makedirs(os.path.join(lib, "pyflakes"))
        os.makedirs(b)
        os.makedirs(repo)
        with open(os.path.join(b, "python3"), "w") as fh:
            fh.write(f'#!/bin/sh\n[ "$1" = -P ] && {{ echo "Unknown option: -P" >&2; exit 2; }}\nexec {sys.executable} "$@"\n')
        os.chmod(os.path.join(b, "python3"), 0o755)
        open(os.path.join(lib, "pyflakes", "__init__.py"), "w").close()
        with open(os.path.join(lib, "pyflakes", "api.py"), "w") as fh:
            fh.write('import sys\ndef main(prog=None, args=None):\n    a = sys.argv[1:]\n    if "--version" in a:\n        print("3.0.0"); return\n'
                     '    for f in a:\n        print(f"{f}:1:1: undefined name \'zz\'")\n    raise SystemExit(1)\n')
        with open(os.path.join(repo, "x.py"), "w") as fh:
            fh.write("zz\n")
        for c in (["init", "-q"], ["add", "x.py"], ["commit", "-qm", "a"]):
            subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
        env = dict(os.environ, PATH=b + ":/usr/bin:/bin", HOME=t, DCR_USER_BIN="", CI="true", PYTHONPATH=lib)
        r = subprocess.run(["bash", os.path.join(D, "review_checks.sh"), "--repo", repo, "--full", "--timeout", "30"], capture_output=True, text=True, env=env)
        rows = json.loads(r.stdout)
        check(any(x.get("tool") == "pyflakes" and x.get("file") == "x.py" for x in rows) and "ruff/pyflakes (not installed)" not in r.stderr,
              f"pyflakes must run without -P: {r.stdout[:300]} {r.stderr[-300:]}")
    finally:
        shutil.rmtree(t, ignore_errors=True)


bad = 0
for f in (test_blocking_gap_alerts, test_missing_core_scanners_named, test_valid_json_then_nonzero_exit_is_error, test_pyflakes_module_without_P):
    try:
        f()
    except AssertionError as e:
        bad += 1
        print("FAIL", f.__name__, e)
print(f"Tests: {ok}/{ok + bad}")
sys.exit(1 if bad else 0)
