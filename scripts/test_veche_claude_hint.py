#!/usr/bin/env python3
"""A malformed `claude` seat reply without --setting-sources gets a hint naming the flag. Stdlib only."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

VECHE = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts/veche.py"


def dropped(cmd, path):
    """Run veche over `cmd` (PATH prefixed with `path`); -> the dropped-seat reasons."""
    d = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, str(VECHE), "--cmd", cmd, "--claim", "c", "--steelman", "s", "--root", d,
                        "--review-date", "2030-01-31"], capture_output=True, text=True,
                       env={**os.environ, "PATH": path + os.pathsep + os.environ["PATH"]})
    return [x[1] for x in json.loads(r.stdout)["dropped"]]


class ClaudeHint(unittest.TestCase):
    def test_hint_only_for_claude_without_the_flag(self):
        d = tempfile.mkdtemp()
        fake = Path(d) / "claude"
        fake.write_text("#!/bin/sh\necho not json\n")
        fake.chmod(0o755)
        for why in dropped("claude -p", d):
            self.assertIn("--setting-sources project", why)
        for why in dropped("claude -p --setting-sources project", d):
            self.assertNotIn("--setting-sources", why)
        other = Path(d) / "other"
        other.write_text("#!/bin/sh\necho not json\n")
        other.chmod(0o755)
        for why in dropped("other", d):
            self.assertNotIn("--setting-sources", why)


if __name__ == "__main__":
    unittest.main()
