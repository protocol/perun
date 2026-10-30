#!/usr/bin/env python3
"""comms_lint._blank_comments and _sections: HTML comments are blanked in linear time. A terminated `<!-- ... -->` becomes
its newlines (line numbers stay put), an unterminated `<!--` stays as written, and a body of thousands of unterminated
`<!--` is handled at once (the earlier `re.sub(r"<!--.*?-->")` rescanned to the end of the text from each one: quadratic).
Synthetic input only; no network."""
import random
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/communication-structure/scripts"))
import comms_lint as L  # noqa: E402


def oracle(text):
    """The earlier implementation: the spec for what counts as a comment."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group().count("\n"), text, flags=re.DOTALL)


class BlankComments(unittest.TestCase):
    def test_matches_the_regex_it_replaced_on_random_text(self):
        rnd = random.Random(7)
        toks = ["<!--", "-->", "<!-->", "<!---->", "--", "->", "<!-", "\n", "x", " ", "#"]
        for _ in range(3000):
            text = "".join(rnd.choices(toks, k=rnd.randint(0, 14)))
            self.assertEqual(L._blank_comments(text), oracle(text), text)

    def test_edge_forms(self):
        for text, want in (("a<!-- x -->b", "ab"), ("a<!---->b", "ab"), ("a<!-->b", "a<!-->b"), ("a<!-- never closed", "a<!-- never closed"),
                           ("<!-- x\ny\nz -->", "\n\n"), ("<!-- 1 --><!-- 2 -->", "")):
            self.assertEqual(L._blank_comments(text), want, text)

    def test_sections_drop_a_comment_but_keep_line_numbers(self):
        got = L._sections("## A\n<!-- hint\nspans lines -->\nbody\n## B\ntext\n")
        self.assertEqual(got["a"][1], [(2, ""), (3, ""), (4, "body")])
        self.assertEqual(got["b"], (5, [(6, "text")]))

    def test_sections_keep_an_unterminated_comment_as_content(self):
        self.assertEqual(L._sections("## A\n<!-- never closed\nbody\n")["a"][1], [(2, "<!-- never closed"), (3, "body")])

    def test_many_unterminated_comments_finish_at_once(self):
        text = "## A\nOne real line about 3 files.\n" + "<!--\n" * 12_000  # about 60 KB; the earlier regex needed several seconds here
        t0 = time.perf_counter()
        L._sections(text)
        L.lint("audit-pr", text)
        self.assertLess(time.perf_counter() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()
