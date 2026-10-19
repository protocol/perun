"""pipeline_profile.py compare: a faster stage is only a KEEP when delivery (lead time, merge rate) did not get worse."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts/pipeline_profile.py")
spec = importlib.util.spec_from_file_location("pp", TOOL)
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)
M = "ci.exec_s.median"


def prof(exec_s, lead=None, rate=None):
    P = {"ci": {"measured_runs": 5, "exec_s": {"median": exec_s}}}
    if lead is not None or rate is not None:
        P["lead"] = {"first_push_to_merge_s": lead, "merged_per_day": rate}
    return P


class OutcomeGuardrail(unittest.TestCase):
    def test_proxy_better_but_outcome_worse_is_revert(self):
        r = pp.compare_profiles(prof(100.0, 1000.0, 5.0), prof(60.0, 1500.0, 5.0), M)
        self.assertEqual(r["verdict"], "REVERT")
        self.assertEqual(r["reason"], "stage improved but delivery outcome regressed: "
                         "lead.first_push_to_merge_s %s->%s" % (pp.fmt(1000.0), pp.fmt(1500.0)))
        r = pp.compare_profiles(prof(100.0, 1000.0, 5.0), prof(60.0, 900.0, 3.0), M)
        self.assertEqual(r["verdict"], "REVERT")
        self.assertIn("lead.merged_per_day 5.00/day->3.00/day", r["reason"])

    def test_both_better_is_keep_and_a_flat_outcome_inside_the_band_is_keep(self):
        self.assertEqual(pp.compare_profiles(prof(100.0, 1000.0, 5.0), prof(60.0, 800.0, 6.0), M)["verdict"], "KEEP")
        self.assertEqual(pp.compare_profiles(prof(100.0, 1000.0, 5.0), prof(60.0, 1020.0, 4.9), M)["verdict"], "KEEP")

    def test_missing_outcome_is_unverified_on_either_side(self):
        for b, a in ((prof(100.0), prof(60.0, 900.0, 5.0)), (prof(100.0, 1000.0, 5.0), prof(60.0)),
                     (prof(100.0, 1000.0, None), prof(60.0, 900.0, 5.0))):
            r = pp.compare_profiles(b, a, M)
            self.assertEqual(r["verdict"], "UNVERIFIED")
            self.assertIn("outcome not measured", r["reason"])

    def test_stage_only_keeps_labelled_and_ignores_a_regression(self):
        r = pp.compare_profiles(prof(100.0), prof(60.0), M, stage_only=True)
        self.assertEqual(r["verdict"], "KEEP")
        self.assertIn("stage-only", r["reason"])
        self.assertEqual(pp.compare_profiles(prof(100.0, 1000.0, 5.0), prof(60.0, 1500.0, 5.0), M,
                                             stage_only=True)["verdict"], "KEEP")

    def test_a_stage_that_did_not_improve_stays_revert_regardless_of_flags(self):
        self.assertEqual(pp.compare_profiles(prof(100.0), prof(100.0), M)["verdict"], "REVERT")
        self.assertEqual(pp.compare_profiles(prof(100.0), prof(100.0), M, stage_only=True)["verdict"], "REVERT")

    def test_default_metric_is_lead_time_and_the_cli_flag_works(self):
        with tempfile.TemporaryDirectory() as d:
            for name, P in (("b", prof(100.0, 1000.0, 5.0)), ("a", prof(60.0, 500.0, 5.0)), ("w", prof(60.0))):
                with open(os.path.join(d, name + ".json"), "w") as f:
                    json.dump(P, f)

            def run(x, y, *extra):
                return subprocess.run([sys.executable, TOOL, "compare", os.path.join(d, x + ".json"),
                                       os.path.join(d, y + ".json"), *extra], capture_output=True, text=True)
            self.assertEqual(run("b", "a").returncode, 0)  # default metric: lead.first_push_to_merge_s dropped 50%
            self.assertEqual(run("b", "a", "--metric", M).returncode, 0)
            self.assertEqual(run("b", "w", "--metric", M).returncode, 2)  # outcome not measured
            self.assertEqual(run("b", "w", "--metric", M, "--stage-only").returncode, 0)

    def test_merged_per_day(self):
        iso = lambda day, h: "2026-01-%02dT%02d:00:00Z" % (day, h)
        pull = lambda n, t: {"number": n, "merged_at": t, "created_at": iso(1, 0)}
        self.assertIsNone(pp.lead_metrics({})["merged_per_day"])
        self.assertIsNone(pp.lead_metrics({"pulls": [pull(1, iso(2, 1))]})["merged_per_day"])
        b = {"pulls": [pull(1, iso(2, 1)), pull(2, iso(2, 9)), pull(3, iso(4, 5)), {"number": 4, "merged_at": None}]}
        self.assertEqual(pp.lead_metrics(b)["merged_per_day"], 1.0)  # 3 merges over days 2..4 inclusive
        self.assertEqual(pp.lead_metrics({"pulls": [pull(1, iso(2, 1)), pull(2, iso(2, 9))]})["merged_per_day"], 2.0)


if __name__ == "__main__":
    unittest.main()
