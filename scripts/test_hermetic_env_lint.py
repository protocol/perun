#!/usr/bin/env python3
"""Tests for hermetic_env_lint.py: an unpinned test of a host-reading script fails; a pinned one, a baselined one pass; the repo is clean."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hermetic_env_lint as h  # noqa: E402


def tree(tests, baseline=""):
    d = Path(tempfile.mkdtemp())
    (d / "scripts").mkdir()
    (d / "scripts/probe.py").write_text("import os\nn = os.cpu_count()\n")
    (d / "scripts/hermetic-env-baseline.tsv").write_text(baseline)
    for name, body in tests.items():
        (d / "scripts" / name).write_text(body)
    return str(d)


class Lint(unittest.TestCase):
    def test_unpinned_fails_pinned_passes(self):
        r = tree({"test_a.py": "import probe\n", "test_b.py": "import probe\nenv = {'PERUN_GATE_CORES': '4'}\n"})
        self.assertEqual(h.lint(r), (["scripts/test_a.py"], []))

    def test_comment_is_not_a_pin(self):
        self.assertEqual(h.lint(tree({"test_a.py": "import probe\n# export unset env = scrub_env\n"}))[0], ["scripts/test_a.py"])

    def test_baseline_row_exempts_then_goes_stale_once_pinned(self):
        self.assertEqual(h.lint(tree({"test_a.py": "import probe\n"}, "scripts/test_a.py\n")), ([], []))
        self.assertEqual(h.lint(tree({"test_a.py": "import probe\nscrub_env\n"}, "scripts/test_a.py\n")), ([], ["scripts/test_a.py"]))

    def test_missing_baseline_fails_closed(self):
        r = tree({})
        os.remove(os.path.join(r, "scripts/hermetic-env-baseline.tsv"))
        with self.assertRaises(OSError):
            h.lint(r)

    def test_repo_is_clean(self):
        p = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/hermetic_env_lint.py"), str(ROOT)], capture_output=True, text=True,
                           env={"PATH": os.environ["PATH"]})
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
