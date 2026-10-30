#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=tell a lane to checkpoint near its tool-call cap, review=2027-01-30
"""PostToolUse hook: count a lane's tool calls and tell it to checkpoint near its cap.

A lane cannot see its own token spend while it runs, but every tool call it
makes fires PostToolUse — so the cap is on tool calls, which the host can
count. Reads the hook's stdin JSON and increments a counter keyed by
`agent_id`, which the host sends only inside a subagent: with no `agent_id`
the call is the main thread and is never counted. The cap is
LANE_TOOL_CAP_<TYPE> for the subagent's `agent_type` (uppercased, every
non-alphanumeric character turned into `_`, e.g. LANE_TOOL_CAP_GENERAL_PURPOSE),
falling back to LANE_TOOL_CAP:

  count == ceil(80% of cap)  -> injects "checkpoint now: write handback marked
                                UNVERIFIED with remaining work"
  count >= cap               -> injects "stop: hand back UNVERIFIED" on every
                                further call

Injection is PostToolUse `hookSpecificOutput.additionalContext` JSON on
stdout with exit 0 (https://code.claude.com/docs/en/hooks). It NEVER blocks a
tool: PostToolUse cannot block (the tool already ran), and a stuck counter
must not wedge a lane — the handback status token is enforced separately by
handback_cap.py at SubagentStop (opt-in). A cap that is unset, empty, zero,
or not an integer -> the hook does nothing for that lane (opt-in; set it per
lane type at the measured p90). Unparseable stdin or an unwritable state dir
-> silent exit 0.

Side effects: one small counter file per agent_id under LANE_CAP_STATE_DIR
(default: <tempdir>/claude-lane-cap), written to a temp file and moved into
place with os.replace so a concurrent reader never sees a torn count. When a
new lane's first counter is written, counter files untouched for more than
PRUNE_DAYS (7) days are deleted.
"""
import json
import math
import os
import re
import sys
import tempfile
import time

CHECKPOINT = "checkpoint now: write handback marked UNVERIFIED with remaining work"
STOP = "stop: hand back UNVERIFIED"
PRUNE_DAYS = 7


def _cap(agent_type):
    typed = "LANE_TOOL_CAP_" + re.sub(r"[^A-Za-z0-9]", "_", agent_type).upper() if agent_type else ""
    raw = (os.environ.get(typed) if typed else None) or os.environ.get("LANE_TOOL_CAP", "")
    try:
        return max(int(raw or 0), 0)
    except ValueError:
        return 0


def _state_dir():
    return os.environ.get("LANE_CAP_STATE_DIR") or os.path.join(tempfile.gettempdir(), "claude-lane-cap")


def _prune(state_dir, now):
    for name in os.listdir(state_dir):
        path = os.path.join(state_dir, name)
        try:
            if now - os.path.getmtime(path) > PRUNE_DAYS * 86400:
                os.remove(path)
        except OSError:
            pass


def check(data):
    """Count one tool call for this subagent lane; return the context line to inject, or None."""
    agent_id = str(data.get("agent_id") or "")
    if not agent_id:
        return None  # main thread: never counted
    cap = _cap(str(data.get("agent_type") or ""))
    if not cap:
        return None
    state_dir = _state_dir()
    safe = "".join(c for c in agent_id if c.isalnum() or c in "-_") or "unknown"
    path = os.path.join(state_dir, safe)
    try:
        with open(path) as fh:
            count = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        count = 0
    count += 1
    os.makedirs(state_dir, exist_ok=True)
    if count == 1:
        _prune(state_dir, time.time())
    fd, tmp = tempfile.mkstemp(dir=state_dir, prefix=".tmp-")
    with os.fdopen(fd, "w") as fh:
        fh.write(str(count))
    os.replace(tmp, path)
    if count >= cap:
        return f"{STOP} (tool call {count} of cap {cap})"
    if count == math.ceil(cap * 0.8):
        return f"{CHECKPOINT} (tool call {count} of cap {cap})"
    return None


def main():
    try:
        line = check(json.load(sys.stdin))
    except Exception:
        return 0  # never wedge a lane on bad input or an unwritable state dir
    if line:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": line}}))
    return 0


# ---------------------------------------------------------------------------
# --selftest — exercises check() and main() in-process with an isolated
# state dir and env.
# ---------------------------------------------------------------------------
def _selftest():
    import io
    import shutil

    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        passed += bool(ok)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    tmp = tempfile.mkdtemp(prefix="lane-cap-selftest-")
    keys = ("LANE_TOOL_CAP", "LANE_CAP_STATE_DIR", "LANE_TOOL_CAP_SECURITY_REVIEWER")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["LANE_CAP_STATE_DIR"] = tmp
    os.environ.pop("LANE_TOOL_CAP_SECURITY_REVIEWER", None)
    try:
        os.environ["LANE_TOOL_CAP"] = ""
        case("unset-cap-is-noop", check({"agent_id": "n1"}) is None and not os.listdir(tmp))
        os.environ["LANE_TOOL_CAP"] = "abc"
        case("non-integer-cap-is-noop", check({"agent_id": "n2"}) is None)

        os.environ["LANE_TOOL_CAP"] = "1"
        case("main-thread-never-counted", check({"session_id": "main-1"}) is None and not os.listdir(tmp))

        os.environ["LANE_TOOL_CAP"] = "10"
        got = [check({"agent_id": "a1", "session_id": "s"}) for _ in range(11)]
        case("silent-before-80pct", all(g is None for g in got[:7]))
        case("checkpoint-at-80pct", got[7] is not None and got[7].startswith(CHECKPOINT))
        case("silent-between-checkpoint-and-cap", got[8] is None)
        case("stop-at-cap", got[9] is not None and got[9].startswith(STOP))
        case("stop-repeats-past-cap", got[10] is not None and got[10].startswith(STOP))
        case("agent-ids-are-independent", check({"agent_id": "a2", "session_id": "s"}) is None)
        case("atomic-write-leaves-no-temp-files", not [n for n in os.listdir(tmp) if n.startswith(".tmp-")])

        os.environ["LANE_TOOL_CAP_SECURITY_REVIEWER"] = "2"
        typed = [check({"agent_id": "t1", "agent_type": "security-reviewer"}) for _ in range(2)]
        case("per-type-cap-overrides-default", typed[1] is not None and typed[1].startswith(STOP))
        case("other-type-falls-back-to-default", check({"agent_id": "t2", "agent_type": "builder"}) is None)

        old = os.path.join(tmp, "stale-lane")
        with open(old, "w") as fh:
            fh.write("5")
        os.utime(old, (time.time() - 8 * 86400,) * 2)
        check({"agent_id": "fresh-lane"})
        case("stale-state-pruned-on-new-lane", not os.path.exists(old) and os.path.exists(os.path.join(tmp, "a1")))

        os.environ["LANE_TOOL_CAP"] = "1"
        real_stdin, real_stdout = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(json.dumps({"agent_id": "j1"})), io.StringIO()
        try:
            rc = main()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = real_stdin, real_stdout
        try:
            ctx = json.loads(out)["hookSpecificOutput"]
            ok = rc == 0 and ctx["hookEventName"] == "PostToolUse" and ctx["additionalContext"].startswith(STOP)
        except (ValueError, KeyError):
            ok = False
        case("main-emits-posttooluse-additionalcontext-exit-0", ok)

        sys.stdin = io.StringIO("not json")
        try:
            case("garbage-stdin-exit-0", main() == 0)
        finally:
            sys.stdin = real_stdin
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
