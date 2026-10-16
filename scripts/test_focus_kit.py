#!/usr/bin/env python3
"""Tests for focus_kit.py (handoff, memory-lint, docs-index, measure) and its wiring. Temp dirs only; no network."""
import datetime
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/agentic-delivery"
sys.path.insert(0, str(SK / "scripts"))
import focus_kit as fk  # noqa: E402
import handoff_inject  # noqa: E402

TODAY = datetime.date(2026, 10, 16)


def run(*args, stdin=None, env=None, script=None):
    """Run focus_kit.py as a subprocess; returns CompletedProcess."""
    e = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
    return subprocess.run([sys.executable, str(script or SK / "scripts/focus_kit.py"), *map(str, args)],
                          capture_output=True, text=True, input=stdin, env=e)


def put(path, text="", mode="w"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as fh:
        fh.write(text)
    return path


def snapshot(d):
    """(relative path, size, mtime_ns, sha256) of every file under d."""
    return sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                  for p in Path(d).rglob("*") if p.is_file())


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="focus-kit-")
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)


class HandoffTests(Tmp):
    def path(self):
        return self.tmp / ".claude/handoff.md"

    def test_first_set_creates_from_template_and_stamps_the_date(self):
        out = fk.handoff_update(self.path(), "goal", "set", "ship the kit", today="2026-10-16")
        self.assertEqual(self.path().read_text(), out)
        self.assertIn("Updated: 2026-10-16\n", out)
        self.assertIn("## Goal\nship the kit\n\n## Stage\n", out)
        self.assertIn("<gate G0-G10", out)  # untouched sections keep their placeholders
        self.assertEqual([p.name for p in self.path().parent.iterdir()], ["handoff.md"])  # no temp file left

    def test_set_changes_only_the_named_section(self):
        fk.handoff_update(self.path(), "goal", "set", "g", today="2026-10-15")
        fk.handoff_update(self.path(), "decisions", "add", "use one script", today="2026-10-15")
        before = self.path().read_text()
        out = fk.handoff_update(self.path(), "next", "set", "1. a\n2. b\n3. c", today="2026-10-16")
        pre0, secs0 = fk._split(before)
        pre1, secs1 = fk._split(out)
        self.assertEqual(len(secs0), len(secs1))
        changed = [i for i, (a, b) in enumerate(zip(secs0, secs1)) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertTrue(secs1[changed[0]].startswith("## Next 3 steps\n1. a\n2. b\n3. c\n"))
        self.assertEqual(pre0.replace("2026-10-15", "2026-10-16"), pre1)  # only the Updated: stamp moved
        # every other section is byte-identical, including its trailing blank line
        self.assertEqual("".join(s for i, s in enumerate(secs0) if i != changed[0]), "".join(s for i, s in enumerate(secs1) if i != changed[0]))

    def test_add_appends_dated_bullets_and_drops_the_placeholder(self):
        fk.handoff_update(self.path(), "decisions", "add", "first", today="2026-10-15")
        out = fk.handoff_update(self.path(), "decisions", "add", "second", today="2026-10-16")
        self.assertTrue(out.endswith("## Decisions\n- 2026-10-15: first\n- 2026-10-16: second\n"), out[-120:])
        out = fk.handoff_update(self.path(), "decisions", "add", "2026-01-02: already dated", today="2026-10-16")
        self.assertIn("- 2026-01-02: already dated\n", out)
        self.assertNotIn("2026-10-16: 2026-01-02", out)

    def test_over_budget_is_refused_and_nothing_is_written(self):
        with self.assertRaises(fk.TooBig) as cm:
            fk.handoff_update(self.path(), "stage", "set", "x" * (fk.HANDOFF_MAX + 1))
        self.assertIn("bytes per section", str(cm.exception))
        self.assertFalse(self.path().exists())
        fk.handoff_update(self.path(), "stage", "set", "ok")
        before = self.path().read_bytes()
        with self.assertRaises(fk.TooBig):
            fk.handoff_update(self.path(), "goal", "set", "y" * 3000)
        self.assertEqual(self.path().read_bytes(), before)

    def test_a_maximum_size_handoff_is_injected_whole(self):
        base = len(fk.handoff_update(self.path(), "stage", "set", "x").encode())
        out = fk.handoff_update(self.path(), "stage", "set", "x" * (1 + fk.HANDOFF_MAX - base))
        self.assertEqual(len(out.encode()), fk.HANDOFF_MAX)
        injected = handoff_inject.render(self.tmp)
        self.assertLessEqual(len(injected.encode()), handoff_inject.CAP)
        self.assertIn(out.strip(), injected)  # the hook cuts nothing: HANDOFF_MAX leaves room for its header

    def test_bad_input_leaves_the_file_alone(self):
        fk.handoff_update(self.path(), "goal", "set", "g")
        before = self.path().read_bytes()
        for name, text in (("bogus", "x"), ("", "x"), ("goal", " \n"), ("goal", "a\n## Sneaky\nb")):
            with self.assertRaises(ValueError, msg=(name, text)):
                fk.handoff_update(self.path(), name, "set", text)
        self.assertEqual(self.path().read_bytes(), before)

    def test_ambiguous_prefix_is_refused_and_custom_headings_work(self):
        put(self.path(), "# H\n\n## Notes A\na\n\n## Notes B\nb\n\n## Tail\nt\n")
        with self.assertRaises(ValueError):
            fk.handoff_update(self.path(), "notes", "set", "x")
        out = fk.handoff_update(self.path(), "notes b", "set", "B2")
        self.assertEqual(out, "# H\n\n## Notes A\na\n\n## Notes B\nB2\n\n## Tail\nt\n")
        out = fk.handoff_update(self.path(), "tail", "set", "T2")
        self.assertEqual(out, "# H\n\n## Notes A\na\n\n## Notes B\nB2\n\n## Tail\nT2\n")

    def test_a_symlinked_handoff_is_not_written_through(self):
        target = put(self.tmp / "outside.md", "# H\n\n## Goal\nold\n")
        self.path().parent.mkdir(parents=True)
        self.path().symlink_to(target)
        with self.assertRaises(ValueError):
            fk.handoff_update(self.path(), "goal", "set", "new")
        self.assertEqual(target.read_text(), "# H\n\n## Goal\nold\n")

    def test_template_fits_the_hook_and_keeps_its_sections(self):
        t = (SK / "templates/handoff.md").read_text()
        self.assertLessEqual(len(t.encode()), 2048)
        self.assertLess(len(t.encode()), fk.HANDOFF_MAX)
        self.assertEqual([ln[3:] for ln in t.splitlines() if ln.startswith("## ")],
                         ["Goal", "Stage", "Next 3 steps", "In flight", "Blockers / owner asks", "Decisions"])
        self.assertRegex(t, r"(?m)^Updated: ")

    def test_cli_set_add_stdin_and_exit_codes(self):
        r = run("handoff", "set", "next", "-", "--root", self.tmp, stdin="1. a\n2. b\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"^handoff: next updated \(\d+/1900 B\)")
        self.assertEqual(run("handoff", "add", "decisions", "chose A", "--root", self.tmp).returncode, 0)
        self.assertIn("1. a\n2. b\n", self.path().read_text())
        self.assertEqual(run("handoff", "set", "nope", "x", "--root", self.tmp).returncode, 2)
        self.assertEqual(run("handoff", "set", "goal", "x" * 3000, "--root", self.tmp).returncode, 1)
        self.assertEqual(run("handoff", "set", "goal", "-", "--root", self.tmp, stdin="").returncode, 2)  # empty stdin

    def test_an_installed_copy_finds_its_template(self):
        inst = self.tmp / "proj/.claude/skills/agentic-delivery"
        for rel in ("scripts/focus_kit.py", "scripts/handoff_inject.py", "templates/handoff.md"):
            put(inst / rel, (SK / rel).read_text())
        r = run("handoff", "set", "goal", "installed", "--root", self.tmp / "proj", script=inst / "scripts/focus_kit.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Goal\ninstalled\n", (self.tmp / "proj/.claude/handoff.md").read_text())

    def test_the_context_nudge_names_the_updater(self):
        src = (SK / "scripts/context_nudge.py").read_text()
        self.assertIn("focus_kit.py", src)
        self.assertEqual(subprocess.run([sys.executable, str(SK / "scripts/context_nudge.py"), "--selftest"],
                                        capture_output=True, text=True).returncode, 0)


class MemoryLintTests(Tmp):
    def setUp(self):
        super().setUp()
        self.mem, self.proj = self.tmp / "mem", self.tmp / "proj"
        self.proj.mkdir()
        self.mem.mkdir()

    def fact(self, name, body="A short fact about the project build.\n", index=True):
        put(self.mem / name, body)
        if index:
            with open(self.mem / "MEMORY.md", "a") as fh:
                fh.write(f"- [{name[:-3]} title]({name}) — hook for {name}\n")

    def lint(self, **kw):
        return fk.lint_memory(self.mem, self.proj, today=TODAY, **kw)

    def codes(self, **kw):
        return sorted(f[2] for f in self.lint(**kw))

    def test_a_clean_memory_dir_has_no_findings(self):
        for n in ("a.md", "b.md", "c.md"):
            self.fact(n, f"Fact {n}: unrelated words {n} alpha beta\n")
        self.assertEqual(self.lint(), [])

    def test_index_budgets_and_line_length(self):
        for n in ("a.md", "b.md", "c.md"):
            self.fact(n, f"fact {n}\n")
        self.assertEqual(self.codes(max_index_lines=2), ["index-lines"])
        self.assertEqual(self.codes(max_index_bytes=10), ["index-bytes"])
        with open(self.mem / "MEMORY.md", "a") as fh:
            fh.write("- [long](a.md) — " + "x" * 200 + "\n")
        long_ = [f for f in self.lint() if f[2] == "index-line-long"]
        self.assertEqual([(f[0], f[1]) for f in long_], [("MEMORY.md", 4)])

    def test_dangling_duplicate_orphan_and_missing_index(self):
        self.fact("a.md")
        with open(self.mem / "MEMORY.md", "a") as fh:
            fh.write("- [a title](a.md) — again\n- [gone](gone.md) — dangling\n")
        self.fact("orphan.md", index=False)
        self.assertEqual(self.codes(), ["index-dangling", "index-dup-link", "index-dup-title", "orphan"])
        (self.mem / "MEMORY.md").unlink()
        self.assertEqual(self.codes(), ["index-missing"])  # no index: orphan is not reported on top of it

    def test_one_fact_per_file_proxies(self):
        self.fact("big.md", "word " * 700)
        self.fact("multi.md", "# One\ntext\n## Two\ntext\n```\n# not a heading\n```\n### Three\ntext\n")
        got = {f[0]: f[2] for f in self.lint() if f[2] in ("file-big", "multi-topic")}
        self.assertEqual(got, {"big.md": "file-big", "multi.md": "multi-topic"})
        self.assertEqual([f for f in self.lint(max_file_bytes=10**6) if f[2] == "file-big"], [])

    def test_near_duplicates_are_listed_once_and_distinct_facts_are_not(self):
        words = " ".join(f"word{i}" for i in range(30))
        self.fact("one.md", words)
        self.fact("two.md", words + " extra")
        self.fact("three.md", " ".join(f"other{i}" for i in range(30)))
        dup = [f for f in self.lint() if f[2] == "near-duplicate"]
        self.assertEqual([(f[0], "one.md" in f[3]) for f in dup], [("two.md", True)])

    def test_stale_dates(self):
        self.fact("old.md", "Decided on 2026-01-01.\n")
        self.fact("mixed.md", "Was 2026-01-01, rechecked 2026-10-10.\n")
        self.fact("future.md", "Ship on 2027-03-01.\n")
        self.fact("bad.md", "Not a date 2026-13-45.\n")
        got = [(f[0], f[2]) for f in self.lint()]
        self.assertEqual(got, [("old.md", "stale-date")])
        self.assertIn("288 days old", self.lint()[0][3])
        self.assertEqual(self.lint(stale_days=0), [])
        self.assertEqual(self.lint(stale_days=400), [])

    def test_gone_paths_and_flags(self):
        put(self.proj / "docs/real.md", "x")
        put(self.proj / "scripts/tool.py", "parser.add_argument('--known')\n")
        home = self.tmp / "home"
        home.mkdir()
        body = ("See `docs/real.md` and `docs/gone.md:12`, `references/other.md` (relative elsewhere), `owner/repo`, "
                "`https://example.com/x.html`, `example.com/a.html`, `scripts/*.py`, `docs/<name>.md`, `~/nope/x.md`, "
                "`/definitely/not/here.txt`. Run `python3 scripts/tool.py --known --gone` or `git push --force-with-lease`.\n"
                "```\n`docs/in-fence.md`\n```\n")
        self.fact("refs.md", body)
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            got = sorted((f[2], f[3]) for f in self.lint())
        self.assertEqual(got, [("flag-gone", "--gone is not in scripts/tool.py"), ("path-gone", "/definitely/not/here.txt"),
                               ("path-gone", "docs/gone.md"), ("path-gone", "~/nope/x.md")])

    def test_it_reports_only_and_never_touches_the_tree(self):
        self.fact("old.md", "2026-01-01 `docs/gone.md`\n")
        put(self.proj / "docs/keep.md", "x")
        before = snapshot(self.tmp)
        self.assertTrue(self.lint())
        r = run("memory-lint", self.mem, "--root", self.proj)
        self.assertEqual(r.returncode, 1)
        self.assertIn("report only; nothing was changed", r.stdout)
        self.assertEqual(snapshot(self.tmp), before)

    def test_symlinked_topic_files_are_skipped(self):
        self.fact("a.md")
        put(self.tmp / "elsewhere.md", "2026-01-01\n")
        (self.mem / "link.md").symlink_to(self.tmp / "elsewhere.md")
        self.assertEqual(self.lint(), [])

    def test_always_loaded_layer(self):
        put(self.proj / "CLAUDE.md", "".join(f"line {i}\n" for i in range(250)) + "`scripts/gone.py` `docs/`\n")
        (self.proj / "docs").mkdir()
        (self.proj / "scripts").mkdir()
        (self.proj / "AGENTS.md").symlink_to("CLAUDE.md")  # one file under two names: counted once
        got = sorted((f[0], f[2]) for f in fk.lint_always_loaded(self.proj))
        self.assertEqual(got, [("CLAUDE.md", "always-loaded-big"), ("CLAUDE.md", "path-gone")])

    def test_this_repos_own_claude_md_is_clean(self):
        self.assertEqual(fk.lint_always_loaded(ROOT), [])

    def test_cli_exit_codes_and_missing_dir(self):
        self.fact("a.md")
        self.assertEqual(run("memory-lint", self.mem, "--root", self.proj).returncode, 0)
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "no-config")}  # auto-detect cannot find the real memory dir
        r = run("memory-lint", "--root", self.proj, env=env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("pass DIR", r.stderr)

    def test_auto_memory_dir_maps_a_worktree_to_its_main_repo(self):
        if not shutil.which("git"):
            self.skipTest("git needed")
        main = self.tmp / "my.repo"
        main.mkdir()
        git = ["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True, capture_output=True)
        wt = self.tmp / "wt"
        subprocess.run([*git, "worktree", "add", "-q", str(wt), "-b", "side"], check=True, capture_output=True)
        cfg = self.tmp / "cfg"
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(cfg)}):
            self.assertIsNone(fk.auto_memory_dir(wt))
            want = cfg / "projects" / str(main.resolve()).replace("/", "-").replace(".", "-") / "memory"
            want.mkdir(parents=True)
            self.assertEqual(fk.auto_memory_dir(wt).resolve(), want.resolve())
            self.assertEqual(fk.auto_memory_dir(main).resolve(), want.resolve())


class DocsIndexTests(Tmp):
    def setUp(self):
        super().setUp()
        d = self.tmp / "docs"
        put(d / "a.md", "# Alpha\n\nIntro words.\n\nRead this when you tune the alpha knob. More text.\n")
        put(d / "b.md", "# Beta\n\n**Bottom line:** see [the guide](guide.md) for *beta* setup. Second sentence.\n")
        put(d / "c.md", "---\ntitle: C\ndescription: \"Gamma: when to rotate keys.\"\n---\n# C\n\nIgnored body.\n")
        put(d / "sub/d.md", "# Delta\n\n> Status: quoted delta summary here, long enough to count.\n")
        put(d / "bench/e.md", "# Excluded\n\nbulk data\n")
        put(d / "INDEX.md", "stale\n")
        put(d / "notes.txt", "not markdown")
        put(d / "node_modules/x.md", "# vendored\n\nno\n")
        (d / "link.md").symlink_to(d / "a.md")

    def rows(self, **kw):
        text = fk.docs_index(self.tmp, **kw)
        return [ln for ln in text.splitlines() if ln.startswith("| `")]

    def test_rows_are_sorted_one_per_doc_and_cut_like_the_skill_index(self):
        rows = self.rows(exclude=["bench"])
        self.assertEqual([r.split("`")[1] for r in rows], ["docs/a.md", "docs/b.md", "docs/c.md", "docs/sub/d.md"])
        self.assertTrue(rows[0].startswith("| `docs/a.md` | Alpha: you tune the alpha knob. |"), rows[0])  # "Read this when" paragraph, lead-in dropped
        self.assertTrue(rows[1].startswith("| `docs/b.md` | Beta: see the guide for beta setup. |"), rows[1])  # label, link and emphasis stripped
        self.assertTrue(rows[2].startswith("| `docs/c.md` | C: Gamma: when to rotate keys. |"), rows[2])  # front-matter description wins
        self.assertTrue(rows[3].startswith("| `docs/sub/d.md` | Delta: quoted delta summary here, long enough to count. |"), rows[3])  # blockquote and label dropped
        self.assertRegex(rows[0], r"\| \d+ \|$")

    def test_a_row_is_capped_and_an_empty_doc_still_gets_one(self):
        put(self.tmp / "docs/long.md", "# " + "T" * 50 + "\n\n" + "word " * 100 + ".\n")
        put(self.tmp / "docs/empty.md", "")
        rows = {r.split("`")[1]: r for r in self.rows()}
        cell = rows["docs/long.md"].split(" | ")[1]
        self.assertTrue(len(cell) <= fk.DOC_MAX and cell.endswith("…"), cell)
        self.assertIn("| (no summary) |", rows["docs/empty.md"])

    def test_exclude_symlinks_vendored_and_index_itself_are_skipped(self):
        names = [r.split("`")[1] for r in self.rows()]
        self.assertIn("docs/bench/e.md", names)
        self.assertEqual([n for n in names if n in ("docs/INDEX.md", "docs/link.md", "docs/node_modules/x.md")], [])
        self.assertNotIn("docs/bench/e.md", [r.split("`")[1] for r in self.rows(exclude=["bench/"])])
        header = fk.docs_index(self.tmp, exclude=["bench"])
        self.assertIn("docs-index --exclude bench`", header)
        self.assertIn("Excluded: `bench`.", header)

    def test_output_is_deterministic(self):
        self.assertEqual(fk.docs_index(self.tmp, exclude=["bench"]), fk.docs_index(self.tmp, exclude=["bench"]))

    def test_check_gate(self):
        a = ["docs-index", "--root", self.tmp, "--exclude", "bench"]
        self.assertEqual(run(*a, "--check").returncode, 1)  # the stale INDEX.md from setUp
        self.assertEqual(run(*a).returncode, 0)
        r = run(*a, "--check")
        self.assertEqual((r.returncode, r.stdout.split(" (")[0]), (0, "docs-index --check: ok"))
        put(self.tmp / "docs/a.md", "# Alpha\n\nRead this when the doc changed.\n")
        r = run(*a, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("STALE: docs/INDEX.md (run: python3 .claude/skills/agentic-delivery/scripts/focus_kit.py docs-index --exclude bench)", r.stderr)
        (self.tmp / "docs/INDEX.md").unlink()
        self.assertEqual(run(*a, "--check").returncode, 1)  # missing index fails closed
        self.assertEqual(run("docs-index", "--root", self.tmp / "nowhere").returncode, 2)

    def test_it_will_not_write_through_a_symlinked_index(self):
        target = put(self.tmp / "keep.md", "keep\n")
        (self.tmp / "docs/INDEX.md").unlink()
        (self.tmp / "docs/INDEX.md").symlink_to(target)
        self.assertEqual(run("docs-index", "--root", self.tmp).returncode, 2)
        self.assertEqual(target.read_text(), "keep\n")

    def test_this_repos_docs_index_is_current(self):
        r = run("docs-index", "--root", ROOT, "--exclude", "bench", "--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_skill_index_reuses_the_helpers_instead_of_copying_them(self):
        spec = importlib.util.spec_from_file_location("skill_index_under_test", ROOT / "scripts/skill_index.py")
        si = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(si)
        for name in ("_short", "_truncate", "_strip_md", "_table_cell", "token_est", "parse_reference_md"):
            self.assertIs(getattr(si, name), getattr(fk, name), name)
        r = subprocess.run([sys.executable, str(ROOT / "scripts/skill_index.py"), "--check"], capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)  # the committed skill INDEX.md files match what the shared helpers generate


class MeasureTests(Tmp):
    def test_baseline_vs_kit_is_plain_arithmetic(self):
        put(self.tmp / "CLAUDE.md", "c" * 100)
        (self.tmp / "AGENTS.md").symlink_to("CLAUDE.md")  # counted once
        put(self.tmp / "docs/a.md", "# A\n\nRead this when a.\n" + "a" * 1000)
        put(self.tmp / "docs/b.md", "# B\n\nRead this when b.\n" + "b" * 2000)
        fk.handoff_update(self.tmp / ".claude/handoff.md", "goal", "set", "g")
        m = fk.measure(self.tmp)
        docs = sum(p.stat().st_size for p in (self.tmp / "docs").glob("*.md"))
        self.assertEqual((m["always"], m["docs"], m["n_docs"]), (100, docs, 2))
        self.assertEqual(m["baseline"], 100 + docs)
        self.assertEqual(m["handoff"], len(handoff_inject.render(self.tmp).encode()))
        self.assertLessEqual(m["handoff"], handoff_inject.CAP)
        self.assertEqual(m["index"], len(fk.docs_index(self.tmp).encode()))
        self.assertEqual(m["kit"], m["handoff"] + m["index"])
        out = run("measure", "--root", self.tmp).stdout
        self.assertIn(f"= {m['baseline']} B", out)
        self.assertIn(f"= {m['kit']} B", out)

    def test_no_handoff_and_no_docs_do_not_crash(self):
        m = fk.measure(self.tmp)
        self.assertEqual((m["baseline"], m["handoff"], m["index"], m["kit"]), (0, 0, 0, 0))
        self.assertEqual(run("measure", "--root", self.tmp).returncode, 0)

    def test_the_kit_reads_less_than_the_baseline_on_this_repo(self):
        m = fk.measure(ROOT, exclude=["bench"])
        self.assertGreater(m["n_docs"], 5)
        self.assertLess(m["index"] + handoff_inject.CAP, m["baseline"])  # index plus a maximum handoff beats reading everything


class WiringTests(unittest.TestCase):
    def test_skills_route_the_kit_with_a_use_when_cue(self):
        skill = (SK / "SKILL.md").read_text()
        row = next(ln for ln in skill.splitlines() if "references/focus-kit.md" in ln)
        for cue in ("compaction", "memory", "scripts/focus_kit.py handoff set", "each gate", "context-heavy", "handback"):
            self.assertIn(cue, row)
        self.assertLessEqual(len(skill.encode()), 24000)  # routing cap, no allowlist
        ref = (SK / "references/focus-kit.md").read_text()
        self.assertTrue(ref.split("\n\n")[1].startswith("Read this when"))
        self.assertIn(".claude/handoff.md", (ROOT / ".claude/skills/agentic-ceo/SKILL.md").read_text())

    def test_the_standards_index_records_the_fetched_pages_with_the_date(self):
        idx = (ROOT / "docs/standards-index.md").read_text()
        tail = idx[idx.rindex("## Verified by direct fetch (2026-10-16) — memory"):]
        for url in ("https://code.claude.com/docs/en/memory", "https://code.claude.com/docs/en/context-window"):
            self.assertIn(url, tail)
        self.assertIn("200 lines or 25KB", tail)


if __name__ == "__main__":
    unittest.main()
