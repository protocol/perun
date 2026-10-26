#!/usr/bin/env python3
"""Latency budget for the hooks that fire on every tool call (Bash PreToolUse guards, PostToolUse lane_cap, the statusline).

Each hook is spawned as a real process on a benign payload; the fastest of RUNS runs must stay under BUDGET_MS. The minimum is
used because machine load only adds time, so it is the stable signal; the budget is generous (a bare `python3 -c pass` costs
~20-40 ms) so it catches regressions such as a heavy module imported at top level, not noise. The test skips when the 1-minute
load average exceeds the core count. Set HOOK_BENCH=1 to print the minimum and median.
"""
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
BUDGET_MS = 400  # minimum of RUNS, 4x the 100 ms target: CI runners are slower than a laptop
BUDGETS = {}
RUNS = 7
_COMMON = {"session_id": "bench", "cwd": str(ROOT), "transcript_path": ""}
BASH = {**_COMMON, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status && ls -la"}}
POST = {**_COMMON, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {}}
STATUS = {**_COMMON, "model": {"display_name": "m"}, "workspace": {"current_dir": str(ROOT)}}
HOOKS = {"pipe_mask_guard": BASH, "bypass_guard": BASH, "destructive_guard": BASH, "heavy_gate": BASH,
         "outcome_claim_guard": BASH, "ceo_altitude_guard": BASH, "lane_cap": POST, "cost_statusline": STATUS}


def timings_ms(name: str, payload: dict, cache: str, runs: int = RUNS) -> list:
    # HOME=cache keeps the statusline's own bytecode cache out of the real home. PYTHONPYCACHEPREFIX gives the other hooks'
    # imported siblings warm bytecode as on an installed machine, even if the tree is read-only; the statusline sets its own prefix.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "HOME": cache}
    if name != "cost_statusline":
        env["PYTHONPYCACHEPREFIX"] = cache

    def run() -> float:
        t = time.perf_counter()
        subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py")], input=json.dumps(payload), text=True,
                       capture_output=True, env=env, cwd=ROOT, check=False)
        return (time.perf_counter() - t) * 1000
    run()  # warm the bytecode cache; not timed
    return [run() for _ in range(runs)]


class HookLatency(unittest.TestCase):
    @unittest.skipIf(hasattr(os, "getloadavg") and os.getloadavg()[0] > (os.cpu_count() or 1),
                     "machine overloaded: 1-minute load average above the core count")
    def test_every_call_hooks_under_budget(self):
        with tempfile.TemporaryDirectory(prefix="perun-hook-bench-") as cache:
            for name, payload in HOOKS.items():
                ts = timings_ms(name, payload, cache)
                if os.environ.get("HOOK_BENCH"):
                    print(f"{name}: min {min(ts):.1f} ms, median {statistics.median(ts):.1f} ms")
                budget = BUDGETS.get(name, BUDGET_MS)
                self.assertLess(min(ts), budget, f"{name} fastest of {len(ts)} runs {min(ts):.0f} ms exceeds {budget} ms")


if __name__ == "__main__":
    unittest.main()
