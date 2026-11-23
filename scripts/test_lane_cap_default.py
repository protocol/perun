"""The shipped LANE_TOOL_CAP default is 150, and every doc or install message that names a value names the template's."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/agentic-delivery"
NAMERS = (SK / "references/operating-discipline.md", SK / "references/cost-quality-guardrails.md", ROOT / "install.sh")


class LaneCapDefault(unittest.TestCase):
    def test_template_ships_150(self):
        env = json.loads((SK / "templates/operating-layer.settings.json").read_text())["env"]
        self.assertEqual(env["LANE_TOOL_CAP"], "150")

    def test_namers_match_template(self):
        cap = json.loads((SK / "templates/operating-layer.settings.json").read_text())["env"]["LANE_TOOL_CAP"]
        for path in NAMERS:
            vals = re.findall(r"LANE_TOOL_CAP=(\d+)", path.read_text())
            self.assertTrue(vals, path.name)
            self.assertEqual(set(vals), {cap}, path.name)


if __name__ == "__main__":
    unittest.main()
