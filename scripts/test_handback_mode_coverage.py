#!/usr/bin/env python3
"""handback.py mode coverage: a --body-file findings claim for a review mode needs a ran/NOT RUN entry. Reuses test_handback.py's fixture."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_handback as th  # noqa: E402


class Mode(unittest.TestCase):
    setUp, tearDown, git, commit, hb = (th.T.__dict__[n] for n in ("setUp", "tearDown", "git", "commit", "hb"))

    def run_body(self, text):
        self.git("checkout", "-q", "-b", "lane")
        self.commit("changelog.d/x.md", "### Added\n- x\n", "frag")
        sha = self.commit("work.txt", "w\n", "work\n\nTests: 1/1")
        body = self.d / "body.md"
        body.write_text(text)
        return self.hb(sha, "--body-file", str(body))

    def test_unbacked_claim_is_red(self):
        r = self.run_body("security 0 new\nCoverage: perf: ran (4 files)\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("handback RED: mode coverage", r.stdout)
        self.assertIn("mode 'security' with no coverage entry", r.stdout)

    def test_backed_claim_is_green(self):
        r = self.run_body("security 0 new\nCoverage: security: ran (12 files)\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_body_file_is_unchecked(self):
        self.git("checkout", "-q", "-b", "lane")
        self.commit("changelog.d/x.md", "### Added\n- x\n", "frag")
        self.assertEqual(self.hb(self.commit("work.txt", "w\n", "work\n\nTests: 1/1")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
