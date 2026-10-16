#!/usr/bin/env python3
"""Tests for deep-code-review/scripts/gate_cache.py: the tree-keyed PASS cache shared by every gate stage.

Real git repos in temp dirs, the real CLI as a subprocess. A suite is `echo x >> $COUNTER`, with the counter
file OUTSIDE the repo (a counter inside would make the tree dirty), so "how many times did the suite run" is
the line count. Run: python3 scripts/test_gate_cache.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GC = ROOT / ".claude/skills/deep-code-review/scripts/gate_cache.py"
sys.dont_write_bytecode = True  # never litter __pycache__ into a checksummed skill tree
sys.path.insert(0, str(GC.parent))
import gate_cache  # noqa: E402

SUITE = 'echo x >> "$COUNTER"'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-cache-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.counter = self.tmp / "counter"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PERUN_", "DCR_"))}
        self.env.update(HOME=str(self.tmp), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", COUNTER=str(self.counter))
        self.git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("one\n")
        self.commit("first")

    def git(self, *a, cwd=None, check=True):
        p = subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *a], cwd=cwd or self.repo,
                           env=self.env, capture_output=True, text=True)
        if check and p.returncode:
            raise AssertionError(f"git {a}: {p.stderr}")
        return p.stdout.strip()

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def gc(self, *args, cwd=None, **env):
        p = subprocess.run([sys.executable, str(GC), "run", *args], cwd=cwd or self.repo,
                           env={**self.env, **env}, capture_output=True, text=True)
        return p

    def runs(self):
        return len(self.counter.read_text().split()) if self.counter.exists() else 0

    def entries(self):
        d = self.repo / ".git" / "perun-gate-cache"
        return sorted(p for p in d.glob("*") if not p.name.startswith(".tmp-")) if d.is_dir() else []

    def tree(self):
        return self.git("rev-parse", "HEAD^{tree}")


class CacheSemantics(Base):
    def test_second_run_on_same_tree_is_one_line_and_runs_nothing(self):
        p1 = self.gc("-c", SUITE, "--label", "unit")
        self.assertEqual((p1.returncode, self.runs()), (0, 1))
        self.assertNotIn("cached PASS", p1.stdout)
        p2 = self.gc("-c", SUITE, "--label", "unit")
        self.assertEqual(p2.returncode, 0)
        self.assertEqual(p2.stdout.strip(), f"cached PASS {self.tree()} (unit)")
        self.assertEqual(self.runs(), 1)

    def test_fail_is_never_cached_and_its_exit_status_passes_through(self):
        for want_runs in (1, 2):
            p = self.gc("-c", SUITE + "; exit 7")
            self.assertEqual((p.returncode, self.runs()), (7, want_runs))
            self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual(self.entries(), [])

    def test_a_different_command_is_a_different_suite(self):
        self.gc("-c", SUITE)
        self.gc("-c", SUITE + " # lint")
        self.assertEqual(self.runs(), 2)
        self.assertEqual(len(self.entries()), 2)

    def test_changed_tree_misses_and_returning_to_a_passed_tree_hits(self):
        self.gc("-c", SUITE)
        (self.repo / "a.txt").write_text("two\n")
        self.commit("second")
        self.gc("-c", SUITE)
        self.assertEqual(self.runs(), 2)
        self.git("reset", "-q", "--hard", "HEAD~1")
        p = self.gc("-c", SUITE)
        self.assertIn("cached PASS", p.stdout)
        self.assertEqual(self.runs(), 2)

    def test_same_tree_new_commit_hits_when_tree_pure_and_misses_when_range_aware(self):
        self.gc("-c", SUITE)
        self.gc("-c", SUITE, "--base", "b1", "--head", "h1")
        self.git("commit", "-q", "--amend", "-m", "reworded")
        self.assertIn("cached PASS", self.gc("-c", SUITE).stdout)
        self.assertEqual(self.runs(), 2)
        self.assertIn("cached PASS", self.gc("-c", SUITE, "--base", "b1", "--head", "h1").stdout)
        self.assertNotIn("cached PASS", self.gc("-c", SUITE, "--base", "b2", "--head", "h1").stdout)
        self.assertEqual(self.runs(), 3)

    def test_tree_flag_must_equal_the_checked_out_tree(self):
        (self.repo / "a.txt").write_text("two\n")
        self.commit("second")
        self.assertEqual(self.gc("-c", SUITE, "--tree", "HEAD~1").returncode, 0)
        self.assertEqual((self.runs(), self.entries()), (1, []))  # ran, but a different tree than claimed: not cached
        self.gc("-c", SUITE, "--tree", "HEAD")
        self.assertIn("cached PASS", self.gc("-c", SUITE, "--tree", "HEAD").stdout)

    def test_pipefail_is_on_by_default_and_part_of_the_key(self):
        p = self.gc("-c", "false | cat")
        self.assertEqual(p.returncode, 1)  # the masked failure surfaces instead of being cached as a PASS
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.gc("-c", "false | cat", "--no-pipefail").returncode, 0)
        self.assertEqual(len(self.entries()), 1)
        p = self.gc("-c", "false | cat")  # the no-pipefail PASS is not served to a pipefail run
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("cached PASS", p.stdout)

    def test_a_pipefail_pass_satisfies_a_no_pipefail_run_but_not_the_reverse(self):
        self.gc("-c", SUITE)
        self.assertIn("cached PASS", self.gc("-c", SUITE, "--no-pipefail").stdout)
        self.assertEqual(self.runs(), 1)
        other = SUITE + " # other"
        self.gc("-c", other, "--no-pipefail")
        self.assertNotIn("cached PASS", self.gc("-c", other).stdout)  # the weaker verdict never serves the stricter run
        self.assertEqual(self.runs(), 3)

    def test_say_prints_only_before_a_real_run(self):
        p1 = self.gc("-c", SUITE, "--say", "running: the suite")
        self.assertEqual(p1.stdout.strip(), "running: the suite")
        p2 = self.gc("-c", SUITE, "--say", "running: the suite")
        self.assertNotIn("running", p2.stdout)
        self.assertIn("cached PASS", p2.stdout)

    def test_cache_failure_never_stops_the_suite_from_running(self):
        from unittest import mock
        with mock.patch.object(gate_cache, "context", side_effect=RuntimeError("boom")):
            err = tempfile.TemporaryFile("w+")
            real = sys.stderr
            sys.stderr = err
            try:
                rc = gate_cache.run(["true"], "true", cwd=str(self.repo))
            finally:
                sys.stderr = real
            err.seek(0)
            self.assertEqual(rc, 0)
            self.assertIn("running uncached", err.read())
        self.assertEqual(gate_cache.run(["false"], "false", cwd=str(self.repo)), 1)

    def test_argv_form_and_usage_errors(self):
        self.assertEqual(self.gc("--", "true").returncode, 0)
        self.assertIn("cached PASS", self.gc("--", "true").stdout)
        self.assertEqual(self.gc().returncode, 2)
        self.assertEqual(self.gc("-c", "true", "--", "true").returncode, 2)

    def test_unstartable_command_is_127(self):
        self.assertEqual(self.gc("--", "no-such-binary-gate-cache").returncode, 127)

    def test_linked_worktree_shares_the_cache(self):
        self.gc("-c", SUITE)
        wt = self.tmp / "wt"
        self.git("worktree", "add", "-q", "--detach", str(wt), "HEAD")
        self.assertIn("cached PASS", self.gc("-c", SUITE, cwd=wt).stdout)
        self.assertEqual(self.runs(), 1)


class NeverSkipsWhenUnprovable(Base):
    def test_dirty_or_untracked_tree_runs_and_records_nothing(self):
        (self.repo / "a.txt").write_text("edited\n")
        self.gc("-c", SUITE)
        self.gc("-c", SUITE)
        self.assertEqual((self.runs(), self.entries()), (2, []))
        self.git("checkout", "-q", "--", "a.txt")
        (self.repo / "stray.txt").write_text("x\n")
        self.gc("-c", SUITE)
        self.assertEqual((self.runs(), self.entries()), (3, []))
        (self.repo / "stray.txt").unlink()
        self.gc("-c", SUITE)  # clean again: the dirty runs above left no entry behind
        self.assertEqual(self.runs(), 4)

    def test_a_cached_tree_is_not_served_to_a_dirty_or_untracked_checkout(self):
        self.gc("-c", SUITE)  # a clean run records a PASS for this tree
        self.assertIn("cached PASS", self.gc("-c", SUITE).stdout)
        (self.repo / "a.txt").write_text("edited after the PASS\n")  # same index tree, different files on disk
        self.assertNotIn("cached PASS", self.gc("-c", SUITE).stdout)
        self.git("checkout", "-q", "--", "a.txt")
        (self.repo / "stray.txt").write_text("untracked\n")
        self.assertNotIn("cached PASS", self.gc("-c", SUITE).stdout)
        (self.repo / "stray.txt").unlink()
        self.assertIn("cached PASS", self.gc("-c", SUITE).stdout)  # clean again: the entry was never lost
        self.assertEqual(self.runs(), 3)

    def test_ignore_glob_exempts_only_the_stages_own_untracked_files(self):
        (self.repo / "train7.log.base").write_text("log\n")
        self.gc("-c", SUITE)
        self.gc("-c", SUITE)
        self.assertEqual((self.runs(), self.entries()), (2, []))  # without --ignore the stray log makes the tree dirty
        self.gc("-c", SUITE, "--ignore", "train*.log*")
        self.assertIn("cached PASS", self.gc("-c", SUITE, "--ignore", "train*.log*").stdout)
        self.assertEqual(self.runs(), 3)
        (self.repo / "other.txt").write_text("not the stage's file\n")  # a second, non-matching untracked file
        self.gc("-c", SUITE, "--ignore", "train*.log*")
        self.assertEqual(self.runs(), 4)

    def test_untracked_files_anywhere_in_the_repo_count_even_from_a_subdirectory(self):
        sub = self.repo / "sub"
        sub.mkdir()
        (sub / "kept.txt").write_text("x\n")
        self.commit("sub")
        (self.repo / "stray.txt").write_text("outside the subdirectory\n")
        self.gc("-c", SUITE, cwd=sub)
        self.gc("-c", SUITE, cwd=sub)
        self.assertEqual((self.runs(), self.entries()), (2, []))

    def test_a_run_that_edits_tracked_files_is_not_cached(self):
        p = self.gc("-c", 'echo more >> a.txt; ' + SUITE)
        self.assertEqual(p.returncode, 0)
        self.assertIn("not cached", p.stderr)
        self.assertEqual(self.entries(), [])

    def test_outside_a_git_repo_the_suite_just_runs(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.gc("-c", SUITE, cwd=plain)
        self.gc("-c", SUITE, cwd=plain)
        self.assertEqual(self.runs(), 2)
        self.assertFalse(list(plain.rglob("perun-gate-cache")))

    def test_unmerged_index_runs(self):
        self.git("checkout", "-q", "-b", "side")
        (self.repo / "a.txt").write_text("side\n")
        self.commit("side")
        self.git("checkout", "-q", "main")
        (self.repo / "a.txt").write_text("main\n")
        self.commit("main")
        self.git("merge", "side", check=False)
        self.gc("-c", SUITE)
        self.gc("-c", SUITE)
        self.assertEqual((self.runs(), self.entries()), (2, []))


class GateSetVersion(Base):
    """A change to the hooks or the gate scripts is a new gate set: every older entry misses."""

    def test_editing_an_out_of_tree_hook_invalidates(self):
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        (hooks / "pre-push").write_text("#!/bin/sh\nexit 0\n")
        self.git("config", "core.hooksPath", str(hooks))
        self.gc("-c", SUITE)
        self.assertIn("cached PASS", self.gc("-c", SUITE).stdout)
        (hooks / "pre-push").write_text("#!/bin/sh\necho changed\nexit 0\n")
        self.assertNotIn("cached PASS", self.gc("-c", SUITE).stdout)
        self.assertEqual(self.runs(), 2)

    def test_adding_a_hook_file_invalidates(self):
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        self.git("config", "core.hooksPath", str(hooks))
        self.gc("-c", SUITE)
        (hooks / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
        self.assertNotIn("cached PASS", self.gc("-c", SUITE).stdout)

    def test_editing_gate_cache_itself_invalidates(self):
        copy = self.tmp / "gc-copy.py"
        shutil.copy(GC, copy)

        def go():
            return subprocess.run([sys.executable, str(copy), "run", "-c", SUITE], cwd=self.repo, env=self.env,
                                  capture_output=True, text=True)
        go()
        self.assertIn("cached PASS", go().stdout)
        copy.write_text(copy.read_text() + "\n# edited\n")
        self.assertNotIn("cached PASS", go().stdout)

    def test_gate_files_and_version_env_invalidate(self):
        tool = self.tmp / "tool.sh"
        tool.write_text("v1\n")
        env = {"PERUN_GATE_FILES": str(tool)}
        self.gc("-c", SUITE, **env)
        self.assertIn("cached PASS", self.gc("-c", SUITE, **env).stdout)
        tool.write_text("v2\n")
        self.assertNotIn("cached PASS", self.gc("-c", SUITE, **env).stdout)
        self.assertIn("cached PASS", self.gc("-c", SUITE, **env).stdout)
        self.assertNotIn("cached PASS", self.gc("-c", SUITE, PERUN_GATE_SET_VERSION="2", **env).stdout)

    def test_operator_key_text_invalidates(self):
        self.gc("-c", SUITE, PERUN_GATE_CACHE_KEY="node20")
        self.assertIn("cached PASS", self.gc("-c", SUITE, PERUN_GATE_CACHE_KEY="node20").stdout)
        self.assertNotIn("cached PASS", self.gc("-c", SUITE, PERUN_GATE_CACHE_KEY="node22").stdout)
        self.assertNotIn("cached PASS", self.gc("-c", SUITE, "--key", "x", PERUN_GATE_CACHE_KEY="node20").stdout)


class OptOutAndExpiry(Base):
    def test_off_never_reads_or_writes(self):
        self.gc("-c", SUITE)
        before = [p.read_bytes() for p in self.entries()]
        p = self.gc("-c", SUITE, PERUN_GATE_CACHE="0")
        self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual(self.runs(), 2)
        (self.repo / "a.txt").write_text("two\n")
        self.commit("second")
        self.gc("-c", SUITE, PERUN_GATE_CACHE="off")
        self.assertEqual([p.read_bytes() for p in self.entries()], before)  # nothing written for the new tree

    def test_refresh_reruns_and_rewrites(self):
        self.gc("-c", SUITE)
        old = json.loads(self.entries()[0].read_text())["ts"]
        time.sleep(0.02)
        p = self.gc("-c", SUITE, PERUN_GATE_CACHE="refresh")
        self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual(self.runs(), 2)
        self.assertGreater(json.loads(self.entries()[0].read_text())["ts"], old)

    def test_entries_expire_after_seven_days_and_are_pruned(self):
        ctx = gate_cache.context(SUITE, cwd=str(self.repo))
        t0 = 1_000_000.0
        gate_cache.store(ctx, "unit", "pre-push", now=t0)
        week = 7 * 86400
        self.assertTrue(gate_cache.lookup(ctx, now=t0 + week - 1))
        self.assertFalse(gate_cache.lookup(ctx, now=t0 + week + 1))
        self.assertFalse(gate_cache.lookup(ctx, now=t0 - 5))  # a timestamp from the future is not trusted
        stale = Path(ctx["dir"]) / "stale-entry"
        stale.write_text("{}")
        os.utime(stale, (time.time() - 8 * 86400,) * 2)
        gate_cache.store(ctx, "unit", "pre-push")
        self.assertFalse(stale.exists())
        self.assertTrue(Path(ctx["path"]).exists())

    def test_corrupt_or_foreign_entry_is_a_miss(self):
        ctx = gate_cache.context(SUITE, cwd=str(self.repo))
        os.makedirs(ctx["dir"])
        for junk in ("", "{not json", "[]", '{"ts": "x"}', json.dumps({"tree": "t", "gate_set": "g", "config": "c", "ts": time.time()})):
            Path(ctx["path"]).write_text(junk)
            self.assertFalse(gate_cache.lookup(ctx), junk)


if __name__ == "__main__":
    unittest.main()
