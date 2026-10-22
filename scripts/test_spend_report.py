#!/usr/bin/env python3
"""Offline tests for spend_report.py and the marketplace/plugin manifests."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import spend_report as sr  # noqa: E402


class Spend(unittest.TestCase):
    def test_project_of(self):
        self.assertEqual(sr.project_of("ENG-12-jane"), "ENG-12")
        self.assertEqual(sr.project_of("web-bob"), "web")
        self.assertEqual(sr.project_of("shared"), "(unattributed)")
        self.assertEqual(sr.project_of(None), "(unattributed)")

    def test_aggregate_and_unpriced(self):
        rows = [
            {"api_key_name": "web-jane", "cost_usd": "1.50"},
            {"api_key_name": "web-bob", "cost_usd": "$2.25"},
            {"api_key_name": "oauth", "cost_usd": "9"},
            {"api_key_name": "web-jane", "cost_usd": ""},
        ]
        totals, unpriced = sr.aggregate(rows)
        self.assertEqual(totals, {"web": Decimal("3.75"), "(unattributed)": Decimal("9")})
        self.assertEqual(unpriced, {"web": 1})

    def test_nan_and_infinity_are_unpriced(self):
        rows = [{"key_name": "web-a", "cost": "NaN"}, {"key_name": "web-b", "cost": "Infinity"},
                {"key_name": "api-a", "cost": "1"}]
        totals, unpriced = sr.aggregate(rows)
        self.assertEqual(totals, {"web": Decimal(0), "api": Decimal(1)})
        self.assertEqual(unpriced, {"web": 2})
        r = self.run_cli("u.csv", "key_name,cost\nweb-a,NaN\napi-a,1\n")
        self.assertEqual(r.returncode, 0)

    def test_missing_columns(self):
        with self.assertRaises(ValueError):
            sr.aggregate([{"a": 1}])

    def run_cli(self, name, text, *args):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / name
            p.write_text(text)
            return subprocess.run([sys.executable, str(SKILL_SCRIPTS / "spend_report.py"), str(p), *args],
                                  capture_output=True, text=True)

    def test_cli_csv_and_json_and_warn(self):
        r = self.run_cli("u.csv", "key_name,cost\nweb-jane,5\nweb-bob,6\napi-x,1\n", "--warn", "10")
        self.assertEqual(r.returncode, 0)
        self.assertIn("web\t11  WARN", r.stdout)
        self.assertIn("TOTAL\t12", r.stdout)
        r = self.run_cli("u.json", json.dumps({"data": [{"workspace": "p1-a", "amount": 2}]}), "--json")
        self.assertEqual(json.loads(r.stdout), {"p1": {"total": "2", "unpriced_rows": 0}})

    def test_cli_bad_input_exit_2(self):
        self.assertEqual(self.run_cli("u.csv", "x,y\n1,2\n").returncode, 2)


class Manifests(unittest.TestCase):
    def setUp(self):
        self.pj = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.mj = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())

    def test_marketplace_schema(self):
        self.assertTrue({"name", "owner", "plugins"} <= self.mj.keys())
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.mj["name"]))
        (entry,) = self.mj["plugins"]
        self.assertEqual(entry["name"], self.pj["name"])  # entry name must equal manifest name
        self.assertEqual(entry["source"], ".")
        self.assertNotIn("version", entry)  # plugin.json is the single version source

    def test_plugin_version_lockstep(self):
        ver = (ROOT / ".claude/skills/deep-code-review/VERSION").read_text().strip()
        self.assertEqual(self.pj["version"], ver)

    def test_commands_have_frontmatter(self):
        cmds = sorted((ROOT / "commands").glob("*.md"))
        self.assertEqual([c.stem for c in cmds], ["cost-retro", "council", "critic", "deliver", "idea", "perun-run", "perun", "review"])
        for c in cmds:
            head = c.read_text().split("---")[1]
            self.assertIn("description:", head)
            self.assertIn("disable-model-invocation: true", head)

    def test_version_gate_catches_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".claude-plugin").mkdir()
            (root / "VERSION").write_text("1.2.3\n")
            (root / "CHANGELOG.md").write_text("## [1.2.3] - x\n")
            pj = root / ".claude-plugin/plugin.json"

            def gate():
                return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "version", str(root)],
                                      capture_output=True, text=True)

            pj.write_text('{\n  "version": "1.2.3",\n  "name": "x"\n}\n')
            self.assertEqual(gate().returncode, 0)
            pj.write_text('{\n  "version": "1.2.2",\n  "name": "x"\n}\n')
            self.assertNotEqual(gate().returncode, 0)
            pj.write_text('{"name":"x",\n    "version":   "1.2.3"}')  # any formatting parses
            self.assertEqual(gate().returncode, 0)
            pj.write_text('{"version":"1.2.2"}')  # compact drift is still caught
            self.assertNotEqual(gate().returncode, 0)
            pj.write_text('{\n  "version": "1.2.3"\n}\n')
            (root / ".claude-plugin/marketplace.json").write_text('{"plugins":[{"version":"1.2.3"}]}')
            self.assertNotEqual(gate().returncode, 0)


if __name__ == "__main__":
    unittest.main()
