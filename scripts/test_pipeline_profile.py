#!/usr/bin/env python3
"""Offline tests for pipeline_profile.py: the suite x stage map, the measurements, the priced fix catalogue and the
re-measure verdict. Synthetic data only: no network, no real repo history, no real names."""
import datetime
import email.message
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SCRIPTS))
import pipeline_profile as pp  # noqa: E402

TOOL = str(SCRIPTS / "pipeline_profile.py")
BASE = 1_700_000_000


def iso(t):
    return datetime.datetime.fromtimestamp(BASE + t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def step(n, name, s, e, concl="success"):
    return {"name": name, "number": n, "conclusion": concl, "started_at": iso(s) if s is not None else None,
            "completed_at": iso(e) if e is not None else None}


def job(jid, name, created, started, completed, steps):
    return {"id": jid, "name": name, "conclusion": "success", "created_at": iso(created), "started_at": iso(started),
            "completed_at": iso(completed), "steps": steps}


def run(rid, prs, sha, created, updated, concl="success", attempt=1, msg="Add feature"):
    return {"id": rid, "name": "gates", "event": "pull_request", "head_branch": "feat/x", "head_sha": sha,
            "run_attempt": attempt, "run_started_at": iso(created), "created_at": iso(created),
            "updated_at": iso(updated), "conclusion": concl, "status": "completed", "prs": prs, "msg": msg}


def ci_job(jid, t, queue, e2e=200, fail_lint=False):
    """One 'gates' job: queue wait, then Set up 5s, Unit 100s, Lint 20s, E2E (skipped when Lint fails), Complete 1s."""
    s = t + queue
    st = [step(1, "Set up job", s, s + 5), step(2, "Unit tests", s + 5, s + 105)]
    if fail_lint:
        st += [step(3, "Lint", s + 105, s + 125, "failure"), step(4, "E2E tests", None, None, "skipped"),
               step(5, "Complete job", s + 125, s + 126)]
        return job(jid, "gates", t, s, s + 126, st)
    st += [step(3, "Lint", s + 105, s + 125), step(4, "E2E tests", s + 125, s + 125 + e2e),
           step(5, "Complete job", s + 125 + e2e, s + 126 + e2e)]
    return job(jid, "gates", t, s, s + 126 + e2e, st)


def bundle():
    """4 runs: PR1 twice (the 2nd is a base-update re-run), PR3 red at Lint, PR2 passed on attempt 2."""
    runs = [run(1, [1], "a1", 0, 337), run(2, [1], "a2", 1000, 1311, msg="Merge branch 'main' into feat/x"),
            run(3, [3], "c1", 2000, 2129, "failure"), run(4, [2], "b1", 3000, 3330, attempt=2)]
    jobs = {"1": [ci_job(11, 0, 10)], "2": [ci_job(12, 1000, 4, e2e=180)], "3": [ci_job(13, 2000, 2, fail_lint=True)],
            "4": [ci_job(14, 3000, 3)]}
    pulls = [{"number": 1, "created_at": iso(-100), "merged_at": iso(1811), "head_ref": "feat/x"},
             {"number": 2, "created_at": iso(2900), "merged_at": iso(3390), "head_ref": "feat/y"}]
    return {"runs": runs, "jobs": jobs, "pulls": pulls, "limits": []}


def write(root, rel, text, mode=None):
    p = Path(root, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if mode:
        p.chmod(mode)


SUITES = ["unit", "lint", "integration", "e2e"]
STEP = {"unit": "Unit tests", "lint": "Lint", "integration": "Integration tests", "e2e": "E2E tests"}


def fixture_repo(root, merge_group=False):
    """The failure shape: the same 4 suites at commit, push, a documented pre-PR check, and CI."""
    trig = "  pull_request:\n    branches: [main]\n" + ("  merge_group:\n" if merge_group else "")
    steps = "".join("      - name: %s\n        run: bash scripts/%s.sh\n" % (STEP[s], s) for s in SUITES)
    write(root, ".github/workflows/ci.yml", "name: gates\non:\n%sjobs:\n  gates:\n    runs-on: ubuntu-latest\n"
          "    steps:\n      - uses: actions/checkout@v4\n%s" % (trig, steps))
    write(root, ".githooks/pre-commit", "#!/bin/sh\n" + "".join("bash scripts/%s.sh\n" % s for s in SUITES), 0o755)
    write(root, ".githooks/pre-push", "#!/bin/sh\n" + "".join("bash scripts/%s.sh\n" % s for s in SUITES), 0o755)
    write(root, "CONTRIBUTING.md", "# Project\n\n## Before you open a PR\n\n```bash\n" +
          "".join("bash scripts/%s.sh\n" % s for s in SUITES) + "```\n")
    for s in SUITES:
        write(root, "scripts/%s.sh" % s, "#!/bin/sh\nexit 0\n", 0o755)


def local_rows(secs=None):
    return {"rows": [{"stage": st, "name": k, "key": k, "n": 1, "wall_median_s": v, "cpu_median_s": v}
                     for (st, k), v in (secs or {}).items()], "stage_s": {}}


class Parse(unittest.TestCase):
    def test_suite_key_normalises_one_check_across_arguments(self):
        k = pp.suite_key
        self.assertEqual(k(["bash", "scripts/ci-gates.sh", "size-ratchet", "--base", "x"]), ("key", "scripts/ci-gates.sh size-ratchet"))
        self.assertEqual(k(["python3", "./a/b.py", "--selftest"]), ("key", "a/b.py --selftest"))
        self.assertEqual(k(["python3", "a/b.py", "--base", "main"]), ("key", "a/b.py"))  # a flag value is not a subcommand
        self.assertEqual(k(["FOO=1", "pytest", "-q", "tests/"]), ("key", "pytest"))
        self.assertEqual(k(["uv", "run", "pytest"]), ("key", "pytest"))
        self.assertEqual(k(["python3", "-m", "pytest"]), ("key", "pytest"))
        self.assertEqual(k(["npm", "run", "lint"]), ("key", "npm run lint"))
        self.assertEqual(k(["make", "-j4", "test"]), ("key", "make test"))
        self.assertEqual(k(["fg", "name", "fix text", "bash", "scripts/x.sh"]), ("key", "scripts/x.sh"))
        self.assertEqual(k(["bash", "-n", "install.sh"]), ("key", "syntax-check install.sh"))

    def test_plumbing_setup_and_dynamic_commands_are_not_suites(self):
        for t in (["npm", "ci"], ["pip", "install", "x"], ["echo", "bash", "x.sh"], ["git", "diff"], ["bash", "$X/run.sh"],
                  ["bash", "-c"], ["python3", "-m", "pip"], ["cd", "x"], ["bash", "noext"], ["pre-commit", "install"]):
            self.assertIsNone(pp.suite_key(t), t)

    def test_commands_skip_heredocs_comments_and_mark_warn_only(self):
        text = "# bash c.sh\nbash a.sh \\\n  --flag\ncat <<EOF\nbash in_heredoc.sh\nEOF\nbash b.sh || true\n" \
               "bash -c 'bash inner.sh && bash inner2.sh'\nfor f in 1 2; do bash \"scripts/$f.sh\"; done\n"
        got = [(c[1], c[2]) for c in pp.commands(text)]
        self.assertEqual(got, [("a.sh", True), ("b.sh", False), ("inner.sh", True), ("inner2.sh", True)])

    def test_redirects_are_dropped_so_the_command_text_replays_as_written(self):
        got = pp.commands("bash a.sh --flag x >/dev/null 2>&1\npython3 b.py 24000 > out.txt\nbash c.sh 2>/dev/null || true\n")
        self.assertEqual([c[0] for c in got], ["bash a.sh --flag x", "python3 b.py 24000", "bash c.sh"])

    def test_workflow_triggers_steps_and_continue_on_error(self):
        wf = pp.parse_workflow("name: x\non:\n  pull_request:\n    branches: [main]\n  merge_group:\njobs:\n  a:\n    if: true\n"
                               "    steps:\n      - uses: actions/checkout@v4\n      - name: T\n        run: |\n"
                               "          bash t.sh\n          bash u.sh\n      - name: W\n        continue-on-error: true\n"
                               "        run: bash w.sh\n")
        self.assertEqual(wf["on"], {"pull_request", "merge_group"})
        steps = wf["jobs"]["a"]["steps"]
        self.assertEqual([pp.step_label(s) for s in steps], ["Run actions/checkout@v4", "T", "W"])
        self.assertEqual([c[1] for c in pp.commands(steps[1]["run"])], ["t.sh", "u.sh"])
        self.assertEqual([s["coe"] for s in steps], [False, False, True])
        self.assertEqual(pp.parse_workflow("on: [push, pull_request]\njobs:\n")["on"], {"push", "pull_request"})

    def test_tag_push_workflow_is_a_release_not_a_gate(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, ".github/workflows/release.yml", "on:\n  push:\n    tags: ['v*']\njobs:\n  r:\n    steps:\n"
                  "      - name: Publish\n        run: bash scripts/publish.sh\n")
            self.assertEqual(pp.stage_map(d)["entries"], [])


class StageMap(unittest.TestCase):
    def test_same_four_suites_at_four_stages_are_flagged_and_keep_ci(self):
        with tempfile.TemporaryDirectory() as d:
            fixture_repo(d)
            smap = pp.stage_map(d)
            self.assertEqual(len(smap["duplicates"]), 4)
            for dup in smap["duplicates"]:
                self.assertEqual(dup["stages"], ["commit", "push", "precheck", "ci"])
                self.assertEqual(dup["keep"], "ci")
                self.assertTrue(dup["enforced"])
                self.assertNotIn("ci", dup["drop"])

    def test_merge_group_makes_the_train_the_latest_gate_and_ci_a_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            fixture_repo(d, merge_group=True)
            dup = next(x for x in pp.stage_map(d)["duplicates"] if x["key"] == "scripts/e2e.sh")
            self.assertEqual((dup["keep"], "ci" in dup["drop"], "train" in dup["stages"]), ("train", True, True))

    def test_declared_stage_and_advisory_ci_step(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, ".github/workflows/ci.yml", "on: pull_request\njobs:\n  g:\n    steps:\n      - name: Advisory only\n"
                  "        continue-on-error: true\n        run: bash scripts/unit.sh\n")
            write(d, ".githooks/pre-push", "#!/bin/sh\nbash scripts/unit.sh\n", 0o755)
            dup = pp.stage_map(d, {"train": ["bash scripts/unit.sh"]})["duplicates"][0]
            self.assertEqual((dup["stages"], dup["keep"]), (["push", "ci", "train"], "train"))
            only = pp.stage_map(d)["duplicates"][0]  # the CI run is advisory, so no gate is proven to block: drop nothing
            self.assertEqual((only["keep"], only["drop"], only["enforced"]), (None, [], False))

    def test_thin_hook_is_its_implementation_and_quoted_ci_step_names_count(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, ".github/workflows/ci.yml", "on: pull_request\njobs:\n  g:\n    steps:\n      - name: Mechanism check here\n"
                  "        run: bash scripts/mech.sh\n")
            write(d, ".githooks/pre-push", '#!/bin/sh\nexec bash "$(dirname "$0")/../tools/verify.sh" "$@"\n', 0o755)
            write(d, "tools/verify.sh", '#!/bin/sh\nbash scripts/quick.sh\nfor n in "Mechanism check here"; do :; done\n')
            smap = pp.stage_map(d)
            keys = {(e["stage"], e["key"]) for e in smap["entries"]}
            self.assertIn(("push", "scripts/quick.sh"), keys)
            self.assertIn(("push", "scripts/mech.sh"), keys)
            self.assertNotIn(("push", "tools/verify.sh"), keys)  # the wrapper is not a suite
            self.assertEqual([x["key"] for x in smap["duplicates"]], ["scripts/mech.sh"])

    def test_precommit_heading_in_docs_maps_to_the_commit_stage(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "CLAUDE.md", "## Pre-commit check\n\n```bash\nbash scripts/a.sh\n```\n\n## Install\n\n```bash\nbash scripts/b.sh\n```\n")
            self.assertEqual({(e["stage"], e["key"]) for e in pp.stage_map(d)["entries"]}, {("commit", "scripts/a.sh")})


class Measure(unittest.TestCase):
    def setUp(self):
        self.ci = pp.ci_metrics(bundle())
        self.lead = pp.lead_metrics(bundle())

    def test_ci_wall_queue_and_step_medians(self):
        self.assertEqual((self.ci["runs"], self.ci["measured_runs"]), (4, 4))
        self.assertEqual(self.ci["exec_s"]["median"], 316.0)  # [126, 306, 326, 326]
        self.assertEqual(self.ci["queue_s"]["median"], 3.5)  # [2, 3, 4, 10]
        self.assertEqual(self.ci["wall_s"]["median"], 319.5)
        steps = {s["name"]: s for s in self.ci["steps"]}
        self.assertEqual((steps["E2E tests"]["median_s"], steps["E2E tests"]["n"]), (200.0, 3))  # the skipped step is not a sample
        self.assertEqual(steps["Unit tests"]["median_s"], 100.0)
        self.assertEqual(self.ci["steps"][0]["name"], "E2E tests")  # ranked by median seconds
        self.assertEqual(self.ci["critical_jobs"], ["gates"])

    def test_red_rate_reruns_flakes_and_waste(self):
        fl = self.ci["flake"]
        self.assertEqual((fl["completed"], fl["failed"], fl["reruns"], fl["flake_suspects"]), (4, 1, 1, 1))
        self.assertEqual(fl["red_rate"], 0.25)
        self.assertEqual(fl["rerun_waste_s_per_run"], 316.0 / 4)

    def test_fail_fast_saving_is_computed_from_the_red_run(self):
        ff = self.ci["fail_fast"]  # red at Lint after 5+100+20; cheapest-first reaches Lint after 5+20
        self.assertEqual((ff["red_runs"], ff["mean_saved_per_red_run_s"], ff["saved_per_run_s"]), (1, 100.0, 25.0))

    def test_lead_time_post_green_wait_and_base_update_reruns(self):
        ld = self.lead
        self.assertEqual((ld["prs"], ld["cycles_median"]), (2, 1.5))
        self.assertEqual(ld["first_push_to_merge_s"], 1100.5)  # [1811, 390]
        self.assertEqual(ld["last_push_to_merge_s"], 600.5)  # [811, 390]
        self.assertEqual(ld["post_green_wait_s"], 280.0)  # [500, 60]
        self.assertEqual(ld["update_branch_ci_s_per_pr"], 155.5)  # (311 + 0) / 2

    def test_a_fork_pr_run_with_no_pull_requests_is_matched_by_its_head_branch(self):
        b = bundle()
        for r in b["runs"]:
            r["prs"] = []  # as GitHub reports a run whose PR head lives in a fork
        b["runs"][0]["head_branch"] = b["runs"][1]["head_branch"] = "feat/x"
        b["runs"][2]["head_branch"] = "feat/z"  # a PR that never merged
        b["runs"][3]["head_branch"] = "feat/y"
        ld = pp.lead_metrics(b)
        self.assertEqual((ld["prs"], ld["cycles_median"], ld["first_push_to_merge_s"]), (2, 1.5, 1100.5))

    def test_missing_data_stays_none_never_zero(self):
        ci, ld = pp.ci_metrics({}), pp.lead_metrics({})
        self.assertIsNone(ci["exec_s"]["median"])
        self.assertIsNone(ci["flake"]["red_rate"])
        self.assertIsNone(ld["first_push_to_merge_s"])
        self.assertEqual(pp.fmt(None), "n/a")

    def test_cache_hit_rate_needs_logs_and_is_measured_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pp.cache_metrics(d)["note"], "no cache step in any workflow")
            write(d, ".github/workflows/ci.yml", "on: pull_request\njobs:\n  g:\n    steps:\n      - uses: actions/cache@v4\n")
            c = pp.cache_metrics(d)
            self.assertEqual((len(c["steps"]), c["hit_rate"]), (1, None))
            self.assertIn("unverified", c["note"])
            logs = ["Cache restored from key: k", "Cache not found for input keys: k", "Cache restored from key: k2"]
            self.assertEqual(pp.cache_metrics(d, logs)["hit_rate"], 2 / 3)

    def test_dup_seconds_split_a_ci_step_over_its_commands_and_use_local_rows(self):
        wf, hook = ".github/workflows/ci.yml", ".githooks/pre-push"
        smap = {"entries": [
            {"stage": "ci", "key": "a.sh", "step": "Gates", "cmd": "bash a.sh", "source": wf},
            {"stage": "ci", "key": "b.sh", "step": "Gates", "cmd": "bash b.sh", "source": wf},
            {"stage": "push", "key": "a.sh", "step": None, "cmd": "bash a.sh", "source": hook},
            {"stage": "push", "key": "b.sh", "step": None, "cmd": "bash b.sh", "source": hook}],
            "duplicates": [{"key": "a.sh", "stages": ["push", "ci"], "keep": "ci", "drop": ["push"], "enforced": True},
                           {"key": "b.sh", "stages": ["push", "ci"], "keep": "ci", "drop": ["push"], "enforced": True}]}
        out = pp.dup_seconds(smap, [{"name": "Gates", "median_s": 60.0}], local_rows({("push", "a.sh"): 7.0}))
        a, b = out
        self.assertEqual((a["seconds"], a["waste_s"], a["unmeasured"]), ({"push": 7.0, "ci": 30.0}, 7.0, []))
        self.assertEqual((b["waste_s"], b["unmeasured"]), (0, ["push"]))  # unmeasured is named, not zero-priced

    def test_dup_seconds_do_not_double_count_a_ci_step_a_hook_also_runs_and_split_a_hook_total_evenly(self):
        e = [{"stage": "ci", "key": "a.sh", "step": "Mechanism check", "cmd": "bash a.sh", "source": ".github/workflows/ci.yml"},
             {"stage": "push", "key": "a.sh", "step": "Mechanism check", "cmd": "bash a.sh", "source": ".githooks/pre-push (runs CI step)"},
             {"stage": "push", "key": "b.sh", "step": None, "cmd": "bash b.sh", "source": ".githooks/pre-push"},
             {"stage": "push", "key": "c.sh", "step": None, "cmd": "bash c.sh", "source": ".githooks/pre-push"}]
        smap = {"entries": e, "duplicates": [{"key": "a.sh", "stages": ["push", "ci"], "keep": "ci", "drop": ["push"], "enforced": True}]}
        local = {"rows": [], "stage_s": {"push": 30.0}}  # the push hook runs 3 suites in 30s
        a = pp.dup_seconds(smap, [{"name": "Mechanism check", "median_s": 12.0}], local)[0]
        self.assertEqual(a["seconds"], {"push": 10.0, "ci": 12.0})  # CI step counted once; hook total / 3 suites
        self.assertEqual((a["waste_s"], a["unmeasured"]), (10.0, []))

    def test_breakeven_red_rate_for_a_local_full_run(self):
        dups = [{"seconds": {"precheck": 480.0, "ci": 600.0}, "keep": "ci"}]  # 8 min local, 10 min CI
        be = pp.local_breakeven(dups, 60.0, 0.12)  # plus 1 min queue, 12% of runs red
        self.assertAlmostEqual(be["red_rate_needed"], 8 / 11)
        self.assertFalse(be["pays_off"])  # costs 8 min every cycle to save 0.12 x 11 min
        self.assertTrue(pp.local_breakeven(dups, 60.0, 0.9)["pays_off"])
        self.assertIsNone(pp.local_breakeven([{"seconds": {"precheck": None, "ci": 600.0}, "keep": "ci"}], 0, 0.1))

    def test_git_history_counts_first_parent_changes_and_lockfiles(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL="jane@example.com",
                   GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL="jane@example.com")
        with tempfile.TemporaryDirectory() as d:
            def sh(*a):
                subprocess.run(["git", "-C", d, "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *a],
                               check=True, capture_output=True, env=env)
            sh("init", "-q")
            for i, files in enumerate([["a.py", "README.md"], ["package-lock.json"], ["a.py"]]):
                for f in files:
                    write(d, f, "x%d" % i)
                sh("add", "-A")
                sh("commit", "-q", "-m", "c%d" % i)
            h = pp.git_history(d, 10)
            self.assertEqual([sorted(m) for m in h["merges"]], [["a.py"], ["package-lock.json"], ["README.md", "a.py"]])
            self.assertEqual((h["has_lock"], round(h["lock_stable"], 3)), (True, round(2 / 3, 3)))
            self.assertEqual(pp.change_fraction(h), (1 / 3 + 1 / 3 + 2 / 3) / 3)

    def test_affected_fraction_is_the_share_of_tests_a_name_reference_selector_runs(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "tests/test_a.py", "import a.py")
            write(d, "tests/test_b.py", "import b.py")
            h = {"merges": [["src/a.py"], ["src/b.py"], ["tests/test_a.py"]], "tracked": ["src/a.py", "src/b.py", "tests/test_a.py", "tests/test_b.py"]}
            self.assertEqual(pp.select_frequency(d, h), {"tests/test_a.py": 2 / 3, "tests/test_b.py": 1 / 3})
            self.assertEqual(pp.affected_fraction(d, h), 0.5)
            self.assertIsNone(pp.affected_fraction(d, {"merges": [], "tracked": []}))

    def test_affected_prices_a_monolithic_test_script_by_how_often_it_is_selected(self):
        steps = [{"job": "g", "name": "Big", "median_s": 600.0, "n": 5}, {"job": "g", "name": "Many", "median_s": 100.0, "n": 5},
                 {"job": "g", "name": "Lint", "median_s": 50.0, "n": 5}]
        P = {"ci": {"steps": steps}, "history": {"merges": 30, "select_freq": {
            "scripts/test-big.sh": 1.0, "scripts/test_a.py": 0.2, "scripts/test_b.py": 0.4}}}
        entries = [{"stage": "ci", "step": "Big", "key": "scripts/test-big.sh"},
                   {"stage": "ci", "step": "Many", "key": "scripts/test_a.py"},
                   {"stage": "ci", "step": "Many", "key": "scripts/test_b.py --selftest"},
                   {"stage": "ci", "step": "Lint", "key": "scripts/lint.sh"}]  # not a test file: not priced
        gain, basis = pp.f_affected(P, __import__("argparse").Namespace(entries=entries))
        self.assertAlmostEqual(gain, 600 * (1 - 1.0) + 100 * (1 - 0.3))  # the monolith is always selected: no gain
        self.assertIn("2 test step(s)", basis)
        self.assertIsNone(pp.f_affected({"ci": {"steps": steps}}, __import__("argparse").Namespace(entries=entries))[0])

    def test_shard_splits_a_step_with_measured_sections_scaled_to_its_ci_median(self):
        steps = [{"job": "g", "name": "Set up job", "median_s": 6.0, "n": 5}, {"job": "g", "name": "Heavy", "median_s": 600.0, "n": 5},
                 {"job": "g", "name": "Light", "median_s": 60.0, "n": 5}]
        P = {"ci": {"steps": steps}, "sections": {"Heavy": {"a": 100, "b": 100, "c": 200, "d": 100}}}  # any unit: scaled x1.2
        gain, basis = pp.f_shard(P, __import__("argparse").Namespace(shards=4))
        self.assertAlmostEqual(gain, 660.0 - 240.0 - 6.0)  # LPT: 240 | 120 | 120 | 120+60
        self.assertIn("1 step(s) split into measured sections", basis)
        whole = pp.f_shard({"ci": {"steps": steps}}, __import__("argparse").Namespace(shards=4))[0]
        self.assertAlmostEqual(whole, 660.0 - 600.0 - 6.0)  # unsplit, the monolith caps the speed-up


class Timings(unittest.TestCase):
    def test_time_records_wall_cpu_rc_and_summary_uses_passing_runs_only(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "t.tsv")
            rc, wall, cpu = pp.record_timing(log, "push", "hook:pre-push", "x", [sys.executable, "-c", "pass"])
            self.assertEqual(rc, 0)
            self.assertGreaterEqual(wall, 0)
            pp.record_timing(log, "push", "hook:pre-push", "x", [sys.executable, "-c", "import sys; sys.exit(3)"])
            write(d, "scripts/unit.sh", "exit 127\n")
            pp.record_timing(log, "precheck", "scripts/unit.sh", "bash scripts/unit.sh", None, True, d)  # runs in cwd=d
            rows = pp.load_timings(log)
            self.assertEqual([r["rc"] for r in rows], [0, 3, 127])
            summ = pp.local_summary(rows)
            self.assertEqual(len(summ["rows"]), 1)  # the failing runs are excluded from medians
            self.assertIn("push", summ["stage_s"])

    def test_ok_rc_counts_a_completed_run_with_known_failures_but_a_crash_never_counts(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "t.tsv")
            pp.record_timing(log, "ci", "suite", "x", [sys.executable, "-c", "import sys; sys.exit(1)"], ok_rc=(1,))
            pp.record_timing(log, "ci", "suite", "x", [sys.executable, "-c", "import sys; sys.exit(2)"], ok_rc=(1,))
            pp.record_timing(log, "ci", "suite", "x", [sys.executable, "-c", "pass"])
            rows = pp.load_timings(log)
            self.assertEqual([(r["rc"], r["ok"]) for r in rows], [(1, True), (2, False), (0, True)])
            self.assertEqual(pp.local_summary(rows)["rows"][0]["n"], 2)  # rc 1 (accepted) and rc 0; rc 2 is excluded
            Path(log).write_text("2026-01-01T00:00:00Z\tci\told\t5.0\t4.0\t0\tx\n")  # a row from before the ok column
            self.assertTrue(pp.load_timings(log)[0]["ok"])

    def test_cli_time_returns_the_child_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, TOOL, "time", "--root", d, "--log", os.path.join(d, "l.tsv"),
                                "--stage", "commit", "--name", "n", "--", sys.executable, "-c", "import sys; sys.exit(5)"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 5)
            self.assertIn("rc=5", r.stdout)
            out = os.path.join(d, "o.txt")  # --shell takes the text as a script: redirects and && work
            r = subprocess.run([sys.executable, TOOL, "time", "--root", d, "--log", os.path.join(d, "l.tsv"), "--stage", "ci",
                                "--name", "s", "--shell", "--", "echo hi > %s && exit 4" % out], capture_output=True, text=True)
            self.assertEqual((r.returncode, Path(out).read_text()), (4, "hi\n"))


class Fixes(unittest.TestCase):
    def profile(self, d, local=None, merge_group=False):
        fixture_repo(d, merge_group)
        smap = pp.stage_map(d)
        hist = {"merges": [["a"], ["b"]], "tracked": ["a", "b", "c", "d"], "has_lock": False, "lock_stable": None}
        return pp.build_profile(d, bundle(), local_rows(local), smap, hist, {"steps": [], "hit_rate": None, "note": "x"}, "o/r"), smap

    def test_four_suites_at_four_stages_price_dedup_first_not_stage_tuning(self):
        with tempfile.TemporaryDirectory() as d:
            secs = {"scripts/unit.sh": 30.0, "scripts/lint.sh": 5.0, "scripts/integration.sh": 90.0, "scripts/e2e.sh": 200.0}
            local = {(st, k): v for st in ("commit", "push", "precheck") for k, v in secs.items()}
            P, smap = self.profile(d, local)
            fixes = pp.price_fixes(P, smap["entries"])
            first = fixes[0]
            self.assertEqual(first["id"], "dedup")
            self.assertTrue(first["lever"])
            # waste per cycle = every local run of the four suites (325s per stage) at commit, push and precheck
            self.assertEqual(first["per_cycle_s"], 975.0)
            self.assertEqual(first["per_pr_s"], 975.0 * 1.5)
            ids = [f["id"] for f in fixes]
            self.assertLess(ids.index("dedup"), ids.index("shard"))
            self.assertLess(ids.index("dedup"), ids.index("runner"))
            self.assertEqual(sorted(ids), sorted(f[0] for f in pp.FIXES))
            self.assertEqual([f["rank"] for f in fixes], list(range(1, len(fixes) + 1)))

    def test_dedup_waste_is_unmeasured_until_local_stages_are_timed(self):
        with tempfile.TemporaryDirectory() as d:
            P, smap = self.profile(d)
            self.assertEqual(sum(len(x["unmeasured"]) for x in P["dups"]), 12)  # 4 suites x (commit, push, precheck)
            fx = {f["id"]: f for f in pp.price_fixes(P, smap["entries"])}
            self.assertEqual(fx["dedup"]["per_cycle_s"], 0.0)
            self.assertFalse(fx["dedup"]["lever"])
            self.assertIn("12 stage run(s) unmeasured", fx["dedup"]["basis"])

    def test_shard_saving_is_the_lpt_makespan_gain(self):
        with tempfile.TemporaryDirectory() as d:
            P, smap = self.profile(d)
            fx = {f["id"]: f for f in pp.price_fixes(P, smap["entries"], shards=2)}
            work = [200.0, 100.0, 20.0]
            setup = 5.0 + 1.0
            self.assertEqual(pp._lpt(work, 2), 200.0)
            self.assertEqual(fx["shard"]["per_cycle_s"], sum(work) - 200.0 - setup)
            self.assertEqual(pp._lpt([5, 4, 3, 3, 3], 2), 10)  # greedy LPT, not optimal (9): a conservative saving

    def test_flake_fail_fast_and_queue_savings_come_from_the_profile(self):
        with tempfile.TemporaryDirectory() as d:
            P, smap = self.profile(d)
            fx = {f["id"]: f for f in pp.price_fixes(P, smap["entries"])}
            self.assertEqual(fx["flake"]["per_cycle_s"], 79.0)
            self.assertEqual(fx["fail-fast"]["per_cycle_s"], 25.0)
            self.assertEqual(fx["queue"]["per_pr_s"], 155.5)  # already per PR
            self.assertEqual(fx["cache"]["per_cycle_s"], 0.0)  # no lockfile tracked: nothing to cache
            self.assertEqual(fx["incremental"]["per_cycle_s"], 20.0 * (1 - 0.25))  # Lint 20s x (1 - 25% change fraction)

    def test_unmeasurable_fixes_are_ranked_last_and_say_why(self):
        with tempfile.TemporaryDirectory() as d:
            P, smap = self.profile(d)
            P.pop("history")
            fx = pp.price_fixes(P, smap["entries"])
            tail = [f for f in fx if f["per_pr_s"] is None]
            self.assertEqual({f["id"] for f in tail}, {"cache", "affected", "incremental", "move-local", "runner"})
            self.assertEqual(fx[-len(tail):], tail)
            self.assertTrue(all("unverified" in f["basis"] for f in tail))

    def test_runner_fix_gains_nothing_for_a_serial_step(self):
        with tempfile.TemporaryDirectory() as d:
            P, smap = self.profile(d)
            P["local"] = {"rows": [{"stage": "precheck", "name": "scripts/e2e.sh", "key": "scripts/e2e.sh", "n": 1,
                                    "wall_median_s": 10.0, "cpu_median_s": 10.0}], "stage_s": {}}
            serial = {f["id"]: f for f in pp.price_fixes(P, smap["entries"])}["runner"]["per_cycle_s"]
            P["local"]["rows"][0]["cpu_median_s"] = 40.0  # uses 4 cores
            multi = {f["id"]: f for f in pp.price_fixes(P, smap["entries"])}["runner"]["per_cycle_s"]
            self.assertEqual((serial, multi), (0.0, 200.0 * (1 - 1 / 2)))

    def test_noise_floor_keeps_a_tiny_dedup_from_being_the_lever(self):
        with tempfile.TemporaryDirectory() as d:
            local = {(st, "scripts/%s.sh" % k): 0.01 for st in ("commit", "push", "precheck") for k in SUITES}
            P, smap = self.profile(d, local)
            fixes = pp.price_fixes(P, smap["entries"])
            dedup = next(f for f in fixes if f["id"] == "dedup")
            self.assertFalse(dedup["lever"])
            self.assertNotEqual(fixes[0]["id"], "dedup")  # below the floor it is not forced to rank first


class Compare(unittest.TestCase):
    def prof(self, v, n=5):
        return {"ci": {"measured_runs": n, "exec_s": {"median": v}}, "stages_s": {"push": v}}

    def test_keep_only_when_the_time_drops(self):
        m = "ci.exec_s.median"
        self.assertEqual(pp.compare_profiles(self.prof(100.0), self.prof(60.0), m)["verdict"], "KEEP")
        self.assertEqual(pp.compare_profiles(self.prof(100.0), self.prof(100.0), m)["verdict"], "REVERT")
        self.assertEqual(pp.compare_profiles(self.prof(100.0), self.prof(98.0), m)["verdict"], "REVERT")  # inside the 5% noise band
        self.assertEqual(pp.compare_profiles(self.prof(100.0), self.prof(130.0), m)["verdict"], "REVERT")
        self.assertEqual(pp.compare_profiles(self.prof(0.5), self.prof(0.1), m)["verdict"], "REVERT")  # under the 1s floor

    def test_unverified_never_keeps(self):
        m = "ci.exec_s.median"
        self.assertEqual(pp.compare_profiles(self.prof(100.0, 2), self.prof(10.0), m)["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles(self.prof(100.0), {}, m)["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles(self.prof(100.0), self.prof(10.0), "no.such.metric")["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles({"stages_s": {"ci_exec": 100.0}}, {"stages_s": {"ci_exec": 60.0}},
                                             "stages_s.ci_exec")["verdict"], "UNVERIFIED")  # no measured_runs behind it

    def test_a_timed_command_is_compared_by_name_and_needs_repeats(self):
        def prof(v, n):
            rows = [{"stage": "ci", "name": "heavy", "key": None, "n": n, "wall_median_s": v, "cpu_median_s": v}]
            return {"local": {"rows": rows, "stage_s": {}, "by_name": {"heavy": v}}}
        m = "local.by_name.heavy"
        self.assertEqual(pp.compare_profiles(prof(600.0, 3), prof(200.0, 3), m)["verdict"], "KEEP")
        self.assertEqual(pp.compare_profiles(prof(600.0, 1), prof(200.0, 3), m)["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles(prof(600.0, 3), prof(590.0, 3), m)["verdict"], "REVERT")
        self.assertEqual(pp.compare_profiles(prof(600.0, 3), prof(200.0, 3), "local.by_name.other")["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles(prof(600.0, 1), prof(200.0, 1), m, min_n=1)["verdict"], "KEEP")

    def test_a_local_hook_metric_needs_repeated_timings(self):
        def hook(v, n):
            return {"stages_s": {"push": v}, "local": {"rows": [{"stage": "push", "name": "hook:pre-push", "n": n}]}}
        self.assertEqual(pp.compare_profiles(hook(30.0, 1), hook(10.0, 5), "stages_s.push")["verdict"], "UNVERIFIED")
        self.assertEqual(pp.compare_profiles(hook(30.0, 5), hook(10.0, 5), "stages_s.push")["verdict"], "KEEP")
        self.assertEqual(pp.compare_profiles(hook(30.0, 5), {"stages_s": {"push": 10.0}}, "stages_s.push")["verdict"], "UNVERIFIED")

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            for name, v in (("b", 100.0), ("a", 50.0), ("c", 100.0)):
                Path(d, name + ".json").write_text(json.dumps(self.prof(v)))

            def rc(x, y):
                return subprocess.run([sys.executable, TOOL, "compare", os.path.join(d, x + ".json"),
                                       os.path.join(d, y + ".json")], capture_output=True, text=True).returncode
            self.assertEqual((rc("b", "a"), rc("b", "c"), rc("b", "missing")), (0, 1, 2))


class Api(unittest.TestCase):
    class Resp:
        def __init__(self, obj):
            self.b = json.dumps(obj).encode()

        def read(self, *a):
            return self.b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_token_is_an_unredirected_header_and_absent_without_one(self):
        seen = []

        def opener(req, timeout=30):
            seen.append(req)
            return self.Resp({"ok": 1})
        self.assertEqual(pp.api_get("/x", "tok", {"a": 1}, opener), {"ok": 1})
        self.assertEqual(seen[0].unredirected_hdrs["Authorization"], "Bearer tok")
        self.assertNotIn("Authorization", seen[0].headers)  # a redirect would not carry it
        self.assertTrue(seen[0].full_url.endswith("/x?a=1"))
        pp.api_get("/x", None, None, opener)
        self.assertFalse(seen[1].has_header("Authorization"))

    def test_gzip_body_is_decoded_and_a_short_read_is_retried_once(self):
        import gzip
        import http.client
        outer = self

        class Gz(self.Resp):
            def __init__(self):
                super().__init__({"ok": 2})
                self.b, self.headers = gzip.compress(self.b), {"Content-Encoding": "gzip"}

        class Short(self.Resp):
            def read(self, *a):
                raise http.client.IncompleteRead(b"x", 5)
        seen = []

        def gz(req, timeout=30):
            seen.append(req)
            return Gz()
        self.assertEqual(pp.api_get("/x", None, None, gz), {"ok": 2})
        self.assertEqual(seen[0].get_header("Accept-encoding"), "gzip")
        calls = []

        def flaky(req, timeout=30):
            calls.append(1)
            return Short({}) if len(calls) == 1 else outer.Resp({"ok": 3})
        self.assertEqual(pp.api_get("/x", None, None, flaky), {"ok": 3})  # one retry fixes a cut body
        with self.assertRaises(ValueError):
            pp.api_get("/x", None, None, lambda req, timeout=30: Short({}))  # twice cut: raised, not swallowed
        b = pp.fetch_bundle("o/r", {}, 3, opener=lambda req, timeout=30: Short({}))
        self.assertIn("cut short", b["limits"][0])

    def test_rate_limit_keeps_partial_data_and_resumes_without_refetching(self):
        calls = []

        def opener(req, timeout=30):
            calls.append(req.full_url)
            if "/jobs" in req.full_url and len([c for c in calls if "/jobs" in c]) > 1:
                h = email.message.Message()
                h["x-ratelimit-remaining"] = "0"
                h["x-ratelimit-reset"] = "1792165179"
                raise urllib.error.HTTPError(req.full_url, 403, "rate limit", h, None)
            if "/jobs" in req.full_url:
                return self.Resp({"jobs": [{"id": 9, "name": "gates", "steps": []}]})
            return self.Resp({"workflow_runs": [{"id": 1, "created_at": iso(0)}, {"id": 2, "created_at": iso(5)}]})
        b = pp.fetch_bundle("o/r", {}, 2, opener=opener)
        self.assertEqual(sorted(b["jobs"]), ["1"])  # run 2 was cut off by the limit
        self.assertIn("rate limit exhausted", b["limits"][0])
        self.assertIn("1792165179", b["limits"][0])
        n = len(calls)

        def ok(req, timeout=30):
            calls.append(req.full_url)
            return self.Resp({"jobs": [{"id": 10, "name": "gates", "steps": []}]} if "/jobs" in req.full_url else [])
        b2 = pp.fetch_bundle("o/r", b, 2, opener=ok)
        self.assertEqual(sorted(b2["jobs"]), ["1", "2"])
        self.assertEqual(len([c for c in calls[n:] if "/runs/1/jobs" in c]), 0)  # run 1 came from the bundle
        self.assertEqual(b2["limits"], [])

    def test_unreachable_api_is_a_recorded_limit_not_a_crash(self):
        def opener(req, timeout=30):
            raise urllib.error.URLError("offline")
        self.assertIn("unreachable", pp.fetch_bundle("o/r", {}, 3, opener=opener)["limits"][0])


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)

    def test_map_prints_the_duplicates_and_what_to_keep(self):
        with tempfile.TemporaryDirectory() as d:
            fixture_repo(d)
            r = self.run_cli("map", "--root", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("4 at more than one stage", r.stdout)
            self.assertIn("scripts/e2e.sh: keep at ci, drop from commit, push, precheck", r.stdout)
            j = json.loads(self.run_cli("map", "--root", d, "--json").stdout)
            self.assertEqual(len(j["duplicates"]), 4)

    def test_perun_pipeline_json_declares_a_stage_no_file_shows(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, ".githooks/pre-push", "#!/bin/sh\nbash scripts/unit.sh\n", 0o755)
            write(d, ".perun/pipeline.json", json.dumps({"stages": {"train": ["bash scripts/unit.sh"], "bogus": ["x"]}}))
            dup = json.loads(self.run_cli("map", "--root", d, "--json").stdout)["duplicates"][0]
            self.assertEqual((dup["stages"], dup["keep"]), (["push", "train"], "train"))
            write(d, ".perun/pipeline.json", "{not json")
            self.assertEqual(self.run_cli("map", "--root", d).returncode, 2)

    def test_profile_offline_then_fixes_then_compare_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            fixture_repo(d)
            data, out = os.path.join(d, "bundle.json"), os.path.join(d, "p.json")
            Path(data).write_text(json.dumps(bundle()))
            r = self.run_cli("profile", "--root", d, "--repo", "o/r", "--offline", "--data", data, "--out", out,
                             "--log", os.path.join(d, "none.tsv"))
            self.assertEqual(r.returncode, 0, r.stderr)
            for needle in ("PER-STAGE WALL TIME", "BOTTLENECKS", "E2E tests", "first push->merge 18m20s"):
                self.assertIn(needle, r.stdout)
            P = json.loads(Path(out).read_text())
            self.assertEqual(P["ci"]["exec_s"]["median"], 316.0)
            self.assertEqual(P["dominant"]["step"], "E2E tests")  # 200s of the 316s median execution
            self.assertAlmostEqual(P["dominant"]["share"], 200 / 316)
            self.assertIn("DOMINANT STEP: 'E2E tests' is 63% of CI execution", r.stdout)
            f = self.run_cli("fixes", "--root", d, out)
            self.assertEqual(f.returncode, 0, f.stderr)
            self.assertIn("FIX CATALOGUE", f.stdout)
            self.assertIn("DECIDE: measure first -- 12 duplicated stage run(s) are not timed", f.stdout)  # dedup is unpriced
            self.assertNotIn("how:", f.stdout)
            f = self.run_cli("fixes", "--root", d, out, "--accept-unmeasured")
            self.assertIn("DECIDE: shard", f.stdout)  # the best priced fix once the owner accepts the gap
            self.assertEqual(self.run_cli("compare", out, out).returncode, 1)  # no change is not a speed-up

    def test_profile_without_any_data_says_so_and_does_not_invent_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_cli("profile", "--root", d, "--offline", "--log", os.path.join(d, "none.tsv"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("no GitHub data: no origin remote and no --repo", r.stdout)
            self.assertIn("n/a", r.stdout)
            self.assertIn("no measurements", r.stdout)

    def test_bad_declare_and_unreadable_profile_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_cli("map", "--root", d, "--declare", "nope=x").returncode, 2)
            self.assertEqual(self.run_cli("fixes", os.path.join(d, "missing.json")).returncode, 2)
            self.assertEqual(self.run_cli().returncode, 2)

    def test_selftest(self):
        r = self.run_cli("--selftest")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "pipeline_profile selftest: ok"))


class Coherence(unittest.TestCase):
    """The catalogue lives in code and in the procedure doc; the sources in the doc live in the standards index."""

    def test_every_fix_and_source_id_is_documented_and_every_source_url_is_logged(self):
        doc = (ROOT / ".claude/skills/agentic-delivery/references/pipeline-optimizer.md").read_text()
        index = (ROOT / "docs/standards-index.md").read_text()
        for fid, _name, _effort, sources, _fn, _how in pp.FIXES:
            self.assertIn("`%s`" % fid, doc, fid)
            for s in sources:
                self.assertRegex(doc, r"\|\s*`%s`\s*\|\s*(https://\S+)\s*\|" % re.escape(s))
        for url in re.findall(r"\|\s*`[a-z0-9-]+`\s*\|\s*(https://\S+)\s*\|", doc):
            self.assertIn(url, index, url)

    def test_dedup_is_first_in_the_catalogue_and_the_eval_for_it_exists(self):
        self.assertEqual(pp.FIXES[0][0], "dedup")
        evals = json.loads((ROOT / ".claude/skills/agentic-delivery/evals/evals.json").read_text())["evals"]
        ids = {e["id"] for e in evals}
        self.assertTrue({"pipeline-dedup-before-stage-tuning", "pipeline-map-first", "pipeline-moving-a-gate-is-not-weakening"} <= ids)


if __name__ == "__main__":
    unittest.main()
