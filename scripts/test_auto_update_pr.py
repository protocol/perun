#!/usr/bin/env python3
"""Tests for the auto_update_pr step of perun_auto_update.py and the committed-version WARN in
session_brief.py / operating_selfcheck.py. Offline: origin is a bare repo under $TMPDIR; gh is a stub script on PATH."""
import json, os, subprocess, sys, tempfile, unittest, unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(AD))
import perun_auto_update as au  # noqa: E402
import session_brief  # noqa: E402

GH = """#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
case "$1 $2" in
  "pr list") echo "${GH_PR_LIST:-[]}" ;;
  "pr create") exit "${GH_CREATE_RC:-0}" ;;
  "api -X") exit 0 ;;
esac
"""
SKILL = ".claude/skills/deep-code-review"
CMD = ".claude/commands/review.md"


def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit(r, msg):
    sh("git", "add", "-A", cwd=r)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", msg, cwd=r)


class AutoUpdatePrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = dict(os.environ)
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "gh").write_text(GH)
        (bin_ / "gh").chmod(0o755)
        self.log = self.tmp / "gh.log"
        os.environ.update(PATH=f"{bin_}:{os.environ['PATH']}", GH_LOG=str(self.log), XDG_CACHE_HOME=str(self.tmp / "cache"))
        for k in ("PERUN_POLICY", "GH_PR_LIST", "GH_CREATE_RC"):
            os.environ.pop(k, None)
        self.origin = self.tmp / "origin.git"
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.proj = self.tmp / "proj"
        sh("git", "init", "-q", "-b", "main", str(self.proj))
        sh("git", "remote", "add", "origin", str(self.origin), cwd=self.proj)
        self.put("1.0.0", "old\n")
        commit(self.proj, "seed")
        sh("git", "push", "-q", "origin", "main", cwd=self.proj)
        sh("git", "fetch", "-q", "origin", cwd=self.proj)
        (self.proj / ".claude/.perun-install.json").write_text(json.dumps(
            {"version": "1.1.0", "skills": {SKILL: {"VERSION": "", "SKILL.md": ""}}, "files": {CMD: ""}}))
        self.put("1.1.0", "new\n")  # the in-place update: uncommitted in the user's checkout
        (self.proj / "mine.txt").write_text("user work\n")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)

    def put(self, ver, body):
        for rel, text in ((f"{SKILL}/VERSION", ver + "\n"), (f"{SKILL}/SKILL.md", body), (CMD, body)):
            (self.proj / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.proj / rel).write_text(text)

    def calls(self):
        return self.log.read_text() if self.log.is_file() else ""

    def branches(self):
        return sh("git", "branch", "--list", "perun/*", cwd=self.origin)

    def test_opens_pr_without_touching_checkout(self):
        self.assertEqual(au.update_pr(self.proj), "pr opened: perun/update-v1.1.0 -> main")
        self.assertIn("perun/update-v1.1.0", self.branches())
        self.assertEqual(sh("git", "log", "-1", "--format=%s", "perun/update-v1.1.0", cwd=self.origin).strip(),
                         "Update Perun skills to v1.1.0")
        self.assertEqual(sh("git", "show", f"perun/update-v1.1.0:{SKILL}/SKILL.md", cwd=self.origin), "new\n")
        self.assertEqual(sh("git", "show", f"perun/update-v1.1.0:{CMD}", cwd=self.origin), "new\n")
        self.assertNotIn("mine.txt", sh("git", "ls-tree", "-r", "--name-only", "perun/update-v1.1.0", cwd=self.origin))
        self.assertIn("pr create --head perun/update-v1.1.0 --base main", self.calls())
        self.assertEqual((self.proj / "mine.txt").read_text(), "user work\n")  # checkout + uncommitted work untouched
        self.assertEqual(sh("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=self.proj).strip(), "main")
        self.assertEqual(sh("git", "worktree", "list", cwd=self.proj).count("\n"), 1)  # throwaway worktree removed

    def test_idempotent_on_open_pr_and_retries_failed_create(self):
        au.update_pr(self.proj)
        self.log.unlink()
        os.environ["GH_PR_LIST"] = '[{"number": 3}]'
        self.assertIn("open PR for perun/update-v1.1.0 exists", au.update_pr(self.proj))
        self.assertNotIn("pr create", self.calls())
        os.environ["GH_PR_LIST"] = "[]"  # branch pushed, no open PR (earlier create failed): PR only, no second branch
        self.assertEqual(au.update_pr(self.proj), "pr opened: perun/update-v1.1.0 -> main (branch already pushed)")

    def test_only_recorded_files_untracked_and_symlinks_excluded(self):
        (self.proj / SKILL / "stray.md").write_text("untracked user file\n")
        (self.proj / SKILL / "link.md").symlink_to(self.proj / "mine.txt")
        m = json.loads((self.proj / ".claude/.perun-install.json").read_text())
        m["skills"][SKILL]["link.md"] = ""
        m["files"]["../escape.md"] = ""
        m["files"]["/etc/hosts"] = ""
        (self.proj / ".claude/.perun-install.json").write_text(json.dumps(m))
        self.assertEqual(au.managed_files(self.proj, m), [f"{SKILL}/VERSION", f"{SKILL}/SKILL.md", CMD])
        au.update_pr(self.proj)
        tree = sh("git", "ls-tree", "-r", "--name-only", "perun/update-v1.1.0", cwd=self.origin)
        for bad in ("stray.md", "link.md", "mine.txt", "escape", "hosts"):
            self.assertNotIn(bad, tree)

    def test_gh_missing_goes_to_rest_path_without_raising(self):
        real = subprocess.run

        def run(cmd, *a, **k):
            if cmd[0] == "gh":
                raise FileNotFoundError("gh")
            return real(cmd, *a, **k)
        with unittest.mock.patch("subprocess.run", run):
            self.assertIsNone(au.pr_open("b", self.proj))
            self.assertTrue(au.pr_create("b", "main", "1.1.0", self.proj).strip())  # no token: a failure line, not a raise

    def test_hook_timeout_aborts_cleans_up_and_logs(self):
        real = au.git

        def git(*a, **k):
            if "commit" in a:
                raise subprocess.TimeoutExpired("git", 1)
            return real(*a, **k)
        with unittest.mock.patch.object(au, "git", git):
            self.assertEqual(au.update_pr(self.proj), "pr failed: hooks timed out")
        self.assertEqual(self.branches(), "")
        self.assertEqual(sh("git", "worktree", "list", cwd=self.proj).count("\n"), 1)

    def test_log_redacts_url_credentials(self):
        au.log(self.proj, "failed: push https://user:tok3n@example.com/r.git denied")
        txt = (au.cache() / "auto-update.log").read_text()
        self.assertIn("https://***@example.com/r.git", txt)
        self.assertNotIn("tok3n", txt)

    def test_existing_pr_or_current_version_skips(self):
        os.environ["GH_PR_LIST"] = '[{"number": 7}]'
        self.assertIn("open PR for perun/update-v1.1.0 exists", au.update_pr(self.proj))
        self.assertEqual(self.branches(), "")
        os.environ.pop("GH_PR_LIST")
        self.put("1.0.0", "old\n")  # working tree equals what is committed
        self.assertIn("is not behind", au.update_pr(self.proj))

    def test_gh_create_failure_falls_back_to_rest_path(self):
        os.environ["GH_CREATE_RC"] = "1"
        self.assertEqual(au.update_pr(self.proj), "pr opened: perun/update-v1.1.0 -> main")
        self.assertIn("api -X POST repos/{owner}/{repo}/pulls --input", self.calls())

    def test_policy_off_does_nothing(self):
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun/policy.json").write_text('{"auto_update_pr": "off"}')
        au.pr_step(self.proj)
        self.assertEqual(self.branches(), "")
        self.assertFalse((au.cache() / "auto-update.log").exists())

    def test_policy_base_targets_named_branch_and_warn_uses_it(self):
        sh("git", "push", "-q", "origin", "main:refs/heads/integ", cwd=self.proj)  # integ stays at 1.0.0
        c = self.tmp / "adv"
        sh("git", "clone", "-q", str(self.origin), str(c))
        (c / SKILL).mkdir(parents=True, exist_ok=True)
        (c / SKILL / "VERSION").write_text("1.1.0\n")
        commit(c, "main is current")
        sh("git", "push", "-q", "origin", "main", cwd=c)  # origin/HEAD target (main) is not behind; integ is
        self.assertTrue(au.update_pr(self.proj).startswith("pr skip: committed version on origin/main"))
        (self.proj / ".perun").mkdir()
        pol = self.proj / ".perun/policy.json"
        pol.write_text('{"auto_update_pr_base": "integ"}')
        self.assertIn("committed Perun v1.0.0 < installed v1.1.0", au.behind_warn(self.proj))
        self.assertEqual(au.update_pr(self.proj), "pr opened: perun/update-v1.1.0 -> integ")
        self.assertIn("--base integ", self.calls())

    def test_policy_base_missing_on_origin_skips_never_guesses(self):
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun/policy.json").write_text('{"auto_update_pr_base": "nope"}')
        self.assertEqual(au.update_pr(self.proj), "pr skip: auto_update_pr_base 'nope' not found on origin")
        self.assertEqual(self.branches(), "")
        self.assertIsNone(au.behind_warn(self.proj))
        (self.proj / ".perun/policy.json").write_text('{"auto_update_pr_base": ""}')  # empty = origin/HEAD as before
        self.assertEqual(au.update_pr(self.proj), "pr opened: perun/update-v1.1.0 -> main")

    def test_policy_base_validation(self):
        import perun_policy
        self.assertEqual(perun_policy.validate({})["auto_update_pr_base"], "")
        self.assertEqual(perun_policy.validate({"auto_update_pr_base": "release/1.x"})["auto_update_pr_base"], "release/1.x")
        for bad in ("-x", "a..b", "a b", 1, None, "HEAD", "a//b", "a/"):
            with self.assertRaises(ValueError):
                perun_policy.validate({"auto_update_pr_base": bad})

    def test_pr_step_logs_and_never_raises(self):
        sh("git", "remote", "remove", "origin", cwd=self.proj)
        au.pr_step(self.proj)
        self.assertIn("pr skip: fetch origin failed", (au.cache() / "auto-update.log").read_text())

    def test_warn_when_committed_behind(self):
        w = au.behind_warn(self.proj)
        self.assertEqual(w, "WARN: committed Perun v1.0.0 < installed v1.1.0: lanes in other worktrees run old skills; "
                            "open/merge the perun/update PR")
        self.assertEqual(session_brief.committed_line(self.proj), w)
        out = subprocess.run([sys.executable, str(AD / "operating_selfcheck.py"), "--project", str(self.proj),
                              "--settings", str(self.proj / "none.json")], capture_output=True, text=True).stdout
        self.assertIn(w, out)

    def test_no_warn_when_current_or_no_remote(self):
        self.put("1.0.0", "old\n")
        self.assertIsNone(au.behind_warn(self.proj))
        self.put("1.1.0", "new\n")
        sh("git", "remote", "remove", "origin", cwd=self.proj)
        sh("git", "update-ref", "-d", "refs/remotes/origin/main", cwd=self.proj)
        self.assertIsNone(au.behind_warn(self.proj))

    def test_no_warn_without_install_marker(self):
        # Perun's own source repo is ahead of its default branch on every release branch: not an install, no WARN
        self.assertIsNotNone(au.behind_warn(self.proj))
        (self.proj / ".claude/.perun-install.json").unlink()
        self.assertIsNone(au.behind_warn(self.proj))


if __name__ == "__main__":
    unittest.main()
