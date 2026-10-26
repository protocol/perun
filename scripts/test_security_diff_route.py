#!/usr/bin/env python3
"""Pins the small-DIFF security route and the held-out seeded-security fixtures. Offline.

SKILL.md sends a security review of a small DIFF to references/appsec-verify.md section 0 (not the full map), reports
new-file line numbers, and section 0 anchors a finding at its sink. The held-out fixtures use classes absent from the
tuned set, every key line holds its marker, and the data stays fictional (no long key-shaped literal)."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / ".claude/skills/deep-code-review"
TUNED = ROOT / "scripts/eval-fixtures/security-seeded"
HELD = ROOT / "scripts/eval-fixtures/security-seeded-heldout"


def added_lines(fix, i):
    lines = (fix / "diffs" / f"{i}.diff").read_text().split("\n")
    start = next(n for n, l in enumerate(lines) if l.startswith("@@"))
    return [l[1:] for l in lines[start + 1:] if l.startswith("+")]


class Route(unittest.TestCase):
    def test_skill_routes_security_small_diff_to_verify_section_0(self):
        body = (D / "SKILL.md").read_text()
        m = re.search(r"Security review of a small DIFF[^\n]*", body)
        self.assertIsNotNone(m)
        self.assertIn("`references/appsec-verify.md` (section 0 first)", m.group(0))
        self.assertIn("not full-map", m.group(0))

    def test_line_is_the_new_file_line(self):
        self.assertIn("never the patch text's own line number", (D / "SKILL.md").read_text())

    def test_section_0_sweeps_and_anchors_at_the_sink(self):
        v = (D / "references/appsec-verify.md").read_text()
        sec = v.split("## 0. Small-DIFF security sweep", 1)[1].split("\n## 1.", 1)[0]
        for needle in ("Anchor each finding at the line a fix would change",
                       "the privileged call a missing check should guard", "skip the script"):
            self.assertIn(needle, sec)
        self.assertIn("start at section 0", v.split("\n", 1)[0])


class Wilson(unittest.TestCase):
    def test_interval_stays_open_at_full_recall_and_handles_edges(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from security_bench_score import wilson
        self.assertEqual(wilson(12, 12), [0.757, 1.0])
        self.assertEqual(wilson(0, 5), [0.0, 0.434])
        self.assertEqual(wilson(0, 0), [0.0, 1.0])


class HeldOut(unittest.TestCase):
    """The 1026 held-out set is burned: its classes shaped a later skill review, so it is regression data now."""

    keys = json.loads((HELD / "keys.json").read_text())

    def test_shape_and_classes_new_to_the_tuned_set(self):
        vuln = {i: k for i, k in self.keys.items() if k["cwe"]}
        self.assertEqual((len(vuln), len(self.keys) - len(vuln)), (6, 2))
        self.assertEqual({p.stem for p in (HELD / "diffs").glob("*.diff")}, set(self.keys))
        tuned = {k["cwe"] for k in json.loads((TUNED / "keys.json").read_text()).values() if k["cwe"]}
        self.assertFalse({k["cwe"] for k in vuln.values()} & tuned)
        self.assertEqual(len({k["cwe"] for k in vuln.values()}), 6)

    def test_key_line_holds_marker_and_data_is_fictional(self):
        for i, k in self.keys.items():
            if k["cwe"]:
                self.assertIn(k["marker"], added_lines(HELD, i)[k["line"] - 1], i)
        txt = "".join(p.read_text() for p in (HELD / "diffs").glob("*.diff"))
        self.assertFalse(re.search(r"[\"'][A-Za-z0-9_+=-]{32,}[\"']", txt))
        self.assertFalse(re.search(r"@(?!example\.com)\w+\.(com|org)\b", txt))


if __name__ == "__main__":
    unittest.main()
