#!/usr/bin/env python3
"""reclaim_disk.sh: the dry run lists exactly what --apply does; it never touches locked, dirty, ignored-file,
unreachable, current or unmerged items. Each guard (# guard:NAME in the script) is mutation-tested: deleting it must make
the scenario fail. Also the perun_doctor 'disk free' row thresholds. Repos live under a temp dir only."""
import os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perun_doctor
from pathlib import Path

S = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/reclaim_disk.sh"
env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
CUR = {}  # extra env for g(): scenario() sets OLD so its lanes and branches are older than the default 24h
def g(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, env={**env, **CUR}, capture_output=True, text=True, check=True).stdout
def sh(script, cwd, *a, age="24"):
    r = subprocess.run(["bash", str(script), *a], cwd=cwd, env={**env, "RECLAIM_MIN_AGE_HOURS": age}, capture_output=True, text=True); assert r.returncode == 0, "SHFAIL " + r.stderr
    return r.stdout, r.stderr

OLD = {"GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}  # backdates the reflog entry
def norm(x): return sorted(re.sub(r".*reclaim-(?:x|disk)\.[^/]*/", "", i) for i in x)
def same(got, want):
    """Exact list check; the failure text names the leaked (listed but not wanted) and missing items, relative to the temp dir."""
    if got != want: raise AssertionError("LEAK " + repr((norm(got[0] - want[0]), norm(got[1] - want[1]), norm(want[0] - got[0]), norm(want[1] - got[1]))))
def extras(script):
    """Age rule needs no tip equality, old items are listed at the default 24h, invalid ages fall back, unfinished
    operations skip, a tag named main never becomes the base."""
    T = Path(tempfile.mkdtemp(prefix="reclaim-x.")); assert T.is_relative_to(tempfile.gettempdir()), T; T = T.resolve()
    try:
        R = T / "repo"; R.mkdir()
        g("init", "-q", "-b", "main", cwd=R); g("commit", "-q", "--allow-empty", "-m", "c1", cwd=R)
        g("commit", "-q", "--allow-empty", "-m", "c2", cwd=R); g("update-ref", "refs/remotes/origin/main", "HEAD", cwd=R)
        old = {**env, **OLD}
        add = lambda n, e=env: subprocess.run(["git", "worktree", "add", "-q", "-b", n, str(T / n), "main~1"], cwd=R, env=e, check=True)
        add("fresh1"); g("branch", "fresh-b1", "main~1", cwd=R)  # cut one commit behind the tip, no own commits, fresh
        add("old1", old); subprocess.run(["git", "branch", "old-b", "main~1"], cwd=R, env=old, check=True)
        add("mid", old); (Path(g("rev-parse", "--absolute-git-dir", cwd=T / "mid").strip()) / "MERGE_HEAD").write_text(g("rev-parse", "HEAD", cwd=T / "mid"))
        subprocess.run(["git", "branch", "nolog-b", "main~1"], cwd=R, env=old, check=True)
        (R / ".git/logs/refs/heads/nolog-b").unlink()  # reflog gone: unknown age, must not be listed
        for a in ("abc", "08", "0", "000", None):  # invalid and octal-looking ages must not crash; default 24h lists only the old items
            out, err = sh(script, R, age=a) if a else sh(script, R, age="24")
            got = ({l.split(" ", 2)[2] for l in out.splitlines() if l.startswith("would-remove worktree ")},
                   {l.split(" ", 2)[2] for l in out.splitlines() if l.startswith("would-remove branch ")})
            same(got, ({str(T / "old1")}, {"old1", "old-b"}))
            assert "newer than" in err and "unfinished MERGE_HEAD" in err, err
            assert "skip . refs/heads/nolog-b (reflog missing" in err, err
        for a in ("99999999999999999999", "9999999"):  # clamped to 87600h: nothing may overflow into eligibility
            out, err = sh(script, R, age=a)
            assert "would-remove" not in out and "newer than 87600h" in err, (a, out, err)
        R2 = T / "repo2"; R2.mkdir()  # tag 'main' at the old commit, no origin: base must be refs/heads/main
        g("init", "-q", "-b", "main", cwd=R2); g("commit", "-q", "--allow-empty", "-m", "c1", cwd=R2)
        g("tag", "main", cwd=R2); g("commit", "-q", "--allow-empty", "-m", "c2", cwd=R2); subprocess.run(["git", "branch", "b2", "refs/heads/main"], cwd=R2, env=old, check=True)
        out, err = sh(script, R2)
        assert "would-remove branch b2" in out, (out, err)
    finally:
        assert T.parent.resolve() == Path(tempfile.gettempdir()).resolve(), T  # resolved only here: macOS /var -> /private/var
        shutil.rmtree(T)

def scenario(script):
    """Build a fresh repo, run script dry then --apply from lane 'runner'; assert exact lists. Raises AssertionError."""
    global CUR; CUR = OLD
    T = Path(tempfile.mkdtemp(prefix="reclaim-disk.")); assert T.is_relative_to(tempfile.gettempdir()), T; T = T.resolve()
    try:
        R = T / "repo"; R.mkdir()
        g("init", "-q", "-b", "main", cwd=R); (R / ".gitignore").write_text(".env\n"); g("add", ".gitignore", cwd=R)
        g("commit", "-q", "-m", "base", cwd=R); g("update-ref", "refs/remotes/origin/main", "HEAD", cwd=R)
        for n in ("runner", "merged", "sp ace", "locked", "dirty", "ign", "unpushed"):
            g("worktree", "add", "-q", "-b", n.replace(" ", "-"), str(T / n), cwd=R)
        g("worktree", "add", "-q", "--detach", str(T / "detached"), cwd=R)
        g("worktree", "lock", str(T / "locked"), cwd=R)
        g("config", "status.showUntrackedFiles", "no", cwd=R)  # must not hide untracked files (dirty/f)
        for n, flag in (("hid-au", "--assume-unchanged"), ("hid-sw", "--skip-worktree")):  # modified but index says clean
            g("worktree", "add", "-q", "-b", n, str(T / n), cwd=R)
            (T / n / ".gitignore").write_text("changed\n"); g("update-index", flag, ".gitignore", cwd=T / n)
        g("worktree", "add", "-q", "-b", "tab-br", str(T / "ta\tb"), cwd=R)  # tab in path must not break parsing
        g("worktree", "add", "-q", "-b", "nl-br", str(T / "nl\nx"), cwd=R)  # newline in path: skipped, never mis-parsed
        for n in ("develop", "trunk", "release-1"): g("branch", n, cwd=R)  # at the main tip: protected by name
        g("tag", "tagged", cwd=R); g("branch", "tagged", cwd=R)  # tag shares the branch name: %(refname:short) would give heads/tagged
        (T / "dirty/f").write_text("x"); (T / "ign/.env").write_text("secret")
        g("commit", "-q", "--allow-empty", "-m", "wip", cwd=T / "unpushed")
        g("branch", "old-merged", cwd=R)
        g("branch", "unmerged", cwd=R); g("worktree", "add", "-q", str(T / "tmp-u"), "unmerged", cwd=R)
        g("commit", "-q", "--allow-empty", "-m", "u", cwd=T / "tmp-u"); g("worktree", "remove", str(T / "tmp-u"), cwd=R)
        run = T / "runner"
        want_wt = {str(T / "merged"), str(T / "sp ace"), str(T / "detached"), str(T / "ta\tb")}
        want_br = {"old-merged", "merged", "sp-ace", "tab-br", "tagged"}
        def lines(out, verb):
            return ({l.split(" ", 2)[2] for l in out.splitlines() if l.startswith(verb + " worktree ")},
                    {l.split(" ", 2)[2] for l in out.splitlines() if l.startswith(verb + " branch ")})
        before = g("worktree", "list", cwd=R) + g("branch", cwd=R)
        out, err = sh(script, run)
        same(lines(out, "would-remove"), (want_wt, want_br))
        assert g("worktree", "list", cwd=R) + g("branch", cwd=R) == before, "dry run must change nothing"
        assert f"worktrees={len(want_wt)} branches={len(want_br)}" in out, out
        for reason in ("(locked)", "modified, untracked or ignored files"): assert reason in err, err
        out2, _ = sh(script, run, "--apply")
        same(lines(out2, "removed"), (want_wt, want_br))
        for p in want_wt: assert not Path(p).exists(), p
        for n in ("runner", "locked", "dirty", "ign", "unpushed", "hid-au", "hid-sw", "nl\nx"): assert (T / n).exists(), f"survivor missing {n}"
        assert (T / "ign/.env").read_text() == "secret" and (T / "dirty/f").exists()
        left = set(g("branch", "--format=%(refname:short)", cwd=R).split())
        assert left == {"main", "runner", "locked", "dirty", "ign", "unpushed", "unmerged", "hid-au", "hid-sw", "nl-br", "develop", "trunk", "release-1"}, left
        # from the main checkout on a detached HEAD: main itself is never listed, the finished runner lane now is
        g("checkout", "-q", "--detach", cwd=R); out3, _ = sh(script, R)
        same(lines(out3, "would-remove"), ({str(T / "runner")}, {"runner"}))
        # fresh lane (HEAD == base tip, no commits) and fresh branch survive the default age; protected names always
        CUR = {}  # fresh from here on
        g("branch", "fresh-br", cwd=R)
        out4, err4 = sh(script, R, age="24")
        same(lines(out4, "would-remove"), ({str(T / "runner")}, {"runner"}))
        assert "skip fresh-br (newer than 24h)" in err4, err4
        extras(script)
    finally:
        assert T.parent.resolve() == Path(tempfile.gettempdir()).resolve(), T  # resolved only here: macOS /var -> /private/var
        shutil.rmtree(T)

scenario(S)
guards = sorted(set(re.findall(r"# guard:(\w+)", S.read_text())))
assert guards == ["checkedout", "dirty", "freshbr", "hidden", "inprogress", "locked", "main", "merged", "protected", "reach", "top", "young"], guards
# exact (leaked worktrees, leaked branches, missing worktrees, missing branches) each mutant must produce, relative to the temp dir
LEAK = {
    "checkedout": "LEAK ([], ['dirty', 'hid-au', 'hid-sw', 'ign', 'locked', 'nl-br', 'runner'], [], [])",
    "dirty": "LEAK (['dirty', 'ign'], ['dirty', 'ign'], [], [])",
    "freshbr": "LEAK ([], ['fresh-br'], [], [])",
    "hidden": "LEAK (['hid-au', 'hid-sw'], ['hid-au', 'hid-sw'], [], [])",
    "inprogress": "LEAK (['mid'], ['mid'], [], [])",
    "locked": "LEAK (['locked'], ['locked'], [], [])",
    "main": "LEAK (['repo'], [], [], [])",
    "merged": "LEAK ([], ['unmerged'], [], [])",
    "protected": "LEAK ([], ['develop', 'release-1', 'trunk'], [], [])",
    "reach": "LEAK (['unpushed'], [], [], [])",
    "top": "LEAK (['runner'], ['runner'], [], [])",
    "young": "LEAK (['fresh1'], [], [], [])",
}
killed = 0
for name in guards:
    M = Path(tempfile.mkdtemp(prefix="reclaim-mut.")) / "m.sh"
    M.write_text("".join(l for l in S.read_text().splitlines(True) if f"# guard:{name}" not in l))
    try:
        scenario(M)
    except AssertionError as e:  # a crashed script or any other failure propagates; the leak must be exactly this guard's items
        assert str(e) == LEAK[name], (name, str(e))
        killed += 1
    else:
        print(f"SURVIVED guard:{name}")
    shutil.rmtree(M.parent)
assert killed == len(guards), f"guards_killed={killed}/{len(guards)}"

# doctor row: thresholds via env, against the real volume's free GiB
def row(w, f):
    os.environ.update(PERUN_DISK_WARN_GB=str(w), PERUN_DISK_FAIL_GB=str(f)); os.environ["DCR_NO_PROBE"] = "1"
    return [r for r in perun_doctor.check(Path.cwd(), Path.cwd()) if r[1] == "disk free"][0]
assert row(0, 0)[0] == "OK"
assert row(1e9, 0)[0] == "WARN" and ".claude/skills/agentic-delivery/scripts/reclaim_disk.sh" in row(1e9, 0)[2]
assert row(1e9, 1e9)[0] == "FAIL"
for w, f in (("nan", 1), ("inf", 1), (5, "nan"), (-1, -2), (5, 10), (10, -1)):
    r = row(w, f); assert "defaults used" in r[2] and "warn < 50, fail < 10" in r[2], (w, f, r)
print(f"ok: reclaim_disk guards_killed={killed}/{len(guards)}, doctor disk row")
