#!/usr/bin/env python3
"""Tests for ceo_altitude_guard.py: main session vs subagent, allowed vs flagged tools, warn vs strict, the owner
override, the per-session counters (selfcheck), policy `role`, and the operating-layer wiring (install, then run the
hook exactly as wired).

Most cases call `handle()` in-process (fast, table-driven); `Contract` and `Wiring` run the script as a subprocess so
the host contract (JSON on stdin, JSON on stdout, exit 0, silent UserPromptSubmit) is what is tested. Fixture paths are
fictional (/work/acme-app); the real cache dir and the real policy file are never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
GUARD = SC / "ceo_altitude_guard.py"
TEMPLATE = ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json"
sys.path.insert(0, str(SC))
sys.path.insert(0, str(ROOT / "scripts"))
import ceo_altitude_guard as cag  # noqa: E402
import heavy_gate  # noqa: E402
import operating_selfcheck as selfcheck  # noqa: E402
import perun_doctor  # noqa: E402
import perun_policy as pp  # noqa: E402

PROJ = "/work/acme-app"  # a fictional project dir; never under a temp dir
DELEGATE = "delegate: spawn a lane with the brief"


def edit(path, tool="Edit", **extra):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: path}, "cwd": PROJ, **extra}


def bash(cmd, **extra):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": PROJ, **extra}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ceo-alt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = self.tmp / "state"
        self.policy = self.tmp / "policy.json"
        self.policy.write_text("{}")
        patch = mock.patch.dict(os.environ, {"PERUN_CEO_DIR": str(self.state), "PERUN_POLICY": str(self.policy),
                                             "CLAUDE_PROJECT_DIR": PROJ})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("PERUN_ROLE", None)
        os.environ.pop("PERUN_HEAVY_PATTERNS", None)
        self.session, self.prompt = "sess-1", "p1"

    def data(self, payload, event="PreToolUse"):
        return {"session_id": self.session, "prompt_id": self.prompt, "hook_event_name": event, **payload}

    def hook(self, payload, role=None, env=None):
        """The guard's decision for one PreToolUse call (in-process): the hookSpecificOutput dict, or None for silence."""
        over = {**(env or {}), **({"PERUN_ROLE": role} if role is not None else {})}
        with mock.patch.dict(os.environ, over):
            return cag.handle(self.data(payload))

    def prompt_submit(self, text, role=None):
        with mock.patch.dict(os.environ, {"PERUN_ROLE": role} if role else {}):
            self.assertIsNone(cag.handle(self.data({"prompt": text}, "UserPromptSubmit")))

    def run_hook(self, payload=None, role=None, env=None, raw=None):
        """The script as the host runs it (subprocess): (returncode, stdout)."""
        e = {**os.environ, **(env or {}), **({"PERUN_ROLE": role} if role is not None else {})}
        p = subprocess.run([sys.executable, str(GUARD)], input=raw if raw is not None else json.dumps(self.data(payload)),
                           capture_output=True, text=True, env=e)
        return p.returncode, p.stdout

    def counters(self, session=None):
        f = self.state / f"{session or self.session}.json"
        return json.loads(f.read_text()) if f.exists() else None


class MainVsSubagent(Base):
    def test_subagent_is_never_counted_flagged_or_blocked(self):
        lane = {"agent_id": "agent-abc123", "agent_type": "delivery-lane"}
        for i in range(4):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py", **lane), "ceo-strict"))
        for _ in range(6):
            self.assertIsNone(self.hook(bash("pytest -q", **lane), "ceo-strict"))
        self.assertFalse(self.state.exists(), "a lane's calls must leave no counter file")

    def test_same_calls_from_the_main_session_are_blocked(self):
        self.assertEqual(self.hook(edit(f"{PROJ}/src/f1.py"), "ceo-strict")["permissionDecision"], "deny")

    def test_agent_type_alone_is_still_the_main_session(self):
        # a main session started with `--agent <name>` carries agent_type but no agent_id (hooks reference, 2026-10-16)
        main_as_agent = {"agent_type": "ceo-conductor"}
        self.assertEqual(self.hook(edit(f"{PROJ}/src/f1.py", **main_as_agent), "ceo-strict")["permissionDecision"], "deny")

    def test_in_process_teammate_has_an_agent_id_and_is_a_lane(self):
        for i in range(3):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py", agent_id="teammate-1"), "ceo-strict"))

    def test_empty_agent_id_is_the_main_session(self):
        self.hook(edit(f"{PROJ}/src/f0.py", agent_id=""), "ceo-strict")
        self.assertEqual(self.hook(edit(f"{PROJ}/src/f1.py", agent_id=""), "ceo-strict")["permissionDecision"], "deny")

    def test_per_process_marker_for_a_top_level_lane(self):
        # a separate top-level lane process (claude -p worker, peer session) has no agent_id: PERUN_ROLE=off is its marker
        self.policy.write_text('{"role": "ceo-strict"}')
        for i in range(3):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py"), env={"PERUN_ROLE": "off"}))


class Modes(Base):
    def test_default_role_is_off_but_counts(self):
        for i in range(3):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py")))
        c = self.counters()
        self.assertEqual((c["edits"], c["warned"], c["blocked"]), (3, 0, 0))

    def test_first_direct_edit_in_a_turn_is_free_in_off_and_warn_only(self):
        for role in ("off", "ceo"):
            self.session = f"free-{role}"
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/a.py"), role), role)

    def test_warn_lets_the_call_run_and_names_the_delegation(self):
        self.policy.write_text('{"role": "ceo"}')
        self.hook(edit(f"{PROJ}/src/a.py"))
        out = self.hook(edit(f"{PROJ}/src/b.py"))
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", out)
        self.assertTrue(out["additionalContext"].startswith(DELEGATE), out)
        self.assertIn("b.py", out["additionalContext"])
        self.assertIn("direct source edit #2", out["additionalContext"])
        c = self.counters()
        self.assertEqual((c["edits"], c["warned"], c["blocked"]), (2, 1, 0))

    def test_strict_blocks_every_in_repo_edit_with_zero_free(self):
        self.policy.write_text('{"role": "ceo strict"}')  # the spaced spelling is the same role
        for name in ("a.py", "b.py"):
            out = self.hook(edit(f"{PROJ}/src/{name}"))
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertTrue(out["permissionDecisionReason"].startswith("BLOCKED (role=ceo-strict): " + DELEGATE))
            self.assertIn("direct source edit #1", out["permissionDecisionReason"])  # still #1: blocked calls did not happen
            self.assertIn("free: 0", out["permissionDecisionReason"])
            self.assertIn("ceo:off", out["permissionDecisionReason"])
        c = self.counters()
        self.assertEqual((c["edits"], c["warned"], c["blocked"]), (0, 0, 2))

    def test_strict_counts_non_code_in_repo_files_but_not_outside_the_repo(self):
        for name, payload in ALLOWED:
            if name in ("changelog", "changelog fragment", "handoff", "roadmap", "task ledger", "policy json", "config", "workflow"):
                self.assertEqual(self.hook(payload, "ceo-strict")["permissionDecision"], "deny", name)
        for name in ("memory", "scratchpad script", "Read", "git"):
            self.assertIsNone(self.hook(dict(ALLOWED)[name], "ceo-strict"), name)
        self.assertEqual(self.hook(bash("echo hi > out.txt"), "ceo-strict")["permissionDecision"], "deny")
        self.assertIsNone(self.hook(bash("echo hi > /dev/null"), "ceo-strict"))
        self.assertIsNone(self.hook(edit(f"{PROJ}/x.md"), "off"), "PERUN_ROLE=off is the escape")

    def test_strict_sed_script_arg_is_not_a_target(self):
        self.assertIsNone(self.hook(bash("sed -i 's/a/b/' /tmp/zz.txt"), "ceo-strict"))
        self.assertIsNone(self.hook(bash("sed -i -e 's/a/b/' /tmp/zz.txt"), "ceo-strict"))
        self.assertIsNone(self.hook(bash("perl -pi -e 's/a/b/' /tmp/zz.txt"), "ceo-strict"))
        self.assertEqual(self.hook(bash("sed -i 's/a/b/' README.md"), "ceo-strict")["permissionDecision"], "deny")
        self.assertEqual(self.hook(bash("sed -i -e 's/a/b/' README.md"), "ceo-strict")["permissionDecision"], "deny")

    def test_strict_expands_home_and_env_and_fails_open_on_unresolved(self):
        env = {"TMPDIR": "/work/scratch", "HOME": "/home/jane"}
        self.assertIsNone(self.hook(bash("echo x > $TMPDIR/a.txt"), "ceo-strict", env=env))
        self.assertIsNone(self.hook(bash("echo x > ~/m.md"), "ceo-strict", env=env))
        self.assertIsNone(self.hook(bash("echo x > $NOPE_UNSET/a.md"), "ceo-strict"))
        self.assertEqual(self.hook(bash("echo x > $CLAUDE_PROJECT_DIR/a.md"), "ceo-strict")["permissionDecision"], "deny")

    def test_strict_root_falls_back_to_git_toplevel_and_resolves_symlinks(self):
        repo, out = self.tmp / "repo", self.tmp / "outside"
        (repo / "sub").mkdir(parents=True)
        out.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "link").symlink_to(out)  # in-project link out of the project
        (out / "back").symlink_to(repo)  # outside link into the project
        os.environ.pop("CLAUDE_PROJECT_DIR")
        sub = {"cwd": str(repo / "sub")}
        self.assertEqual(self.hook(edit("../x.md", **sub), "ceo-strict")["permissionDecision"], "deny")
        self.assertIsNone(self.hook(edit(str(repo / "link/x.md"), **sub), "ceo-strict"))
        self.assertEqual(self.hook(edit(str(out / "back/x.md"), **sub), "ceo-strict")["permissionDecision"], "deny")

    def test_warn_role_keeps_one_free_edit_and_ignores_non_code(self):
        self.assertIsNone(self.hook(edit(f"{PROJ}/a.py"), "ceo"))
        self.assertIsNone(self.hook(edit(f"{PROJ}/docs/x.md"), "ceo"))

    def test_env_role_beats_the_policy_file_both_ways(self):
        self.policy.write_text('{"role": "ceo-strict"}')
        for i in range(2):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py"), "off"))
        self.session = "other"
        self.policy.write_text("{}")
        self.hook(edit(f"{PROJ}/src/a.py"), "ceo")
        self.assertIn(DELEGATE, self.hook(edit(f"{PROJ}/src/b.py"), "ceo")["additionalContext"])

    def test_empty_env_role_defers_to_the_policy(self):
        self.policy.write_text('{"role": "ceo-strict"}')
        self.hook(edit(f"{PROJ}/src/a.py"), "")
        self.assertEqual(self.hook(edit(f"{PROJ}/src/b.py"), "")["permissionDecision"], "deny")

    def test_unknown_role_and_bad_policy_fail_open(self):
        for i in range(3):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py"), "boss"))
        for bad, session in (('{"role": "boss"}', "bad-value"), ("{not json", "bad-json"), ('{"nope": 1}', "bad-key")):
            self.policy.write_text(bad)
            self.session = session
            for i in range(3):
                self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py")), bad)


ALLOWED = [  # none of these is ever flagged, however many a turn holds
    ("Read", {"tool_name": "Read", "tool_input": {"file_path": f"{PROJ}/src/a.py"}}),
    ("Grep", {"tool_name": "Grep", "tool_input": {"pattern": "x", "path": PROJ}}),
    ("WebFetch", {"tool_name": "WebFetch", "tool_input": {"url": "https://example.com"}}),
    ("Linear MCP", {"tool_name": "mcp__claude_ai_Linear__save_issue", "tool_input": {"title": "x"}}),
    ("spawn a lane", {"tool_name": "Agent", "tool_input": {"description": "do it", "prompt": "brief"}}),
    ("git", bash("git status")),
    ("git commit mentioning a file", bash('git commit -m "move helper -> foo.py"')),
    ("gh merge", bash("gh pr merge 12 --squash")),
    ("release", bash("bash scripts/land-release.sh")),
    ("set policy", bash("python3 .claude/skills/agentic-delivery/scripts/perun_policy.py set role ceo")),
    ("redirect to a log", bash("echo hi > out.txt")),
    ("read a source file with sed", bash("sed -n 1,5p src/a.py")),
    ("grep a source file", bash("grep -n x src/a.py")),
    ("test --version", bash("pytest --version")),
    ("changelog", edit(f"{PROJ}/CHANGELOG.md")),
    ("changelog fragment", edit(f"{PROJ}/changelog.d/feat-x.md", "Write")),
    ("handoff", edit(f"{PROJ}/.claude/handoff.md", "Write")),
    ("roadmap", edit(f"{PROJ}/docs/roadmap.md")),
    ("memory", edit("/home/jane/.claude/projects/acme/memory/MEMORY.md")),
    ("task ledger", edit(f"{PROJ}/.claude/TASKS.md")),
    ("policy json", edit(f"{PROJ}/.perun/policy.json", "Write")),
    ("config", edit(f"{PROJ}/package.json")),
    ("workflow", edit(f"{PROJ}/.github/workflows/ci.yml")),
    ("scratchpad script", edit("/work/scratch/probe.py", "Write", scratchpad_dir="/work/scratch")),
]

FLAGGED = [
    ("Edit py", edit(f"{PROJ}/src/a.py")),
    ("Edit test", edit(f"{PROJ}/tests/test_a.py")),
    ("Write ts", edit(f"{PROJ}/src/x.ts", "Write")),
    ("MultiEdit go", edit(f"{PROJ}/lib/y.go", "MultiEdit")),
    ("NotebookEdit", edit(f"{PROJ}/n.ipynb", "NotebookEdit")),
    ("heredoc write", bash("cat > src/a.py <<'EOF'\nprint(1)\nEOF")),
    ("redirect append", bash("echo x >> src/a.sh")),
    ("tee", bash("printf x | tee src/a.js")),
    ("sudo tee", bash("printf x | sudo tee src/a.c")),
    ("sed -i", bash("sed -i 's/a/b/' src/a.py")),
    ("sed -i with empty suffix", bash("sed -i '' 's/a/b/' src/a.py")),
    ("sed -i.bak", bash("sed -i.bak 's/a/b/' src/a.py")),
    ("perl -pi", bash("perl -pi -e 's/a/b/' src/a.rb")),
]


class AllowedVsFlagged(Base):
    def spend_free_edit(self):
        self.assertIsNone(self.hook(edit(f"{PROJ}/src/free.py"), "ceo"))  # strict has no free edit: spend it under warn

    def test_allowed_tools_are_never_flagged_even_after_the_free_edit(self):
        self.spend_free_edit()
        for name, payload in ALLOWED:
            for _ in range(5):
                self.assertIsNone(self.hook(payload, "ceo"), name)
        c = self.counters()
        self.assertEqual((c["edits"], c["heavy"], c["blocked"]), (1, 0, 0), "allowed calls must not count as direct work")

    def test_temp_dir_file_is_scratch_but_a_project_inside_a_temp_dir_is_not(self):
        self.spend_free_edit()
        self.assertIsNone(self.hook(edit(str(self.tmp / "probe.py"), "Write"), "ceo-strict"))
        repo = self.tmp / "repo"
        self.session = "tmp-project"
        env = {"CLAUDE_PROJECT_DIR": str(repo)}
        self.assertIsNone(self.hook(edit(str(repo / "a.py"), cwd=str(repo)), "ceo", env=env))
        self.assertEqual(self.hook(edit(str(repo / "b.py"), cwd=str(repo)), "ceo-strict", env=env)["permissionDecision"], "deny")

    def test_relative_paths_resolve_against_the_session_cwd(self):
        self.spend_free_edit()
        self.assertEqual(self.hook(edit("src/a.py"), "ceo-strict")["permissionDecision"], "deny")

    def test_direct_source_writes_are_flagged_as_the_second_edit(self):
        for i, (name, payload) in enumerate(FLAGGED):
            self.session = f"second{i}"
            self.spend_free_edit()
            out = self.hook(payload, "ceo-strict")
            self.assertEqual(out and out["permissionDecision"], "deny", name)
            self.assertEqual(self.counters()["blocked"], 1, name)

    def test_a_flagged_write_counts_as_a_direct_edit_even_as_the_first_one(self):
        for i, (name, payload) in enumerate(FLAGGED):
            self.session = f"first{i}"
            self.assertIsNone(self.hook(payload, "ceo"), name)
            self.assertEqual(self.counters()["edits"], 1, name)

    def test_build_and_test_commands_flag_on_the_fourth_in_a_turn(self):
        for i, cmd in enumerate(("pytest -q", "cd src && npm test", "cargo test", "go test ./...")):
            self.session = f"heavy{i}"
            for _ in range(3):
                self.assertIsNone(self.hook(bash(cmd), "ceo-strict"), cmd)
            out = self.hook(bash(cmd), "ceo-strict")
            self.assertEqual(out["permissionDecision"], "deny", cmd)
            self.assertIn("build/test command #4", out["permissionDecisionReason"])
            c = self.counters()
            self.assertEqual((c["heavy"], c["blocked"], c["edits"]), (3, 1, 0), cmd)

    def test_heavy_warn_runs_the_command_and_names_a_gate_to_delegate_with(self):
        for _ in range(3):
            self.assertIsNone(self.hook(bash("pytest"), "ceo"))
        out = self.hook(bash("pytest"), "ceo")
        self.assertTrue(out["additionalContext"].startswith(DELEGATE))
        self.assertIn("DONE-gate", out["additionalContext"])
        self.assertNotIn("permissionDecision", out)
        self.assertEqual((self.counters()["heavy"], self.counters()["warned"]), (4, 1))

    def test_heavy_and_edit_allowances_are_separate(self):
        for _ in range(3):
            self.assertIsNone(self.hook(bash("pytest"), "ceo-strict"))
        self.assertIsNone(self.hook(edit(f"{PROJ}/src/a.py"), "ceo"))

    def test_custom_heavy_patterns_are_honoured(self):
        with mock.patch.dict(os.environ, {"PERUN_HEAVY_PATTERNS": "make check\\b"}):
            for _ in range(3):
                self.assertIsNone(self.hook(bash("make check"), "ceo-strict"))
            self.assertEqual(self.hook(bash("make check"), "ceo-strict")["permissionDecision"], "deny")
            self.assertIsNone(self.hook(bash("pytest"), "ceo-strict"), "a pattern list replaces the defaults")


class TurnsAndOverride(Base):
    def test_a_new_prompt_id_is_a_new_turn(self):
        self.assertIsNotNone(self.hook(edit(f"{PROJ}/src/a.py"), "ceo-strict"))
        self.prompt = "p2"
        self.assertIsNotNone(self.hook(edit(f"{PROJ}/src/c.py"), "ceo-strict"))
        self.assertIsNone(self.hook(edit(f"{PROJ}/src/d.py"), "ceo"), "a new turn restores warn's free edit")

    def test_user_prompt_submit_also_resets_the_turn(self):
        self.hook(edit(f"{PROJ}/src/a.py"), "ceo")
        self.assertIsNotNone(self.hook(edit(f"{PROJ}/src/b.py"), "ceo"))
        self.prompt_submit("carry on", "ceo")  # same prompt_id, no override token
        self.assertIsNone(self.hook(edit(f"{PROJ}/src/c.py"), "ceo"))

    def test_without_a_prompt_id_only_user_prompt_submit_resets_the_turn(self):
        self.prompt = None
        self.hook(edit(f"{PROJ}/src/a.py"), "ceo")
        self.assertIsNotNone(self.hook(edit(f"{PROJ}/src/b.py"), "ceo"))
        self.prompt_submit("next", "ceo")
        self.assertIsNone(self.hook(edit(f"{PROJ}/src/c.py"), "ceo"))

    def test_owner_override_lifts_the_flags_until_the_next_prompt(self):
        self.prompt_submit("ceo:off fix the typo in parser.py yourself", "ceo-strict")
        for i in range(4):
            self.assertIsNone(self.hook(edit(f"{PROJ}/src/f{i}.py"), "ceo-strict"))
        for _ in range(5):
            self.assertIsNone(self.hook(bash("pytest"), "ceo-strict"))
        self.assertEqual(self.counters()["edits"], 4, "overridden edits are still counted")
        self.prompt = "p2"
        self.prompt_submit("thanks, now back to normal", "ceo-strict")
        self.hook(edit(f"{PROJ}/src/g0.py"), "ceo-strict")
        self.assertIsNotNone(self.hook(edit(f"{PROJ}/src/g1.py"), "ceo-strict"))

    def test_override_spellings(self):
        for i, text in enumerate(("ceo:off", "CEO: off please", "ceo off", "ceo-off")):
            self.session = f"yes{i}"
            self.prompt_submit(text, "ceo-strict")
            self.assertTrue(self.counters()["override"], text)
        for i, text in enumerate(("the ceo offered a plan", "ceo on", "turn off the ceo guard", "")):
            self.session = f"no{i}"
            self.prompt_submit(text, "ceo-strict")
            self.assertFalse(self.counters()["override"], text)

    def test_a_lane_prompt_event_is_ignored(self):
        self.assertIsNone(cag.handle(self.data({"prompt": "ceo:off", "agent_id": "a1"}, "UserPromptSubmit")))
        self.assertFalse(self.state.exists())


class Contract(Base):
    """The script as a subprocess: what the host actually reads."""

    def test_warn_prints_additional_context_json_and_exits_0(self):
        self.policy.write_text('{"role": "ceo"}')
        self.assertEqual(self.run_hook(edit(f"{PROJ}/src/a.py")), (0, ""))
        rc, out = self.run_hook(edit(f"{PROJ}/src/b.py"))
        hso = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(rc, 0)
        self.assertEqual(set(hso), {"hookEventName", "additionalContext"})
        self.assertEqual(hso["hookEventName"], "PreToolUse")

    def test_strict_prints_a_deny_decision_and_still_exits_0(self):
        rc, out = self.run_hook(edit(f"{PROJ}/src/b.py"), "ceo-strict")
        hso = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(rc, 0, "a block is a JSON decision, never exit 2")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertEqual(set(hso), {"hookEventName", "permissionDecision", "permissionDecisionReason"})

    def test_subagent_call_is_silent_and_exits_0(self):
        for _ in range(3):
            self.assertEqual(self.run_hook(edit(f"{PROJ}/src/a.py", agent_id="a1", agent_type="builder"), "ceo-strict"), (0, ""))

    def test_user_prompt_submit_never_prints(self):
        # stdout of a UserPromptSubmit hook is added to the model's context
        for text in ("hello", "ceo:off", "x" * 5000):
            self.assertEqual(self.run_hook({"hook_event_name": "UserPromptSubmit", "prompt": text}, "ceo-strict"), (0, ""))

    def test_garbage_and_non_object_stdin_exit_0_silently(self):
        for raw in ("", "not json", "[]", "null", '"x"', "{"):
            self.assertEqual(self.run_hook(role="ceo-strict", raw=raw), (0, ""), raw)

    def test_unwritable_state_dir_fails_open_even_in_strict(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        for i in range(3):
            self.assertEqual(self.run_hook(edit(f"{PROJ}/src/f{i}.py"), "ceo-strict", env={"PERUN_CEO_DIR": str(blocker / "sub")}), (0, ""))

    def test_default_state_dir_is_under_the_cache_dir(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.tmp / "cache")}):
            os.environ.pop("PERUN_CEO_DIR")
            self.assertEqual(self.run_hook(edit(f"{PROJ}/src/a.py"), "off"), (0, ""))
        self.assertTrue((self.tmp / "cache/perun/ceo-altitude/sess-1.json").is_file())
        self.assertFalse(self.state.exists())

    def test_relative_cache_dir_fails_open_without_littering_the_project(self):
        env = {k: v for k, v in os.environ.items() if k != "PERUN_CEO_DIR"} | {"XDG_CACHE_HOME": "rel-cache", "PERUN_ROLE": "ceo-strict"}
        for i in range(2):
            p = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(self.data(edit(f"{PROJ}/src/f{i}.py"))),
                               capture_output=True, text=True, env=env, cwd=self.tmp)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertEqual(os.listdir(self.tmp).count("rel-cache"), 0)

    def test_torn_state_file_starts_over(self):
        self.state.mkdir()
        (self.state / "sess-1.json").write_text('{"edits": 4, "tur')
        self.assertEqual(self.run_hook(edit(f"{PROJ}/src/a.py"), "ceo"), (0, ""))
        self.assertEqual(self.counters()["edits"], 1)

    def test_parallel_tool_calls_count_exactly(self):
        payload = json.dumps(self.data(edit(f"{PROJ}/src/a.py")))
        procs = [subprocess.Popen([sys.executable, str(GUARD)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  env={**os.environ, "PERUN_ROLE": "off"}) for _ in range(12)]
        for p in procs:  # feed them all before waiting on any, so the 12 hooks overlap
            p.stdin.write(payload)
            p.stdin.close()
        for p in procs:
            self.assertEqual(p.wait(), 0)
            p.stdout.close()
        self.assertEqual(self.counters()["edits"], 12)

    def test_old_session_files_are_pruned_when_a_session_starts(self):
        self.state.mkdir()
        old, fresh = self.state / "old.json", self.state / "fresh.json"
        for f in (old, fresh):
            f.write_text("{}")
        os.utime(old, (time.time() - 31 * 86400,) * 2)
        self.hook(edit(f"{PROJ}/src/a.py"), "off")
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())


class Helpers(Base):
    def test_write_targets(self):
        t = cag.write_targets
        self.assertEqual(t("echo x > a.py"), ["a.py"])
        self.assertEqual(t("cat > a.py <<'EOF'\n> not.py\nEOF"), ["a.py"])  # a heredoc body is not a write
        self.assertEqual(t('git commit -m "a > b.py"'), [])  # quoted text is one token
        self.assertEqual(t("a 2>&1 | tee out.log"), ["out.log"])
        self.assertEqual(t("sed -n 1p a.py"), [])
        self.assertEqual(t("sed -i s/a/b/ a.py b.py"), ["a.py", "b.py"])  # the script is not a file
        self.assertEqual(t("echo 'unclosed > a.py"), [])  # unparsable: fail open

    def test_is_source(self):
        d = {"cwd": PROJ}
        for p in ("a.py", "src/a.TSX", "/work/acme-app/x/y.go", "n.ipynb", "run.sh"):
            self.assertTrue(cag.is_source(p, d), p)
        for p in ("", "README.md", "a.json", "Makefile", "notes.txt", "a.yaml", "a.py.bak"):
            self.assertFalse(cag.is_source(p, d), p)

    def test_classify_ignores_other_tools_and_missing_fields(self):
        for payload in ({}, {"tool_name": "Edit"}, {"tool_name": "Edit", "tool_input": {}}, {"tool_name": "Bash", "tool_input": None},
                        {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}):
            self.assertIsNone(cag.classify(payload), payload)

    def test_heavy_gate_helpers_the_guard_reuses(self):
        self.assertIn(">", heavy_gate.tokens("echo x > a.py"))
        self.assertEqual(heavy_gate.segments("a b; c | d"), [["a", "b"], ["c"], ["d"]])
        self.assertEqual(heavy_gate.strip_wrappers(["sudo", "tee", "a"]), ["tee", "a"])
        with mock.patch.dict(os.environ, {"PERUN_HEAVY_PATTERNS": "make check\\b\n\n"}):
            self.assertEqual(heavy_gate.heavy_patterns(), ["make check\\b"])
        self.assertIs(heavy_gate.heavy_patterns(), heavy_gate.DEFAULT_PATTERNS)

    def test_a_quoted_empty_argument_is_not_a_segment_break(self):
        # regression: set('') <= set(PUNCT) made `sed -i '' ...` split into two segments
        self.assertEqual(heavy_gate.segments("sed -i '' x.py"), [["sed", "-i", "", "x.py"]])
        self.assertTrue(heavy_gate.is_heavy("pytest -k '' tests", heavy_gate.DEFAULT_PATTERNS))


class PolicyRole(unittest.TestCase):
    def test_default_and_values(self):
        self.assertEqual(pp.validate({})["role"], "off")
        for v, want in (("off", "off"), ("ceo", "ceo"), ("ceo-strict", "ceo-strict"), ("ceo strict", "ceo-strict"),
                        ("  CEO   Strict ", "ceo-strict")):
            self.assertEqual(pp.validate({"role": v})["role"], want, v)

    def test_bad_values_fail_closed(self):
        for v in ("boss", "", "ceo-loose", True, 1, None, ["ceo"]):
            with self.assertRaises(ValueError, msg=repr(v)):
                pp.validate({"role": v})

    def test_cli_set_get_check(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "PERUN_POLICY": str(Path(d) / "p.json")}
            run = lambda *a: subprocess.run([sys.executable, str(SC / "perun_policy.py"), *a], capture_output=True, text=True, env=env)  # noqa: E731
            self.assertEqual(run("set", "role", "ceo strict").returncode, 0)
            self.assertEqual(run("get", "role").stdout.strip(), "ceo-strict")
            self.assertEqual(run("check", "role", "ceo").returncode, 0)
            self.assertEqual(run("check", "role", "boss").returncode, 2)
            self.assertEqual(run("get", "tokens").stdout.strip(), "efficient", "other dimensions are untouched")

    def test_existing_selftest_still_passes(self):
        r = subprocess.run([sys.executable, str(SC / "perun_policy.py"), "--selftest"], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if k != "PERUN_POLICY"})
        self.assertEqual(r.returncode, 0, r.stderr)


class SelfcheckCounter(Base):
    def test_report_lines_count_direct_edits_per_session_and_project(self):
        for sid, n in (("aaaaaaaa-1", 3), ("bbbbbbbb-2", 1)):
            self.session = sid
            for i in range(n):
                self.hook(edit(f"{PROJ}/src/f{i}.py"), "ceo")
        self.session = "cccccccc-3"  # another project's session: not reported here
        self.hook(edit("/work/other-app/a.py", cwd="/work/other-app"), "ceo", env={"CLAUDE_PROJECT_DIR": "/work/other-app"})
        lines = cag.report_lines(PROJ)
        self.assertTrue(lines[0].startswith("ceo-altitude: role="), lines)
        self.assertIn("2 main session(s) recorded, 4 direct source edit(s) in all", lines[0])
        text = "\n".join(lines[1:])
        self.assertIn("ceo-altitude-session aaaaaaaa: 3 direct source edit(s)", text)
        self.assertIn("warned 2", text)  # the 2nd and 3rd edit of a turn under role ceo
        self.assertIn("ceo-altitude-session bbbbbbbb: 1 direct source edit(s)", text)
        self.assertNotIn("cccccccc", text)
        self.assertFalse(any(line.startswith("WARN") for line in lines))

    def test_report_lines_with_nothing_recorded_shows_the_arm_hint(self):
        lines = cag.report_lines(PROJ)
        self.assertEqual(len(lines), 1)
        self.assertIn("role=off; 0 main session(s) recorded, 0 direct source edit(s) in all; arm it: perun_policy.py set role ceo", lines[0])
        self.policy.write_text('{"role": "ceo"}')
        self.assertNotIn("arm it", cag.report_lines(PROJ)[0])

    def test_report_lists_the_newest_sessions_first_and_caps_them(self):
        for i in range(7):
            self.session = f"s{i}"
            self.hook(edit(f"{PROJ}/src/a.py"), "off")
            f = self.state / f"s{i}.json"
            f.write_text(json.dumps({**json.loads(f.read_text()), "last": 1_800_000_000 + i}))
        lines = cag.report_lines(PROJ, limit=3)
        self.assertEqual([line.split(":")[0] for line in lines[1:]],
                         ["ceo-altitude-session s6", "ceo-altitude-session s5", "ceo-altitude-session s4"])

    def test_selfcheck_cli_prints_the_counter_and_the_wiring_item(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(proj)
        self.hook(edit(str(proj / "src/a.py"), cwd=str(proj)), "ceo")
        settings = self.tmp / "settings.json"
        settings.write_text(TEMPLATE.read_text())
        nobin = self.tmp / "nobin"  # no gh/git on PATH: the self-check's network and git probes degrade to COULD_NOT_CHECK
        nobin.mkdir()
        p = subprocess.run([sys.executable, str(SC / "operating_selfcheck.py"), "--settings", str(settings), "--project", str(proj)],
                           capture_output=True, text=True, env={**os.environ, "PATH": str(nobin)})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ceo-altitude-guard: PRESENT", p.stdout)
        self.assertIn("ceo-altitude: role=off; 1 main session(s) recorded, 1 direct source edit(s) in all", p.stdout)
        self.assertIn("ceo-altitude-session sess-1: 1 direct source edit(s)", p.stdout)

    def test_check_settings_wiring_states(self):
        self.assertEqual(selfcheck.check_settings(str(TEMPLATE))["ceo-altitude-guard"], "PRESENT")
        cfg = json.loads(TEMPLATE.read_text())
        cfg["hooks"]["UserPromptSubmit"] = [e for e in cfg["hooks"]["UserPromptSubmit"] if "ceo_altitude_guard" not in json.dumps(e)]
        half = self.tmp / "half.json"
        half.write_text(json.dumps(cfg))
        self.assertTrue(selfcheck.check_settings(str(half))["ceo-altitude-guard"].startswith("MISSING (needs both"))
        self.assertEqual(selfcheck.check_settings(str(self.tmp / "none.json"))["ceo-altitude-guard"], "MISSING")
        bad = self.tmp / "bad.json"
        bad.write_text("{not json")
        self.assertTrue(selfcheck.check_settings(str(bad))["ceo-altitude-guard"].startswith("COULD_NOT_CHECK"))

    def test_selfcheck_selftest_still_passes(self):
        r = subprocess.run([sys.executable, str(SC / "operating_selfcheck.py"), "--selftest"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Wiring(Base):
    def test_template_registers_the_guard_on_the_right_events_and_tools(self):
        import re
        hooks = json.loads(TEMPLATE.read_text())["hooks"]
        pre = [e for e in hooks["PreToolUse"] if "ceo_altitude_guard.py" in json.dumps(e)]
        self.assertEqual(len(pre), 1)
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
            self.assertRegex(tool, "^(?:" + pre[0]["matcher"] + ")$")
        for tool in ("Read", "Agent", "Task", "Grep", "WebFetch"):
            self.assertNotRegex(tool, "^(?:" + pre[0]["matcher"] + ")$")
        cmd = pre[0]["hooks"][0]["command"]
        self.assertTrue(cmd.endswith("|| true"), "a crash must never become a block")
        self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/skills/agentic-delivery/scripts/ceo_altitude_guard.py"', cmd)
        ups = [e for e in hooks["UserPromptSubmit"] if "ceo_altitude_guard.py" in json.dumps(e)]
        self.assertEqual(len(ups), 1)
        self.assertNotIn("matcher", ups[0])
        self.assertTrue(re.search(r"\|\| true$", ups[0]["hooks"][0]["command"]))

    def test_doctor_flags_an_installed_guard_that_nothing_calls(self):
        self.assertIn("ceo_altitude_guard.py", perun_doctor.HOOK_SCRIPTS)

    def install(self, target, home, *flags):
        (target / ".claude").mkdir(parents=True)
        home.mkdir()
        (target / ".claude/settings.local.json").write_text("{}")
        env = {k: v for k, v in os.environ.items() if k != "PERUN_POLICY"} | {"DCR_NO_PROBE": "1", "CLAUDE_CONFIG_DIR": str(home)}
        run = lambda: subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", "--apply-operating-layer", *flags, str(target)],  # noqa: E731
                                     capture_output=True, text=True, env=env)
        return run

    @unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "install.sh needs jq and bash")
    def test_install_wires_the_guard_and_the_installed_copy_runs_as_wired(self):
        target = self.tmp / "target"
        run = self.install(target, self.tmp / "home")
        self.assertEqual(run().returncode, 0)
        settings = target / ".claude/settings.local.json"
        before = settings.read_text()
        self.assertEqual(run().returncode, 0)
        self.assertEqual(settings.read_text(), before, "re-install must be idempotent")
        hooks = json.loads(before)["hooks"]
        cmds = {ev: [h["command"] for e in hooks[ev] for h in e["hooks"] if "ceo_altitude_guard.py" in h["command"]]
                for ev in ("PreToolUse", "UserPromptSubmit")}
        self.assertEqual({ev: len(c) for ev, c in cmds.items()}, {"PreToolUse": 1, "UserPromptSubmit": 1})
        self.assertTrue((target / ".claude/skills/agentic-delivery/scripts/ceo_altitude_guard.py").is_file())

        def wired(event, payload):  # exactly the command the host runs, with the host's env var
            env = {**os.environ, "CLAUDE_PROJECT_DIR": str(target), "PERUN_ROLE": "ceo-strict"}
            p = subprocess.run(["bash", "-c", cmds[event][0]], capture_output=True, text=True, env=env,
                               input=json.dumps(self.data({"cwd": str(target), **payload}, event)))
            self.assertEqual(p.returncode, 0, p.stderr)
            return p.stdout

        src = {"tool_name": "Write", "tool_input": {"file_path": str(target / "src/a.py")}}
        denied = json.loads(wired("PreToolUse", src))["hookSpecificOutput"]
        self.assertEqual(denied["permissionDecision"], "deny")
        self.assertEqual(wired("UserPromptSubmit", {"prompt": "ceo:off"}), "")
        self.assertEqual(wired("PreToolUse", src), "", "the owner's override reaches the installed hook")
        self.assertEqual(wired("PreToolUse", {**src, "agent_id": "lane-1"}), "")

    @unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "install.sh needs jq and bash")
    def test_uninstall_removes_the_guard_hooks_it_installed(self):
        target = self.tmp / "gone"
        self.assertEqual(self.install(target, self.tmp / "home3")().returncode, 0)
        settings = target / ".claude/settings.local.json"
        self.assertEqual(settings.read_text().count("ceo_altitude_guard.py"), 2)
        p = subprocess.run([sys.executable, str(ROOT / "scripts/perun_uninstall.py"), str(target), "--apply"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("ceo_altitude_guard", settings.read_text() if settings.exists() else "")

    @unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "install.sh needs jq and bash")
    def test_install_policy_flag_arms_the_role(self):
        target = self.tmp / "armed"
        p = self.install(target, self.tmp / "home2", "--policy", "role=ceo-strict")()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((target / ".perun/policy.json").read_text())["role"], "ceo-strict")


if __name__ == "__main__":
    unittest.main()
