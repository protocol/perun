#!/usr/bin/env python3
"""Offline tests for agentic-delivery privacy_guard.py: a banlisted identifier in the title or body of a GitHub write is denied for
every tool form comms_guard reads unless the write's explicit target is a sibling repository of the session origin's owner, a write
into the Perun repository from another repository's session that names that repository is denied too, the reason carries line and pattern numbers but never the matched text or the name, and every failure to read allows.
Fixtures are fictional (Acme Capital, nightjar-7, acme/acme-widgets) in throwaway git repos; no network, no real banlist."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, ".claude/skills/agentic-delivery")
GUARD = os.path.join(SK, "scripts/privacy_guard.py")
TEMPLATE = os.path.join(SK, "templates/operating-layer.settings.json")
sys.path.insert(0, os.path.dirname(GUARD))
import comms_guard as G  # noqa: E402
import privacy_guard as P  # noqa: E402

IDENT = "Acme Capital"  # banned by the local banlist: pattern 3
CODE = "nightjar-7"  # banned by the committed banlist: pattern 1 (the leading spaces of its line are stripped)
COMMITTED = "# fixture banlist\n# Globex Corp is a comment, never a pattern\n\n# --- Names ---\n  [Nn]ightjar-[0-9]\n(unclosed\n"  # 2 patterns, the 2nd an invalid ERE
LOCAL = "Acme Capital\n"
URL = "https://api.github.com/repos/o/r"


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=Jane Smith", "-c", "user.email=jane@example.com", *args], cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="privacy-guard-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.make("repo", COMMITTED, LOCAL)

    def make(self, name, committed=None, local=None):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        git(d, "init", "-q")
        for f, text in ((".banlist.txt", committed), (".banlist.local.txt", local)):
            if text is not None:
                with open(os.path.join(d, f), "w") as fh:
                    fh.write(text)
        return d

    def write(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def hook(self, cmd, cwd=None, env=None, tool="Bash", raw=None):
        e = {k: v for k, v in os.environ.items() if k != "PERUN_PRIVACY_GUARD"}
        e.update(env or {})
        payload = raw if raw is not None else json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": cwd or self.repo})
        p = subprocess.run([sys.executable, GUARD], input=payload, capture_output=True, text=True, env=e)
        return p.returncode, p.stdout, p.stderr

    def denied(self, cmd, **kw):
        rc, out, err = self.hook(cmd, **kw)
        self.assertEqual((rc, out), (2, ""), cmd)
        self.assertNotIn(IDENT, out + err, "the reason must never echo the matched text")
        self.assertNotIn(CODE, out + err)
        return err

    def allowed(self, cmd, **kw):
        self.assertEqual(self.hook(cmd, **kw), (0, "", ""), cmd)


class Deny(Base):
    def test_every_write_form_is_denied_without_echoing_the_text(self):
        body = self.write("body.md", f"intro\n{IDENT}\n")
        data = self.write("data.json", json.dumps({"title": "t", "body": f"see {IDENT}"}))
        forms = [
            f"gh pr create --title t --body 'Moves {IDENT} to the new queue'",
            f"gh pr edit 4 -b 'note: {IDENT}'",
            f"gh issue create --title t --body \"$(cat <<'EOF'\nline one\nline two {IDENT}\nEOF\n)\"",
            f"gh issue comment 3 --body-file {body}",
            f"gh pr comment 5 -F - <<'EOF'\n{IDENT}\nEOF",
            f"gh release create v1 --notes 'for {IDENT}'",
            f"cd {self.repo} && git push && gh pr create --title t --body '{IDENT}'",
            f"gh api repos/o/r/issues -f body='{IDENT}'",
            f"gh api repos/o/r/pulls -F body=@{body}",
            f"gh api repos/o/r/issues --input {data}",
            f"curl -X POST {URL}/issues/7/comments -d '{{\"body\":\"{IDENT}\"}}'",
            f"curl -X PATCH {URL}/pulls/9 --data-binary @{data}",
        ]
        for cmd in forms:
            self.assertIn("body line", self.denied(cmd), cmd)

    def test_every_title_form_is_denied(self):
        forms = [
            f"gh pr create --title '{IDENT} rollout' --body ok",
            f"gh issue create -t \"{IDENT}\" -b ok",
            f"gh release create v1 --title '{IDENT}' --notes ok",
            f"gh pr edit 2 --title=\"{IDENT}x\"",
            f"gh api repos/o/r/issues -f title='{IDENT}' -f body=ok",
            f"curl -X POST {URL}/pulls -d '{{\"title\":\"{IDENT}\",\"body\":\"ok\"}}'",
        ]
        for cmd in forms:
            err = self.denied(cmd)
            self.assertIn("title (pattern 3)", err, cmd)
            self.assertNotIn("body line", err, cmd)

    def test_reason_gives_line_and_pattern_numbers_only(self):
        err = self.denied(f"gh pr create --title t --body \"$(cat <<'EOF'\nfine\nstill fine\n{IDENT} and {CODE}\nEOF\n)\"")
        # line 3 matches pattern 1 (committed) and pattern 3 (local); pattern 2 is an invalid ERE and is skipped, not renumbered
        self.assertIn("body line 3 (pattern 1); body line 3 (pattern 3).", err)

    def test_reason_names_five_hits_and_counts_the_rest(self):
        lines = "\n".join(f"row {n} {IDENT}" for n in range(7))
        err = self.denied(f"gh issue comment 1 --body '{lines}'")
        self.assertEqual((err.count("(pattern 3)"), "; 2 more." in err), (5, True))

    def test_matching_is_grep_ere_and_case_sensitive(self):
        posix = self.make("posix", "[[:upper:]]{3}-[0-9]{4}\n")  # a POSIX class: Python's re would read it as a different set
        self.assertEqual(self.hook("gh issue comment 1 -b 'see ABC-1234'", cwd=posix)[0], 2)
        self.assertEqual(self.hook("gh issue comment 1 -b 'see abc-1234'", cwd=posix)[0], 0)

    def test_linked_worktree_reads_the_main_checkouts_local_banlist(self):
        git(self.repo, "add", ".banlist.txt")
        git(self.repo, "commit", "-q", "-m", "init")
        wt = os.path.join(self.tmp, "wt")
        git(self.repo, "worktree", "add", "-q", wt, "-b", "lane")
        self.assertFalse(os.path.exists(os.path.join(wt, ".banlist.local.txt")))  # gitignored files are not checked out
        self.assertIn("pattern 3", self.denied(f"gh pr create --title t --body '{IDENT}'", cwd=wt))
        self.assertIn("pattern 1", self.denied(f"gh pr create --title t --body '{CODE}'", cwd=wt))


class Allow(Base):
    def test_clean_text_and_unrelated_commands(self):
        for cmd in ("gh pr create --title t --body 'all good'", "gh issue comment 3 -b 'Globex Corp is only a comment in the banlist'",
                    f"git commit -m '{IDENT}'", f"gh pr list --search '{IDENT}'", "gh pr view 5", "ls -la",
                    f"echo {IDENT}", f"gh api repos/o/r/issues -f state=closed -f note='{IDENT}'"):
            self.allowed(cmd)

    def test_no_repo_no_banlist_or_a_banlist_with_no_patterns(self):
        nogit = os.path.join(self.tmp, "nogit")
        os.makedirs(nogit)
        for cwd in (self.make("bare"), self.make("empty", "# only a comment\n   \n# --- Names ---\n"), nogit):
            self.allowed(f"gh pr create --title '{IDENT}' --body '{IDENT}'", cwd=cwd)

    def test_unreadable_body_allows_but_a_readable_title_is_still_checked(self):
        self.allowed("gh pr create --title t --body-file /nonexistent/body.md")
        self.allowed(f"curl -X POST {URL}/issues -d 'not json'")
        self.assertIn("title (pattern 3)", self.denied(f"gh pr create --title '{IDENT}' --body-file /nonexistent/body.md"))

    def test_opt_out_env(self):
        for v in ("off", "0", "FALSE"):
            self.allowed(f"gh pr create --title t --body '{IDENT}'", env={"PERUN_PRIVACY_GUARD": v})

    def test_fail_open_on_bad_input_and_other_tools(self):
        for raw in ("not json", "", "[]", json.dumps({"tool_name": "Bash", "tool_input": [1]}), json.dumps({"tool_name": "Bash", "tool_input": {"command": 7}})):
            self.assertEqual(self.hook("", raw=raw), (0, "", ""), raw)
        self.allowed(f"gh pr create --title t --body '{IDENT}'", tool="Edit")


class RestField(unittest.TestCase):
    def test_title_and_body_from_each_rest_form(self):
        with tempfile.TemporaryDirectory(prefix="privacy-guard-rest-") as d:
            for name, text in (("t.txt", "File title"), ("b.txt", "File body"), ("j.json", json.dumps({"title": "Json title", "body": "Json body"}))):
                with open(os.path.join(d, name), "w") as fh:
                    fh.write(text)
            cases = [
                ("gh api repos/o/r/issues -f title=Plain -f body=B", "title", "Plain"),
                ("gh api repos/o/r/issues -f body=B -f 'title=Quoted title'", "title", "Quoted title"),
                ("gh api repos/o/r/issues -F title=@t.txt", "title", "File title"),
                ("gh api repos/o/r/issues --input j.json", "title", "Json title"),
                ("curl -X POST u/repos/o/r/pulls -d @j.json", "body", "Json body"),
                ("curl -X POST u/repos/o/r/pulls -d '{\"title\":\"Curl title\"}'", "title", "Curl title"),
                ("gh api repos/o/r/issues -f body=B", "title", None),
                ("gh api repos/o/r/issues -F body=@b.txt --jq .id", "body", "File body"),  # more arguments after the file
                ("gh api repos/o/r/issues -F 'body=@b.txt' -f title=t", "body", "File body"),
                ("gh api repos/o/r/issues -F body=@b.txt && echo done", "body", "File body"),
            ]
            for cmd, key, want in cases:
                self.assertEqual(G._rest_field(cmd, d, key), want, cmd)


class Extraction(Base):
    def test_body_file_field_with_more_arguments_after_it(self):
        body = self.write("body.md", f"intro\n{IDENT}\n")
        for cmd in (f"gh api repos/o/r/issues/5/comments -F body=@{body} --jq .id", f"gh api repos/o/r/issues -F body=@{body} -f title=t",
                    f"gh api repos/o/r/issues -F body=@{body} && echo done", f"gh api repos/o/r/issues -F 'body=@{body}' --jq .id",
                    f"gh api repos/o/r/issues -F \"body=@{body}\" --jq .id", f"gh api repos/o/r/issues -f title=t -F body=@{body}"):
            self.assertIn("body line 2 (pattern 3)", self.denied(cmd), cmd)

    def test_a_flag_like_word_inside_a_quoted_value_or_a_heredoc_body_is_not_a_flag(self):
        body = self.write("body.md", f"intro\n{IDENT}\n")
        stray = "It's the \"foo\" thing, don't \"bar -t x"  # quotes that pair with nothing, and a flag-like word
        for cmd, want in ((f"gh pr create --title \"Add -b flag\" --body \"{IDENT}\"", "body line 1 (pattern 3)"),
                          (f"gh issue create --title \"Support -F option\" --body-file {body}", "body line 2 (pattern 3)"),
                          (f"gh pr create --body \"run pytest -t smoke\" --title \"{IDENT}\"", "title (pattern 3)"),
                          (f"gh pr create --body \"$(cat <<'EOF'\n{stray}\nEOF\n)\" --title \"{IDENT}\"", "title (pattern 3)")):
            self.assertIn(want, self.denied(cmd), cmd)
        self.allowed("gh pr create --title \"Add -b flag\" --body \"fine\"")

    def test_every_write_in_a_command_is_read(self):
        for cmd in (f"gh issue comment 1 -b ok && gh issue comment 2 -b '{IDENT}'", f"echo 'gh pr create later'; gh api repos/o/r/issues -f body='{IDENT}'"):
            self.assertIn("body line 1 (pattern 3)", self.denied(cmd), cmd)
        self.assertIn("body line 1 (pattern 1); body line 1 (pattern 3)", self.denied(f"gh issue comment 1 -b '{CODE}' && gh issue comment 2 -b '{IDENT}'"))
        self.allowed("gh issue comment 1 -b ok && gh issue comment 2 -b fine")


class SelfWritten(Base):
    def test_a_body_file_the_command_writes_is_read_from_its_heredocs(self):
        f = os.path.join(self.tmp, "new-body.md")  # absent on disk
        for write in (f"cat > {f} <<'EOF'", f"cat >> {f} <<'EOF'", f"tee {f} <<'EOF'", f"tee -a '{f}' <<'EOF'"):
            for send in (f"gh pr create --title t --body-file {f}", f"gh issue comment 1 --body \"$(cat {f})\"", f"gh api repos/o/r/issues -F body=@{f}"):
                self.assertIn("body line 2 (pattern 3)", self.denied(f"{write}\nfine\n{IDENT}\nEOF\n{send}"), (write, send))
        self.assertFalse(os.path.exists(f))

    def test_a_stale_body_file_rewritten_in_the_same_command_is_not_scanned(self):
        stale = self.write("stale.md", f"old draft {IDENT}\n")
        self.denied(f"gh pr create --title t --body-file {stale}")  # control: with no rewrite, the old text on disk goes out
        self.allowed(f"cat > {stale} <<'EOF'\nreworded\nEOF\ngh pr create --title t --body-file {stale}")
        self.allowed(f"cat > {stale} <<'EOF'\nreworded\nEOF\ngh api repos/o/r/issues -F body=@{stale}")


class OwnRepo(Base):
    """A write into SELF_REPO from a session whose origin is another repository must not name that repository."""
    TEXT = "Field report: acme-widgets crashed"

    def session(self, name, url):
        d = self.make(name)  # no banlist: the rule does not need one
        if url:
            git(d, "remote", "add", "origin", url)
        return d

    def test_denied_when_a_write_to_perun_names_the_session_repository(self):
        s = self.session("https", "https://github.com/acme/acme-widgets.git")
        t = self.TEXT
        for cmd in (f"gh issue create -R protocol/perun --title t --body '{t}'", f"gh issue create --repo protocol/perun --title t --body '{t}'",
                    f"gh issue create --repo=protocol/perun --title t --body '{t}'", f"gh issue create --title t --body '{t}' -R \"protocol/perun\"",
                    f"gh api repos/protocol/perun/issues -f title=t -f body='{t}'", f"gh pr comment https://github.com/protocol/perun/pull/12 --body '{t}'",
                    f"curl -X POST https://api.github.com/repos/protocol/perun/issues -d '{{\"title\":\"t\",\"body\":\"{t}\"}}'",
                    "gh issue create -R PROTOCOL/Perun --title t --body 'ACME-WIDGETS again'"):
            err = self.denied(cmd, cwd=s)
            self.assertIn("this write to protocol/perun names the session's own repository", err, cmd)
            self.assertIn("body line 1", err, cmd)
            self.assertNotIn("acme", err.lower(), "the reason must not name the session repository")

    def test_title_owner_slash_name_and_an_ssh_origin(self):
        err = self.denied("gh issue create -R protocol/perun --title 'About acme/acme-widgets' --body ok", cwd=self.session("ssh", "git@github.com:acme/acme-widgets"))
        self.assertIn("(name withheld): title.", err)
        self.assertNotIn("acme", err.lower())

    def test_allowed_elsewhere_or_with_no_other_repository_in_play(self):
        s, t = self.session("https", "https://github.com/acme/acme-widgets.git"), self.TEXT
        for cmd in (f"gh issue create -R other/repo --title t --body '{t}'", f"gh issue create --title t --body '{t}'",
                    f"gh issue create -R protocol/perun-extras --title t --body '{t}'", "gh issue create -R protocol/perun --title t --body 'a plain report'"):
            self.allowed(cmd, cwd=s)
        for name, url, text in (("perun", "git@github.com:protocol/perun.git", "see protocol/perun"), ("perun2", "https://github.com/Protocol/Perun", "see protocol/perun"),
                                ("none", None, t), ("bare", "somewhere", t)):  # the session is Perun itself, or has no usable origin
            self.allowed(f"gh issue create -R protocol/perun --title t --body '{text}'", cwd=self.session(name, url))

    def test_a_bare_name_counts_only_when_distinctive(self):
        s = self.session("app", "https://github.com/acme/app.git")  # 3 plain characters: ordinary English
        self.allowed("gh issue create -R protocol/perun --title t --body 'the app crashed'", cwd=s)
        self.assertIn("body line 1", self.denied("gh issue create -R protocol/perun --title t --body 'see acme/app'", cwd=s))
        for name, rc in (("widgets", 0), ("gadgetry", 2), ("my_pkg", 2)):  # 7 plain characters, 8, and an underscore
            s = self.session(name, f"https://github.com/acme/{name}")
            self.assertEqual(self.hook(f"gh issue create -R protocol/perun --title t --body 'the {name} crashed'", cwd=s)[0], rc, name)

    def test_whole_word_and_case_insensitive(self):
        s = self.session("dots", "https://github.com/acme/site.io")
        for text, rc in (("see site.io", 2), ("see SITE.IO.", 2), ("mysite.io", 0), ("site.iox", 0), ("siteXio", 0)):
            self.assertEqual(self.hook(f"gh issue create -R protocol/perun --title t --body '{text}'", cwd=s)[0], rc, text)

    def test_banlist_and_own_repository_hits_are_both_reported(self):
        git(self.repo, "remote", "add", "origin", "https://github.com/acme/acme-widgets.git")
        err = self.denied(f"gh issue create -R protocol/perun --title t --body 'acme-widgets and {IDENT}'")
        self.assertIn("matches the repo banlist (matched text withheld): body line 1 (pattern 3).", err)
        self.assertIn("names the session's own repository (name withheld): body line 1.", err)
        self.assertNotIn("acme", err.lower())

    def test_a_failing_git_means_no_rule_not_an_error(self):
        for exc in (OSError(), subprocess.TimeoutExpired("git", 5)):
            with mock.patch.object(P.subprocess, "run", side_effect=exc):
                self.assertEqual((P._git(self.repo, "status"), P._own_names(self.repo)), ("", None))


class Scope(Base):
    """The banlist scan is skipped only for a write whose explicit target is a sibling: another repository of the session origin's owner.
    The session here is acme/acme-widgets; the banlist has no entry for any repository name."""

    def setUp(self):
        super().setUp()
        git(self.repo, "remote", "add", "origin", "https://github.com/acme/acme-widgets.git")

    def test_a_sibling_target_is_not_scanned(self):
        t = f"'{IDENT} and {CODE}'"
        for cmd in (f"gh pr create --repo acme/acme-gadgets --title t --body {t}", f"gh issue create -R acme/acme-gadgets --title t --body {t}",
                    f"gh issue create --repo=acme/acme-gadgets --title t --body {t}", f"gh issue create -R \"acme/acme-gadgets\" --title t --body {t}",
                    f"gh issue create -R github.com/ACME/Acme-Gadgets --title t --body {t}", f"gh issue create --title '{IDENT}' -R acme/acme-gadgets --body ok",
                    f"gh issue comment https://github.com/acme/acme-gadgets/issues/5 --body {t}", f"gh api repos/acme/acme-gadgets/issues -f title=t -f body={t}",
                    f"gh issue create --repo https://github.com/acme/acme-gadgets.git --title t --body {t}",
                    f"curl -X POST 'https://api.github.com/repos/acme/acme-gadgets/issues' -d '{{\"title\":\"{IDENT}\"}}'"):
            self.allowed(cmd)

    def test_the_own_repository_perun_and_other_owners_are_scanned(self):
        for cmd in (f"gh issue create --title t --body '{IDENT}'", f"gh issue create -R acme/acme-widgets --title t --body '{IDENT}'",
                    f"gh issue create -R ACME/Acme-Widgets --title t --body '{IDENT}'", f"gh api repos/acme/acme-widgets/issues -f title=t -f body='{IDENT}'",
                    f"gh issue create -R protocol/perun --title t --body '{IDENT}'", f"gh issue create -R other/acme-gadgets --title t --body '{IDENT}'",
                    f"gh api repos/other/acme-gadgets/issues -f body='{IDENT}'", f"gh issue comment https://github.com/other/acme-gadgets/issues/5 --body '{IDENT}'",
                    f"gh issue create -R acme/acme-gadgets -R protocol/perun --title t --body '{IDENT}'",  # a sibling and Perun
                    f"gh issue create --repo https://github.com/acme/acme-widgets.git --title t --body '{IDENT}'",  # the clone URL of the session repository
                    f"gh pr create --title t --body '{IDENT}' -r acme/reviewers"):  # -r names a reviewer, not a repository
            self.assertIn("(pattern 3)", self.denied(cmd), cmd)

    def test_the_origin_matches_in_any_case(self):
        s = self.make("upper", COMMITTED, LOCAL)
        git(s, "remote", "add", "origin", "https://github.com/ACME/Acme-Widgets.git")
        self.allowed(f"gh issue create -R acme/acme-gadgets --title t --body '{IDENT}'", cwd=s)
        self.assertIn("(pattern 3)", self.denied(f"gh issue create -R acme/acme-widgets --title t --body '{IDENT}'", cwd=s))

    def test_perun_is_scanned_under_an_origin_in_its_own_org(self):
        s = self.make("org", COMMITTED, LOCAL)
        git(s, "remote", "add", "origin", "https://github.com/protocol/other-tool.git")
        self.assertIn("(pattern 3)", self.denied(f"gh issue create -R protocol/perun --title t --body '{IDENT}'", cwd=s))
        self.allowed(f"gh issue create -R protocol/another --title t --body '{IDENT}'", cwd=s)

    def test_no_usable_origin_scans_everything(self):
        for name, url in (("none", None), ("bare", "somewhere"), ("perun", "git@github.com:protocol/perun.git")):
            s = self.make(name, COMMITTED, LOCAL)
            if url:
                git(s, "remote", "add", "origin", url)
            self.assertIn("(pattern 3)", self.denied(f"gh issue create -R protocol/another --title t --body '{IDENT}'", cwd=s), name)

    def test_text_that_only_names_a_sibling_sets_no_target(self):
        s, sib = "https://github.com/acme/acme-gadgets/issues/3", "repos/acme/acme-gadgets/issues/3"
        os.makedirs(os.path.join(self.tmp, "repos/acme/acme-gadgets"))
        bodyfile = self.write("repos/acme/acme-gadgets/body.md", "ok")
        for cmd in (f"gh issue create --title t --body 'fixed in {sib}: {IDENT}'", f"gh issue create --title t --body 'see gh issue list -R acme/acme-gadgets: {IDENT}'",
                    f"gh issue create --title t --body '{IDENT}' # -R acme/other",
                    f"gh issue create --title t --body \"say \\\"hi\\\" {s} {IDENT}\"", f"gh issue create --title t --body \"$(cat <<'EOF'\nsee {s}\n{IDENT}\nEOF\n)\"",
                    f"gh issue create --title t --body-file - <<'EOF'\nsee {s}\n{IDENT}\nEOF",
                    f"gh issue create --title '{IDENT}' --body {s}", f"gh issue create --title '{IDENT}' --body '{s}'",
                    f"gh issue create --title '{IDENT}' --body-file {bodyfile}", f"gh api repos/acme/acme-widgets/issues -f title='{IDENT}' -f body={s}",
                    f"gh api repos/acme/acme-widgets/issues -f title=t -f body='see {sib} {IDENT}'",
                    f"curl -X POST https://api.github.com/repos/acme/acme-widgets/issues -d '{{\"body\":\"see {sib} {IDENT}\"}}'"):
            self.assertIn("(pattern 3)", self.denied(cmd), cmd)

    def test_a_sibling_write_does_not_exempt_the_next_write(self):
        sib, own = f"gh issue create -R acme/acme-gadgets --title t --body '{IDENT}'", f"gh issue create --title t --body '{IDENT}'"
        for cmd in (f"{sib} && {own}", f"{own} && {sib}", f"{sib}\n{own}"):
            self.assertIn("body line 1 (pattern 3).", self.denied(cmd), cmd)
        self.allowed(f"{sib} && {sib}")

    def test_text_beside_a_write_is_not_its_target(self):
        perun = "https://github.com/protocol/perun"
        head = "gh pr create --title 'Fix acme-widgets crash' --body ok"
        for cmd in (f"gh issue comment 5 --body 'Tracked upstream: {perun}/issues/12 ; acme-widgets workaround in PR 4'",
                    f"gh issue comment 5 --body 'Tracked upstream: {perun}/issues/12 ; see acme/acme-widgets#4'",
                    f"{head} && gh issue create -R protocol/perun --title t --body ok", f"{head} && echo 'filed {perun}/issues/3'",
                    f"{head} && echo filed {perun}/issues/3", f"{head}; echo filed {perun}/issues/3", f"{head}\necho filed {perun}/issues/3",
                    f"{head} # filed {perun}/issues/3",
                    f"{head} & gh issue create -R protocol/perun --title t --body ok", f"gh pr create --title t --body \"$(cat <<'EOF'\nacme-widgets, see {perun}/pull/9\nEOF\n)\"",
                    "gh pr create --title t --body 'run gh issue list -R protocol/perun to see acme-widgets items'"):
            self.allowed(cmd)

    def test_a_write_into_perun_naming_the_session_repository_is_still_denied(self):
        t = "'acme-widgets crashed'"
        for cmd in (f"gh issue create -R protocol/perun --body {t}", f"gh issue create -R protocol/perun --title t --body {t}",
                    f"gh pr create --title t --body ok && gh issue create -R protocol/perun --title t --body {t}",
                    f"gh pr create --title t --body ok & gh issue create -R protocol/perun --title t --body {t}",
                    f"cd /tmp && gh issue create --title t --body {t} -R protocol/perun", f"gh issue create --title t \\\n  -R protocol/perun \\\n  --body {t}",
                    f"bash -c \"gh issue create -R protocol/perun --title t --body {t}\"",
                    f"curl -s https://x.example/y | jq . && gh api repos/protocol/perun/issues -f title=t -f body={t}",
                    "curl -X POST -d '{\"body\":\"gh issue comment: acme-widgets\"}' https://api.github.com/repos/protocol/perun/issues"):
            self.assertIn("names the session's own repository", self.denied(cmd), cmd)


class RawFieldVersusFile(Base):
    """gh reads `@FILE` only for -F/--field; -f/--raw-field sends the text as typed (`@jane` is a mention), and an unreadable `@FILE` is scanned as typed."""

    def test_f_text_starting_with_an_at_sign_is_scanned(self):
        for cmd in (f"gh api repos/o/r/issues -f body='@jane thanks, {IDENT} is done'", f"gh api repos/o/r/issues -f title='@jane {IDENT}'",
                    f"gh api repos/o/r/issues --raw-field body='@jane {IDENT}'", f"gh api repos/o/r/issues -f 'body=@jane {IDENT}'"):
            self.denied(cmd)

    def test_only_a_capital_F_reads_the_file(self):
        body = self.write("body.md", f"intro\n{IDENT}\n")
        self.allowed(f"gh api repos/o/r/issues -f title=t -f body=@{body}")
        for flag in ("-F", "--field"):
            self.assertIn("body line 2 (pattern 3)", self.denied(f"gh api repos/o/r/issues -f title=t {flag} body=@{body}"))

    def test_an_unreadable_F_file_is_scanned_as_typed(self):
        self.denied(f"gh api repos/o/r/issues -F body='@jane thanks, {IDENT}'")
        self.denied(f"gh api repos/o/r/issues --field body='@jane {IDENT}'")
        self.allowed("gh api repos/o/r/issues -F body=@/nonexistent/body.md -f title=t")

    def test_the_extraction_itself(self):
        tail = "gh api repos/o/r/issues -f body=@jane -F title=@/nonexistent/t.md"
        self.assertEqual(G._rest_field(tail, "", "body"), "@jane")
        with self.assertRaises(OSError):  # the comms lint keeps treating an unreadable file as no body
            G._rest_field(tail, "", "title")
        self.assertEqual(G._rest_field(tail, "", "title", True), "@/nonexistent/t.md")
        self.assertEqual(G.extract("Bash", {"command": "gh api repos/o/r/issues -f body='@jane hello'"}), ("message", "@jane hello"))


class FeedingHeredoc(Base):
    """A body file the command writes itself is read as the heredoc that feeds it, not as every heredoc in the command."""

    def test_an_unrelated_heredoc_is_not_the_body(self):
        f = os.path.join(self.tmp, "b.md")
        noise, commit = f"python3 - <<'PY'\nprint('{IDENT}')\nPY\n", f"git commit -m \"$(cat <<'EOF'\n{IDENT} fix\nEOF\n)\"\n"
        for feed in (f"cat > {f} <<'EOF'\nclean body\nEOF\n", f"cat >> {f} <<'EOF'\nclean body\nEOF\n", f"tee {f} <<'EOF'\nclean body\nEOF\n"):
            for other in (noise, commit):
                for cmd in (other + feed, feed + other):
                    self.allowed(f"{cmd}gh pr create --title t --body-file {f}")

    def test_the_feeding_heredoc_is_still_scanned(self):
        f = os.path.join(self.tmp, "b.md")
        err = self.denied(f"python3 - <<'PY'\nprint('ok')\nPY\ncat > {f} <<'EOF'\nintro\n{IDENT}\nEOF\ngh pr create --title t --body-file {f}")
        self.assertIn("body line 2 (pattern 3)", err)


class Wiring(unittest.TestCase):
    def test_registered_once_on_bash_without_or_true_and_known_to_the_doctor(self):
        with open(TEMPLATE) as fh:
            pre = json.load(fh)["hooks"]["PreToolUse"]
        found = [(e["matcher"], h["command"]) for e in pre for h in e["hooks"] if "privacy_guard.py" in h["command"]]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "Bash")
        self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/skills/agentic-delivery/scripts/privacy_guard.py"', found[0][1])
        self.assertNotIn("|| true", found[0][1])  # exit 2 is the deny; `|| true` would turn it into an allow
        with open(os.path.join(ROOT, "scripts/perun_doctor.py")) as fh:
            self.assertIn('"privacy_guard.py"', fh.read())


if __name__ == "__main__":
    unittest.main()
