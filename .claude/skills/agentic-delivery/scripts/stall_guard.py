#!/usr/bin/env python3
"""stall_guard.py — Stop hook: one nudge when an autonomous turn ends on "stopped / holding / waiting on you" with nothing launched.

WHY: an agent hit one denial or blocker, then ended its turn saying it was stopped or waiting on the owner while other
lanes, reviews and builds were still open. A denial stops only that action.

RULE: read the hook JSON on stdin. Allow (print nothing) when `stop_hook_active` is true (the host sets it on the stop
that follows a block, so the nudge is one-shot and cannot loop) or `PERUN_STALL_GUARD=off`. Otherwise read the last
turn from `transcript_path` (Claude Code JSONL; the last 1 MB): the assistant entries after the last real user prompt.
When the last assistant text matches STALL (fenced code removed) and that turn made no tool_use of `Agent`/`Task` and none
with `run_in_background` true, print {"decision":"block","reason":REASON}.

Fail open: bad stdin, a missing or unreadable transcript, or any error exits 0 with no output.
Side effects: none (no state files). Register as `python3 ".../stall_guard.py" || true` on Stop.
Tests: scripts/test_stall_guard.py.
"""
import json
import os
import re
import sys

TAIL = 1 << 20
LAUNCH = ("Agent", "Task")
REASON = ("A denial or blocker stops only that action. Launch the next lane, review or build now, "
          "or end by naming the one owner-only blocker and what keeps running.")
# ponytail: phrase list, not a classifier; a miss just lets the stop through. Add phrases when the field shows one.
STALL = re.compile(
    r"\b(?:i(?:'m| am) (?:stopp(?:ed|ing)|paus(?:ed|ing)|holding(?: here| off)?|standing by)|stopp(?:ed|ing) here"
    r"|holding (?:here|off|until|for)|on hold|standing by"
    r"|(?:waiting|awaiting) (?:on|for) (?:you|your|the owner|owner|approval|a decision)"
    r"|awaiting (?:you|your|approval|a decision)"
    r"|(?:blocked|stuck) (?:on|by) (?:you|your|the owner|owner|a denial|the denial|permission)"
    r"|until you (?:approve|confirm|reply|say|decide|unblock))\b", re.I)
FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)


def _blocks(entry):
    c = (entry.get("message") or {}).get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else [b for b in c or [] if isinstance(b, dict)]


def last_turn(path):
    """(last assistant text, launched?) for the turn after the last real user prompt in the transcript at `path`.
    Sidechain (subagent) entries are skipped; a Bash tool_use with run_in_background true counts as a launch."""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - TAIL))
        lines = fh.read().decode("utf-8", "ignore").splitlines()
    text, launched = "", False
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        bl = _blocks(e)
        if e.get("type") == "user":
            if any(b.get("type") != "tool_result" for b in bl):
                break  # a real prompt: the turn starts here
            continue
        if e.get("type") != "assistant":
            continue
        for b in bl:
            if b.get("type") == "tool_use":
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                launched = launched or b.get("name") in LAUNCH or inp.get("run_in_background") is True
            elif b.get("type") == "text" and not text:
                text = str(b.get("text") or "")
    return text, launched


def decide(payload):
    """The block dict for this Stop payload, or None to allow."""
    if payload.get("stop_hook_active") or os.environ.get("PERUN_STALL_GUARD", "").lower() == "off":
        return None
    text, launched = last_turn(payload["transcript_path"])
    if launched or not STALL.search(FENCE.sub("", text)):
        return None
    return {"decision": "block", "reason": REASON}


def main():
    try:
        out = decide(json.load(sys.stdin))
        if out:
            print(json.dumps(out))
    except Exception:  # fail open: a broken nudge must never trap a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
