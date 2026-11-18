#!/usr/bin/env python3
"""Tests: audit_sweep against the real review_checks.sh hub texts. gitleaks' "not installed; secrets were not scanned" counts as a missing
tool (the sha advances); a tool on PATH that the hub still calls missing is rescanned once, not forever; a real gap still holds the sha
while the missing list updates; hub names that are not binaries map to their binaries; the same text on two lines of a file is two
alerts; state is saved per repo; save() cleans its temp file on any exception and returns 3 on OSError. Temp dirs are removed."""
import contextlib, io, json, os, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

GITLEAKS = "not installed; secrets were not scanned"  # review_checks.sh: add gitleaks ... not-checked
# fake review_checks.sh: prints $T/rows.json (T = the dir above the repo) and logs argv
FAKE = '''import os, sys
t = os.path.dirname(sys.argv[sys.argv.index("--repo") + 1])
open(t + "/calls.log", "a").write(" ".join(sys.argv[1:]) + "\\n")
print(open(t + "/rows.json").read())
'''
ok = 0


def check(c, msg):
    global ok
    if not c:
        sys.exit(f"FAIL: {msg}")
    ok += 1


def gap(tool, text):
    return {"file": "", "line": 0, "rule": "not-checked", "text": text, "tool": tool}


class Env:
    def __init__(self, t, rows):
        self.t, self.state = t, os.path.join(t, "s.json")
        self.repo = os.path.join(t, "acme")
        os.makedirs(os.path.join(t, "bin"))
        for n, c in (("fake.py", FAKE), ("checks.sh", f'exec {sys.executable} {t}/fake.py "$@"\n')):
            with open(os.path.join(t, n), "w") as fh:
                fh.write(c)
        self.rows(rows)
        os.makedirs(self.repo)
        self.git("init", "-q")
        with open(os.path.join(self.repo, "f.py"), "w") as fh:
            fh.write("x")
        self.git("add", "f.py")
        self.git("commit", "-qm", "a")

    def git(self, *c):
        subprocess.run(["git", "-C", self.repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)

    def rows(self, rows):
        with open(os.path.join(self.t, "rows.json"), "w") as fh:
            json.dump(rows, fh)

    def run(self):
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(self.t, "checks.sh"), PATH=os.path.join(self.t, "bin") + os.pathsep + os.environ["PATH"])
        r = subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", self.repo, "--state", self.state], capture_output=True, text=True, env=env)
        return r, [l.split("\t") for l in r.stdout.splitlines()[1:]]

    def st(self):
        with open(self.state) as fh:
            return list(json.load(fh).values())[0]

    def calls(self):
        with open(os.path.join(self.t, "calls.log")) as fh:
            return fh.read().splitlines()

    def install(self, name):
        p = os.path.join(self.t, "bin", name)
        with open(p, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(p, 0o755)


def test_gitleaks_text_is_missing_not_blocking(t):
    e = Env(t, [gap("gitleaks", GITLEAKS)])
    r, rows = e.run()
    st = e.st()
    check(st.get("sha") and st["missing"] == ["gitleaks"], f"gitleaks hub text must count as missing and advance the sha: {st}")
    check(rows[-1][1] == "COVERAGE", f"the gap is still reported: {rows}")


def test_on_path_but_still_missing_rescans_once(t):
    e = Env(t, [gap("faketool", "install: brew install faketool")])
    e.run()
    e.install("faketool")
    e.run()
    check(e.calls()[-1].endswith("--full") and len(e.calls()) == 2, f"install forces one full rescan: {e.calls()}")
    check(e.st()["missing"] == [] and e.st().get("sha"), "hub still says missing: dropped after one rescan")
    e.run()
    check(len(e.calls()) == 2, "no rescan loop: third run skips the idle repo")


def test_binary_map(t):
    check(a.installed("faketool-nope") is False, "an unknown tool name is looked up as a binary")
    e = Env(t, [gap("ruff/pyflakes", "not installed")])
    e.run()
    check(e.st()["missing"] == ["ruff/pyflakes"], "hub name kept as is")
    e.install("pyflakes")
    old = os.environ["PATH"]
    os.environ["PATH"] = os.path.join(t, "bin") + os.pathsep + old
    try:
        check(a.installed("ruff/pyflakes"), "ruff/pyflakes maps to the pyflakes binary")
    finally:
        os.environ["PATH"] = old


def test_block_updates_missing(t):
    e = Env(t, [gap("faketool", "not installed"), gap("shellcheck", "exit 2")])
    e.run()
    st = e.st()
    check("sha" not in st and st["missing"] == ["faketool"], f"a real gap holds the sha, the missing list still updates: {st}")


def test_occurrence_index(t):
    row = {"file": "f.py", "line": 3, "rule": "r", "text": "same text", "tool": "x"}
    e = Env(t, [row, dict(row, line=9)])
    r, rows = e.run()
    check(len([x for x in rows if x[3] == "r"]) == 2, f"same text on two lines is two alerts: {rows}")
    check(a.fingerprint("r", row) == a.fingerprint("r", row, 0) and a.fingerprint("r", row) != a.fingerprint("r", row, 1), "index 0 is the old hash")
    e.rows([row, dict(row, line=9)])
    e.git("commit", "-q", "--allow-empty", "-m", "b")
    r, rows = e.run()
    check([x for x in rows if x[3] == "r"] == [], f"second run reports neither again: {rows}")


def test_per_repo_save_and_cleanup(t):
    repos = []
    for n in ("one", "two"):
        p = os.path.join(t, n)
        os.makedirs(p)
        subprocess.run(["git", "-C", p, "init", "-q"], check=True, capture_output=True)
        subprocess.run(["git", "-C", p, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", "commit", "-q", "--allow-empty", "-m", "a"], check=True, capture_output=True)
        repos.append((n, p))
    state = os.path.join(t, "s.json")
    real_list, real_sweep, real_argv, real_mk, made = a.list_repos, a.sweep_repo, sys.argv, tempfile.mkdtemp, []

    def mk(**k):  # the clone dirs land in t, so the cleanup check below sees them
        made.append(real_mk(dir=t, **k))
        return made[-1]

    def boom(name, path, st):
        if name == "x/two":  # --org rows are org/name
            raise KeyboardInterrupt
        st["sha"] = "abc"
        return []
    a.list_repos, a.sweep_repo, sys.argv, tempfile.mkdtemp = (lambda org, tok: repos), boom, ["audit_sweep.py", "--org", "x", "--token-env", "NOPE", "--state", state], mk
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                a.main()
                check(False, "KeyboardInterrupt must propagate")
            except KeyboardInterrupt:
                pass
    finally:
        a.list_repos, a.sweep_repo, sys.argv, tempfile.mkdtemp = real_list, real_sweep, real_argv, real_mk
    with open(state) as fh:
        check(len(json.load(fh)) == 1, "repo one's state is saved although repo two was killed")
    check(len(made) == 2 and not any(os.path.exists(p) for p in made), f"both mkdtemp clone dirs made and removed: {made}")
    # save(): temp file removed on a non-OSError, OSError gives rc 3
    d = os.path.join(t, "sv")
    os.makedirs(d)
    real_dump = json.dump
    json.dump = lambda *x, **k: (_ for _ in ()).throw(KeyboardInterrupt())
    try:
        try:
            a.save({}, os.path.join(d, "s.json"))
            check(False, "save must re-raise")
        except KeyboardInterrupt:
            pass
    finally:
        json.dump = real_dump
    check(os.listdir(d) == [], f"temp file left behind after KeyboardInterrupt: {os.listdir(d)}")
    with open(os.path.join(t, "afile"), "w") as fh:
        fh.write("x")
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = a.save({}, os.path.join(t, "afile", "s.json"))
    check(rc == 3 and "state not saved" in out.getvalue(), f"save OSError -> 3: {rc}")


for f in (test_gitleaks_text_is_missing_not_blocking, test_on_path_but_still_missing_rescans_once, test_binary_map, test_block_updates_missing,
          test_occurrence_index, test_per_repo_save_and_cleanup):
    with tempfile.TemporaryDirectory() as t:
        f(t)
print(f"Tests: {ok}/{ok}")
