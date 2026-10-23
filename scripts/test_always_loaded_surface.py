#!/usr/bin/env python3
"""Completeness tripwire for scripts/always_loaded_bytes.py: every always-on source of a plugin install is either
measured there or proven silent here. Fails when a new agent, plugin hook or SessionStart/UserPromptSubmit hook
appears without being measured. Offline; runs three hooks in a temp dir with a throwaway HOME."""
import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts")
TEMPLATE = os.path.join(ROOT, ".claude/skills/agentic-delivery/templates/operating-layer.settings.json")
sys.path.insert(0, HERE)
import always_loaded_bytes as alb  # noqa: E402

# Silent in a clean session (print only when their condition fires): run below. Network hooks: not run.
SILENT_RUN = ("context_nudge.py", "ceo_altitude_guard.py", "outcome_claim_guard.py")
SILENT_NETWORK = ("landing_watchdog.py", "perun_auto_update.py")


def script_name(command):
    """Basename of the script a hook command runs: first arg after the interpreter, past leading VAR=value words."""
    words = shlex.split(command)
    while words and re.match(r"[A-Za-z_]\w*=", words[0]):
        words.pop(0)
    return os.path.basename(words[1])


def hook_names(event, template=TEMPLATE):
    with open(template, encoding="utf-8") as f:
        groups = json.load(f)["hooks"][event]
    return {script_name(h["command"]) for g in groups for h in g["hooks"]}


def default_path_sources(root):
    """Files a plugin install auto-loads from default paths even when plugin.json does not name them."""
    found = ("agents", ".claude/agents", "hooks/hooks.json", ".mcp.json")
    return [p for p in found if os.path.exists(os.path.join(root, p))]


def stdout_writers(source):
    """Names of the functions (or <module>) in `source` that call print() or touch sys.stdout."""
    found = set()

    def walk(node, owner):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print") or (
                isinstance(node, ast.Attribute) and node.attr == "stdout" and getattr(node.value, "id", "") == "sys"):
            found.add(owner)
        for child in ast.iter_child_nodes(node):
            walk(child, owner)

    walk(ast.parse(source), "<module>")
    return found


def read_script(name):
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as f:
        return f.read()


class AlwaysLoadedSurface(unittest.TestCase):
    def test_plugin_install_adds_only_skills_and_commands(self):
        with open(os.path.join(ROOT, ".claude-plugin/plugin.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual({"agents", "hooks", "commands", "mcpServers"} & set(manifest), set())
        self.assertEqual(default_path_sources(ROOT), [])

    def test_default_path_sources_detects_auto_loaded_files(self):
        with tempfile.TemporaryDirectory(prefix="always-loaded-root-") as tmp:
            os.makedirs(os.path.join(tmp, "hooks"))
            for rel in ("hooks/hooks.json", ".mcp.json"):
                open(os.path.join(tmp, rel), "w").close()
            self.assertEqual(default_path_sources(tmp), ["hooks/hooks.json", ".mcp.json"])

    def test_script_name_handles_env_prefixed_and_unquoted_commands(self):
        cases = {
            'HOUSE_DEFAULTS_FILE="$D/house-defaults.md" python3 "$D/s/subagent_start_inject.py"': "subagent_start_inject.py",
            "python3 $D/s/plain.py || true": "plain.py",
            'python3 "$D/s/quoted.py" || true': "quoted.py",
        }
        for cmd, want in cases.items():
            self.assertEqual(script_name(cmd), want, cmd)
        self.assertIn("subagent_start_inject.py", hook_names("SubagentStart"))

    def test_every_session_start_hook_is_measured_or_silent(self):
        known = set(alb.HOOKS) | {"perun_auto_update.py"}  # auto-update prints nothing
        self.assertEqual(hook_names("SessionStart") - known, set())

    def test_stdout_writers_finds_print_and_sys_stdout(self):
        src = "print('x')\ndef a():\n    print('y')\ndef b():\n    sys.stdout.write('z')\ndef c():\n    return 1\n"
        self.assertEqual(stdout_writers(src), {"<module>", "a", "b"})

    def test_network_hooks_print_nothing_on_session_start(self):
        self.assertEqual(stdout_writers(read_script("perun_auto_update.py")), set())  # SessionStart hook, any path
        lw = read_script("landing_watchdog.py")
        self.assertEqual(stdout_writers(lw), {"check", "main"})  # check() is the CLI; main() prints only a hook line
        self.assertIn("not _event(data)", lw)  # _line returns None unless the event is answerable ...
        self.assertNotIn("SessionStart", lw)  # ... and SessionStart never is
        self.assertNotIn("landing_watchdog.py", hook_names("SessionStart"))

    def test_every_user_prompt_hook_is_proven_silent(self):
        self.assertEqual(hook_names("UserPromptSubmit") - set(SILENT_RUN) - set(SILENT_NETWORK), set())
        payload = json.dumps({"prompt": "list the files", "session_id": "s"})
        with tempfile.TemporaryDirectory(prefix="always-loaded-ups-") as tmp:
            env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "CLAUDE_PROJECT_DIR": tmp, "XDG_CACHE_HOME": tmp}
            for h in SILENT_RUN:
                r = subprocess.run([sys.executable, os.path.join(SCRIPTS, h)], cwd=tmp, env=env, input=payload,
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, ""), f"{h} injects text in a clean session")


if __name__ == "__main__":
    unittest.main()
