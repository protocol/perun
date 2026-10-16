#!/usr/bin/env python3
"""Tests for deep-code-review/scripts/gate_map.py: the read-only report of which suites each gate stage runs
and which run more than once per tree. Real hook files in temp git repos, the real CLI as a subprocess.
Run: python3 scripts/test_gate_map.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GM = ROOT / ".claude/skills/deep-code-review/scripts/gate_map.py"
GCQ = ".claude/skills/deep-code-review/scripts/gate_cache.py"


class Map(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-map-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.hooks = self.repo / ".githooks"
        self.hooks.mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PERUN_", "DCR_", "VERIFY_", "BASE_AUDIT_",
                                                                              "BROWSER_", "RATCHET_"))}
        self.env.update(HOME=str(self.tmp), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, env=self.env, check=True)

    def hook(self, name, body):
        p = self.hooks / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)
        return p

    def gm(self, *args, **env):
        p = subprocess.run([sys.executable, str(GM), *args], cwd=self.repo, env={**self.env, **env}, capture_output=True, text=True)
        return p.returncode, p.stdout

    def lines(self, *args, **env):
        rc, out = self.gm(*args, **env)
        self.assertEqual(rc, 0, out)
        return out.splitlines()


class Stages(Map):
    def test_lists_each_stage_and_flags_an_uncached_duplicate(self):
        self.hook("pre-commit", "npm run lint\nnpm test\necho done\n")
        self.hook("pre-push", "npm test\nnpm run lint\nbash scripts/other-gate.sh\n")
        out = self.lines()
        self.assertEqual(out[:3], ["pre-commit:", "  uncached  npm run lint", "  uncached  npm test"])
        self.assertIn("pre-push:", out)
        self.assertIn("  uncached  bash scripts/other-gate.sh", out)
        dup = [ln for ln in out if ln.startswith("DUPLICATE")]
        self.assertEqual(len(dup), 2)
        self.assertIn("DUPLICATE  npm test  runs in pre-commit, pre-push; uncached in pre-commit, pre-push: wrap it with gate_cache.py run", dup)

    def test_suites_wrapped_in_every_stage_are_shared(self):
        self.hook("pre-commit", f"python3 {GCQ} run --stage pre-commit -c 'npm test'\n")
        self.hook("pre-push", f"python3 {GCQ} run --stage pre-push -c 'npm test'\n")
        out = self.lines()
        self.assertIn("  cached    npm test", out)
        self.assertIn("SHARED     npm test  runs in pre-commit, pre-push; cached everywhere, so once per tree", out)
        self.assertFalse([ln for ln in out if ln.startswith("DUPLICATE")])

    def test_a_suite_wrapped_in_only_one_stage_names_the_uncached_stage(self):
        self.hook("pre-commit", f"python3 {GCQ} run --stage pre-commit -c 'npm test'\n")
        self.hook("pre-push", "npm test\n")
        self.assertIn("DUPLICATE  npm test  runs in pre-commit, pre-push; uncached in pre-push: wrap it with gate_cache.py run",
                      self.lines())

    def test_argv_form_and_options_before_the_dash_dash(self):
        self.hook("pre-commit", f"python3 {GCQ} run --stage pre-commit -- pytest -c setup.cfg -q\n")
        self.hook("pre-push", f"python3 {GCQ} run --stage pre-push -- pytest -c setup.cfg -q\n")
        self.assertIn("SHARED     pytest -c setup.cfg -q  runs in pre-commit, pre-push; cached everywhere, so once per tree", self.lines())

    def test_range_aware_pre_push_tier_does_not_share_with_a_tree_pure_stage(self):
        self.hook("pre-commit", f"python3 {GCQ} run --stage pre-commit -c 'npm test'\n")
        out = self.lines(DCR_PREPUSH_CMD="npm test")
        self.assertIn("  cached    npm test  [range-aware]", out)
        self.assertTrue([ln for ln in out if ln.startswith("DUPLICATE  npm test") and "scopes differ" in ln and "DCR_PREPUSH_TREE_PURE=1" in ln])
        shared = self.lines(DCR_PREPUSH_CMD="npm test", DCR_PREPUSH_TREE_PURE="1")
        self.assertIn("SHARED     npm test  runs in pre-commit, pre-push; cached everywhere, so once per tree", shared)

    def test_train_stage_reads_its_env_commands(self):
        self.hook("pre-commit", f"python3 {GCQ} run --stage pre-commit -c 'npm test'\n")
        out = self.lines(BASE_AUDIT_CMD="npm test", BROWSER_CMD="npx playwright test", VERIFY_CMD="python3 merge_train.py verify --verify-cmd 'npm run lint'")
        self.assertIn("train:", out)
        self.assertIn("  cached    npm test", out)  # BASE_AUDIT_CMD is cached by train_land.sh
        self.assertIn("  uncached  npx playwright test", out)  # BROWSER_CMD is run directly
        self.assertIn("  cached    npm run lint", out)  # merge_train.py consults the cache for --verify-cmd
        self.assertIn("SHARED     npm test  runs in pre-commit, train; cached everywhere, so once per tree", out)

    def test_custom_stage_files_and_precheck_discovery(self):
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "precheck.sh").write_text("npm run lint\n")
        (self.repo / "ci").mkdir()
        (self.repo / "ci" / "gate.sh").write_text("make test\n")
        out = self.lines("--stage", "nightly=ci/gate.sh")
        self.assertIn("precheck:", out)
        self.assertIn("  uncached  npm run lint", out)
        self.assertIn("nightly:", out)
        self.assertIn("  uncached  make test", out)

    def test_follows_a_script_one_level_and_ignores_noise(self):
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "verify.sh").write_text(
            'pytest -q\necho "run pytest here"\ngit commit -m "fix; npm test"\ncd build && ls\n'
            'python3 "${scope_check}" x\nfor f in a b; do cat "$f"; done\nif ! npm run lint; then exit 1; fi\n')
        self.hook("pre-push", 'exec bash "$(dirname "$0")/../tools/verify.sh" "$@"\n')
        out = self.lines()
        self.assertEqual(out[0], "pre-push:")
        self.assertEqual([ln.strip() for ln in out[1:] if ln.startswith("  ")], ["uncached  pytest -q", "uncached  npm run lint"])

    def test_commands_that_only_mention_a_suite_are_not_listed(self):
        self.hook("pre-commit", "echo npm test\ngit grep pytest\ncat make test\ncommand -v npm\nmkdir -p build/out\n")
        self.assertEqual([ln for ln in self.lines() if ln.startswith("  ")], [])

    def test_a_program_that_is_a_variable_is_not_guessed_at(self):
        self.hook("pre-commit", '"$ROOT/scripts/test.sh"\n$RUNNER test\npython3 "$SCRIPT_DIR/check.py"\nmake lint\n')
        self.assertEqual([ln for ln in self.lines() if ln.startswith("  ")], ["  uncached  make lint"])

    def test_unparseable_lines_are_skipped_not_guessed(self):
        self.hook("pre-commit", "npm test 'unclosed\nmake lint\n")
        self.assertEqual([ln for ln in self.lines() if ln.startswith("  ")], ["  uncached  make lint"])

    def test_core_hookspath_is_honoured(self):
        outside = self.tmp / "hooks-elsewhere"
        outside.mkdir()
        (outside / "pre-push").write_text("cargo test\n")
        subprocess.run(["git", "config", "core.hooksPath", str(outside)], cwd=self.repo, env=self.env, check=True)
        self.assertIn("  uncached  cargo test", self.lines())

    def test_no_stage_at_all_says_so_and_exits_zero(self):
        shutil.rmtree(self.hooks)
        rc, out = self.gm()
        self.assertEqual(rc, 0)
        self.assertIn("no gate stages found", out)

    def test_bad_stage_option_is_a_usage_error(self):
        self.assertEqual(self.gm("--stage", "nope")[0], 2)

    def test_report_only_never_writes_anything(self):
        self.hook("pre-commit", "npm test\n")
        self.hook("pre-push", "npm test\n")

        def snapshot():
            return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in self.repo.rglob("*") if p.is_file()}
        before = snapshot()
        self.lines()
        self.lines("--stage", "x=.githooks/pre-push")
        self.assertEqual(snapshot(), before)
        self.assertFalse((self.repo / ".git" / "perun-gate-cache").exists())


if __name__ == "__main__":
    unittest.main()
