#!/usr/bin/env python3
"""Tests for perun_auto_update.py and its install.sh wiring. Offline: the "remote" is a local git repo
with release tags under $TMPDIR, and its update-installed.sh is a stub that records how it was called."""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(AD))
import perun_auto_update as au  # noqa: E402

STUB = """#!/usr/bin/env bash
# Fake update-installed.sh: record the call instead of installing.
printf '%s %s\\n' "${DCR_NO_PULL:-}" "$(cat "$(dirname "$0")/../TAGNAME")" >> "$1/.claude/ran"
"""


def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def commit_tag(r: Path, t: str, sums_ok=True, force=False):
    """Commit TAGNAME=t with a SHA256SUMS over the tree (corrupted when not sums_ok), then tag it."""
    (r / "TAGNAME").write_text(t)
    rows = [f"{hashlib.sha256((r / f).read_bytes()).hexdigest() if sums_ok else '0' * 64}  {f}"
            for f in ("TAGNAME", "scripts/update-installed.sh")]
    (r / "SHA256SUMS").write_text("\n".join(rows) + "\n")
    sh("git", "add", "-A", cwd=r)
    sh("git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", t, cwd=r)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "tag", "-a", "-m", t, *(["-f"] if force else []), t, cwd=r)


def fake_remote(base: Path, tags=("v1.2.0", "v1.9.0", "v1.10.0")) -> Path:
    r = base / "remote"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts/update-installed.sh").write_text(STUB)
    sh("git", "init", "-q", "-b", "main", str(r))
    for t in tags:
        commit_tag(r, t)
    sh("git", "tag", "not-a-release", cwd=r)
    return r


def fake_installed(base: Path, remote: Path, version="1.2.0") -> Path:
    t = base / "proj"
    skill = t / ".claude/skills/deep-code-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("name: deep-code-review\n")
    sh("git", "init", "-q", str(t))
    marker = {"version": version, "remote": str(remote),
              "skills": {".claude/skills/deep-code-review": {"SKILL.md": hashlib.sha256(b"name: deep-code-review\n").hexdigest()}}}
    (t / ".claude/.perun-install.json").write_text(json.dumps(marker))
    return t



class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["XDG_CACHE_HOME"] = str(self.tmp / "cache")
        os.environ.pop("PERUN_POLICY", None)
        self.delay = 0  # cooldown off unless a test sets it
        p = mock.patch.object(au, "delay_h", lambda t: self.delay)
        p.start()
        self.addCleanup(p.stop)
        self.remote = fake_remote(self.tmp)
        self.proj = fake_installed(self.tmp, self.remote)

    def log(self):
        f = au.cache() / "auto-update.log"
        return f.read_text() if f.is_file() else ""

    def test_newer_tag_applies_newest_semver_tag_via_update_installed(self):
        self.assertEqual(au.run(self.proj), 0)
        self.assertEqual((self.proj / ".claude/ran").read_text(), "1 v1.10.0\n")  # 1.10 > 1.9, DCR_NO_PULL=1
        self.assertIn("updated 1.2.0 -> v1.10.0", self.log())

    def test_marker_remote_starting_with_dash_is_skipped(self):
        sent = self.tmp / "pwned"
        mf = self.proj / ".claude/.perun-install.json"
        m = json.loads(mf.read_text()); m["remote"] = f"--upload-pack=touch {sent}"; mf.write_text(json.dumps(m))
        cwd = self.tmp / "cwdrepo"
        sh("git", "init", "-q", str(cwd)); sh("git", "remote", "add", "origin", str(self.remote), cwd=cwd)
        oc = os.getcwd(); os.chdir(cwd)
        try:
            self.assertEqual(au.run(self.proj), 0)
        finally:
            os.chdir(oc)
        self.assertFalse(sent.exists())
        self.assertIn("skip: install marker remote is not a repository", self.log())

    def test_up_to_date_does_nothing(self):
        proj = fake_installed(self.tmp / "b", self.remote, version="1.10.0")
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("up to date at 1.10.0", self.log())

    def test_merge_rebase_cherry_pick_and_train_locks_skip_and_log(self):
        for lock in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply", "train-land.lock",
                     "worktrees/lane1/train-land.lock"):
            proj = fake_installed(self.tmp / lock.replace("/", "_"), self.remote)
            (proj / ".git" / lock).mkdir(parents=True)
            self.assertEqual(au.run(proj), 0)
            self.assertFalse((proj / ".claude/ran").exists(), lock)
            self.assertIn(f"skip: {Path(lock).name} present", self.log())

    def test_uncommitted_settings_change_skips_but_untracked_files_do_not(self):
        s = self.proj / ".claude/settings.local.json"
        s.write_text("{}\n")
        sh("git", "add", "-f", ".claude/settings.local.json", cwd=self.proj)
        sh("git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "s", cwd=self.proj)
        s.write_text('{"model": "opus"}\n')
        self.assertEqual(au.run(self.proj), 0)
        self.assertFalse((self.proj / ".claude/ran").exists())
        self.assertIn("skip: uncommitted changes: .claude/settings.local.json", self.log())

    def test_moved_tag_restarts_cooldown_instead_of_stalling(self):
        self.assertEqual(au.run(self.proj, now=1000.0), 0)  # delay 0: applied, cached tag now old
        (self.proj / ".claude/ran").unlink()
        commit_tag(self.remote, "v1.10.0", force=True)  # the remote re-points an existing tag
        self.delay = 72
        self.assertEqual(au.run(self.proj, now=2000.0), 0)  # forced fetch works; moved sha resets the clock
        self.assertFalse((self.proj / ".claude/ran").exists())
        self.assertIn("waiting cooldown", self.log())

    def test_tag_not_on_main_is_refused(self):
        sh("git", "checkout", "-q", "-b", "side", cwd=self.remote)
        commit_tag(self.remote, "v9.0.0")
        sh("git", "checkout", "-q", "main", cwd=self.remote)
        self.assertEqual(au.run(self.proj), 1)
        self.assertFalse((self.proj / ".claude/ran").exists())
        self.assertIn("aborted, v9.0.0 is not an ancestor of main", self.log())

    def test_bad_sha256sums_is_refused(self):
        commit_tag(self.remote, "v9.0.0", sums_ok=False)
        self.assertEqual(au.run(self.proj), 1)
        self.assertFalse((self.proj / ".claude/ran").exists())
        self.assertIn("aborted, SHA256SUMS mismatch: TAGNAME", self.log())

    def test_dirty_managed_file_skips_and_logs(self):
        (self.proj / ".claude/skills/deep-code-review/SKILL.md").write_text("edited by the user\n")
        self.assertEqual(au.run(self.proj), 0)
        self.assertFalse((self.proj / ".claude/ran").exists())
        self.assertIn("skip: dirty Perun-managed file .claude/skills/deep-code-review/SKILL.md", self.log())

    def test_marker_without_remote_is_a_logged_skip(self):
        (self.proj / ".claude/.perun-install.json").write_text('{"version": "1.2.0"}')
        self.assertEqual(au.run(self.proj), 0)
        self.assertIn("no remote or version", self.log())

    @mock.patch.object(au.subprocess, "Popen")
    def test_throttle_runs_at_most_once_per_6h(self, popen):
        self.assertTrue(au.hook(self.proj))
        self.assertFalse(au.hook(self.proj))
        self.assertFalse(au.hook(self.proj, now=time.time() + 5 * 3600))
        self.assertTrue(au.hook(self.proj, now=time.time() + 7 * 3600))
        self.assertEqual(popen.call_count, 2)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])  # detached from the session

    @mock.patch.object(au.subprocess, "Popen")
    def test_policy_off_never_spawns(self, popen):
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun/policy.json").write_text('{"auto_update": "off"}')
        self.assertFalse(au.hook(self.proj))
        self.assertFalse(au.stamp(self.proj).exists())
        popen.assert_not_called()

    def test_malformed_policy_fails_closed(self):
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun/policy.json").write_text('{"auto_update": "sometimes"}')
        self.assertFalse(au.hook(self.proj))

    def test_hook_returns_fast_and_the_detached_worker_still_updates(self):
        slow = self.tmp / "bin"
        slow.mkdir()
        real = shutil.which("git")
        (slow / "git").write_text(f"#!/bin/sh\nsleep 2\nexec {real} \"$@\"\n")
        (slow / "git").chmod(0o755)
        pol = self.tmp / "nodelay.json"
        pol.write_text('{"auto_update_delay_h": 0}')  # the detached worker is a subprocess: the delay_h patch does not reach it
        env = {**os.environ, "PATH": f"{slow}:{os.environ['PATH']}", "CLAUDE_PROJECT_DIR": str(self.proj), "PERUN_POLICY": str(pol)}
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, str(AD / "perun_auto_update.py")], env=env, capture_output=True, text=True)
        elapsed = time.monotonic() - t0
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertLess(elapsed, 0.3, f"hook took {elapsed:.3f}s")
        deadline = time.monotonic() + 60  # the worker waits on the slow git several times
        while time.monotonic() < deadline and "updated" not in self.log():
            time.sleep(0.2)
        self.assertIn("updated 1.2.0 -> v1.10.0", self.log())


class CooldownAndSignerTests(unittest.TestCase):
    """Supply-chain mitigation: per-tag cooldown, installed-copy release-signers, non-empty SHA256SUMS."""
    H = 3600

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["XDG_CACHE_HOME"] = str(self.tmp / "cache")
        os.environ.pop("PERUN_POLICY", None)
        self.remote = fake_remote(self.tmp, tags=("v1.2.0",))
        self.proj = fake_installed(self.tmp, self.remote)
        self.now = 1_000_000_000.0
        d = mock.patch.object(au, "delay_h", lambda t: 72)
        d.start()
        self.addCleanup(d.stop)

    def log(self):
        f = au.cache() / "auto-update.log"
        return f.read_text() if f.is_file() else ""

    def seed(self, ages_h: dict):
        """Pretend each tag was first seen `age` hours before self.now, with the remote's current sha."""
        sha = {t: subprocess.run(["git", "rev-parse", t], cwd=self.remote, capture_output=True, text=True).stdout.strip() for t in ages_h}
        au.cache().mkdir(parents=True, exist_ok=True)
        (au.cache() / "seen.json").write_text(json.dumps({t: {"sha": sha[t], "first_seen": self.now - a * self.H} for t, a in ages_h.items()}))

    def ran(self):
        f = self.proj / ".claude/ran"
        return f.read_text() if f.exists() else ""

    def test_picks_newest_tag_past_the_cooldown(self):
        for t in ("v1.3.0", "v1.4.0", "v1.5.0"):
            commit_tag(self.remote, t)
        self.seed({"v1.3.0": 100, "v1.4.0": 10, "v1.5.0": 1})
        self.assertEqual(au.run(self.proj, now=self.now), 0)
        self.assertEqual(self.ran(), "1 v1.3.0\n")

    def test_nothing_eligible_waits_and_exits_zero(self):
        commit_tag(self.remote, "v1.3.0")
        self.assertEqual(au.run(self.proj, now=self.now), 0)  # first sight starts the clock
        self.assertEqual(self.ran(), "")
        self.assertIn("skip: newest eligible release after 1.2.0 is waiting cooldown", self.log())
        self.assertEqual(au.run(self.proj, now=self.now + 73 * self.H), 0)
        self.assertEqual(self.ran(), "1 v1.3.0\n")

    def test_moved_sha_resets_the_clock(self):
        commit_tag(self.remote, "v1.3.0")
        self.seed({"v1.3.0": 100})
        commit_tag(self.remote, "v1.3.0-x")  # new commit, then move the tag onto it
        sh("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "tag", "-a", "-m", "m", "-f", "v1.3.0", cwd=self.remote)
        self.assertEqual(au.run(self.proj, now=self.now), 0)
        self.assertEqual(self.ran(), "")
        self.assertEqual(json.loads((au.cache() / "seen.json").read_text())["v1.3.0"]["first_seen"], self.now)

    def test_old_tag_object_pushed_under_higher_name_is_refused(self):
        commit_tag(self.remote, "v1.3.0")
        sha = subprocess.run(["git", "rev-parse", "v1.3.0"], cwd=self.remote, capture_output=True, text=True).stdout.strip()
        sh("git", "update-ref", "refs/tags/v1.9.0", sha, cwd=self.remote)  # same tag object, new name
        sh("git", "tag", "-d", "v1.3.0", cwd=self.remote)
        with mock.patch.object(au, "delay_h", lambda t: 0):
            self.assertEqual(au.run(self.proj, now=self.now), 1)
        self.assertEqual(self.ran(), "")
        self.assertIn("not an annotated tag named v1.9.0", self.log())

    def test_delay_zero_is_the_old_behaviour(self):
        commit_tag(self.remote, "v1.3.0")
        with mock.patch.object(au, "delay_h", lambda t: 0):
            self.assertEqual(au.run(self.proj, now=self.now), 0)
        self.assertEqual(self.ran(), "1 v1.3.0\n")

    def test_policy_key_default_and_validation(self):
        import perun_policy
        self.assertEqual(perun_policy.validate({})["auto_update_delay_h"], 72)
        self.assertEqual(perun_policy.validate({"auto_update_delay_h": 0})["auto_update_delay_h"], 0)
        for bad in (-1, "72", True, 1.5):
            with self.assertRaises(ValueError):
                perun_policy.validate({"auto_update_delay_h": bad})

    def test_empty_or_comment_only_sums_fail(self):
        for body in ("", "\n", "# nothing\n\n"):
            (self.tmp / "SHA256SUMS").write_text(body)
            self.assertEqual(au.verify_sums(self.tmp), "empty SHA256SUMS")

    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen needed")
    def test_release_signers_verify_tag(self):
        keys = {}
        for n in ("good", "other"):
            k = self.tmp / n
            sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", n, "-f", str(k))
            keys[n] = k
        signers = self.tmp / "release-signers"
        signers.write_text("releaser@example.com " + (self.tmp / "good.pub").read_text())

        def tag(t, key=None):
            commit_tag(self.remote, t)
            if key:
                sh("git", "-c", "gpg.format=ssh", "-c", f"user.signingkey={keys[key]}.pub", "-c", "user.name=t", "-c", "user.email=t@example.com",
                   "tag", "-f", "-s", "-m", t, t, cwd=self.remote)

        def attempt(t):
            os.environ["XDG_CACHE_HOME"] = str(self.tmp / ("cache-" + t))
            (self.proj / ".claude/ran").unlink(missing_ok=True)
            with mock.patch.object(au, "delay_h", lambda _t: 0), mock.patch.object(au, "SIGNERS", signers):
                return au.run(self.proj, now=self.now), self.ran(), au.cache()
        tag("v1.3.0", "good")
        rc, ran, c = attempt("v1.3.0")
        self.assertEqual((rc, ran), (0, "1 v1.3.0\n"))
        tag("v1.4.0")  # unsigned (lightweight)
        rc, ran, c = attempt("v1.4.0")
        self.assertEqual((rc, ran), (1, ""))
        self.assertIn("signature not verified", (c / "auto-update.log").read_text())
        tag("v1.5.0", "other")  # signed, but not by an allowed signer
        rc, ran, c = attempt("v1.5.0")
        self.assertEqual((rc, ran), (1, ""))
        with mock.patch.object(au, "delay_h", lambda _t: 0), mock.patch.object(au, "SIGNERS", self.tmp / "absent"):
            self.assertEqual(au.run(self.proj, now=self.now), 0)
        self.assertIn("unsigned release: cooldown only", self.log())


@unittest.skipUnless(shutil.which("jq"), "jq needed to apply the operating layer")
class InstallWiringTests(unittest.TestCase):
    def install(self, repo, *flags):
        env = {**os.environ, "PERUN_REMOTE": "https://example.com/perun.git"}
        return subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(repo)], capture_output=True, text=True, env=env)

    def test_operating_layer_wires_hooks_and_marker_records_version_and_remote(self):
        repo = Path(tempfile.mkdtemp())
        p = self.install(repo, "--with-delivery")
        self.assertEqual(p.returncode, 0, p.stderr)
        hooks = json.loads((repo / ".claude/settings.local.json").read_text())["hooks"]
        for ev in ("SessionStart", "UserPromptSubmit"):
            self.assertIn("perun_auto_update.py", json.dumps(hooks[ev]))
        m = json.loads((repo / ".claude/.perun-install.json").read_text())
        self.assertEqual(m["remote"], "https://example.com/perun.git")
        self.assertEqual(m["version"], (ROOT / ".claude/skills/deep-code-review/VERSION").read_text().strip())
        self.assertNotIn("restart your", p.stdout.lower())
        self.assertIn("without a restart", p.stdout)
        self.assertIn("runs release code from the Perun remote in the background", p.stdout)
        self.assertIn("--no-auto-update", p.stdout)
        self.assertIn('"auto_update": "off"', p.stdout)
        pol = repo / ".perun/policy.json"  # the default install only arms the CEO guard (role); auto_update stays unset
        self.assertNotIn("auto_update", json.loads(pol.read_text()) if pol.exists() else {})

    def test_no_auto_update_turns_policy_off_and_keeps_other_keys(self):
        repo = Path(tempfile.mkdtemp())
        (repo / ".perun").mkdir()
        (repo / ".perun/policy.json").write_text('{"tokens": 5}')
        p = self.install(repo, "--no-auto-update")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((repo / ".perun/policy.json").read_text()), {"tokens": 5, "auto_update": "off"})
        self.assertIn("--no-auto-update", (repo / ".claude/.dcr-install-flags").read_text())

    def test_machine_local_flags_go_to_untracked_local_file_and_migrate(self):
        repo = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        p = self.install(repo, "--with-delivery", "--apply-operating-layer", "--no-sandbox")
        self.assertEqual(p.returncode, 0, p.stderr)
        tracked, local = (repo / ".claude/.dcr-install-flags").read_text(), (repo / ".claude/.dcr-install-flags.local").read_text()
        self.assertEqual((tracked.split(), local.split()), (["--with-delivery"], ["--apply-operating-layer", "--no-sandbox"]))
        self.assertIn(".dcr-install-flags.local", (repo / ".git/info/exclude").read_text())
        self.assertNotIn("dcr-install-flags", (repo / ".claude/.perun-install.json").read_text())  # not a managed file
        # tracked-file carrying a local-only flag (old record): ignored + warned, never applied; opt-outs still honored
        (repo / ".claude/.dcr-install-flags").write_text("--apply-operating-layer\n--no-auto-update\n")
        (repo / ".claude/.dcr-install-flags.local").unlink()
        (repo / ".claude/settings.local.json").unlink()
        u = self.update(repo)
        self.assertEqual(u.returncode, 0, u.stderr)
        self.assertIn("ignoring --apply-operating-layer", u.stderr)
        self.assertFalse((repo / ".claude/settings.local.json").exists())  # layer not applied
        self.assertEqual((repo / ".claude/.dcr-install-flags").read_text().split(), ["--no-auto-update"])
        self.assertFalse((repo / ".claude/.dcr-install-flags.local").exists())
        self.assertEqual(json.loads((repo / ".perun/policy.json").read_text())["auto_update"], "off")

    def update(self, repo):
        return subprocess.run(["bash", str(ROOT / "scripts/update-installed.sh"), str(repo)], capture_output=True, text=True,
                              env={**os.environ, "DCR_NO_PULL": "1", "PERUN_REMOTE": "https://example.com/perun.git"})

    def test_local_file_honored_and_survives_pre_marker_path(self):
        repo = Path(tempfile.mkdtemp())
        self.assertEqual(self.install(repo, "--with-delivery", "--apply-operating-layer").returncode, 0)
        (repo / ".claude/.dcr-install-flags").unlink()  # pre-marker state
        (repo / ".claude/.dcr-install-flags.local").write_text("--apply-operating-layer\n--no-sandbox\n")
        u = self.update(repo)
        self.assertEqual(u.returncode, 0, u.stderr)
        self.assertEqual((repo / ".claude/.dcr-install-flags.local").read_text().split(), ["--apply-operating-layer", "--no-sandbox"])

    def test_exclude_line_is_anchored_for_a_subdirectory_target(self):
        top = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(top)], check=True)
        sub = top / "pkg/app"
        sub.mkdir(parents=True)
        self.assertEqual(self.install(sub, "--with-delivery", "--apply-operating-layer").returncode, 0)
        self.assertIn("/pkg/app/.claude/.dcr-install-flags.local\n", (top / ".git/info/exclude").read_text())
        ign = subprocess.run(["git", "-C", str(top), "check-ignore", "-q", "pkg/app/.claude/.dcr-install-flags.local"])
        self.assertEqual(ign.returncode, 0)


if __name__ == "__main__":
    unittest.main()
