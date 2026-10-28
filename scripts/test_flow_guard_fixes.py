"""Review fixes for fitness_tick, baseline_guard, wired_check, freeze_hook and the canonical flow-guards reference."""
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/agentic-delivery"
sys.path.insert(0, str(ROOT / "scripts"))
from test_orphan_allowlist_wired import wired  # noqa: E402
from test_fitness_tick import run as tick_run  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SK / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FitnessCaller(unittest.TestCase):
    def closable(self, files):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/fit")
        os.makedirs(f"{d}/repo")
        c = pathlib.Path(f"{d}/fit/a")
        c.write_text("#!/bin/sh\nexit 0\n")
        c.chmod(0o755)
        for p, text in files.items():
            os.makedirs(os.path.dirname(f"{d}/repo/{p}"), exist_ok=True)
            pathlib.Path(f"{d}/repo/{p}").write_text(text)
        tick_run(d)
        tick_run(d)
        return tick_run(d, "closable", "a").stdout

    def test_prose_comment_or_non_command_is_not_a_caller(self):
        for f in ({"notes.md": "run python3 fitness_tick.py\n"}, {"loop.md": "run fitness_tick.py each tick\n"},
                  {"loop.md": "each tick: python3 fitness_tick.py\n"}, {"routines/r.md": "see fitness_tick.py\n"},
                  {"loop.sh": "# python3 fitness_tick.py\n"}, {"settings.json": '{"note": "see fitness_tick.py"}\n'}):
            self.assertIn("nothing calls fitness_tick.py", self.closable(f), f)

    def test_hook_ci_loop_script_make_package_are_callers(self):
        for f in ({"settings.json": '{"command": "python3 fitness_tick.py"}\n'},
                  {".github/workflows/ci.yml": "      - run: python3 fitness_tick.py\n"},
                  {"loop.md": "- python3 fitness_tick.py\n"}, {"routines/r.md": "$ bash x/fitness_tick.py\n"},
                  {"loop.sh": "python3 fitness_tick.py\n"}, {"Makefile": "tick:\n\tpython3 fitness_tick.py\n"},
                  {"package.json": '{"scripts": {"tick": "python3 fitness_tick.py"}}\n'}):
            self.assertEqual(self.closable(f), "CLOSABLE a\n", f)

    def test_default_root_dot_keeps_dot_github(self):
        d = tempfile.mkdtemp()
        for p, text in {"fit/a": "#!/bin/sh\nexit 0\n", "repo/.github/workflows/ci.yml": "      - run: python3 fitness_tick.py\n"}.items():
            os.makedirs(os.path.dirname(f"{d}/{p}"), exist_ok=True)
            pathlib.Path(f"{d}/{p}").write_text(text)
        os.chmod(f"{d}/fit/a", 0o755)
        tick_run(d)
        tick_run(d)
        r = subprocess.run([sys.executable, str(SK / "scripts/fitness_tick.py"), "--dir", f"{d}/fit", "--state", f"{d}/st.json",
                            "closable", "a"], cwd=f"{d}/repo", capture_output=True, text=True)
        self.assertEqual(r.stdout, "CLOSABLE a\n")


class BaselineDefaults(unittest.TestCase):
    def test_normal_check_on_by_default_and_force_overrides(self):
        d = tempfile.mkdtemp()
        pathlib.Path(d, "f").write_text("".join(f"real_{i}\n" for i in range(20)))
        base = [sys.executable, str(SK / "scripts/baseline_guard.py"), "--fails", f"{d}/f", "--rerun", "false", "--out", f"{d}/o.json"]
        env = {**os.environ, "PERUN_GATE_CORES": "100000"}
        r = subprocess.run(base, capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, os.path.exists(f"{d}/o.json")), (1, False))
        self.assertIn("REFUSE baseline: 20 failures", r.stdout)
        self.assertEqual(subprocess.run(base + ["--force"], capture_output=True, env=env).returncode, 0)

    def test_load_check_on_by_default(self):
        bg = load("baseline_guard")
        d = tempfile.mkdtemp()
        pathlib.Path(d, "f").write_text("real_a\n")
        with mock.patch.object(os, "getloadavg", return_value=(500.0, 0, 0)), mock.patch("sys.stdout", io.StringIO()) as out:
            rc = bg.main(["--fails", f"{d}/f", "--rerun", "false", "--out", f"{d}/o.json"])
        self.assertEqual((rc, os.path.exists(f"{d}/o.json")), (1, False))
        self.assertIn("above --max-load", out.getvalue())


class WiredAllowNarrow(unittest.TestCase):
    def test_incidental_words_still_wire(self):
        out = wired({"scripts/tool.sh": "echo hi\n",
                     "scripts/unused-vars-check.sh": "bash scripts/tool.sh  # run: unreferenced orphan handling\n"})
        self.assertNotIn("scripts/tool.sh has no caller", out)

    def test_bare_orphan_marker_and_allowlist_key_still_exempt(self):
        for line in ("bash scripts/tool.sh  # orphan: kept for later\n", "allowlist: tool.sh\n"):
            self.assertIn("merged-not-wired", wired({"scripts/tool.sh": "echo hi\n", "scripts/c.sh": line}), line)

    def test_explicit_allowlist_name_still_blocks(self):
        self.assertIn("merged-not-wired", wired({"scripts/tool.sh": "echo hi\n", "scripts/c.sh": 'UNUSED_ALLOWLIST="tool.sh"\n'}))


class FreezeHook(unittest.TestCase):
    def hook(self, cmd, frozen=True, raw=None, repo=True, path=None):
        d = tempfile.mkdtemp()
        if repo:
            subprocess.run(["git", "-C", d, "init", "-q"], check=True)
        if frozen:
            pathlib.Path(d, ".perun-freeze").write_text("release stabilisation\n")
        inp = raw if raw is not None else json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        env = {k: v for k, v in os.environ.items() if k != "PERUN_FREEZE"}
        if path is not None:
            env["PATH"] = path
        return subprocess.run([sys.executable, str(SK / "scripts/freeze_hook.py")], input=inp, cwd=d, capture_output=True, text=True, env=env)

    def test_blocks_push_and_merge_while_frozen(self):
        for c in ("git push origin feat", "git -C /x push", "cd r && git push -u", "gh pr merge 5 --squash",
                  "gh -R o/r pr merge 5", "gh --repo x pr merge 5", "gh api -X PUT repos/o/r/pulls/5/merge",
                  "FOO=1 env git -c a=b push", "bash -c 'git push'", "gh --hostname h pr merge 1"):
            r = self.hook(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("FROZEN: release stabilisation", r.stderr)

    def test_allows_other_commands_and_unfrozen(self):
        for c in ("git status && gh pr view 5", "git log --grep push", "echo git push", "gh -R o/r pr view 5"):
            self.assertEqual(self.hook(c).returncode, 0, c)
        self.assertEqual(self.hook("git push origin feat", frozen=False).returncode, 0)

    def test_fails_closed_on_malformed_input_while_frozen(self):
        for raw in ("not json", "[]", "{}", '{"tool_input": {}}', '{"tool_input": {"command": 5}}',
                    '{"tool_input": {"command": "git push \'x"}}'):
            self.assertEqual(self.hook("", raw=raw).returncode, 2, raw)

    def test_non_repo_without_freeze_allows(self):
        self.assertEqual(self.hook("git push", frozen=False, repo=False).returncode, 0)
        self.assertEqual(self.hook("", raw="not json", frozen=False, repo=False).returncode, 0)

    def test_missing_git_denies(self):
        self.assertEqual(self.hook("git push", frozen=False, path="/nonexistent").returncode, 2)

    def test_wired_in_template_and_doctor(self):
        t = json.load(open(SK / "templates/operating-layer.settings.json"))
        cmds = [h["command"] for e in t["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertTrue(any("freeze_hook.py" in c for c in cmds))
        self.assertIn("freeze_hook.py", (ROOT / "scripts/perun_doctor.py").read_text())


class CanonicalReference(unittest.TestCase):
    def test_doctrine_lives_once_and_is_routed(self):
        refs = SK / "references"
        self.assertIn("references/flow-guards.md", (refs / "full-map.md").read_text())
        for f in ("unattended-operating-mode.md", "red-gate-triage.md"):
            t = (refs / f).read_text()
            self.assertIn("references/flow-guards.md", t)
            self.assertNotIn("fitness_tick.py", t)
            self.assertNotIn("flow_alarm.py", t)
        home = (refs / "flow-guards.md").read_text()
        for name in ("finding_guard.py", "fitness_tick.py", "flow_alarm.py", "freeze_hook.py"):
            self.assertIn(name, home)


if __name__ == "__main__":
    unittest.main()
