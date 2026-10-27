#!/usr/bin/env python3
"""Tests for merge_train.py --vs-base (no new failures vs base), --admit-red (red-main admission by touched test) and
the `stage` subcommand (queue-published perun/train-stage status). All offline; gh is stubbed. Run: python3 scripts/test_train_vs_base.py
"""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import merge_train as mt  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="train-vsbase-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "wt").mkdir()
        self.calls, self.out = [], io.StringIO()

    def train(self, runner=mt.default_runner, **kw):
        a = SimpleNamespace(**{**dict(repo=None, state=str(self.tmp / "s.json"), verify_cmd="", rerun_cmd="", count_cmd="", cap=None,
                                      retries=0, gate_backoff=0, backoff=0, timeout=60, base="main", no_status=False), **kw})
        t = mt.Train(a, runner, self.out, lambda s: None)
        t.base_sha = "b" * 40

        @contextmanager
        def tree(start, merges):  # a plain dir stands in for the base worktree; the marker tells the rerun it is on the base
            d = self.tmp / "base"
            (d / "wt").mkdir(parents=True, exist_ok=True)
            (d / "isbase").write_text("")
            yield str(d / "wt")
        t.tree = tree
        return t


class VsBase(Base):
    def gate(self, verify, base_out, base_rc):
        self.known = None
        rerun = f"if [ -e ../isbase ]; then {base_out}; exit {base_rc}; fi; echo RERAN 1; exit 1"
        t = self.train(verify_cmd=verify, rerun_cmd=rerun, vs_base=True)
        why = t._gate(str(self.tmp / "wt"), "union")
        self.known = t.known  # fails() skips the cross-stage PASS cache when set
        return why, self.out.getvalue()

    def test_failures_also_red_on_base_are_known(self):
        why, out = self.gate("echo 'FAIL t1'; exit 1", "echo 'FAIL t1'; echo 'RERAN 1'", 1)
        self.assertEqual(why, "")
        self.assertIn("KNOWN-RED union", out)
        self.assertTrue(self.known)

    def test_a_failure_the_base_passes_is_new(self):
        why, out = self.gate("echo 'FAIL t1'; exit 1", "echo 'RERAN 1'", 0)
        self.assertEqual(why, "verify")
        self.assertIn("new failures vs base", out)
        self.assertFalse(self.known)

    def test_only_the_new_id_is_named(self):
        why, out = self.gate("echo 'FAIL t1'; echo 'FAIL t2'; exit 1", "echo 'FAIL t1'; echo 'RERAN 2'", 1)
        self.assertEqual(why, "verify")
        self.assertIn("new failures vs base bbbbbbb: t2", out)

    def test_base_run_error_fails_closed(self):
        why, out = self.gate("echo 'FAIL t1'; exit 1", "echo boom", 1)
        self.assertEqual(why, "verify")
        self.assertIn("base run errored", out)

    def test_off_by_default(self):
        t = self.train(verify_cmd="echo 'FAIL t1'; exit 1", rerun_cmd="echo RERAN 1; exit 1")
        self.assertEqual(t._gate(str(self.tmp / "wt"), "union"), "verify")
        self.assertNotIn("KNOWN-RED", self.out.getvalue())


class AdmitRed(Base):
    def test_admitted_id_still_failing_rejects_the_union(self):
        rerun = "if [ -e ../isbase ]; then echo 'FAIL t1'; echo 'RERAN 1'; exit 1; fi; echo RERAN 1; exit 1"
        t = self.train(verify_cmd="echo 'FAIL t1'; exit 1", rerun_cmd=rerun, vs_base=True)
        t.admitted = {"t1"}  # a PR was admitted for t1, so t1 must pass on the union
        self.assertEqual(t._gate(str(self.tmp / "wt"), "union"), "verify")
        self.assertIn("admitted id still fails: t1", self.out.getvalue())
        self.assertFalse(t.known)

    def admit(self, files, log):
        def runner(argv, cwd=None, timeout=None):
            if argv[:2] == ["git", "log"]:
                return 0, log.get(argv[-1].split("..")[1], ""), ""
            return mt.default_runner(argv, cwd, timeout)
        t = self.train(runner, verify_cmd="echo 'FAIL tests/test_a.py::t1'; echo 'FAIL Some title'; exit 1", admit_red=True)
        t.changed = lambda base, head: files[head]
        members = [{"number": n, "head": f"h{n}"} for n in (1, 2, 3)]
        return t.admit_red(members), self.out.getvalue()

    def test_admits_by_changed_test_file_or_fixes_trailer_only(self):
        kept, out = self.admit({"h1": ["tests/test_a.py"], "h2": ["README.md"], "h3": ["x.py"]}, {"h3": "Fixes: Some title\n"})
        self.assertEqual([m["number"] for m in kept], [1, 3])  # h3 matches via its trailer
        self.assertEqual([m["admit"] for m in kept], [["tests/test_a.py::t1"], ["Some title"]])

    def test_unrelated_pr_is_skipped_whatever_it_is_called(self):
        kept, out = self.admit({"h1": ["a.md"], "h2": ["b.md"], "h3": ["c.md"]}, {h: "fix tests/test_a.py::t1 (title says so)\n" for h in ("h1", "h2", "h3")})
        self.assertEqual(kept, [])
        self.assertIn("SKIP #1 red base", out)

    def test_no_failing_ids_on_base_admits_nothing(self):
        t = self.train(verify_cmd="exit 0", admit_red=True)
        self.assertEqual(t.admit_red([{"number": 1, "head": "h1"}]), [])
        self.assertIn("names no failing", self.out.getvalue())

    def test_red_base_admit_message_and_merge_gate(self):
        t = self.train(admit_red=True, base_fix=None)
        t._latest = lambda sha: {"ci": {"status": "completed", "conclusion": "failure"}}
        self.assertTrue(t.red_base("b" * 40, [{"number": 1}]))
        self.assertIn("--admit-red", self.out.getvalue())


class Stage(Base):
    def run_stage(self, stage, gh_rc=0, eta=0):
        seen = []

        def runner(argv, cwd=None, timeout=None):
            if argv[:3] == ["gh", "pr", "view"]:
                return 0, "abc1234\n", ""
            with open(argv[argv.index("--input") + 1]) as f:
                body = json.load(f)
            seen.append((argv[4], body))
            return gh_rc, "", "boom"
        t = self.train(runner, stage=stage, prs=[7], eta=eta)
        return t.stage(), seen, self.out.getvalue()

    def test_gating_is_pending_with_eta_and_run_id(self):
        rc, seen, out = self.run_stage("gating", eta=600)
        self.assertEqual((rc, len(seen)), (0, 1))
        url, body = seen[0]
        self.assertTrue(url.endswith("/statuses/abc1234"))
        self.assertEqual((body["state"], body["context"]), ("pending", "perun/train-stage"))
        self.assertRegex(body["description"], r"^gating run=\S+ at=\d+ eta<=600s$")

    def test_terminal_stages_map_to_success_and_failure(self):
        self.assertEqual(self.run_stage("done")[1][0][1]["state"], "success")
        self.assertEqual(self.run_stage("failed")[1][0][1]["state"], "failure")

    def test_failed_post_is_a_warn_not_an_error(self):
        rc, _, out = self.run_stage("landing", gh_rc=1)
        self.assertEqual(rc, 0)
        self.assertIn("WARN perun/train-stage=pending NOT posted on #7", out)
        self.assertNotIn("a base that requires it", out)  # that hint belongs to the train-gate vouch only

    def test_skipped_and_deferred_states(self):
        self.assertEqual(self.run_stage("skipped")[1][0][1]["state"], "failure")
        self.assertEqual(self.run_stage("deferred")[1][0][1]["state"], "error")

    def test_cli_parses_stage(self):
        a = mt.build_parser().parse_args(["stage", "--base", "main", "--stage", "queued", "3", "4"])
        self.assertEqual((a.stage, a.prs, a.eta), ("queued", [3, 4], 0))


class TrainLandShell(unittest.TestCase):
    """train_land.sh stage()/stage_end() run for real against a stub merge_train.py that logs its argv (no gh, no network)."""
    SH = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/train_land.sh"

    def calls(self, body, env=""):
        tmp = Path(tempfile.mkdtemp(prefix="train-land-stage-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "merge_train.py").write_text("import sys\nopen(sys.argv[0] + '.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n")
        lines = [ln for ln in self.SH.read_text().splitlines() if ln.startswith(("stage() ", "stage_end() "))]
        script = f'HERE={tmp} BASE_BRANCH=main\nunl() {{ echo 5 6; }}\n' + env + "\n".join(lines) + "\n" + body
        subprocess.run(["bash", "-c", script], check=True, capture_output=True)
        log = tmp / "merge_train.py.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_rc0_posts_done_for_landed_and_skipped_for_the_rest(self):
        got = self.calls('landed=" 4"; stage_end 0')
        self.assertEqual(got, ["stage --base main --stage done 4", "stage --base main --stage skipped 5 6"])

    def test_defer_and_failure_exit_codes(self):
        self.assertEqual(self.calls("landed=; stage_end 5"), ["stage --base main --stage deferred 5 6"])
        self.assertEqual(self.calls("landed=; stage_end 3"), ["stage --base main --stage failed 5 6"])

    def test_eta_flag_and_opt_out(self):
        self.assertEqual(self.calls("stage gating 600 7"), ["stage --base main --stage gating --eta 600 7"])
        self.assertEqual(self.calls("stage gating 600 7", "TRAIN_STAGES=0\n"), [])
        self.assertEqual(self.calls("stage gating 600"), [])  # no PRs, no call

    def test_gating_eta_survives_a_fractional_stage_timeout(self):
        # TRAIN_STAGE_TIMEOUT_MIN=0.02 (test-stage-rc.sh) made `$(( $(stg) * 60 ))` a fatal arithmetic error
        self.assertNotIn("$(( $(stg)", self.SH.read_text())
        self.assertEqual(subprocess.run(["bash", "-c", "echo 0.02 | awk '{printf \"%d\", $1 * 60}'"], capture_output=True, text=True).stdout, "1")

    def test_exit_trap_calls_stage_end_first(self):
        self.assertRegex(self.SH.read_text(), r"(?m)^trap 'stage_end \$\?;")


if __name__ == "__main__":
    unittest.main()
