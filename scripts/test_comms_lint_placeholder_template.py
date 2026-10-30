#!/usr/bin/env python3
"""comms_lint placeholder rule: a mktemp template inside a single-backtick span on one line (`drain.XXXXXX`) is not a
placeholder, while TBD, TODO, <FILL>, <fill me>, [date] and a lone XXX in prose still are, even on a line that also carries a
template, and the same run in a double-backtick span or a span split across lines still is. Synthetic input only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/communication-structure/scripts"))
import comms_lint as L  # noqa: E402


def placeholders(text):
    """The text each placeholder hit matched, for `text` linted as a message."""
    res = L.lint("message", text)
    return [h["problem"].strip("'") for r in res["rules"] if r["rule"] == "placeholder" for h in r["hits"]]


class Templates(unittest.TestCase):
    def test_mktemp_template_in_a_code_span_passes(self):
        for text in ("Scratch lives in `drain.XXXXXX`.",
                     'Each run makes `mktemp -d "${TMPDIR:-/tmp}/drain.XXXXXX"` and removes it.',
                     "Run `mktemp XXXXXX` once.",
                     "Two dirs: `a.XXXXXX` and `b.XXXXXXXX`."):
            self.assertEqual(placeholders(text), [], text)

    def test_real_placeholders_still_fail(self):
        for text, want in (("Owner: TBD", "TBD"), ("TODO: name the file", "TODO"), ("Owner <FILL>", "<FILL>"), ("Owner <fill in>", "<fill in>"),
                           ("Owner <fill me>", "<fill me>"), ("Due [date]", "[date]"), ("Owner: XXX", "XXX"), ("ETA xxx", "xxx")):
            self.assertEqual(placeholders(text), [want], text)

    def test_a_template_does_not_hide_a_placeholder_on_its_line(self):
        for text, want in (("Owner: TBD; scratch is `drain.XXXXXX`.", "TBD"), ("ETA XXX, scratch is `drain.XXXXXX`.", "XXX"),
                           ("`drain.XXXXXX` TODO", "TODO"), ("`a.XXXXXX` and a bare XXX", "XXX")):
            self.assertEqual(placeholders(text), [want], text)

    def test_the_same_run_outside_a_code_span_still_fails(self):
        self.assertEqual(placeholders("Scratch lives in drain.XXXXXX."), ["XXXXXX"])
        self.assertEqual(placeholders("Scratch lives in `drain.XXXXXX and never closed."), ["XXXXXX"])  # no closing backtick: not a code span
        self.assertEqual(placeholders("Scratch lives in ``drain.XXXXXX``."), ["XXXXXX"])  # a double-backtick span is not exempt
        self.assertEqual(placeholders("Scratch lives in `drain.XXXXXX\nand is removed`."), ["XXXXXX"])  # nor is a span split across lines


if __name__ == "__main__":
    unittest.main()
