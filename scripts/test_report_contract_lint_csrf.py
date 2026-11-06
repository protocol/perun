#!/usr/bin/env python3
"""Tests: report_contract_lint.py csrf disposition on cookie/session state-changing inventory rows (inventory-no-csrf, csrf-unfiled)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LINT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/report_contract_lint.py"
SRC = "\n".join(f"line{i}" for i in range(1, 31)) + "\n"
HEAD = "# Audit\n\n## Per-standard table\n| Item | Status | Basis | Files | Negative |\n|---|---|---|---|---|\n| A3 | not-checked | tool:zap | | |\n"
MID = "\n## NOT CHECKED\n- A3: needs runtime\n\n## NOT RUN\n- zap: no running target\n\n## Static vs runtime\nNeeds a deployed system.\n\n## Dependencies\nLockfile read.\n\n"
MSG = "file a [csrf] finding at the line that commits the change (name the route path), or name the defence in csrf="


def lint(inv, findings="", other=False):
    text = HEAD + (f"\n## Findings\n{findings}\n" if findings else "") + MID + "## Route inventory\n" + inv
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "src").mkdir()
        (Path(d) / "src/app.py").write_text(SRC)
        (Path(d) / "src/other.py").write_text(SRC)
        r = Path(d) / "report.md"
        r.write_text(text)
        p = subprocess.run([sys.executable, str(LINT), str(r), "--root", d], capture_output=True, text=True)
        return p.returncode, p.stdout


class Csrf(unittest.TestCase):
    def test_missing_field(self):
        rc, out = lint("- POST /a src/app.py:5 auth=cookie rate-limit=no\n")
        self.assertEqual(rc, 1)
        self.assertIn("inventory-no-csrf", out)

    def test_none_without_finding(self):
        rc, out = lint("- DELETE /a src/app.py:5 auth=session rate-limit=no csrf=none\n")
        self.assertEqual(rc, 1)
        self.assertIn("csrf-unfiled", out)
        self.assertIn(MSG, out)

    def test_none_with_finding_by_path(self):
        f = "- [csrf] src/app.py:20 high: POST /a commits the change with no token.\n"
        self.assertEqual(lint("- POST /a src/app.py:5 auth=cookie rate-limit=no csrf=none\n", f)[0], 0)

    def test_none_with_finding_by_span(self):
        inv = "- PUT /a src/app.py:5 auth=Session-Cookie rate-limit=no csrf=none\n- GET /b src/app.py:15 auth=none rate-limit=no csrf=n/a\n"
        self.assertEqual(lint(inv, "- [csrf] src/app.py:9 high: state change without a token.\n")[0], 0)

    def test_finding_for_other_route_does_not_clear(self):
        inv = "- PATCH /a src/app.py:5 auth=cookie rate-limit=no csrf=none\n- POST /b src/app.py:15 auth=cookie rate-limit=no csrf=none\n"
        rc, out = lint(inv, "- [csrf] src/app.py:20 high: state change without a token.\n")
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("csrf-unfiled"), 1)
        self.assertIn("PATCH /a", out)

    def test_bearer_and_get_exempt(self):
        inv = "- POST /a src/app.py:5 auth=bearer rate-limit=no\n- GET /b src/app.py:15 auth=cookie rate-limit=no\n"
        self.assertEqual(lint(inv)[0], 0)

    def test_defence_value_clears(self):
        for v in ("token", "origin", "samesite", "n/a"):
            with self.subTest(v=v):
                self.assertEqual(lint(f"- POST /a src/app.py:5 auth=cookie rate-limit=no csrf={v}\n")[0], 0)

    def test_path_only_clear_from_other_file(self):
        f = "- [csrf] src/app.py:25 high: POST /a commits the change with no token.\n"
        self.assertEqual(lint("- POST /a src/other.py:5 auth=cookie rate-limit=no csrf=none\n", f, other=True)[0], 0)

    def test_trailing_comma_on_route(self):
        f = "- [csrf] src/app.py:20 high: POST /a commits the change with no token.\n"
        self.assertEqual(lint("- POST /a, src/app.py:5 auth=cookie rate-limit=no csrf=none\n", f)[0], 0)

    def test_param_route_cleared_by_span(self):
        inv = "- POST /u/{id} src/app.py:5 auth=cookie rate-limit=no csrf=none\n"
        self.assertEqual(lint(inv, "- [csrf] src/app.py:7 high: state change without a token.\n")[0], 0)

    def test_numbered_and_bold_rows(self):
        for row in ("1. POST /a src/app.py:5 auth=cookie rate-limit=no csrf=none\n", "- **POST** /a `src/app.py:5` auth=cookie rate-limit=no\n"):
            with self.subTest(row=row):
                self.assertEqual(lint(row)[0], 1)

    def test_none_variants(self):
        for v in ("NONE.", "no", "Off", '"false"', "disabled", "missing", "absent"):
            with self.subTest(v=v):
                self.assertIn("csrf-unfiled", lint(f"- POST /a src/app.py:5 auth=cookie rate-limit=no csrf={v}\n")[1])

    def test_subheading_stays_in_inventory(self):
        inv = "### Admin\n- POST /a src/app.py:5 auth=cookie rate-limit=no\n"
        self.assertIn("inventory-no-csrf", lint(inv)[1])

    def test_dot_slash_normalized(self):
        inv = "- POST /a ./src/app.py:5 auth=cookie rate-limit=no csrf=none\n"
        self.assertEqual(lint(inv, "- [csrf] src/app.py:7 high: state change without a token.\n")[0], 0)
        inv = "- POST /a src/app.py:5 auth=cookie rate-limit=no csrf=none\n"
        self.assertEqual(lint(inv, "- [csrf] ./src/app.py:7 high: state change without a token.\n")[0], 0)


if __name__ == "__main__":
    unittest.main()
