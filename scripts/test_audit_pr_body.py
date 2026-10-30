#!/usr/bin/env python3
"""Tests for the audit-pr body check: comms_lint.py's `sections` rule (required headings, a non-empty behavior section,
counts-only "Not fixed", every changed file named under "Changes by area"), `--range` against a throwaway git repo, and the
comms_guard.py PreToolUse wiring that picks the kind from the PR title and passes the diff.

Fixtures are synthetic (Acme, example.com); no network and no real gh.
"""
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
LINT_DIR = ROOT / ".claude/skills/communication-structure/scripts"
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/comms_guard.py"
REFERENCE = ROOT / ".claude/skills/communication-structure/references/artifact-templates.md"
sys.path.insert(0, str(LINT_DIR))
sys.path.insert(0, str(GUARD.parent))
import comms_guard as G  # noqa: E402
import comms_lint as L  # noqa: E402

GOOD = """## Summary
Adds sign-in checks to the Acme export routes and caps uploads at 5 MB. Please review the new limit.

## What changes for reviewers and users
- GET /export now needs sign-in; it was public.
- Uploads over 5 MB return a 413 with a new error message.

## Changes by area
- **Export routes:** require a session. Why: anyone could download another team's data. Files: `src/export/handler.ts`. Test: `test/export.test.ts`.
- **Uploads:** size cap. Why: a very large upload could exhaust memory. Files: `src/upload/`. Test: `test/upload.test.ts`.
- **Docs:** describe the new limit. Files: `README.md`, `docs/`.

## Dependency upgrades
- express: 4.18 -> 4.19, fixes a request-parsing bug; no breaking changes.

## How to verify
✅ `npm test` on this head: 42/42 pass.
⏳ NOT RUN: load test (needs staging); reviewer: run `npm run load`.

## Not fixed
2 high, 5 medium findings, tracked privately.
"""
FILES = ["src/export/handler.ts", "src/upload/limit.ts", "test/export.test.ts", "test/upload.test.ts", "README.md", "docs/guide.md"]
FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"  # the attribution line a PR body must end with


def sections(body, files=None):
    """Problems the `sections` rule reports for `body`."""
    res = L.lint("audit-pr", body, files=files)
    return [h["problem"] for r in res["rules"] if r["rule"] == "sections" for h in r["hits"]]


def drop(name, body=GOOD):
    """`body` without the `## name` section."""
    return re.sub(rf"(?ms)^## {re.escape(name)}\n.*?(?=^## |\Z)", "", body)


def with_section(name, content, body=GOOD):
    """`body` with the `## name` section's content replaced."""
    return re.sub(rf"(?ms)(^## {re.escape(name)}\n).*?(?=^## |\Z)", lambda m: m.group(1) + content + "\n", body)


class Sections(unittest.TestCase):
    def test_good_body_passes_every_rule(self):
        res = L.lint("audit-pr", GOOD, files=FILES)
        self.assertTrue(res["ok"], L.render(res))
        self.assertIn("sections", [r["rule"] for r in res["rules"]])
        self.assertEqual(sections(GOOD, FILES), [])

    def test_section_names_live_in_one_constant_and_the_template_uses_them(self):
        self.assertEqual(L.AUDIT_SECTIONS, ("Summary", "What changes for reviewers and users", "Changes by area", "How to verify", "Not fixed"))
        ref = REFERENCE.read_text(encoding="utf-8")
        for name in L.AUDIT_SECTIONS:
            self.assertIn(f"\n    ## {name}\n", ref, name)
        self.assertIn("sections", L.load_kinds()["audit-pr"][2])

    def test_each_missing_section_fails_with_its_exact_heading(self):
        for name in L.AUDIT_SECTIONS:
            got = sections(drop(name))
            self.assertTrue(any(f"no `## {name}` section" in p for p in got), (name, got))
            res = L.lint("audit-pr", drop(name))
            self.assertFalse(res["ok"], name)
            hit = next(h for r in res["rules"] if r["rule"] == "sections" for h in r["hits"])
            self.assertIn(f"add `## {name}`", hit["fix"])

    def test_optional_dependency_section_is_not_required(self):
        self.assertEqual(sections(drop("Dependency upgrades"), FILES), [])

    def test_a_short_body_still_fails_the_rule(self):
        res = L.lint("audit-pr", "Adds sign-in checks to the export routes.\n")
        self.assertFalse(res["ok"])
        self.assertEqual(len(sections("Adds sign-in checks to the export routes.\n")), len(L.AUDIT_SECTIONS))

    def test_empty_behavior_section_fails_and_none_or_an_item_passes(self):
        name = L.AUDIT_SECTIONS[1]
        for empty in ("", "\n\n", "-", "- \n-", "<!-- list every change, or None -->", "```\n```"):
            got = sections(with_section(name, empty))
            self.assertEqual([p for p in got if "is empty" in p], [f"`{name}` is empty"], repr(empty))
        for ok in ("None", "None: every change is internal.", "- A new 5 MB upload limit."):
            self.assertEqual(sections(with_section(name, ok)), [], repr(ok))

    def test_heading_forms(self):
        for heading in ("### Not fixed", "## Not fixed:", "## **Not fixed**", "## not fixed", "#### Not   fixed ####"):
            self.assertEqual(sections(GOOD.replace("## Not fixed", heading)), [], heading)
        for bad in ("##Not fixed", "## Not fixed (3)", "Not fixed", "**Not fixed**", "    ## Not fixed", "####### Not fixed"):  # the last two are code and text
            self.assertEqual(len(sections(GOOD.replace("## Not fixed", bad))), 1, bad)

    def test_a_heading_inside_a_code_fence_is_not_a_section(self):
        body = drop("Not fixed") + "```\n## Not fixed\n2 high, tracked privately\n```\n"
        self.assertEqual(sections(body), ["no `## Not fixed` section"])

    def test_sub_headings_stay_inside_their_section(self):
        body = with_section("Changes by area", "### Export\n- `src/export/handler.ts`\n### Uploads\n- `src/upload/`\n- `test/`\n- `README.md`, `docs/`")
        self.assertEqual(sections(body, FILES), [])

    def test_every_hit_names_an_exact_fix(self):
        res = L.lint("audit-pr", with_section("Not fixed", "src/auth.ts:42"), files=["x.py"])
        hits = [h for r in res["rules"] if r["rule"] == "sections" for h in r["hits"]]
        self.assertGreaterEqual(len(hits), 2)
        for h in hits:
            self.assertTrue(h["problem"] and h["fix"], h)
        self.assertIn("FAIL sections", L.render(res))


class Coverage(unittest.TestCase):
    def covered(self, area, *files):
        return sections(with_section("Changes by area", area), list(files))

    def test_an_unnamed_file_fails_and_is_listed(self):
        got = sections(GOOD, FILES + ["src/auth/session.ts", "scripts/deploy.sh"])
        self.assertEqual(len(got), 1)
        self.assertIn("2 changed file(s) not named under `Changes by area`: src/auth/session.ts, scripts/deploy.sh", got[0])
        res = L.lint("audit-pr", GOOD, files=["src/auth/session.ts"])
        hit = next(h for r in res["rules"] if r["rule"] == "sections" for h in r["hits"])
        self.assertEqual(hit["line"], GOOD.splitlines().index("## Changes by area") + 1)
        self.assertIn("trailing slash", hit["fix"])

    def test_naming_forms_that_cover_a_file(self):
        for area in ("`src/a/b.py`", "src/a/b.py:12 adds a check", "(src/a/b.py).", "./src/a/b.py", "`src/a/`", "`src/`",
                     "`src/a/*.py`", "[b](src/a/b.py)", "| src/a/b.py | 12 |"):
            self.assertEqual(self.covered(area, "src/a/b.py"), [], area)

    def test_naming_forms_that_do_not_cover_a_file(self):
        for area in ("b.py", "src/a", "src/ab/", "src/a/c.py", "src/a/b.pyc", "src/a/b.py.bak", "lib/src/a/b.py", "/srv/src/a/b.py", "src/a/b",
                     "src", "the src and a dirs"):
            self.assertEqual(len(self.covered(area, "src/a/b.py")), 1, area)

    def test_root_files_need_their_own_name(self):
        self.assertEqual(self.covered("`Makefile`", "Makefile"), [])
        self.assertEqual(len(self.covered("`src/`", "Makefile")), 1)

    def test_only_the_changes_by_area_section_counts(self):
        body = with_section("Changes by area", "- **Core:** a change. Files: `src/a/`.").replace("Adds sign-in", "Adds sign-in to lib/x.py:1 and")
        self.assertEqual(len(sections(body, ["lib/x.py"])), 1)
        self.assertEqual(sections(body, ["src/a/b.py"]), [])

    def test_special_characters_in_a_path_match_literally(self):
        for path in ("app/users/[id]/page.tsx", "pkg/c++/x.cc", "a.b/c(1).ts"):
            self.assertEqual(self.covered(f"`{path}`", path), [], path)
            self.assertEqual(len(self.covered("`app/users/x.tsx` `pkg/cxx/x.cc` `a_b/c(1).ts`", path)), 1, path)

    def test_no_files_means_nothing_to_cover_and_none_skips_the_check(self):
        self.assertEqual(sections(GOOD, []), [])
        self.assertEqual(sections(GOOD, None), [])
        self.assertEqual(sections(with_section("Changes by area", ""), None), [])

    def test_a_missing_area_section_reports_the_heading_only(self):
        self.assertEqual(sections(drop("Changes by area"), FILES), ["no `## Changes by area` section"])

    def test_covers_agrees_with_the_boundary_regex_it_replaced(self):
        def oracle(area, path):
            parts = path.split("/")
            return any(re.search(r"(?<![\w@+~/.-])(?:\./)?" + re.escape(c) + r"(?![\w@+~/-]|\.\w)", area)
                       for c in [path] + ["/".join(parts[:i]) + "/" for i in range(1, len(parts))])

        rnd = random.Random(11)
        ctx = ["", " ", "`", "(", ".", "..", "./", "/", "-", "_", "a", "\u00e9", "*", ":12", ",", "\n", "~", "@", "+", "x/", ".b", "b.", "[", "**"]
        for path in ("a/b.ts", "a/b/c/d.ts", "b.ts", "a.b/c.ts", "\u00e9/a.ts"):
            parts = path.split("/")
            forms = [path, path[:-1], path + "x"] + ["/".join(parts[:i]) + s for i in range(1, len(parts)) for s in ("", "/")]
            for _ in range(2000):
                area = "".join(rnd.choices(ctx, k=rnd.randint(0, 3))) + rnd.choice(forms) + "".join(rnd.choices(ctx, k=rnd.randint(0, 3)))
                if rnd.random() < 0.3:  # a glued first occurrence must not hide a clean second one
                    area += rnd.choice(ctx) + rnd.choice(forms) + rnd.choice(ctx)
                self.assertEqual(L._covers(area, path), oracle(area, path), (area, path))

    @unittest.skipUnless(hasattr(signal, "SIGALRM"), "needs SIGALRM")
    def test_pathological_input_cannot_hang_the_check(self):
        def stuck(*_):
            raise AssertionError("the check did not finish in 20 s")

        old = signal.signal(signal.SIGALRM, stuck)
        self.addCleanup(signal.signal, signal.SIGALRM, old)
        self.addCleanup(signal.alarm, 0)
        signal.alarm(20)
        files = [f"pkg{i % 50}/dir{i % 7}/mod{i}.py" for i in range(8000)]
        area = "\n".join(f"- `pkg{i}/`, `lib/x{i}.py`, `pkg{i}/dir1/a-{i}.ts`" for i in range(1000))
        for body in (GOOD.replace("## Summary\n", "## Summary" + " " * 50_000 + "x\n# a" + " " * 50_000 + "b\n"),
                     with_section("Not fixed", "a/" * 100_000 + "\n" + "a." * 100_000 + "\n" + "a-b/" * 50_000),
                     with_section("Changes by area", area)):
            self.assertIsInstance(sections(body, files), list)

    def test_many_uncovered_files_are_counted_not_dumped(self):
        got = sections(GOOD, [f"pkg{i}/mod.py" for i in range(9)])
        self.assertEqual(len(got), 1)
        self.assertIn("9 changed file(s)", got[0])
        self.assertIn("pkg4/mod.py (+4 more)", got[0])
        self.assertNotIn("pkg5/mod.py", got[0])


class NotFixed(unittest.TestCase):
    def check(self, text):
        return [p for p in sections(with_section("Not fixed", text), FILES) if "carries detail" in p]

    def test_file_line_route_and_url_detail_fails(self):
        for detail in ("src/auth.ts:42", "see auth.py:7-9", "app.js:3", "line 12 of the handler", "lines 4-9", "src/a.ts#L12",
                       "GET /admin/users is open", "POST /login", "DELETE /{id} is open", "POST /", "the /admin page", "(/api/v1/keys)", "https://example.com/x",
                       "see docs/threat-model.md", "- 1 high in src/auth/session.ts"):
            self.assertEqual(len(self.check(detail)), 1, detail)

    def test_counts_only_passes(self):
        for counts in ("2 high, 5 medium findings, tracked privately.", "None. Every finding is fixed.", "3 low / 2 info, tracked privately",
                       "High: 1, Medium: 4 (tracked privately)", "1 critical and/or high, tracked privately", "Node.js 18: 2 medium"):
            self.assertEqual(self.check(counts), [], counts)

    def test_detail_in_a_fence_is_flagged_and_reports_its_line(self):
        body = with_section("Not fixed", "2 high, tracked privately.\n```\nsrc/auth.ts:42\n```")
        res = L.lint("audit-pr", body)
        hit = next(h for r in res["rules"] if r["rule"] == "sections" for h in r["hits"])
        self.assertEqual(body.splitlines()[hit["line"] - 1], "src/auth.ts:42")

    def test_detail_outside_not_fixed_is_fine(self):
        body = with_section("Changes by area", "- **Core:** fixes `src/a/b.py:12`. Files: `src/a/`.") + "\n## Notes\nsee src/a/b.py:1\n"
        self.assertEqual(sections(body, ["src/a/b.py"]), [])
        self.assertEqual(sections(GOOD + "\n## Notes\nsee src/a/b.py:1\n"), [])


class Footer(unittest.TestCase):
    """A trailing attribution footer (a `---` rule or 🤖 Generated line, then only footer lines) ends the last section and is not its content; test_audit_pr_footer_rule.py covers what a rule must not hide."""

    def detail(self, text, body=GOOD):
        return [p for p in sections(with_section("Not fixed", text, body), FILES) if "carries detail" in p]

    def test_counts_only_with_a_footer_passes(self):
        counts = "2 high, 5 medium findings, tracked privately."
        for tail in (FOOTER, "---\n" + FOOTER, "---\n\n" + FOOTER, "---\nGenerated with [Claude Code](https://claude.com/claude-code)"):
            self.assertEqual(self.detail(f"{counts}\n\n{tail}"), [], tail)
        self.assertEqual(sections(GOOD + "\n" + FOOTER, FILES), [])

    def test_detail_in_not_fixed_still_fails_beside_a_footer(self):
        for text in ("src/auth.ts:42\n\n" + FOOTER, "2 high.\nGET /admin/users is open\n\n---\n" + FOOTER, "2 high.\nsee https://example.com/x\n---\n" + FOOTER):
            self.assertEqual(len(self.detail(text)), 1, text)

    def test_the_footer_is_not_content_of_a_last_section_that_must_have_some(self):
        body = drop("What changes for reviewers and users") + "\n## What changes for reviewers and users\n\n" + FOOTER + "\n"
        self.assertEqual([p for p in sections(body, FILES) if "is empty" in p], ["`What changes for reviewers and users` is empty"])

    def test_a_rule_or_robot_line_above_a_later_heading_is_content_not_a_footer(self):
        body = GOOD.replace("## How to verify", "---\n\n## How to verify").replace("## Not fixed", FOOTER + "\n\n## Not fixed")
        self.assertEqual(sections(body, FILES), [])
        self.assertEqual(len(self.detail("src/auth.ts:42", body)), 1)

    def test_a_rule_inside_a_code_fence_is_not_a_footer(self):
        self.assertEqual(len(self.detail("2 high.\n```\n---\nsrc/auth.ts:42\n```")), 1)


class Repo(unittest.TestCase):
    """A throwaway repo: main moves on after branch feat forks from it; feat adds two files and a docs file and deletes README.md."""

    @classmethod
    def git(cls, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout

    def put(self, path, text="x\n"):
        f = self.repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("needs git")
        self.tmp = Path(tempfile.mkdtemp(prefix="audit-pr-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "Jane Smith", "GIT_AUTHOR_EMAIL": "jane@example.com",
               "GIT_COMMITTER_NAME": "Jane Smith", "GIT_COMMITTER_EMAIL": "jane@example.com"}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("PERUN_COMMS_GUARD", None)
        self.repo = self.tmp / "acme-app"
        self.repo.mkdir()
        g = lambda *a: self.git(self.repo, *a)  # noqa: E731
        g("init", "-q", "-b", "main")
        self.put("README.md")
        g("add", "-A")
        g("commit", "-qm", "init")
        g("switch", "-qc", "feat")
        for p in ("src/export/handler.ts", "src/upload/limit.ts", "docs/café.md"):
            self.put(p)
        g("rm", "-q", "README.md")
        g("add", "-A")
        g("commit", "-qm", "feat")
        g("switch", "-q", "main")
        self.put("later.txt")
        g("add", "-A")
        g("commit", "-qm", "main moves on")
        g("update-ref", "refs/remotes/origin/main", "HEAD")
        g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        g("switch", "-q", "feat")
        self.want = sorted(["README.md", "docs/café.md", "src/export/handler.ts", "src/upload/limit.ts"])
        self.body = self.tmp / "body.md"
        self.body.write_text(GOOD, encoding="utf-8")

    def files(self, rng):
        return sorted(unicodedata.normalize("NFC", f) for f in L.changed_files(rng, cwd=self.repo))


class Range(Repo):
    def test_changed_files_is_what_the_pr_carries_whatever_the_range_form(self):
        for rng in ("main..feat", "main...feat", "main", "origin/main..feat"):
            self.assertEqual(self.files(rng), self.want, rng)

    def test_a_range_git_cannot_read_raises(self):
        for rng in ("nope..feat", "", "--output=x", "-p"):
            with self.assertRaises(ValueError, msg=rng):
                L.changed_files(rng, cwd=self.repo)
        with self.assertRaises(ValueError):
            L.changed_files("main..feat", cwd=self.tmp)  # not a repo

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(LINT_DIR / "comms_lint.py"), "--kind", "audit-pr", "--file", str(self.body), *args],
                           cwd=self.repo, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_cli_passes_when_every_changed_file_is_named(self):
        rc, out, _ = self.cli("--range", "main..feat")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.cli()[0], 0)

    def test_cli_fails_and_names_the_unnamed_file(self):
        self.body.write_text(self.body.read_text(encoding="utf-8").replace("`README.md`, ", ""), encoding="utf-8")
        rc, out, _ = self.cli("--range", "main..feat")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL sections", out)
        self.assertIn("1 changed file(s) not named under `Changes by area`: README.md", out)
        self.assertEqual(self.cli()[0], 0)  # no range, no coverage check

    def test_cli_fails_closed_on_an_unreadable_range(self):
        rc, out, err = self.cli("--range", "nope..feat")
        self.assertEqual(rc, 2)
        self.assertIn("cannot read --range", err)
        self.assertEqual(out, "")


class Hook(Repo):
    def fire(self, cmd, cwd=None):
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd or self.repo)}
        p = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else ""

    def no_readme(self):
        self.body.write_text(GOOD.replace("`README.md`, ", ""), encoding="utf-8")

    def test_an_audit_title_checks_the_sections_and_the_diff_against_base(self):
        self.no_readme()
        for title in ("Audit: harden exports", "Security fixes for export", "harden uploads", "-t 'Fix audit findings'"):
            flag = title if title.startswith("-t") else f'--title "{title}"'
            note = self.fire(f"gh pr create {flag} --base main --body-file {self.body}")
            self.assertIn("on the audit-pr you just sent", note, title)
            self.assertIn("README.md", note, title)
            self.assertIn("advisory", note)

    def test_the_default_base_is_origin_head_and_a_dash_base_cannot_inject(self):
        self.no_readme()
        self.assertIn("README.md", self.fire(f'gh pr create --title "Audit" --body-file {self.body}'))
        note = self.fire(f'gh pr create --title "Audit" --base "--output=pwned" --body-file {self.body}')
        self.assertNotIn("README.md", note)
        self.assertFalse((self.repo / "--output=pwned").exists())

    def test_base_means_the_remote_branch_not_a_stale_local_one(self):
        self.no_readme()
        self.git(self.repo, "branch", "-f", "main", "feat")  # local main is stale; the PR targets origin/main
        self.assertIn("README.md", self.fire(f'gh pr create --title "Audit" --base main --body-file {self.body}'))

    def test_a_cd_before_gh_picks_the_checkout_the_diff_is_read_from(self):
        self.no_readme()
        tail = f'&& gh pr create --title "Audit" --base main --body-file {self.body}'
        for cd in (f"cd {self.repo}", f'cd "{self.repo}"', f"cd {self.repo.name}", f"cd {self.tmp} && cd {self.repo.name}"):
            self.assertIn("README.md", self.fire(f"{cd} {tail}", self.tmp), cd)  # the hook's cwd is not the repo
        with mock.patch.dict(os.environ, {"ACME_WT": str(self.repo), "HOME": str(self.tmp)}):
            for cd in ("cd $ACME_WT", 'cd "${ACME_WT}"', f"cd ~/{self.repo.name}"):
                self.assertIn("README.md", self.fire(f"{cd} {tail}", "/"), cd)
        self.assertEqual(self.fire(f"cd {self.tmp}/nope {tail}", self.repo), "")  # unreadable checkout: headings only, never this one's diff

    def test_a_body_that_names_every_file_and_has_every_section_stays_silent(self):
        self.assertEqual(self.fire(f'gh pr create --title "Audit" --base main --body-file {self.body}'), "")

    def test_a_heredoc_body_is_checked_whichever_side_of_it_the_title_is_on(self):
        leak = GOOD.replace("2 high, 5 medium findings, tracked privately.", "See src/export/handler.ts:12 for the rest.")
        for body, clean in ((leak, False), (GOOD, True)):
            doc = f"\"$(cat <<'EOF'\n{body}EOF\n)\""
            for cmd in (f'gh pr create --title "Security: harden exports" --base main --body {doc}',
                        f'gh pr create --base main --body {doc} --title "Security: harden exports"'):
                note = self.fire(cmd)
                self.assertEqual(note, "") if clean else self.assertIn("`Not fixed` carries detail", note)
                self.assertNotIn("not named", note, cmd)

    def test_missing_sections_are_reported_on_any_audit_pr_command(self):
        self.body.write_text(drop("Not fixed"), encoding="utf-8")
        for cmd in (f'gh pr create --title "Audit" --base main --body-file {self.body}', f'gh pr edit 7 --title "Security" --body-file {self.body}',
                    f'gh pr create --title "Audit" --head other --body-file {self.body}'):
            self.assertIn("no `## Not fixed` section", self.fire(cmd), cmd)

    def test_edit_and_head_skip_coverage_because_the_diff_is_not_this_checkout(self):
        self.no_readme()
        for cmd in (f'gh pr edit 7 --title "Audit" --body-file {self.body}', f'gh pr create --title "Audit" --head other --body-file {self.body}'):
            self.assertEqual(self.fire(cmd), "", cmd)

    def test_no_repo_or_unknown_base_degrades_to_the_sections_check(self):
        self.body.write_text(drop("Not fixed"), encoding="utf-8")
        for cmd, cwd in ((f'gh pr create --title "Audit" --body-file {self.body}', self.tmp),
                         (f'gh pr create --title "Audit" --base nope --body-file {self.body}', self.repo)):
            note = self.fire(cmd, cwd)
            self.assertIn("no `## Not fixed` section", note)
            self.assertNotIn("not named", note)

    def test_other_titles_keep_the_pr_kind(self):
        self.no_readme()
        self.body.write_text(self.body.read_text(encoding="utf-8").replace("## Not fixed\n", "## Not fixed\nHope this helps! "), encoding="utf-8")
        note = self.fire(f'gh pr create --title "Add export button" --base main --body-file {self.body}')
        self.assertIn("on the pr you just sent", note)
        for text in (note, self.fire(f"gh pr comment 3 --body-file {self.body}")):
            self.assertNotIn("audit-pr", text)
            self.assertNotIn("sections", text)

    def test_the_off_switch_and_an_old_comms_lint_leave_the_write_alone(self):
        self.body.write_text(drop("Not fixed"), encoding="utf-8")
        cmd = f'gh pr create --title "Audit" --base main --body-file {self.body}'
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.repo)})
        off = subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, env=dict(os.environ, PERUN_COMMS_GUARD="off"))
        self.assertEqual((off.returncode, off.stdout), (0, ""))
        old = mock.Mock(spec=["lint"])  # a comms_lint without AUDIT_TITLE / changed_files
        self.assertEqual(G.audit("pr", cmd, str(self.repo), old), ("pr", {}))
        self.assertEqual(G.audit("pr", "", "", L), ("pr", {}))
        self.assertEqual(G.audit("message", cmd, str(self.repo), L), ("message", {}))


if __name__ == "__main__":
    unittest.main()
