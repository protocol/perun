#!/usr/bin/env python3
"""Tests: audit_sweep rescans when a tool recorded as not installed appears on PATH; only the exact hub marker text counts as missing;
fingerprints ignore line numbers but keep digit-only-different rows apart; stdout never carries finding text."""
import atexit, json, os, shutil, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

FAKE = '''import json, os, sys
t = os.path.dirname(sys.argv[sys.argv.index("--repo") + 1])
open(t + "/calls.log", "a").write(" ".join(sys.argv[1:]) + "\\n")
rows = [{"file": "f.py", "line": 1, "rule": "r", "text": "SECRET-TEXT 1", "tool": "fake"}]
if os.path.exists(t + "/bin/faketool"):
    pass
else:
    rows.append({"file": "", "line": 0, "rule": "not-checked", "text": open(t + "/gap").read(), "tool": "faketool"})
print(json.dumps(rows))
'''


def test_fingerprint():
    row = lambda text, line: {"tool": "t", "rule": "r", "file": "f", "text": text, "line": line}
    assert a.fingerprint("r", row("x", 3)) == a.fingerprint("r", row("x", 9)), "same row at 2 line numbers is one alert"
    assert a.fingerprint("r", row("port 80 open", 1)) != a.fingerprint("r", row("port 81 open", 1)), "digit-only-different rows stay distinct"


def sweep_env(gap):
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    atexit.register(shutil.rmtree, t, True)
    open(os.path.join(t, "fake.py"), "w").write(FAKE)
    open(os.path.join(t, "gap"), "w").write(gap)
    os.makedirs(os.path.join(t, "bin"))
    open(os.path.join(t, "checks.sh"), "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
    repo, state = os.path.join(t, "acme"), os.path.join(t, "s.json")
    os.makedirs(repo)
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("init", "-q"); open(os.path.join(repo, "f.py"), "w").write("x"); g("add", "f.py"); g("commit", "-qm", "a")
    def run():
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(t, "checks.sh"), PATH=os.path.join(t, "bin") + os.pathsep + os.environ["PATH"])
        return subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", repo, "--state", state], capture_output=True, text=True, env=env)
    return t, state, run


def test_missing_then_installed_rescans():
    t, state, run = sweep_env("not installed")
    r = run()
    assert "SECRET-TEXT" not in r.stdout, "stdout must carry no finding text"
    st = list(json.load(open(state)).values())[0]
    assert st["missing"] == ["faketool"] and st.get("sha"), st
    n = len(open(os.path.join(t, "calls.log")).read().splitlines())
    run()
    assert len(open(os.path.join(t, "calls.log")).read().splitlines()) == n, "tool still missing: idle repo skipped"
    p = os.path.join(t, "bin", "faketool")
    open(p, "w").write("#!/bin/sh\n"); os.chmod(p, 0o755)
    r = run()
    assert open(os.path.join(t, "calls.log")).read().splitlines()[-1].endswith("--full"), "install must force a full rescan"
    assert list(json.load(open(state)).values())[0]["missing"] == [], "missing list cleared"


def test_crash_text_does_not_advance():
    t, state, run = sweep_env("faketool: crashed, not installed correctly")
    run()
    st = list(json.load(open(state)).values())[0]
    assert "sha" not in st, "crash text mentioning 'not installed' must hold the sha"


bad = 0
for f in (test_fingerprint, test_missing_then_installed_rescans, test_crash_text_does_not_advance):
    try:
        f(); print("ok", f.__name__)
    except AssertionError as e:
        bad += 1; print("FAIL", f.__name__, e)
print(f"Tests: {3 - bad}/3")
sys.exit(bad)
