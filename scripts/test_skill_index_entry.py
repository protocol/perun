#!/usr/bin/env python3
"""Offline tests for the low-context entry index, `.claude/skills/INDEX.md`, built by scripts/skill_index.py.

Covers its skill, command and script lines, the gate that every shipped script and command is listed (and that it
does not depend on the generator), the `--tokens` measurement, the INDEX.md size budget (the gate fires when it is
exceeded) and its refresh by `land-release.sh --regen`. Fixture trees are synthetic; the real-repo cases assert
structure (listed, budgeted, green), never prose.
"""
import contextlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import skill_index as si  # noqa: E402

LONG_FIRST = ("Use when the fixture needs a widget, a first sentence that is long enough to be cut because it "
              "runs well past the one hundred twenty character cap by a deliberate margin.")
SECOND = "A second sentence is dropped."
WIDE_ARGS = "--alpha AAAA --bravo BBBB --charlie CCCC --delta DDDD --echo EEEE"


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_tree(root):
    """A fixture repo: one skill with every script shape the index handles, plus one slash command."""
    skill = root / ".claude/skills/widget"
    put(skill / "SKILL.md", f"---\nname: widget\ndescription: >-\n  {LONG_FIRST} {SECOND}\n---\n\n# Widget\n")
    s = skill / "scripts"
    put(s / "usage.py", '"""usage.py — fixture with a Usage section.\n\nUsage:\n  usage.py --in FILE\n"""\n')
    put(s / "header.py", '"""header.py [--a X] FILE -- fixture with a header line.\n\nBody.\n"""\n')
    put(s / "call.py", '"""Fixture whose call sits inside prose.\n\nIt is chained as:\n  call.py once && echo done\n\n'
                       '  call.py --dir D   # the real call\n"""\n')
    put(s / "lonely.py", '"""lonely.py [--x] FILE\n\nWHY: the purpose is in the next paragraph. More text.\n"""\n')
    put(s / "hook.py", '"""SessionStart hook: fixture, no CLI documented."""\n')
    put(s / "run.sh", "#!/usr/bin/env bash\n# run.sh <arg> — Run the fixture shell tool. More.\nset -e\n")
    put(s / "lib.sh", "#!/usr/bin/env bash\n# Sourced by run.sh.\n")
    put(root / "commands/go.md", '---\ndescription: Run the fixture goal\nargument-hint: "[goal]"\n---\nBody $ARGUMENTS\n')


def generate(root):
    with contextlib.redirect_stdout(io.StringIO()):
        si.cmd_generate(root)
    return (root / ".claude/skills/INDEX.md").read_text(encoding="utf-8")


def check(root):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = si.cmd_check(root)
    return rc, err.getvalue()


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_tree(self.root)


class Lines(Fixture):
    def test_skill_line_is_the_first_sentence_cut_at_a_word(self):
        line = next(l for l in generate(self.root).splitlines() if l.startswith("- widget:"))
        body = line[len("- widget: "):]
        cut = body[:-1]
        self.assertTrue(body.endswith("…") and LONG_FIRST.startswith(cut), line)
        self.assertEqual(LONG_FIRST[len(cut)], " ")  # cut on a word boundary
        self.assertLessEqual(len(body), si.SKILL_LINE_MAX)
        self.assertNotIn("second sentence", line)

    def test_command_line_carries_description_and_argument_hint(self):
        self.assertIn("- /go: Run the fixture goal — [goal]\n", generate(self.root))

    def test_script_lines_name_purpose_and_arguments(self):
        text = generate(self.root)
        self.assertIn("- usage.py: fixture with a Usage section. — --in FILE\n", text)
        self.assertIn("- header.py: fixture with a header line. — [--a X] FILE\n", text)
        self.assertIn("- run.sh: Run the fixture shell tool. — <arg>\n", text)

    def test_a_call_inside_prose_is_not_the_usage_but_a_real_call_is(self):
        text = generate(self.root)
        self.assertIn("— --dir D\n", text)
        self.assertNotIn("echo done", text)

    def test_a_bare_usage_first_paragraph_takes_its_purpose_from_the_next_one(self):
        self.assertIn("- lonely.py: the purpose is in the next paragraph. — [--x] FILE\n", generate(self.root))

    def test_header_separators_and_a_bare_name(self):
        p = self.root / "x.py"
        for sep in ("—", "-", "--"):
            put(p, f'"""x.py [--a] {sep} does a thing."""\n')
            self.assertEqual(si.parse_script_py(p), ("does a thing.", ["x.py [--a]"]), sep)
        put(p, '"""x.py — does a thing."""\n')
        self.assertEqual(si.parse_script_py(p), ("does a thing.", []))  # a bare name is no usage

    def test_scripts_without_a_documented_cli_are_listed_by_name(self):
        text = generate(self.root)
        self.assertIn(f"\n{si.NO_CLI}hook.py, lib.sh\n", text)
        self.assertNotIn("- hook.py:", text)

    def test_long_arguments_are_cut_at_a_token_boundary(self):
        put(self.root / ".claude/skills/widget/scripts/wide.py", f'"""wide.py -- fixture.\n\nUsage:\n  wide.py {WIDE_ARGS}\n"""\n')
        line = next(l for l in generate(self.root).splitlines() if l.startswith("- wide.py:"))
        args = line.split(" — ", 1)[1]
        cut = args[:-1]
        self.assertTrue(args.endswith("…") and len(args) <= si.ARGS_MAX, args)
        self.assertTrue(WIDE_ARGS.startswith(cut) and WIDE_ARGS[len(cut)] == " ", args)

    def test_generation_is_deterministic(self):
        self.assertEqual(generate(self.root), generate(self.root))

    def test_per_skill_index_keeps_every_script_with_its_cli(self):
        generate(self.root)
        per_skill = (self.root / ".claude/skills/widget/INDEX.md").read_text(encoding="utf-8")
        for name in ("usage.py", "header.py", "call.py", "lonely.py", "hook.py", "run.sh", "lib.sh"):
            self.assertIn(f"`scripts/{name}`", per_skill)
        self.assertIn("| header.py [--a X] FILE |", per_skill)


class CoverageGate(Fixture):
    def test_green_after_generate(self):
        generate(self.root)
        self.assertEqual(check(self.root)[0], 0)

    def test_a_script_added_without_regenerating_is_named(self):
        generate(self.root)
        put(self.root / ".claude/skills/widget/scripts/new.py", '"""new.py --x — added later."""\n')
        rc, err = check(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("NOT IN INDEX: widget/new.py", err)

    def test_a_command_added_without_regenerating_is_named(self):
        generate(self.root)
        put(self.root / "commands/extra.md", "---\ndescription: Later\n---\n")
        rc, err = check(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("NOT IN INDEX: /extra", err)

    def test_the_gate_holds_even_if_the_generator_drops_a_script(self):
        real = si.generate_repo_index

        def dropping(root, skill_dirs):
            return "".join(l + "\n" for l in real(root, skill_dirs).splitlines() if not l.startswith("- header.py:"))

        with mock.patch.object(si, "generate_repo_index", dropping):
            generate(self.root)  # the file on disk now equals what the (buggy) generator writes: freshness is green
            rc, err = check(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("NOT IN INDEX: widget/header.py", err)
        self.assertNotIn("STALE", err)

    def test_a_name_in_the_no_cli_list_counts_and_dropping_it_is_caught(self):
        generate(self.root)
        index = self.root / ".claude/skills/INDEX.md"
        index.write_text(index.read_text(encoding="utf-8").replace("hook.py, lib.sh", "hook.py"), encoding="utf-8")
        rc, err = check(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("NOT IN INDEX: widget/lib.sh", err)
        self.assertNotIn("NOT IN INDEX: widget/hook.py", err)


class Tokens(Fixture):
    def measure(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(si.cmd_tokens(self.root), 0)
        lines = out.getvalue().splitlines()
        rows = [tuple(map(int, re.search(r"(\d+) B +(\d+) tok", l).groups())) for l in lines[:3]]
        return rows, int(re.search(r"(\d+) tok", lines[3]).group(1)), lines[-1]

    def test_three_surfaces_in_bytes_and_bytes_div_4(self):
        rules = "Host rules: one.\nSecond line é."  # non-ASCII: bytes, not characters, are counted
        put(self.root / ".claude/skills/agentic-delivery/scripts/subagent_start_inject.py",
            'HOST_RULES = ("Host rules: one.\\n"\n"Second line é.")\n')
        index = generate(self.root)
        descriptions = f"- widget: {LONG_FIRST} {SECOND}\n"
        rows, total, note = self.measure()
        want = [len(t.encode()) for t in (descriptions, rules, index)]
        self.assertEqual(rows, [(n, n // 4) for n in want])
        self.assertEqual(total, sum(n // 4 for n in want))
        self.assertIn("estimate", note)

    def test_missing_inputs_count_as_zero_and_do_not_crash(self):
        rows, _, _ = self.measure()  # no INDEX.md and no delivery skill in the fixture
        self.assertEqual(rows[1:], [(0, 0), (0, 0)])


class Real(unittest.TestCase):
    index = ROOT / ".claude/skills/INDEX.md"

    def test_check_is_green_on_the_real_tree(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/skill_index.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_skill_is_listed_and_the_two_paths_its_line_implies_exist(self):
        # parity with the old table, which spelled out `<skill>/SKILL.md` and `<skill>/INDEX.md` per row
        section = self.index.read_text(encoding="utf-8").split("## Skills", 1)[1].split("## Commands", 1)[0]
        listed = {l[2:].split(":", 1)[0] for l in section.splitlines() if l.startswith("- ")}
        skills = {p.parent.name for p in (ROOT / ".claude/skills").glob("*/SKILL.md")}
        self.assertEqual(listed, skills)
        for name in skills:
            self.assertTrue((ROOT / ".claude/skills" / name / "INDEX.md").is_file(), name)

    def test_every_shipped_script_and_command_is_in_the_real_index(self):
        text = self.index.read_text(encoding="utf-8")  # re-scanned here, not through skill_index's own helpers
        scripts = [p for ext in ("py", "sh") for p in (ROOT / ".claude/skills").glob(f"*/scripts/*.{ext}")]
        commands = list((ROOT / "commands").glob("*.md"))
        self.assertGreater(len(scripts), 50)
        self.assertGreater(len(commands), 0)
        for p in scripts:
            self.assertRegex(text, rf"(?<![\w.-]){re.escape(p.name)}(?![\w-])", f"{p.name} is not in {self.index.name}")
        for p in commands:
            self.assertIn(f"- /{p.stem}:", text)

    def size_gate(self, config):
        return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "size", "--config", str(config), str(ROOT)],
                              capture_output=True, text=True)

    def test_index_has_a_size_budget_and_the_gate_fires_when_it_is_exceeded(self):
        config = ROOT / "scripts/size-budgets.tsv"
        rows = [l.split("\t") for l in config.read_text(encoding="utf-8").splitlines() if l.startswith(".claude/skills/INDEX.md\t")]
        self.assertEqual(len(rows), 1, "one budget row for .claude/skills/INDEX.md")
        size = self.index.stat().st_size
        self.assertLessEqual(size, int(rows[0][1]))
        self.assertEqual(self.size_gate(config).returncode, 0)
        with tempfile.TemporaryDirectory() as d:  # planted defect: a budget one byte under the real size
            planted = Path(d) / "size-budgets.tsv"
            planted.write_text(config.read_text(encoding="utf-8").replace(
                f".claude/skills/INDEX.md\t{rows[0][1]}", f".claude/skills/INDEX.md\t{size - 1}"), encoding="utf-8")
            r = self.size_gate(planted)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SIZE FAIL: .claude/skills/INDEX.md", r.stderr)

    def test_tokens_runs_on_the_real_tree(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/skill_index.py"), "--tokens"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("total", r.stdout)
        self.assertIn("INDEX.md", r.stdout)


class Regen(unittest.TestCase):
    """`land-release.sh --regen` keeps the INDEX.md budget row at the regenerated file's size (it once dropped it)."""

    def test_a_stale_row_is_refreshed_and_a_missing_row_is_added(self):
        with tempfile.TemporaryDirectory() as d:
            w = Path(d)
            shutil.copytree(ROOT / ".claude/skills", w / ".claude/skills", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ROOT / "commands", w / "commands")
            for f in ("skill_index.py", "write-checksums.sh", "size-budgets.tsv", "land-release.sh"):
                put(w / "scripts" / f, (ROOT / "scripts" / f).read_text(encoding="utf-8"))
            subprocess.run(["git", "init", "-q"], cwd=w, check=True)
            config = w / "scripts/size-budgets.tsv"
            others = [l for l in config.read_text(encoding="utf-8").splitlines() if not l.startswith(".claude/skills/INDEX.md\t")]
            for row in (".claude/skills/INDEX.md\t1", None):  # a stale row, then no row at all
                config.write_text("\n".join(others + ([row] if row else [])) + "\n", encoding="utf-8")
                r = subprocess.run(["bash", "scripts/land-release.sh", "--regen"], cwd=w, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                size = (w / ".claude/skills/INDEX.md").stat().st_size
                kept = [l for l in config.read_text(encoding="utf-8").splitlines() if l.startswith(".claude/skills/INDEX.md\t")]
                self.assertEqual(kept, [f".claude/skills/INDEX.md\t{size}"], row)


if __name__ == "__main__":
    unittest.main()
