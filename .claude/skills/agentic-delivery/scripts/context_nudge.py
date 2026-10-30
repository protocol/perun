#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=nudge a handoff at a huge context since long sessions re-read it every turn, review=2027-01-30
"""context_nudge.py — UserPromptSubmit hook: handoff nudge at a huge context, the host's own commands, a model-tier hint.

Long sessions re-read their whole context from cache on every turn, so cost grows with size. This hook reads the
hook JSON on stdin, takes the last assistant message's usage (input + cache_read + cache_creation tokens) from
`transcript_path` (Claude Code transcript format) as the current context size, and when it is at least
`PERUN_CONTEXT_NUDGE_TOKENS` (default 250000) prints (UserPromptSubmit stdout enters context) a line telling the agent
to update `.claude/handoff.md` with `focus_kit.py handoff set` (handoff_inject.py re-injects it after auto-compact on
Claude Code) and not to ask the owner to restart. A known host adds a second line with its own commands for compaction, a new chat, usage/cost, resume
and model/effort switching. It repeats only after another 50000 tokens of growth, tracked in a stamp under
`$XDG_CACHE_HOME/perun/context-nudge/` (default `~/.cache`).

HOST: read from env, never guessed. `PERUN_HOST` (claude-code, codex, gemini, copilot, cursor, opencode, qwen) wins;
else exactly one host's marker variable must be set (CLAUDECODE, GEMINI_CLI or GEMINI_SESSION_ID, CURSOR_VERSION,
QWEN_PROJECT_DIR). Codex CLI, Copilot CLI and OpenCode document no such variable, so set `PERUN_HOST` in their hook
config. No marker, or markers of several hosts, means unknown: the handoff line only, no commands. Each command was taken
from the vendor's docs on 2026-10-16 (docs/standards-index.md; Cursor's are the Cursor CLI's); a control the docs do not
show is not listed.

WORK KIND: a prompt that opens with a mechanical step (rebase, cleanup, apply a patch, a changelog fragment, a
done-sweep) or names a hard one (security review, threat model, P0, race condition, data integrity, design or
architecture decision, harness artifact) prints one line with the model tier and effort for it, taken from
references/model-tiering.md "Route delivery lanes by work type and stage", plus the host's switch command. It prints
only when that kind differs from the last one printed for the session (stamp `<session>.kind`); a prompt matching
neither changes nothing, so a follow-up never flips the advice back. On Claude Code a model switch re-reads the whole
context with no cache hits (docs/standards-index.md), so from 50000 tokens up the line says what the switch costs.

Output is at most two lines. Plain stdout is Claude Code's UserPromptSubmit contract; Gemini CLI hooks must print JSON
only, Copilot CLI drops `userPromptSubmitted` command-hook output and Cursor's `beforeSubmitPrompt` accepts only
`continue`/`user_message`, so on those hosts forward this text yourself. Silent otherwise; any error exits 0 silently;
only the last 1 MB of the transcript is read.

Run `context_nudge.py --selftest` to check it.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

STEP = 50_000
TAIL = 1 << 20

# Host key -> (name, marker env vars only that host sets, session commands, model/effort switch).
# Gemini CLI and Cursor document no effort control and Cursor no usage view, so none is listed.
HOSTS = {
    "claude-code": ("Claude Code", ("CLAUDECODE",),
                    "/compact summarize, /autocompact window, /clear new chat, /context size, /usage cost (alias /cost), /resume",
                    "/model, /effort"),
    "codex": ("Codex CLI", (), "/compact summarize, /clear or /new new chat, /status or /usage tokens, /resume",
              "/model (and reasoning effort, when available)"),
    "gemini": ("Gemini CLI", ("GEMINI_CLI", "GEMINI_SESSION_ID"),
               "/compress summarize, /clear new session, /stats usage, /resume", "/model; no effort command documented"),
    "copilot": ("Copilot CLI", (), "/compact summarize, /clear or /new new chat, /context size, /usage cost, /resume",
                "/model (model, reasoning effort or context window)"),
    "cursor": ("Cursor CLI", ("CURSOR_VERSION",), "/summarize summarize, /clear new chat, /resume",
               "/model; no effort command documented"),
    "opencode": ("OpenCode", (), "/compact summarize, /new new session, `opencode stats` in a shell for usage, /sessions resume",
                 "/models, ctrl+t cycles model variants"),
    "qwen": ("Qwen Code", ("QWEN_PROJECT_DIR",),
             "/compress summarize, /clear new chat, /context size, /stats usage, /resume", "/model, /effort"),
}

# Work kind -> (model tier, effort): the rows of references/model-tiering.md "Route delivery lanes by work type and stage".
TIERS = {"mechanical": ("cheapest", "low"), "build": ("mid", "medium"), "hard": ("top", "high")}
# ponytail: keyword rules on the prompt text; unkeyworded hard work is missed. Upgrade path: route by lane type when the host exposes it.
# First match wins. Mechanical counts only when the prompt opens with it, so "the rebase failed, debug it" stays build work.
RULES = (
    ("hard", re.compile(r"\b(?:security (?:re-?)?review|threat[- ]model|p0|race condition|data[- ]integrity"
                        r"|(?:design|architecture) decision|harness artifact)\b", re.I)),
    ("mechanical", re.compile(r"^\W*(?:please\s+)?(?:re-?base|clean ?up|apply (?:the |this |that )?patch"
                              r"|(?:add|write|draft) (?:a |the )?changelog|done[- ]sweep)\b", re.I)),
)


def detect_host(env=None):
    """The HOSTS key of the host running this hook, or None. `PERUN_HOST` wins (an unknown value means None); else exactly
    one host's marker variable must be set: none, or markers of several hosts, is None (skip rather than guess)."""
    env = os.environ if env is None else env
    pin = (env.get("PERUN_HOST") or "").strip().lower()
    if pin:
        return pin if pin in HOSTS else None
    hits = [k for k, h in HOSTS.items() if any(env.get(v) for v in h[1])]
    return hits[0] if len(hits) == 1 else None


def work_kind(prompt):
    """"hard", "mechanical", or None when the prompt names neither."""
    return next((k for k, rx in RULES if rx.search(str(prompt or ""))), None)


def kind_line(kind):
    """The tier/effort advice for a work kind (see TIERS), without any host command."""
    tier, effort = TIERS[kind]
    back = TIERS["build"][0]
    if kind == "hard":
        return f"Hard step: use the {tier}-tier model at {effort} effort, then switch back to the {back} tier."
    return f"Mechanical step: use the {tier} model at {effort} effort (fully specified steps only; judgment work stays on the {back} tier)."


def context_size(path):
    """Tokens in context at the last main-thread assistant message in the transcript, or None if there is none."""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - TAIL))
        lines = fh.read().decode("utf-8", "ignore").splitlines()
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
            u = e["message"]["usage"]
        except (ValueError, KeyError, TypeError):
            continue
        if e.get("type") == "assistant" and not e.get("isSidechain"):
            return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return None


def check(payload):
    """The hint (at most two lines) for this hook payload, or None. Writes the growth and work-kind stamps when it fires."""
    limit = int(os.environ.get("PERUN_CONTEXT_NUDGE_TOKENS") or 250_000)
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun" / "context-nudge"
    sid = str(payload.get("session_id") or "unknown").replace("/", "_")
    stamp, kstamp = root / sid, root / (sid + ".kind")
    key = detect_host()
    host = HOSTS.get(key)
    try:
        size = context_size(payload["transcript_path"])
    except (KeyError, TypeError, OSError):
        size = None  # the work-kind hint needs no transcript
    hot = False
    if size is not None:
        try:
            last = int(stamp.read_text())
        except (OSError, ValueError):
            last = 0
        if size < last:  # context shrank (/compact or /clear): restart the growth baseline
            root.mkdir(parents=True, exist_ok=True)
            stamp.write_text(str(size))
            last = size
        if size >= limit and size >= last + STEP:
            root.mkdir(parents=True, exist_ok=True)
            stamp.write_text(str(size))
            hot = True
    kind = work_kind(payload.get("prompt"))
    try:
        seen = kstamp.read_text()
    except OSError:
        seen = ""
    note = None
    if kind and kind != seen:
        root.mkdir(parents=True, exist_ok=True)
        kstamp.write_text(kind)
        note = kind_line(kind)
        if key == "claude-code" and size and size >= STEP:  # documented there: a model switch re-reads the context uncached
            note += f" A model switch now re-reads the {size // 1000}k-token context uncached."
    lines = []
    if hot:
        lines.append(f"Context is {size // 1000}k tokens and every turn re-reads it: update .claude/handoff.md now with "
                     f"`python3 {Path(__file__).resolve().with_name('focus_kit.py')} handoff set <section> <text>` (goal, stage, "
                     "next, in flight, blockers, decisions). " + ("Auto-compact then re-injects it; do not" if key == "claude-code" else "Do not")
                     + " tell the owner to restart the session.")
    if host and hot:
        tail = f"{host[0]} commands: {host[2]}; model and effort: {host[3]}."
    else:
        tail = f"{host[0]}: {host[3]}." if host and note else ""
    if note or tail:
        lines.append(" ".join(x for x in (note, tail) if x))
    return "\n".join(lines) or None


def main():
    try:
        line = check(json.load(sys.stdin))
    except Exception:
        return 0  # fail open
    if line:
        print(line)
    return 0


def _run(payload):
    real_in, real_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)), io.StringIO()
    try:
        rc = main()
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = real_in, real_out


def _selftest():
    tmp = tempfile.mkdtemp(prefix="ctx-nudge-")
    markers = [v for h in HOSTS.values() for v in h[1]]
    saved = {k: os.environ.get(k) for k in ("XDG_CACHE_HOME", "PERUN_CONTEXT_NUDGE_TOKENS", "PERUN_HOST", *markers)}
    os.environ["XDG_CACHE_HOME"] = tmp
    for k in ("PERUN_CONTEXT_NUDGE_TOKENS", "PERUN_HOST", *markers):
        os.environ.pop(k, None)
    tr = os.path.join(tmp, "t.jsonl")

    def write(n, tail=""):
        usage = {"input_tokens": 2, "cache_read_input_tokens": n - 2, "cache_creation_input_tokens": 0}
        with open(tr, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"usage": usage}}) + "\n" + tail)

    res = []
    try:
        pl = {"transcript_path": tr, "session_id": "s"}
        write(100_000)
        res.append(("silent-below-threshold", check(pl) is None))
        write(260_000, "garbage\n" + json.dumps({"type": "user"}) + "\n")
        line = check(pl) or ""
        res.append(("fires-over-threshold-skipping-junk-tail", "260k" in line))
        res.append(("nudge-names-the-handoff-updater", "focus_kit.py handoff set" in line))
        write(290_000)
        res.append(("silent-within-50k-growth", check(pl) is None))
        write(310_000)
        res.append(("fires-again-after-50k-growth", check(pl) is not None))
        write(80_000)
        res.append(("silent-after-compact", check(pl) is None))
        write(270_000)
        res.append(("fires-after-compact-regrowth", check(pl) is not None))
        os.environ["PERUN_CONTEXT_NUDGE_TOKENS"] = "1000"
        res.append(("env-threshold-other-session", check({"transcript_path": tr, "session_id": "t"}) is not None))
        res.append(("garbage-stdin-exit-0-silent", _run("not json") == (0, "")))
        res.append(("missing-transcript-exit-0-silent", _run({"transcript_path": tr + "x"}) == (0, "")))
        os.environ.pop("PERUN_CONTEXT_NUDGE_TOKENS")

        res.append(("unknown-host-is-none", detect_host({}) is None and detect_host({"PERUN_HOST": "bogus"}) is None))
        res.append(("marker-per-host", [detect_host({v: "1"}) for v in markers]
                    == [k for k, h in HOSTS.items() for _ in h[1]]))
        res.append(("pin-beats-markers", detect_host({"PERUN_HOST": " Codex ", "CLAUDECODE": "1"}) == "codex"))
        res.append(("two-hosts-markers-is-none", detect_host({"CLAUDECODE": "1", "CURSOR_VERSION": "1"}) is None))
        write(260_000)
        for i, (k, h) in enumerate(HOSTS.items()):
            os.environ["PERUN_HOST"] = k
            out = (check({"transcript_path": tr, "session_id": f"h{i}"}) or "").split("\n")
            res.append((f"host-{k}-two-lines-with-its-name", len(out) == 2 and out[1].startswith(h[0]) and h[3] in out[1]))
        os.environ["PERUN_HOST"] = "bogus"
        res.append(("unknown-host-handoff-line-only", len((check({"transcript_path": tr, "session_id": "u"}) or "").split("\n")) == 1))

        os.environ["PERUN_HOST"] = "claude-code"
        quiet = {"transcript_path": tr + "x", "session_id": "k"}  # no transcript: only the work-kind hint can fire
        res.append(("neutral-prompt-silent", check({**quiet, "prompt": "thanks, continue"}) is None))
        out = check({**quiet, "prompt": "Run a security review of the auth change"}) or ""
        res.append(("hard-prompt-top-tier-high-effort-host-commands",
                    out.count("\n") == 0 and "top-tier" in out and "high effort" in out and "/model, /effort" in out))
        res.append(("same-kind-silent", check({**quiet, "prompt": "another P0 data-integrity bug"}) is None))
        out = check({**quiet, "prompt": "Rebase onto main"}) or ""
        res.append(("kind-change-mechanical-cheapest-low", out.count("\n") == 0 and "cheapest" in out and "low effort" in out))
        res.append(("judgment-prompt-is-not-mechanical", work_kind("the rebase failed, debug it") is None))
        os.environ["PERUN_HOST"] = "bogus"
        out = check({**quiet, "prompt": "architecture decision for the queue"}) or ""
        res.append(("unknown-host-advice-without-commands", "top-tier" in out and "/" not in out))
        os.environ["PERUN_HOST"] = "gemini"
        out = check({"transcript_path": tr, "session_id": "both", "prompt": "threat model the upload path"}) or ""
        res.append(("threshold-plus-kind-still-two-lines", len(out.split("\n")) == 2 and "top-tier" in out.split("\n")[1]))
        for host, tokens, sid in (("claude-code", 100_000, "c1"), ("claude-code", 40_000, "c2"), ("gemini", 100_000, "c3")):
            write(tokens)
            os.environ["PERUN_HOST"] = host
            out = check({"transcript_path": tr, "session_id": sid, "prompt": "security review please"}) or ""
            res.append((f"switch-cost-clause-{sid}", ("re-reads the 100k-token context uncached" in out) == (sid == "c1") and bool(out)))
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(tmp, ignore_errors=True)
    for n, ok in res:
        print(f"{'PASS' if ok else 'FAIL'}  {n}")
    print(f"\nselftest: {sum(ok for _, ok in res)}/{len(res)} passed")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
