#!/usr/bin/env python3
"""SubagentStop hook: cap a subagent handback, log how far it is from fields-only, and audit each lane's prose.

Caps CHAT NARRATION only — a subagent's final chat message to its caller.
Deliverables (code, reports, long findings) belong in FILES, which are
uncapped by this hook; a compliant handback names the file path instead of
pasting its content into chat. Blocks (exit 2) a message longer than
MAX_CHARS or MAX_LINES (defaults 800 characters / 10 lines, the legacy cap);
stderr carries the rewrite instruction. Per the
official docs (https://code.claude.com/docs/en/hooks, "Exit code 2 behavior
per event"), exit code 2 on SubagentStop "prevents the subagent from
stopping, continues the subagent" — so a block does not lose the subagent's
work, it sends the same turn back to compose a shorter handback.

FIELDS-ONLY TARGET (log only, NEVER blocks). A rewrite costs the lane one more
turn that re-reads its whole context, more than a shorter handback saves, so a
miss is recorded, not sent back. The target is TARGET_CHARS / TARGET_LINES
(defaults 400 / 8; HANDBACK_TARGET_CHARS, HANDBACK_TARGET_LINES) and, unless
HANDBACK_FIELDS_ONLY=0, every non-blank line a field: `key=value` (`sha=1a2b3c`;
`key: value` and a leading `- ` also pass), the older `status | evidence | next`
list, or one bare token (`VERIFIED`). A sentence is prose. The ledger row gets
`viol` (`long`, `prose`) and `cut_tok`, the estimated tokens a truncation to the
field lines within the target would drop; the hook cannot rewrite what the
caller receives, so delivery is not altered. This is a SHAPE check, not a
semantic one. The lever is the SubagentStart rule (subagent_start_inject.py).

WHAT COUNTS. Fenced code blocks (the fence lines included) and lines that start
with `! ` (a command the owner copies and runs with the host's `!` prefix) are
not counted toward MAX_CHARS or MAX_LINES, so a copy-paste command for the user
never forces a rewrite. To keep a long deliverable from hiding in a fence, the
whole message (those lines included) may not pass COPY_FACTOR (5) times
MAX_CHARS; past that it is blocked like any over-long handback, and the fix is
the same: put it in a file. An unclosed fence hides the rest of the message
from the line and char counts, and only that total limit then applies.

EXEMPTION IS A NAME LIST, NOT A TOOL CHECK. A subagent is exempt (never
capped, at any length) iff its `agent_type` is listed in the comma-separated
HANDBACK_EXEMPT_TYPES env var. The default list is four built-in agent types
whose chat answer is itself the deliverable: `Explore`, `Plan`,
`claude-code-guide`, `statusline-setup`. This hook does NOT inspect an
agent's tools — it cannot tell whether a type has a Write tool. Do NOT add a
custom read-only review lane's type here: exempt means uncapped, which
reopens the cost problem on a harness with no report file. Instead raise
MAX_CHARS/MAX_LINES for that type only via a
matcher-scoped SubagentStop entry, and scope the default entry so it does not
also match that type (agentic-delivery/references/host-enforcement.md).
Setting HANDBACK_EXEMPT_TYPES REPLACES the default list, so repeat the
defaults you still want.

After MAX_BLOCKS (3) blocks for one agent_id, this hook lets the stop through
unconditionally, so a subagent that cannot comply never loops forever. Block
counters live in per-agent_id state files under a temp dir (sanitized id;
directory overridable via HANDBACK_STATE_DIR, e.g. for isolated tests).

STATUS TOKEN (opt-in: HANDBACK_REQUIRE_STATUS=1). When on, a non-exempt
handback must also carry a status: a line that starts (case-insensitive,
optionally after `status=` or `status:`) with `verified` or `unverified` as a
whole word, or the host style `status | evidence | next` whose status field
is `done`, `verified`, or `unverified`. The caller counts only verified work
as done; a lane stopped by its tool-call cap (lane_cap.py) hands back
UNVERIFIED with the remaining work. A handback with no status is blocked like
an over-long one (same MAX_BLOCKS release valve). Off by default so an
existing install's handbacks are not suddenly rejected; exempt types always
skip it.

BACKGROUND WORK (policy `background_guard`: `off|warn|block`, default `warn`; env PERUN_BACKGROUND_GUARD overrides). A lane
owns its background jobs until they exit. When the lane's cwd is inside a LINKED worktree and a test or build runner
(BG_RE: pytest, jest, vitest, playwright, make, `npm test`, `cargo test`, `go build`, a `*test*.py|sh` script, ...) has its
cwd inside that worktree, `warn` sends the owner a `systemMessage` naming the pid and command, and `block` exits 2 with the
same text on stderr (released after PUSH_MAX_S, like a live push). Dev servers are not matched. The scan reuses
lane_liveness.cwd_pids (lsof, else /proc) plus one `ps`, excludes this hook's own pid, ancestors and descendants, and
fails open: a blind scan prints COULD_NOT_CHECK and never blocks. A non-worktree cwd (a shared checkout) is not scanned.

LANE AUDIT (default on). Whenever the stop is allowed (also for exempt types,
flagged `exempt`), one JSON line per lane is appended to a local ledger so
prose waste is measurable: the lane's assistant TEXT tokens (`narr_tok`
between tool calls, `final_tok` the handback, `text_tok` their sum) against
its tool-call tokens (`tool_tok`, name plus input JSON), plus `calls`,
`fields_ok` (the handback passed the fields-only shape), `viol`/`cut_tok` (see
FIELDS-ONLY TARGET), `blocks` (legacy-cap rewrites this hook forced) and `cpt` (characters per token used). Every token figure is
an ESTIMATE, characters / CPT (4, a rule of thumb: no tokenizer is available
offline). The transcript's own `usage.output_tokens` is not used: on 60 real
lane transcripts it summed to 157k against 461k estimated from the content
(cause unverified), so it would understate. The ledger holds only counts and
the agent type and id, never transcript content.
  Input: the hook's `agent_transcript_path`, the SUBAGENT's own JSONL transcript
  (hooks docs: SubagentStop). `transcript_path` is the PARENT session's file and
  is never read; when `agent_transcript_path` is absent the documented nested
  `<session>/subagents/agent-<agent_id>.jsonl` beside it is derived. The docs
  also say the file is written asynchronously and may lag, so the final message
  comes from `last_assistant_message` (or the lane's last `SubagentHandback`
  tool call) and is excluded from `narr_tok` when the transcript already holds it.
  Format: the docs say a transcript line is a JSON object for a message, tool
  use or metadata entry and that the entry format is internal and changes
  between versions (https://code.claude.com/docs/en/sessions). The parser reads
  only `type == "assistant"` entries whose `message.content` blocks are
  `text` / `tool_use` (as observed 2026-10-16) and skips anything else; a file
  with no parsable assistant entry is `COULD_NOT_CHECK` (stderr, no ledger line),
  never a row of zeros. The audit never blocks and never raises.
  Ledger: HANDBACK_AUDIT_LEDGER (a path; empty or `off` disables), else
  `$XDG_CACHE_HOME/perun/lane-audit.jsonl` (default `~/.cache`, the same root as
  perun_policy's heavy leases). One line per agent_id (first stop wins).
  Read it back with `handback_cap.py --report [LEDGER]` (medians, p90, totals);
  `handback_cap.py --scan PATH... [--since-days N]` audits existing transcripts
  (files, or directories searched for `subagents/agent-*.jsonl`) without
  writing the ledger. Both print aggregates only, never content.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

MAX_CHARS = int(os.environ.get("HANDBACK_MAX_CHARS", "800"))  # the only BLOCKING cap (legacy, unchanged)
MAX_LINES = int(os.environ.get("HANDBACK_MAX_LINES", "10"))
MAX_BLOCKS = 3
# Soft target a handback should meet: never blocks, only logged (a rewrite re-reads the lane's whole context).
TARGET_CHARS = int(os.environ.get("HANDBACK_TARGET_CHARS", "400"))
TARGET_LINES = int(os.environ.get("HANDBACK_TARGET_LINES", "8"))
CPT = 4  # characters per token for the audit's ESTIMATE; recorded in every ledger row
COPY_FACTOR = 5  # whole message, fenced code and `! ` lines included, may be at most this many times MAX_CHARS
# Default exempt agent-type NAMES (chat IS their deliverable). Matched by name
# only; override/extend via HANDBACK_EXEMPT_TYPES (replaces this list).
DEFAULT_EXEMPT_TYPES = "Explore,Plan,claude-code-guide,statusline-setup"
STATE_DIR = os.environ.get(
    "HANDBACK_STATE_DIR", os.path.join(tempfile.gettempdir(), "claude-handback-cap")
)


STATUS_RE = re.compile(
    r"^\W*(?:status\s*[=:]\s*)?(?:(?:un)?verified\b|done\s*\|)", re.MULTILINE | re.IGNORECASE
)
# One handback line is a field, never prose: `key=value` (or `key: value`, optionally bulleted), a
# `status | evidence | next` list, or one bare token. A sentence starts with a word that is none of these.
FIELD_RE = re.compile(r"(?:[-*]\s+)?[A-Za-z][\w.-]*\s*[=:]\s*\S.*|[^|]+(?:\|[^|]+)+|\S+")


def _require_status():
    return os.environ.get("HANDBACK_REQUIRE_STATUS", "0") == "1"


def _fields_only():
    return os.environ.get("HANDBACK_FIELDS_ONLY", "1") != "0"


def _prose_lines(msg):
    """1-based numbers of the non-blank lines of `msg` that are not fields (see FIELD_RE)."""
    return [i for i, ln in enumerate(msg.splitlines(), 1) if ln.strip() and not FIELD_RE.fullmatch(ln.strip())]


def _shape(msg):
    """`(chars, lines, too_long)`: `too_long` is the BLOCKING cap (MAX_CHARS / MAX_LINES over the counted lines,
    see _counted; the whole message may not pass MAX_CHARS * COPY_FACTOR)."""
    kept = _counted(msg) if msg else []
    chars, lines = len("\n".join(kept)), len(kept)
    return chars, lines, chars > MAX_CHARS or lines > MAX_LINES or len(msg) > MAX_CHARS * COPY_FACTOR


def _violations(msg):
    """Soft violations of the target shape, logged never blocked: `long` (over TARGET_*) and, with fields-only on,
    `prose` (a non-field line). Empty list = within target."""
    chars, lines = len(msg), msg.count("\n") + 1 if msg else 0
    v = ["long"] if chars > TARGET_CHARS or lines > TARGET_LINES else []
    return v + (["prose"] if _fields_only() and _prose_lines(msg) else [])


def _truncate(msg):
    """The handback cut to its field lines within the target. The hook cannot rewrite what the caller receives, so
    this only measures what a truncation would drop (`cut_tok`)."""
    keep = [ln for ln in msg.splitlines() if ln.strip() and FIELD_RE.fullmatch(ln.strip())][:TARGET_LINES]
    return "\n".join(keep)[:TARGET_CHARS]


def _exempt_types():
    return set(filter(None, os.environ.get("HANDBACK_EXEMPT_TYPES", DEFAULT_EXEMPT_TYPES).split(",")))


def _state_path(agent_id):
    safe = "".join(c for c in agent_id if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(STATE_DIR, safe)


def _read_blocks(path):
    try:
        with open(path) as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0


# `git [-c k=v] [-C dir | -C "dir w/ space"] [--opt] push`; group 2/3 = the -C dir (quoted or bare)
PUSH_RE = re.compile(r"""\bgit\b((?:\s+-C\s+(?:"([^"]*)"|'([^']*)'|(\S+))|\s+-c\s+\S+|\s+-\S+)*)\s+push\b""")
PUSH_MAX_S = int(os.environ.get("HANDBACK_PUSH_MAX_S", "1800"))  # keep blocking while the push is live, at most this long


def _inside(p, root):
    p = os.path.realpath(p)
    return p == root or p.startswith(root.rstrip("/") + "/")


def _push_running(cwd):
    """True/False: is a `git push` (also `git -C <dir> push`) live with its cwd or -C dir inside `cwd`?
    None = could not check (no cwd, ps/lsof denied or failed): the hook stays advisory and fails open, but says so."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        root = os.path.realpath(cwd)
        for ln in r.stdout.splitlines():
            pid, _, cmd = ln.strip().partition(" ")
            m = PUSH_RE.search(cmd)
            if not m or not pid.isdigit() or int(pid) == os.getpid():
                continue
            cdir = m.group(2) or m.group(3) or m.group(4)
            if cdir and _inside(cdir, root):
                return True
            out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True, text=True, timeout=10)
            if out.returncode > 1:
                return None
            if any(n.startswith("n") and _inside(n[1:], root) for n in out.stdout.splitlines()):
                return True
        return False
    except (OSError, subprocess.SubprocessError):
        return None


# A test or build runner (not a dev server: those are long-lived by design and `lane_guard.py wait` owns them).
BG_RE = re.compile(
    r"(?<![\w.-])(?:pytest|jest|vitest|playwright|cypress|mocha|tox|nox|ctest|tsc|webpack|make|gradle|mvn|bazel"
    r"|cargo\s+(?:test|build|check|nextest)|go\s+(?:test|build)|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build)"
    r"|(?:python3?\s+-m\s+)?unittest|[^/\s]*test[^/\s]*\.(?:py|sh))(?![\w-])")  # *test*.py|sh: basename only


def _bg_mode():
    """off|warn|block: env PERUN_BACKGROUND_GUARD, else policy `background_guard`, else warn. Fails open to warn."""
    env = os.environ.get("PERUN_BACKGROUND_GUARD", "").strip().lower()
    if env in ("off", "warn", "block"):
        return env
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        mode = perun_policy.load().get("background_guard")
    except Exception:
        mode = None
    return mode if mode in ("off", "warn", "block") else "warn"


def _ps_table(text):
    """pid -> (ppid, command) from `ps -axo pid=,ppid=,command=` output (macOS and Linux); malformed lines are skipped."""
    rows = (ln.split(None, 2) for ln in text.splitlines())
    return {int(a): (int(b), c) for a, b, c in (r for r in rows if len(r) == 3) if a.isdigit() and b.isdigit()}


def _bg_found(table, pids, me):
    """[(pid, command)] of test/build processes among `pids`. `table` maps pid -> (ppid, command). Never counts `me`,
    its ancestors (the host that runs this hook) or its descendants (the ps/lsof it spawned)."""
    skip, p = {me}, me
    while p in table and table[p][0] > 1 and table[p][0] not in skip:
        p = table[p][0]
        skip.add(p)
    kids = {me}
    while True:
        more = {q for q, (pp, _) in table.items() if pp in kids} - kids
        if not more:
            break
        kids |= more
    skip |= kids
    return sorted((p, table[p][1]) for p in pids if p in table and p not in skip and BG_RE.search(table[p][1]))


def _bg_running(cwd):
    """[(pid, command)] of test/build processes whose cwd is inside this lane's worktree (empty = none), or None =
    could not check (ps/lsof/proc blind or failed; the hook fails open). Only a linked worktree is scanned: in a shared
    checkout the same scan would also catch other lanes' nested worktrees, so a non-worktree cwd reports none."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        top = os.path.realpath(cwd)
        while not os.path.exists(os.path.join(top, ".git")) and top != os.path.dirname(top):
            top = os.path.dirname(top)
        if not os.path.isfile(os.path.join(top, ".git")):
            return []
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lane_liveness
        pids, _ = lane_liveness.cwd_pids(top)
        if pids is None:
            return None
        r = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, timeout=10)
        table = _ps_table(r.stdout) if r.returncode == 0 else {}
        return _bg_found(table, pids, os.getpid()) if table else None
    except Exception:  # fail open: a broken scan must never wedge a handback
        return None


def _hold(agent_id, suffix):
    """True while a block on this lane's `suffix` condition is younger than PUSH_MAX_S (the state file's mtime is the
    first block), so a stuck process cannot trap the lane forever."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(agent_id) + suffix
    try:
        first = os.path.getmtime(path)
    except OSError:
        first = time.time()
        open(path, "w").close()
    return time.time() - first < PUSH_MAX_S


def _counted(msg):
    """Lines of `msg` that count toward the cap: all but fenced code blocks (fence lines included) and
    lines starting with '! '. A one-line fence (an even number of ``` on a line starting with one) toggles
    nothing; an unclosed fence hides the rest of the message."""
    kept, fenced = [], False
    for ln in msg.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced ^= ln.count("```") % 2 == 1
        elif not fenced and not ln.startswith("! "):
            kept.append(ln)
    return kept


def check(data):
    """Return the hook exit code (0 pass, 2 block) for one hook-input dict."""
    if str(data.get("agent_type") or "") in _exempt_types():
        return 0
    running = _push_running(data.get("cwd"))
    if running is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether a git push from this worktree is still running (ps/lsof unavailable).\n")
    agent_id = str(data.get("agent_id") or "unknown")
    if running and _hold(agent_id, ".push"):  # keep blocking while the push is live, released after PUSH_MAX_S
        sys.stderr.write(
            "A git push from this worktree is still running (its pre-push hook may take 15+ minutes). "
            "You own it until it exits: wait with lane_guard.py wait --pid <pid> --timeout <s>, then hand back.\n"
        )
        return 2
    mode = _bg_mode()
    bg = _bg_running(data.get("cwd")) if mode != "off" else []
    if bg is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether a test or build from this worktree is still running (ps/lsof unavailable).\n")
    if bg:
        what = ", ".join(f"pid {p} `{c[:80]}`" for p, c in bg[:3]) + (f" (+{len(bg) - 3} more)" if len(bg) > 3 else "")
        if mode == "block" and _hold(agent_id, ".bg"):
            sys.stderr.write(
                f"Background work from this worktree is still running: {what}. You own it until it exits: wait with "
                "lane_guard.py wait --pid <pid> --timeout <s> (or stop your own process), then hand back.\n"
            )
            return 2
        if mode == "warn":
            print(json.dumps({"systemMessage": f"background_guard: this lane handed back with a test/build still running from its worktree: {what}."}))
    msg = data.get("last_assistant_message") or ""
    chars, lines, too_long = _shape(msg)  # fields-only and the 400/8 target never block: audit() logs them
    no_status = _require_status() and not STATUS_RE.search(msg)
    if not (too_long or no_status):
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(agent_id)
    blocks = _read_blocks(path)
    if blocks >= MAX_BLOCKS:
        return 0
    with open(path, "w") as fh:
        fh.write(str(blocks + 1))
    why = []
    if too_long:
        why.append(f"too long ({chars} chars, {lines} lines; cap {MAX_CHARS} chars / {MAX_LINES} lines)")
    if no_status:
        why.append("no status field")
    sys.stderr.write(
        f"Handback rejected: {'; '.join(why)} (the cap does not count fenced code or '! ' lines; whole message "
        f"{len(msg)} chars, limit {MAX_CHARS * COPY_FACTOR}). Rewrite your final message as key=value fields only, "
        "one per line, no sentences: status=VERIFIED (a green gate or a confirmed effect at the exact SHA) "
        "or status=UNVERIFIED (anything else), sha=<sha>, result=<few words>, tests=<n/n>, "
        "blockers=<none|text>. Put any long content in a file and give report=<path>.\n"
    )
    return 2


def _tok(chars):
    """Estimated tokens for `chars` characters (ceil(chars / CPT))."""
    return -(-chars // CPT)


def _lane_transcript(data):
    """The subagent's OWN transcript path, or None. `transcript_path` is the PARENT session's file (hooks docs,
    SubagentStop) and is never returned; without `agent_transcript_path`, derive the documented nested
    `<session>/subagents/agent-<agent_id>.jsonl` beside the parent's."""
    p = data.get("agent_transcript_path")
    if not p:
        tp, aid = data.get("transcript_path"), "".join(c for c in str(data.get("agent_id") or "") if c.isalnum() or c in "-_")
        if not (tp and aid):
            return None
        p = os.path.join(os.path.splitext(str(tp))[0], "subagents", f"agent-{aid}.jsonl")
    return os.path.expanduser(str(p))


def lane_stats(path, final=None):
    """Estimate one lane's assistant output from its JSONL transcript: `({text_tok, narr_tok, final_tok, tool_tok,
    calls}, final_text)`, or None when the file is unreadable or holds no parsable assistant entry (skip rather than
    guess zeros). Pure read: no writes. `final` is the hook's `last_assistant_message`; a `SubagentHandback` tool
    call's `message` wins and is counted as the final message, not as a tool call. The final message is counted once:
    when the transcript already ends with it, it is removed from the narration (the file may lag the hook)."""
    texts, tool_chars, calls, hb, seen = [], 0, 0, None, 0
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with fh:
        for ln in fh:
            if '"assistant"' not in ln:  # cheap pre-filter: skip tool results and metadata without parsing them
                continue
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            m = o.get("message") if isinstance(o, dict) and o.get("type") == "assistant" else None
            blocks = m.get("content") if isinstance(m, dict) else None
            if not isinstance(blocks, list):
                continue
            seen += 1
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and isinstance(b.get("text"), str):
                    texts.append(b["text"])
                elif b.get("type") == "tool_use":
                    inp = b.get("input")
                    if b.get("name") == "SubagentHandback" and isinstance(inp, dict) and isinstance(inp.get("message"), str):
                        hb = inp["message"]
                    else:
                        calls += 1
                        tool_chars += len(str(b.get("name") or "")) + len(json.dumps(inp, ensure_ascii=False))
    if not seen:
        return None
    fin = hb if hb is not None else ((final if isinstance(final, str) else None) or (texts[-1] if texts else ""))
    if texts and texts[-1].strip() == fin.strip():
        texts.pop()
    narr, fn = _tok(sum(map(len, texts))), _tok(len(fin))
    return {"text_tok": narr + fn, "narr_tok": narr, "final_tok": fn, "tool_tok": _tok(tool_chars), "calls": calls}, fin


def _ledger_path():
    """`HANDBACK_AUDIT_LEDGER` (empty or `off`: None = audit disabled), else `$XDG_CACHE_HOME|~/.cache`/perun/lane-audit.jsonl."""
    p = os.environ.get("HANDBACK_AUDIT_LEDGER")
    if p is None:
        return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "perun", "lane-audit.jsonl")
    return None if p in ("", "off") else p


def _shape_row(fin):
    """Ledger fields for one final message: `fields_ok` (non-empty, every line a field), `viol` (soft target
    violations, see _violations) and `cut_tok` (estimated tokens a truncation to the fields would drop)."""
    return {"fields_ok": bool(fin.strip()) and not _prose_lines(fin), "viol": _violations(fin),
            "cut_tok": max(_tok(len(fin)) - _tok(len(_truncate(fin))), 0) if _violations(fin) else 0}


def audit(data):
    """Append one JSON line for this lane to the local ledger (see LANE AUDIT in the module docstring).
    Side-effects: one append to the ledger plus a `<agent_id>.audited` marker in STATE_DIR so a lane that two hook
    entries match, or that stops twice, is logged once. Never raises, never blocks: any failure is a stderr note."""
    try:
        agent_id, ledger, path = str(data.get("agent_id") or ""), _ledger_path(), _lane_transcript(data)
        if not (agent_id and ledger and path):
            return
        got = lane_stats(path, data.get("last_assistant_message"))
        if got is None:
            sys.stderr.write("COULD_NOT_CHECK: lane audit skipped (no readable lane transcript with assistant entries).\n")
            return
        stats, fin = got
        os.makedirs(STATE_DIR, exist_ok=True)
        try:
            os.close(os.open(_state_path(agent_id) + ".audited", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            return
        agent_type = str(data.get("agent_type") or "")
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "agent_id": agent_id, "type": agent_type,
               "exempt": agent_type in _exempt_types(), **stats, **_shape_row(fin),
               "blocks": _read_blocks(_state_path(agent_id)), "cpt": CPT}
        os.makedirs(os.path.dirname(ledger) or ".", exist_ok=True)
        # ponytail: append-only, no rotation (about 200 bytes a lane); delete the file to reset.
        fd = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)  # one write: concurrent hooks never interleave
        try:
            os.write(fd, (json.dumps(row, separators=(",", ":")) + "\n").encode())
        finally:
            os.close(fd)
    except Exception as exc:  # a failing audit must never wedge a stop
        sys.stderr.write(f"COULD_NOT_CHECK: lane audit skipped ({type(exc).__name__}).\n")


def _p90(vals):
    s = sorted(vals)
    return s[min(len(s) - 1, int(0.9 * len(s)))] if s else 0


def summary(rows):
    """Aggregates only (counts and token estimates, never transcript content) for ledger/scan rows, one string.
    Exempt types (chat is their deliverable) are counted but left out of the medians. The last line is a
    PROJECTION, an upper bound that assumes every lane complies: narration 0, handback within the cap."""
    from statistics import median
    live = [r for r in rows if not r.get("exempt")]
    if not live:
        return f"lanes=0 ({len(rows)} exempt-type lanes excluded)"
    out = [f"lanes={len(live)} (+{len(rows) - len(live)} exempt-type lanes excluded); token figures are ESTIMATES, chars/{CPT}"]
    for k in ("text_tok", "narr_tok", "final_tok", "tool_tok"):
        v = [r.get(k) or 0 for r in live]
        out.append(f"{k:<9} median={median(v):.0f} p90={_p90(v)} total={sum(v)}")
    prose, tool = sum(r.get("text_tok") or 0 for r in live), sum(r.get("tool_tok") or 0 for r in live)
    out.append(f"text share of assistant output (text / (text + tool)): {100 * prose / max(prose + tool, 1):.1f}%")
    out.append(f"fields_ok: {100 * sum(bool(r.get('fields_ok')) for r in live) / len(live):.1f}% of handbacks already fields-only")
    out.append(f"off target (over {TARGET_CHARS} chars / {TARGET_LINES} lines, or prose): "
               f"{100 * sum(bool(r.get('viol')) for r in live) / len(live):.1f}% of handbacks, never blocked; "
               f"a truncation to the fields would drop {sum(r.get('cut_tok') or 0 for r in live)} tokens (delivery is not altered)")
    out.append(f"legacy-cap rewrites forced (over {MAX_CHARS} chars / {MAX_LINES} lines): {sum(r.get('blocks') or 0 for r in live)}")
    fo = [r.get("final_tok") or 0 for r in live if r.get("fields_ok")]
    lim = min(TARGET_CHARS // CPT, median(fo) if fo else TARGET_CHARS // CPT)
    after = [min(r.get("final_tok") or 0, lim) for r in live]
    out.append(f"projection (ESTIMATE; assumes every lane complies: narration 0, handback no larger than {lim:.0f} tokens = the "
               f"smaller of the cap and today's median fields-only handback): text_tok median={median(after):.0f} total={sum(after)}")
    return "\n".join(out)


def _cli(args):
    """`--report [LEDGER]` or `--scan PATH... [--since-days N]`: print aggregates; return the exit code."""
    import argparse
    import glob
    ap = argparse.ArgumentParser(prog="handback_cap.py", description="Aggregate lane-audit figures (never prints content).")
    ap.add_argument("--report", nargs="?", const="", metavar="LEDGER", help="summarise the ledger (default: the audit ledger path)")
    ap.add_argument("--scan", nargs="+", metavar="PATH", help="audit existing lane transcripts: files, or dirs holding subagents/agent-*.jsonl")
    ap.add_argument("--since-days", type=float, help="with --scan: only transcripts modified within N days")
    a = ap.parse_args(args)
    rows = []
    if a.report is not None:
        path = a.report or _ledger_path()
        if not path or not os.path.isfile(path):
            sys.stderr.write(f"no ledger at {path!r}\n")
            return 2
        for ln in open(path, encoding="utf-8", errors="replace"):
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    elif a.scan:
        files = []
        for p in map(os.path.expanduser, a.scan):
            files += [p] if os.path.isfile(p) else glob.glob(os.path.join(p, "**", "subagents", "agent-*.jsonl"), recursive=True)
        cut = time.time() - a.since_days * 86400 if a.since_days else 0
        for f in sorted(files):
            if os.path.getmtime(f) < cut:
                continue
            got = lane_stats(f)
            if got is None:
                continue
            try:
                with open(f[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
                    t = str(json.load(fh).get("agentType") or "")
            except (OSError, ValueError, AttributeError):
                t = ""
            rows.append({"type": t, "exempt": t in _exempt_types(), **got[0], **_shape_row(got[1]), "blocks": int(_shape(got[1])[2])})
    else:
        ap.error("give --report or --scan")
    print(summary(rows))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # unparseable input: never wedge a subagent
    rc = check(data)
    if rc == 0:
        audit(data)
    return rc


# ---------------------------------------------------------------------------
# --selftest — exercises check() directly (no subprocess, no real stdin) so
# the state dir and env overrides are trivially isolated per case.
# ---------------------------------------------------------------------------
def _selftest():
    import shutil

    global STATE_DIR
    tmp = tempfile.mkdtemp(prefix="handback-cap-selftest-")
    STATE_DIR = tmp
    passed = 0
    failed = 0

    def case(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print(f"PASS  {name} (rc={got})")
        else:
            failed += 1
            print(f"FAIL  {name} (got rc={got}, want rc={want})")

    global _push_running
    real_push = _push_running
    _push_running = lambda cwd: {"/live": True, "/idle": False}.get(cwd)
    case("push-running-blocks", check({"agent_id": "p1", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 2)
    case("push-not-running-passes", check({"agent_id": "p2", "cwd": "/idle", "last_assistant_message": "VERIFIED"}), 0)
    case("push-unknown-passes-with-COULD_NOT_CHECK", check({"agent_id": "p5", "cwd": "/denied", "last_assistant_message": "VERIFIED"}), 0)
    case("push-exempt-type-passes", check({"agent_id": "p3", "agent_type": "Explore", "cwd": "/live", "last_assistant_message": "x"}), 0)
    for _ in range(MAX_BLOCKS + 5):  # many stop attempts while the push is live: still blocked
        rc = check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"})
    case("push-live-keeps-blocking", rc, 2)
    os.utime(_state_path("p4") + ".push", (0, 0))  # first block long ago (> PUSH_MAX_S): released
    case("push-block-releases-after-max-age", check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 0)
    _push_running = real_push
    case("push-check-no-cwd-is-unknown", _push_running(""), None)
    real_run = subprocess.run
    def _deny(*a, **k):
        raise PermissionError("ps denied")
    subprocess.run = _deny
    try:
        case("ps-denied-is-unknown-not-false", _push_running(tmp), None)
    finally:
        subprocess.run = real_run
    def cd(c):
        m = PUSH_RE.search(c)
        return m and (m.group(2) or m.group(3) or m.group(4))
    case("git-dash-C-push-matches", cd("git -C /w/x push -q origin main"), "/w/x")
    case("git-dash-C-quoted-space-matches", cd('git -C "/w/dir w/ space" push'), "/w/dir w/ space")
    case("git-dash-c-kv-push-matches", bool(PUSH_RE.search("git -c core.x=1 push origin main")), True)
    case("git-dash-c-then-C-matches", cd("git -c a=b -C /w/y push"), "/w/y")
    case("plain-git-push-matches", bool(PUSH_RE.search("git push origin")), True)
    case("git-status-does-not-match", bool(PUSH_RE.search("git status --push")), False)

    # short message passes
    case("short-passes", check({"agent_id": "a1", "last_assistant_message": "VERIFIED | verdict=ok"}), 0)

    # fields-only is log-only: prose never blocks (no second handback), it is only classified
    case("fields-pass", check({"agent_id": "f1", "last_assistant_message": "status=VERIFIED\nsha=1a2b3c\ntests=3/3\nblockers=none"}), 0)
    case("sentence-never-blocks", check({"agent_id": "f2", "last_assistant_message": "Done. All the tests pass and I pushed."}), 0)
    case("sentence-is-a-violation", _violations("Done. All the tests pass and I pushed."), ["prose"])
    case("fields-are-no-violation", _violations("status=VERIFIED\nsha=1a2b3c"), [])
    case("over-target-is-a-violation", _violations("k=" + "v" * TARGET_CHARS), ["long"])
    case("truncation-keeps-only-fields", _truncate("sha=1a2b3c\nI also fixed the docs.\ntests=3/3"), "sha=1a2b3c\ntests=3/3")

    # status token is opt-in: off by default, a status-less short handback passes
    case("status-check-off-by-default", check({"agent_id": "s0", "last_assistant_message": "verdict=ok"}), 0)
    saved_req = os.environ.get("HANDBACK_REQUIRE_STATUS")
    os.environ["HANDBACK_REQUIRE_STATUS"] = "1"
    case("no-status-blocks-when-on", check({"agent_id": "s1", "last_assistant_message": "verdict=ok"}), 2)
    case("host-style-done-passes", check({"agent_id": "s8", "last_assistant_message": "done | 4b2765b | next=merge"}), 0)
    case("mixed-case-verified-passes", check({"agent_id": "s9", "last_assistant_message": "Verified | sha=abc"}), 0)
    case("done-in-prose-blocks", check({"agent_id": "s10", "last_assistant_message": "done with it, sha=abc"}), 2)
    case("unverified-passes", check({"agent_id": "s2", "last_assistant_message": "UNVERIFIED | todo=tests"}), 0)
    case("status-key-passes", check({"agent_id": "s3", "last_assistant_message": "sha=abc\nstatus=VERIFIED"}), 0)
    case("lowercase-verified-in-prose-blocks",
         check({"agent_id": "s4", "last_assistant_message": "all verified, sha=abc"}), 2)
    case("status-block-releases-after-max-blocks",
         [check({"agent_id": "s5", "last_assistant_message": "ok"}) for _ in range(MAX_BLOCKS + 1)][-1], 0)
    case("exempt-type-needs-no-status",
         check({"agent_id": "s6", "agent_type": "Explore", "last_assistant_message": "ok"}), 0)
    os.environ["HANDBACK_REQUIRE_STATUS"] = "0"
    try:
        case("status-check-off-via-env", check({"agent_id": "s7", "last_assistant_message": "ok"}), 0)
    finally:
        if saved_req is None:
            os.environ.pop("HANDBACK_REQUIRE_STATUS", None)
        else:
            os.environ["HANDBACK_REQUIRE_STATUS"] = saved_req

    # long message (chars) blocks MAX_BLOCKS times then releases
    long_msg = "x" * (MAX_CHARS + 100)
    for i in range(MAX_BLOCKS):
        case(f"long-blocks-{i+1}", check({"agent_id": "a2", "last_assistant_message": long_msg}), 2)
    case("long-releases-after-max-blocks", check({"agent_id": "a2", "last_assistant_message": long_msg}), 0)

    # more than MAX_LINES lines but few chars still blocks
    many_lines = "\n".join(["k=v"] * (MAX_LINES + 5))
    case("many-lines-blocks", check({"agent_id": "a3", "last_assistant_message": many_lines}), 2)

    # garbage stdin (simulated: main() catches JSON errors; check() only takes dicts,
    # so exercise main()'s parse-failure path via a broken stdin stand-in)
    class _BadStdin:
        def read(self):
            return "not json"

    real_stdin = sys.stdin
    sys.stdin = _BadStdin()
    try:
        case("garbage-stdin-passes", main(), 0)
    finally:
        sys.stdin = real_stdin

    # per-agent_id counters are independent: a4 fresh, still blocks despite a2 exhausted
    case("independent-agent-id-still-blocks", check({"agent_id": "a4", "last_assistant_message": long_msg}), 2)

    # exempt type: 5000-char message always passes, no state file, no block count spent
    huge_msg = "y" * 5000
    case(
        "exempt-type-huge-message-passes",
        check({"agent_id": "a5", "agent_type": "Explore", "last_assistant_message": huge_msg}),
        0,
    )
    # same huge message, non-exempt type: blocks
    case(
        "non-exempt-type-huge-message-blocks",
        check({"agent_id": "a6", "agent_type": "builder", "last_assistant_message": huge_msg}),
        2,
    )

    # exemption is by listed NAME: a custom review-lane type is capped by
    # default, and exempt once added via HANDBACK_EXEMPT_TYPES.
    lane = {"agent_id": "a7", "agent_type": "security-reviewer", "last_assistant_message": huge_msg}
    case("custom-type-capped-by-default", check(dict(lane)), 2)
    saved = os.environ.get("HANDBACK_EXEMPT_TYPES")
    os.environ["HANDBACK_EXEMPT_TYPES"] = DEFAULT_EXEMPT_TYPES + ",security-reviewer"
    try:
        case("custom-type-exempt-via-env", check(dict(lane, agent_id="a8")), 0)
    finally:
        if saved is None:
            os.environ.pop("HANDBACK_EXEMPT_TYPES", None)
        else:
            os.environ["HANDBACK_EXEMPT_TYPES"] = saved

    # matcher-scoped env override raises the cap for one agent type (the
    # host-enforcement.md fix for a report-file-less review lane) — must be a
    # real subprocess: MAX_LINES/MAX_CHARS are read from os.environ at import,
    # so an in-process check() call can never see a per-invocation override.

    twenty_lines = "\n".join(["status=VERIFIED"] + ["k=ok"] * 19)  # 20 lines, well under MAX_CHARS

    def run_subproc(agent_id, extra_env):
        env = dict(os.environ, HANDBACK_STATE_DIR=tmp, HANDBACK_AUDIT_LEDGER="off")
        if "HANDBACK_MAX_LINES" not in extra_env:
            env.pop("HANDBACK_MAX_LINES", None)
        env.update(extra_env)
        payload = json.dumps({"agent_id": agent_id, "last_assistant_message": twenty_lines})
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            input=payload, capture_output=True, text=True, env=env,
        )
        return proc.returncode

    case(
        "env-override-raises-cap-for-type",
        run_subproc("sub1", {"HANDBACK_MAX_LINES": "25"}),
        0,
    )
    case(
        "same-message-default-cap-blocks",
        run_subproc("sub2", {}),
        2,
    )

    # lane audit: a synthetic transcript (one assistant block per entry, as observed) -> expected ledger row
    def tr(*entries):
        p = os.path.join(tmp, f"t{len(os.listdir(tmp))}.jsonl")
        with open(p, "w") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        return p

    def asst(*blocks):
        return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}

    t = tr({"type": "user", "message": {"role": "user", "content": "assistant brief"}},
           asst({"type": "text", "text": "a" * 40}),  # 10 tok narration
           asst({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}),  # 4 + 17 = 21 chars: 6 tok
           asst({"type": "text", "text": "status=VERIFIED"}))  # the final, already in the transcript
    got = lane_stats(t, "status=VERIFIED")
    case("audit-counts-narration-final-tool", got and got[0], {"text_tok": 14, "narr_tok": 10, "final_tok": 4, "tool_tok": 6, "calls": 1})
    got = lane_stats(t[:-6] + "x.jsonl")
    case("audit-unreadable-transcript-is-none", got, None)
    case("audit-never-reads-parent-transcript",
         _lane_transcript({"transcript_path": "/s/abc.jsonl", "agent_id": "d1"}), "/s/abc/subagents/agent-d1.jsonl")
    ledger = os.path.join(tmp, "ledger.jsonl")
    os.environ["HANDBACK_AUDIT_LEDGER"] = ledger
    try:
        hook = {"agent_id": "L1", "agent_type": "builder", "agent_transcript_path": t, "last_assistant_message": "status=VERIFIED"}
        check(hook), audit(hook), audit(hook)  # a second stop of the same lane is not logged again
        rows = [json.loads(x) for x in open(ledger)]
        case("audit-one-ledger-line-per-lane", len(rows), 1)
        case("audit-row-numbers", (rows[0]["text_tok"], rows[0]["narr_tok"], rows[0]["tool_tok"], rows[0]["fields_ok"]), (14, 10, 6, True))
        case("audit-ledger-holds-no-content", "aaaa" in open(ledger).read(), False)
        case("audit-summary-is-aggregates", "narr_tok" in summary(rows), True)
    finally:
        os.environ.pop("HANDBACK_AUDIT_LEDGER", None)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if {"--report", "--scan", "-h", "--help"} & set(sys.argv):
        sys.exit(_cli(sys.argv[1:]))
    sys.exit(main())
