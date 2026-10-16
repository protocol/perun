#!/usr/bin/env python3
"""SubagentStart hook: inject the project's house standing-default text into
every newly-spawned subagent's context, with a per-agent-type minimal-code
exemption.

WHY THIS EXISTS
---------------
A standing default that must hold for the whole fleet (a terse reporting
voice, a minimal-code bias, a cost rule) reaches only the main loop through a
session-start/per-turn hook, and is forgettable through a per-dispatch brief —
one missed dispatch, or a subagent spawned by another agent that never saw
the brief, silently drops it (`multi-session-coordination.md`, "A standing
house default must live where every subagent reads it"). `SubagentStart`
fires for every spawned subagent (built-in types and custom agent names
alike) and, per the host's hooks reference (`docs/standards-index.md`,
2026-09-27), can inject `hookSpecificOutput.additionalContext` into that
subagent's context before its first prompt — the durable, host-scope fix.

HOUSE_DEFAULTS_FILE FORMAT
--------------------------
`HOUSE_DEFAULTS_FILE` (env, required) names a plain-text file: the project's
own house standard, one line per rule. The voice/content is never vendored
here — this script only reads whatever file the project points it at. A line
starting with the literal tag `MINIMAL-CODE: ` carries a minimal-code-bias
rule. For every agent type EXCEPT one listed in
`HOUSE_MINIMAL_CODE_EXEMPT_TYPES` (comma-separated `agent_type` names,
default empty), the tag is stripped and the line is injected normally. For an
exempt type the line is dropped entirely: a design-port/design-alignment
lane's job is to reproduce a reference exactly, and a "simplest change that
works" bias makes it approximate the design with a generic component or drop
states (`rendered-parity.md`'s goalpost rule) — omission beats a caveat
nobody reads. Every other line is injected for every agent type unchanged.

LANE RULES (always injected, no house file needed)
---------------------------------------------------
`LANE_RULES` is a fixed constant, like `HOST_RULES`: every lane runs tool calls
only (zero prose between them) and ends with a key=value fields-only handback.
`handback_cap.py` (SubagentStop) only logs a miss of the shape (a rewrite would
re-read the lane's whole context and cost more than it saves), so this short
rule, about 48 estimated tokens, is the only lever.
Skipped for a type whose chat is its deliverable: `HANDBACK_EXEMPT_TYPES`
(same env var and same default list as `handback_cap.py`) plus
`LANE_RULES_SKIP_TYPES` (comma-separated, default empty) for a read-only review
type that keeps a raised cap instead of being exempt. `LANE_RULES=0` drops it.

FAILS OPEN, NEVER BLOCKS A SPAWN
---------------------------------
`SubagentStart` hooks cannot block subagent creation at all, but this script
still fails open deliberately: a missing `HOUSE_DEFAULTS_FILE` env var or an
unreadable file prints a stderr note and injects only the built-in `LANE_RULES`
and `HOST_RULES`; a non-`SubagentStart` event or malformed stdin injects nothing
(empty stdout, exit 0) — never a crash, never a partial/garbled injection.

INSTALL
-------
See `agentic-delivery/references/host-enforcement.md`.

USAGE
-----
  HOUSE_DEFAULTS_FILE=.claude/house-defaults.md subagent_start_inject.py < hook-input.json
  subagent_start_inject.py --selftest
"""
import json
import os
import sys

MINIMAL_CODE_TAG = "MINIMAL-CODE: "
# One-line skill-route reminder appended to every injection (default-on; set
# SKILL_ROUTE_REMINDER=0 to drop). Names the moments that are skipped most:
# the adversarial pass before an owner ask, structure before a human-facing message.
SKILL_ROUTE = ("Skill route: idea-critic before any owner ask or new plan; "
               "communication-structure before any human-facing message; "
               "agentic-ceo to choose among skills.")
# Host-refusal rules, always injected (SubagentStart here, SessionStart via session_brief.py): field logs
# showed hundreds of daily refusals for `sleep N` waits and `cd X && ...; git ...` chains in worktrees.
HOST_RULES = ("Host rules: never `sleep N` to wait; background the command and act on its completion notification, "
              "or Monitor with an until-loop.\n"
              "In an isolated worktree run plain separate git commands from the worktree root; "
              "no `cd X &&` chains or loops around git (the host refuses them as too complex to verify).\n"
              "Find any Perun skill or tool: read .claude/skills/INDEX.md first.")
# Zero-chat lane rules, injected for every type except those in CHAT_TYPES. The size and shape named here are the target
# handback_cap.py logs against (its default TARGET_CHARS 400); scripts/test_zero_chat_lanes.py pins both and CHAT_TYPES.
LANE_RULES = ("Lane output: tool calls only, no prose between them. Final message: key=value fields only, "
              "under 400 characters: status=VERIFIED|UNVERIFIED, sha=, result=, tests=, blockers=, report=<path>.")
CHAT_TYPES = "Explore,Plan,claude-code-guide,statusline-setup"  # equals handback_cap.DEFAULT_EXEMPT_TYPES


def build_context(house_text: str, agent_type: str, exempt_types: set) -> str:
    """The `additionalContext` text for one `agent_type`.

    A `MINIMAL_CODE_TAG`-prefixed line is dropped for an exempt type, else
    injected with the tag stripped; every other line is injected as is.
    """
    exempt = agent_type in exempt_types
    lines = []
    for line in house_text.splitlines():
        if line.startswith(MINIMAL_CODE_TAG):
            if exempt:
                continue
            line = line[len(MINIMAL_CODE_TAG):]
        lines.append(line)
    return "\n".join(lines)


def run(stdin_text: str) -> str:
    """The hook's stdout for one hook-input JSON string; `''` injects nothing.

    `''` on: a non-`SubagentStart` event or unparseable stdin. With no/unreadable
    `HOUSE_DEFAULTS_FILE` (or an all-dropped one) only `LANE_RULES` (unless the type is in `CHAT_TYPES`) and
    `HOST_RULES` are injected. Never raises.
    """
    try:
        data = json.loads(stdin_text)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        sys.stderr.write("subagent_start_inject: hook input is not a JSON object; injecting nothing.\n")
        return ""
    if data.get("hook_event_name") != "SubagentStart":
        return ""
    house_file = os.environ.get("HOUSE_DEFAULTS_FILE")
    house_text = ""
    if not house_file:
        sys.stderr.write("subagent_start_inject: HOUSE_DEFAULTS_FILE not set; injecting the built-in lane and host rules only.\n")
    else:
        try:
            with open(house_file, encoding="utf-8") as fh:
                house_text = fh.read()
        except OSError as exc:
            sys.stderr.write(f"subagent_start_inject: cannot read HOUSE_DEFAULTS_FILE {house_file!r}: {exc}; injecting the built-in lane and host rules only.\n")
    exempt_types = set(filter(None, os.environ.get("HOUSE_MINIMAL_CODE_EXEMPT_TYPES", "").split(",")))
    agent_type = str(data.get("agent_type") or "")
    context = build_context(house_text, agent_type, exempt_types)
    if context.strip() and os.environ.get("SKILL_ROUTE_REMINDER") != "0":
        context += "\n" + SKILL_ROUTE
    skip = set(filter(None, (os.environ.get("HANDBACK_EXEMPT_TYPES", CHAT_TYPES) + "," + os.environ.get("LANE_RULES_SKIP_TYPES", "")).split(",")))
    lane = LANE_RULES + "\n" if os.environ.get("LANE_RULES") != "0" and agent_type not in skip else ""
    context = (context + "\n" if context.strip() else "") + lane + HOST_RULES
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}})


def main() -> int:
    out = run(sys.stdin.read())
    if out:
        print(out)
    return 0


# ---------------------------------------------------------------------------
# --selftest — exercises run()/build_context() directly (no subprocess).
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    passed = 0
    failed = 0

    def case(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print(f"PASS  {name}")
        else:
            failed += 1
            print(f"FAIL  {name} (got {got!r}, want {want!r})")

    house = "Be terse.\nMINIMAL-CODE: Simplest change that works.\nNo unrequested features.\n"
    tmp = tempfile.mkdtemp(prefix="subagent-start-inject-selftest-")
    house_path = os.path.join(tmp, "house.md")
    with open(house_path, "w", encoding="utf-8") as fh:
        fh.write(house)

    saved_env = {k: os.environ.get(k) for k in ("HOUSE_DEFAULTS_FILE", "HOUSE_MINIMAL_CODE_EXEMPT_TYPES", "SKILL_ROUTE_REMINDER")}
    try:
        os.environ["HOUSE_DEFAULTS_FILE"] = house_path
        os.environ.pop("HOUSE_MINIMAL_CODE_EXEMPT_TYPES", None)

        payload = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "builder"})
        out = run(payload)
        obj = json.loads(out) if out else {}
        ctx = obj.get("hookSpecificOutput", {}).get("additionalContext", "")
        case("non-exempt-keeps-minimal-code-tag-stripped",
             "Simplest change that works." in ctx and "MINIMAL-CODE:" not in ctx, True)
        case("non-exempt-keeps-other-lines", "Be terse." in ctx and "No unrequested features." in ctx, True)
        case("output-names-the-event", obj.get("hookSpecificOutput", {}).get("hookEventName"), "SubagentStart")

        os.environ["HOUSE_MINIMAL_CODE_EXEMPT_TYPES"] = "design-lane,other-exempt"
        payload = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "design-lane"})
        out = run(payload)
        obj = json.loads(out) if out else {}
        ctx = obj.get("hookSpecificOutput", {}).get("additionalContext", "")
        case("exempt-type-drops-minimal-code-line", "Simplest change" not in ctx and "MINIMAL-CODE" not in ctx, True)
        case("exempt-type-keeps-other-lines", "Be terse." in ctx and "No unrequested features." in ctx, True)

        case("route-reminder-default-on", "Skill route: idea-critic" in ctx, True)
        os.environ["SKILL_ROUTE_REMINDER"] = "0"
        off = json.loads(run(payload))["hookSpecificOutput"]["additionalContext"]
        case("route-reminder-opt-out", "Skill route" not in off, True)
        os.environ.pop("SKILL_ROUTE_REMINDER")

        case("non-subagentstart-event-empty", run(json.dumps({"hook_event_name": "Stop"})), "")
        case("malformed-stdin-empty", run("not json"), "")

        os.environ.pop("HOUSE_DEFAULTS_FILE", None)
        hr = lambda o: json.loads(o)["hookSpecificOutput"]["additionalContext"] if o else ""
        case("missing-env-var-lane-and-host-rules-only", hr(run(json.dumps({"hook_event_name": "SubagentStart"}))), LANE_RULES + "\n" + HOST_RULES)
        case("host-rules-no-sleep-no-cd-chain", "sleep N" in HOST_RULES and "cd X &&" in HOST_RULES and HOST_RULES.count("\n") <= 2, True)
        case("host-rules-also-with-house-file", HOST_RULES in ctx, True)
        case("lane-rules-also-with-house-file", LANE_RULES in ctx, True)
        explore = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "Explore"})
        case("chat-deliverable-type-gets-no-lane-rules", hr(run(explore)), HOST_RULES)
        os.environ["LANE_RULES"] = "0"
        case("lane-rules-opt-out", hr(run(json.dumps({"hook_event_name": "SubagentStart"}))), HOST_RULES)
        os.environ.pop("LANE_RULES")
        os.environ["LANE_RULES_SKIP_TYPES"] = "security-reviewer"
        case("skip-types-env-drops-lane-rules", hr(run(json.dumps({"hook_event_name": "SubagentStart", "agent_type": "security-reviewer"}))), HOST_RULES)
        os.environ.pop("LANE_RULES_SKIP_TYPES")

        os.environ["HOUSE_DEFAULTS_FILE"] = os.path.join(tmp, "does-not-exist.md")
        case("unreadable-file-lane-and-host-rules-only", hr(run(json.dumps({"hook_event_name": "SubagentStart"}))), LANE_RULES + "\n" + HOST_RULES)

        os.environ["HOUSE_DEFAULTS_FILE"] = house_path
        case("build-context-pure", build_context("MINIMAL-CODE: x\ny\n", "a", {"a"}), "y")
    finally:
        for key, val in saved_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
