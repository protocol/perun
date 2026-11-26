#!/usr/bin/env python3
"""perun_doctor newest_release() per-remote and legacy rows, the updater's non-string marker remote, and the _last_log resolved-key
branch. Offline: perun_auto_update.git is stubbed; every path lives under a temp dir."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perun_doctor

tmp = Path(tempfile.mkdtemp(prefix="dcr-doctor-remotes."))
try:
    repo, home = tmp / "repo", tmp / "home"
    os.environ["HOME"] = str(home)
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    for d in (repo, home):
        (d / ".claude").mkdir(parents=True)
    pa = perun_doctor.auto_update()

    def marker(root, v, remote):
        (root / ".claude/.perun-install.json").write_text(json.dumps({"version": v, "remote": remote}))

    def fake(tags_by_remote, calls):
        def git(*a, **k):
            calls.append(a[-1])
            return subprocess.CompletedProcess(a, 0, "".join(f"sha\trefs/tags/{t}\n" for t in tags_by_remote[a[-1]]), "")
        return git

    def run(tags_by_remote):
        calls, orig = [], pa.git
        pa.git = fake(tags_by_remote, calls)
        try:
            return perun_doctor.newest_release(repo, home), calls
        finally:
            pa.git = orig

    # 1. distinct remotes: one ls-remote each, every row compared with its OWN remote's tags
    marker(repo, "1.0.0", "https://example.com/a.git"); marker(home, "1.0.0", "https://example.com/b.git")
    rows, calls = run({"https://example.com/a.git": ["v1.0.0"], "https://example.com/b.git": ["v2.0.0"]})
    assert sorted(calls) == ["https://example.com/a.git", "https://example.com/b.git"], calls
    assert rows[0][0] == "OK" and rows[1][0] == "INFO" and "v2.0.0 is out" in rows[1][2], rows

    # 2. same remote: still ONE ls-remote
    marker(home, "1.0.0", "https://example.com/a.git")
    rows, calls = run({"https://example.com/a.git": ["v1.0.0"]})
    assert calls == ["https://example.com/a.git"] and len(rows) == 2, (calls, rows)

    # 3. legacy install (flags + SKILL.md, no marker) auto-updates, so it gets a row, not "update by hand"
    (home / ".claude/.perun-install.json").unlink(); (repo / ".claude/.perun-install.json").unlink()
    (repo / ".claude/.dcr-install-flags").write_text("--with-delivery\n")
    (repo / ".claude/skills/deep-code-review").mkdir(parents=True)
    (repo / ".claude/skills/deep-code-review/SKILL.md").write_text('---\nname: deep-code-review\nmetadata:\n  version: "1.0.0"\n---\n')
    rows, calls = run({pa.CANONICAL_REMOTE: ["v1.5.0"]})
    assert len(rows) == 1 and rows[0][1] == "newest release" and "v1.5.0 is out" in rows[0][2], rows
    assert "update by hand" not in rows[0][2], rows

    # 4. non-string marker remote: the updater logs a "no remote" skip and returns 0 (is_canonical never sees it)
    marker(repo, "1.0.0", 7)
    assert pa.run(repo) == 0
    last = perun_doctor._last_log(repo)
    assert last and "no remote or version" in last, last

    (repo / ".claude/.perun-install.json").write_text("[1]")  # valid JSON, not an object: a skip, never AttributeError
    assert pa.run(repo) == 0 and "no readable install marker" in perun_doctor._last_log(repo)

    # 5. _last_log resolved-key branch: the updater logged the real path, the caller holds a symlink to it
    real, link = tmp / "real", tmp / "link"
    real.mkdir(); link.symlink_to(real)
    pa.log(real.resolve(), "skip: resolved line")
    assert perun_doctor._last_log(link) == "skip: resolved line", perun_doctor._last_log(link)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok: newest release per-remote rows, legacy row, non-string remote, resolved log key")
