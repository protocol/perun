#!/usr/bin/env python3
"""Tests: audit_sweep fingerprint stability (a volatile commit counter is ignored, the file is not) and that a not-installed tool does not block the sha advance."""
import json, os, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

FAKE = '''import json, sys
open(sys.argv[sys.argv.index("--repo") + 1] + "/../calls.log", "a").write(" ".join(sys.argv[1:]) + "\\n")
print(json.dumps([{"file": "", "line": 0, "rule": "not-checked", "text": "not installed", "tool": "nosuchtool-xyz"}]))
'''


def test_fingerprint_stable():
    row = lambda n, f="k.env": {"tool": "secret-exposure", "rule": "exposed-secret", "file": f, "text": f"P1; in {f}; {n} commits since"}
    assert a.fingerprint("r", row(3)) == a.fingerprint("r", row(4)), "counter change must keep fingerprint"
    assert a.fingerprint("r", row(3)) != a.fingerprint("r", row(3, "other.env")), "different file must differ"



def test_missing_tool_does_not_block_advance():
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "fake.py"), "w").write(FAKE)
        open(os.path.join(t, "checks.sh"), "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(t, "checks.sh"))
        repo, state = os.path.join(t, "acme"), os.path.join(t, "s.json")
        os.makedirs(repo)
        g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
        g("init", "-q")
        run = lambda: subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", repo, "--state", state], capture_output=True, text=True, env=env)
        calls = lambda: open(os.path.join(t, "calls.log")).read().splitlines()
        head = lambda: subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        for n in ("a", "b"):
            open(os.path.join(repo, n), "w").write(n)
            g("add", n); g("commit", "-qm", n)
            r = run()
            assert "COVERAGE" in r.stdout, r.stdout  # missing tool stays listed
            assert json.load(open(state)) and list(json.load(open(state)).values())[0]["sha"] == head(), "sha must advance despite a missing tool"
        assert any("--base" in c for c in calls()), "second sweep must reach delta mode"
        n = len(calls())
        run()
        assert len(calls()) == n, "unchanged HEAD must skip"


bad = 0
for f in (test_fingerprint_stable, test_missing_tool_does_not_block_advance):
    try:
        f()
        print("ok", f.__name__)
    except AssertionError as e:
        bad += 1
        print("FAIL", f.__name__, e)
print(f"Tests: {2 - bad}/2")
sys.exit(bad)
