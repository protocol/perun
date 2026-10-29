#!/usr/bin/env python3
"""Affected-run receipts: `run-ci-tests.sh --affected` records a kind=affected receipt (lkg.py) keyed on the working-tree hash, and
`handback.py --body-file` flags a run-ci-tests / affected / "Tests: N/N" pass claim that no valid receipt for the head's tree backs
(runner blob and re-derived selection checked; unwritable receipt dirs are "could not verify", never red). Offline."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(AD))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handback  # noqa: E402
import lkg  # noqa: E402
import test_handback as th  # noqa: E402

GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


class Fixture(unittest.TestCase):
    """A temp git repo plus a private landing dir (PERUN_LANDING_DIR) so receipts never touch the real cache."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.land = str(self.tmp / "land")
        old = os.environ.get("PERUN_LANDING_DIR")
        os.environ["PERUN_LANDING_DIR"] = self.land
        self.addCleanup(lambda: os.environ.pop("PERUN_LANDING_DIR") if old is None else os.environ.__setitem__("PERUN_LANDING_DIR", old))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.write("foo.txt", "1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def git(self, *a, cwd=None):
        return subprocess.run(["git", *a], cwd=cwd or self.repo, env={**os.environ, **GIT_ENV}, check=True, capture_output=True, text=True).stdout.strip()

    def write(self, name, text):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def rpath(self, tree):
        """Where a receipt for `tree` lands first (the git common dir)."""
        return os.path.join(lkg.receipt_dirs(str(self.repo))[0], lkg.affected_name(tree, str(self.repo)))

    def deny(self, *which):
        """The agent sandbox: block the receipt dirs named in `which` ('common', 'tmp', 'cache') by putting a file where each dir would go. Returns the env patch (apply with `with`)."""
        blocker = self.tmp / "blocker"
        blocker.write_text("x")
        env = {}
        if "common" in which:
            (self.repo / ".git/perun").write_text("x")
        if "tmp" in which:
            env["TMPDIR"] = str(blocker / "t")
        if "cache" in which:
            env["PERUN_LANDING_DIR"] = str(blocker / "land")
        return mock.patch.dict(os.environ, env)


class WorkTree(Fixture):
    def test_clean_tree_is_head_tree(self):
        self.assertEqual(lkg.work_tree(str(self.repo)), self.git("rev-parse", "HEAD^{tree}"))

    def test_modified_untracked_change_it_ignored_does_not_and_index_is_untouched(self):
        clean = lkg.work_tree(str(self.repo))
        self.write(".gitignore", "junk\n")
        gi = lkg.work_tree(str(self.repo))  # .gitignore itself is untracked content
        self.write("junk", "x\n")
        self.assertEqual(lkg.work_tree(str(self.repo)), gi)
        self.write("foo.txt", "2\n")
        mod = lkg.work_tree(str(self.repo))
        self.write("new.txt", "n\n")
        new = lkg.work_tree(str(self.repo))
        self.assertEqual(len({clean, gi, mod, new}), 4)
        self.assertEqual(self.git("status", "--porcelain"), "M foo.txt\n?? .gitignore\n?? new.txt")  # git() strips the leading space
        self.git("add", "-A")
        self.git("commit", "-qm", "all")
        self.assertEqual(self.git("rev-parse", "HEAD^{tree}"), new)  # what a lane commits is the tree that was scanned

    def test_same_size_edit_under_a_racy_index_is_seen(self):
        foo, idx = self.repo / "foo.txt", self.repo / ".git/index"
        m = foo.stat().st_mtime_ns
        foo.write_text("2\n")  # same size, and the stat below makes it identical to the index entry's: only git's racy-index rule (file mtime >= index mtime) can catch it
        os.utime(foo, ns=(m, m))
        os.utime(idx, ns=(m, m))
        time.sleep(1.1)  # a temp index copy that got a fresh mtime would now look older than the file and trust the stale stat
        self.assertNotEqual(lkg.work_tree(str(self.repo)), self.git("rev-parse", "HEAD^{tree}"))


class Receipt(Fixture):
    def rec(self, suites, tree=None, now=None):
        return lkg.record_affected("b" * 40, tree or lkg.work_tree(str(self.repo)), suites, str(self.repo), now=now)

    def test_pass_receipt_checks_ok_and_is_not_the_lkg_pointer(self):
        r = self.rec({"scripts/ci-tests.d/a.sh": 0})
        self.assertEqual((r["kind"], r["rc"]), ("affected", 0))
        self.assertTrue(lkg.affected_check(r["tree"], str(self.repo))[0])
        self.assertIsNone(lkg.read(str(self.repo)))
        self.assertFalse(lkg.check(r["sha"], str(self.repo))[0])
        self.assertFalse(lkg.verdict(self.rpath(r["tree"]), str(self.repo))[0])

    def test_failing_and_not_run_suites_are_not_ok(self):
        r = self.rec({"a.sh": 1, "b.sh": None, "c.sh": 0})
        ok, why = lkg.affected_check(r["tree"], str(self.repo))
        self.assertEqual(r["rc"], 1)
        self.assertFalse(ok)
        self.assertIn("a.sh rc=1", why)
        self.assertIn("b.sh rc=not run", why)
        self.assertNotIn("c.sh", why)

    def test_stale_receipt_for_another_tree_is_no_receipt(self):
        self.rec({"a.sh": 0})
        self.write("foo.txt", "changed\n")
        self.assertEqual(lkg.affected_check(lkg.work_tree(str(self.repo)), str(self.repo)), (False, "no receipt for this tree"))

    def test_corrupt_receipt_fails_closed(self):
        r = self.rec({"a.sh": 0})
        Path(self.rpath(r["tree"])).write_text('{"kind": "affected", "tree": "%s", "suites": 5, "rc": 0}' % r["tree"])
        self.assertFalse(lkg.affected_check(r["tree"], str(self.repo))[0])

    def test_record_affected_is_not_a_cli_subcommand(self):
        r = subprocess.run([sys.executable, str(AD / "lkg.py"), "record-affected", "b", "t", "x.sh=0"], cwd=self.repo, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("record-affected", r.stderr)
        self.assertEqual(lkg.record_affected_cli(["b"], str(self.repo)), 1)  # the internal entry rejects a short call with a message, not a traceback

    def test_unreadable_receipt_is_could_not_verify_not_a_refusal(self):
        p = self.rpath(self.rec({"a.sh": 0})["tree"])
        os.remove(p)
        os.mkdir(p)  # exists, cannot be read
        ok, why = lkg.affected_check(lkg.work_tree(str(self.repo)), str(self.repo))
        self.assertIsNone(ok)
        self.assertIn("could not verify: a receipt for this tree exists but cannot be read", why)

    def test_receipt_missing_a_key_is_refused_without_a_keyerror(self):
        r = self.rec({"a.sh": 0})
        p = Path(self.rpath(r["tree"]))
        full = json.loads(p.read_text())
        for k in ("kind", "tree", "base", "suites", "utc", "rc"):
            with self.subTest(missing=k):
                p.write_text(json.dumps({a: b for a, b in full.items() if a != k}))
                self.assertFalse(lkg.affected_check(r["tree"], str(self.repo))[0])
        p.write_text(json.dumps({**full, "base": 7}))  # a wrong type is as bad as a missing key
        self.assertFalse(lkg.affected_check(r["tree"], str(self.repo))[0])

    def test_old_receipts_are_pruned_on_write(self):
        old = self.rec({"a.sh": 0})
        p = self.rpath(old["tree"])
        os.utime(p, (1, 1))
        self.write("foo.txt", "2\n")
        self.rec({"a.sh": 0})
        self.assertFalse(os.path.exists(p))

    def test_receipt_records_the_runner_blob(self):
        self.assertEqual(self.rec({"a.sh": 0})["runner"], "")  # no runner in this repo
        self.write(lkg.RUNNER, "echo hi\n")
        self.assertEqual(self.rec({"a.sh": 0})["runner"], self.git("hash-object", lkg.RUNNER))

    def test_denied_home_still_writes_and_reads_in_the_git_common_dir(self):
        with self.deny("cache"):
            with self.assertRaises(OSError):
                lkg.path(str(self.repo))  # ~/.cache (the landing dir) is unusable, as in the agent sandbox
            r = self.rec({"a.sh": 0})
            self.assertTrue(os.path.exists(self.rpath(r["tree"])))
            self.assertTrue(lkg.affected_check(r["tree"], str(self.repo))[0])

    def test_tmpdir_is_the_second_choice(self):
        with self.deny("common", "cache"):
            tmp = self.tmp / "tmpdir"
            with mock.patch.dict(os.environ, {"TMPDIR": str(tmp)}):
                r = self.rec({"a.sh": 0})
                self.assertTrue((tmp / "perun" / lkg.affected_name(r["tree"], str(self.repo))).exists())
                self.assertTrue(lkg.affected_check(r["tree"], str(self.repo))[0])

    def test_landing_cache_dir_is_the_last_choice(self):
        with self.deny("common", "tmp"):
            r = self.rec({"a.sh": 0})
            self.assertTrue((Path(self.land) / lkg.affected_name(r["tree"], str(self.repo))).exists())
            self.assertTrue(lkg.affected_check(r["tree"], str(self.repo))[0])

    def test_the_newest_receipt_across_dirs_wins(self):
        one, two = str(self.tmp / "one"), str(self.tmp / "two")
        tree = lkg.work_tree(str(self.repo))
        with mock.patch.object(lkg, "receipt_dirs", return_value=[one]):
            lkg.record_affected("b" * 40, tree, {"a.sh": 1}, str(self.repo), now=1)  # an old failure in the preferred dir
        with mock.patch.object(lkg, "receipt_dirs", return_value=[two]):
            lkg.record_affected("b" * 40, tree, {"a.sh": 0}, str(self.repo))  # a later pass, when only the next dir was writable
        with mock.patch.object(lkg, "receipt_dirs", return_value=[one, two]):
            self.assertTrue(lkg.affected_check(tree, str(self.repo))[0])

    def test_no_writable_location_is_could_not_verify_not_a_false_claim(self):
        tree = lkg.work_tree(str(self.repo))
        with self.deny("common", "tmp", "cache"):
            with self.assertRaises(OSError) as cm:
                self.rec({"a.sh": 0})
            self.assertNotIn(str(self.tmp), str(cm.exception))  # no path in the text
            ok, why = lkg.affected_check(tree, str(self.repo))
            self.assertIsNone(ok)
            self.assertIn("could not verify", why)
            r = subprocess.run([sys.executable, str(AD / "lkg.py"), "affected-check", tree], cwd=self.repo, env=os.environ.copy(), capture_output=True, text=True)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_tilde_hides_the_home_dir(self):
        with mock.patch.dict(os.environ, {"HOME": "/home/jane"}):
            self.assertEqual(lkg.tilde(OSError("denied: '/home/jane/.cache/perun'")), "denied: '~/.cache/perun'")
        with mock.patch.dict(os.environ, {"HOME": "/"}):
            self.assertEqual(lkg.tilde("a/b"), "a/b")  # a root home must not eat every slash


class RunnerFixture(Fixture):
    """A repo holding a copy of the runner and the ci-tests a.sh then b.sh, both naming foo.txt (changed against self.base)."""

    def setUp(self):
        super().setUp()
        d = self.repo / ".claude/skills/agentic-delivery/scripts"
        d.mkdir(parents=True)
        for n in ("scrub_env.sh", "lkg.py", "landing_watchdog.py"):
            shutil.copy(AD / n, d)
        (self.repo / "scripts/ci-tests.d").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/run-ci-tests.sh", self.repo / "scripts")
        self.write("scripts/ci-gates.sh", "true\n")
        self.write(".banlist.txt", "# none\n")
        self.write(".gitignore", "__pycache__/\n")  # the runner's own python imports must not change the scanned tree
        self.git("add", "-A")
        self.git("commit", "-qm", "runner")
        self.base = self.git("rev-parse", "HEAD")
        self.write("foo.txt", "2\n")

    def suite(self, name, body):
        self.write(f"scripts/ci-tests.d/{name}.sh", f"# covers foo.txt\n{body}\n")

    def run_affected(self):
        env = {k: v for k, v in os.environ.items() if k not in ("RUN_CI_BASE", "BASE_SHA")}
        return subprocess.run(["bash", "scripts/run-ci-tests.sh", "--affected", self.base], cwd=self.repo, env={**env, **GIT_ENV}, capture_output=True, text=True)

    SUITES = ["scripts/ci-tests.d/a.sh", "scripts/ci-tests.d/b.sh"]


class Runner(RunnerFixture):
    def test_pass_records_a_receipt_with_the_runner_blob_and_every_suite(self):
        self.suite("a", "true")
        self.suite("b", "true")
        tree = lkg.work_tree(str(self.repo))
        r = self.run_affected()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ok, why = lkg.affected_check(tree, str(self.repo))
        self.assertTrue(ok, why)
        rec = json.loads(Path(self.rpath(tree)).read_text())
        self.assertEqual(rec["runner"], self.git("hash-object", "scripts/run-ci-tests.sh"))
        self.assertEqual(rec["suites"], dict.fromkeys(self.SUITES, 0))
        self.assertIsNone(lkg.read(str(self.repo)))

    def test_a_suite_that_changes_the_tree_leaves_no_receipt(self):
        self.suite("a", "touch stray.txt")  # the scanned state is no longer the state that ran: re-hashed after the run
        self.suite("b", "true")
        tree = lkg.work_tree(str(self.repo))
        r = self.run_affected()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("affected receipt not recorded (the suites changed the working tree", r.stderr)
        self.assertEqual(lkg.affected_check(tree, str(self.repo)), (False, "no receipt for this tree"))
        self.assertFalse(lkg.affected_check(lkg.work_tree(str(self.repo)), str(self.repo))[0])

    def test_list_affected_is_dry(self):
        self.suite("a", "touch ran.txt")
        self.suite("b", "true")
        env = {k: v for k, v in os.environ.items() if k not in ("RUN_CI_BASE", "BASE_SHA")}
        r = subprocess.run(["bash", "scripts/run-ci-tests.sh", "--list-affected", self.base], cwd=self.repo, env={**env, **GIT_ENV}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([n[10:] for n in r.stdout.splitlines() if n.startswith("selected: ")], self.SUITES)
        self.assertNotIn("== ", r.stdout)  # no privacy gate, no suite header
        self.assertFalse((self.repo / "ran.txt").exists())
        self.assertFalse(os.path.exists(self.rpath(lkg.work_tree(str(self.repo)))))

    def test_fail_fast_failure_records_rc_and_unrun_suites(self):
        self.suite("a", "false")
        self.suite("b", "true")
        tree = lkg.work_tree(str(self.repo))
        r = self.run_affected()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        ok, why = lkg.affected_check(tree, str(self.repo))
        self.assertFalse(ok)
        self.assertIn("scripts/ci-tests.d/a.sh rc=1", why)
        self.assertIn("scripts/ci-tests.d/b.sh rc=not run", why)

    def test_missing_lkg_script_still_runs_and_warns(self):
        (self.repo / ".claude/skills/agentic-delivery/scripts/lkg.py").unlink()
        self.suite("a", "true")
        r = self.run_affected()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("affected receipt not recorded", r.stderr)


class Forge(RunnerFixture):
    """A receipt must be backed by the runner and the selection of THIS tree: a one-line CLI call that lists some suites, or names another runner, is refused."""

    def honest(self):
        self.suite("a", "true")
        self.suite("b", "true")
        tree = lkg.work_tree(str(self.repo))
        r = self.run_affected()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return tree

    def forge(self, tree, *suites):
        self.assertEqual(lkg.record_affected_cli([self.base, tree, *suites], str(self.repo)), 0)

    def test_the_honest_receipt_passes_the_rederived_selection(self):
        tree = self.honest()
        ok, why = lkg.affected_check(tree, str(self.repo), self.base)
        self.assertTrue(ok, why)

    def test_a_partial_forged_receipt_is_refused(self):
        tree = self.honest()
        self.forge(tree, "scripts/ci-tests.d/a.sh=0")
        ok, why = lkg.affected_check(tree, str(self.repo), self.base)
        self.assertFalse(ok)
        self.assertIn("lacks selected suite(s) at rc 0: scripts/ci-tests.d/b.sh", why)

    def test_a_receipt_naming_unrelated_suites_is_refused(self):
        tree = self.honest()
        self.forge(tree, "x.sh=0")
        self.assertIn("scripts/ci-tests.d/a.sh, scripts/ci-tests.d/b.sh", lkg.affected_check(tree, str(self.repo), self.base)[1])

    def test_a_selected_but_not_run_suite_is_refused(self):
        tree = self.honest()
        self.forge(tree, "scripts/ci-tests.d/a.sh=0", "scripts/ci-tests.d/b.sh=-")
        self.assertFalse(lkg.affected_check(tree, str(self.repo), self.base)[0])

    def test_another_runner_blob_is_refused(self):
        tree = self.honest()
        p = Path(self.rpath(tree))
        p.write_text(json.dumps({**json.loads(p.read_text()), "runner": "0" * 40}))
        ok, why = lkg.affected_check(tree, str(self.repo), self.base)
        self.assertFalse(ok)
        self.assertIn("receipt runner 000000000000 is not scripts/run-ci-tests.sh in this tree", why)

    def test_a_base_chosen_by_the_forger_does_not_shrink_the_selection(self):
        self.suite("a", "true")
        self.suite("b", "true")
        self.git("add", "-A")
        self.git("commit", "-qm", "work")
        tree = lkg.work_tree(str(self.repo))
        lkg.record_affected(self.git("rev-parse", "HEAD"), tree, {"x.sh": 0}, str(self.repo))  # base = HEAD: nothing changed, nothing selected
        self.assertTrue(lkg.affected_check(tree, str(self.repo))[0])  # vs its own base, vacuous
        ok, why = lkg.affected_check(tree, str(self.repo), self.base)  # vs the base the hand-back names
        self.assertFalse(ok)
        self.assertIn("lacks selected suite", why)

    def test_a_dirty_worktree_cannot_rederive_the_claimed_tree(self):
        tree = self.honest()
        self.write("late.txt", "x\n")
        ok, why = lkg.affected_check(tree, str(self.repo), self.base)
        self.assertFalse(ok)
        self.assertIn("worktree is not the receipt's tree", why)

    def test_an_underivable_selection_is_could_not_verify(self):
        tree = self.honest()
        ok, why = lkg.affected_check(tree, str(self.repo), "no-such-base")
        self.assertIsNone(ok)
        self.assertIn("could not verify", why)


class Claim(unittest.TestCase):
    """handback.py --body-file: a run-ci-tests / affected pass claim needs a passing receipt for the head's tree."""
    setUp, tearDown, git, commit = (th.T.__dict__[n] for n in ("setUp", "tearDown", "git", "commit"))

    def go(self, body, receipt=None, lkg_head=False, deny=()):
        """Handback a lane whose body is `body`; receipt = (tree-of 'head' | 'main', suites) to record first; deny = receipt dirs ('cache', 'tmp', 'common') the hand-back cannot use, as in the agent sandbox
        (the test process itself keeps a writable landing dir, so a receipt can still be recorded before the denied hand-back)."""
        land = str(self.d / "land")
        self.env["PERUN_LANDING_DIR"] = land
        os.environ["PERUN_LANDING_DIR"] = land
        self.addCleanup(os.environ.pop, "PERUN_LANDING_DIR", None)
        (self.d / "blocker").write_text("x")
        if "cache" in deny:
            self.env["PERUN_LANDING_DIR"] = str(self.d / "blocker" / "land")
        if "tmp" in deny:
            self.env["TMPDIR"] = str(self.d / "blocker" / "t")
        if "common" in deny:
            (self.repo / ".git/perun").write_text("x")
        self.git("checkout", "-q", "-b", "lane")
        self.commit("changelog.d/x.md", "### Added\n- x\n", "frag")
        sha = self.commit("work.txt", "w\n", "work\n\nTests: 1/1")
        if receipt:
            which, suites = receipt
            lkg.record_affected("main", self.git("rev-parse", ("HEAD" if which == "head" else "main") + "^{tree}"), suites, str(self.repo))
        if lkg_head:
            lkg.record(str(self.repo))
        (self.d / "body.md").write_text(body)
        return th.T.hb(self, sha, "--body-file", str(self.d / "body.md"))

    def flagged(self, r, why):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("handback RED: test claim", r.stdout)
        self.assertIn(f"unverified test claim ({why})", r.stdout)

    def test_claim_without_receipt_is_flagged(self):
        self.flagged(self.go("run-ci-tests --affected: 45/45 pass\n"), "no receipt for this tree")

    def test_stale_receipt_for_a_different_tree_is_flagged(self):
        self.flagged(self.go("run-ci-tests --affected: 3/3 pass\n", receipt=("main", {"a.sh": 0})), "no receipt for this tree")

    def test_failing_receipt_is_flagged(self):
        self.flagged(self.go("affected: 45/45 pass\n", receipt=("head", {"a.sh": 1, "b.sh": 0})), "receipt for this tree failed: a.sh rc=1")

    def test_matching_passing_receipt_is_green(self):
        r = self.go("run-ci-tests --affected: 2/2 pass\n", receipt=("head", {"a.sh": 0, "b.sh": 0}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_full_suite_lkg_of_the_head_backs_the_claim(self):
        self.assertEqual(self.go("run-ci-tests: all green\n", lkg_head=True).returncode, 0)

    def test_honest_prose_is_not_a_claim(self):
        for body in ("security: NOT RUN (docs only)\n", "run-ci-tests --affected: NOT RUN (no base)\n", "run-ci-tests: FAIL a.sh\n", "run-ci-tests --affected: not passed\n",
                     "run-ci-tests did not pass on b.sh\n", "affected: 2 of 3 passed\n", "run-ci-tests --affected: 44/45 pass, a.sh failed\n", "Tests: 11/12, one skipped\n",
                     "added 2 tests; lint ok\n", "added 2 tests; lint 3/3 not green\n"):
            with self.subTest(body=body):
                self.tearDown()
                self.setUp()  # a fresh repo per body
                self.assertEqual(self.go(body).returncode, 0, body)

    def test_tests_n_of_n_and_passing_claims_are_detected(self):
        for body in ("Tests: 12/12\n", "Tests 12/12 pass\n", "run-ci-tests --affected: 44/45 pass; rerun 45/45 pass\n", "all tests passing\n", "12 tests passing\n", "run-ci-tests passing\n", "Tests: 3 of 3 \u2705\n"):
            with self.subTest(body=body):
                self.tearDown()
                self.setUp()
                self.flagged(self.go(body), "no receipt for this tree")

    def test_prose_table(self):
        for line, claim in (("run-ci-tests: all green", True), ("Tests: 12/12", True), ("Tests 12/12 pass", True), ("run-ci-tests --affected: 44/45 pass; rerun 45/45 pass", True), ("added 2 tests; lint ok", False),
                            ("3 tests, all green", True), ("Tests 11/12 pass", False), ("affected tests ok", True), ("run-ci-tests: not ok", False), ("run-ci-tests never passed", False),
                            ("isn't passing: run-ci-tests", False), ("run-ci-tests: 2 of 3 passed", False), ("affected: 3/3 pass, not flaky", True), ("added a test", False), ("No-Tests-Reason: docs", False)):
            self.assertEqual(handback._is_claim(line), claim, line)

    def test_denied_home_with_a_receipt_in_the_common_dir_is_green(self):
        r = self.go("run-ci-tests --affected: 2/2 pass\n", receipt=("head", {"a.sh": 0, "b.sh": 0}), deny=("cache",))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_writable_receipt_location_is_yellow_not_red(self):
        r = self.go("run-ci-tests --affected: 2/2 pass\n", deny=("cache", "tmp", "common"))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertNotIn("RED", r.stdout)
        self.assertIn("test claim could not be verified (could not verify: no writable receipt location", r.stdout)
        self.assertIn("handback UNVERIFIED", r.stdout)

    def test_the_selection_is_rederived_against_the_merge_base_of_the_handback_base(self):
        self.go("no claim\n")
        sha, main = self.git("rev-parse", "HEAD"), self.git("rev-parse", "main")
        (self.d / "b.md").write_text("Tests: 1/1\n")
        with mock.patch.object(lkg, "affected_check", return_value=(True, "ok")) as m:
            self.assertEqual(handback.test_claim_gaps(str(self.d / "b.md"), sha, str(self.repo), "main"), ([], []))
        self.assertEqual(m.call_args.args, (self.git("rev-parse", "HEAD^{tree}"), str(self.repo), main))

    def test_unresolvable_tree_or_merge_base_is_yellow_and_never_uses_the_receipts_own_base(self):
        self.go("no claim\n")
        (self.d / "b.md").write_text("Tests: 1/1\n")
        head = self.git("rev-parse", "HEAD")
        with mock.patch.object(lkg, "affected_check", return_value=(True, "ok")) as m:
            for sha, base, what in (("0" * 40, "main", "tree"), (head, "no-such-ref", "merge-base of no-such-ref and the head"), (head, None, "merge-base of None and the head")):
                with self.subTest(what=what):
                    red, yellow = handback.test_claim_gaps(str(self.d / "b.md"), sha, str(self.repo), base)
                    self.assertEqual(red, [])
                    self.assertEqual(len(yellow), 1)
                    self.assertIn(f"test claim could not be verified (could not verify: cannot resolve the {what})", yellow[0])
        m.assert_not_called()

    def test_unreadable_receipt_is_yellow_in_the_handback(self):
        self.go("no claim\n")
        (self.d / "b.md").write_text("Tests: 1/1\n")
        tree = self.git("rev-parse", "HEAD^{tree}")
        p = os.path.join(lkg.receipt_dirs(str(self.repo))[0], lkg.affected_name(tree, str(self.repo)))
        os.makedirs(p)
        red, yellow = handback.test_claim_gaps(str(self.d / "b.md"), self.git("rev-parse", "HEAD"), str(self.repo), "main")
        self.assertEqual(red, [])
        self.assertIn("exists but cannot be read", yellow[0])

    def test_error_text_never_carries_the_home_path(self):
        self.go("no claim\n")
        (self.d / "b.md").write_text("Tests: 1/1\n")
        with mock.patch.dict(os.environ, {"HOME": "/home/jane"}), mock.patch.object(lkg, "affected_check", side_effect=OSError("denied: '/home/jane/.cache/perun'")):
            red, yellow = handback.test_claim_gaps(str(self.d / "b.md"), self.git("rev-parse", "HEAD"), str(self.repo), "main")
        self.assertEqual(red, [])
        self.assertIn("~/.cache/perun", yellow[0])
        self.assertNotIn("/home/jane", yellow[0])


if __name__ == "__main__":
    unittest.main()
