#!/usr/bin/env python3
"""Tests for the merge-train gate's use of the shared tree-keyed PASS cache (gate_cache.py): merge_train.py's
`Train.fails()` skips a union tree whose PASS another run or stage already recorded, never persists a FAIL, and
honours the opt-out. Real git repo and real throwaway worktrees (the train's own `tree()`), a real `sh -c` verify
command that counts its runs in a file outside the repo. Run: python3 scripts/test_train_gate_cache.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
GC = ROOT / ".claude/skills/deep-code-review/scripts/gate_cache.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import merge_train  # noqa: E402

VERIFY = 'echo x >> "$COUNTER"'


class TrainCache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="train-gc-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.counter = self.tmp / "counter"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PERUN_"))}
        self.env.update(HOME=str(self.tmp), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", COUNTER=str(self.counter))
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)  # the train's own git/sh children inherit this hermetic environment
        self.addCleanup(self.restore)
        self.git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("one\n")
        self.git("add", "-A")
        self.git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self._cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)

    def restore(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.pop("PERUN_GATE_CACHE", None)

    def git(self, *a):
        p = subprocess.run(["git", *a], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def train(self, verify=VERIFY, count_cmd="", cap=None):
        a = SimpleNamespace(repo=None, state=str(self.tmp / "state.json"), verify_cmd=verify, count_cmd=count_cmd, cap=cap,
                            retries=0, gate_backoff=0, backoff=0, timeout=60)
        out = io.StringIO()
        t = merge_train.Train(a, merge_train.default_runner, out, lambda s: None)
        t.base_sha = self.base
        return t, out

    def runs(self):
        return len(self.counter.read_text().split()) if self.counter.exists() else 0

    def entries(self):
        d = self.repo / ".git" / "perun-gate-cache"
        return list(d.glob("*")) if d.is_dir() else []


class Fails(TrainCache):
    def test_a_green_union_tree_is_not_retested_by_the_next_train_run(self):
        t1, _ = self.train()
        self.assertEqual(t1.fails([], "base"), "")
        self.assertEqual(self.runs(), 1)
        t2, out = self.train()  # a fresh Train: its in-memory verdicts are empty, only the shared cache can answer
        self.assertEqual(t2.fails([], "base"), "")
        self.assertEqual(self.runs(), 1)
        self.assertIn("(gate_cache)", out.getvalue())

    def test_a_pass_recorded_by_another_stage_is_honoured(self):
        p = subprocess.run([sys.executable, str(GC), "run", "--stage", "pre-push", "-c", VERIFY], cwd=self.repo, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual((p.returncode, self.runs()), (0, 1))  # a pipefail run: the stricter verdict
        t, out = self.train()
        self.assertEqual(t.fails([], "base"), "")
        self.assertEqual(self.runs(), 1)
        self.assertIn("verdict=pass (gate_cache)", out.getvalue())

    def test_a_fail_is_never_persisted(self):
        for want in (1, 2):
            t, _ = self.train(verify=VERIFY + "; exit 1")
            self.assertEqual(t.fails([], "base"), "verify")
            self.assertEqual(self.runs(), want)
        self.assertEqual(self.entries(), [])

    def test_opt_out_runs_every_time_and_records_nothing(self):
        os.environ["PERUN_GATE_CACHE"] = "0"
        for want in (1, 2):
            t, out = self.train()
            self.assertEqual(t.fails([], "base"), "")
            self.assertEqual(self.runs(), want)
            self.assertNotIn("gate_cache", out.getvalue())
        self.assertEqual(self.entries(), [])

    def test_a_count_gate_is_part_of_the_verdict_and_the_key(self):
        t, _ = self.train(count_cmd="echo 3", cap=5)
        self.assertEqual(t.fails([], "base"), "")
        self.assertEqual(self.runs(), 1)
        t2, _ = self.train(count_cmd="echo 3", cap=5)
        self.assertEqual(t2.fails([], "base"), "")
        self.assertEqual(self.runs(), 1)  # same verify + same count gate: cached
        t3, _ = self.train(count_cmd="echo 9", cap=5)
        self.assertEqual(t3.fails([], "base"), "cap 9>5")  # a different count command is a different suite
        self.assertEqual(self.runs(), 2)
        t4, _ = self.train(count_cmd="echo 9", cap=5)
        self.assertEqual(t4.fails([], "base"), "cap 9>5")  # the cap failure was not persisted
        self.assertEqual(self.runs(), 3)

    def test_without_the_cache_module_the_gate_just_runs(self):
        real, merge_train._GC = merge_train._GC, None
        try:
            for want in (1, 2):
                t, _ = self.train()
                self.assertEqual(t.fails([], "base"), "")
                self.assertEqual(self.runs(), want)
        finally:
            merge_train._GC = real
        self.assertEqual(self.entries(), [])


class Loader(unittest.TestCase):
    def test_the_sibling_skill_script_is_loaded(self):
        self.assertIsNotNone(merge_train._GC)
        self.assertTrue(callable(merge_train._GC.lookup))


if __name__ == "__main__":
    unittest.main()
