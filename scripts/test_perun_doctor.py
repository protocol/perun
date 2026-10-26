#!/usr/bin/env python3
"""Tests for perun_doctor.py, perun_uninstall.py and install.sh default-on operating layer (temp repos)."""
import contextlib, io, json, os, re, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perun_doctor  # noqa: E402

HAS_JQ = shutil.which("jq") is not None
os.environ["DCR_NO_PROBE"] = "1"  # no network/probe in temp-repo tests; probe has its own tests


def install(repo, *flags):
    return subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(repo)], capture_output=True, text=True)


def rows(repo, home):
    return {c: (s, d) for s, c, d in perun_doctor.check(Path(repo), Path(home))}


@unittest.skipUnless(HAS_JQ, "jq needed to apply the operating layer")
class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo, self.home = self.tmp / "r", self.tmp / "h"
        self.repo.mkdir(); self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_default_on_applies_layer_and_prints_summary(self):
        p = install(self.repo, "--with-delivery")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("What changed in", p.stdout)
        self.assertIn("perun_uninstall.py", p.stdout)
        self.assertIn("subagent_start_inject.py", (self.repo / ".claude/settings.local.json").read_text())
        self.assertEqual(rows(self.repo, self.home)["hooks wired"][0], "OK")

    def test_install_ends_with_three_plain_lines(self):
        p = install(self.repo, "--with-delivery")
        last = p.stdout.rstrip("\n").split("\n")[-3:]
        self.assertRegex(last[0], r"^Perun installed \d+ skill\(s\) into \d+ tool folder\(s\)")
        self.assertIn("Next, run this one command", last[1])
        self.assertIn("perun_doctor.py", last[1])
        self.assertIn("To undo everything", last[2])
        self.assertIn("perun_uninstall.py", last[2])

    def test_doctor_leads_with_verdict(self):
        install(self.repo, "--with-delivery")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            perun_doctor.main([str(self.repo), "--home", str(self.home)])
        first = out.getvalue().splitlines()[0]
        self.assertRegex(first, r"^(Healthy|\d+ things? needs? attention: )")
        (self.repo / ".claude/skills/agentic-delivery/scripts/handback_cap.py").unlink()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            perun_doctor.main([str(self.repo), "--home", str(self.home)])
        self.assertRegex(out.getvalue().splitlines()[0], r"^\d+ things? needs? attention: run python3 .*--fix")

    def test_opt_out_leaves_no_settings(self):
        install(self.repo, "--with-delivery", "--no-operating-layer")
        self.assertFalse((self.repo / ".claude/settings.local.json").exists())
        self.assertEqual(rows(self.repo, self.home)["hooks wired"][0], "OK")  # opted out is not a failure

    def test_conflicting_flags_rejected(self):
        self.assertNotEqual(install(self.repo, "--with-delivery", "--apply-operating-layer", "--no-operating-layer").returncode, 0)

    def test_installed_but_never_runs(self):
        install(self.repo, "--with-delivery", "--no-operating-layer")
        (self.repo / ".claude/.dcr-install-flags").write_text("--with-delivery\n")  # not opted out, no hooks
        r = rows(self.repo, self.home)["hooks wired"]
        self.assertEqual(r[0], "FAIL")
        self.assertIn("never runs", r[1])

    def test_missing_hook_file_and_drift(self):
        install(self.repo, "--with-delivery")
        (self.repo / ".claude/skills/agentic-delivery/scripts/handback_cap.py").unlink()
        fork = self.repo / "tools"; fork.mkdir()
        shutil.copy(ROOT / ".claude/skills/agentic-delivery/scripts/lane_cap.py", fork / "lane_cap.py")
        (fork / "lane_cap.py").write_text("# forked\n")
        r = rows(self.repo, self.home)
        self.assertEqual(r["hook files exist"][0], "FAIL")
        self.assertIn("handback_cap.py", r["hook files exist"][1])
        self.assertEqual(r["drifted copies"][0], "WARN")
        self.assertIn("lane_cap.py", r["drifted copies"][1])

    def test_stale_versions_and_policy_janitor(self):
        install(self.repo, "--with-delivery")
        (self.repo / ".claude/skills/deep-code-review/VERSION").write_text("0.0.1\n")
        (self.home / ".claude/skills/deep-code-review").mkdir(parents=True)
        (self.home / ".claude/skills/deep-code-review/VERSION").write_text("0.0.2\n")
        r = rows(self.repo, self.home)
        self.assertEqual(r["installed version"][0], "WARN")
        self.assertEqual(r["global copy"][0], "WARN")
        self.assertEqual(r["policy file"][0], "INFO")
        self.assertEqual(r["janitor/scheduler"][0], "INFO")
        (self.repo / "perun-policy.json").write_text("{}")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/janitor.sh").write_text("#!/bin/sh\n")
        r = rows(self.repo, self.home)
        self.assertEqual((r["policy file"][0], r["janitor/scheduler"][0]), ("OK", "OK"))

    def _break(self):
        (self.repo / ".claude/skills/agentic-delivery/scripts/handback_cap.py").write_text("# stale fork\n")
        (self.repo / ".claude/settings.local.json").unlink()

    def test_fix_needs_confirmation(self):
        install(self.repo, "--with-delivery")
        self._break()
        with mock.patch("sys.stdin.isatty", return_value=False):  # no TTY, no --yes: refuse, change nothing
            self.assertEqual(perun_doctor.main([str(self.repo), "--fix", "--home", str(self.home)]), 2)
        self.assertFalse((self.repo / ".claude/settings.local.json").exists())
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="y"):
            self.assertEqual(perun_doctor.main([str(self.repo), "--fix", "--home", str(self.home)]), 2)
        self.assertFalse((self.repo / ".claude/settings.local.json").exists())
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="yes"):
            perun_doctor.main([str(self.repo), "--fix", "--home", str(self.home)])
        self.assertEqual(rows(self.repo, self.home)["hooks wired"][0], "OK")

    def test_fix_yes_warns_repairs_and_previews_default_on(self):
        install(self.repo, "--with-delivery")
        self._break()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = perun_doctor.main([str(self.repo), "--fix", "--yes", "--home", str(self.home)])
        self.assertIn("without an interactive confirmation", err.getvalue())
        self.assertIn("Default-on operating layer", out.getvalue())
        self.assertIn("model:", out.getvalue())
        r = rows(self.repo, self.home)
        self.assertEqual((r["hooks wired"][0], r["hook files exist"][0]), ("OK", "OK"))
        self.assertTrue(list((self.repo / ".claude/skill-backups").glob("agentic-delivery-*")))  # fork preserved
        self.assertEqual(rc, 0)  # janitor/policy are INFO: fix never invents them and they never fail the exit code

    def test_fix_fails_loudly_when_reinstall_fails(self):
        install(self.repo, "--with-delivery")
        self._break()
        err = io.StringIO()
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = perun_doctor.main([str(self.repo), "--fix", "--yes", "--home", str(self.home)])
        self.assertEqual(rc, 2)
        self.assertIn("update-installed.sh failed", err.getvalue())

    def test_bak_is_timestamped_never_overwritten(self):
        cfg = self.repo / ".claude/settings.local.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"mine": 1}))
        install(self.repo, "--with-delivery")
        c = json.loads(cfg.read_text()); c["hooks"].pop("PreToolUse"); cfg.write_text(json.dumps(c))
        install(self.repo, "--with-delivery")
        baks = sorted(cfg.parent.glob("settings.local.json.bak.*"))
        self.assertEqual(len(baks), 2)
        self.assertEqual(json.loads(baks[0].read_text()), {"mine": 1})  # first backup survived the second install

    def test_summary_names_model_pin(self):
        self.assertIn("sonnet, set only if you had none", install(self.repo, "--with-delivery").stdout)
        r2 = self.tmp / "r2"; r2.mkdir(); (r2 / ".claude").mkdir()
        (r2 / ".claude/settings.local.json").write_text('{"model": "opus"}')
        self.assertIn("your existing model kept", install(r2, "--with-delivery").stdout)


@unittest.skipUnless(HAS_JQ, "jq needed to apply the operating layer")
class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "r"
        self.repo.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = self.repo / ".claude/settings.local.json"

    def cli(self, *a):
        return subprocess.run([sys.executable, str(ROOT / "scripts/perun_uninstall.py"), str(self.repo), *a], capture_output=True, text=True)

    def test_dry_run_is_default_and_inert(self):
        install(self.repo, "--with-delivery")
        before = self.cfg.read_text()
        p = self.cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("dry run", p.stdout)
        self.assertEqual(self.cfg.read_text(), before)
        self.assertTrue((self.repo / ".claude/skills/agentic-delivery").exists())
        self.assertTrue((self.repo / ".claude/.perun-install.json").exists())

    def test_apply_restores_backup_keeps_user_files_and_foreign_hooks(self):
        orig = self.repo / ".claude/skills/deep-code-review"
        orig.mkdir(parents=True)
        (orig / "SKILL.md").write_text("mine\n")
        self.cfg.write_text(json.dumps({"hooks": {"SubagentStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}, "env": {"KEEP": "1"}}))
        install(self.repo, "--with-delivery")
        install(self.repo, "--with-delivery")  # reinstall: a Perun copy lands in backups too
        ad = self.repo / ".claude/skills/agentic-delivery"
        (ad / "my-notes.md").write_text("user file\n")                         # added by user: kept
        (ad / "SKILL.md").write_text((ad / "SKILL.md").read_text() + "\nedit\n")  # edited: kept
        p = self.cli("--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("my-notes.md", p.stdout)
        self.assertEqual((ad / "my-notes.md").read_text(), "user file\n")
        self.assertTrue((ad / "SKILL.md").exists())
        self.assertFalse((ad / "references").exists())  # untouched installed files are gone
        self.assertEqual((orig / "SKILL.md").read_text(), "mine\n")  # fully removed dir -> original restored
        self.assertFalse((orig / "VERSION").exists())
        c = json.loads(self.cfg.read_text())
        self.assertEqual(c["hooks"], {"SubagentStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]})
        self.assertEqual(c["env"], {"KEEP": "1"})
        self.assertNotIn("model", c)  # Perun set it, so it is reverted
        self.assertFalse((self.repo / ".claude/.perun-install.json").exists())

    def test_preexisting_model_and_identical_hook_are_kept(self):
        t = json.loads((ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json").read_text())
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": t["hooks"]["PreToolUse"]}}))
        install(self.repo, "--with-delivery")
        self.assertEqual(self.cli("--apply").returncode, 0)
        c = json.loads(self.cfg.read_text())
        self.assertEqual(c["model"], "opus")
        self.assertEqual(c["hooks"], {"PreToolUse": t["hooks"]["PreToolUse"]})  # was yours before install: not removed by template equality
        self.assertNotIn("SubagentStart", c["hooks"])

    def test_invalid_settings_abort_with_no_change(self):
        install(self.repo, "--with-delivery")
        self.cfg.write_text("{not json")
        p = self.cli("--apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.cfg.read_text(), "{not json")
        self.assertTrue((self.repo / ".claude/skills/agentic-delivery").exists())  # nothing else touched
        self.assertFalse(list(self.cfg.parent.glob("*.perun-tmp")))

    def test_no_marker_removes_nothing(self):
        install(self.repo, "--with-delivery")
        (self.repo / ".claude/.perun-install.json").unlink()
        p = self.cli("--apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("marker", p.stderr)
        self.assertTrue((self.repo / ".claude/skills/agentic-delivery").exists())


class NoJqTests(unittest.TestCase):
    def test_clean_unrelated_repo_reports_not_installed(self):
        with tempfile.TemporaryDirectory() as t:
            r = rows(t, t)
            self.assertEqual(r["installed version"][0], "FAIL")


class SandboxProbeTests(unittest.TestCase):
    """Probe output shape with injected failures, and the doctor rows it produces."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
        import sandbox_probe
        self.sp = sandbox_probe

    def boom(self):
        raise OSError("blocked")

    def test_injected_failures_print_cause_fix_and_verdict(self):
        items = [(n, (self.boom if n in ("network", "local-bind") else (lambda: None)), c, f) for n, _, c, f in self.sp.checks(".")]
        lines, bad = self.sp.probe(items)
        self.assertEqual(bad, 2)
        self.assertEqual(len(lines), len(items) + 1)
        self.assertIn('FAIL  network: HTTPS to github.com is blocked. Fix: add "github.com" to sandbox.network.allowedDomains', lines)
        self.assertIn("FAIL  local-bind: dev servers cannot listen on localhost. Fix: set sandbox.network.allowLocalBinding: true", lines)
        self.assertIn("OK    git", lines)
        self.assertRegex(lines[-1], r"^sandbox probe: 2 of 9 checks failed; run python3 .*sandbox_probe\.py")

    def test_all_ok_verdict(self):
        lines, bad = self.sp.probe([(n, lambda: None, c, f) for n, _, c, f in self.sp.checks(".")])
        self.assertEqual(bad, 0)
        self.assertTrue(lines[-1].startswith("sandbox probe: 9/9 checks passed in this shell"))

    def test_tool_probes_skip_when_absent_and_never_install(self):
        with mock.patch.object(self.sp.shutil, "which", return_value=None), mock.patch.object(self.sp, "_exec") as run:
            lines, bad = self.sp.probe([c for c in self.sp.checks(".") if c[0] in ("gh", "chromium", "postgres", "tsx")])
        run.assert_not_called()
        self.assertEqual(bad, 0)
        self.assertEqual(lines[:4], [f"SKIP  {n}: not installed" for n in ("gh", "chromium", "postgres", "tsx")])
        self.assertIn("0/0 checks passed, 4 skipped", lines[-1])

    def _run(self, rc, err=""):
        return mock.Mock(returncode=rc, stderr=err)

    def _probe(self, name, res):
        items = [c for c in self.sp.checks(".") if c[0] == name]
        with mock.patch.object(self.sp.shutil, "which", return_value="/usr/bin/x"), \
                mock.patch.object(self.sp.os.path, "isfile", return_value=True), \
                mock.patch.object(self.sp, "_exec", side_effect=res if isinstance(res, Exception) else None, return_value=res) as self.ex:
            return self.sp.probe(items)

    def test_gh_tls_block_fails_but_unauthenticated_skips(self):
        lines, bad = self._probe("gh", self._run(1, "x509: OSStatus -26276"))
        self.assertEqual(bad, 1)
        self.assertIn('Fix: add "gh *" to sandbox.excludedCommands (sandbox_preflight.py rule: gh)', lines[0])
        lines, bad = self._probe("gh", self._run(4, "gh: To get started with GitHub CLI, please run: gh auth login"))
        self.assertEqual((bad, lines[0].split(":")[0]), (0, "SKIP  gh"))

    def test_postgres_block_fails_but_no_server_skips(self):
        lines, bad = self._probe("postgres", self._run(2, "psql: error: connection to server failed: Operation not permitted"))
        self.assertEqual(bad, 1)
        self.assertIn("sandbox_preflight.py rule: db", lines[0])
        lines, bad = self._probe("postgres", self._run(2, "psql: error: connection refused"))
        self.assertEqual((bad, lines[0].split(":")[0]), (0, "SKIP  postgres"))

    def test_chromium_and_tsx_block_or_timeout_fails_other_failure_skips(self):
        for name, rule, err in (("chromium", "browser", "bootstrap_check_in: Permission denied (1100)"),
                                ("tsx", "tsx", "Error: listen EPERM: operation not permitted /tmp/tsx-501/1.pipe")):
            lines, bad = self._probe(name, self._run(1, err))
            self.assertEqual(bad, 1)
            self.assertIn(f"sandbox_preflight.py rule: {rule}", lines[0])
            # not a sandbox block (root without --no-sandbox, old node): never advise widening the sandbox
            lines, bad = self._probe(name, self._run(1, "Running as root without --no-sandbox is not supported"))
            self.assertEqual((bad, lines[0].split(":")[0]), (0, f"SKIP  {name}"))
            self.assertEqual(self._probe(name, subprocess.TimeoutExpired("x", 20))[1], 1)
            self.assertEqual(self._probe(name, self._run(0))[0][0], f"OK    {name}")

    def test_proxy_forbidden_gh_fails_and_exit_127_skips(self):
        self.assertEqual(self._probe("gh", self._run(1, 'Post "https://api.github.com/graphql": Forbidden'))[1], 1)
        # an ordinary GitHub 403 (revoked token, SSO) is not a sandbox block
        self.assertEqual(self._probe("gh", self._run(1, "HTTP 403: Resource protected by organization SAML enforcement"))[1], 0)
        self.assertEqual(self._probe("gh", self._run(1, "HTTP 403: Forbidden (https://api.github.com/rate_limit)"))[1], 0)
        for name in ("chromium", "tsx"):
            lines, bad = self._probe(name, self._run(127, "env: node: No such file or directory"))
            self.assertEqual((bad, lines[0]), (0, f"SKIP  {name}: cannot execute (exit 127)"))

    def test_chromium_never_uses_the_real_profile(self):
        self._probe("chromium", self._run(0))
        cmd = self.ex.call_args[0][0]
        prof = [a for a in cmd if a.startswith("--user-data-dir=")]
        self.assertEqual(len(prof), 1)
        self.assertIn("perun-probe-chrome-", prof[0])

    def test_timeout_kills_the_whole_process_group(self):
        with mock.patch.object(self.sp.subprocess, "Popen") as po, mock.patch.object(self.sp.os, "killpg") as kp:
            proc = po.return_value.__enter__.return_value
            proc.pid = 4242
            proc.communicate.side_effect = [subprocess.TimeoutExpired("x", 20), ("", "")]
            with self.assertRaises(subprocess.TimeoutExpired):
                self.sp._exec(["x"])
        self.assertTrue(po.call_args.kwargs["start_new_session"])
        kp.assert_called_once_with(4242, self.sp.signal.SIGKILL)

    def test_every_fix_names_a_real_preflight_rule(self):
        import sandbox_preflight
        for name, _, _, fix in self.sp.checks("."):
            m = re.search(r"sandbox_preflight\.py rule: (\w+)", fix)
            if m:
                self.assertIn(m.group(1), sandbox_preflight.RISKS, name)

    def test_doctor_shows_skip_as_info(self):
        items = [(n, (lambda: (_ for _ in ()).throw(self.sp.Skip("not installed"))) if n == "gh" else (lambda: None), c, f)
                 for n, _, c, f in self.sp.checks(".")]
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DCR_NO_PROBE": ""}), \
                mock.patch.object(self.sp, "checks", lambda repo: items):
            r = rows(d, d)
        self.assertEqual(r["sandbox gh"], ("INFO", "not installed"))

    def test_checks_are_harmless(self):
        src = (ROOT / ".claude/skills/agentic-delivery/scripts/sandbox_probe.py").read_text()
        for bad in ('"rm"', '"kill"', "unlink(", "rmtree", "os.remove", "os.kill(", "worktree"):
            self.assertNotIn(bad, src)
        # the only signal sent is to the probe's own child process group, on timeout
        self.assertEqual(src.count("os.killpg("), 1)
        self.assertIn("os.killpg(p.pid", src)

    def test_doctor_turns_probe_failures_into_warn_rows(self):
        items = [(n, self.boom if n == "cache-write" else (lambda: None), c, f) for n, _, c, f in self.sp.checks(".")]
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DCR_NO_PROBE": ""}), \
                mock.patch.object(self.sp, "checks", lambda repo: items):
            r = rows(d, d)
        self.assertNotIn("sandbox git", r)  # d is a non-git target and its own home: no repo to probe
        self.assertEqual(r["sandbox cache-write"][0], "WARN")
        self.assertIn('Fix: add "~/.cache" to sandbox.filesystem.allowWrite', r["sandbox cache-write"][1])


if __name__ == "__main__":
    unittest.main()
