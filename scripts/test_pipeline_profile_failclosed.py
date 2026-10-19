"""pipeline_profile.py review fixes: a check counts as blocking only when proven, compare never keeps what it cannot
count, and a profile file is never left half-written."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / ".claude" / "skills" / "agentic-delivery" / "scripts"))
import pipeline_profile as pp  # noqa: E402
from test_pipeline_profile import write  # noqa: E402

HOOK = "#!/bin/sh\nbash scripts/unit.sh\n"


def repo(root, workflow):
    write(root, ".github/workflows/ci.yml", workflow)
    write(root, ".githooks/pre-push", HOOK, 0o755)


def only_dup(root):
    return pp.stage_map(root)["duplicates"][0]


def ci_blocking(root):
    return [e["blocking"] for e in pp.stage_map(root)["entries"] if e["stage"] == "ci"]


PR = "on: pull_request\njobs:\n  g:\n%s    steps:\n      - name: Unit\n%s        run: bash scripts/unit.sh\n"


class Blocking(unittest.TestCase):
    def test_a_push_only_workflow_does_not_gate_a_pr(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, "on: push\njobs:\n  g:\n    steps:\n      - name: Unit\n        run: bash scripts/unit.sh\n")
            self.assertEqual(ci_blocking(d), [False])
            dup = only_dup(d)
            self.assertEqual((dup["keep"], dup["drop"], dup["enforced"]), (None, [], False))

    def test_a_pr_workflow_still_gates_and_the_local_run_is_the_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, PR % ("", ""))
            dup = only_dup(d)
            self.assertEqual((dup["keep"], dup["drop"], dup["enforced"]), ("ci", ["push"], True))

    def test_job_level_continue_on_error_is_not_blocking(self):
        for coe in ("true", "${{ matrix.experimental }}", "True"):
            with tempfile.TemporaryDirectory() as d:
                repo(d, PR % ("    continue-on-error: %s\n" % coe, ""))
                self.assertEqual(ci_blocking(d), [False], coe)
                self.assertFalse(only_dup(d)["enforced"], coe)
        with tempfile.TemporaryDirectory() as d:
            repo(d, PR % ("    continue-on-error: false\n", ""))
            self.assertEqual(ci_blocking(d), [True])

    def test_step_continue_on_error_expression_is_not_blocking(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, PR % ("", "        continue-on-error: ${{ github.event_name == 'push' }}\n"))
            self.assertEqual(ci_blocking(d), [False])

    def test_an_unrecognised_if_is_not_enforced(self):
        for cond in ("github.ref == 'refs/heads/main'", "failure()", "matrix.os == 'linux'", "github.event_name == 'push'",
                     "contains(github.event.pull_request.labels.*.name, 'run-ci')"):
            with tempfile.TemporaryDirectory() as d:
                repo(d, PR % ("", "        if: %s\n" % cond))
                self.assertEqual(ci_blocking(d), [False], cond)
                self.assertEqual(only_dup(d)["drop"], [], cond)
            with tempfile.TemporaryDirectory() as d:
                repo(d, PR % ("    if: %s\n" % cond, ""))
                self.assertEqual(ci_blocking(d), [False], cond)

    def test_recognised_conditions_keep_blocking(self):
        for cond in ("success()", "always()", "${{ github.event_name != 'merge_group' }}", "github.event_name == 'pull_request'"):
            with tempfile.TemporaryDirectory() as d:
                repo(d, "on:\n  pull_request:\n  merge_group:\njobs:\n  g:\n    steps:\n      - name: Unit\n"
                     "        if: %s\n        run: bash scripts/unit.sh\n" % cond)
                self.assertEqual(ci_blocking(d), [True], cond)

    def test_a_merge_group_only_step_is_the_train_stage(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, "on:\n  pull_request:\n  merge_group:\njobs:\n  g:\n    steps:\n      - name: Unit\n"
                 "        if: github.event_name == 'merge_group'\n        run: bash scripts/unit.sh\n")
            self.assertEqual({e["stage"] for e in pp.stage_map(d)["entries"]}, {"push", "train"})


class Compare(unittest.TestCase):
    def test_an_unknown_metric_with_no_sample_count_is_unverified(self):
        r = pp.compare_profiles({"x": {"y": 100.0}}, {"x": {"y": 10.0}}, "x.y")
        self.assertEqual(r["verdict"], "UNVERIFIED")
        self.assertIn("sample", r["reason"])

    def test_known_stage_metrics_count_their_samples(self):
        b = {"ci": {"measured_runs": 5}, "stages_s": {"ci_exec": 100.0}}
        a = {"ci": {"measured_runs": 5}, "stages_s": {"ci_exec": 50.0}}
        self.assertEqual(pp.compare_profiles(b, a, "stages_s.ci_exec", stage_only=True)["verdict"], "KEEP")
        a["ci"]["measured_runs"] = 1
        self.assertEqual(pp.compare_profiles(b, a, "stages_s.ci_exec")["verdict"], "UNVERIFIED")


class SaveJson(unittest.TestCase):
    def test_a_failed_write_leaves_the_old_file_and_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "profile.json")
            pp.save_json(str(p), {"v": 1})
            with self.assertRaises(TypeError):
                pp.save_json(str(p), {"v": object()})
            self.assertEqual(json.loads(p.read_text()), {"v": 1})
            self.assertEqual([x.name for x in Path(d).iterdir()], ["profile.json"])

    def test_a_good_write_replaces_the_file_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "profile.json")
            pp.save_json(str(p), {"v": 1})
            pp.save_json(str(p), {"v": 2})
            self.assertEqual(json.loads(p.read_text()), {"v": 2})
            self.assertEqual([x.name for x in Path(d).iterdir()], ["profile.json"])


if __name__ == "__main__":
    unittest.main()
