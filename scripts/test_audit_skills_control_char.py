#!/usr/bin/env python3
"""audit_skills control-char rule: NUL and C0 control characters (all but tab, LF, CR, FF) in text files are reported
as `path:line: high control-char: control character U+XXXX at col N`; binary files (a NUL in the first 8 KB, or a known
binary extension) are not scanned for it; fixture paths are (no path skip). Hermetic: temp dirs only, control bytes built with chr() so
this file stays plain ASCII."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import audit_skills  # noqa: E402

NUL, ESC, BEL, VT = chr(0), chr(27), chr(7), chr(11)


def ctrl(files):
    """Scan a temp dir holding {relative path: text or bytes}; return [(file, line, message)] for control-char findings."""
    with tempfile.TemporaryDirectory() as td:
        for rel, body in files.items():
            p = Path(td) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
        return sorted((f["file"], f["line"], f["message"]) for f in audit_skills.scan(td)[0] if f["rule"] == "control-char")


class ControlChar(unittest.TestCase):
    def test_reports_line_col_codepoint(self):
        got = ctrl({"a.py": "ok\nx = 'a" + ESC + "b'\n\n" + BEL + "y\n"})
        self.assertEqual(got, [("a.py", 2, "control character U+001B at col 7"), ("a.py", 4, "control character U+0007 at col 1")])

    def test_col_counts_characters_and_crlf_keeps_line_numbers(self):
        got = ctrl({"a.md": "caf" + chr(233) + " " + chr(233) + VT + "\r\nsecond" + ESC + "\r\n"})
        self.assertEqual(got, [("a.md", 1, "control character U+000B at col 7"), ("a.md", 2, "control character U+001B at col 7")])

    def test_nul_past_8k_in_a_text_file_is_flagged(self):
        got = ctrl({"big.py": "x = 1\n" * 2000 + "y = '" + NUL + "'\n"})
        self.assertEqual(got, [("big.py", 2001, "control character U+0000 at col 6")])

    def test_tab_lf_cr_ff_and_del_are_clean(self):
        self.assertEqual(ctrl({"a.py": "a\tb\n\fc\r\nd\rf" + chr(127) + "\n"}), [])

    def test_nul_in_first_8k_is_binary_to_git_so_only_the_first_is_listed(self):
        got = ctrl({"src.py": "a = '" + NUL + "'\nb = '" + NUL + "'\n"})
        self.assertEqual(got, [("src.py", 1, "control character U+0000 at col 6")])
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "src.py").write_bytes(b"a = '\0'\n")
            rules = [f["rule"] for f in audit_skills.scan(td)[0]]
        self.assertEqual(sorted(rules), ["control-char", "unscanned"])  # still reported as unscanned: never skipped silently

    def test_known_binary_extensions_are_not_flagged_and_fixtures_are(self):  # audit_skills has ignore markers, so no path skip
        body = "a" + NUL + ESC + "b"
        self.assertEqual(ctrl({"logo.png": body, "lib/x.WASM": body}), [])
        self.assertEqual([f for f, _, _ in ctrl({"tests/fixtures/a.txt": ESC, "testdata/b.py": ESC, "x/FIXTURE_c.md": ESC})], ["testdata/b.py", "tests/fixtures/a.txt", "x/FIXTURE_c.md"])

    def test_cap_lists_twenty_then_counts_the_rest(self):
        got = ctrl({"a.txt": (ESC + "\n") * 25})
        self.assertEqual(len(got), 21)
        self.assertIn("5 more control characters not listed", [m for _, _, m in got])

    def test_cli_output_shape_and_exit(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "s.sh").write_text("echo hi\necho" + ESC + "[0m\n")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_skills.py"), td], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("s.sh:2: high control-char: control character U+001B at col 5", r.stdout)

    def test_hidden_unicode_rule_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.md").write_text("x" + chr(0x202E) + "y\n")
            self.assertEqual([f["rule"] for f in audit_skills.scan(td)[0]], ["hidden-unicode"])


if __name__ == "__main__":
    unittest.main()
