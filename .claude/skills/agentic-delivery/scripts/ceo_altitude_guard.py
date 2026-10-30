#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=keep the main session delegating instead of hand-editing source, review=2027-01-30
"""ceo_altitude_guard.py — PreToolUse + UserPromptSubmit hook: keep the MAIN session at CEO altitude.

WHY: the doctrine says the conductor specs, delegates and verifies while lanes type (agentic-ceo `references/full-map.md` **Stay strategic**;
roles.md "The Conductor self-executes under pressure"). As prose it did not hold: the main session kept hand-editing
source. This hook counts that drift (always, silently) and, when armed, warns or blocks.

WHO IS THE MAIN SESSION: the host puts `agent_id` in a hook's input only inside a subagent or an in-process teammate
(Claude Code hooks reference, fetched 2026-10-16, see docs/standards-index.md). No `agent_id` = main session; a call
with one is never counted, warned or blocked. `agent_type` cannot tell them apart: a main session started with
`--agent` carries it too. The docs never say outright that the main session omits `agent_id`; if that is wrong, every
call looks like a lane's and the guard goes silent. It can never block a lane. A separate top-level process that is
itself a lane (a `claude -p` worker, a peer session) also has no `agent_id`: start it with PERUN_ROLE=off.

ARMED BY: role `ceo` (warn) or `ceo-strict` (block): env PERUN_ROLE, else policy key `role` (`perun_policy.py set role
ceo`); the policy default is `off`, but install.sh with the operating layer applied writes `role: ceo` unless the policy
already has a role or PERUN_ROLE is set; an unreadable policy reads as `off` (fail open). Counting does not depend on the role, so
`operating_selfcheck.py` can show drift before and after arming.

WHAT IT FLAGS (main session, per turn = per `prompt_id`): under `ceo` the 2nd direct edit of a source file (EDIT_FREE) and the 4th
build/test command (HEAVY_FREE). A direct edit is an Edit/Write/MultiEdit/NotebookEdit of a file with a code extension
(CODE_EXT) or a Bash write to one (`> f.py`, `>> f.py`, `tee`, `sed -i`, `perl -i`). A build/test command is whatever
heavy_gate.py treats as heavy. Never flagged: reads, planning, git/gh/merge/release commands, tracker and MCP calls,
edits of docs, config, memory, handoff or changelog files (no code extension), and files under a temp or scratchpad dir.
`ceo` adds a `delegate: spawn a lane with the brief ...` line to the model's context and lets the call run;
`ceo-strict` denies it (JSON `permissionDecision`, exit 0, never exit 2).

STRICT = ZERO REPO EDITS: under `ceo-strict` the free edit allowance is 0 (EDIT_FREE applies to `ceo` only) and an edit is
ANY file under the project dir (CLAUDE_PROJECT_DIR, else the git toplevel of cwd, else cwd) whatever its extension: docs,
config, changelog fragments and handoffs included. Seen writes are the Edit/Write tools and shell redirect, tee,
`sed -i` and `perl -i`; KNOWN GAP: cp, mv, rm, touch, dd and an interpreter's own writes (`python -c`) are not caught. Files outside the project (memory, a temp or scratchpad dir) stay allowed. Build/test allowance
(HEAVY_FREE) is unchanged. Escapes: `ceo:off` in a prompt, PERUN_ROLE=off, or role `ceo` for the warn-only mode.

OWNER OVERRIDE: `ceo:off` in a user prompt lifts the flags until the next prompt. It is read at UserPromptSubmit, which
sees prompts, not tool calls, so the agent cannot grant it inside a tool call. This is a drift guard, not a security
boundary: an agent can still edit its policy or state file, or put the token in a prompt it schedules for itself.

Fail open: bad stdin, an unwritable state dir or a bad policy exits 0 with no output. UserPromptSubmit never prints
(stdout there becomes model context). A subagent's call exits before importing anything heavy: start-up is paid on every tool call.

Side effects: one JSON counter file per session under $PERUN_CEO_DIR (default <cache>/perun/ceo-altitude), updated
under flock so parallel tool calls count exactly; files untouched for PRUNE_DAYS are deleted when a new session starts.
Register as `python3 ".../ceo_altitude_guard.py" || true` on PreToolUse (Edit|Write|MultiEdit|NotebookEdit|Bash) and UserPromptSubmit.
"""
import fcntl
import importlib
import json
import os
import re
import subprocess
import sys
import time

# ponytail: an extension list, not a parser. Config/docs/data never count, and a Bash write from inside an
# interpreter (python -c, a heredoc'd script) is not seen; add detection if the selfcheck counter shows bypasses.
CODE_EXT = frozenset(".py .js .jsx .ts .tsx .mjs .cjs .go .rs .java .kt .rb .php .c .h .cc .cpp .hpp .cs .swift "
                     ".sh .bash .zsh .sql .css .scss .html .vue .svelte .ipynb".split())
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
REDIRECTS = frozenset((">", ">>", ">|", "&>", "&>>"))
IN_PLACE = re.compile(r"-[A-Za-z]*i.*|--in-place.*")  # sed/perl in-place flags: -i, -i.bak, -pi, -Ei, --in-place
OVERRIDE = re.compile(r"\bceo[:\s-]+off\b", re.I)
ARMED = ("ceo", "ceo-strict")
EDIT_FREE, HEAVY_FREE = 1, 3  # free per turn: a one-line fix is allowed, a loop is not; a lane's handback needs a check or three
PRUNE_DAYS = 30
FRESH = {"turn": "", "t_edits": 0, "t_heavy": 0, "override": False, "edits": 0, "heavy": 0, "warned": 0,
         "blocked": 0, "proj": "", "last": 0.0}

BRIEF = ('delegate: spawn a lane with the brief "<{what}>; DONE-gate: <{gate}>; one-line handback" '
         "(paste templates/lane-preamble.md). That is the main session's {noun} #{n} this turn (free: {free}); {why}")
WHAT = {"edit": ("what to change in {name}", "a test that fails before and passes after",
                 "direct source edit", "at CEO altitude you write the spec and the gate and verify the handback; lanes type."),
        "heavy": ("what to build or fix", "the command that must pass",
                  "build/test command", "verifying one handback is CEO work, iterating on builds and tests is a lane's.")}


def _sibling(name: str):
    """Import a sibling script on first use (heavy_gate, perun_policy): a lane's call never needs one, and python
    start-up is paid on every tool call."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    return importlib.import_module(name)


def state_dir() -> str:
    """Where the per-session counters live: $PERUN_CEO_DIR, else <cache>/perun/ceo-altitude (beside the heavy leases).
    Raises OSError when there is no absolute cache dir (HOME unset): a relative one would litter the project."""
    if os.environ.get("PERUN_CEO_DIR"):
        return os.environ["PERUN_CEO_DIR"]
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    if not os.path.isabs(base):
        raise OSError(f"no absolute cache dir ({base!r}): set HOME, XDG_CACHE_HOME or PERUN_CEO_DIR")
    return os.path.join(base, "perun", "ceo-altitude")


def role() -> str:
    """The armed role: env PERUN_ROLE (non-empty), else the policy `role`. Unreadable or unknown reads as off/unarmed."""
    perun_policy = _sibling("perun_policy")
    env = os.environ.get("PERUN_ROLE")
    if env:
        return perun_policy.norm_role(env)
    try:
        return perun_policy.load()["role"]
    except (ValueError, OSError):  # fail open here; perun_policy fails closed for its own readers
        return "off"


def _under(p: str, root: str) -> bool:
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def _project_root(cwd: str) -> str:
    """CLAUDE_PROJECT_DIR, else the git toplevel of `cwd`, else `cwd`."""
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.path.realpath(os.environ["CLAUDE_PROJECT_DIR"])
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return os.path.realpath(top or cwd)


def is_source(path: str, data: dict, strict: bool = False) -> bool:
    """True for a project source or test file: a code extension and not under a temp or scratchpad dir.
    The project dir wins when it sits inside a temp dir. `strict`: any file under the project dir counts, whatever its
    extension, and nothing outside it. `~` and `$VAR` are expanded; a path with an unresolved `$` is not a target
    (fail open). Symlinks are resolved, so a link out of the project is outside. Relative paths resolve against `cwd`."""
    path = os.path.expandvars(os.path.expanduser(path))
    if "$" in path or (not strict and os.path.splitext(path)[1].lower() not in CODE_EXT):
        return False
    cwd = data.get("cwd") or "."
    p = os.path.realpath(os.path.join(cwd, path))
    if _under(p, _project_root(cwd)):
        return True
    if strict:
        return False
    scratch = (os.path.realpath(r) for r in (data.get("scratchpad_dir"), os.environ.get("TMPDIR"), "/tmp") if r)
    return not any(_under(p, r) for r in scratch)


def write_targets(cmd: str) -> list:
    """Paths a Bash command visibly writes: redirect targets, `tee` args, and the file args of `sed -i` / `perl -i` (the
    script, the first non-flag arg or the -e/-f value, is not a file; is_source() filters the rest). Quoted text and heredoc bodies are not scanned; an
    unparsable command writes nothing."""
    heavy_gate = _sibling("heavy_gate")
    try:
        toks, segs = heavy_gate.tokens(cmd, "${}"), heavy_gate.segments(cmd, "${}")  # keep $VAR / ${VAR} in one word
    except ValueError:
        return []
    out = [b for a, b in zip(toks, toks[1:]) if a in REDIRECTS]
    for seg in map(heavy_gate.strip_wrappers, segs):
        if seg[:1] == ["tee"] or (seg[:1] in (["sed"], ["perl"]) and any(IN_PLACE.fullmatch(a) for a in seg[1:])):
            args, skip, script = [], False, seg[0] == "tee"  # tee has no script argument
            for a in seg[1:]:
                if skip:
                    skip = False
                elif a in ("-e", "-f", "--expression", "--file"):
                    skip, script = True, True
                elif a and not a.startswith("-"):
                    if script:
                        args.append(a)
                    script = True  # the first non-flag arg was the script
            out += args
    return out


def classify(data: dict, strict: bool = False):
    """`("edit", path)` for a direct source edit (any in-project file when `strict`), `("heavy", "")` for a build/test
    command, else None."""
    tool, ti = data.get("tool_name"), data.get("tool_input") or {}
    if tool in EDIT_TOOLS:
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        return ("edit", path) if is_source(path, data, strict) else None
    if tool == "Bash":
        cmd = str(ti.get("command") or "")
        hit = next((t for t in write_targets(cmd) if is_source(t, data, strict)), None)
        if hit:
            return "edit", hit
        heavy_gate = _sibling("heavy_gate")
        if heavy_gate.is_heavy(cmd, heavy_gate.heavy_patterns()):
            return "heavy", ""
    return None


def _update(data: dict, fn):
    """Run `fn(state)` under an exclusive flock on this session's counter file, persist the state, return fn's result."""
    d = state_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, (re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or "")) or "unknown") + ".json")
    new = not os.path.exists(path)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            st = json.loads(f.read() or "{}")
        except ValueError:  # a torn write from a crashed hook: start the session's counters over
            st = {}
        st = {**FRESH, **(st if isinstance(st, dict) else {})}
        st["proj"] = st["proj"] or os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
        out = fn(st)
        st["last"] = time.time()
        f.seek(0)
        f.truncate()
        f.write(json.dumps(st))
    if new:
        for name in os.listdir(d):
            old = os.path.join(d, name)
            try:
                if name.endswith(".json") and time.time() - os.stat(old).st_mtime > PRUNE_DAYS * 86400:
                    os.unlink(old)
            except OSError:
                pass
    return out


def _tally(st: dict, data: dict, kind: str, path: str, mode: str):
    """Count one main-session action in `st` and return the hook output for it (None = silent). A blocked call
    is counted in `blocked` only: it did not happen, so it does not use up the turn's free allowance."""
    pid = str(data.get("prompt_id") or "")
    if pid != st["turn"]:  # a new user prompt = a new turn (UserPromptSubmit also resets this)
        st.update(turn=pid, t_edits=0, t_heavy=0)
    key, free = ("t_edits", 0 if mode == "ceo-strict" else EDIT_FREE) if kind == "edit" else ("t_heavy", HEAVY_FREE)
    n = st[key] + 1
    flagged = mode in ARMED and not st["override"] and n > free
    what, gate, noun, why = WHAT[kind]
    text = BRIEF.format(what=what.format(name=os.path.basename(path) or "the file"), gate=gate, noun=noun, n=n, free=free, why=why)
    if flagged and mode == "ceo-strict":
        st["blocked"] += 1
        return {"permissionDecision": "deny",
                "permissionDecisionReason": "BLOCKED (role=ceo-strict): " + text + " The owner can lift this with ceo:off in a prompt."}
    st[key] = n
    st["edits" if kind == "edit" else "heavy"] += 1
    if flagged:
        st["warned"] += 1
        return {"additionalContext": text}
    return None


def handle(data: dict):
    """Process one hook payload; returns the `hookSpecificOutput` dict to print, or None for silence."""
    if data.get("agent_id"):
        return None  # a subagent or teammate: never counted, never flagged
    if data.get("hook_event_name") == "UserPromptSubmit":
        _update(data, lambda st: st.update(override=bool(OVERRIDE.search(str(data.get("prompt") or ""))),
                                           turn=str(data.get("prompt_id") or ""), t_edits=0, t_heavy=0))
        return None
    mode = role()
    hit = classify(data, mode == "ceo-strict")
    if hit is None:
        return None
    out = _update(data, lambda st: _tally(st, data, *hit, mode))
    return out and {"hookEventName": "PreToolUse", **out}


def main() -> int:
    try:
        out = handle(json.load(sys.stdin))
    except Exception:  # fail open: a broken guard must never block work
        return 0
    if out:
        print(json.dumps({"hookSpecificOutput": out}))
    return 0


def sessions(project: str = ".") -> list:
    """`[(session_id, state)]` for the recorded main sessions of `project`, newest first. Unreadable files are skipped."""
    root, d, out = os.path.realpath(project), state_dir(), []
    for name in os.listdir(d) if os.path.isdir(d) else ():
        try:
            with open(os.path.join(d, name)) as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if name.endswith(".json") and isinstance(st, dict) and st.get("proj") == root:
            out.append((name[:-5], {**FRESH, **st}))
    return sorted(out, key=lambda s: s[1]["last"], reverse=True)


def report_lines(project: str = ".", limit: int = 5) -> list:
    """The lines operating_selfcheck.py prints: the role, and direct source edits per recorded main session (newest `limit`)."""
    sess, mode = sessions(project), role()
    arm = "" if mode in ARMED else "; arm it: perun_policy.py set role ceo"
    lines = [f"ceo-altitude: role={mode}; {len(sess)} main session(s) recorded, "
             f"{sum(s['edits'] for _, s in sess)} direct source edit(s) in all{arm}"]
    for sid, s in sess[:limit]:
        lines.append(f"ceo-altitude-session {sid[:8]}: {s['edits']} direct source edit(s), {s['heavy']} build/test command(s), "
                     f"warned {s['warned']}, blocked {s['blocked']}, last {time.strftime('%Y-%m-%d', time.localtime(s['last']))}")
    return lines


if __name__ == "__main__":
    sys.exit(main())
