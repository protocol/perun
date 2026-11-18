#!/usr/bin/env python3
"""Tests: audit_sweep.py on temp git repos with a fake scanner (AUDIT_SWEEP_CHECKS). Run 1 reports every finding (mode
first); run 2 reports only the delta since the stored sha and scans with plain `--base LAST` (the `new` filter) plus `--base LAST --history`; an unchanged HEAD
is not scanned; a history rewrite forces a `--full` rescan marked `rewrite` that reports only unseen fingerprints; rows
with `new: false` are dropped; `not-checked` rows (missing tool) are never reported but give a COVERAGE row, a stderr gap count and no sha advance; a scanner-file change forces a `rescan`; a failing scanner gives an ERROR row, exit 1, an unchanged state and no temp file; a corrupt state or failed listing gives an ERROR row and exit 3; a --org clone failure gives an ERROR row and exit 1; the REAL review_checks.sh (tiny temp repo) emits a JSON array with `new` only in plain diff mode. No network."""
import json
import os
import subprocess
import sys
import tempfile

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "audit_sweep.py")
# fake review_checks.sh: one row per tracked file (--full) or per file changed since --base (--history) containing MARK.
FAKE = '''#!/usr/bin/env python3
import json, subprocess, sys
a = sys.argv[1:]
repo = a[a.index("--repo") + 1]
open(repo + "/../calls.log", "a").write(" ".join(a[2:]) + "\\n")
g = lambda *x: subprocess.run(["git", "-C", repo, *x], capture_output=True, text=True).stdout.split()
files = g("diff", "--name-only", a[a.index("--base") + 1], "HEAD") if "--base" in a else g("ls-files")
rows = [{"file": f, "rule": "fake-secret", "text": "fake-secret: hit", "tool": "fake"} for f in files if f.startswith("m_")]
if "--base" in a:
    if "--history" not in a:  # like the real scanner, `new` only in plain diff mode
        rows.append({"file": "old.txt", "rule": "fake-secret", "text": "x", "tool": "fake", "new": False})
if __import__("os").path.exists(repo + "/../gap"):  # coverage gap, never a finding
    rows.append({"file": "", "line": 0, "rule": "not-checked", "text": "devskim: crashed", "tool": "devskim"})
print(json.dumps(rows))
'''
ok = 0


def check(c, msg):
    global ok
    if not c:
        sys.exit(f"FAIL: {msg}")
    ok += 1


def smoke_real(t):
    """Real review_checks.sh on a tiny repo: JSON array each mode; `new` only in plain diff mode (not --full or --history)."""
    rc = os.path.join(os.path.dirname(S), "review_checks.sh")
    repo = os.path.join(t, "real")
    os.makedirs(repo)
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("init", "-q")
    # the Dockerfile, added in the last commit, is flagged by the hub's own world-writable-chmod grep in every mode, whatever is installed
    for n, body in (("a.txt", "a\n"), ("Dockerfile", "FROM scratch\nRUN chmod 777 /app\n")):
        with open(os.path.join(repo, n), "w") as fh:
            fh.write(body)
        g("add", n)
        g("commit", "-qm", n)
    env = dict(os.environ, HOME=t, CI="true")
    for flags, has_new in ((["--full"], False), (["--base", "HEAD~1", "--history"], False), (["--base", "HEAD~1"], True)):
        r = subprocess.run(["bash", rc, "--repo", repo, "--timeout", "5", *flags], capture_output=True, text=True, env=env)
        rows = json.loads(r.stdout)
        check(isinstance(rows, list) and any(x.get("rule") == "world-writable-chmod" for x in rows) and all(("new" in x) == has_new for x in rows),
              f"real scanner {flags}: rc={r.returncode} {r.stdout[:200]}")


def main():
    with tempfile.TemporaryDirectory() as t:
        fake = os.path.join(t, "fake.py")
        with open(fake, "w") as fh:
            fh.write(FAKE)
        env = dict(os.environ)
        wrap = os.path.join(t, "checks.sh")  # S runs `bash $CHECKS`; make that exec the python fake
        with open(wrap, "w") as fh:
            fh.write(f'exec {sys.executable} {fake} "$@"\n')
        env["AUDIT_SWEEP_CHECKS"] = wrap
        repo, state, log = os.path.join(t, "acme"), os.path.join(t, "state.json"), os.path.join(t, "calls.log")

        def git(*c):
            subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c],
                           check=True, capture_output=True)

        def commit(name):
            with open(os.path.join(repo, name), "w") as fh:
                fh.write(name)
            git("add", name)
            git("commit", "-qm", name)

        err = [""]

        def sweep():
            r = subprocess.run([sys.executable, S, "--local", repo, "--state", state], capture_output=True, text=True, env=env)
            err[:] = [r.stderr]
            rows = [l.split("\t") for l in r.stdout.splitlines()[1:]]
            calls = open(log).read().splitlines() if os.path.exists(log) else []
            return r.returncode, rows, calls

        os.makedirs(repo)
        git("init", "-q")
        commit("m_a.txt")
        rc, rows, calls = sweep()
        check(rc == 0 and [(r[1], r[2]) for r in rows] == [("first", "m_a.txt")], f"run1 {rc} {rows}")
        check(calls[-1].endswith("--full"), f"run1 must scan --full: {calls}")
        commit("m_b.txt")
        rc, rows, calls = sweep()
        check([(r[1], r[2]) for r in rows] == [("delta", "m_b.txt")], f"run2 must report only the delta: {rows}")
        check("--base" in calls[-2] and "--history" not in calls[-2] and "--history" in calls[-1], f"run2 must scan diff then history: {calls[-2:]}")
        n = len(calls)
        rc, rows, calls = sweep()
        check(rc == 0 and rows == [] and len(calls) == n, "same HEAD must skip with no scan")
        # forced rewrite: drop m_b, add m_c; stored sha is no longer an ancestor
        git("reset", "-q", "--hard", "HEAD~1")
        commit("m_c.txt")
        rc, rows, calls = sweep()
        check(calls[-1].endswith("--full"), f"rewrite must rescan --full: {calls[-1]}")
        check([(r[1], r[2]) for r in rows] == [("rewrite", "m_c.txt")], f"rewrite reports only unseen: {rows}")
        with open(state) as fh:
            st = json.load(fh)
        check("fake-secret: hit" not in json.dumps(st) and len(list(st.values())[0]["seen"]) == 3, "state: hashed repo key, 3 seen")
        # rule/tool upgrade (scanner file changes) on a plain descendant: full rescan, only unseen reported
        commit("m_d.txt")
        with open(wrap, "a") as fh:
            fh.write("# upgraded\n")
        rc, rows, calls = sweep()
        check(calls[-1].endswith("--full") and [(r[1], r[2]) for r in rows] == [("rescan", "m_d.txt")], f"stamp change: {calls[-1]} {rows}")
        # same HEAD, scanner changed again: the idle repo is still rescanned (mode rescan, --full), no new rows
        n = len(calls)
        with open(wrap, "a") as fh:
            fh.write("# upgraded again\n")
        rc, rows, calls = sweep()
        check(rc == 0 and rows == [] and len(calls) == n + 1 and calls[-1].endswith("--full"), f"idle stamp change: {calls[-1]} {rows}")
        rc, rows, calls = sweep()
        check(len(calls) == n + 1, "stamp now current: idle repo skipped again")
        # coverage gap: COVERAGE row, stderr count, sha and tool stamp not advanced; once the gap closes the sha advances
        sha0 = list(json.load(open(state)).values())[0]["sha"]
        commit("m_g.txt")
        open(os.path.join(t, "gap"), "w").close()
        rc, rows, _ = sweep()
        st = list(json.load(open(state)).values())[0]
        check(rc == 0 and [(r[1], r[2]) for r in rows] == [("delta", "m_g.txt"), ("COVERAGE", "")] and rows[1][3] == "2 not-checked", f"gap rows: {rc} {rows}")
        check("2 not-checked row(s)" in err[0] and st["sha"] == sha0, f"gap must count on stderr and hold sha: {err} {st['sha']}")
        rc, rows, _ = sweep()  # same range rescanned: nothing new, gap still reported
        check([r[1] for r in rows] == ["COVERAGE"], f"gap persists: {rows}")
        os.remove(os.path.join(t, "gap"))
        rc, rows, _ = sweep()
        check(rc == 0 and rows == [] and list(json.load(open(state)).values())[0]["sha"] != sha0, f"closed gap must advance sha: {rows}")
        # failing scanner: alert, state untouched
        commit("m_e.txt")
        before = open(state).read()
        with open(wrap, "w") as fh:
            fh.write("exit 7\n")
        rc, rows, _ = sweep()
        check(rc == 1 and rows and rows[0][1] == "ERROR", f"failing scanner must alert: {rc} {rows}")
        check(open(state).read() == before, "failed run must not advance state")
        check(not [f for f in os.listdir(t) if f.startswith("tmp")], "temp state file left behind")
        # scanner exits 0 with no output: broken tool, not "0 findings"
        with open(wrap, "w") as fh:
            fh.write("exit 0\n")
        rc, rows, _ = sweep()
        check(rc == 1 and rows and rows[0][1] == "ERROR" and open(state).read() == before, f"silent scanner must alert: {rc} {rows}")
        # corrupt state: ERROR row, distinct exit 3, file untouched
        with open(state, "w") as fh:
            fh.write("{not json")
        rc, rows, _ = sweep()
        check(rc == 3 and rows[0][1] == "ERROR" and open(state).read() == "{not json", f"corrupt state: {rc} {rows}")
        # unwritable state path (parent is a file): ERROR row, exit 3, no traceback
        with open(os.path.join(t, "afile"), "w") as fh:
            fh.write("x")
        r = subprocess.run([sys.executable, S, "--local", repo, "--state", os.path.join(t, "afile", "s.json")],
                           capture_output=True, text=True, env=dict(env, AUDIT_SWEEP_CHECKS=wrap.replace("checks", "nope")))
        check(r.returncode == 3 and "state not saved" in r.stdout and "Traceback" not in r.stderr, f"write failure: {r.returncode} {r.stdout} {r.stderr}")
        # failed org listing (fake curl on PATH): ERROR row, exit 3, no traceback
        os.makedirs(os.path.join(t, "bin"))
        with open(os.path.join(t, "bin", "curl"), "w") as fh:
            fh.write("#!/bin/sh\nexit 22\n")
        os.chmod(os.path.join(t, "bin", "curl"), 0o755)
        r = subprocess.run([sys.executable, S, "--org", "acme", "--token-env", "NOPE", "--state", os.path.join(t, "s2.json")],
                           capture_output=True, text=True, env=dict(env, PATH=os.path.join(t, "bin")))
        check(r.returncode == 3 and "ERROR" in r.stdout and "Traceback" not in r.stderr, f"listing failure: {r.returncode} {r.stderr}")
        # --org: listed repo whose clone fails -> ERROR row, exit 1 (curl fake lists one repo with a dead clone url)
        os.makedirs(os.path.join(t, "bin2"))
        with open(os.path.join(t, "bin2", "curl"), "w") as fh:
            fh.write('#!/bin/sh\necho \'[{"name":"ghost","clone_url":"/nonexistent/ghost.git"}]\'\n')
        os.chmod(os.path.join(t, "bin2", "curl"), 0o755)
        r = subprocess.run([sys.executable, S, "--org", "acme", "--token-env", "NOPE", "--state", os.path.join(t, "s3.json")],
                           capture_output=True, text=True, env=dict(env, PATH=os.path.join(t, "bin2") + os.pathsep + os.environ["PATH"]))
        check(r.returncode == 1 and "ghost\tERROR\t\tRuntimeError: clone failed" in r.stdout and "Traceback" not in r.stderr, f"clone failure: {r.returncode} {r.stdout}")
        smoke_real(t)
    print(f"Tests: {ok}/{ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
