#!/usr/bin/env python3
"""Tests for the shared verdict cache as wired into templates/pre-push-verify.sh: the pre-push tier asks
gate_cache.py before paying for DCR_PREPUSH_CMD, and a PASS from another stage (pre-commit) on the same tree
is honoured. Real git repos, the real hook as a subprocess fed git's `<ref> <sha> <ref> <sha>` stdin line.
Run: python3 scripts/test_prepush_gate_cache.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PPV = ROOT / ".claude/skills/deep-code-review/templates/pre-push-verify.sh"
GC = ROOT / ".claude/skills/deep-code-review/scripts/gate_cache.py"
SUITE = 'echo x >> "$COUNTER"'


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prepush-gc-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.counter = self.tmp / "counter"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PERUN_", "DCR_"))}
        self.env.update(HOME=str(self.tmp), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", COUNTER=str(self.counter))
        self.git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("one\n")
        self.commit("base")
        self.base = self.sha()
        (self.repo / "a.txt").write_text("two\n")
        self.commit("change")

    def git(self, *a):
        p = subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=T", "-c", "user.email=t@example.com", *a], cwd=self.repo, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def sha(self):
        return self.git("rev-parse", "HEAD")

    def tree(self):
        return self.git("rev-parse", "HEAD^{tree}")

    def push(self, hook=PPV, **env):
        """Run the pre-push hook for HEAD against the base commit, as `git push` would feed it."""
        line = f"refs/heads/main {self.sha()} refs/heads/main {self.base}\n"
        return subprocess.run(["bash", str(hook), "origin"], input=line, cwd=self.repo, env={**self.env, "DCR_PREPUSH_CMD": SUITE, **env},
                              capture_output=True, text=True)

    def precommit_stage(self, *extra):
        """What a pre-commit hook does when it wraps the same suite: `gate_cache.py run` on the staged tree."""
        return subprocess.run([sys.executable, str(GC), "run", "--stage", "pre-commit", *extra, "-c", SUITE], cwd=self.repo,
                              env=self.env, capture_output=True, text=True)

    def runs(self):
        return len(self.counter.read_text().split()) if self.counter.exists() else 0

    def entries(self):
        d = self.repo / ".git" / "perun-gate-cache"
        return list(d.glob("*")) if d.is_dir() else []


class SharedAcrossStages(Hook):
    def test_commit_then_push_of_an_unchanged_tree_runs_the_suite_once(self):
        (self.repo / "a.txt").write_text("three\n")
        self.git("add", "a.txt")
        self.assertEqual(self.precommit_stage().returncode, 0)  # pre-commit: staged tree, runs the suite
        self.assertEqual(self.runs(), 1)
        self.git("commit", "-q", "-m", "three")
        p = self.push(DCR_PREPUSH_TREE_PURE="1")  # pre-push: the same tree, the same suite
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"cached PASS {self.tree()}", p.stdout)
        self.assertNotIn("running:", p.stdout)
        self.assertEqual(self.runs(), 1)

    def test_default_pre_push_is_range_aware_and_does_not_borrow_a_rangeless_stages_pass(self):
        (self.repo / "a.txt").write_text("three\n")
        self.git("add", "a.txt")
        self.precommit_stage()
        self.git("commit", "-q", "-m", "three")
        p = self.push()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("cached PASS", p.stdout)
        self.assertIn("running:", p.stdout)
        self.assertEqual(self.runs(), 2)

    def test_range_aware_push_repeated_over_the_same_range_is_cached(self):
        self.assertNotIn("cached PASS", self.push().stdout)
        self.assertIn("cached PASS", self.push().stdout)
        self.assertEqual(self.runs(), 1)

    def test_tree_pure_pass_survives_an_amend_but_a_range_aware_one_does_not(self):
        self.push(DCR_PREPUSH_TREE_PURE="1")
        self.push(DCR_PREPUSH_CMD=SUITE + " # range")
        self.git("commit", "-q", "--amend", "-m", "reworded")
        self.assertIn("cached PASS", self.push(DCR_PREPUSH_TREE_PURE="1").stdout)
        self.assertNotIn("cached PASS", self.push(DCR_PREPUSH_CMD=SUITE + " # range").stdout)
        self.assertEqual(self.runs(), 3)

    def test_a_changed_hook_is_a_new_gate_set(self):
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
        self.git("config", "core.hooksPath", str(hooks))
        self.push(DCR_PREPUSH_TREE_PURE="1")
        self.assertIn("cached PASS", self.push(DCR_PREPUSH_TREE_PURE="1").stdout)
        (hooks / "pre-commit").write_text("#!/bin/sh\necho edited\nexit 0\n")
        self.assertNotIn("cached PASS", self.push(DCR_PREPUSH_TREE_PURE="1").stdout)


class Plumbing(Hook):
    """What the hook hands gate_cache.py: a python3 shim on PATH records its argv, then runs the real interpreter."""

    def shimmed_push(self, **env):
        shim = self.tmp / "shim"
        shim.mkdir(exist_ok=True)
        log = self.tmp / "argv.log"
        (shim / "python3").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexec "{sys.executable}" "$@"\n')
        (shim / "python3").chmod(0o755)
        p = self.push(PATH=f"{shim}{os.pathsep}{os.environ['PATH']}", **env)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = log.read_text().splitlines()
        self.assertTrue(any(ln.split()[:1] and ln.split()[0].endswith("stage_run.py") for ln in lines), "stage_run.py wrapper line missing")
        return [ln for ln in lines if ln.split()[:1] and ln.split()[0].endswith("gate_cache.py")]  # not the stage_run.py wrapper line that carries the same argv

    def test_the_hook_passes_the_pushed_commit_tree_and_the_range(self):
        (call,) = self.shimmed_push()
        self.assertIn(f"--tree {self.sha()} ", call)
        self.assertIn(f"--base {self.base} --head {self.sha()}", call)
        self.assertIn("--stage pre-push", call)

    def test_a_tree_pure_tier_passes_no_range(self):
        (call,) = self.shimmed_push(DCR_PREPUSH_TREE_PURE="1")
        self.assertIn(f"--tree {self.sha()} ", call)
        self.assertNotIn("--base", call)
        self.assertNotIn("--head", call)

    def test_the_cache_key_text_and_skip_cache_reach_the_cache(self):
        (call,) = self.shimmed_push(DCR_PREPUSH_CACHE_KEY="node20")
        self.assertIn("--key node20", call)


class OptOutAndFailure(Hook):
    def test_perun_gate_cache_off_runs_every_time_and_writes_nothing(self):
        for _ in range(2):
            p = self.push(DCR_PREPUSH_TREE_PURE="1", PERUN_GATE_CACHE="0")
            self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual((self.runs(), self.entries()), (2, []))

    def test_skip_cache_forces_a_rerun_and_refreshes_the_entry(self):
        self.push(DCR_PREPUSH_TREE_PURE="1")
        p = self.push(DCR_PREPUSH_TREE_PURE="1", DCR_PREPUSH_SKIP_CACHE="1")
        self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual(self.runs(), 2)
        self.assertIn("cached PASS", self.push(DCR_PREPUSH_TREE_PURE="1").stdout)

    def test_skip_cache_does_not_override_an_explicit_off(self):
        self.push(DCR_PREPUSH_TREE_PURE="1", DCR_PREPUSH_SKIP_CACHE="1", PERUN_GATE_CACHE="off")
        self.assertEqual(self.entries(), [])

    def test_a_failing_tier_rejects_the_push_and_is_never_cached(self):
        for _ in range(2):
            p = self.push(DCR_PREPUSH_CMD=SUITE + "; exit 3", DCR_PREPUSH_TREE_PURE="1")
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("FAIL -- rejecting push", p.stderr)
            self.assertNotIn("cached PASS", p.stdout)
        self.assertEqual((self.runs(), self.entries()), (2, []))

    def test_without_the_cache_script_the_tier_still_runs_and_gates_the_push(self):
        lone = self.tmp / "lone" / "templates"
        lone.mkdir(parents=True)
        shutil.copy(PPV, lone / "pre-push-verify.sh")  # no ../scripts/gate_cache.py, no .claude/skills in the repo
        for _ in range(2):
            self.assertEqual(self.push(lone / "pre-push-verify.sh", DCR_PREPUSH_TREE_PURE="1").returncode, 0)
        self.assertEqual(self.runs(), 2)
        self.assertNotEqual(self.push(lone / "pre-push-verify.sh", DCR_PREPUSH_CMD="exit 5").returncode, 0)


if __name__ == "__main__":
    unittest.main()
