#!/usr/bin/env python3
"""reply_cap.py — owner rule: chat replies max 3 lines, 500 chars.

Two events, one file (the global install copies it alone):
- UserPromptSubmit: prints the cap as one line, so the reply is short the first time.
- Stop: reads the transcript; when the last assistant text of the turn is over the cap, appends one dated line to the
  counter log and exits 2 with a rewrite instruction (blocks the stop). The log makes the rewrite rate measurable.

Allowed without a block: `stop_hook_active` true (one block per turn, no loop), `REPLY_CAP=off`, and a last user
message that asks for detail ("detail", "details", "full", "explain"). Register on Stop and UserPromptSubmit only.
A different reply_cap script on a user-level Stop hook (`CLAUDE_USER_SETTINGS`, default ~/.claude/settings.json) makes this
one skip, so an over-cap reply gets one rewrite demand, not two.
Caps: REPLY_CAP_LINES (3), REPLY_CAP_CHARS (500). Log: REPLY_CAP_LOG, else `$XDG_CACHE_HOME|~/.cache`/perun/reply-cap.log,
lines `YYYY-MM-DD lines=N chars=M`; count a day with `grep -c ^2026-10-26 FILE`. Fail open: any error exits 0.
Side effects: the log append only. Tests: `reply_cap.py --selftest`.
"""
import json
import os
import re
import sys
import tempfile
import time

LINES = int(os.environ.get("REPLY_CAP_LINES", "3"))
CHARS = int(os.environ.get("REPLY_CAP_CHARS", "500"))
DETAIL = ("detail", "details", "full", "explain")
INJECT = (f"Reply cap (owner rule): at most {LINES} short lines and {CHARS} characters; outcome and any decision only, "
          "no lists, tables or recap. Put detail in a file.")


def _text(entry):
    c = (entry.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text")


def last_texts(path):
    """(last assistant text of the current turn, last real user text) from a JSONL transcript."""
    a = u = ""
    with open(path, errors="ignore") as fh:
        for ln in fh:
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("isSidechain"):
                continue
            t = _text(e)
            if e.get("type") == "assistant" and t.strip():
                a = t
            elif e.get("type") == "user" and not e.get("toolUseResult") and t.strip():
                u, a = t, ""
    return a, u


def log_path():
    p = os.environ.get("REPLY_CAP_LOG")
    return p or os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "perun", "reply-cap.log")


def other_cap_hook():
    """True when a user-level Stop hook runs a reply_cap script other than this file (it already enforces the cap)."""
    try:
        sp = os.environ.get("CLAUDE_USER_SETTINGS") or os.path.expanduser("~/.claude/settings.json")
        with open(sp) as fh:
            groups = (json.load(fh).get("hooks") or {}).get("Stop") or []
        me = os.path.realpath(__file__)
        for g in groups:
            for h in g.get("hooks") or []:
                for tok in re.findall(r"[^\s\"']*reply[_-]cap[^\s\"']*", h.get("command") or ""):
                    p = os.path.realpath(os.path.expandvars(os.path.expanduser(tok)))
                    if p != me and os.path.isfile(p) and os.access(p, os.X_OK):
                        return True
    except Exception:
        pass
    return False


def check(data):
    """(exit code, stderr message). Appends the counter line when it blocks."""
    if data.get("stop_hook_active") or os.environ.get("REPLY_CAP", "").lower() == "off" or other_cap_hook():
        return 0, ""
    reply, user = data.get("last_assistant_message") or "", ""
    p = data.get("transcript_path")
    if p and os.path.exists(p):
        t, user = last_texts(p)
        reply = reply or t
    n = len([x for x in reply.splitlines() if x.strip()])
    if not reply or (n <= LINES and len(reply) <= CHARS) or any(w in user.lower() for w in DETAIL):
        return 0, ""
    lp = log_path()
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    with open(lp, "a") as fh:  # ponytail: append-only, no rotation (about 30 bytes a block)
        fh.write(f"{time.strftime('%Y-%m-%d')} lines={n} chars={len(reply)}\n")
    return 2, (f"Reply too long ({n} lines, {len(reply)} chars; owner cap {LINES} lines / {CHARS} chars). "
               f"Rewrite your final reply in at most {LINES} short lines: the outcome and any decision needed. "
               "No lists, tables, or recap. Put detail in a file, not in chat.")


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("hook_event_name") == "UserPromptSubmit":
            if os.environ.get("REPLY_CAP", "").lower() != "off":
                print(INJECT)
            return 0
        code, msg = check(data)
    except Exception:
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code


def _selftest():
    import subprocess
    tmp = tempfile.mkdtemp(prefix="reply-cap-")
    log = os.environ["REPLY_CAP_LOG"] = os.path.join(tmp, "sub", "cap.log")
    os.environ.pop("REPLY_CAP", None)
    os.environ["CLAUDE_USER_SETTINGS"] = os.path.join(tmp, "none.json")  # the host's real settings must not leak in
    tr =os.path.join(tmp, "t.jsonl")

    def write(user, reply):
        with open(tr, "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": user}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}}) + "\n")
    long_ = "\n".join(f"line {i}" for i in range(6))
    res = []
    write("hi", "done")
    res.append(("short-allowed", check({"transcript_path": tr}) == (0, "")))
    write("hi", long_)
    code, msg = check({"transcript_path": tr})
    res.append(("long-lines-blocked", code == 2 and "6 lines" in msg))
    res.append(("block-logs-dated-line", open(log).read().strip() == f"{time.strftime('%Y-%m-%d')} lines=6 chars={len(long_)}"))
    write("hi", "x" * 501)
    res.append(("long-chars-blocked", check({"transcript_path": tr})[0] == 2))
    res.append(("two-blocks-two-log-lines", len(open(log).read().splitlines()) == 2))
    res.append(("stop-hook-active-allows", check({"transcript_path": tr, "stop_hook_active": True}) == (0, "")))
    write("explain the plan in detail", long_)
    res.append(("detail-request-allowed", check({"transcript_path": tr}) == (0, "")))
    write("hi", long_)
    os.environ["REPLY_CAP"] = "off"
    res.append(("off-allows", check({"transcript_path": tr}) == (0, "")))
    os.environ.pop("REPLY_CAP")
    res.append(("last_assistant_message-used", check({"last_assistant_message": long_})[0] == 2))
    res.append(("missing-transcript-allows", check({"transcript_path": tr + "x"}) == (0, "")))
    us = os.environ["CLAUDE_USER_SETTINGS"] = os.path.join(tmp, "user.json")

    def settings(cmd):
        json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": cmd}]}]}}, open(us, "w"))
    settings('python3 "/elsewhere/reply_cap.py"')
    res.append(("nonexistent-other-cap-hook-still-blocks", check({"transcript_path": tr})[0] == 2))
    other = os.path.join(tmp, "reply_cap.py")
    open(other, "w").write("#!/bin/sh\n")
    settings(f'python3 "{other}"')
    res.append(("non-executable-other-cap-hook-still-blocks", check({"transcript_path": tr})[0] == 2))
    os.chmod(other, 0o755)
    res.append(("other-user-level-cap-hook-skips", check({"transcript_path": tr}) == (0, "")))
    settings(f'python3 "{os.path.abspath(__file__)}"')
    res.append(("own-user-level-entry-still-blocks", check({"transcript_path": tr})[0] == 2))
    settings("python3 other_hook.py")
    res.append(("unrelated-stop-hook-still-blocks", check({"transcript_path": tr})[0] == 2))
    os.environ["CLAUDE_USER_SETTINGS"] = os.path.join(tmp, "missing.json")
    res.append(("missing-user-settings-still-blocks", check({"transcript_path": tr})[0] == 2))
    n =len(open(log).read().splitlines())
    r = subprocess.run([sys.executable, __file__], input=json.dumps({"hook_event_name": "UserPromptSubmit"}),
                       capture_output=True, text=True)
    res.append(("prompt-submit-injects-cap", r.returncode == 0 and "Reply cap" in r.stdout and "3 short lines" in r.stdout))
    r = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True)
    res.append(("garbage-stdin-exit-0", r.returncode == 0 and r.stdout == ""))
    res.append(("inject-does-not-log", len(open(log).read().splitlines()) == n))
    for name, ok in res:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"selftest: {sum(ok for _, ok in res)}/{len(res)} passed")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
