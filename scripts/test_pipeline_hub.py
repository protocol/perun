#!/usr/bin/env python3
"""Offline tests for pipeline_hub.py: per-workflow and per-job percentiles, per-job flakes from earlier attempts,
duplicate-check detection across CI jobs (enforced check steps only, the same command rather than the same script,
jobs matched on workflow and name, no even-split price), PR lead time,
the gh-workflow-stats adapter and its fallback, collect's resume and its skip of one failed run, the API message in a
gh_get error, the named-job recommendations and the CLI (exit 2 on bad input, the --root checkout gate). Synthetic
data only: no network, no real repo, no real names."""
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SCRIPTS))
import pipeline_hub as hub  # noqa: E402

# No inherited GIT_* (a hook's GIT_DIR/GIT_INDEX_FILE would aim git at the wrong repo), no global git config.
ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "GIT_CONFIG_GLOBAL": os.devnull,
       "GIT_CONFIG_NOSYSTEM": "1"}
BASE = 1_700_000_000
WORKFLOW = """name: gates
on:
  pull_request:
jobs:
  cheap:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules
  unit:
    runs-on: ubuntu-latest
    steps:
      - name: Run unit
        run: |
          bash scripts/ci-gates.sh rules
          python3 scripts/run_unit.py
"""
RELEASE = """name: release
on:
  push:
    tags:
      - 'v*'
jobs:
  ship:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules
"""
ONE_GATE = """name: gates
on:
  pull_request:
jobs:
  cheap:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules
"""
POST_MERGE = """name: post-merge
on:
  push:
    branches: [main]
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules
"""
MAIN_ONLY_COPY = ONE_GATE + """  main-only:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules
"""
BUILD_TWICE = """name: gates
on:
  pull_request:
jobs:
  first:
    runs-on: ubuntu-latest
    steps:
      - run: make
      - run: npm run build
      - run: pytest -q
  second:
    runs-on: ubuntu-latest
    steps:
      - run: make
      - run: npm run build
      - run: pytest -q
"""
ALPHA = """name: alpha
on:
  pull_request:
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - name: Run checks
        run: bash scripts/ci-gates.sh rules
"""
BETA = ALPHA.replace("name: alpha\n", "")  # unnamed: its runs are named after the file path
TWO_GATES = """name: gates
on:
  pull_request:
jobs:
  cheap:
    runs-on: ubuntu-latest
    steps:
      - name: Gate changed files
        run: python3 scripts/fix_class_gate.py --changed
      - name: Gate all files
        run: python3 scripts/fix_class_gate.py --all
"""
SPELLINGS = """name: gates
on:
  pull_request:
jobs:
  first:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check
        run: bash scripts/ci-gates.sh rules --base main
  second:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check again
        run: bash  scripts/ci-gates.sh   rules "--base" 'main' > out.txt 2>&1
  third:
    runs-on: ubuntu-latest
    steps:
      - name: Rule check everything
        run: bash scripts/ci-gates.sh rules --all
"""


def iso(t):
    return datetime.datetime.fromtimestamp(BASE + t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jb(name, dur, concl="success", step=None):
    steps = [{"name": step[0], "number": 1, "conclusion": concl, "started_at": iso(0), "completed_at": iso(step[1])}] if step else []
    return {"id": 1, "name": name, "conclusion": concl, "created_at": iso(0), "started_at": iso(0),
            "completed_at": iso(dur), "steps": steps}


def run(rid, dur, concl="success", attempt=1, pr=1):
    return {"id": rid, "name": "gates", "event": "pull_request", "head_branch": "f%d" % pr, "head_sha": "s%d" % rid,
            "run_attempt": attempt, "run_started_at": iso(0), "created_at": iso(0), "updated_at": iso(dur),
            "conclusion": concl, "status": "completed", "prs": [pr], "msg": "x"}


def bundle():
    runs = [run(1, 400), run(2, 500), run(3, 600, "failure"), run(4, 700, attempt=2)]
    jobs = {str(r["id"]): [jb("cheap", 60), jb("unit", r["updated_at"] and 300 + 50 * r["id"], step=("Run unit", 280))]
            for r in runs}
    jobs["3"][1]["conclusion"] = "failure"
    return {"runs": runs, "jobs": jobs, "prior": {"4/1": [jb("cheap", 60), jb("unit", 200, "failure")]},
            "pulls": [{"number": 1, "created_at": iso(0), "merged_at": iso(1000), "head_ref": "f1"},
                      {"number": 2, "created_at": iso(0), "merged_at": iso(3000), "head_ref": "f2"},
                      {"number": 3, "created_at": iso(0), "merged_at": None, "head_ref": "f3"}]}


class Hub(unittest.TestCase):
    def checkout(self, origin=None, **files):
        """A temp git checkout holding .github/workflows/<key>.yml per keyword, with an `origin` remote when given."""
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        wd = Path(d.name, ".github/workflows")
        wd.mkdir(parents=True)
        for key, text in files.items():
            (wd / (key + ".yml")).write_text(text)
        subprocess.run(["git", "init", "-q", d.name], check=True, capture_output=True, env=ENV)
        if origin:
            subprocess.run(["git", "-C", d.name, "remote", "add", "origin", origin], check=True, capture_output=True, env=ENV)
        return d

    def setUp(self):
        self.tmp = self.checkout("https://github.com/o/r.git", ci=WORKFLOW, release=RELEASE)

    def cli(self, *args, root=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "pipeline_hub.py"), "--root", root or self.tmp.name, *args],
                              capture_output=True, text=True, env=ENV)

    def data(self, name="b.json", text=None):
        p = Path(self.tmp.name, name)
        p.write_text(json.dumps(bundle()) if text is None else text)
        return str(p)

    def test_workflow_stats(self):
        w = hub.workflow_stats(bundle())[0]
        self.assertEqual((w["workflow"], w["runs"], w["p50_s"], w["p90_s"]), ("gates", 4, 550, 700))
        self.assertEqual((w["fail_rate"], w["rerun_rate"], w["flake_suspects"]), (0.25, 0.25, 1))

    def test_job_stats_flake_and_top_step(self):
        j = {x["job"]: x for x in hub.job_stats(bundle())}
        self.assertEqual(list(j)[0], "unit")  # slowest first
        self.assertEqual((j["unit"]["flakes"], j["cheap"]["flakes"]), (1, 0))
        self.assertEqual((j["unit"]["top_step"], j["unit"]["top_step_s"]), ("Run unit", 280))
        self.assertEqual(j["unit"]["fail_rate"], 0.25)

    def test_rerun_without_its_earlier_attempts_is_n_a_not_zero(self):
        b = bundle()
        b["prior"] = {}  # run 4 is attempt 2 and its attempt 1 was never fetched: a flake cannot be ruled out
        j = {x["job"]: x for x in hub.job_stats(b)}
        self.assertEqual((j["unit"]["flakes"], j["cheap"]["flakes"]), (None, None))
        rep = hub.build("o/r", self.tmp.name, b)
        self.assertNotIn("flaky-job", [r["kind"] for r in rep["recs"]])
        row = next(l for l in hub.render(rep).splitlines() if l.split()[:2] == ["gates", "unit"])
        self.assertTrue(row.endswith("n/a"), row)
        c = bundle()
        c["prior"], c["runs"][3]["run_attempt"] = {}, 1  # no re-run at all: a real zero, not n/a
        self.assertEqual({x["job"]: x["flakes"] for x in hub.job_stats(c)}, {"unit": 0, "cheap": 0})

    def test_cancelled_and_skipped_ignored(self):
        b = bundle()
        b["runs"].append(run(9, 9999, "cancelled"))
        self.assertEqual(hub.workflow_stats(b)[0]["runs"], 4)

    def test_dup_jobs_only_pr_workflows_and_a_multi_command_step_is_not_priced(self):
        d = hub.dup_jobs(self.tmp.name, hub.job_stats(bundle()))
        self.assertEqual([x["suite"] for x in d], ["scripts/ci-gates.sh rules"])  # release.yml (tag push) is no gate
        self.assertEqual((d[0]["keep"]["job"], d[0]["drop"][0]["job"]), ("cheap", "unit"))  # lower p50 kept
        # `Run unit` (280s) runs two commands: an even split (140s) is not the suite's own time, so nothing is priced
        self.assertEqual((d[0]["drop"][0]["step_p50_s"], d[0]["saved_s"]), (None, None))

    def test_dup_ignores_a_post_merge_push_and_an_unproven_if(self):
        gate_and_post_merge = self.checkout(gates=ONE_GATE, post=POST_MERGE)  # the push-to-main copy is not a PR gate
        self.assertEqual(hub.dup_jobs(gate_and_post_merge.name, []), [])
        maybe_skipped = self.checkout(gates=MAIN_ONLY_COPY)  # an `if:` we cannot read may skip the copy
        self.assertEqual(hub.dup_jobs(maybe_skipped.name, []), [])

    def test_dup_flags_checks_not_builds(self):
        d = hub.dup_jobs(self.checkout(gates=BUILD_TWICE).name, [])  # a second `make` or build is needed by what follows
        self.assertEqual([x["suite"] for x in d], ["pytest"])

    def test_same_script_with_different_arguments_is_an_advisory_not_a_duplicate(self):
        root = self.checkout(gates=TWO_GATES).name  # two gates, one script, two flag sets, both steps timed
        rows = [{"workflow": "gates", "job": "cheap", "p50_s": 60,
                 "step_p50": {"Gate changed files": 40.0, "Gate all files": 30.0}}]
        d, = hub.dup_jobs(root, rows)
        self.assertEqual((d["suite"], d.get("identical"), d["saved_s"]), ("scripts/fix_class_gate.py", False, None))
        text, = [r["text"] for r in hub.recommend([], [], [d], {})]
        self.assertIn("same suite, different arguments: check one covers the other before dropping", text)
        for word in ("keep the first", "drop the second", "saves", "unmeasured", "40.0s", "30.0s"):  # no drop, no price
            self.assertNotIn(word, text)
        out = hub.render(hub.build("o/r", root, bundle()))
        self.assertIn("scripts/fix_class_gate.py: different arguments in `cheap`, `cheap` (advisory", out)
        self.assertNotIn("keep in", out)

    def test_identical_command_is_a_duplicate_however_it_is_spelled(self):
        root = self.checkout(gates=SPELLINGS).name  # extra spaces, quotes and a redirect do not make another command
        d, = hub.dup_jobs(root, [])  # `rules --all` in a third job is another command: not part of this duplicate
        self.assertEqual((d["suite"], d.get("identical")), ("scripts/ci-gates.sh rules", True))
        self.assertEqual([r["job"] for r in [d["keep"]] + d["drop"]], ["first", "second"])

    def test_a_lone_command_step_is_priced_from_its_own_median(self):
        rows = [{"workflow": "gates", "job": "cheap", "p50_s": 500, "step_p50": {"Rule check": 45.1}},  # one command
                {"workflow": "gates", "job": "unit", "p50_s": 100, "step_p50": {"Run unit": 180.0}}]
        d, = hub.dup_jobs(self.tmp.name, rows)  # `cheap` is the dropped copy
        self.assertEqual((d["keep"]["job"], d["drop"][0]["step_p50_s"], d["saved_s"]), ("unit", 45.1, 45.1))
        self.assertIn("saves at most about 45.1s per run (its step's median).", hub.recommend([], [], [d], {})[0]["text"])

    def test_a_multi_command_step_is_unmeasured_not_split_evenly(self):
        rows = [{"workflow": "gates", "job": "cheap", "p50_s": 100, "step_p50": {"Rule check": 45.1}},
                {"workflow": "gates", "job": "unit", "p50_s": 500, "step_p50": {"Run unit": 180.0}}]  # two commands
        d, = hub.dup_jobs(self.tmp.name, rows)  # `unit` is the dropped copy
        self.assertEqual((d["keep"]["step_p50_s"], d["drop"][0]["step_p50_s"], d["saved_s"]), (45.1, None, None))
        text = hub.recommend([], [], [d], {})[0]["text"]
        self.assertIn("the suite's own time is unmeasured: time it locally to price the saving.", text)
        for word in ("even split", "saves", "1m30s", "3m00s"):  # the 90s split, the whole 180s step
            self.assertNotIn(word, text)
        rep = hub.build("o/r", self.tmp.name, bundle())  # end to end: `Run unit` has a 280s median over two commands
        self.assertIn("scripts/ci-gates.sh rules: keep in `cheap`; also in `unit`", hub.render(rep))  # line unchanged
        self.assertTrue(all("saves" not in r["text"] for r in rep["recs"] if r["kind"] == "duplicate-job"))

    def test_is_check_tells_a_check_from_a_build_or_setup_step(self):
        for line, want in (("pytest -q", True), ("npm run lint", True), ("make test", True), ("cargo test", True),
                           ("go vet ./...", True), ("bash scripts/ci-gates.sh rules", True),
                           ("make", False), ("make build", False), ("npm run build", False), ("cargo build", False),
                           ("python3 -m build", False), ("bash scripts/regen-unlanded.sh", False),
                           ("python3 scripts/inspect_logs.py", False)):  # `inspect` is not `spec`
            (_, key, _b), = hub.pp.commands(line)
            self.assertEqual(hub.is_check(key), want, line)

    def test_same_named_jobs_in_two_workflows_keep_their_own_numbers(self):
        root = self.checkout(alpha=ALPHA, beta=BETA).name
        rows = [{"workflow": "alpha", "job": "unit (3.11)", "p50_s": 280, "step_p50": {"Run checks": 90}},
                {"workflow": "alpha", "job": "unit (3.12)", "p50_s": 300, "step_p50": {"Run checks": 100}},
                {"workflow": ".github/workflows/beta.yml", "job": "unit", "p50_s": 50, "step_p50": {"Run checks": 5}}]
        d = hub.dup_jobs(root, rows)
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["keep"]["workflow_file"], d[0]["drop"][0]["workflow_file"]), ("beta.yml", "alpha.yml"))
        self.assertEqual((d[0]["keep"]["job_p50_s"], d[0]["drop"][0]["job_p50_s"]), (50, 300))  # matrix legs: the slowest
        self.assertEqual((d[0]["keep"]["step_p50_s"], d[0]["saved_s"]), (5, 100))  # not beta's 5s mixed into alpha's cost

    def test_lead_stats(self):
        ld = hub.lead_stats(bundle())
        self.assertEqual((ld["prs"], ld["open_to_merge_p50_s"], ld["open_to_merge_p90_s"]), (2, 2000, 3000))

    def test_recommendations_name_the_job(self):
        b = bundle()
        b["pulls"][0]["merged_at"] = iso(1500)  # PR 1 waits 800s after its last green run: the lead-time rec fires too
        rep = hub.build("o/r", self.tmp.name, b)
        by = {r["kind"]: r for r in rep["recs"]}
        self.assertEqual(set(by), {"duplicate-job", "slowest-job", "red-job", "flaky-job", "rerun-rate", "lead-time"})
        self.assertIn("`unit`", by["duplicate-job"]["text"])
        self.assertEqual((by["slowest-job"]["target"], by["red-job"]["target"], by["flaky-job"]["target"],
                          by["rerun-rate"]["target"], by["lead-time"]["target"]),
                         ("unit", "unit", "unit", "gates", "merge gate"))
        self.assertTrue(all("`%s`" % r["target"] in r["text"] for r in rep["recs"]))  # every rec names its target
        self.assertIn("RECOMMENDATIONS", hub.render(rep))

    def test_lead_time_rec_needs_a_big_post_green_wait(self):
        kinds = lambda b: [r["kind"] for r in hub.build("o/r", self.tmp.name, b)["recs"]]  # noqa: E731
        self.assertEqual(hub.lead_stats(bundle())["post_green_wait_s"], 300)  # 300s of a 2000s p50: under the share
        self.assertNotIn("lead-time", kinds(bundle()))
        b = bundle()
        b["pulls"][0]["merged_at"] = iso(1500)
        self.assertEqual(hub.lead_stats(b)["post_green_wait_s"], 800)  # 800s of a 2250s p50
        self.assertIn("lead-time", kinds(b))

    def test_dup_below_floor_is_listed_not_recommended(self):
        d = [{"suite": "k", "keep": {"job": "a", "step": "s"},
              "drop": [{"job": "b", "step": "s", "workflow_file": "ci.yml", "step_p50_s": 1.0}], "saved_s": 1.0}]
        self.assertEqual(hub.recommend([], [], d, {}), [])

    def test_oss_adapter_parses_documented_json(self):
        out = {"workflow_jobs_stats_summary": [
            {"name": "unit", "total_runs_count": 10, "rate": {"success_rate": 0.9, "failure_rate": 0.1, "others_rate": 0},
             "execution_duration_stats": {"min": 1, "max": 400, "avg": 300, "med": 250, "std": 5}, "steps_summary": []}]}
        calls = []

        def fake(argv, **kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")

        rows, why = hub.oss_jobs("o/r", self.tmp.name, run=fake)
        self.assertIsNone(why)
        self.assertEqual((rows[0]["job"], rows[0]["p50_s"], rows[0]["tail"], rows[0]["tail_s"], rows[0]["fail_rate"]),
                         ("unit", 250, "max", 400, 0.1))
        self.assertEqual(calls[0][:3], ["gh", "workflow-stats", "jobs"])
        rep = hub.build("o/r", self.tmp.name, bundle(), oss=rows)
        self.assertEqual(rep["slowest_jobs"][0]["tail"], "max")
        self.assertIn("gh-workflow-stats", rep["source"])
        self.assertIn("successful runs only", " ".join(rep["notes"]))

    def test_oss_missing_or_unreadable_falls_back(self):
        miss = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", 'unknown command "workflow-stats" for "gh"')
        junk = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "not json", "")
        gone = lambda argv, **kw: (_ for _ in ()).throw(FileNotFoundError("gh"))
        for fake in (miss, junk, gone):
            rows, why = hub.oss_jobs("o/r", self.tmp.name, run=fake)
            self.assertIsNone(rows)
            rep = hub.build("o/r", self.tmp.name, bundle(), oss=rows, notes=[why])
            self.assertEqual(rep["source"], "gh API sample")
            self.assertTrue(why in rep["notes"])

    @staticmethod
    def api(seen, pulls=True):
        """Stub for the REST reads `collect` makes; /pulls raises OSError when `pulls` is False."""
        def get(path, params=None):
            seen.append(path)
            if path.endswith("/actions/runs"):
                return {"workflow_runs": [run(1, 100), run(2, 100, attempt=2)]}
            if "/attempts/1/jobs" in path:
                return {"jobs": [jb("unit", 5, "failure")]}
            if path.endswith("/jobs"):
                return {"jobs": [jb("unit", 5)]}
            if path.endswith("/pulls") and pulls:
                return [{"number": 7, "created_at": iso(0), "merged_at": iso(900), "head": {"ref": "f7"}},
                        {"number": 8, "created_at": iso(0), "merged_at": None, "head": {"ref": "f8"}}]
            raise OSError("rate limited")
        return get

    def test_collect_parses_the_api_and_resumes_without_refetching(self):
        seen = []
        b = hub.collect("o/r", {}, 2, 10, get=self.api(seen))
        self.assertEqual((sorted(b["jobs"]), list(b["prior"]), b["limits"]), (["1", "2"], ["2/1"], []))
        self.assertEqual(b["pulls"], [{"number": 7, "created_at": iso(0), "merged_at": iso(900), "head_ref": "f7"}])  # merged only
        self.assertEqual(b["pulls_pages"], 1)
        n = len(seen)
        hub.collect("o/r", b, 2, 10, get=self.api(seen))  # resume: runs, jobs, prior and the pulls page are not fetched again
        self.assertEqual(len(seen), n)

    def test_collect_records_a_failed_call_instead_of_raising(self):
        seen = []
        b = hub.collect("o/r", {}, 2, 10, get=self.api(seen, pulls=False))
        self.assertIn("rate limited", b["limits"][0])  # /pulls failed: recorded, not raised
        self.assertEqual((sorted(b["jobs"]), b["pulls"]), (["1", "2"], []))
        n = len(seen)
        b = hub.collect("o/r", b, 2, 10, get=self.api(seen))  # resume: only /pulls is fetched
        self.assertEqual((len(seen) - n, b["limits"], len(b["pulls"])), (1, [], 1))

    def test_collect_skips_a_run_whose_call_fails_and_keeps_going(self):
        """GitHub answers HTTP 502 for one run's /jobs every time (run 2) and for one earlier attempt (run 3): each is
        named once in limits, the other runs and the pulls are still collected, and a re-run retries only the two."""
        seen, ok = [], self.api([])

        def get(path, params=None):
            if path.endswith("/actions/runs"):
                return {"workflow_runs": [run(i, 100, attempt=2 if i in (2, 3) else 1) for i in (1, 2, 3, 4)]}
            if "/runs/2/" in path or "/runs/3/attempts/" in path:
                seen.append(path)
                raise OSError("Server Error (HTTP 502)")
            return ok(path, params)

        b = hub.collect("o/r", {}, 4, 10, get=get)
        self.assertEqual((sorted(b["jobs"]), list(b["prior"]), len(b["pulls"])), (["1", "3", "4"], [], 1))
        self.assertEqual(seen, ["/repos/o/r/actions/runs/2/jobs", "/repos/o/r/actions/runs/3/attempts/1/jobs"])  # run 2: no attempts call after its jobs call failed
        self.assertEqual(len(b["limits"]), 2)
        for line, rid in zip(b["limits"], "23"):
            self.assertIn("run %s " % rid, line)
            self.assertIn("Server Error (HTTP 502)", line)
            self.assertNotIn("collection stopped", line)
        seen.clear()
        b = hub.collect("o/r", b, 4, 10, get=self.api(seen))  # resume: only what failed is fetched again
        self.assertEqual((seen, b["limits"], sorted(b["jobs"]), sorted(b["prior"])),
                         (["/repos/o/r/actions/runs/2/jobs", "/repos/o/r/actions/runs/2/attempts/1/jobs",
                           "/repos/o/r/actions/runs/3/attempts/1/jobs"], [], ["1", "2", "3", "4"], ["2/1", "3/1"]))

    def test_collect_still_stops_when_the_runs_list_fails(self):
        def get(path, params=None):
            raise OSError("Server Error (HTTP 502)")
        b = hub.collect("o/r", {}, 2, 10, get=get)
        self.assertEqual((b["runs"], b["jobs"], b["pulls"]), ([], {}, []))
        self.assertTrue(b["limits"][0].startswith("collection stopped: Server Error (HTTP 502)"), b["limits"])

    def test_gh_get_parses_raises_and_uses_the_tls_fallback(self):
        done = lambda rc, out="", err="": subprocess.CompletedProcess([], rc, out, err)
        with mock.patch.object(hub.subprocess, "run", return_value=done(0, '{"a": 1}')) as r:
            self.assertEqual(hub.gh_get("/repos/o/r/x", {"per_page": 5}), {"a": 1})
        self.assertEqual(r.call_args[0][0], ["gh", "api", "/repos/o/r/x?per_page=5"])
        with mock.patch.object(hub.subprocess, "run", return_value=done(1, "", "HTTP 404: Not Found\nsecond line")):
            with self.assertRaisesRegex(OSError, "second line"):  # a real error is raised, not retried through curl
                hub.gh_get("/repos/o/r/x")
        tls = done(1, "", "tls: failed to verify certificate: x509: OSStatus -26276")
        with mock.patch.object(hub.subprocess, "run", return_value=tls), \
                mock.patch.object(hub.gh_rest, "fallback", return_value=(0, '{"b": 2}', "")) as fb:
            self.assertEqual(hub.gh_get("/repos/o/r/y"), {"b": 2})
        self.assertEqual(fb.call_args[0][:2], (["gh", "api", "/repos/o/r/y"], 1))

    def test_gh_get_error_names_the_api_message_not_a_bare_brace(self):
        body = '{\n  "message": "Server Error"\n}\n'
        for triple, want in (((1, body, "gh: Server Error (HTTP 502)\n"), "Server Error (HTTP 502)"),  # gh's own line
                             ((1, "", "HTTP 502: " + body), "Server Error (HTTP 502)"),  # the curl fallback keeps the body: last line is "}"
                             ((1, "", body), "Server Error"),  # no status in the text: none is invented
                             ((1, "", "gh: HTTP 502\nsecond line"), "second line"),  # no message at all: the last line, as before
                             ((1, "", " \n"), "gh api failed")):  # blank stderr: a fixed text, not an IndexError
            with mock.patch.object(hub.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")), \
                    mock.patch.object(hub.gh_rest, "fallback", return_value=triple):
                with self.assertRaises(OSError) as c:
                    hub.gh_get("/repos/o/r/x")
            self.assertEqual(str(c.exception), want)

    def test_cli_offline_json(self):
        for args, repo in (([], "o/r"), (["--repo", "O/r"], "O/r")):  # --repo defaults to the origin; case is ignored
            p = self.cli(*args, "--data", self.data(), "--offline", "--json")
            self.assertEqual(p.returncode, 0, p.stderr)
            rep = json.loads(p.stdout)
            self.assertEqual((rep["repo"], rep["workflows"][0]["workflow"], rep["notes"]), (repo, "gates", []))
        self.assertEqual(self.cli("--repo", "o/r", "--offline").returncode, 2)  # no data: nothing to analyse

    def test_cli_root_must_be_a_checkout_of_the_repo(self):
        other = self.checkout("https://github.com/x/y.git", ci=WORKFLOW)
        p = self.cli("--repo", "o/r", "--data", self.data(), "--offline", root=other.name)  # y's workflows, o/r's runs
        self.assertEqual(p.returncode, 2)
        self.assertIn("is a checkout of x/y, not o/r", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        bare = self.checkout(ci=WORKFLOW)  # no origin: unverifiable, so labelled instead of refused
        p = self.cli("--repo", "o/r", "--data", self.data(), "--offline", "--json", root=bare.name)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no github.com origin", " ".join(json.loads(p.stdout)["notes"]))
        self.assertEqual(self.cli("--data", self.data(), "--offline", root=bare.name).returncode, 2)  # and no --repo

    def test_cli_bad_input_exits_2_with_a_message_not_a_traceback(self):
        good = self.data()
        for why, args, want in (
                ("corrupt --data", ["--data", self.data("c.json", "{not json"), "--offline"], "JSONDecodeError"),
                ("--data is a list", ["--data", self.data("l.json", "[1]"), "--offline"], "not a JSON object"),
                ("--data has the wrong shape", ["--data", self.data("s.json", '{"runs": [{"id": 1}], "jobs": "x"}'),
                                                "--offline"], "pipeline_hub: KeyError"),
                ("--data is a directory", ["--data", self.tmp.name, "--offline"], "pipeline_hub:"),
                ("bare --repo", ["--repo", "r", "--data", good, "--offline"], "must be OWNER/NAME"),
                ("missing --root", ["--data", good, "--offline"], "is not a directory")):
            p = self.cli(*args, root=str(Path(self.tmp.name, "gone")) if why == "missing --root" else None)
            self.assertEqual(p.returncode, 2, "%s: %s" % (why, p.stderr))
            self.assertIn(want, p.stderr, why)
            self.assertNotIn("Traceback", p.stderr, why)

    def test_cli_unwritable_data_exits_2(self):
        err = io.StringIO()
        gone = str(Path(self.tmp.name, "no/such/dir/b.json"))
        fill = lambda repo, b, *a, **k: b.update(runs=[run(1, 100)])  # collect without the network  # noqa: E731
        with mock.patch.dict(os.environ, ENV, clear=True), mock.patch.object(hub, "collect", fill), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            hub.main(["--repo", "o/r", "--root", self.tmp.name, "--data", gone, "--no-oss"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("FileNotFoundError", err.getvalue())


if __name__ == "__main__":
    unittest.main()
