#!/usr/bin/env python3
"""veche.py documents what the code does. The --json-out help states the directory rule of its temp-file-then-os.replace write: a
read-only file in a writable directory is replaced (its mode kept), a read-only directory exits 2 even when the file itself is
writable. council.md says the `scores` map may sit in the verdict object, which is where the seat prompt asks for it. Stdlib only."""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic"
sys.path.insert(0, str(SK / "scripts"))
import veche  # noqa: E402

BASE = ["--cmd", "true", "--claim", "c", "--steelman", "s", "--review-date", "2030-01-31", "--progress-s", "0", "--dry-run"]
ENV = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {"COLUMNS": "10000", "NO_COLOR": "1", "PYTHON_COLORS": "0"}


def run(out):
    """(exit code, stderr) of an in-process veche.main --dry-run that writes its record to `out`."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = veche.main([*BASE, "--json-out", str(out)])
        except SystemExit as e:
            code = e.code
    return code, stderr.getvalue()


class JsonOutDirectoryRule(unittest.TestCase):
    def test_the_help_states_the_rule(self):
        text = subprocess.run([sys.executable, str(SK / "scripts/veche.py"), "--help"], capture_output=True, text=True, env=ENV).stdout
        text = " ".join(text.split())
        for phrase in ("The directory must be writable", "a read-only file in it is replaced", "a read-only directory or a bind-mounted file"):
            self.assertIn(phrase, text)

    def test_a_read_only_file_in_a_writable_directory_is_replaced_and_keeps_its_mode(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "rec.json"
            out.write_text("stale")
            out.chmod(0o444)
            self.assertEqual(run(out)[0], 0)
            self.assertEqual(json.loads(out.read_text())["verdict"], "DRY_RUN")
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o444)

    @unittest.skipIf(os.geteuid() == 0, "root writes into a read-only directory")
    def test_a_read_only_directory_exits_2_even_for_a_writable_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "rec.json"
            out.write_text("stale")
            os.chmod(d, 0o555)
            try:
                code, err = run(out)
            finally:
                os.chmod(d, 0o755)  # so the temp directory can be removed
            self.assertEqual(code, 2)
            self.assertIn(f"--json-out: cannot write {out}: Permission denied", err)
            self.assertEqual(out.read_text(), "stale")


class ScoresPlacement(unittest.TestCase):
    def test_council_md_says_the_verdict_object_may_carry_the_scores(self):
        text = " ".join((SK / "references/council.md").read_text(encoding="utf-8").split())
        self.assertIn("the `scores` map may sit under `scores` in that object, or in any other object (bare or under `scores`)", text)


if __name__ == "__main__":
    unittest.main()
