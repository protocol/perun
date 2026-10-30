#!/usr/bin/env python3
"""veche.py CLI and record surface, the open asks of #2136 #2137 #2139 #2140: --help states the --option name rule and the
stakes gate, --json-out is a temp-file-then-os.replace write on every outcome, the record maps each seat to its own kill
criterion, and council.md states the reply contract a custom --cmd must meet. Stdlib only."""
import contextlib, errno, importlib.util, io, json, os, re, stat, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/idea-critic"
VECHE = SK / "scripts/veche.py"
LENSES = ("skeptic", "better-way", "kill-criteria")
ENV = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {"COLUMNS": "10000", "NO_COLOR": "1", "PYTHON_COLORS": "0"}
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
if "STAGE: TWIN" in p:
    print(cfg.get("twin", "")); sys.exit()
for lens, out in cfg["answers"].items():
    if "LENS: " + lens + " " in p: print(out)
'''
SCORES = {"do-nothing": {"impact": 1, "cost": 1}, "ship": {"impact": 3, "cost": 1}}
OPTION = ["--option", "ship", "--criteria", "impact:3,cost:1"]

spec = importlib.util.spec_from_file_location("veche_under_test", VECHE)
veche = importlib.util.module_from_spec(spec)
spec.loader.exec_module(veche)


def reply(kill="M below 5 by day 30", **kw):
    d = {"verdict": "REVISE", "claims": [], "would_change_it": "w", **kw}
    if kill:
        d["kill_criterion"] = kill
    return json.dumps(d)


def council(answer, extra=(), twin=""):
    """Every seat gives `answer` (one raw reply, or a {lens: reply} dict); -> (exit code, record, completed process)."""
    d = Path(tempfile.mkdtemp())
    (d / "fake.py").write_text(FAKE)
    (d / "cfg.json").write_text(json.dumps({"answers": answer if isinstance(answer, dict) else {l: answer for l in LENSES}, "twin": twin}))
    r = subprocess.run([sys.executable, str(VECHE), "--cmd", f"{sys.executable} {d / 'fake.py'} {d / 'cfg.json'}", "--claim", "c",
                        "--steelman", "s", "--root", str(d), "--review-date", "2030-01-31", *extra], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout), r


def help_of(flag):
    """The --help text of one veche.py option on one line (COLUMNS wide enough that nothing wraps)."""
    out = subprocess.run([sys.executable, str(VECHE), "--help"], capture_output=True, text=True, env=ENV).stdout
    return " ".join(next(c for c in re.split(r"\n  (?=-)", out) if c.startswith(flag + " ")).split())


class OptionHelp(unittest.TestCase):
    """#2136: the --option name rule is the TOKEN regex, stated in the help and in the error for a bad name."""

    def test_help_states_the_exact_rule(self):
        self.assertIn(veche.TOKEN.pattern, help_of("--option"))

    def test_the_error_for_a_bad_name_states_it_too(self):
        rc, rec, _ = council(reply(), ["--option", "_x", "--criteria", "impact:1"])
        self.assertEqual((rc, rec["verdict"]), (3, "COULD_NOT_DECIDE"))
        self.assertIn(veche.TOKEN.pattern, rec["reason"])
        self.assertIn("short token", rec["reason"])


class GateHelp(unittest.TestCase):
    """#2139: --stakes and --reversibility say when the council is skipped, and the gate does exactly that."""

    def test_stakes_help_states_the_gate(self):
        h = help_of("--stakes")
        for phrase in ("low or medium skips", "NOT_CONVENED", "exit 4", "no seat called", "--reversibility easy", "high, or no --reversibility, convenes"):
            self.assertIn(phrase, h)

    def test_reversibility_help_states_the_gate_and_the_default(self):
        h = help_of("--reversibility")
        for phrase in ("easy skips", "NOT_CONVENED", "exit 4", "no seat called", "--stakes low or medium", "hard, or no --stakes, convenes", "default_action", "proceed"):
            self.assertIn(phrase, h)

    def test_the_gate_skips_only_low_or_medium_stakes_with_easy_reversibility(self):
        for stakes in (None, "low", "medium", "high"):
            for rev in (None, "easy", "hard"):
                extra = ["--dry-run", *(["--stakes", stakes] if stakes else []), *(["--reversibility", rev] if rev else [])]
                rc, rec, _ = council(reply(), extra)
                skipped = stakes in ("low", "medium") and rev == "easy"
                self.assertEqual((rc, rec["verdict"]), (4, "NOT_CONVENED") if skipped else (0, "DRY_RUN"), (stakes, rev))


class JsonOutAtomic(unittest.TestCase):
    """#2139: --json-out goes through a temp file in the same directory and os.replace, on every outcome."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "seat.py").write_text("import sys, json\nsys.stdin.read()\nprint(json.dumps({'verdict': 'REVISE', 'claims': [], 'would_change_it': 'w'}))\n")
        self.out = self.d / "rec.json"

    def main(self, *extra, fail_on=0):
        """veche.main in this process with os.replace spied (the `fail_on`-th call raises); -> (exit code, [(src, dst)], stdout, stderr)."""
        calls, real = [], os.replace

        def spy(src, dst):
            calls.append((src, dst))
            if len(calls) == fail_on:
                raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))
            real(src, dst)
        argv = ["--cmd", f"{sys.executable} {self.d / 'seat.py'}", "--claim", "c", "--steelman", "s", "--root", str(self.d), "--review-date",
                "2030-01-31", "--lenses", "skeptic,better-way", "--progress-s", "0", "--json-out", str(self.out), *extra]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("os.replace", spy), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = veche.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, calls, out.getvalue(), err.getvalue()

    def test_every_outcome_is_written_through_a_temp_file_in_the_same_directory(self):
        for verdict, rc, extra in (("REVISE", 0, []), ("COULD_NOT_DECIDE", 3, ["--max-calls", "1"]),
                                   ("NOT_CONVENED", 4, ["--stakes", "low", "--reversibility", "easy"]), ("DRY_RUN", 0, ["--dry-run"])):
            code, calls, stdout, _ = self.main(*extra)
            self.assertEqual((code, json.loads(self.out.read_text())["verdict"]), (rc, verdict), verdict)
            self.assertEqual(len(calls), 2, verdict)  # the start-of-run check, then the record
            for src, dst in calls:
                self.assertNotEqual(src, dst)
                self.assertEqual(os.path.dirname(src), os.path.dirname(dst))
                self.assertTrue(os.path.samefile(dst, self.out))
            self.assertEqual(json.loads(self.out.read_text()), json.loads(stdout))
            self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["rec.json", "seat.py"], verdict)  # no temp file left behind

    def test_a_failed_replace_exits_2_and_leaves_no_temp_file(self):
        for n in (1, 2):  # 1: the start-of-run check, so no seat is paid for; 2: the final record, which is still printed
            code, calls, stdout, stderr = self.main(fail_on=n)
            self.assertEqual((code, len(calls), bool(stdout.strip())), (2, n, n == 2), n)
            self.assertIn(f"--json-out: cannot write {self.out}: {os.strerror(errno.EXDEV)}", stderr)
            self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["rec.json", "seat.py"] if n == 2 else ["seat.py"], n)
            self.assertEqual(self.out.exists() and self.out.read_text(), "" if n == 2 else False, n)  # never half a record

    def test_a_symlinked_path_keeps_pointing_at_its_target(self):
        target = self.d / "real.json"
        target.write_text("stale")
        self.out.symlink_to(target)
        self.assertEqual(self.main("--dry-run")[0], 0)
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(json.loads(target.read_text())["verdict"], "DRY_RUN")

    def test_an_existing_records_mode_survives_the_rewrite(self):
        self.out.write_text("stale")
        os.chmod(self.out, 0o604)  # not what any umask gives a new file, so a plain temp-file rename would show
        self.assertEqual(self.main("--dry-run")[0], 0)
        self.assertEqual(stat.S_IMODE(os.stat(self.out).st_mode), 0o604)
        self.assertEqual(json.loads(self.out.read_text())["verdict"], "DRY_RUN")

    @unittest.skipIf(os.geteuid() == 0, "a regression here would, as root, replace /dev/null itself")
    def test_a_device_path_is_written_in_place_not_renamed_over(self):
        self.out = Path(os.devnull)
        code, calls, stdout, _ = self.main("--dry-run")
        self.assertEqual((code, calls, json.loads(stdout)["verdict"]), (0, [], "DRY_RUN"))
        self.assertTrue(stat.S_ISCHR(os.stat(os.devnull).st_mode))


class KillByLens(unittest.TestCase):
    """#2140: the record keeps each seat's own tripwire beside the deduplicated list."""

    def test_each_seat_keeps_its_own_text_beside_the_deduped_list(self):
        kills = {"skeptic": "Churn above 5% by 2030-01-31.", "better-way": "churn  above 5% by 2030-01-31", "kill-criteria": "p95 above 2s by 2030-01-31"}
        rc, rec, _ = council({l: reply(k) for l, k in kills.items()})
        self.assertEqual(rc, 0)
        self.assertEqual(rec["kill_criteria_by_lens"], kills)
        self.assertEqual(rec["kill_criteria"], [kills["skeptic"], kills["kill-criteria"]])  # the list still collapses near-duplicates

    def test_a_seat_without_a_tripwire_is_left_out_and_none_gives_an_empty_map(self):
        _, rec, _ = council({"skeptic": reply("p95 above 2s by day 30"), "better-way": reply(None), "kill-criteria": reply("   ")})
        self.assertEqual(rec["kill_criteria_by_lens"], {"skeptic": "p95 above 2s by day 30"})
        _, rec, _ = council(reply(None))
        self.assertEqual(rec["kill_criteria_by_lens"], {})
        self.assertTrue(rec["kill_criteria"][0].startswith("UNVERIFIED"))

    def test_the_twins_tripwire_joins_the_list_but_is_not_a_seat_entry(self):
        twin = json.dumps({"dissent": "d", "kill_criterion": "outages above 2 by day 30"})
        _, rec, _ = council(reply("p95 above 2s by day 30"), ["--twin"], twin=twin)
        self.assertEqual(rec["kill_criteria"], ["p95 above 2s by day 30", "outages above 2 by day 30"])
        self.assertEqual(rec["kill_criteria_by_lens"], {l: "p95 above 2s by day 30" for l in LENSES})

    def test_a_decision_record_with_the_field_still_validates(self):
        _, rec, r = council(reply(scores=SCORES), OPTION)
        self.assertEqual((rec["decision"], sorted(rec["kill_criteria_by_lens"])), ("ship", sorted(LENSES)))
        f = Path(tempfile.mkdtemp()) / "rec.json"
        f.write_text(r.stdout)
        v = subprocess.run([sys.executable, str(SK / "scripts/validate_verdict.py"), "--file", str(f)], capture_output=True, text=True)
        self.assertEqual(v.returncode, 0, v.stderr)


class ReplyContract(unittest.TestCase):
    """#2137: council.md states what a custom --cmd reply must hold, and the parser accepts exactly that."""

    def test_council_md_states_the_contract(self):
        text = " ".join((SK / "references/council.md").read_text(encoding="utf-8").split())
        for phrase in ("A custom `--cmd` reply needs a JSON object with a `verdict`", "string-only `claims` items", "stray braces",
                       "the first object with a valid `verdict` wins", "bare or under `scores`"):
            self.assertIn(phrase, text)

    def test_the_first_object_with_a_valid_verdict_is_used_among_prose_braces_and_other_objects(self):
        wrapped = 'Here {as asked}: {"note": 1} {"verdict": "MAYBE"} ' + reply(verdict="HOLD") + " then " + reply() + " {bye}"
        rc, rec, _ = council(wrapped)
        self.assertEqual((rc, rec["verdict"], rec["dropped"]), (0, "HOLD", []))

    def test_a_claim_with_a_non_string_value_drops_the_seat(self):
        rc, rec, _ = council(reply(claims=[{"text": "t", "evidence": "README.md:1", "quote": "q", "line": 3}]))
        self.assertEqual((rc, rec["verdict"]), (3, "COULD_NOT_DECIDE"))
        self.assertTrue(all("bad shape" in why for _, why in rec["dropped"]) and len(rec["dropped"]) == 3)


if __name__ == "__main__":
    unittest.main()
