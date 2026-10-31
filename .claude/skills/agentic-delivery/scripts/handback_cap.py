#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=cap a subagent handback and audit each lane's prose, review=2027-01-30
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
waits for background work from its worktree until it exits. When the lane's cwd is inside a LINKED worktree and a test or build runner
(BG_RE: pytest, jest, vitest, playwright, make, `npm test`, `cargo test`, `go build`, a `*test*.py|sh` script, ...) has its
cwd inside that worktree, `warn` sends the owner a `systemMessage` naming the pid and command, and `block` exits 2 with the
same text on stderr (released after PUSH_MAX_S, like a live `git push` or `git commit`: PUSH_RE matches both for a process whose argv[0] is `git`, `-C`/`-c`
and an `env VAR=...` or perl alarm wrapper included, but not `commit-tree`, `commit-graph`, `push-x` or a `claude -p` brief or `grep` that names them; read-only
agent types, READONLY_RE, are never held for one). Every hold (live push or commit, background work, dirty worktree) restarts its window once a check
finds its condition gone (`_release`); a check that could not run keeps it. Dev servers are not matched. The scan reuses
lane_liveness.cwd_pids (lsof, else /proc) plus one `ps`, excludes this hook's own pid, ancestors and descendants
(`_skip_pids`, shared with the live push/commit check), and fails open: a blind scan prints COULD_NOT_CHECK and never blocks. A non-worktree cwd (a shared checkout) is not scanned.
DIRTY WORKTREE (same switch): in a linked worktree, `git status --porcelain` (gitignored files excluded) listing
uncommitted or untracked paths gets a `systemMessage` under `warn` (merged with the line above, one JSON line) or exit 2
under `block` (released after PUSH_MAX_S). Read-only agent types (READONLY_RE: review, investigat, audit, explore) are
skipped. Linked worktrees are told from the main checkout, submodules and `--separate-git-dir` repos by `git rev-parse
--git-dir` differing from `--git-common-dir`; the payload does not expose the parent session cwd, so the message
says to ignore edits that are not the lane's. The main checkout is never reported; a git failure prints COULD_NOT_CHECK
and passes. A leaked listening process is not checked: `reap_own.sh --report` prints `orphans=COULD_NOT_CHECK` in the
sandbox (pgrep denied), so it is no usable primitive there.
REAP OWN WORKTREE (on a passing stop; PERUN_REAP_WORKTREE=0 disables). `git worktree remove` (never --force) of the stopping
lane's linked worktree, only when lane_worktree.sh made it (marker file, `lane/` branch, matching repo, agent id if the marker
has one), it sits under the lane root, is clean including ignored files, equals its upstream, and no test/build runs from
it (a blind scan only reports). Other trees and the main checkout are never touched; any doubt keeps the tree and says so
on stderr. Full rule list: `_reap_own_worktree`.
When the scan finds nothing but the handback text itself says the lane is "waiting on" its background tests (WAIT_RE),
a `systemMessage` flags it in every mode but `off`; never a block (the text is a claim, not evidence).

NARRATION NUDGE: when a non-exempt lane wrote at least HANDBACK_NARR_NUDGE (default 100, 0 = off) estimated tokens of
prose between tool calls, a `systemMessage` names the amount and the per-call `narr_rate`. Detect-and-measure after the
lane ended; it does not prevent narration.

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
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [text](url) counts as `text`
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
    kept = [LINK_RE.sub(r"\1", ln) for ln in _counted(msg) if ln.strip()] if msg else []  # blank lines and link URLs are not prose
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


# A process whose argv[0] is `git` (any path), alone or behind `env VAR=...` or `perl -e 'alarm N; exec @ARGV'`:
# `git [-c k=v] [-C dir | -C "dir w/ space"] [--opt] push|commit` (a hook can make either slow; `commit-tree`, `commit-graph` and `push-x` do not match,
# nor does a `claude -p` lane brief, a shell string or a `grep` that only names the words); group 2/3/4 = the -C dir (double-quoted, single-quoted or bare;
# `ps` prints argv without quotes, so a space inside a -c value or -C path splits it: a known limit, see `_push_running`)
PUSH_RE = re.compile(r"""^(?:(?:\S*/)?env\s+(?:\w+=\S*\s+)*|(?:\S*/)?perl\s+-e\s+(?:'[^']*'|alarm\s+\d+;\s*exec\s+@ARGV)\s+)*(?:\S*/)?git((?:\s+-C\s+(?:"([^"]*)"|'([^']*)'|(\S+))|\s+-c\s+\S+|\s+-\S+)*)\s+(?:push|commit)(?![\w-])""")
PUSH_MAX_S = int(os.environ.get("HANDBACK_PUSH_MAX_S", "1800"))  # keep blocking while the push or commit is live, at most this long


def _push_running(cwd):
    """True/False: is a `git push` or `git commit` (also `git -C <dir> push|commit`) live with its cwd or -C dir in the same git worktree as `cwd`?
    Only a process whose argv[0] is `git` counts (PUSH_RE), so a `claude -p "<brief that says git commit>"` host, a sibling lane or a `grep` that merely names the words does not.
    Never counts `_skip_pids`: this hook, its ancestors (a `git commit` whose own hook runs this one) or its descendants.
    None = could not check (no cwd, ps/lsof denied or failed): the hook stays advisory and fails open, but says so.
    Known limit: `ps` prints argv without quoting, so a space inside a `-c` value or a `-C` path splits it
    (`git -c user.name=Jane Smith commit`, `git -C /acme/my repo commit`), PUSH_RE no longer matches, and that push or
    commit is not held (fails open, no COULD_NOT_CHECK). Selftest cases `known-limit-*` pin this."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lane_liveness import same_tree as _same_tree
        r = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, timeout=10)
        table = _ps_table(r.stdout) if r.returncode == 0 else {}
        if not table:
            return None
        root, skip = os.path.realpath(cwd), _skip_pids(table, os.getpid())
        for pid, (_, cmd) in table.items():
            m = PUSH_RE.search(cmd)
            if not m or pid in skip:
                continue
            cdir = m.group(2) or m.group(3) or m.group(4)
            if cdir and _same_tree(cdir, root):
                return True
            out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"], capture_output=True, text=True, timeout=10)
            if out.returncode > 1:
                return None
            if any(n.startswith("n") and _same_tree(n[1:], root) for n in out.stdout.splitlines()):
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


def _skip_pids(table, me):
    """pids a process scan must never count: `me`, its ancestors (the host that runs this hook; a headless `claude -p`
    host carries the lane's brief, `git commit` included, in its argv) and its descendants (the ps/lsof it spawned).
    `table` maps pid -> (ppid, command)."""
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
    return skip | kids


# The lane's own words: it hands back "waiting on" its background tests. Advisory only (see check()).
_WAIT_KW = (r"(?:background|bg|tests?|test\s+(?:suite|run)|suites?|builds?|pytest|playwright|e2e|gates?|pre-push|ci|checks?"
            r"|lint|workflows?|actions|jobs?|runs?)")
WAIT_RE = re.compile(
    r"\b(?:waiting|awaiting)\s+(?:on\s+|for\s+)?(?:[\w-]+\s+){0,3}?" + _WAIT_KW + r"\b"
    r"|\b(?:background|bg)\s+(?:\w+\s+){0,2}?(?:is\s+|are\s+)?(?:still\s+)?running"
    r"|\b" + _WAIT_KW + r"\s+(?:[\w-]+\s+){0,2}?(?:is\s+|are\s+)?still\s+(?:running|going)"
    r"|running\s+in\s+(?:the\s+)?background", re.IGNORECASE)
# Words in the claim's own clause that cancel it: a negation, a wait on a person rather than on background work, or
# CI on main rather than the lane's own. A past tense cancels only "running in the background", and only in the
# three words before it ("that was running in the background"), so "I ran the suite and I am waiting on CI" counts.
_NOT_A_CLAIM = re.compile(r"\b(?:not|no|never|longer|nothing|none|nobody|owner|parent|human|user|approv\w*|decision|review\w*"
                          r"|main|pre-existing)\b|n't\b", re.IGNORECASE)
_PAST = re.compile(r"\b(?:was|were|had|ran|finished|killed|stopped)\b", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[.;:,!?()\u2013\u2014]|\s-\s|\b(?:after|and|then|but)\b")


def _waiting_claim(msg):
    """True when a counted line of `msg` (fences and '! ' lines excluded, as for the cap) claims the lane is waiting
    on background work. A match whose own clause (the text back to the previous punctuation, and the next five words
    after it) carries a negation ("not waiting on tests", "wait for CI not needed") or names a person ("waiting on
    owner to run tests") does not count. A heuristic: it misses wordings it has no keyword for, which is why it only
    advises."""
    for ln in _counted(msg):
        for m in WAIT_RE.finditer(ln):
            head = _CLAUSE_END.split(ln[:m.start()])[-1]
            tail = " ".join(_CLAUSE_END.split(ln[m.end():])[0].split()[:5])
            past = m.group(0).lower().startswith("running") and _PAST.search(" ".join(head.split()[-3:]))
            if not (_NOT_A_CLAIM.search(head + " " + m.group(0) + " " + tail) or past):
                return True
    return False


def _bg_found(table, pids, me):
    """[(pid, command)] of test/build processes among `pids`. `table` maps pid -> (ppid, command). Never counts
    `_skip_pids(table, me)`."""
    skip = _skip_pids(table, me)
    return sorted((p, table[p][1]) for p in pids if p in table and p not in skip and BG_RE.search(table[p][1]))


def _linked_top(cwd):
    """Root of the LINKED git worktree containing `cwd` (its `.git` is a file), else None: a shared checkout (`.git` a
    directory) or no repo at all. The bg process scan skips a shared checkout (the dirty check uses git instead)."""
    top = os.path.realpath(cwd)
    while not os.path.exists(os.path.join(top, ".git")) and top != os.path.dirname(top):
        top = os.path.dirname(top)
    return top if os.path.isfile(os.path.join(top, ".git")) else None


def _dirty_tree(cwd):
    """`git status --porcelain` lines (gitignored files excluded) of the LINKED worktree containing `cwd`: [] = clean,
    not a linked worktree (the main checkout, a submodule or a `--separate-git-dir` repo: their git-dir equals the
    common dir; also a non-repo or missing dir) or no cwd; None = git failed or timed out (the hook fails open and says
    COULD_NOT_CHECK). Read-only: `--no-optional-locks` keeps it from touching the index. Limit: the hook payload names
    only the lane's own cwd, so a lane whose linked worktree is also its parent session's cwd cannot be told apart;
    the message therefore says to ignore the finding when the edits are not the lane's."""
    if not cwd or not os.path.isdir(cwd):
        return []
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel", "--git-dir", "--git-common-dir"], cwd=cwd, capture_output=True, text=True, timeout=15)
        paths = r.stdout.splitlines()
        if r.returncode != 0 or len(paths) != 3:
            return []
        top, gd, cd = (os.path.realpath(os.path.join(cwd, x)) for x in paths)
        if gd == cd:
            return []
        r = subprocess.run(["git", "--no-optional-locks", "status", "--porcelain"], cwd=top, capture_output=True, text=True, timeout=15)
        return r.stdout.splitlines() if r.returncode == 0 else None
    except Exception:
        return None


def _git(top, *a):
    r = subprocess.run(["git", "--no-optional-locks", *a], cwd=top, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else None


def _lane_kept(top, why):
    sys.stderr.write(f"perun: lane worktree {top} left in place ({why}); remove it yourself with git worktree remove once pushed.\n")


def _reap_own_worktree(cwd, agent_id="", sure=True):
    """SubagentStop: `git worktree remove` (never --force) of the stopping lane's linked worktree, only when it is provably a
    lane tree made by lane_worktree.sh: marker <git-dir>/perun-lane (branch, repo, path, optional agent) matches this tree and
    repo, the marker agent (if any) is this agent, the tree sits strictly under the lane root (PERUN_WT_ROOT, default
    ${XDG_CACHE_HOME:-~/.cache}/perun-wt; `/`, $HOME and any ancestor of the repo are refused), HEAD is the `lane/` branch
    and equals its own upstream, and `status --porcelain --ignored` is empty. `sure` False (a blind bg scan, a released
    block) only reports. After the remove the merged branch is deleted (`branch -d`). Any doubt or git failure keeps the
    tree and, for a marked lane tree, says so on stderr. PERUN_REAP_WORKTREE=0 disables. Returns the removed path or None."""
    try:
        if os.environ.get("PERUN_REAP_WORKTREE") == "0" or not cwd or not os.path.isdir(cwd):
            return None
        top = _linked_top(cwd)
        gd = _git(top, "rev-parse", "--absolute-git-dir") if top else None
        if not gd or not os.path.isfile(os.path.join(gd, "perun-lane")):
            return None
        with open(os.path.join(gd, "perun-lane")) as fh:
            mk = dict(l.split("=", 1) for l in fh.read().splitlines() if "=" in l)
        common = os.path.realpath(os.path.join(gd, _git(top, "rev-parse", "--git-common-dir")))
        root = os.path.realpath(os.environ.get("PERUN_WT_ROOT") or os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "perun-wt"))
        repo_dir = os.path.dirname(common) if os.path.basename(common) == ".git" else common
        branch = _git(top, "symbolic-ref", "-q", "--short", "HEAD") or ""
        bad = next((m for c, m in (
            (not sure, "could not check for running work"),
            (mk.get("repo") != common or mk.get("path") != top, "marker does not match this tree"),
            (bool(mk.get("agent")) and mk["agent"] != agent_id, "tree belongs to another agent"),
            (root in ("/", os.path.realpath(os.path.expanduser("~"))) or repo_dir.startswith(root + os.sep), "unsafe lane root"),
            (not top.startswith(root + os.sep), "outside the lane root"),
            (branch != mk.get("branch") or not branch.startswith("lane/"), "not on its lane branch"),
            (_git(top, "status", "--porcelain", "--ignored") != "", "uncommitted, untracked or ignored files"),
            (_git(top, "rev-parse", "HEAD") != _git(top, "rev-parse", "@{u}"), "HEAD differs from its upstream, or none"),
        ) if c), "")
        if bad:
            _lane_kept(top, bad)
            return None
        r = subprocess.run(["git", f"--git-dir={common}", "worktree", "remove", top], cwd="/", capture_output=True, text=True, timeout=120)
        if r.returncode:
            _lane_kept(top, "git worktree remove refused")
            return None
        subprocess.run(["git", f"--git-dir={common}", "branch", "-d", branch], cwd="/", capture_output=True, timeout=30)
        return top
    except Exception:
        return None


# Agent types that only read: a dirty tree is never theirs, so it is not reported against them.
READONLY_RE = re.compile(r"review|investigat|audit|explore", re.I)


def _bg_running(cwd):
    """[(pid, command)] of test/build processes whose cwd is inside this lane's worktree (empty = none), or None =
    could not check (ps/lsof/proc blind or failed; the hook fails open). Only a linked worktree is scanned: in a shared
    checkout the same scan would also catch other lanes' nested worktrees, so a non-worktree cwd reports none."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        top = _linked_top(cwd)
        if not top:
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
    first block), so a stuck process cannot trap the lane forever. `_release` removes the file once the condition is gone."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(agent_id) + suffix
    try:
        first = os.path.getmtime(path)
    except OSError:
        first = time.time()
        open(path, "w").close()
    return time.time() - first < PUSH_MAX_S


def _release(agent_id, suffix):
    """Forget this lane's `suffix` hold because its condition is gone: the next block opens a fresh PUSH_MAX_S window.
    Without it the state file's mtime stays the first block, so a later block after one long-past block is released at
    once. Never called when the check could not run (None): the hold is kept. Ignores OSError (no file, no dir)."""
    try:
        os.remove(_state_path(agent_id) + suffix)
    except OSError:
        pass


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
    """Return the hook exit code (0 pass, 2 block) for one hook-input dict.
    The push or commit, background and dirty-worktree checks are all evaluated before it returns 2, so each one that finds
    no condition resets its hold's window even while another hold blocks (`_release`; a check that could not run, None,
    keeps it). The first hold that blocks wins, in that order, and a lower hold is never started while a higher one blocks."""
    if str(data.get("agent_type") or "") in _exempt_types():
        return 0
    ro = READONLY_RE.search(str(data.get("agent_type") or ""))  # a read-only type never owns a commit or push: not held, not scanned
    running = False if ro else _push_running(data.get("cwd"))
    if running is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether a git push or commit from this worktree is still running (ps/lsof unavailable).\n")
    agent_id = str(data.get("agent_id") or "unknown")
    hold_text = None  # stderr text of the first hold that blocks; the scans below still run so each empty one resets its hold
    if running and _hold(agent_id, ".push"):  # keep blocking while the push or commit is live, released after PUSH_MAX_S
        hold_text = (
            "A git push or commit from this worktree is still running (its pre-push or pre-commit hook may take 15+ minutes) and may not be yours. "
            f"Wait for it with lane_guard.py wait --pid <pid> --timeout <s>, then hand back; the hold ends after {PUSH_MAX_S} s at most.\n"
        )
    if running is False:
        _release(agent_id, ".push")
    mode = _bg_mode()
    notes = []
    bg = _bg_running(data.get("cwd")) if mode != "off" else []
    if bg is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether a test or build from this worktree is still running (ps/lsof unavailable).\n")
    if bg:
        what = ", ".join(f"pid {p} `{c[:80]}`" for p, c in bg[:3]) + (f" (+{len(bg) - 3} more)" if len(bg) > 3 else "")
        if mode == "block" and hold_text is None and _hold(agent_id, ".bg"):
            hold_text = (
                f"Background work from this worktree is still running: {what}. Wait for it with "
                "lane_guard.py wait --pid <pid> --timeout <s>, or stop it if this lane started it, then hand back; "
                f"the hold ends after {PUSH_MAX_S} s at most.\n"
            )
        if mode == "warn":
            notes.append(f"background_guard: this lane handed back with a test/build still running from its worktree: {what}.")
    elif bg == []:
        _release(agent_id, ".bg")
    dirty = [] if ro or mode == "off" else _dirty_tree(data.get("cwd"))
    if dirty is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether this worktree has uncommitted changes (git status failed).\n")
    if dirty:
        left = f"{len(dirty)} uncommitted path(s) (first: `{dirty[0][:80]}`)"
        if mode == "block" and hold_text is None and _hold(agent_id, ".dirty"):
            hold_text = f"This linked worktree has {left}. Commit or discard your own changes, then hand back; if the edits are not yours, tell the owner.\n"
        if mode == "warn":
            notes.append(f"background_guard: this lane handed back with a dirty worktree: {left}. Ignore if these edits are not yours.")
    elif dirty == []:
        _release(agent_id, ".dirty")
    if hold_text:
        sys.stderr.write(hold_text)
        return 2
    msg = data.get("last_assistant_message") or ""
    if not bg and mode != "off" and _waiting_claim(msg):  # scan saw nothing (or was blind) but the lane says it is waiting
        notes.append("background_guard: this lane's handback says it is waiting on background work; it must wait in its own turn (lane_guard.py wait) and hand back the result.")
    if notes:  # one JSON line however many findings
        _SENT.append(1)
        print(json.dumps({"systemMessage": " ".join(notes)}))
    chars, lines, too_long = _shape(msg)  # fields-only and the 400/8 target never block: audit() logs them
    no_status = _require_status() and not STATUS_RE.search(msg)
    if not (too_long or no_status):
        _reap_own_worktree(data.get("cwd"), agent_id, sure=bg == [])  # bg None = could not check: report only
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(agent_id)
    blocks = _read_blocks(path)
    if blocks >= MAX_BLOCKS:
        _reap_own_worktree(data.get("cwd"), agent_id, sure=False)
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


_SENT = []  # filled once check() has printed its systemMessage; the narration nudge then stays silent (one JSON line)


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
        stats["narr_rate"] = round(stats["narr_tok"] / max(stats["calls"], 1), 1)  # narration tokens per tool call
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
        return row
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
        row = audit(data)
        limit = int(os.environ.get("HANDBACK_NARR_NUDGE", "100"))  # estimated tokens of between-call prose; 0 turns the nudge off
        if row and limit and not row["exempt"] and row["narr_tok"] >= limit and not _SENT:
            print(json.dumps({"systemMessage": f"narration: lane {row['agent_id']} wrote ~{row['narr_tok']} tokens of prose "
                              f"between {row['calls']} tool calls ({row['narr_rate']}/call). Rule: tool calls only, no narration. "
                              "Measured after the fact, not prevented."}))
    return rc


# ---------------------------------------------------------------------------
# --selftest — exercises check() directly (no subprocess, no real stdin) so
# the state dir and env overrides are trivially isolated per case.
# ---------------------------------------------------------------------------
def _selftest():
    import io
    import shutil
    from contextlib import redirect_stderr

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
    case("push-readonly-type-passes", check({"agent_id": "p6", "agent_type": "security-reviewer", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 0)  # a review type never owns a commit
    case("push-writer-type-blocks", check({"agent_id": "p7", "agent_type": "general-purpose", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 2)
    err = io.StringIO()
    with redirect_stderr(err):
        check({"agent_id": "p8", "cwd": "/live", "last_assistant_message": "VERIFIED"})
    case("push-hold-text-does-not-claim-ownership", ("You own" in err.getvalue(), "lane_guard.py wait" in err.getvalue()), (False, True))
    for _ in range(MAX_BLOCKS + 5):  # many stop attempts while the push is live: still blocked
        rc = check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"})
    case("push-live-keeps-blocking", rc, 2)
    os.utime(_state_path("p4") + ".push", (0, 0))  # first block long ago (> PUSH_MAX_S): released
    case("push-block-releases-after-max-age", check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 0)
    # a hold forgets its first block once its condition is gone: block long past, condition clears, condition returns -> held again
    global _bg_mode, _bg_running, _dirty_tree
    real_scans = (_bg_mode, _bg_running, _dirty_tree)
    live = {".push": False, ".bg": False, ".dirty": False}  # per scan: True condition live, False none, None could not check
    _bg_mode = lambda: "block"
    _push_running = lambda cwd: live[".push"]
    _bg_running = lambda cwd: {True: [(7, "pytest -x")], False: [], None: None}[live[".bg"]]
    _dirty_tree = lambda cwd: {True: [" M a.py"], False: [], None: None}[live[".dirty"]]
    lane = lambda aid: {"agent_id": aid, "cwd": "/idle", "last_assistant_message": "VERIFIED"}
    sfile = lambda held, sfx: _state_path(held["agent_id"]) + sfx
    with redirect_stderr(io.StringIO()):
        for sfx in live:
            held, name = lane(f"hold{sfx}"), sfx[1:]
            live[sfx] = True
            case(f"{name}-hold-blocks-while-condition-live", check(held), 2)
            os.utime(sfile(held, sfx), (0, 0))  # first block long ago (> PUSH_MAX_S)
            live[sfx] = None
            case(f"{name}-hold-kept-when-scan-could-not-run", [check(held), os.path.exists(sfile(held, sfx))], [0, True])
            live[sfx] = True
            case(f"{name}-hold-released-after-max-age", check(held), 0)
            live[sfx] = False
            case(f"{name}-hold-condition-clears-passes", check(held), 0)
            live[sfx] = True
            case(f"{name}-hold-fresh-window-when-condition-returns", check(held), 2)
            live[sfx] = False
        # a lower hold that a higher one masks on this call still resets once its own scan is empty, so it gets a fresh window later
        for low, high in ((".bg", ".push"), (".dirty", ".push"), (".dirty", ".bg")):
            held, lo, hi = lane(f"mask{low}{high}"), low[1:], high[1:]
            live[low] = True
            case(f"{lo}-hold-opens-before-{hi}-blocks", check(held), 2)
            os.utime(sfile(held, low), (0, 0))
            live[low], live[high] = False, True
            case(f"{lo}-hold-reset-while-{hi}-blocks", [check(held), os.path.exists(sfile(held, low))], [2, False])
            live[low], live[high] = True, False
            case(f"{lo}-hold-fresh-window-after-{hi}-ends", check(held), 2)
            live[low] = False
        # the first hold that blocks wins (push, background, dirty) and no lower hold is started on that call
        marks = ("A git push or commit", "Background work", "uncommitted path")
        for on, want in (((".push", ".bg", ".dirty"), marks[0]), ((".bg", ".dirty"), marks[1]), ((".dirty",), marks[2])):
            held, out = lane(f"first{on[0]}"), io.StringIO()
            live.update({s: s in on for s in live})
            with redirect_stderr(out):
                rc = check(held)
            case(f"{on[0][1:]}-hold-wins-and-starts-no-lower-hold",
                 [rc, [m in out.getvalue() for m in marks], [os.path.exists(sfile(held, s)) for s in live]],
                 [2, [m == want for m in marks], [s == on[0] for s in live]])
        live.update({s: False for s in live})
    live[".bg"] = True
    err = io.StringIO()
    with redirect_stderr(err):
        check({"agent_id": "bgtext", "cwd": "/idle", "last_assistant_message": "VERIFIED"})
    live[".bg"] = False
    case("bg-hold-text-names-the-way-out-not-ownership",
         [s in err.getvalue() for s in ("You own", "lane_guard.py wait", "if this lane started it", f"after {PUSH_MAX_S} s")], [False, True, True, True])
    _bg_mode, _bg_running, _dirty_tree = real_scans
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
    mdir = os.path.join(tmp, "main")  # a lane worktree nested under the main checkout must not look like main's push
    wt = os.path.join(mdir, "wt-x")
    os.makedirs(os.path.join(mdir, "sub"))
    os.makedirs(os.path.join(mdir, ".git"))
    os.makedirs(wt)
    open(os.path.join(wt, ".git"), "w").close()
    def _ps_with(cmd, *rows, cwd=""):  # pid 123 (ppid 1) runs `cmd`; `rows` are extra "pid ppid command" lines; lsof says every pid sits in `cwd`
        def run(argv, **k):
            out = "".join(f"{r}\n" for r in (f"123 1 {cmd}", *rows)) if argv[0] == "ps" else f"n{cwd}\n" if cwd else ""
            return subprocess.CompletedProcess(argv, 0, out, "")
        return run
    subprocess.run = _ps_with(f"git -C {wt} push origin x")
    try:
        case("nested-worktree-push-not-main-push", _push_running(mdir), False)
        case("nested-worktree-push-is-own-push", _push_running(wt), True)
        subprocess.run = _ps_with(f"git -C {mdir}/sub push origin x")
        case("subdir-push-is-own-push", _push_running(mdir), True)
        sm = os.path.join(mdir, "vendor", "sm")  # submodule: its .git file points into .../modules/, same tree as main
        os.makedirs(sm)
        with open(os.path.join(sm, ".git"), "w") as f:
            f.write("gitdir: ../../.git/modules/sm\n")
        subprocess.run = _ps_with(f"git -C {sm} push origin x")
        case("submodule-push-is-own-push", _push_running(mdir), True)
        subprocess.run = _ps_with(f"git -C {wt} commit -m x")  # a live commit (slow pre-commit hook) is held like a push
        case("nested-worktree-commit-not-main-commit", _push_running(mdir), False)
        case("nested-worktree-commit-is-own-commit", _push_running(wt), True)
        brief = "git commit -m Fix it"  # a live commit whose pre-commit hook runs this hook: an ancestor, not a bystander; its cwd is the lane worktree
        me = os.getpid()
        subprocess.run = _ps_with(brief, f"{me} 123 python3 handback_cap.py", cwd=wt)
        case("ancestor-with-git-commit-in-argv-not-counted", _push_running(wt), False)
        subprocess.run = _ps_with(brief, f"{me} 124 python3 handback_cap.py", "124 123 sh -c handback_cap.py", cwd=wt)
        case("grandparent-with-git-commit-in-argv-not-counted", _push_running(wt), False)
        subprocess.run = _ps_with(brief, f"{me} 1 python3 handback_cap.py", cwd=wt)
        case("unrelated-git-commit-still-counted", _push_running(wt), True)
        for who, row in (("sibling-claude-brief", "claude -p Implement X. Never run git commit --no-verify. Report when done"),
                         ("shell-string", "zsh -c sleep 900; echo remember to git commit later"), ("grep", "grep -rn git commit docs")):
            subprocess.run = _ps_with(row, f"{me} 1 python3 handback_cap.py", cwd=wt)  # a process that only names the words, not an ancestor either
            case(f"{who}-naming-git-commit-not-counted", _push_running(wt), False)
        subprocess.run = _ps_with("sleep 1", f"{me} 1 python3 handback_cap.py", f"124 {me} sh -c lsof", "125 124 git commit -m x", cwd=wt)
        case("descendant-with-git-commit-in-argv-not-counted", _push_running(wt), False)
        subprocess.run = lambda argv, **k: subprocess.CompletedProcess(argv, 0, "garbage\n", "")
        case("ps-unparseable-is-unknown-not-false", _push_running(wt), None)
        # known limit: ps prints argv without quotes, so a space inside a -c value or a -C path splits it and PUSH_RE no longer matches: not held (fails open)
        subprocess.run = _ps_with("git -c user.name=Jane commit -m x", cwd=wt)
        case("known-limit-control-dash-c-without-space-is-held", _push_running(wt), True)
        for who, row in (("dash-c-value-with-space", "git -c user.name=Jane Smith commit -m x"), ("dash-C-path-with-space", "git -C /acme/my repo commit -m x")):
            subprocess.run = _ps_with(row, cwd=wt)
            case(f"known-limit-{who}-is-not-held", _push_running(wt), False)
    finally:
        subprocess.run = real_run
    ptab = _ps_table("400 1 claude -p brief\n450 400 sh -c hook\n500 450 python3 handback_cap.py\n510 500 sh -c lsof\n520 510 git commit -m x\n900 1 git commit -m y\n")
    skipped = _skip_pids(ptab, 500)  # hook 500: ancestors 450 and 400 (the walk up stops at a pid whose parent is 1), descendants 510 and 520
    case("skip-pids-skips-hook-ancestors-and-descendants", sorted(skipped), [400, 450, 500, 510, 520])
    case("skip-pids-leaves-only-the-unrelated-git-commit", sorted(p for p, (_, c) in ptab.items() if PUSH_RE.search(c) and p not in skipped), [900])
    def cd(c):
        m = PUSH_RE.search(c)
        return m and (m.group(2) or m.group(3) or m.group(4))
    case("git-dash-C-push-matches", cd("git -C /w/x push -q origin main"), "/w/x")
    case("git-dash-C-quoted-space-matches", cd('git -C "/w/dir w/ space" push'), "/w/dir w/ space")
    case("git-dash-c-kv-push-matches", bool(PUSH_RE.search("git -c core.x=1 push origin main")), True)
    case("git-dash-c-then-C-matches", cd("git -c a=b -C /w/y push"), "/w/y")
    case("plain-git-push-matches", bool(PUSH_RE.search("git push origin")), True)
    case("git-status-does-not-match", bool(PUSH_RE.search("git status --push")), False)
    case("plain-git-commit-matches", bool(PUSH_RE.search("git commit -m x")), True)
    case("git-dash-C-commit-matches", cd("git -C /w/x commit -q -m x"), "/w/x")
    case("wrapped-git-commit-matches",  # the second form is how ps prints the same argv: no quotes
         [bool(PUSH_RE.search(c)) for c in ("perl -e 'alarm 30; exec @ARGV' git commit -m x", "perl -e alarm 30; exec @ARGV git commit -m x")], [True, True])
    case("env-wrapped-git-commit-and-push-match",
         [bool(PUSH_RE.search(c)) for c in ("env GIT_AUTHOR_NAME=x GIT_COMMITTER_NAME=y git commit -m x", "/usr/bin/env A=b git push origin x")], [True, True])
    case("perl-wrapped-git-push-matches",
         [bool(PUSH_RE.search(c)) for c in ("perl -e 'alarm 30; exec @ARGV' git push origin x", "perl -e alarm 30; exec @ARGV git push origin x")], [True, True])
    case("path-qualified-git-matches", [bool(PUSH_RE.search(c)) for c in ("/usr/bin/git commit -m x", "/opt/homebrew/bin/git -C /w/x push")], [True, True])
    case("words-in-another-argv0-do-not-match",  # a lane brief, a shell string, a grep, and names that merely end in git
         [bool(PUSH_RE.search(c)) for c in ("claude -p Implement X. Never run git commit --no-verify. Report when done", "zsh -c sleep 900; echo remember to git commit later",
                                            "grep -rn git commit docs", "echo git push", "mygit commit -m x", "/opt/legit/bin/legit push")], [False] * 6)
    case("git-commit-tree-does-not-match", bool(PUSH_RE.search("git commit-tree HEAD^{tree}")), False)
    case("git-commit-graph-does-not-match", bool(PUSH_RE.search("git commit-graph write")), False)
    case("git-push-x-does-not-match", bool(PUSH_RE.search("git push-x origin")), False)
    case("git-log-grep-commit-does-not-match", bool(PUSH_RE.search("git log --grep commit")), False)

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

    # narration nudge: 3 calls with 60 tok prose each -> rate 60.0 and a systemMessage; a quiet lane stays silent
    import io
    from contextlib import redirect_stdout
    big = tr(*[b for _ in range(3) for b in (asst({"type": "text", "text": "n" * 240}), asst({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}))],
             asst({"type": "text", "text": "status=VERIFIED"}))
    os.environ["HANDBACK_AUDIT_LEDGER"] = os.path.join(tmp, "nl.jsonl")

    def run_main(path, aid):
        real, buf = sys.stdin, io.StringIO()
        sys.stdin = io.StringIO(json.dumps({"agent_id": aid, "agent_type": "builder", "agent_transcript_path": path, "last_assistant_message": "status=VERIFIED"}))
        try:
            with redirect_stdout(buf):
                main()
        finally:
            sys.stdin = real
        return buf.getvalue()
    try:
        out = run_main(big, "N1")
        case("narration-nudge-fires-over-limit", ("narration:" in out and "~180 tokens" in out and "60.0/call" in out), True)
        case("narration-rate-logged", json.loads(open(os.environ["HANDBACK_AUDIT_LEDGER"]).readline())["narr_rate"], 60.0)
        case("narration-quiet-lane-silent", run_main(t, "N2"), "")
        os.environ["HANDBACK_NARR_NUDGE"] = "0"
        case("narration-nudge-off-switch", run_main(big, "N3"), "")
    finally:
        os.environ.pop("HANDBACK_AUDIT_LEDGER", None)
        os.environ.pop("HANDBACK_NARR_NUDGE", None)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if {"--report", "--scan", "-h", "--help"} & set(sys.argv):
        sys.exit(_cli(sys.argv[1:]))
    sys.exit(main())
