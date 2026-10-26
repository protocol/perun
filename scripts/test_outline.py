#!/usr/bin/env python3
"""Tests for deep-code-review/scripts/outline.py: exact Python ranges, regex fallback for other files, and the bytes-read cut on real files."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/deep-code-review/scripts"))
import outline  # noqa: E402


def write(d, name, text):
    p = os.path.join(d, name)
    Path(p).write_text(text)
    return p


class Outline(unittest.TestCase):
    def test_python_ranges_methods_and_decorators(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "a.py", "import os\n\n\n@dec\ndef f():\n    return 1\n\n\nclass C:\n    def m(self):\n        pass\n")
            self.assertEqual(outline.symbols(p), [(4, 6, "def", "f"), (9, 11, "class", "C"), (10, 11, "def", "C.m")])

    def test_regex_fallback_shell_markdown_js(self):
        with tempfile.TemporaryDirectory() as d:
            sh = write(d, "a.sh", "set -e\nbuild() {\n  make\n}\nclean() {\n  rm x\n}\n")
            md = write(d, "a.md", "# Top\ntext\n## Sub\nmore\n# Next\n")
            js = write(d, "a.js", "export function go() {\n  return 1\n}\nclass K {\n}\n")
            self.assertEqual([(a, b, n) for a, b, _, n in outline.regex_symbols(Path(sh).read_text().splitlines())], [(2, 4, "build"), (5, 7, "clean")])
            self.assertEqual([(a, b, n) for a, b, _, n in outline.regex_symbols(Path(md).read_text().splitlines())], [(1, 2, "Top"), (3, 4, "Sub"), (5, 5, "Next")])
            self.assertEqual([(a, n) for a, b, _, n in outline.symbols(js)], [(1, "go"), (4, "K")])

    def test_syntax_error_falls_back_and_unreadable_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "bad.py", "def ok():\n    pass\ndef broken(:\n")
            self.assertTrue(any(n == "ok" for *_, n in outline.symbols(p)))
            self.assertEqual(outline.main([os.path.join(d, "missing.py")]), 1)

    def test_bytes_read_cut_on_real_files(self):
        # reading the map plus the one wanted symbol must be far smaller than reading the whole file
        cases = [(".claude/skills/agentic-ceo/scripts/token_report.py", "orchestration_actions"),
                 (".claude/skills/deep-code-review/scripts/outline.py", "ctags_symbols")]
        for rel, sym in cases:
            p = ROOT / rel
            syms = outline.symbols(str(p))
            a, b = next((a, b) for a, b, _, n in syms if n == sym)
            lines = p.read_bytes().splitlines(keepends=True)
            after = len("\n".join(f"{rel}:{x}-{y} {k} {n}" for x, y, k, n in sorted(syms))) + sum(map(len, lines[a - 1:b]))
            self.assertLess(after, p.stat().st_size * 0.5, rel)


if __name__ == "__main__":
    unittest.main()
