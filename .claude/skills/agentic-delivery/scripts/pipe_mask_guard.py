#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=flag a gate or push piped to tail/head/grep that masks its exit status, review=2027-01-30
"""PreToolUse(Bash) hook: flag a gate/push/merge command piped to tail/head/grep.

`gate | tail` reports the reader's exit status, so a failing gate reads as 0 and a
failed push gets reported as pushed. Reads the hook's stdin JSON
(`tool_input.command`) and matches `(git commit|push|merge | gh pr merge | qa | gate |
test | ci-gates | pytest | jest | vitest | lint | build | make | tsc | mypy | ruff | cargo | npm | pnpm | yarn) ... | tail|head|grep|tee|sed|awk` (`|&` too) where the command has neither `pipefail` nor
`PIPESTATUS`/`pipestatus`.

Default WARN: exit 0 with PreToolUse `hookSpecificOutput.additionalContext` JSON on
stdout. PIPE_MASK_MODE=block: exit 2 with the reason on stderr (the host blocks the
call). Unparseable stdin, a non-Bash tool, or no command -> silent exit 0 (a guard
must never wedge a session). Side effects: none.
Known limits: a quoted `|` inside an argument can false-positive; a pipe built
across separate commands is not seen. Fix for both: capture then echo the exit code.
"""
import json
import os
import re
import sys

HIT = re.compile(
    r"\b(git\s+(commit|push|merge)|gh\s+pr\s+merge|qa|gate|test|ci-gates|pytest|jest|vitest|lint|build|make|tsc|mypy|ruff|cargo|npm|pnpm|yarn)\b[^|]*(?<!\|)\|(?!\|)&?\s*(tail|head|grep|tee|sed|awk)\b"
)
SAFE = re.compile(r"pipefail|PIPESTATUS|pipestatus")
MSG = (
    "Pipe masks the gate's exit code: `cmd | tail/head/grep` returns the reader's status, so a failure reads as 0. "
    "Capture then echo (`cmd >/tmp/g.log 2>&1; echo exit=$?; tail /tmp/g.log`), or `set -o pipefail`, "
    "or read ${PIPESTATUS[0]} on the next command."
)


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return 0
    if data.get("tool_name", "Bash") != "Bash" or not HIT.search(cmd) or SAFE.search(cmd):
        return 0
    if os.environ.get("PIPE_MASK_MODE") == "block":
        print(MSG, file=sys.stderr)
        return 2
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": MSG}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
