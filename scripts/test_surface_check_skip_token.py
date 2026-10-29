#!/usr/bin/env python3
"""surface_check.py `checks`: a head commit message with a CI-skip token explains a head that has zero check runs.

GitHub skips every push/pull_request workflow when the PR head commit message holds a skip token anywhere (a bare prose mention
counts), so a green-checks merge gate refuses the PR forever. The verdict must be a terminal FAIL naming the token, never the
"wait and re-check" COULD_NOT_CHECK. Hermetic: a fake `gh` replaces the forge; no network.
"""
import json
import sys
import unittest
from pathlib import Path

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/surface_check.py"
sys.path.insert(0, str(SC.parent))
import surface_check as sc  # noqa: E402

SHA = "a" * 40


def run(name, state="completed", conclusion="success"):
    return {"id": 1, "name": name, "status": state, "conclusion": conclusion if state == "completed" else None,
            "completed_at": "2026-10-29T10:00:00Z" if state == "completed" else None, "head_sha": SHA}


class SkipToken(unittest.TestCase):
    def check(self, runs, message, required=(), commit_rc=0):
        """check_checks against a fake forge: (code, reason, number of commit-message reads)."""
        reads = []

        def fake(args, timeout):
            if args[2].endswith(f"/commits/{SHA}"):
                reads.append(args)
                return commit_rc, json.dumps({"commit": {"message": message}}) if message is not None else "not json", ""
            return 0, json.dumps({"total_count": len(runs), "check_runs": runs}), ""

        saved, sc._gh = sc._gh, fake
        try:
            code, _, why = sc.check_checks("acme/app", SHA, list(required), 5)
        finally:
            sc._gh = saved
        return code, why, len(reads)

    def test_zero_check_runs_with_token_in_body_is_a_terminal_fail(self):
        code, why, _ = self.check([], "train: land\n\nthe convention is to add [skip ci] to merges")
        self.assertEqual(code, sc.FAIL, why)
        self.assertIn("'[skip ci]'", why)
        self.assertIn("Push a new commit with a clean message", why)
        self.assertIn("likely cause", why)  # not certain: no CI on the ref or path filters also leave zero runs
        self.assertIn("path filters", why)

    def test_required_names_all_missing_with_token_is_a_terminal_fail(self):
        code, why, _ = self.check([], "wip [ci skip]", required=["test", "lint"])
        self.assertEqual(code, sc.FAIL, why)
        self.assertIn("2 NO-RUN", why)

    def test_every_github_token_and_the_trailer_match(self):
        for tok in ("[skip ci]", "[ci skip]", "[no ci]", "[skip actions]", "[actions skip]"):
            with self.subTest(tok=tok):
                self.assertEqual(self.check([], f"msg {tok}")[0], sc.FAIL)
        for msg in ("msg\n\n\nskip-checks: true", "msg\n\n\nskip-checks:true\n", "msg\n\n\nSigned-off-by: A <a@example.com>\nskip-checks: true"):
            with self.subTest(msg=msg):
                self.assertEqual(self.check([], msg)[0], sc.FAIL)

    def test_clean_message_keeps_the_wait_verdict(self):
        # The docs do not say matching ignores case (so [SKIP CI] is not matched) and place the trailer last, after two empty lines.
        for msg in ("fix: reword the skip ci marker", "skip-checks: false", "mention skip-checks: true mid-line", "msg [SKIP CI]",
                    "msg\n\nskip-checks: true", "msg\n\n\nskip-checks: true\n\nmore text", "msg\n\n\nskip-checks: true\nSigned-off-by: A"):
            with self.subTest(msg=msg):
                self.assertEqual(self.check([], msg)[0], sc.COULD_NOT_CHECK)

    def test_unreadable_commit_read_adds_nothing(self):
        self.assertEqual(self.check([], "[skip ci]", commit_rc=1)[0], sc.COULD_NOT_CHECK)
        self.assertEqual(self.check([], None)[0], sc.COULD_NOT_CHECK)

    def test_any_real_run_keeps_the_plain_verdict_and_skips_the_read(self):
        code, _, reads = self.check([run("test", "in_progress")], "[skip ci]")
        self.assertEqual((code, reads), (sc.COULD_NOT_CHECK, 0))
        code, _, reads = self.check([run("test")], "[skip ci]")
        self.assertEqual((code, reads), (sc.PASS, 0))
        code, _, reads = self.check([run("lint")], "[skip ci]", required=["test", "lint"])  # lint ran: not a skipped head
        self.assertEqual((code, reads), (sc.COULD_NOT_CHECK, 0))
        # --require with the required name unrun while an unrelated check passed: a run exists, so no skip verdict
        code, _, reads = self.check([run("lint")], "[skip ci]", required=["test"])
        self.assertEqual((code, reads), (sc.COULD_NOT_CHECK, 0))

    def test_cli_exit_is_1_for_a_skipped_head(self):
        saved = sc._gh
        sc._gh = lambda args, t: (0, json.dumps({"commit": {"message": "x [no ci]"}}) if "/commits/" in args[2]
                                  else json.dumps({"total_count": 0, "check_runs": []}), "")
        try:
            self.assertEqual(sc.main(["checks", "--gh-repo", "acme/app", "--sha", SHA]), 1)
        finally:
            sc._gh = saved


if __name__ == "__main__":
    unittest.main()
