#!/usr/bin/env python3
"""invisible_chars.py: hidden-unicode and control-char rows with line, col and codepoint; caps; binary and symlink skips; stdin CLI.
Hermetic: temp dirs only; special characters are built with chr() so this file stays plain ASCII."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "deep-code-review" / "scripts"
sys.path.insert(0, str(SCRIPT))
sys.dont_write_bytecode = True
import invisible_chars as ic  # noqa: E402

NUL, ESC, RLO, ZWSP = chr(0), chr(27), chr(0x202E), chr(0x200B)


class ScanFile(unittest.TestCase):
    def test_hidden_and_control_rows_carry_line_col_codepoint(self):
        raw = ("ok\nname = '" + RLO + "x'\r\n" + ESC + "z" + ZWSP + "\n").encode()
        self.assertEqual(ic.scan_file("a.js", raw), [
            (3, "control-char", "control character U+001B at col 1"),
            (2, "hidden-unicode", "hidden character U+202E at col 9"),
            (3, "hidden-unicode", "hidden character U+200B at col 3")])

    def test_clean_text_tab_cr_ff_emoji_joiner_and_bom_are_quiet(self):
        raw = (chr(0xFEFF) + "a\tb\r\n\f" + chr(0x1F468) + chr(0x200D) + chr(0x1F469) + "\n").encode()
        self.assertEqual(ic.scan_file("a.md", raw), [])

    def test_hidden_cap_lists_twenty_then_counts_the_rest(self):
        rows = ic.scan_file("a.txt", (RLO + "\n").encode() * 25)
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[-1][2], "5 more hidden characters not listed")

    def test_binary_extension_gets_nothing_and_early_nul_only_its_first_control_row(self):
        body = (NUL + ESC + RLO).encode()
        self.assertEqual(ic.scan_file("logo.PNG", body), [])
        self.assertEqual(ic.scan_file("a.py", body), [(1, "control-char", "control character U+0000 at col 1")])

    def test_fixture_paths_are_not_dropped_here(self):  # review_checks.sh tags them [likely-fixture]; see test_invisible_chars_hardening.py
        rows = ic.scan_file("tests/fixtures/a.txt", (ESC + RLO).encode())
        self.assertEqual([r[1] for r in rows], ["control-char", "hidden-unicode"])


class Cli(unittest.TestCase):
    def test_stdin_paths_print_tsv_and_symlinks_and_missing_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "a.txt").write_bytes(("x" + ESC + "\n").encode())
            (td / "link.txt").symlink_to(td / "a.txt")
            r = subprocess.run([sys.executable, str(SCRIPT / "invisible_chars.py")], cwd=td, input="a.txt\nlink.txt\ngone.txt\n\n",
                               capture_output=True, text=True, timeout=30)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "a.txt\t1\tcontrol-char\tcontrol character U+001B at col 2\n", ""))


if __name__ == "__main__":
    unittest.main()
