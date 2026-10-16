#!/usr/bin/env python3
"""Tests for ci_cost_advisor.py, the `ci` policy key, `ci_cost_lint.py --advise` and the pre-push re-push notice.
Offline: the github.com visibility probe is stubbed, every repo is a throwaway temp dir."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
DR = ROOT / ".claude/skills/deep-code-review/scripts"
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
HOOK = ROOT / ".claude/skills/deep-code-review/templates/pre-push-verify.sh"
sys.path[:0] = [str(DR), str(AD)]
import ci_cost_advisor as A  # noqa: E402
import ci_cost_lint as L  # noqa: E402
import perun_policy as P  # noqa: E402

for _k in [k for k in os.environ if k.startswith("GIT_") or k in ("PERUN_POLICY", "PERUN_GITHUB_ACTIONS", "DCR_PREPUSH_CMD")]:
    del os.environ[_k]  # a hook or lane that runs these tests must not leak its repo or policy into them
os.environ.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)


def _no_network(url):
    raise AssertionError(f"unexpected visibility probe: {url}")


A._http_status = _no_network  # a test that wants the probe patches it explicitly

MATRIX = """name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.11", "3.12"]
    steps:
      - run: pytest
"""
UNIT = """name: unit
on: [push, pull_request]
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
"""
PR_ONLY = """name: tiny
on:
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
LINT = """name: lint
on:
  pull_request:
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: ruff check .
"""
NIGHTLY = """name: nightly
on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:
jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - run: ./probe.sh
"""
TAGS = """name: release
on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - run: gh release create
"""
BLOCK_SCALAR_ON = """name: dispatch
on:
  push:
  pull_request:
  workflow_dispatch:
    inputs:
      note:
        description: |
          multi
          line
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo
"""
W = ".github/workflows/"
DOC_HISTORY = [frozenset({"src/a.py"})] * 7 + [frozenset({"README.md"}), frozenset({"docs/x/y.md", "docs/z.md"}), frozenset({"CHANGELOG.md"})]
MD_IS_THE_PRODUCT = [frozenset({"skills/a.md"})] * 9 + [frozenset({"src/x.py"})]


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@example.com", "-c", "user.name=T", *a],
                          capture_output=True, text=True, check=True).stdout


def make_repo(files, use_git=False):
    """A temp repo whose .github/workflows holds {name: text}; committed when use_git."""
    d = Path(tempfile.mkdtemp(prefix="ci-advisor-test-"))
    (d / ".github/workflows").mkdir(parents=True)
    for name, text in files.items():
        (d / ".github/workflows" / name).write_text(text)
    if use_git:
        (d / "README").write_text("x")
        git(d, "init", "-q", "-b", "main")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "base")
    return d


def advise(root, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = A.main([str(root), *args])
    return rc, out.getvalue(), err.getvalue()


def runs(text, ctx):
    return A.monthly_runs(L._normalize_on(L.parse_workflow_yaml(text).get("on")), ctx, ctx.pushes)[0]


class Pricing(unittest.TestCase):
    def test_rates_and_allowances_match_the_dated_standards_index(self):
        idx = (ROOT / "docs/standards-index.md").read_text()
        sec = idx[idx.index("(2026-10-16) — GitHub Actions prices"):]
        for cls, rate in A.RATES.items():
            self.assertIn(f"${rate:.3f}", sec, cls)
        for plan, n in A.PLANS.items():
            self.assertIn(f"{n:,}", sec, plan)

    def test_runner_labels(self):
        want = {"ubuntu-latest": "linux", "ubuntu-22.04": "linux", "ubuntu-24.04-arm": "linux-arm", "ubuntu-slim": "linux-slim",
                "windows-latest": "windows", "windows-11-arm": "windows", "macos-14": "macos", "macos-15-intel": "macos",
                "self-hosted": "self-hosted", "ubuntu-latest-8-cores": None, "macos-latest-xlarge": None, "my-runners": None}
        for label, cls in want.items():
            self.assertEqual(A.runner_class(label), cls, label)

    def test_matrix_is_priced_per_runner_class(self):
        rows, tot = A.estimate({W + "ci.yml": MATRIX}, A.Ctx(prs=10, pushes=3))
        self.assertEqual(rows[0].per_run, {"linux": 10, "windows": 10, "macos": 10})  # 6 legs, 2 per OS, 5 min each
        self.assertAlmostEqual(A.list_price(tot), 70 * 10 * (0.006 + 0.010 + 0.062))  # 10 + 30 push runs, 30 PR runs
        self.assertNotIn(None, tot)  # every label resolved to a rate

    def test_every_job_is_rounded_up_to_a_whole_minute_and_capped_by_its_timeout(self):
        rows, _ = A.estimate({W + "ci.yml": MATRIX}, A.Ctx(mins={"*": 0.2}))
        self.assertEqual(rows[0].per_run, {"linux": 2, "windows": 2, "macos": 2})  # a 12 s job bills 1 min per leg
        capped = "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 3\n    steps:\n      - run: x\n"
        self.assertEqual(A.estimate({W + "a.yml": capped}, A.Ctx())[0][0].per_run, {"linux": 3})
        self.assertEqual(A.estimate({W + "a.yml": capped}, A.Ctx(mins={"*": 9, "a.yml:a": 2}))[0][0].per_run, {"linux": 2})

    def test_unpriced_and_free_runners(self):
        big = "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest-8-cores\n    steps:\n      - run: x\n"
        own = "on: pull_request\njobs:\n  a:\n    runs-on: [self-hosted, linux]\n    steps:\n      - run: x\n"
        call = "on: pull_request\njobs:\n  a:\n    uses: ./.github/workflows/b.yml\n"
        self.assertEqual(A.estimate({W + "a.yml": big}, A.Ctx(prs=1, pushes=1))[1], {None: 5})
        self.assertEqual(A.list_price(A.estimate({W + "a.yml": own}, A.Ctx(prs=1, pushes=1))[1]), 0)
        rows, tot = A.estimate({W + "a.yml": call}, A.Ctx())
        self.assertEqual(tot, {})
        self.assertIn("reusable workflow", rows[0].notes[0])

    def test_include_only_axis_values_are_priced(self):
        wf = ("on: pull_request\njobs:\n  a:\n    runs-on: ${{ matrix.os }}\n    strategy:\n      matrix:\n        include:\n"
              "          - os: ubuntu-latest\n          - os: macos-latest\n    steps:\n      - run: x\n")
        self.assertEqual(A.estimate({W + "a.yml": wf}, A.Ctx())[0][0].per_run, {"linux": 5, "macos": 5})

    def test_billed_is_zero_on_public_and_nets_the_included_minutes_on_private(self):
        mins = {"linux": 10000}
        self.assertEqual(A.billed(mins, A.Ctx(private=False)), 0.0)
        self.assertAlmostEqual(A.billed(mins, A.Ctx(private=True, allowance=A.PLANS["free"])), (10000 - 2000) * 0.006)
        self.assertEqual(A.billed({"linux": 100}, A.Ctx(private=True)), 0.0)


class Triggers(unittest.TestCase):
    def test_push_and_pull_request_double_trigger(self):
        r = runs(UNIT, A.Ctx(prs=20, pushes=3))
        self.assertEqual(r, {"pull_request": 60, "push (default branch)": 20, "push (PR branches)": 60})

    def test_branch_filter_removes_the_pr_branch_pushes(self):
        wf = UNIT.replace("on: [push, pull_request]", "on:\n  push:\n    branches: [main]\n  pull_request:")
        self.assertEqual(runs(wf, A.Ctx(prs=20, pushes=3)), {"pull_request": 60, "push (default branch)": 20})

    def test_pull_request_types_are_respected(self):
        wf = "on:\n  pull_request:\n    types: [opened]\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: x\n"
        self.assertEqual(runs(wf, A.Ctx(prs=20, pushes=3)), {"pull_request": 20})

    def test_schedule_and_cron(self):
        self.assertAlmostEqual(A.cron_runs("0 2 * * *"), 365 / 12)
        self.assertAlmostEqual(A.cron_runs("*/15 * * * *"), 96 * 365 / 12)
        self.assertAlmostEqual(A.cron_runs("0 0 * * 1"), 365 / 12 / 7)
        self.assertEqual(A.cron_runs("0 0 1 * *"), 1)
        self.assertIsNone(A.cron_runs("0 0 * * MON"))
        self.assertAlmostEqual(runs(NIGHTLY, A.Ctx())["schedule"], 365 / 12)

    def test_tag_pushes_count_the_matching_tags_in_the_window(self):
        self.assertEqual(runs(TAGS, A.Ctx(tags=["v1.2.3", "v1.2.4", "nightly", "v1.x"])), {"push (tags)": 2})

    def test_path_filters_use_the_recent_history(self):
        wf = LINT.replace("pull_request:", "pull_request:\n    paths-ignore: ['**.md', 'docs/**']")
        self.assertEqual(runs(wf, A.Ctx(prs=10, pushes=3, files=DOC_HISTORY)), {"pull_request": 21})
        paths = LINT.replace("pull_request:", "pull_request:\n    paths:\n      - 'src/**'\n      - '!src/docs/**'")
        hist = [frozenset({"src/a.py"}), frozenset({"src/docs/a.md"}), frozenset({"README.md"}), frozenset({"src/docs/a.md", "src/b.py"})]
        self.assertEqual(runs(paths, A.Ctx(prs=4, pushes=1, files=hist)), {"pull_request": 2})

    def test_hostile_filter_patterns_cannot_hang_the_matcher(self):
        start = time.time()
        for pat in ("**a" * 12 + "b", "a+" * 40 + "b", "[a-z]+" * 40 + "!", "*a" * 30 + "b"):  # regex backtracking bait
            self.assertFalse(A._glob(pat, "a" * 400), pat)
        self.assertLess(time.time() - start, 2)
        self.assertTrue(A._glob("[a-z]+" * 3, "abcdef"))
        self.assertFalse(A._glob("[z-a]x", "ax"))  # an invalid class is a literal, never an exception

    def test_filter_pattern_semantics(self):
        for pat, s, want in [("**.md", "README.md", True), ("**.md", "a/b.md", True), ("*.md", "docs/a.md", False), ("docs/**", "docs/a/b.md", True),
                             ("v[0-9]+.[0-9]+", "v1.22", True), ("v?1", "v1", True), ("main", "main2", False), ("a.b", "axb", False)]:
            self.assertEqual(A._glob(pat, s), want, (pat, s))
        self.assertFalse(A._select(["src/**", "!src/docs/**"], "src/docs/x.md"))
        self.assertTrue(A._select(["src/**", "!src/docs/**", "src/docs/keep.md"], "src/docs/keep.md"))


class Plan(unittest.TestCase):
    def test_public_repo_is_free_and_says_so(self):
        d = make_repo({"ci.yml": MATRIX})
        rc, out, _ = advise(d, "--visibility", "public", "--prs", "20")
        self.assertEqual(rc, 0)
        self.assertIn("VERDICT: FREE. Public repo on standard runners", out)
        self.assertIn("costs $0", out)
        self.assertNotIn("Plan (local-first)", out)
        self.assertNotIn("Patch (not applied)", out)
        self.assertEqual(advise(d, "--visibility", "public", "--decide")[1].strip(), "cloud")

    def test_public_repo_with_an_unpriced_runner_is_flagged(self):
        d = make_repo({"a.yml": "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest-8-cores\n    steps:\n      - run: x\n"})
        self.assertIn("cannot price", advise(d, "--visibility", "public", "--prs", "2")[1])

    def test_private_report_has_before_after_plan_and_patch(self):
        d = make_repo({"ci.yml": MATRIX, "unit.yml": UNIT, "nightly.yml": NIGHTLY})
        rc, out, _ = advise(d, "--visibility", "private", "--prs", "20", "--required", "ci.yml")
        self.assertEqual(rc, 0)
        self.assertIn("VERDICT: COSTS MONEY", out)
        for want in ("Before (", "After (", "apply the patch", "push each PR once", "shrunk to 1 min", "Plan (local-first)",
                     "Patch (not applied)", "[required]", "Windows/macOS legs", "runs ~30/mo on a schedule", "assumed"):
            self.assertIn(want, out)
        self.assertIn("no local gate found", out)  # a temp repo has no pre-push hook: workflows stay in Actions

    def test_unknown_required_is_conservative(self):
        d = make_repo({"unit.yml": UNIT})
        self.assertIn("treated as possibly required", advise(d, "--visibility", "private", "--prs", "20")[1])
        patch = advise(d, "--patch")[1]
        self.assertIn("+      - main", patch)  # the double trigger is safe to remove
        self.assertNotIn("workflow_dispatch", patch)  # leaving Actions needs --required and a local gate

    def test_required_known_and_local_gate_moves_a_non_required_test_workflow_to_dispatch(self):
        ctx = A.Ctx(required=frozenset({"ci.yml"}), local_gate=True)
        new, steps = A.edit_workflow(W + "unit.yml", UNIT, ctx)
        self.assertEqual(L._normalize_on(L.parse_workflow_yaml(new)["on"]), {"workflow_dispatch": None})
        self.assertIn("workflow_dispatch", steps[0])
        held = A.edit_workflow(W + "unit.yml", UNIT, A.Ctx(required=frozenset({"ci.yml"}), local_gate=False))[0]
        self.assertNotIn("workflow_dispatch", held)  # no local gate: the cloud run is the only gate, keep it
        req = A.edit_workflow(W + "unit.yml", UNIT, A.Ctx(required=frozenset({"unit.yml"}), local_gate=True))[0]
        self.assertIn("pull_request", L._normalize_on(L.parse_workflow_yaml(req)["on"]))  # never strand a required check

    def test_strict_protection_drops_the_duplicate_push(self):
        new, steps = A.edit_workflow(W + "unit.yml", UNIT, A.Ctx(strict=True))
        self.assertEqual(L._normalize_on(L.parse_workflow_yaml(new)["on"]), {"pull_request": None})
        self.assertIn("drop `push`", steps[0])
        self.assertIn("concurrency", new)

    def test_concurrency_group_is_per_pr_so_push_runs_never_collide(self):
        group = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
        target = "on:\n  pull_request_target:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: x\n"
        for name, text in (("unit.yml", UNIT), ("tiny.yml", PR_ONLY), ("target.yml", target)):
            new = A.edit_workflow(W + name, text, A.Ctx())[0]
            self.assertIn(group, new, name)  # a PR number, else the run id: only a superseded PR run is ever cancelled
            self.assertIn("cancel-in-progress: true", new, name)
            self.assertEqual(new.count("\nconcurrency:"), 1)
            self.assertIsNone(A.edit_workflow(W + name, new, A.Ctx())[0])  # idempotent: nothing left to add
        patched = A.edit_workflow(W + "unit.yml", UNIT, A.Ctx())[0]
        self.assertNotIn("CONCURRENCY", {f[0] for f in L.lint_workflow(W + "unit.yml", patched, matrix_max=99, strict=None)})
        self.assertIn("CONCURRENCY", {f[0] for f in L.lint_workflow(W + "unit.yml", UNIT, matrix_max=99, strict=None)})

    def test_an_existing_concurrency_block_is_never_duplicated(self):
        text = "on: [pull_request, push]\nconcurrency:\n  group: x\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: x\n"
        new, steps = A.edit_workflow(W + "c.yml", text, A.Ctx())
        self.assertEqual(new.count("concurrency:"), 1)  # a second top-level key would be invalid
        self.assertTrue(any(s.startswith("by hand:") for s in steps))
        self.assertIsNone(A.edit_workflow(W + "c.yml", text.replace("[pull_request, push]", "[pull_request]"), A.Ctx())[0])
        self.assertTrue(A.edit_workflow(W + "c.yml", text.replace("[pull_request, push]", "[pull_request]"), A.Ctx())[1])

    def test_doc_only_path_filter_is_proposed_only_when_it_skips_a_minority(self):
        ctx = A.Ctx(prs=10, pushes=3, files=DOC_HISTORY, required=frozenset())
        new, steps = A.edit_workflow(W + "lint.yml", LINT, ctx)
        self.assertEqual(L._normalize_on(L.parse_workflow_yaml(new)["on"])["pull_request"], {"paths-ignore": ["**.md", "docs/**", "LICENSE"]})
        self.assertIn("30%", " ".join(steps))
        before = A.estimate({W + "lint.yml": LINT}, ctx)[1]["linux"]
        after = A.estimate({W + "lint.yml": new}, ctx)[1]["linux"]
        self.assertAlmostEqual(after / before, 0.7)
        md = A.Ctx(prs=10, pushes=3, files=MD_IS_THE_PRODUCT, required=frozenset())
        self.assertNotIn("paths-ignore", A.edit_workflow(W + "lint.yml", LINT, md)[0])  # 90% skipped: it would filter the product
        required = A.Ctx(prs=10, pushes=3, files=DOC_HISTORY, required=frozenset({"lint.yml"}))
        self.assertNotIn("paths-ignore", A.edit_workflow(W + "lint.yml", LINT, required)[0])  # a required check is never filtered
        self.assertNotIn("paths-ignore", A.edit_workflow(W + "lint.yml", LINT, A.Ctx(files=DOC_HISTORY))[0])  # unknown = possibly required
        self.assertNotIn("paths-ignore", A.edit_workflow(W + "lint.yml", LINT, A.Ctx(required=frozenset()))[0])  # no history, no filter

    def test_doc_globs_are_configurable(self):
        ctx = A.Ctx(prs=10, pushes=3, files=[frozenset({"notes/a.txt"})] * 2 + [frozenset({"src/a.py"})] * 8, required=frozenset(), docs=("notes/**",))
        self.assertIn('"notes/**"', A.edit_workflow(W + "lint.yml", LINT, ctx)[0])

    def test_unsafe_layouts_are_never_patched(self):
        ctx = A.Ctx()
        new, steps = A.edit_workflow(W + "d.yml", BLOCK_SCALAR_ON, ctx)
        self.assertIsNone(new)
        self.assertIn("edit by hand", steps[0])  # a block scalar inside on: would be lost by a rewrite
        number = "on:\n  push:\n  workflow_dispatch:\n    inputs:\n      n:\n        type: number\n        default: 5\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n"
        new, steps = A.edit_workflow(W + "n.yml", number, A.Ctx(required=frozenset(), local_gate=True))
        self.assertIsNone(new)  # a bare number would come back as a string
        self.assertIn("edit by hand", steps[0])
        crlf = UNIT.replace("\n", "\r\n")
        self.assertIn("CRLF", A.edit_workflow(W + "unit.yml", crlf, ctx)[1][0])
        self.assertEqual(A.edit_workflow(W + "bad.yml", "on: pull_request\njobs: &a\n  x: 1\n", ctx), (None, []))

    def test_tag_release_workflow_is_left_alone(self):
        self.assertEqual(A.edit_workflow(W + "release.yml", TAGS, A.Ctx(required=frozenset(), local_gate=True)), (None, []))

    def test_unparseable_workflow_is_reported_not_guessed(self):
        d = make_repo({"a.yml": "on: pull_request\njobs: &a\n  x: 1\n"})
        self.assertIn("not priced", advise(d, "--visibility", "private", "--prs", "2")[1])

    def test_after_numbers_reprice_the_patched_text(self):
        d = make_repo({"unit.yml": UNIT})
        _, out, _ = advise(d, "--visibility", "private", "--prs", "20")
        ctx = A.Ctx(prs=20, pushes=3)
        patched = A.build_patch({W + "unit.yml": UNIT}, ctx)[0]
        self.assertEqual(A.estimate(patched, ctx)[1], {"linux": 80 * 5})  # 20 push + 60 PR runs, the 60 PR-branch pushes gone
        self.assertEqual(A.estimate(patched, ctx, pushes=1)[1], {"linux": 40 * 5})
        self.assertIn("400 min/mo", out)
        self.assertIn("700 min/mo", out)

    def test_minutes_per_push_and_per_merged_pr(self):
        ctx = A.Ctx(prs=20, pushes=3)
        rows = A.estimate({W + "unit.yml": UNIT}, ctx)[0]
        mp, dp, mr, dr = A.per_event(rows, ctx, 3)
        self.assertEqual((mp, mr), (10, 35))  # a push runs unit twice (push + pull_request); a PR is 3 pushes plus the run on the merge
        self.assertAlmostEqual(dp, 10 * 0.006)
        self.assertAlmostEqual(dr, 35 * 0.006)
        patched = A.build_patch({W + "unit.yml": UNIT}, ctx)[0]
        after = A.estimate(patched, ctx)[0]
        self.assertEqual(A.per_event(after, ctx, 3)[::2], (5, 20))  # push limited to main: one run per push
        out = advise(make_repo({"unit.yml": UNIT}), "--visibility", "private", "--prs", "20")[1]
        self.assertIn("one push to a PR branch: 10.0 min $0.06; one merged PR: 35.0 min $0.21", out)

    def test_job_minutes_flag(self):
        d = make_repo({"ci.yml": UNIT})
        _, out, _ = advise(d, "--visibility", "private", "--prs", "10", "--pushes-per-pr", "1", "--job-minutes", "ci.yml=14")
        self.assertIn("x 14 min/run", out)
        _, out, _ = advise(d, "--visibility", "private", "--prs", "10", "--pushes-per-pr", "1", "--job-minutes", "3")
        self.assertIn("x 3 min/run", out)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            advise(d, "--job-minutes", "ci.yml=0")
        self.assertEqual(cm.exception.code, 2)

    def test_missing_root_exits_2_and_no_workflows_is_a_clean_verdict(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(A.main([os.path.join(tempfile.gettempdir(), "no-such-ci-advisor-root")]), 2)
        empty = Path(tempfile.mkdtemp())
        self.assertIn("no workflows", advise(empty, "--visibility", "private")[1])


class Decide(unittest.TestCase):
    def test_public_cloud_heavy_private_local_first_tiny_private_cloud(self):
        heavy = make_repo({"ci.yml": MATRIX})
        self.assertEqual(advise(heavy, "--visibility", "private", "--prs", "20", "--decide")[1].strip(), "local-first")
        self.assertIn("included", advise(heavy, "--visibility", "private", "--prs", "20", "--decide")[2])
        tiny = make_repo({"t.yml": PR_ONLY})
        self.assertEqual(advise(tiny, "--visibility", "private", "--prs", "1", "--pushes-per-pr", "1", "--decide")[1].strip(), "cloud")
        self.assertEqual(advise(heavy, "--visibility", "public", "--prs", "20", "--decide")[1].strip(), "cloud")

    def test_unknown_visibility_is_treated_as_private(self):
        heavy = make_repo({"ci.yml": MATRIX})  # not a git repo: no origin, nothing to probe
        out, err = advise(heavy, "--prs", "20", "--decide")[1:]
        self.assertEqual(out.strip(), "local-first")
        self.assertIn("unknown", err)

    def test_no_workflows_is_cloud(self):
        self.assertEqual(advise(Path(tempfile.mkdtemp()), "--decide")[1].strip(), "cloud")


class Patch(unittest.TestCase):
    def test_patch_applies_with_git_and_the_tool_never_edits_a_workflow(self):
        d = make_repo({"ci.yml": MATRIX, "unit.yml": UNIT}, use_git=True)
        (d / ".githooks").mkdir()
        (d / ".githooks/pre-push").write_text("#!/bin/sh\n")  # a local gate exists, so unit.yml may leave Actions
        before = {p.name: p.read_text() for p in (d / ".github/workflows").iterdir()}
        rc, patch, _ = advise(d, "--patch", "--required", "ci.yml")
        self.assertEqual(rc, 0)
        self.assertEqual({p.name: p.read_text() for p in (d / ".github/workflows").iterdir()}, before)  # printed, never applied
        (d / "p.diff").write_text(patch)
        git(d, "apply", "--check", "p.diff")
        git(d, "apply", "p.diff")
        new = L.load_workflows(d)
        ci, unit = (L.parse_workflow_yaml(new[W + n]) for n in ("ci.yml", "unit.yml"))
        self.assertEqual(L._normalize_on(ci["on"]), {"push": {"branches": ["main"]}, "pull_request": None})
        self.assertEqual(L._normalize_on(unit["on"]), {"workflow_dispatch": None})
        self.assertNotIn("CONCURRENCY", {f[0] for f in L.lint_workflow(W + "ci.yml", new[W + "ci.yml"], matrix_max=99, strict=None)})
        self.assertEqual(ci["jobs"], L.parse_workflow_yaml(before["ci.yml"])["jobs"])  # jobs untouched
        git(d, "diff", "--check")
        self.assertEqual(advise(d, "--patch", "--required", "ci.yml")[1], "")  # applied: nothing left to patch

    def test_patched_yaml_is_valid_for_a_real_yaml_parser(self):
        yaml = self._yaml()
        ctx = A.Ctx(required=frozenset({"ci.yml"}), local_gate=True, files=DOC_HISTORY)
        patched, _, _ = A.build_patch({W + "ci.yml": MATRIX, W + "unit.yml": UNIT, W + "lint.yml": LINT, W + "n.yml": NIGHTLY}, ctx)
        for path, text in patched.items():
            doc = yaml.safe_load(text)
            on = doc.get("on", doc.get(True))  # YAML 1.1 reads the key `on` as true
            self.assertEqual({k: v for k, v in on.items()}, {k: v for k, v in L._normalize_on(L.parse_workflow_yaml(text)["on"]).items()}, path)
        self.assertIs(yaml.safe_load(patched[W + "ci.yml"])["concurrency"]["cancel-in-progress"], True)

    def _yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed: the independent YAML oracle is optional")
        return yaml

    def test_every_hunk_reparses_through_the_lint(self):
        ctx = A.Ctx(required=frozenset(), local_gate=True, files=DOC_HISTORY)
        patched, steps, diff = A.build_patch({W + "lint.yml": LINT, W + "ci.yml": MATRIX}, ctx)
        self.assertEqual(diff.count("\n+++ b/"), 2)
        for path, text in patched.items():
            self.assertNotIn(L.PARSE_ERROR_TAG, {f[0] for f in L.lint_workflow(path, text, matrix_max=99, strict=None)}, path)
        self.assertTrue(steps[W + "lint.yml"])


class Inputs(unittest.TestCase):
    def test_history_counts_first_parent_commits_files_and_tags(self):
        d = make_repo({"ci.yml": UNIT}, use_git=True)
        (d / "src").mkdir()
        (d / "src/a.py").write_text("a")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "code")
        git(d, "checkout", "-q", "-b", "feat")
        (d / "src/b.py").write_text("b")
        (d / "docs").mkdir()
        (d / "docs/c.md").write_text("c")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "feat work")
        git(d, "checkout", "-q", "main")
        git(d, "merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        git(d, "tag", "v1.0.0")
        git(d, "tag", "-a", "v1.0.1", "-m", "x")
        prs, tags = A.hist_from_git(str(d), "main")
        self.assertEqual(len(prs), 3)  # base, code, and the merge (its feature commit is not a separate PR)
        self.assertIn({"src/b.py", "docs/c.md"}, prs)  # a merge commit shows what the PR changed
        self.assertEqual(sorted(tags), ["v1.0.0", "v1.0.1"])
        self.assertEqual(A.hist_from_git(str(Path(tempfile.mkdtemp())), "main"), ([], []))

    def test_history_feeds_the_pr_count_and_the_report_says_where_it_came_from(self):
        d = make_repo({"ci.yml": UNIT}, use_git=True)
        out = advise(d, "--visibility", "private")[1]
        self.assertIn("merged PRs/mo: 1 counted from git first-parent history", out)
        out = advise(make_repo({"ci.yml": UNIT}), "--visibility", "private")[1]
        self.assertIn("20 ASSUMED", out)

    def test_visibility_probe_is_cached_and_unknown_is_not(self):
        d = make_repo({"ci.yml": UNIT}, use_git=True)
        git(d, "remote", "add", "origin", "https://github.com/acme/widgets.git")
        with mock.patch.object(A, "_http_status", return_value=404) as probe:
            vis, why = A.visibility(str(d), None, "auto")
            self.assertEqual(vis, "private")
            self.assertIn("404", why)
        self.assertEqual(probe.call_args[0][0], "https://github.com/acme/widgets")
        with mock.patch.object(A, "_http_status", side_effect=AssertionError("must come from the cache")):
            self.assertEqual(A.visibility(str(d), None, "auto")[0], "private")
        with mock.patch.object(A, "_http_status", return_value=200):
            self.assertEqual(A.visibility(str(d), "acme/other", "auto")[0], "public")
        d2 = make_repo({"ci.yml": UNIT}, use_git=True)
        git(d2, "remote", "add", "origin", "git@github.com:acme/widgets.git")
        with mock.patch.object(A, "_http_status", return_value=None):
            self.assertEqual(A.visibility(str(d2), None, "auto")[0], "unknown")
        with mock.patch.object(A, "_http_status", return_value=200) as probe:
            self.assertEqual(A.visibility(str(d2), None, "auto")[0], "public")  # the unknown answer was not cached
        self.assertEqual(A.visibility(str(d2), None, "private"), ("private", "--visibility"))
        self.assertEqual(A.visibility(str(Path(tempfile.mkdtemp())), None, "auto")[0], "unknown")

    def test_local_gate_detection(self):
        d = make_repo({"ci.yml": UNIT}, use_git=True)
        self.assertFalse(A.local_gate(str(d)))
        (d / ".githooks").mkdir()
        (d / ".githooks/pre-push").write_text("#!/bin/sh\n")
        self.assertTrue(A.local_gate(str(d)))

    def test_toplevel_is_found_from_a_subdirectory(self):
        d = make_repo({"ci.yml": UNIT}, use_git=True)
        (d / "sub").mkdir()
        self.assertIn("ci_cost_advisor:", advise(d / "sub", "--visibility", "private")[1])
        self.assertIn(".github/workflows/ci.yml", advise(d / "sub", "--visibility", "private")[1])


class LintRoute(unittest.TestCase):
    def test_advise_runs_the_advisor_after_the_findings(self):
        d = make_repo({"ci.yml": MATRIX})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = L.main([str(d), "--advise", "--required", "ci.yml"])
        text = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(text.index("CONCURRENCY"), text.index("VERDICT:"))
        self.assertIn("[required]", text)

    def test_default_run_only_hints_and_keeps_its_exit_code(self):
        d = make_repo({"ci.yml": MATRIX})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = L.main([str(d), "--gate"])
        self.assertEqual(rc, L.GATE_FAIL)
        self.assertIn("hint: --advise", out.getvalue())
        self.assertNotIn("VERDICT:", out.getvalue())

    def test_the_shared_loader_keeps_the_lints_missing_root_contract(self):
        with self.assertRaises(FileNotFoundError):
            L.load_workflows(os.path.join(tempfile.gettempdir(), "no-such-ci-advisor-root"))
        self.assertEqual(L.load_workflows(str(Path(tempfile.mkdtemp()))), {})


class PolicyCi(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.pol = self.d / "policy.json"
        self.env = {k: v for k, v in os.environ.items() if k != "PERUN_GITHUB_ACTIONS"} | {"PERUN_POLICY": str(self.pol)}

    def pp(self, *a):
        return subprocess.run([sys.executable, str(AD / "perun_policy.py"), *a], capture_output=True, text=True, env=self.env, cwd=self.d)

    def test_key_validates_and_defaults_to_auto(self):
        self.assertEqual(P.validate({})["ci"], "auto")
        for v in P.CI:
            self.assertEqual(P.validate({"ci": v})["ci"], v)
        for bad in ("maybe", True, 1, None, "Local-First"):
            with self.assertRaises(ValueError):
                P.validate({"ci": bad})

    def test_cli_get_set_and_resolved_mode(self):
        self.pol.write_text("{}")
        self.assertEqual(self.pp("get", "ci").stdout.strip(), "auto")
        self.assertEqual(self.pp("set", "ci", "local-first").returncode, 0)
        self.assertEqual(json.loads(self.pol.read_text()), {"ci": "local-first"})
        r = self.pp("ci")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "local-first"))
        self.assertIn("policy ci=local-first", r.stderr)
        self.assertEqual(self.pp("set", "ci", "cloud").returncode, 0)
        self.assertEqual(self.pp("ci").stdout.strip(), "cloud")
        self.assertEqual(self.pp("set", "ci", "maybe").returncode, 2)
        self.assertEqual(self.pp("check", "ci", "maybe").returncode, 2)
        self.assertEqual(self.pp("get", "ci").stdout.strip(), "cloud")  # a rejected value leaves the file alone

    def test_install_accepts_the_key(self):
        (self.d / "t").mkdir()
        r = subprocess.run(["bash", str(ROOT / "install.sh"), "--policy", "ci=local-first", str(self.d / "t")], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.d / "t/.perun/policy.json").read_text()), {"ci": "local-first"})

    def test_auto_resolution(self):
        stub = self.d / "stub.py"
        stub.write_text("import sys\nprint('local-first')\nprint('stub reason', file=sys.stderr)\n")
        pol = P.validate({})
        self.assertEqual(P.resolve_ci(pol, stub), ("local-first", "auto: stub reason"))
        stub.write_text("print('cloud')\n")
        self.assertEqual(P.resolve_ci(pol, stub)[0], "cloud")
        stub.write_text("print('maybe')\n")
        self.assertEqual(P.resolve_ci(pol, stub), ("cloud", "auto: ci_cost_advisor.py failed"))
        stub.write_text("import sys\nprint('local-first')\nsys.exit(3)\n")
        self.assertEqual(P.resolve_ci(pol, stub)[0], "cloud")  # a failing advisor never means local-first
        self.assertEqual(P.resolve_ci(pol, self.d / "missing.py")[0], "cloud")
        self.assertEqual(P.resolve_ci(P.validate({"github_actions": "off"}), self.d / "missing.py")[0], "local-first")
        self.assertEqual(P.resolve_ci(P.validate({"ci": "cloud", "github_actions": "off"}))[0], "cloud")  # explicit wins
        self.assertEqual(P.resolve_ci(P.validate({"ci": "local-first"}), self.d / "missing.py")[0], "local-first")

    def test_the_real_advisor_decides_auto_in_a_repo(self):
        self.pol.write_text("{}")
        for use_git, want in ((False, "local-first"), (True, "cloud")):
            d = make_repo({"ci.yml": MATRIX}, use_git=use_git)  # no origin: visibility unknown is billable
            r = subprocess.run([sys.executable, str(AD / "perun_policy.py"), "ci"], capture_output=True, text=True, env=self.env, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            # no history: 20 assumed PRs on a heavy matrix; one real commit: almost no activity, inside the free minutes
            self.assertEqual(r.stdout.strip(), want, use_git)

    def test_preamble_and_docs_name_the_key(self):
        pre = (AD.parent / "templates/lane-preamble.md").read_text()
        self.assertIn("perun_policy.py ci", pre)
        self.assertIn("push each PR once", pre)
        self.assertLessEqual(len(pre.splitlines()), 60)
        self.assertIn("`ci` (`local-first|cloud|auto`", (ROOT / "docs/for-fleets.md").read_text())


class PrePushNotice(unittest.TestCase):
    def run_hook(self, ci, remote="old", ref="refs/heads/work"):
        d = make_repo({}, use_git=True)
        tools = d / ".claude/skills/agentic-delivery/scripts"
        tools.mkdir(parents=True)
        shutil.copy(AD / "perun_policy.py", tools / "perun_policy.py")
        (d / "x").write_text("x")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "second")
        head, first = git(d, "rev-parse", "HEAD").strip(), git(d, "rev-parse", "HEAD~1").strip()
        pol = Path(tempfile.mkdtemp()) / "policy.json"  # outside the repo: the hook refuses a dirty tree
        pol.write_text(json.dumps({"ci": ci}))
        env = {**os.environ, "PERUN_POLICY": str(pol), "DCR_PREPUSH_CMD": "true", "DCR_PREPUSH_DEFAULT_BRANCH": "main"}
        sha = first if remote == "old" else "0" * 40
        r = subprocess.run(["bash", str(HOOK), "origin"], cwd=d, input=f"refs/heads/work {head} {ref} {sha}\n", env=env, capture_output=True, text=True)
        return r

    def test_repush_warns_only_in_local_first(self):
        r = self.run_hook("local-first")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ci=local-first expects one push per PR", r.stderr)

    def test_no_notice_in_cloud_mode_on_a_first_push_or_on_the_default_branch(self):
        self.assertNotIn("one push per PR", self.run_hook("cloud").stderr)
        first = self.run_hook("local-first", remote="new")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotIn("one push per PR", first.stderr)
        self.assertNotIn("one push per PR", self.run_hook("local-first", ref="refs/heads/main").stderr)


if __name__ == "__main__":
    unittest.main()
