#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=ask the owner only after a recorded evil-twin and council pass, review=2027-01-30
"""decision_gate.py — gate: ask the owner only after a decision record.

Owner rule: before a question or plan reaches the owner, run an evil-twin attack and a council pass and record both.
This gate checks that a record EXISTS and is recent. It does not judge the reasoning; a record is a claim the owner can
audit, not proof of quality. It never gates Bash, Edit or merges.

A record is a `*.md` file in the decision dir (`PERUN_DECISION_DIR`, else `$CLAUDE_PROJECT_DIR/.perun/decisions`, else
`./.perun/decisions`: project-local so the Write tool can create it under sandbox or plan mode; keep `.perun/` git-ignored),
modified within `PERUN_DECISION_MAX_MIN` minutes (30), holding two lines (idea-critic's verdict values):
    evil_twin: HOLD|REVISE|PASS_TO_USER <one-line reason>
    council: HOLD|REVISE|PASS_TO_USER <one-line reason>
The default dir gets a self-ignoring `.perun/.gitignore` (`*`) when the gate runs. For ExitPlanMode the two lines may
instead sit inside the plan text (`tool_input.plan`), since plan mode can deny the Write.
PreToolUse (default event): missing, stale or malformed record: exit 2 with the block message below (fails closed, also
on unparseable stdin).
Stop event (same file, argument `stop`, same record): the FINAL sentence of the reply, if it asks the owner to decide
(a trailing question mark, "should I", "want me to", "which one", "please decide" and similar; fenced and quoted text
ignored; the same phrases earlier in the text are not matched), is blocked once per turn unless a recent record
exists. Fails open on unparseable input and honors `stop_hook_active`. Message: run evil twin + council, decide
yourself unless hard-gated (irreversible, spend, external, permission); a record may add a `hard_gated: <why>` line.
A phrase list, not a classifier: a miss lets the reply through.
Escape for the owner: `PERUN_DECISION_GATE=off` in the environment. Side effects: none. Tests: `--selftest`.
"""
import json
import os
import re
import sys
import tempfile
import time

MAX_MIN = float(os.environ.get("PERUN_DECISION_MAX_MIN", "30"))
GATED = ("AskUserQuestion", "ExitPlanMode")
ASK = re.compile(r"\b(?:should i|shall i|want me to|do you want|would you like|which (?:one|option|approach|do you)|"
                 r"please (?:decide|choose|approve|confirm)|(?:need|needs|awaiting) (?:your|owner) (?:decision|approval)|your call)\b|\?\s*$", re.I)
QUOTED = re.compile(r"(?s:```.*?(?:```|\Z))|`[^`\n]*`|^[ \t]*>[^\n]*", re.M)
STOP_MSG = ("Run evil twin + council; decide yourself unless hard-gated (irreversible, spend, external, permission). "
            "Your reply asks the owner to decide and no decision record from the last {m:g} minutes exists. Use the Write tool to create {d}/decision.md with "
            "`evil_twin: HOLD|REVISE|PASS_TO_USER <reason>` and `council: HOLD|REVISE|PASS_TO_USER <reason>` (plus `hard_gated: <why>` if it is), "
            "then reply with the decision made, or the one hard-gated question. The gate checks the record exists, not its quality.")
LINE = r"^[ \t]*{}:[ \t]*(HOLD|REVISE|PASS_TO_USER)\b"


def decision_dir():
    return os.environ.get("PERUN_DECISION_DIR") or os.path.join(
        os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), ".perun", "decisions")


def final_sentence(text):
    """Last sentence of the last non-empty line: the part that is addressed to the owner."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return re.split(r"(?<=[.!?])\s+", lines[-1].strip())[-1] if lines else ""


def has_lines(t):
    return all(re.search(LINE.format(k), t, re.M | re.I) for k in ("evil_twin", "council"))


def ensure_ignored(d):
    """Make the default project-local dir self-ignoring (`.perun/.gitignore` = `*`): no repo edit, no untracked noise."""
    if os.environ.get("PERUN_DECISION_DIR"):
        return
    try:
        root = os.path.dirname(d)
        os.makedirs(d, exist_ok=True)
        g = os.path.join(root, ".gitignore")
        if not os.path.exists(g):
            open(g, "w").write("*\n")
    except OSError:
        pass


def has_record(now=None):
    d, now = decision_dir(), now or time.time()
    ensure_ignored(d)
    try:
        names = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md")]
    except OSError:
        return False
    for p in names:
        try:
            if now - os.path.getmtime(p) > MAX_MIN * 60:
                continue
            t = open(p, errors="ignore").read()
        except OSError:
            continue
        if has_lines(t):
            return True
    return False


def block_message():
    return (f"Blocked: no decision record from the last {MAX_MIN:g} minutes. Before asking the owner or presenting a plan, "
            "run an evil-twin attack (skeptic, better-way, kill-criteria; see the idea-critic skill) and a council pass, "
            f"then use the Write tool to create {os.path.join(decision_dir(), 'decision.md')} (any .md name; the Write tool makes the dir) with two lines: "
            "`evil_twin: HOLD|REVISE|PASS_TO_USER <reason>` and `council: HOLD|REVISE|PASS_TO_USER <reason>`. "
            "For ExitPlanMode you may instead put the same two lines inside the plan text itself (plan mode can deny the Write). Then retry. Decide it yourself if neither verdict needs the owner. The gate checks the record exists, not its quality.")


def stop(data):
    """Exit 2 when the final reply asks the owner to decide and no recent record exists. Fails open (a Stop hook must not trap a session)."""
    try:
        if data.get("stop_hook_active"):
            return 0
        reply = data.get("last_assistant_message") or ""
        p = data.get("transcript_path")
        if not reply and p and os.path.exists(p):
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from reply_cap import last_texts
            reply = last_texts(p)[0]
        if not ASK.search(final_sentence(QUOTED.sub("", reply))) or has_record():
            return 0
    except Exception:
        return 0
    print(STOP_MSG.format(m=MAX_MIN, d=decision_dir()), file=sys.stderr)
    return 2


def main():
    if os.environ.get("PERUN_DECISION_GATE", "").lower() == "off":
        return 0
    is_stop = "stop" in sys.argv[1:]
    try:
        data = json.load(sys.stdin)
        data = data if isinstance(data, dict) else {}
    except Exception:
        if is_stop:
            return 0  # a Stop hook must not trap a session on garbage input
        data = {}  # PreToolUse: unparseable input fails closed (treated as a gated tool call)
    if is_stop or data.get("hook_event_name") == "Stop":
        return stop(data)
    tool = data.get("tool_name", GATED[0])
    plan = (data.get("tool_input") or {}).get("plan") if tool == "ExitPlanMode" else None
    if tool not in GATED or (isinstance(plan, str) and has_lines(plan)) or has_record():
        return 0
    print(block_message(), file=sys.stderr)
    return 2


def _selftest():
    import subprocess
    tmp = tempfile.mkdtemp(prefix="decision-gate-")
    env = {**os.environ, "PERUN_DECISION_DIR": os.path.join(tmp, "d")}
    env.pop("PERUN_DECISION_GATE", None)

    def run(tool, e=env):
        r = subprocess.run([sys.executable, __file__], input=json.dumps({"tool_name": tool}), capture_output=True, text=True, env=e)
        return r.returncode, r.stderr

    def rec(name, body, age_min=0):
        os.makedirs(env["PERUN_DECISION_DIR"], exist_ok=True)
        p = os.path.join(env["PERUN_DECISION_DIR"], name)
        open(p, "w").write(body)
        os.utime(p, (time.time() - age_min * 60,) * 2)
    good = "claim: x\nevil_twin: REVISE use the cheaper path\ncouncil: PASS_TO_USER 3 of 3 agree\n"
    res = []
    c, m = run("AskUserQuestion")
    res.append(("no-dir-blocks-with-how-to", c == 2 and "evil_twin:" in m and "council:" in m and "idea-critic" in m))
    res.append(("exit-plan-mode-also-gated", run("ExitPlanMode")[0] == 2))
    res.append(("bash-and-edit-never-gated", run("Bash")[0] == 0 and run("Edit")[0] == 0))
    rec("a.md", "evil_twin: HOLD no\n")
    res.append(("half-record-blocks", run("AskUserQuestion")[0] == 2))
    rec("a.md", good, age_min=31)
    res.append(("stale-record-blocks", run("AskUserQuestion")[0] == 2))
    rec("a.md", good, age_min=29)
    res.append(("recent-record-allows", run("AskUserQuestion")[0] == 0 and run("ExitPlanMode")[0] == 0))
    rec("a.md", "evil_twin: MAYBE\ncouncil: PASS_TO_USER\n")
    res.append(("bad-verdict-blocks", run("AskUserQuestion")[0] == 2))
    rec("a.md", good)
    res.append(("off-allows", run("AskUserQuestion", {**env, "PERUN_DECISION_GATE": "off"})[0] == 0))
    def stop_run(reply, e=env, **extra):
        r = subprocess.run([sys.executable, __file__], capture_output=True, text=True, env=e,
                           input=json.dumps({"hook_event_name": "Stop", "last_assistant_message": reply, **extra}))
        return r.returncode, r.stderr
    os.remove(os.path.join(env["PERUN_DECISION_DIR"], "a.md"))
    c, m = stop_run("Two options exist.\nShould I use the cache or the queue?")
    res.append(("stop-ask-blocks-with-message", c == 2 and "Run evil twin + council; decide yourself unless hard-gated" in m))
    res.append(("stop-want-me-to-blocks", stop_run("Done with A. Want me to start B")[0] == 2))
    res.append(("stop-plain-report-allowed", stop_run("Merged PR 12. Tests 9/9.")[0] == 0))
    res.append(("stop-quoted-question-ignored", stop_run("Fixed.\n> should I?\n`which one?`\nDone.")[0] == 0))
    res.append(("stop-hook-active-allows", stop_run("Should I?", stop_hook_active=True)[0] == 0))
    rec("b.md", good)
    res.append(("stop-ask-with-record-allowed", stop_run("Should I use the cache?")[0] == 0))
    res.append(("stop-off-switch", stop_run("Should I?", {**env, "PERUN_DECISION_GATE": "off", "PERUN_DECISION_DIR": tmp + "/none"})[0] == 0))
    none = {**env, "PERUN_DECISION_DIR": tmp + "/none"}
    r = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True, env=none)
    res.append(("garbage-stdin-pretooluse-fails-closed", r.returncode == 2))
    r = subprocess.run([sys.executable, __file__, "stop"], input="not json", capture_output=True, text=True, env=none)
    res.append(("garbage-stdin-stop-fails-open", r.returncode == 0))
    r = subprocess.run([sys.executable, __file__, "stop"], capture_output=True, text=True, env=none,
                       input=json.dumps({"last_assistant_message": "Done. Should I start B?"}))
    res.append(("argv-stop-without-event-name-blocks", r.returncode == 2))
    res.append(("stop-which-one-midtext-allowed", stop_run("Which one did I pick? Picked A.\nMerged.", none)[0] == 0))
    res.append(("stop-your-call-midtext-allowed", stop_run("Your call on naming was right. Merged PR 4.", none)[0] == 0))
    res.append(("stop-final-which-one-blocks", stop_run("Two paths.\nWhich one do you prefer", none)[0] == 2))
    pd = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(pd, ".perun", "decisions"))
    open(os.path.join(pd, ".perun", "decisions", "x.md"), "w").write(good)
    pe = {k: v for k, v in env.items() if k != "PERUN_DECISION_DIR"}
    res.append(("project-local-record-allows", run("AskUserQuestion", {**pe, "CLAUDE_PROJECT_DIR": pd})[0] == 0))
    c, m = run("AskUserQuestion", {**pe, "CLAUDE_PROJECT_DIR": tmp + "/empty"})
    res.append(("block-self-ignores-dir", open(os.path.join(tmp, "empty", ".perun", ".gitignore")).read() == "*\n"))
    plan_ok = "# Plan\nevil_twin: REVISE x\ncouncil: PASS_TO_USER y\n"
    def plan_run(tool, plan):
        r = subprocess.run([sys.executable, __file__], capture_output=True, text=True, env={**pe, "CLAUDE_PROJECT_DIR": tmp + "/empty"},
                           input=json.dumps({"tool_name": tool, "tool_input": {"plan": plan}}))
        return r.returncode, r.stderr
    res.append(("plan-text-record-allows-exitplanmode", plan_run("ExitPlanMode", plan_ok)[0] == 0))
    res.append(("plan-text-half-record-blocks", plan_run("ExitPlanMode", "evil_twin: HOLD x\n")[0] == 2))
    res.append(("plan-text-not-accepted-for-askuserquestion", plan_run("AskUserQuestion", plan_ok)[0] == 2))
    res.append(("block-says-plan-text-works", "inside the plan text" in plan_run("ExitPlanMode", "x")[1]))
    res.append(("block-names-exact-path", c == 2 and os.path.join(tmp, "empty", ".perun", "decisions", "decision.md") in m))
    for name, ok in res:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"selftest: {sum(ok for _, ok in res)}/{len(res)} passed")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
