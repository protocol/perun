#!/usr/bin/env python3
"""perun_doctor "newest release" rows: each install with a .claude/.perun-install.json marker is compared with the newest vX.Y.Z tag
from ONE `git ls-remote --tags --refs` (timeout <= 10 s). Rows show the updater's last log line and the command that takes the
release now; offline, timeout, no marker and a bad marker are INFO (never WARN/FAIL). Hermetic and offline: the remote is a local
bare repo under a temp dir, and the canonical-remote and timeout cases stub perun_auto_update.git."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perun_doctor

os.environ["DCR_NO_PROBE"] = "1"  # check() skips this row under it; newest_release() is called directly
tmp = Path(tempfile.mkdtemp(prefix="dcr-doctor-newest."))
try:
    repo, home, bare, work = tmp / "repo", tmp / "home", tmp / "remote.git", tmp / "work"
    os.environ["HOME"] = str(home)
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    g = lambda *a, cwd=work: subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *a], cwd=cwd, check=True, capture_output=True)
    work.mkdir()
    g("init", "-q", "-b", "main"); g("commit", "-q", "--allow-empty", "-m", "x")
    for t in ("v1.0.0", "v1.2.0", "v1.10.0", "not-a-release"):
        g("tag", t)
    g("init", "-q", "--bare", str(bare), cwd=tmp); g("push", "-q", str(bare), "--tags")
    pa = perun_doctor.auto_update()

    def marker(root, v, remote):
        (root / ".claude").mkdir(parents=True, exist_ok=True)
        (root / ".claude/.perun-install.json").write_text(json.dumps({"version": v, "remote": remote}))

    def reset():
        for r in (repo, home, tmp / "cache"):
            shutil.rmtree(r, ignore_errors=True)
        repo.mkdir(); home.mkdir()

    reset()  # behind: numeric newest (1.10.0 beats 1.2.0), INFO with the take-it-now command for this target
    marker(repo, "1.0.0", str(bare))
    (rows,) = perun_doctor.newest_release(repo, home)
    st, name, d = rows
    assert (st, name) == ("INFO", "newest release") and "v1.10.0 is out, installed 1.0.0" in d, rows
    assert "no line for this target" in d and "update-installed.sh" in d and d.rstrip().endswith(str(repo)), d
    assert "cooldown" in d and "auto_update_delay_h" in d, d

    pa.log(repo.resolve(), "skip: newest eligible release after 1.0.0 is waiting cooldown (72h)")  # the updater's own log writer
    pa.log(home.resolve(), "up to date at 1.0.0")  # another target's line never leaks in
    d = perun_doctor.newest_release(repo, home)[0][2]
    assert "updater log: skip: newest eligible release after 1.0.0 is waiting cooldown (72h)" in d, d

    reset()  # up to date: OK
    marker(repo, "1.10.0", str(bare))
    assert perun_doctor.newest_release(repo, home)[0][:2] == ("OK", "newest release")
    marker(repo, "v1.10.0", str(bare))  # a v-prefixed marker version parses too
    assert perun_doctor.newest_release(repo, home)[0][0] == "OK"

    reset()  # repo and home installs: two rows, ONE ls-remote, never WARN/FAIL
    marker(repo, "1.10.0", str(bare)); marker(home, "1.0.0", str(bare))
    calls, orig = [], pa.git
    pa.git = lambda *a, **k: (calls.append((a, k)), orig(*a, **k))[1]
    rows = perun_doctor.newest_release(repo, home)
    pa.git = orig
    assert [r[:2] for r in rows] == [("OK", "newest release"), ("INFO", "newest release (global)")], rows
    assert len(calls) == 1 and calls[0][1]["timeout"] <= 10 and calls[0][0][:3] == ("ls-remote", "--tags", "--refs"), calls
    assert str(home) in rows[1][2], rows

    reset()  # (a) a repo-controlled marker remote must not smuggle an option: --upload-pack=<cmd> would run in a local origin
    sent = tmp / "pwned"
    cwdrepo = tmp / "cwdrepo"
    g("init", "-q", "-b", "main", str(cwdrepo), cwd=tmp); g("remote", "add", "origin", str(bare), cwd=cwdrepo)
    marker(repo, "1.0.0", f"--upload-pack=touch {sent}")
    oc = os.getcwd(); os.chdir(cwdrepo)
    try:
        perun_doctor.newest_release(repo, home)
    finally:
        os.chdir(oc)
    assert not sent.exists(), "marker remote ran as an option (--upload-pack)"

    reset()  # (b) the updater logs the unresolved target; a symlinked target must still find its line
    real = tmp / "realrepo"; link = tmp / "linkrepo"
    real.mkdir(); link.symlink_to(real)
    pa.log(link, "skip: symlink line")
    assert perun_doctor._last_log(link) == "skip: symlink line", perun_doctor._last_log(link)

    reset()  # repo == home: one row
    marker(home, "1.0.0", str(bare))
    assert len(perun_doctor.newest_release(home, home)) == 1

    reset()  # offline: unreachable remote -> INFO unknown, no raise
    marker(repo, "1.0.0", str(tmp / "does-not-exist.git"))
    (st, name, d), = perun_doctor.newest_release(repo, home)
    assert st == "INFO" and "newest release: unknown (offline)" in d, (st, d)

    def stub(fn):
        orig = pa.git
        pa.git = fn
        try:
            return perun_doctor.newest_release(repo, home)
        finally:
            pa.git = orig

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("git", k.get("timeout", 0))
    (st, _, d), = stub(slow)  # timeout -> INFO offline, never an exception
    assert st == "INFO" and "unknown (offline)" in d, (st, d)
    (st, _, d), = stub(lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    assert st == "INFO" and "unknown (offline)" in d, (st, d)

    seen = []  # the canonical (or legacy) remote is normalised exactly as the updater does; a foreign one is used as written
    marker(repo, "1.0.0", pa.LEGACY_REMOTE)
    stub(lambda *a, **k: (seen.append(a[-1]), subprocess.CompletedProcess(a, 1, "", ""))[1])
    marker(repo, "1.0.0", "https://example.com/acme/other.git")
    stub(lambda *a, **k: (seen.append(a[-1]), subprocess.CompletedProcess(a, 1, "", ""))[1])
    assert seen == [pa.CANONICAL_REMOTE, "https://example.com/acme/other.git"], seen

    for bad in ("not json", json.dumps({"version": "1.0.0"}), json.dumps({"version": 7, "remote": str(bare)}), json.dumps([])):
        reset()
        (repo / ".claude").mkdir()
        (repo / ".claude/.perun-install.json").write_text(bad)
        (st, _, d), = perun_doctor.newest_release(repo, home)
        assert st == "INFO" and d.startswith("n/a (install marker"), (bad, st, d)

    reset()  # no marker anywhere: INFO n/a pointing at the manual path
    (st, name, d), = perun_doctor.newest_release(repo, home)
    assert (st, name) == ("INFO", "newest release") and "no .claude/.perun-install.json" in d, d

    marker(repo, "1.0.0", str(bare))  # check() under DCR_NO_PROBE: row present, no network
    rows = {r[1]: r for r in perun_doctor.check(repo, home)}
    assert rows["newest release"][0] == "INFO" and "not checked" in rows["newest release"][2], rows["newest release"]
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok: newest release row: behind/current/offline/timeout/no-marker/bad-marker, one ls-remote, canonical remote, log line, take-it-now command")
