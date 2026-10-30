#!/usr/bin/env python3
"""veche.py --json-out failing at the end of the run: the record is already printed, so a blocking verdict keeps its exit
(3 COULD_NOT_DECIDE, 4 NOT_CONVENED) and only an exit 0 becomes 2; the stderr message is the one the early check prints.
The failure is an os.replace (the atomic --json-out write) that works once (the early check) and then raises, run in-process. Stdlib only."""
import contextlib
import errno
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"))
import veche  # noqa: E402

BASE = ["--cmd", "true", "--claim", "c", "--steelman", "s", "--review-date", "2030-01-31", "--progress-s", "0"]
EXIT_OF = {  # verdict -> (extra args that produce it without calling a seat, exit code when the record is written)
    "DRY_RUN": (["--dry-run"], 0),
    "COULD_NOT_DECIDE": (["--max-calls", "0"], 3),
    "NOT_CONVENED": (["--stakes", "low", "--reversibility", "easy"], 4),
}


def late_failure(extra):
    """(exit code, record printed, stderr, write attempts) of veche.main with a --json-out whose first write works and later ones fail."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "rec.json"
        real, writes = os.replace, []

        def flaky(src, dst):
            writes.append(dst)
            if len(writes) > 1:
                raise OSError(errno.ENOSPC, "No space left on device")
            real(src, dst)

        o, e = io.StringIO(), io.StringIO()
        with mock.patch("os.replace", flaky), contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            try:
                code = veche.main([*BASE, *extra, "--json-out", str(out)])
            except SystemExit as x:
                code = x.code
        return code, json.loads(o.getvalue()), e.getvalue().replace(str(out), "OUT"), len(writes)


class LateWriteExit(unittest.TestCase):
    def test_a_failed_late_write_keeps_a_blocking_verdict_exit_and_turns_exit_0_into_2(self):
        for verdict, (extra, verdict_exit) in EXIT_OF.items():
            with self.subTest(verdict):
                code, rec, err, writes = late_failure(extra)
                self.assertEqual((rec["verdict"], writes), (verdict, 2))
                self.assertEqual(code, verdict_exit or 2, err)

    def test_the_message_is_the_early_check_message_for_every_verdict(self):
        for verdict, (extra, _) in EXIT_OF.items():
            err = late_failure(extra)[2]
            self.assertIn("error: --json-out: cannot write OUT: No space left on device", err, verdict)
            self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
