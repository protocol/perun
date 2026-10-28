"""flow_alarm.py: stop-starting hook, one symptom alarm, value-stream split."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/flow_alarm.py"
GREEN = {"isDraft": False, "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
RED = {"isDraft": False, "statusCheckRollup": [{"conclusion": "FAILURE"}]}
DRAFT = {"isDraft": True, "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
NOW = 1_800_000_000


def run(args, open_prs=(), merged=(), stdin="", fail=False, env=None):
    d = tempfile.mkdtemp()
    pathlib.Path(d, "open.json").write_text(json.dumps(list(open_prs)))
    pathlib.Path(d, "merged.json").write_text(json.dumps(list(merged)))
    gh = pathlib.Path(d, "gh")
    gh.write_text(f'#!/bin/sh\n[ {int(fail)} -eq 1 ] && exit 1\ncase "$*" in *"--state open"*) cat {d}/open.json;; '
                  f'*"--state merged"*) cat {d}/merged.json;; esac\n')
    gh.chmod(0o755)
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--now", str(NOW)], input=stdin, capture_output=True, text=True,
                          env={**os.environ, "PERUN_GH": str(gh), **(env or {})})


def hook(cmd, ready, env=None):
    return run([], [GREEN] * ready, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}), env=env)


class T(unittest.TestCase):
    def test_hook_blocks_pr_create_at_threshold(self):
        r = hook("gh pr create --title x", 5)
        self.assertEqual(r.returncode, 2)
        self.assertIn("5 ready-but-unmerged", r.stderr)

    def test_hook_allows_below_threshold_priority_and_other_commands(self):
        self.assertEqual(hook("gh pr create --title x", 4).returncode, 0)
        self.assertEqual(hook("gh pr create --title x # priority: red trunk fix", 9).returncode, 0)
        self.assertEqual(hook("gh pr list", 9).returncode, 0)
        self.assertEqual(hook("gh pr create", 2, {"PERUN_STOP_STARTING_READY": "2"}).returncode, 2)

    def test_hook_gh_timeout_degrades_with_notice(self):
        import importlib.util
        import unittest.mock as m
        spec = importlib.util.spec_from_file_location("fa", SCRIPT)
        fa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fa)
        seen = []

        def slow(*a, timeout=60):
            seen.append(timeout)
            raise subprocess.TimeoutExpired("gh", timeout)
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create"}})
        with m.patch.object(fa, "gh_json", slow), m.patch("sys.stdin", __import__("io").StringIO(stdin)), \
                m.patch("sys.stderr", __import__("io").StringIO()) as err:
            self.assertEqual(fa.hook(), 0)
        self.assertEqual(seen, [10])
        self.assertIn("timed out", err.getvalue())

    def test_hook_fails_open(self):
        self.assertEqual(run([], fail=True, stdin='{"tool_input":{"command":"gh pr create"}}').returncode, 0)
        self.assertEqual(run([], stdin="garbage").returncode, 0)

    def test_draft_and_red_prs_are_not_ready(self):
        r = run([], [GREEN, RED, DRAFT] * 3, stdin='{"tool_input":{"command":"gh pr create"}}',
                env={"PERUN_STOP_STARTING_READY": "4"})
        self.assertEqual(r.returncode, 0)  # 3 ready < 4

    def test_symptom_ready_but_nothing_landed(self):
        r = run(["symptom"], [GREEN], [{"mergedAt": "2027-01-15T05:00:00Z"}])  # epoch 1.8e9 = 2027-01-15T08:00:00Z
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM flow: 1 ready PR(s) and nothing merged in 3.0h\n"))

    def test_symptom_healthy_cases(self):
        self.assertEqual(run(["symptom"], [GREEN], [{"mergedAt": "2027-01-15T07:30:00Z"}]).returncode, 0)
        self.assertEqual(run(["symptom"], [], [{"mergedAt": "2020-01-01T00:00:00Z"}]).returncode, 0)  # idle, not stuck

    def test_symptom_trunk_red_and_fail_closed(self):
        r = run(["symptom", "--red-since", str(NOW - 7200)], [], [{"mergedAt": "2027-01-15T07:30:00Z"}])
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM flow: trunk red for 2.0h\n"))
        self.assertEqual(run(["symptom"], fail=True).returncode, 2)

    def test_split_prints_medians_and_largest(self):
        f = pathlib.Path(tempfile.mkdtemp(), "v.json")
        row = {"queuedAt": "2027-01-01T00:00:00Z", "startedAt": "2027-01-01T10:00:00Z",
               "readyAt": "2027-01-01T12:00:00Z", "mergedAt": "2027-01-01T13:00:00Z"}
        f.write_text(json.dumps([row, {"queuedAt": "2027-01-01T00:00:00Z"}]))
        r = run(["split", str(f)])
        self.assertEqual(r.returncode, 0)
        self.assertIn("waiting-to-start\tmedian_h=10.0", r.stdout)
        self.assertIn("largest\twaiting-to-start\trows=1", r.stdout)

    def test_split_bad_input_exit_2(self):
        f = pathlib.Path(tempfile.mkdtemp(), "v.json")
        f.write_text("[]")
        self.assertEqual(run(["split", str(f)]).returncode, 2)
        self.assertEqual(run(["bogus"]).returncode, 2)


if __name__ == "__main__":
    unittest.main()
