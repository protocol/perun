#!/usr/bin/env python3
"""Offline tests for the lazy script table of a large skill index (scripts/skill_index.py, INDEX-scripts.md).

A skill with more than SCRIPTS_INLINE_MAX scripts keeps its references in INDEX.md and moves the script table to
INDEX-scripts.md, so the file a run reads on a routing miss does not carry ~80 script rows. Fixture trees are
synthetic; the real-repo cases assert structure and a byte cap, never prose.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import skill_index as si  # noqa: E402

CORE_CAP = 6000  # bytes: agentic-delivery/INDEX.md was 16962 before the split


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_skill(root, name, n):
    skill = root / ".claude/skills" / name
    put(skill / "SKILL.md", f"---\nname: {name}\ndescription: Use when testing {name}.\n---\n\n# {name}\n")
    put(skill / "references/r.md", "# R\n\nRead this when the fixture needs a reference.\n")
    for i in range(n):
        put(skill / f"scripts/s{i:02d}.py", f'"""s{i:02d}.py [--x] FILE -- fixture script number {i}."""\n')
    return skill


def run(fn, root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(root)
    return rc, err.getvalue()


class Split(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.big = make_skill(self.root, "big", si.SCRIPTS_INLINE_MAX + 1)
        self.small = make_skill(self.root, "small", si.SCRIPTS_INLINE_MAX)
        run(si.cmd_generate, self.root)

    def test_large_skill_moves_its_script_table_to_the_lazy_file(self):
        core = (self.big / "INDEX.md").read_text(encoding="utf-8")
        lazy = (self.big / si.SCRIPTS_INDEX).read_text(encoding="utf-8")
        self.assertIn("`references/r.md`", core)
        self.assertIn("Read `INDEX-scripts.md` when you need a script", core)  # the trigger the pointer carries
        self.assertIn("`../INDEX.md`, `### big`, has only each one-line purpose and arguments", core)
        self.assertNotIn("`scripts/s00.py`", core)
        for i in range(si.SCRIPTS_INLINE_MAX + 1):
            self.assertIn(f"| `scripts/s{i:02d}.py` | fixture script number {i}. | s{i:02d}.py [--x] FILE |", lazy)

    def test_skill_at_the_cap_keeps_its_table_inline(self):
        self.assertIn("`scripts/s00.py`", (self.small / "INDEX.md").read_text(encoding="utf-8"))
        self.assertFalse((self.small / si.SCRIPTS_INDEX).exists())

    def test_check_covers_the_lazy_file(self):
        self.assertEqual(run(si.cmd_check, self.root)[0], 0)
        (self.big / si.SCRIPTS_INDEX).write_text("stale\n", encoding="utf-8")
        rc, err = run(si.cmd_check, self.root)
        self.assertEqual(rc, 1)
        self.assertIn(f"STALE: .claude/skills/big/{si.SCRIPTS_INDEX}", err)
        (self.big / si.SCRIPTS_INDEX).unlink()
        self.assertIn(f"MISSING: .claude/skills/big/{si.SCRIPTS_INDEX}", run(si.cmd_check, self.root)[1])


    def test_check_flags_an_orphan_lazy_file(self):
        put(self.small / si.SCRIPTS_INDEX, "left over\n")
        rc, err = run(si.cmd_check, self.root)
        self.assertEqual(rc, 1)
        self.assertIn(f"ORPHAN: .claude/skills/small/{si.SCRIPTS_INDEX}", err)


class RealRepo(unittest.TestCase):
    def test_delivery_core_index_stays_small_and_the_lazy_file_lists_every_script(self):
        d = ROOT / ".claude/skills/agentic-delivery"
        self.assertLessEqual((d / "INDEX.md").stat().st_size, CORE_CAP)
        lazy = (d / si.SCRIPTS_INDEX).read_text(encoding="utf-8")
        for s in si.shipped_scripts(d):
            self.assertIn(f"`scripts/{s.name}`", lazy)

    def test_lookup_cost_is_measured_not_assumed(self):
        d = ROOT / ".claude/skills/agentic-delivery"
        core, lazy = (d / "INDEX.md").stat().st_size, (d / si.SCRIPTS_INDEX).stat().st_size
        self.assertLess(core, 16962)  # a reference lookup reads core only
        self.assertLess(core + lazy, 16962 + 5500)  # a script lookup reads both: about the old size, not far above; +130 for the reply_cap and decision_gate rows, +820 for the destructive_guard_core, file_finding, repeat_poll_guard, stage_run and subagent_brief_lint rows, +150 for the feeder_order row, +200 for the train_yield row, +100 for the lkg row, +200 for the red_main row and the stage-weights/serial CLI text, +400 = +348 INDEX-scripts.md (14732->15080: host_installer, peer_ack, pregate_parity rows) +51 skills/INDEX.md (14295->14346), +100 for the vendor_drift row, +200 = +284 INDEX-scripts.md growth (admission_check, host_accept rows) plus INDEX.md regen, +100 for the lane_worktree row, +50 for the bg_admit row, +150 for wave L28 rows (council, flow_health), +1000 for wave AL rows (reply_cap, fitness_tick, flake_holder, finding_guard, baseline_guard, freeze_gate, flow_alarm, prevention_lint, quarantine; measured 21360), +300 for the freeze_hook and flow-guards rows (measured 21617), +300 for the pipeline_hub row (measured 21895), +300 for the repo_settings_audit row (measured 22162), +200 for the privacy_guard row (measured 22303)

    def test_entry_index_points_at_the_lazy_file(self):
        self.assertIn(si.SCRIPTS_INDEX, (ROOT / ".claude/skills/INDEX.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
