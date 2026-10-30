#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=stop a subagent brief that names a tool the lane does not have, review=2027-01-30
"""PreToolUse(Agent|Task) hook: stop a subagent brief that tells the lane to use a tool it does not have.

A lane told to "use the Monitor tool" or "call the bash tool" burns turns on `No such tool` errors (166 dead turns in
one heavy-use audit: Monitor absent in subagents, the shell tool is `Bash`, not `bash`). Reads the hook JSON on stdin
(`tool_input.prompt`, optional `subagent_type`) and flags:
- a tool in the dead set (`PERUN_BRIEF_DEAD_TOOLS`, default `Monitor`) named in the brief as a tool (`Monitor tool`,
  `use Monitor`, `the Monitor`), unless `.claude/agents/<subagent_type>.md` lists it in its `tools:` frontmatter;
- a lowercase built-in tool name used as a tool name (`bash tool`, `the read tool`, `tool: grep`); the real names are
  `Bash`, `Read`, `Edit`, `Write`, `Grep`, `Glob`. Prose such as "a bash script" or "bash -c" is not flagged.

Default: ADVISORY, not a hard gate. Exit 2 with the fix on stderr, ONCE per distinct brief (a stamp in
`$XDG_CACHE_HOME/perun/brief-lint/`, default `~/.cache`); resending the same brief unchanged passes by design, so the
guard cannot wedge a session. `BRIEF_LINT_MODE=warn` prints
PreToolUse `additionalContext` instead and never blocks. Unparseable stdin, another tool or no prompt -> silent exit 0.
Side effects: one empty stamp file per blocked brief.
Known limit: it sees only the brief text, not the lane's real tool list; a tool the host removes elsewhere is not known.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

LOWER = re.compile(r"(?<![\w/.-])(bash|read|edit|write|grep|glob)(?:`|\")?\s+tool\b|\btool[:=\s]+[`\"']?(bash|read|edit|write|grep|glob)\b(?![\w.-])|\b(?i:call|use|run|invoke)\s+`(bash|read|edit|write|grep|glob)`")


def _allowed(agent_type):
    """Tool names from the `tools:` frontmatter of .claude/agents/<type>.md, or set() when unknown."""
    if not re.fullmatch(r"[\w.-]+", agent_type or ""):
        return set()
    p = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".") / ".claude/agents" / f"{agent_type}.md"
    try:
        m = re.search(r"^tools:\s*(.+)$", p.read_text().split("---")[1], re.M)
    except (OSError, ValueError, IndexError):  # ValueError covers a non-UTF-8 agent file
        return set()
    return {t.strip() for t in m.group(1).split(",")} if m else set()


def problems(prompt, agent_type=""):
    out = []
    dead = [t for t in (os.environ.get("PERUN_BRIEF_DEAD_TOOLS") or "Monitor").split(",") if t.strip()]
    allowed = _allowed(agent_type)
    for t in dead:
        t = t.strip()
        if t not in allowed and re.search(rf"\b(?:use|call|invoke|run|with|the|via)\s+(?:the\s+)?`?{re.escape(t)}`?\b|\b{re.escape(t)}\s+tool\b", prompt):
            out.append(f"`{t}` is not available to this lane (`No such tool`); tell it to run a detached job with `Bash` and read the log, or wait for the completion notice")
    for m in LOWER.finditer(prompt):
        n = next(g for g in m.groups() if g)
        out.append(f"tool names are case-sensitive: `{n.capitalize()}`, not `{n}`")
    return out


def main():
    try:
        data = json.load(sys.stdin)
        ti = data.get("tool_input") or {}
        prompt = ti.get("prompt")
    except (ValueError, AttributeError):
        return 0
    if data.get("tool_name") not in ("Agent", "Task") or not isinstance(prompt, str) or not prompt:
        return 0
    found = problems(prompt, ti.get("subagent_type") or "")
    if not found:
        return 0
    msg = "Subagent brief names tools the lane lacks: " + "; ".join(dict.fromkeys(found)) + ". Fix the brief."
    if os.environ.get("BRIEF_LINT_MODE") == "warn":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))
        return 0
    try:
        d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun" / "brief-lint"
        stamp = d / hashlib.sha256(prompt.encode()).hexdigest()[:32]
        if stamp.exists():
            return 0
        d.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        return 0
    print(msg + " Resending the same brief unchanged will pass.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
