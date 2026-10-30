#!/usr/bin/env python3
"""heavy_gate.DEFAULT_PATTERNS hold perf_compare.sh (a hyperfine A/B: it checks out a second tree and runs the command repeatedly)
like Perun's other scan/CI entrypoints: held while the machine is busy, never held for --help/-h, a read or lint of the file,
or a mere mention of its name. The hook tests feed heavy_gate.py a busy and an idle machine through its $PERUN_GATE_* injection
and a private lease dir. Offline; nothing named here is ever executed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
SC = Path(__file__).resolve().parents[1] / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import heavy_gate as hg  # noqa: E402

PC = ".claude/skills/deep-code-review/scripts/perf_compare.sh"
HEAVY = [
    f"bash {PC} -- npm test", f"bash {PC} --runs 5 --base origin/main -- make bench", "./perf_compare.sh --runs 5 -- make",
    f"time bash {PC} -- ./run", f"cd app && bash {PC} --base HEAD~3 -- node bench.js", "bash -c 'bash scripts/perf_compare.sh -- ./run'",
    f"sh {PC} -- ./run", f"zsh {PC} -- ./run", f"nice -n 5 bash {PC} -- ./run", f"CI=1 bash {PC} -- ./run", f"echo ok && bash {PC} -- ./run",
]
LIGHT = [
    f"bash {PC} --help", f"bash {PC} -h", "perf_compare.sh --help", f"cat {PC}", f"shellcheck {PC}", f"bash -n {PC}", f"grep -n runs {PC}",
    "git commit -m 'perf_compare.sh tweak'", "echo perf_compare.sh", "command -v perf_compare.sh", f"ls {PC}",
]


def hook(cmd, load1, d):
    """Run heavy_gate.py as the PreToolUse hook on `cmd` with an injected load; returns its stdout (empty = allowed)."""
    env = {k: v for k, v in os.environ.items() if k != "PERUN_HEAVY_PATTERNS"}
    env.update(PERUN_HEAVY_DIR=str(Path(d) / "heavy"), PERUN_POLICY=str(Path(d) / "none.json"), PERUN_GATE_LOAD1=str(load1),
               PERUN_GATE_CORES="8", PERUN_GATE_FREE_RAM_PCT="60", PERUN_HEAVY_HOOK_WAIT_SECS="0")
    return subprocess.run([sys.executable, str(SC / "heavy_gate.py")], input=json.dumps({"tool_input": {"command": cmd}, "cwd": "/w"}),
                          env=env, capture_output=True, text=True, timeout=30).stdout


class PerfComparePatterns(unittest.TestCase):
    def test_entrypoint_is_heavy_however_it_is_launched(self):
        for c in HEAVY:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_help_reads_lints_and_mentions_stay_light(self):
        for c in LIGHT:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_docstring_lists_the_entrypoint(self):
        self.assertIn("perf_compare.sh", hg.__doc__)


class PerfCompareHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / "heavy").mkdir()
        (Path(self.tmp.name) / "none.json").write_text("{}")

    def test_busy_machine_denies_the_run(self):
        out = json.loads(hook(HEAVY[0], 99, self.tmp.name))["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("machine busy", out["permissionDecisionReason"])

    def test_idle_machine_allows_the_run(self):
        self.assertEqual(hook(HEAVY[0], 0, self.tmp.name), "")

    def test_help_passes_even_when_busy(self):
        for c in LIGHT[:3]:
            self.assertEqual(hook(c, 99, self.tmp.name), "", c)


if __name__ == "__main__":
    unittest.main()
