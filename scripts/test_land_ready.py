#!/usr/bin/env python3
"""review_status.py and land_ready.py: offline, `gh` is a stub on PATH answering by endpoint from $FAKE/<kind>.json."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
HEAD = "b" * 40
STUB = """#!/bin/sh
echo "$*" >> "$FAKE/calls.log"
for a in "$@"; do [ "$prev" = --input ] && cp "$a" "$FAKE/body.json"; prev=$a; done
case "$*" in
  *graphql*) f=graphql ;;
  *check-runs*) f=checks ;;
  *"-X POST"*) f=post ;;
  */status*) f=status ;;
  */pulls*) f=pulls ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
cat "$FAKE/$f.json" 2>/dev/null || { echo "fake gh: no $f.json" >&2; exit 1; }
"""


def gql(**kw):
    pr = {"state": "OPEN", "isDraft": False, "headRefOid": HEAD, "baseRefName": "main", "mergeable": "MERGEABLE",
          "mergeStateStatus": "CLEAN", "reviewDecision": None, "labels": {"nodes": []}}
    pr.update(kw)
    return {"data": {"repository": {"pullRequest": pr}}}


def runs(conclusion="success"):
    return {"total_count": 1, "check_runs": [{"id": 1, "name": "unit", "status": "completed", "conclusion": conclusion,
            "head_sha": HEAD, "completed_at": "2026-01-01T00:00:00Z", "app": {"id": 1}, "check_suite": {"id": 1}}]}


class T(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = Path(self.t.name)
        gh = self.d / "gh"
        gh.write_text(STUB)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.env = {**os.environ, "PATH": f"{self.d}{os.pathsep}{os.environ['PATH']}", "FAKE": str(self.d)}
        for var in ("GH_TOKEN", "GITHUB_TOKEN"):
            self.env.pop(var, None)

    def tearDown(self):
        self.t.cleanup()

    def run_py(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--repo", "acme/widgets"], env=self.env,
                              cwd=self.d, capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def feed(self, **kinds):
        for k, v in kinds.items():
            (self.d / f"{k}.json").write_text(json.dumps(v))

    def ready_line(self, graphql=None, checks=None, status=None):
        self.feed(pulls=[{"number": 7, "head": {"sha": HEAD}}], graphql=graphql or gql(), checks=checks or runs(),
                  status=status if status is not None else {"statuses": [{"context": "perun/review", "state": "success"}]})
        r = self.run_py("land_ready.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_post_success_and_failure(self):
        self.feed(post={})
        for red, state in ((0, "success"), (2, "failure")):
            r = self.run_py("review_status.py", "--sha", HEAD, "--red", str(red))
            self.assertEqual(r.returncode, 0, r.stderr)
            body = json.loads((self.d / "body.json").read_text())
            self.assertEqual((body["state"], body["context"]), (state, "perun/review"))
            self.assertIn(f"repos/acme/widgets/statuses/{HEAD}", (self.d / "calls.log").read_text())

    def test_dry_run_posts_nothing(self):
        r = self.run_py("review_status.py", "--sha", HEAD, "--red", "0", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY-RUN", r.stdout)
        self.assertFalse((self.d / "calls.log").exists())

    def test_bad_args_and_failed_post(self):
        self.assertEqual(self.run_py("review_status.py", "--sha", "abc", "--red", "0").returncode, 3)
        self.assertEqual(self.run_py("review_status.py", "--sha", HEAD, "--red", "-1").returncode, 3)
        self.assertEqual(self.run_py("review_status.py", "--sha", HEAD, "--red", "0").returncode, 1)  # no post.json: stub fails

    def test_ready(self):
        self.assertEqual(self.ready_line(), "#7 ready")

    def test_each_blocker_is_named(self):
        cases = (("draft", dict(graphql=gql(isDraft=True)), "draft"),
                 ("conflict", dict(graphql=gql(mergeable="CONFLICTING")), "merge conflict"),
                 ("unknown", dict(graphql=gql(mergeable="UNKNOWN")), "mergeable unknown"),
                 ("behind", dict(graphql=gql(mergeStateStatus="BEHIND")), "behind base"),
                 ("checks", dict(checks=runs("failure")), "checks:"),
                 ("no status", dict(status={"statuses": []}), "perun/review missing on current head"),
                 ("failed review", dict(status={"statuses": [{"context": "perun/review", "state": "failure"}]}),
                  "perun/review failure"),
                 ("other context only", dict(status={"statuses": [{"context": "ci", "state": "success"}]}), "missing"))
        for label, kw, want in cases:
            with self.subTest(label):
                line = self.ready_line(**kw)
                self.assertTrue(line.startswith("#7 not ready: "), line)
                self.assertIn(want, line)

    def test_status_read_asks_for_100(self):
        self.ready_line()
        self.assertIn("/status?per_page=100", (self.d / "calls.log").read_text())

    def test_warns_at_100_prs(self):
        self.feed(pulls=[{"number": n, "head": {"sha": HEAD}} for n in range(100)], graphql=gql(), checks=runs(),
                  status={"statuses": []})
        self.assertIn("warning", self.run_py("land_ready.py").stderr)

    def test_list_failure_is_exit_3(self):
        self.assertEqual(self.run_py("land_ready.py").returncode, 3)


if __name__ == "__main__":
    unittest.main()
