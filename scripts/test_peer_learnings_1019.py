#!/usr/bin/env python3
"""Regression tests for two field-reported bugs: destructive_guard blocked the read-only `kill -0`, and a normal
`install.sh --apply-operating-layer` warned about a placeholder SubagentStop matcher."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import destructive_guard as dg  # noqa: E402


class KillSignalZero(unittest.TestCase):
    def test_signal_zero_allowed(self):
        for c in ("kill -0 $PID", "kill -s 0 $PID", "kill -0 4242", 'kill -0 "$(cat run.pid)"', "kill -0 $PID && echo up",
                  "kill -0 ${PID}", "kill -0 -- $PID", 'kill -s 0 "$PID"'):
            self.assertFalse(dg.check(c), c)

    def test_real_signals_still_blocked(self):
        for c in ("kill -9 $PID", "kill $PID", "kill -s 9 $PID", "kill -0 $PID && kill -9 $PID", "kill -9 $(pgrep -f x)",
                  "kill -0 -s 9 $PID", "kill -s 0 -s 9 $PID", "kill -s 0 -9 $PID",
                  "kill -0 $S $PID", "kill -0 $(echo -9) $PID", "kill -0 $(pgrep x)",
                  "kill -0 {-s,9,$PID}", "kill -s 0 {-s,9,$PID}", "kill -0 -- {-s,9,$PID}", "kill -0 $P*",
                  "pkill -0 node"):
            self.assertTrue(dg.check(c), c)

    def test_regex_fallback_matches(self):
        # an unbalanced quote forces the regex fallback
        self.assertFalse(dg.check('echo "x; kill -0 $PID'))
        self.assertTrue(dg.check('echo "x; kill -9 $PID'))
        for c in ('echo "x; kill -0 -s 9 $PID', 'echo "x; kill -s 0 -9 $PID', 'echo "x; kill -0 2>&1 -9 $PID',
                  'echo "x; kill -0 $S $PID',
                  'echo "x; kill -0 {-s,9,$PID}'):
            self.assertTrue(dg.check(c), c)


@unittest.skipUnless(shutil.which("jq"), "install.sh --apply-operating-layer needs jq")
class FreshInstallSubagentStop(unittest.TestCase):
    def test_no_placeholder_warning_and_cap_wired(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / ".claude").mkdir()
            (Path(t) / ".claude/settings.local.json").write_text("{}")
            r = subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", "--apply-operating-layer", t],
                               capture_output=True, text=True)
            self.assertNotIn("placeholder", r.stderr)
            s = json.loads((Path(t) / ".claude/settings.local.json").read_text())
            stop = s["hooks"]["SubagentStop"]
            self.assertTrue(any("handback_cap.py" in h["command"] for e in stop for h in e["hooks"]))
            self.assertFalse(any("<" in e.get("matcher", "") for e in stop))
            sc = subprocess.run([sys.executable, str(SC / "operating_selfcheck.py"), "--settings",
                                 str(Path(t) / ".claude/settings.local.json")], capture_output=True, text=True)
            line = next(x for x in (sc.stdout + sc.stderr).splitlines() if "handback-cap-two-tier" in x)
            self.assertIn("PRESENT", line)

if __name__ == "__main__":
    unittest.main()
