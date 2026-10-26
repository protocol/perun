#!/usr/bin/env python3
"""stall_guard.py — Stop hook: one nudge when an autonomous turn ends on "stopped / holding / waiting on you" with nothing launched.

WHY: an agent hit one denial or blocker, then ended its turn saying it was stopped or waiting on the owner while other
lanes, reviews and builds were still open. A denial stops only that action.

RULE: read the hook JSON on stdin. Allow (print nothing) when `stop_hook_active` is true (the host sets it on the stop
that follows a block, so the nudge is one-shot and cannot loop) or `PERUN_STALL_GUARD=off`. Otherwise read the last
turn from `transcript_path` (Claude Code JSONL; the last 1 MB): the assistant entries after the last real user prompt.
When the last assistant text block matches STALL and that turn made no tool_use of `Agent`/`Task`/`Workflow` and none with
`run_in_background` true, print {"decision":"block","reason":REASON}. Second trigger (idle wait): the turn called
`ScheduleWakeup` or `CronCreate`, launched nothing, and the last text matches WAITING (CI, checks, merge, waiting):
block with WAIT_REASON, because a scheduled wake-up while a backlog is open is a stall, not progress. STALL is first person ("I'm stopped", "I am
holding") or names the owner ("waiting on you", "blocked by the owner"); fenced code, inline code and `>` quote lines
are removed first, so a quoted log line or "PR #12 on hold" never matches. REASON lets an owner-requested stop end the
turn, and the one-shot rule means that second stop passes.

Fail open: bad stdin, a missing or unreadable transcript, or any error exits 0 with no output.
Side effects: none (no state files). Register as `python3 ".../stall_guard.py" || true` on Stop.
Tests: scripts/test_stall_guard.py.
"""
import json
import os
import re
import sys

TAIL = 1 << 20
LAUNCH = ("Agent", "Task", "Workflow")
SLEEP = ("ScheduleWakeup", "CronCreate")
REASON = ("A denial or blocker stops only that action. Launch the next lane, review or build now, "
          "end if the owner asked you to stop or pause, or end by naming the one owner-only blocker and what keeps running.")
WAIT_REASON = "Waiting on CI is not a stop: launch the next priority lane now, then wake on the CI notification."
WAITING = re.compile(r"\b(?:waiting (?:on|for)|(?:CI|checks?) (?:is |are )?(?:running|pending|in progress)|until (?:CI|checks?))\b", re.I)
# ponytail: phrase list, not a classifier; a miss just lets the stop through. Add phrases when the field shows one.
STALL = re.compile(
    r"\b(?:i(?:'m| am) (?:stopp(?:ed|ing)|paus(?:ed|ing)|holding(?: here| off)?|standing by|on hold)"
    r"|(?:waiting|awaiting) (?:on|for) (?:you|your|the owner|owner|approval|a decision)"
    r"|awaiting (?:you|your|approval|a decision)"
    r"|(?:blocked|stuck) (?:on|by) (?:you|your|the owner|owner|a denial|the denial|permission)"
    r"|until you (?:approve|confirm|reply|say|decide|unblock))\b", re.I)
QUOTED = re.compile(r"(?s:```.*?(?:```|\Z))|`[^`\n]*`|^[ \t]*>[^\n]*", re.M)


def _blocks(entry):
    c = (entry.get("message") or {}).get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else [b for b in c or [] if isinstance(b, dict)]


NOTE_ID = re.compile(r"<(task-id|tool-use-id)>([^<]+)</\1>")
DONE = re.compile(r"<status>(?:completed|failed|killed|stopped|error)</status>")
LAUNCHED = re.compile(r'agentId: (\w+).{0,300}in the background|resumedAgentId\\?":\s*\\?"(\w+)', re.S)


def _open_bg(lines):
    """True when a background task is still open. State is per id, the latest event wins: a background tool_use (keyed by its
    tool_use id), a launch result (`agentId: X ... in the background`) or a resume result (`resumedAgentId`) opens it; a
    `<task-notification>` with a terminal `<status>` closes both its `<task-id>` and `<tool-use-id>`. One agent notifies again
    on every resume, so ids are tracked, not counted."""
    st = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        bl = _blocks(e)
        if e.get("type") != "user":
            for b in bl:
                if b.get("type") == "tool_use" and isinstance(b.get("input"), dict) and b["input"].get("run_in_background") is True:
                    st[b.get("id")] = True
            continue
        raw = json.dumps(bl)
        for m in LAUNCHED.finditer(raw):
            st[m.group(1) or m.group(2)] = True
        if "<task-notification>" in raw and DONE.search(raw):
            for m in NOTE_ID.finditer(raw):
                st[m.group(2)] = False
    return any(st.values())


def last_turn(path):
    """(last assistant text block, launched?, scheduled a wake-up?, background tasks still open?) for the turn after the last real user prompt in the transcript at `path`.
    Sidechain (subagent) entries are skipped; a tool_use with run_in_background true counts as a launch."""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - TAIL))
        lines = fh.read().decode("utf-8", "ignore").splitlines()
    text, launched, slept = "", False, False
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        bl = _blocks(e)
        if e.get("type") == "user":
            if any(b.get("type") != "tool_result" for b in bl) :
                break  # a real prompt: the turn starts here
            continue
        if e.get("type") != "assistant":
            continue
        for b in reversed(bl):
            if b.get("type") == "tool_use":
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                slept = slept or b.get("name") in SLEEP
                launched = launched or b.get("name") in LAUNCH or inp.get("run_in_background") is True
            elif b.get("type") == "text" and not text:
                text = str(b.get("text") or "")
    return text, launched, slept, _open_bg(lines)


def decide(payload):
    """The block dict for this Stop payload, or None to allow."""
    if payload.get("stop_hook_active") or os.environ.get("PERUN_STALL_GUARD", "").lower() == "off":
        return None
    text, launched, slept, open_bg = last_turn(payload["transcript_path"])
    text = QUOTED.sub("", text)
    if launched:
        return None
    if STALL.search(text):
        return {"decision": "block", "reason": REASON}
    if slept and not open_bg and WAITING.search(text):
        return {"decision": "block", "reason": WAIT_REASON}
    return None


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
