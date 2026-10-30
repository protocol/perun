#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=nudge when the same command runs more than 3 times in a session, review=2027-01-30
"""PreToolUse(Bash) hook: nudge when the same command runs more than 3 times in one session.

A poll loop (`sleep 30; gh pr checks`, a watchdog call, a status snippet) re-reads the whole cached context on every
turn; in one heavy-use audit 4,730 repeated Bash calls cost about a tenth of all cache-read tokens. Reads the hook JSON
on stdin (`session_id`, `tool_input.command`), normalizes the command (whitespace collapsed, first 200 characters),
counts it per session in `$XDG_CACHE_HOME/perun/repeat-poll/<session>.json` (default `~/.cache`) and, on the
`REPEAT_POLL_MAX + 1`-th run (default 3, so the 4th) and every 10th run after that, prints PreToolUse
`hookSpecificOutput.additionalContext` telling the agent to start one detached job that writes a done-marker and to act
on its completion notice instead.

ADVISES ONLY: it always exits 0 and never blocks. Commands under 15 characters (`ls`, `git status`) are not counted.
Unparseable stdin, a non-Bash tool, a missing session id or an unwritable cache dir -> silent exit 0. Side effects: one
small JSON file per session; files older than 7 days are deleted on write.
Known limit: the same poll written with a different counter or timestamp counts as different commands.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

MSG = (
    "This exact command has run {n} times this session. Re-polling re-reads the whole context each turn. "
    "Start ONE detached job (`nohup CMD >log 2>&1 & disown`, or run_in_background) that writes a done-marker, "
    "then act on its completion notice instead of polling."
)


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command")
        cmd = cmd if isinstance(cmd, str) else ""
        sid = re.sub(r"[^\w.-]", "_", str(data.get("session_id") or ""))
    except (ValueError, AttributeError):
        return 0
    key = re.sub(r"\s+", " ", cmd.strip())[:200]
    if data.get("tool_name", "Bash") != "Bash" or len(key) < 15 or not sid:
        return 0
    try:
        d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun" / "repeat-poll"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{sid}.json"
        try:
            counts = json.loads(f.read_text())
        except (OSError, ValueError):
            counts = {}
        counts[key] = n = counts.get(key, 0) + 1
        f.write_text(json.dumps(counts))
        for old in d.glob("*.json"):
            if time.time() - old.stat().st_mtime > 7 * 86400:
                old.unlink(missing_ok=True)
    except OSError:
        return 0
    cap = int(os.environ.get("REPEAT_POLL_MAX", "3") or 3)
    if n > cap and (n - cap - 1) % 10 == 0:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": MSG.format(n=n)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
