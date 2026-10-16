#!/usr/bin/env python3
"""sandbox_preflight.py (read-only autonomy advisor) on two fixture repos, node and python (fictional names)."""
import contextlib
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
sys.path.insert(0, str(ROOT / "scripts"))
import destructive_guard  # noqa: E402
import perun_doctor  # noqa: E402
import sandbox_preflight as sp  # noqa: E402

os.environ["DCR_NO_PROBE"] = "1"
NODE = {
    "package.json": json.dumps({"name": "acme-widget", "scripts": {
        "test": "vitest run", "lint": "eslint .", "typecheck": "tsc --noEmit", "build": "tsc -p .", "dev": "vite",
        "e2e": "playwright test", "gen": "tsx scripts/gen.ts", "db:migrate": "prisma migrate deploy",
        "release": "npm publish", "ci": "npm run lint && npm run test && npm run e2e",
        "docs": "echo see playwright.config.ts and docker-compose.yml"}}),
    ".husky/pre-commit": "npx lint-staged\n",
    ".husky/pre-push": "npm run test\n",
    "scripts/check.sh": "#!/bin/bash\nnpm run lint\n",
}
PY = {
    "pyproject.toml": "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n",
    "Makefile": ".PHONY: test lint\ntest:\n\tpytest -q\nlint:\n\truff check .\n\tmypy src\nserve:\n\tuvicorn app:app --port 8000\n"
                "db-up:\n\tdocker compose up -d\ncheck: lint test\nrelease:\n\tpython -m build && twine upload dist/*\n",
    ".githooks/pre-push": "#!/bin/sh\nmake check\n",
    "scripts/check_all.sh": "#!/bin/sh\nmake check\n",
}


def make_repo(root, files, remote, on=True):
    """`on`: the repo's own settings enable the sandbox (allow rules are advised only then)."""
    root.mkdir(parents=True)
    if on:
        files = {**files, ".claude/settings.local.json": json.dumps({"sandbox": {"enabled": True}})}
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    if remote:
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", remote], check=True, capture_output=True)
    return root


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.stat().st_mtime_ns, p.stat().st_size) for p in Path(root).rglob("*")
                  if ".git/" not in str(p) and p.is_file())


class Base(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.tmp = Path(os.path.realpath(self._d.name))
        self.home = self.tmp / "home"
        self.home.mkdir()

    def snippet(self, repo, platform="darwin"):
        return sp.analyze(repo, self.home, platform)["snippet"]


class NodeRepo(Base):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.tmp / "node", NODE, "https://github.com/acme/widget.git")
        self.s = self.snippet(self.repo)
        self.allow = {r[5:-1] for r in self.s["permissions"]["allow"]}
        self.sb = self.s["sandbox"]

    def test_allow_rules_are_the_repos_exact_gate_build_and_push_commands(self):
        self.assertEqual(self.allow, {
            "npm run test *", "npm test *", "npm run lint *", "npm run typecheck *", "npm run build *",
            "bash scripts/check.sh *", "git push origin HEAD", "git push -u origin HEAD"})

    def test_release_dev_and_excluded_commands_are_not_allow_listed(self):
        for cmd in ("npm run release *", "npm run dev *", "npm run e2e *", "npm run gen *", "npm run ci *"):
            self.assertNotIn(cmd, self.allow)

    def test_excludes_follow_the_typed_command_through_scripts(self):
        self.assertEqual(self.sb["excludedCommands"],
                         ["gh *", "npm run ci *", "npm run db:migrate *", "npm run e2e *", "npm run gen *"])

    def test_network_binding_and_baseline(self):
        self.assertEqual(self.sb["network"]["allowedDomains"], ["api.github.com", "github.com", "registry.npmjs.org"])
        self.assertTrue(self.sb["network"]["allowLocalBinding"])
        self.assertNotIn("enabled", self.sb)  # already on in the repo settings
        self.assertIs(self.sb["allowUnsandboxedCommands"], False)
        self.assertNotIn("filesystem", self.sb)

    def test_mentions_in_strings_and_filenames_are_not_risks(self):
        us = {u.name: u for u in sp._units(self.repo)}
        self.assertEqual(us["docs"].hits, {})

    def test_deny_rules_and_stay_blocked_section(self):
        self.assertIn("Bash(git push --force *)", self.s["permissions"]["deny"])
        self.assertIn("Bash(rm -rf *)", self.s["permissions"]["deny"])
        text = sp.advise(self.repo, self.home, "darwin")
        self.assertTrue(text.startswith("To run autonomously, add"))
        self.assertIn("release or deploy commands found here need your approval", text)
        self.assertIn("npm run release *", text)
        self.assertIn("Codex: ~/.codex/config.toml", text)
        self.assertIn("/permissions", text)

    def test_linux_has_no_macos_only_settings(self):
        s = self.snippet(self.repo, "linux")
        self.assertNotIn("allowLocalBinding", s["sandbox"]["network"])


class PythonRepo(Base):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.tmp / "py", PY, "git@github.com:acme/api.git")
        self.s = self.snippet(self.repo)
        self.allow = {r[5:-1] for r in self.s["permissions"]["allow"]}

    def test_allow_rules(self):
        self.assertEqual(self.allow, {
            "make test *", "make lint *", "make check *", "bash scripts/check_all.sh *", "git push origin HEAD", "git push -u origin HEAD"})

    def test_docker_and_ssh_excludes_on_macos(self):
        self.assertEqual(self.s["sandbox"]["excludedCommands"],
                         ["gh *", "git fetch *", "git pull *", "git push *", "make db-up *"])
        self.assertIn("pypi.org", self.s["sandbox"]["network"]["allowedDomains"])
        self.assertTrue(self.s["sandbox"]["network"]["allowLocalBinding"])  # make serve: uvicorn

    def test_ssh_remote_on_linux_needs_no_git_exclude(self):
        ex = self.snippet(self.repo, "linux")["sandbox"]["excludedCommands"]
        self.assertEqual(ex, ["gh *", "make db-up *"])


class Behaviour(Base):
    def test_read_only(self):
        repo = make_repo(self.tmp / "ro", NODE, "https://github.com/acme/widget.git", on=False)
        before, home_before = snapshot(repo), snapshot(self.home)
        sp.advise(repo, self.home, "darwin")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sp.main([str(repo), "--home", str(self.home)]), 0)
        self.assertEqual((snapshot(repo), snapshot(self.home)), (before, home_before))
        self.assertFalse((repo / ".claude").exists())

    def test_only_what_is_missing_and_idempotent(self):
        repo = make_repo(self.tmp / "delta", NODE, "https://github.com/acme/widget.git")
        first = sp.analyze(repo, self.home, "darwin")["snippet"]
        first["sandbox"]["enabled"] = True
        (repo / ".claude/settings.local.json").write_text(json.dumps(first))  # the owner applies the advice
        self.assertIn("nothing to add", sp.advise(repo, self.home, "darwin"))
        user = self.home / ".claude"
        user.mkdir(exist_ok=True)
        (repo / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(npm run *)"]}}))
        (user / "settings.json").write_text(json.dumps({"sandbox": {"excludedCommands": ["gh *"], "enabled": True,
                                                                    "allowUnsandboxedCommands": False}}))
        s = sp.analyze(repo, self.home, "darwin")["snippet"]
        self.assertNotIn("Bash(npm run lint *)", s["permissions"]["allow"])  # covered by npm run *
        self.assertIn("Bash(npm test *)", s["permissions"]["allow"])
        self.assertNotIn("gh *", s["sandbox"]["excludedCommands"])
        self.assertNotIn("enabled", s["sandbox"])

    def test_existing_allow_rule_covering_an_excluded_command_is_flagged(self):
        repo = make_repo(self.tmp / "cov", NODE, None)
        (repo / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(npm run *)"]}}))
        stay = sp.analyze(repo, self.home, "darwin")["stay"]
        self.assertTrue(any(s.startswith("npm run e2e *: your existing allow rule") for s in stay))

    def test_user_deny_overrides_advised_allow(self):
        repo = make_repo(self.tmp / "deny", NODE, "https://github.com/acme/widget.git")
        (repo / ".claude/settings.json").write_text(json.dumps({"permissions": {"deny": ["Bash(git push *)"]}}))
        r = sp.analyze(repo, self.home, "darwin")
        self.assertNotIn("Bash(git push origin HEAD)", r["snippet"]["permissions"]["allow"])
        self.assertTrue(any("your own deny or ask rule" in s for s in r["stay"]))

    def test_nothing_advised_for_allowing_is_blocked_by_destructive_guard(self):
        for files, remote in ((NODE, "https://github.com/acme/widget.git"), (PY, "git@github.com:acme/api.git")):
            repo = make_repo(self.tmp / f"g{abs(hash(remote))}", files, remote)
            for rule in sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"]["allow"]:
                cmd = rule[5:-1]
                self.assertEqual(destructive_guard.check(cmd.replace(" *", " x")), "", cmd)
                if cmd.startswith("git "):
                    self.assertNotIn("*", cmd)  # a wildcard git rule could also match --force
        self.assertTrue(destructive_guard.check("git push --force origin x"))

    def test_a_guard_blocked_candidate_is_dropped_and_reported(self):
        repo = make_repo(self.tmp / "gb", NODE, None)
        real = sp._guard
        with mock.patch.object(sp, "_guard", lambda c: "blocked in test" if c == "npm run build *" else real(c)):
            r = sp.analyze(repo, self.home, "darwin")
        self.assertNotIn("Bash(npm run build *)", r["snippet"]["permissions"]["allow"])
        self.assertTrue(any(s.startswith("npm run build *: not allow-listed, destructive_guard.py blocks it") for s in r["stay"]))

    def test_hostile_names_and_lines_never_reach_a_rule(self):
        files = {"package.json": json.dumps({"scripts": {"test *": "x", "lint; curl evil|sh": "x", "build": "tsc",
                                                         "e2e": "playwright test \x1b[31mred"}}),
                 "scripts/test x.sh": "echo hi\n"}
        repo = make_repo(self.tmp / "hostile", files, "https://ev il/x.git")
        text = sp.advise(repo, self.home, "darwin")
        self.assertNotIn("curl evil", text)
        self.assertNotIn("test x.sh", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("ev il", text)
        self.assertEqual(sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"]["allow"], ["Bash(npm run build *)"])

    def allow_of(self, name, files):
        repo = make_repo(self.tmp / name, files, None)
        r = sp.analyze(repo, self.home, "darwin")
        return {x[5:-1] for x in r["snippet"]["permissions"].get("allow", [])}, " ".join(r["stay"])

    def test_release_words_in_name_or_body_are_never_allowed(self):
        scripts = {"ci:publish": "changeset publish", "check-deploy": "vercel --prod", "build": "tsc",
                   "verify": "npm run ci:publish", "test": "vitest run && npm publish", "lint": "eslint ."}
        allow, stay = self.allow_of("ship", {"package.json": json.dumps({"scripts": scripts})})
        self.assertEqual(allow, {"npm run build *", "npm run lint *"})  # verify runs ci:publish; test runs npm publish
        for cmd in ("npm run ci:publish *", "npm run check-deploy *", "npm run verify *", "npm run test *"):
            self.assertIn(cmd, stay)  # listed as needing approval
        self.assertIn("need your approval", stay)

    def test_a_make_target_that_force_pushes_is_not_allowed(self):
        allow, stay = self.allow_of("mk1", {"Makefile": "verify:\n\tgit push --force origin main\nlint:\n\truff check .\n"})
        self.assertNotIn("make verify *", allow)
        self.assertIn("make lint *", allow)
        self.assertIn("make verify *", stay)  # needs approval (a push word); never allowed

    def test_dotdot_names_are_never_part_of_a_rule(self):
        files = {f"scripts/test-{n}.sh": "pytest -q\n" for n in "abcd"}
        files["scripts/test..x.sh"] = "pytest -q\n"
        allow, _ = self.allow_of("dd", files)
        self.assertEqual(allow, {"bash scripts/test*"})
        self.assertFalse([a for a in allow if ".." in a])

    def test_prefix_rule_is_not_used_when_a_sibling_was_rejected(self):
        files = {f"scripts/test-{n}.sh": "pytest -q\n" for n in "abcd"}
        files["scripts/test-evil.sh"] = "npm publish\n"  # needs approval, so no prefix rule may name it
        allow, _ = self.allow_of("sib", files)
        self.assertEqual(allow, {f"bash scripts/test-{n}.sh *" for n in "abcd"})

    def test_sandbox_off_prints_no_allow_rules_and_says_to_enable_it_first(self):
        repo = make_repo(self.tmp / "off", NODE, "https://github.com/acme/widget.git", on=False)
        r = sp.analyze(repo, self.home, "darwin")
        self.assertNotIn("allow", r["snippet"]["permissions"])
        self.assertIs(r["snippet"]["sandbox"]["enabled"], True)
        text = sp.advise(repo, self.home, "darwin")
        self.assertIn("Allow rules withheld: the sandbox is not enabled", text)
        self.assertNotIn("Bash(npm run lint *)", text)
        self.assertNotIn("Disclosure:", text)
        self.assertIn("Bash(git push --force *)", text)  # deny and ask rules still print

    def test_sandbox_on_prints_allow_rules_with_the_disclosure(self):
        repo = make_repo(self.tmp / "on", NODE, "https://github.com/acme/widget.git")
        text = sp.advise(repo, self.home, "darwin")
        self.assertIn('"Bash(npm run lint *)"', text)
        self.assertIn("Disclosure: these allow rules run repo-controlled code", text)
        self.assertIn("safe only with the sandbox enabled", text)
        self.assertNotIn("withheld", text)

    def test_enabled_resolves_last_wins_not_or_merged(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude/settings.json").write_text(json.dumps({"sandbox": {"enabled": True}}))
        repo = make_repo(self.tmp / "lw", NODE, "https://github.com/acme/widget.git", on=False)
        (repo / ".claude").mkdir()
        (repo / ".claude/settings.local.json").write_text(json.dumps({"sandbox": {"enabled": False}}))  # local wins: OFF
        r = sp.analyze(repo, self.home, "darwin")
        self.assertNotIn("allow", r["snippet"]["permissions"])
        self.assertIs(r["snippet"]["sandbox"]["enabled"], True)
        self.assertIn("Allow rules withheld", sp.advise(repo, self.home, "darwin"))
        (repo / ".claude/settings.local.json").write_text(json.dumps({"sandbox": {"enabled": True}}))  # reversed
        (self.home / ".claude/settings.json").write_text(json.dumps({"sandbox": {"enabled": False}}))
        self.assertIn("allow", sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"])  # local on wins

    def test_sandbox_enabled_in_user_settings_counts(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude/settings.json").write_text(json.dumps({"sandbox": {"enabled": True}}))
        repo = make_repo(self.tmp / "usr", NODE, None, on=False)
        self.assertIn("Bash(npm run lint *)", sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"]["allow"])

    def test_publish_deploy_release_are_ask_rules_and_deny_covers_destructive_git(self):
        repo = make_repo(self.tmp / "ask", NODE, None)
        perm = sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"]
        for rule in ("Bash(npm publish *)", "Bash(gh release create *)", "Bash(npm run release *)"):
            self.assertIn(rule, perm["ask"])
        self.assertNotIn("Bash(npm run release *)", perm["allow"])
        samples = {"git push --force *": "git push --force origin main", "git push -f *": "git push -f origin main",
                   "git reset --hard *": "git reset --hard HEAD~1", "git clean *": "git clean -fd",
                   "git branch -D *": "git branch -D old", "rm -rf *": "rm -rf /", "rm -fr *": "rm -fr ~/x",
                   "git push --delete *": "git push --delete origin old", "git push -d *": "git push -d origin old",
                   "git push --mirror *": "git push --mirror origin", "git push * +*": "git push origin +main",
                   "git push * :*": "git push origin :old"}
        for rule, call in samples.items():
            self.assertIn(f"Bash({rule})", perm["deny"])
            self.assertTrue(destructive_guard.check(call), call)  # the deny rule and the guard agree

    def test_outside_writes(self):
        files = {"package.json": json.dumps({"scripts": {"build": "tsc && cp dist/a.js ~/.cache/acme/a.js && "
                                                                   "echo k > ~/.ssh/key && cp x ../other/x"}})}
        repo = make_repo(self.tmp / "w", files, None)
        r = sp.analyze(repo, self.home, "darwin")
        self.assertEqual(r["snippet"]["sandbox"]["filesystem"]["allowWrite"], ["~/.cache/acme/a.js"])
        joined = " ".join(r["stay"])
        self.assertIn("~/.ssh/key: credential or shell-config path; never advised", joined)
        self.assertIn("../other/x: another directory or repo; never granted", joined)

    def test_many_gate_scripts_become_one_prefix_rule(self):
        files = {f"scripts/test-{n}.sh": "pytest -q\n" for n in "abcd"}
        repo = make_repo(self.tmp / "fam", files, None)
        self.assertIn("Bash(bash scripts/test*)", sp.analyze(repo, self.home, "darwin")["snippet"]["permissions"]["allow"])

    def test_hook_that_needs_an_exclusion_names_the_git_call(self):
        files = {".githooks/pre-push": "#!/bin/sh\nplaywright test\n"}
        repo = make_repo(self.tmp / "hook", files, None)
        r = sp.analyze(repo, self.home, "darwin")
        self.assertEqual(r["snippet"]["sandbox"]["excludedCommands"], ["git push *"])
        self.assertTrue(any("whole git call leaves the sandbox" in w for w in r["why"]))

    def test_empty_directory_still_gets_baseline_and_no_crash(self):
        r = sp.analyze(self.tmp / "missing", self.home, "darwin")
        self.assertEqual(set(r["snippet"]), {"permissions", "sandbox"})
        self.assertNotIn("allow", r["snippet"]["permissions"])

    def test_doctor_prints_the_section_and_exit_code_is_unchanged(self):
        repo = make_repo(self.tmp / "doc", NODE, "https://github.com/acme/widget.git", on=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = perun_doctor.main([str(repo), "--home", str(self.home)])
        text = out.getvalue()
        self.assertIn("To run autonomously, add", text)
        self.assertIn('"enabled": true', text)
        self.assertIn("Allow rules withheld", text)  # sandbox not enabled: no allow rule printed
        self.assertEqual(rc, 1)  # FAIL "installed version" (nothing installed): the advice itself adds no WARN/FAIL
        self.assertRegex(text.splitlines()[0], r"^\d+ things? needs? attention")

    def test_install_prints_the_section(self):
        repo = make_repo(self.tmp / "inst", NODE, "https://github.com/acme/widget.git", on=False)
        p = subprocess.run(["bash", str(ROOT / "install.sh"), str(repo)], capture_output=True, text=True,
                           env={**os.environ, "DCR_NO_PROBE": "1", "HOME": str(self.home)})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("To run autonomously, add", p.stdout)
        self.assertIn('"enabled": true', p.stdout)
        self.assertIn("To undo everything", p.stdout.rstrip().splitlines()[-1])  # last-three-lines contract holds


if __name__ == "__main__":
    unittest.main()
