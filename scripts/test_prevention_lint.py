"""prevention_lint.py: each action item needs owner, tracking id, verifiable end state."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/prevention_lint.py"
HEAD = "| Action | Type | Owner | Bug/issue | Done when |\n|---|---|---|---|---|\n"


def lint(body, head=HEAD):
    f = pathlib.Path(tempfile.mkdtemp(), "pm.md")
    f.write_text(head + body)
    return subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)


class T(unittest.TestCase):
    def test_complete_row_passes(self):
        r = lint("| add alert | prevent | jane | #42 | alert fires in the staging drill |\n")
        self.assertEqual((r.returncode, r.stdout), (0, "ok\n"))

    def test_each_missing_field_is_named(self):
        r = lint("| a | prevent | | no ticket | |\n")
        self.assertEqual(r.returncode, 1)
        for w in ("owner missing", "tracking id missing", "verifiable end state missing"):
            self.assertIn(w, r.stdout)

    def test_placeholder_values_fail_and_blank_template_row_is_skipped(self):
        self.assertEqual(lint("| a | p | TBD | #1 | check passes |\n").returncode, 1)
        self.assertEqual(lint("| | | | | |\n| a | p | jane | ABC-7 | test green |\n").returncode, 0)

    def test_header_names_match_whole_not_substring(self):
        # "Provider" contains "id", "Ownership" contains "owner": neither is the tracking/owner column.
        r = lint("| a | b | c | d | e |\n", "| Provider | Ownership | Verified by | Action | Notes |\n|---|---|---|---|---|\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no table", r.stdout)
        r = lint("| a | jane | #4 | ok at drill |\n", "| Action | Owner | Bug/issue | Done when (verifiable) |\n|---|---|---|---|\n")
        self.assertEqual(r.returncode, 0)

    def test_url_counts_as_id(self):
        self.assertEqual(lint("| a | p | jane | https://example.com/i/3 | done |\n").returncode, 0)

    def test_table_without_the_columns_fails_closed(self):
        r = lint("| a | b |\n", head="| Action | Owner |\n|---|---|\n")
        self.assertEqual(r.returncode, 2)

    def test_unreadable_file_exit_2(self):
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), "/nonexistent.md"], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
