"""flake_ledger quarantine: each entry carries a ticket and expiry; a full list exits 1 (and can file a P0 issue)."""
import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import flake_ledger as fl  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name
        self.addCleanup(self._t.cleanup)
        for t in ("t1", "t2", "t3"):
            self.cli("record", "--tree", t, stdin="".join(f"FAIL x{i}\nPASS x{i}\n" for i in range(3)))

    def cli(self, *args, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            rc = fl.main(["--dir", self.d, "--today", "2026-10-16", *args])
        return rc, out.getvalue()

    def test_ticket_is_stored_printed_and_missing_ticket_flagged(self):
        rc, out = self.cli("quarantine", "--ticket", "T-9")
        self.assertEqual(rc, 0)
        self.assertIn("QUARANTINE x0 expires=2026-10-30 ticket=T-9", out)
        self.assertNotIn("NO-TICKET", self.cli("report")[1])
        self.assertIn("expires=2026-10-30\tNO-TICKET", self._ticketless())

    def _ticketless(self):
        import json
        q = Path(self.d) / "quarantine.json"
        data = json.loads(q.read_text())
        data["x0"].pop("ticket")
        q.write_text(json.dumps(data))
        return self.cli("report")[1]

    def test_full_list_exits_1_and_names_the_cap(self):
        rc, out = self.cli("quarantine", "--max", "2")
        self.assertEqual(rc, 1)
        self.assertIn("FULL quarantine list: 3 > 2", out)

    def test_full_list_files_p0_issue_when_asked(self):
        bindir = tempfile.mkdtemp()
        log = os.path.join(bindir, "args")
        gh = Path(bindir, "gh")
        gh.write_text(f'#!/bin/sh\necho "$@" > {log}\necho https://example.com/issues/1\n')
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"PATH": f"{bindir}:{os.environ['PATH']}"}):
            rc, out = self.cli("quarantine", "--max", "2", "--file-issue")
        self.assertEqual(rc, 1)
        self.assertIn("https://example.com/issues/1", out)
        self.assertIn("--label P0", Path(log).read_text())

    def test_under_cap_exit_0(self):
        self.assertEqual(self.cli("quarantine", "--max", "3")[0], 0)


if __name__ == "__main__":
    unittest.main()
