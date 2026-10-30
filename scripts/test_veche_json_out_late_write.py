#!/usr/bin/env python3
"""veche.py --json-out: a path that is writable when the council starts but not when it ends (here a seat swaps the file for a
directory) is reported on stderr like the early check, with exit 2 and no traceback; the record is still printed on stdout.
Stdlib only."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VECHE = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts/veche.py"
SEAT = '''import json, os, sys
sys.stdin.read()
out, mode = sys.argv[1], sys.argv[2]
if mode == "swap":  # the early check left an empty file here; make the final write fail
    for step in (lambda: os.remove(out), lambda: os.mkdir(out)):
        try:
            step()
        except OSError:
            pass
print(json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w"}))
'''


def council(mode):
    """(result, json-out path) for a two-seat council whose seats run in `mode`: swap or keep."""
    d = Path(tempfile.mkdtemp())
    out = d / "rec.json"
    (d / "seat.py").write_text(SEAT)
    r = subprocess.run([sys.executable, str(VECHE), "--cmd", f"{sys.executable} {d / 'seat.py'} {out} {mode}", "--claim", "c",
                        "--steelman", "s", "--root", str(d), "--review-date", "2030-01-31", "--lenses", "skeptic,better-way",
                        "--json-out", str(out)], capture_output=True, text=True, timeout=60)
    return r, out


class LateWrite(unittest.TestCase):
    def test_a_path_that_stops_being_writable_is_reported_not_a_traceback(self):
        r, out = council("swap")
        self.assertTrue(out.is_dir())
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(f"--json-out: cannot write {out}", r.stderr)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "REVISE")  # the record is printed before the write

    def test_a_writable_path_still_gets_the_record(self):
        r, out = council("keep")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(out.read_text()), json.loads(r.stdout))


if __name__ == "__main__":
    unittest.main()
