#!/usr/bin/env python3
# rail: owner=agentic-ceo, why=a deferred owner question is no reason to sit idle while work remains, review=2027-01-30
"""stop_reminder.py — advisory deferred-question hooks: a deferred owner
question is not a reason to sit idle while other work remains.

WHY THIS EXISTS
---------------
In an owner-requested autonomous run, agents stopped for hours on a question
the owner was not there to answer, although other items in the backlog did not
depend on it. `task_ledger.py defer` records such a question (with the default
taken, or the one item parked) and `task_ledger.py next` names the next item
that is not owner-gated. These hooks surface that at two moments.

TWO OUTPUTS, CHOSEN BY THE HOOK EVENT (hooks reference, fetched 2026-09-24)
-------------------------------------------------------------------------
- `Stop`: an OWNER-FACING notice. It prints only `{"systemMessage": ...}`, the
  universal field documented as "Warning message shown to the user"; the
  model is not guaranteed to see it.
- `SessionStart` / `UserPromptSubmit`: a MODEL-VISIBLE line at turn start. It
  prints `hookSpecificOutput.additionalContext` ("pending deferred questions:
  N; next non-gated item: T-###"), which those events inject as context.
- Any other event: nothing.
A notice is due only when a deferred question is pending AND an open/doing row
exists (a bounded O(rows) check; blocked and parked rows never count).

WHAT IT NEVER DOES
------------------
It never blocks and never continues a turn: no `decision`, no `continue`, and
always exit 0. A missing sibling module, unreadable input, a bad argument, a
missing ledger, a malformed file, or any crash prints nothing and exits 0: it
is advisory, so it fails open to silence rather than to a block. The owner can
always stop the agent or answer; nothing here prevents an agent from asking or
stopping.

INSTALL (optional, owner-installed; `install.sh` never edits settings)
----------------------------------------------------------------------
See `agentic-delivery/references/host-enforcement.md` for the `Stop` and `UserPromptSubmit` snippet.
The ledger defaults to `<cwd>/.claude/TASKS.md`, where `cwd` comes from the
hook input; `--file PATH` overrides it.

EXIT CODES
----------
  0  always as a hook, with or without a reminder (exit 2 would block a Stop)
  1  `--selftest` only: a selftest case failed

USAGE
-----
  stop_reminder.py [--file PATH] < hook-input.json
  stop_reminder.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import task_ledger  # sibling script, stdlib-only
except BaseException:  # noqa: BLE001 - a missing/broken sibling must mean silence, never a failing hook
    task_ledger = None

TURN_START_EVENTS = ("SessionStart", "UserPromptSubmit")


def pending_and_next(ledger_path: str):
    """(pending question count, first non-gated item id), or None when no notice is due.

    Bounded O(rows + questions): the item is the oldest `doing` row, else the
    oldest `open` row. Blocked (including parked) and resolved rows never
    count. No PRIORITY.md similarity pass; `task_ledger.py next` gives the
    priority order. Raises on an unreadable/malformed file; `run` swallows it.
    Side-effects: reads the ledger and QUESTIONS.jsonl beside it; writes nothing.
    """
    pending = len(task_ledger.pending_questions(task_ledger._read_questions(ledger_path)))
    if not pending:
        return None
    live = [r for r in task_ledger._read_rows(ledger_path) if r["status"] in ("doing", "open")]
    if not live:
        return None
    row = min(live, key=lambda r: (r["status"] != "doing", r["created"], r["id"]))
    return pending, row["id"]


def run(stdin_text: str, file_arg: str = None) -> str:
    """Hook stdout for one invocation ("" = print nothing). Never raises.

    `Stop` (or no event name) -> an owner-facing `systemMessage`;
    `SessionStart` / `UserPromptSubmit` -> model-visible
    `hookSpecificOutput.additionalContext`; any other event -> nothing.
    """
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
        event = data.get("hook_event_name") or "Stop"
        path = file_arg or os.path.join(data.get("cwd") or os.getcwd(), ".claude", "TASKS.md")
        if event != "Stop" and event not in TURN_START_EVENTS:
            return ""
        due = pending_and_next(path)
        if not due:
            return ""
        count, item = due
        if event in TURN_START_EVENTS:
            text = (f"pending deferred questions: {count}; next non-gated item: {item}. Keep working "
                    "(`task_ledger.py next`); the owner's batch is `task_ledger.py questions`.")
            return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})
        return json.dumps({"systemMessage": (
            f"Deferred-question owner notice: {count} question(s) wait in `task_ledger.py questions`; "
            f"{item} is not gated on them (`task_ledger.py next`).")})
    except BaseException:  # noqa: BLE001 - advisory: any failure is silence, never a block or an error notice
        return ""


def main(argv: list = None) -> int:
    """CLI / hook entry point. Always exits 0 outside --selftest (exit 2 would block a Stop)."""
    try:
        ap = argparse.ArgumentParser(prog="stop_reminder.py", description="Advisory deferred-question hook.")
        ap.add_argument("--file", default=None, help="ledger file (default <hook cwd>/.claude/TASKS.md)")
        ap.add_argument("--selftest", action="store_true")
        args = ap.parse_args(argv)
    except BaseException:  # noqa: BLE001
        return 0
    if args.selftest:
        return _selftest()
    try:
        out = run(sys.stdin.read(), args.file)
        if out:
            print(out)
    except BaseException:  # noqa: BLE001
        pass
    return 0


def _selftest() -> int:
    global task_ledger, run
    import contextlib
    import io
    import shutil
    import tempfile

    failures, ran = [], [0]

    def check(label: str, cond: bool, detail: str = "") -> None:
        ran[0] += 1
        if not cond:
            failures.append(f"{label}: {detail}")

    def ledger(*args) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            task_ledger.main(["--file", path, *args])

    tmp = tempfile.mkdtemp(prefix="stop_reminder_selftest_")
    try:
        path = os.path.join(tmp, ".claude", "TASKS.md")
        hook_in = json.dumps({"hook_event_name": "Stop", "cwd": tmp, "stop_hook_active": False})
        check("no-ledger-silent", run(hook_in) == "")
        ledger("add", "--ask", "Migrate the billing database")
        ledger("add", "--ask", "Write the onboarding guide")
        check("no-question-silent", run(hook_in) == "")
        ledger("defer", "--id", "T-001", "--question", "Drop the old table?", "--park")
        out = run(hook_in)
        try:
            obj = json.loads(out)
        except ValueError:
            obj = {}
        check("pending-plus-open-reminds", set(obj) == {"systemMessage"}, out)
        msg = obj.get("systemMessage", "")
        check("reminder-names-next-and-questions", "task_ledger.py next" in msg and "task_ledger.py questions" in msg, msg)
        check("reminder-names-non-gated-item", "T-002" in msg and "T-001" not in msg, msg)
        check("never-blocks-or-continues", not {"decision", "continue", "hookSpecificOutput"} & set(obj), out)
        check("file-arg-overrides-cwd", run("{}", path) == out, run("{}", path))
        check("bad-stdin-fails-open-to-silence", run("not json") == "")
        for event in ("UserPromptSubmit", "SessionStart"):
            ctx_out = run(json.dumps({"hook_event_name": event, "cwd": tmp}))
            try:
                ctx = json.loads(ctx_out)
            except ValueError:
                ctx = {}
            hso = ctx.get("hookSpecificOutput", {})
            check(f"turn-start-context[{event}]", set(ctx) == {"hookSpecificOutput"}
                  and hso.get("hookEventName") == event
                  and "pending deferred questions: 1" in hso.get("additionalContext", "")
                  and "next non-gated item: T-002" in hso.get("additionalContext", ""), ctx_out)
        check("other-event-silent", run(json.dumps({"hook_event_name": "PreToolUse", "cwd": tmp})) == "")
        check("stop-notice-is-owner-facing", "owner notice" in msg, msg)
        saved = task_ledger
        task_ledger = None
        try:
            check("missing-sibling-import-silent", run(hook_in) == "")
        finally:
            task_ledger = saved
        saved_run = run
        run = None  # calling it raises TypeError inside main
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                old_stdin = sys.stdin
                sys.stdin = io.StringIO(hook_in)
                try:
                    check("main-crash-exits-0", main([]) == 0)
                finally:
                    sys.stdin = old_stdin
        finally:
            run = saved_run
        check("odd-cwd-type-silent", run('{"cwd": 5}') == "")
        with contextlib.redirect_stderr(io.StringIO()):
            check("bad-cli-args-exit-0-not-2", main(["--bogus"]) == 0)
        ledger("block", "--id", "T-002", "--party", "vendor", "--evidence", "API key pending")
        check("pending-but-nothing-workable-silent", run(hook_in) == "")
        with open(os.path.join(tmp, ".claude", "QUESTIONS.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("garbage\n")
        check("malformed-questions-silent", run(hook_in) == "")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(hook_in)
            try:
                rc = main([])
            finally:
                sys.stdin = old_stdin
        check("main-always-exits-0", rc == 0 and buf.getvalue() == "", f"rc={rc} out={buf.getvalue()!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST OK: stop_reminder {ran[0]}/{ran[0]} cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
