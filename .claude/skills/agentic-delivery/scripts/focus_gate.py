#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=no work outside the owner's open priority until it is done or blocked, review=2027-01-30
"""focus_gate.py — no work outside the owner's open priority until that priority is done or blocked.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
Agent fleets repeatedly stopped working on the owner's main priority before it
was finished and drifted to cheaper, more visible items. The prose rule ("an
open owner priority outranks every other item") existed and did not fire: every
drifting lane had a locally plausible reason to move on. This gate turns the
rule into a blocking fact. The owner writes the priority down once; the
priority is DONE only when its acceptance command exits 0, never when a lane
judges it "close enough".

THE RULE
--------
  status  NONE     no record at --rev and none ever existed in its (complete)
                   history, or an owner-trusted commit deleted it: nothing to
                   focus on. A shallow clone cannot prove "never existed" -> OPEN.
          OPEN     the record is trusted, its acceptance command did not exit 0,
                   and no valid blocker row exists — or the record is unreadable,
                   malformed, not owner-authored, or deleted by a non-owner (fail
                   closed: never DONE, and an untrusted scope puts nothing in scope).
          DONE     the acceptance command exited 0 in a clean detached worktree of
                   --rev (`git worktree add --detach`, removed afterwards), never
                   the working tree. Evidence: the sha actually tested, exit code,
                   duration, output tail. A DONE is cached under .git/, keyed by
                   record hash + tested sha, so an unchanged check does not re-run
                   the command (--no-cache disables it).
          BLOCKED  not DONE, and at least one blocker row names another party
                   AND an http(s) evidence link. A row without both is
                   reported as rejected and the priority stays OPEN.
  check   GO       the priority is NONE (with a notice), DONE, or BLOCKED, or
                   the item/paths are inside the priority scope.
          NO-GO    the priority is OPEN and the item/paths are outside scope.
  In scope means: (the item is a scope ref, or every changed path matches a
  scope glob) AND no changed path falls outside the globs — tagging a change
  with the priority's issue number does not carry unrelated paths in with it,
  and a refs-only record puts every changed path outside.
  Oracle guard: when the priority is DONE but the change touches a path named
  in the acceptance command that is outside scope (the reference design, the
  differ script), the DONE is unproven for that change and the verdict is
  NO-GO — land oracle changes separately, owner-reviewed. Without --head the
  guard also counts uncommitted working-tree edits.

RECORD GRAMMAR (default path `.claude/PRIORITY.md`; read from the committed
blob at `--rev`, never from the working tree, so an uncommitted edit is inert)
------------------------------------------------------------------------------
Only lines of the form `key: value` (optionally led by `- ` or `* `) with the
keys below are parsed; every other line (headings, prose) is ignored.
  priority: <id>                         exactly one; required
  scope: <token> [<token> ...]           repeatable; tokens split on space/comma.
                                         `#123` (any `#`-led token) is an item
                                         ref; anything else is a path glob
                                         (`**`, `*`, `?`; fix_class_gate grammar)
  acceptance: <shell command>            exactly one; one pair of surrounding
                                         backticks is stripped. Missing or
                                         duplicated -> OPEN, never DONE
  acceptance-trivial-ok: <reason>        owner line allowing a trivially-true
                                         acceptance (below)
  blocker: <party> | <evidence-url> | <note>
                                         repeatable; owner-accepted blocker
  owner-quote: <YYYY-MM-DD> | <where said> | <verbatim text>
                                         repeatable; the quote route (below)
Example:
  priority: design-alignment
  scope: app/screens/** #123 #124
  acceptance: python3 tools/parity_differ.py design.html app.html
  blocker: design vendor | https://example.com/tickets/42 | final spec pending

TRUST (same authorship rule as the standing grant in agentic-delivery SKILL.md)
-------------------------------------------------------------------------------
Route 1, owner commit (the default and, without --allow-quote, the only route):
the last commit touching the record AND every commit that authored a surviving
line (`git blame`) must have an author email in the owner set, carry no
`Co-authored-by:` trailer (an agent-assisted commit is not the owner's own),
and, with --require-signed, a good signature (`%G?` = G). Route 2, owner quote
(only with --allow-quote): a quote row counts only when its own line is blamed
to such an owner commit — a record cannot vouch for itself — and then every
scope token and every valid blocker's party and evidence must appear as whole
tokens in those quotes, and the acceptance command as an exact backtick-quoted
span (`...`); a substring never matches. Owner set, first non-empty of:
--owner-email (repeatable), env DCR_OWNER_EMAIL (comma/space separated; in CI
set it from protected configuration), `git config --get-all dcr.owner` (a local
fallback that warns "unprotected owner identity": any process with write access
to the repository or home directory can edit it). None -> untrusted -> OPEN.
The acceptance command of an untrusted record is NEVER executed.
Rejected even in a trusted record: a scope glob made only of `*`, `/`, `?`
(`**`, `*`, `**/*`: too broad -> the record is untrusted), and a trivially-true
acceptance (`true`, `:`, `exit 0`, `ls`, `echo ...`, `... || true`, a pipe into
`cat`) -> OPEN, never DONE, unless an owner-authored `acceptance-trivial-ok:`
line is present.

WHAT IS ENFORCED, AND THE RESIDUAL
----------------------------------
Enforced: a record line, last touch, or deletion by an identity outside the
owner set, or by an owner commit carrying a Co-authored-by trailer, makes the
record untrusted (OPEN, nothing in scope) or the deletion NO-GO — so a lane
committing under its own identity or attribution convention cannot create,
widen, narrow, close, or delete the priority. Residual: an agent that holds the
owner's git identity AND commit access can forge all of it, because a commit
author email is unauthenticated metadata; --require-signed with a signing key
the agent cannot use is the only hard guarantee.

HONESTY (what this cannot prove)
--------------------------------
The owner-email setting is the trust root: in CI set DCR_OWNER_EMAIL from
protected configuration, not from a file the change under review can edit. The
quote route cannot authenticate a quote beyond its line's blame. The trivial
list is a heuristic denylist, not a proof that a command tests anything. The
DONE cache is a file any local process can write; CI starts from a fresh clone,
and --no-cache removes the cache from the trust path. The oracle guard covers
paths named literally in the acceptance command, not their transitive imports.
DONE proves the owner's own acceptance command passed on the tested sha; it
cannot judge whether that command is the right test.

EXIT CODES
----------
  check:  0 GO      1 NO-GO (including every fail-closed OPEN)   2 usage/range error
  status: 0 DONE    1 OPEN    3 BLOCKED    4 NONE                2 usage error

USAGE
-----
  focus_gate.py status [common options] [--evidence FILE]
  focus_gate.py check  [common options] [--item REF] [--paths P ...] [--base REF --head REF]
  focus_gate.py --selftest
common options: --record PATH (.claude/PRIORITY.md)  --rev REV (HEAD; --head when given)
                --owner-email E ...  --allow-quote  --require-signed  --no-cache
                --timeout SECONDS (900)  --repo DIR (.)
                (--commit-only is accepted and is the default)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

sys.dont_write_bytecode = True
from refix_gate import load_fix_class_gate  # noqa: E402  (sibling script; one loader)

GO, NO_GO, ERROR = 0, 1, 2
S_DONE, S_OPEN, S_BLOCKED, S_NONE = "DONE", "OPEN", "BLOCKED", "NONE"
STATUS_EXIT = {S_DONE: 0, S_OPEN: 1, S_BLOCKED: 3, S_NONE: 4}
DEFAULT_RECORD = ".claude/PRIORITY.md"
DEFAULT_TIMEOUT = 900.0
ZERO_SHA = "0" * 40
MAX_STATUS_LINES = 10
CACHE_FILE = "focus_gate-done.json"
CACHE_MAX_ENTRIES = 64
UNPROTECTED_OWNER = ("unprotected owner identity: owner taken from `git config dcr.owner`, which any "
                     "local process can edit; set DCR_OWNER_EMAIL from protected configuration")

GitRunner = Callable[[list], str]
# (command, cwd, timeout_seconds) -> (exit_code, combined stdout+stderr). Raises on
# timeout / spawn failure; the caller turns any exception into OPEN.
CmdRunner = Callable[[str, str, float], tuple]

_KEY_RE = re.compile(r"^\s*(?:[-*]\s+)?(acceptance-trivial-ok|priority|scope|acceptance|blocker|owner-quote)"
                     r"\s*:\s*(.*?)\s*$", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://\S+$")
_SELF_PARTIES = {"self", "me", "us", "we", "agent", "the agent", "this agent", "lane", "this lane", "myself"}
_BLAME_HEADER_RE = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
_TRIVIAL_WORDS = {"true", ":", "ls", "echo", "printf", "pwd"}
_PIPE_TAIL_TRUE = _TRIVIAL_WORDS | {"cat", "tee", "head", "tail", "wc", "sort", "uniq"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class GitError(RuntimeError):
    """A git invocation failed; the caller must fail closed."""


def real_git(repo: str = ".") -> GitRunner:
    """Return a runner executing `git -C repo <args>`; raises GitError on a non-zero exit."""
    def run(args: list) -> str:
        proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed (rc={proc.returncode})")
        return proc.stdout
    return run


def real_cmd(command: str, cwd: str, timeout: float) -> tuple:
    """Run the owner's acceptance command through the shell; return (exit_code, combined output).

    Side effect: executes an arbitrary shell command — callers only reach this for a
    TRUSTED record. Raises subprocess.TimeoutExpired / OSError, which the caller maps
    to OPEN (a command that could not finish never proves DONE).
    """
    proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


@dataclass
class Record:
    """The parsed priority record. `fatal` non-empty means the scope cannot be trusted.

    Line numbers are 1-based and match `git blame` final line numbers, so a single
    row (an owner quote, the trivial-ok flag) can be checked for its own author.
    """
    priority: str = ""
    globs: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    raw_scope: list = field(default_factory=list)
    acceptance: str | None = None
    acceptance_note: str = ""
    blockers: list = field(default_factory=list)          # [(party, evidence, note)]
    rejected_blockers: list = field(default_factory=list)  # [(raw, reason)]
    quotes: list = field(default_factory=list)            # [(date, where, text, line_no)]
    trivial_ok_lines: list = field(default_factory=list)  # line numbers of acceptance-trivial-ok rows
    fatal: list = field(default_factory=list)
    digest: str = ""                                      # sha256 of the record text (cache key)


def _norm_ref(token: str) -> str:
    """`#123`, `123`, `#ENG-7` -> case-folded id without the leading `#`."""
    return token.strip().lstrip("#").casefold()


def _norm_path(path: str) -> str:
    """Repo-relative, `/`-separated, no leading `./`."""
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _strip_ticks(value: str) -> str:
    """Remove one pair of surrounding backticks (markdown inline code)."""
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def parse_record(text: str) -> Record:
    """Parse the record grammar (module docstring). Pure; never raises.

    Edge cases: zero or several `priority:` lines, or a scope glob made only of
    `*`/`/`/`?` (too broad) -> fatal (scope untrusted); zero or several
    `acceptance:` lines -> acceptance None with a note (OPEN, never DONE); a
    blocker without another party or an http(s) evidence link, and a malformed
    owner-quote row, are kept aside as rejected rather than honoured. The
    trivially-true acceptance rule needs authorship, so load_record applies it.
    """
    rec = Record(digest=hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest())
    priorities, acceptances = [], []
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = _KEY_RE.match(line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2)
        if key == "priority":
            priorities.append(value)
        elif key == "scope":
            for tok in re.split(r"[\s,]+", value):
                tok = _strip_ticks(tok.strip())
                if not tok:
                    continue
                rec.raw_scope.append(tok)
                if tok.startswith("#"):
                    if _norm_ref(tok):
                        rec.refs.append(_norm_ref(tok))
                    continue
                glob = _norm_path(tok)
                if set(glob) <= set("*/?"):
                    rec.fatal.append(f"scope token {tok!r} is too broad (matches everything)")
                else:
                    rec.globs.append(glob)
        elif key == "acceptance":
            acceptances.append(_strip_ticks(value))
        elif key == "acceptance-trivial-ok":
            if value:
                rec.trivial_ok_lines.append(line_no)
        elif key == "blocker":
            parts = [p.strip() for p in value.split("|")]
            party = parts[0] if parts else ""
            evidence = parts[1] if len(parts) > 1 else ""
            note = " | ".join(parts[2:]) if len(parts) > 2 else ""
            if not party or party.casefold() in _SELF_PARTIES:
                rec.rejected_blockers.append((value, "names no other party"))
            elif not _URL_RE.match(evidence):
                rec.rejected_blockers.append((value, "no http(s) evidence link"))
            else:
                rec.blockers.append((party, evidence, note))
        elif key == "owner-quote":
            parts = [p.strip() for p in value.split("|", 2)]
            if len(parts) == 3 and all(parts):
                try:
                    date.fromisoformat(parts[0])
                except ValueError:
                    continue
                quote = parts[2]
                if len(quote) >= 2 and quote[0] == quote[-1] and quote[0] in "\"'":
                    quote = quote[1:-1]
                if quote:
                    rec.quotes.append((parts[0], parts[1], quote, line_no))
    if len(priorities) != 1 or not priorities[0]:
        rec.fatal.insert(0, f"expected exactly one non-empty `priority:` line, found {len(priorities)}")
    else:
        rec.priority = priorities[0]
    if not acceptances or not acceptances[0]:
        rec.acceptance_note = "acceptance command missing"
    elif len(acceptances) > 1:
        rec.acceptance_note = f"ambiguous: {len(acceptances)} `acceptance:` lines"
    else:
        rec.acceptance = acceptances[0]
    return rec


def _simple_words(words: list) -> list:
    """Drop leading `VAR=value` assignments from one simple command's words."""
    i = 0
    while i < len(words) and _ENV_ASSIGN_RE.match(words[i]):
        i += 1
    return words[i:]


def _always_zero(words: list, pipe_tail: bool = False) -> bool:
    """True when this simple command exits 0 regardless of the tree under test."""
    words = _simple_words(words)
    if not words:
        return False
    if words[0] == "exit":
        return words[1:] in ([], ["0"])
    return words[0] in (_PIPE_TAIL_TRUE if pipe_tail else _TRIVIAL_WORDS)


def trivially_true(command: str) -> str:
    """Why `command` exits 0 no matter what it runs against, or "" when it may fail.

    Heuristic over shell tokens (quotes respected): the exit status is the last
    `;`/newline statement's; that statement is trivially true when any `||`
    alternative after the first is, or when every `&&` part of the first ends in a
    trivially-true command (a pipeline's status is its last command's, so `x | cat`
    counts). Unparseable input returns "" (the command just runs). Pure.
    """
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    try:
        toks = list(lexer)
    except ValueError:
        return ""
    stmts, cur = [], []
    for t in toks:
        if t == ";" or (t == "&" and not (cur and cur[-1][-1:] in "<>")):  # `2>&1` is a redirect
            stmts.append(cur)
            cur = []
        else:
            cur.append(t)
    stmts.append(cur)
    stmts = [s for s in stmts if s]
    if not stmts:
        return ""
    alts, cur = [], []
    for t in stmts[-1]:
        if t == "||":
            alts.append(cur)
            cur = []
        else:
            cur.append(t)
    alts.append(cur)

    def alt_true(words: list) -> bool:
        parts, cur2 = [], []
        for t in words:
            if t == "&&":
                parts.append(cur2)
                cur2 = []
            else:
                cur2.append(t)
        parts.append(cur2)
        for part in parts:
            pipe = [[]]
            for t in part:
                if t == "|":
                    pipe.append([])
                else:
                    pipe[-1].append(t)
            if not _always_zero(pipe[-1], pipe_tail=len(pipe) > 1):
                return False
        return True

    for alt in alts[1:]:
        if alt_true(alt):
            return f"`|| {' '.join(alt)}` always exits 0"
    if alt_true(alts[0]):
        return f"`{' '.join(stmts[-1])}` always exits 0"
    return ""


def resolve_owners(explicit: list | None, git: GitRunner, env: dict | None = None) -> tuple:
    """(owner emails case-folded, warning): --owner-email, else DCR_OWNER_EMAIL, else git config.

    The `git config dcr.owner` fallback returns the "unprotected owner identity"
    warning: repository and user git config are editable by the process being gated.
    """
    env = os.environ if env is None else env
    warning = ""
    if explicit:
        vals = explicit
    elif env.get("DCR_OWNER_EMAIL", "").strip():
        vals = re.split(r"[,\s]+", env["DCR_OWNER_EMAIL"])
    else:
        try:
            vals = git(["config", "--get-all", "dcr.owner"]).split()
        except GitError:
            vals = []
        if any(v.strip() for v in vals):
            warning = UNPROTECTED_OWNER
    return sorted({v.strip().strip("<>").casefold() for v in vals if v.strip()}), warning


def _commit_meta(git: GitRunner, sha: str) -> tuple:
    """(author_email_casefolded, signature_status, has_coauthor_trailer) for one commit."""
    out = git(["show", "-s", "--format=%ae%x1f%G?%x1f%(trailers:key=Co-authored-by,valueonly)", sha])
    parts = out.split("\x1f")
    if len(parts) != 3:
        raise GitError(f"unparseable commit metadata for {sha[:12]}")
    return parts[0].strip().casefold(), parts[1].strip(), bool(parts[2].strip())


def _owner_problem(git: GitRunner, sha: str, owners: list, require_signed: bool) -> str:
    """"" when commit `sha` is the owner's own; else why not. Raises GitError."""
    email, sig, coauthor = _commit_meta(git, sha)
    if email not in owners:
        return f"{sha[:7]} by {email or '?'} is not the owner"
    if coauthor:
        return f"{sha[:7]} carries a Co-authored-by trailer (agent-assisted)"
    if require_signed and sig != "G":
        return f"{sha[:7]} has no good signature (%G?={sig or '?'})"
    return ""


def _quote_tokens(text: str) -> list:
    """Whitespace tokens with surrounding quotes/brackets and trailing punctuation removed."""
    out = []
    for tok in text.split():
        tok = tok.strip("\"'`()[]{}<>").rstrip(".,;:!?").strip("\"'`()[]{}<>")
        if tok:
            out.append(tok)
    return out


def _has_run(haystack: list, needle: list) -> bool:
    """True when `needle` occurs as a contiguous whole-token run inside `haystack`."""
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def _quote_claims_missing(rec: Record, quotes: list) -> list:
    """Record claims not stated by `quotes`: tokens as whole tokens, acceptance as an exact `span`."""
    tokens = [t for q in quotes for t in _quote_tokens(q[2])]
    spans = {" ".join(s.split()) for q in quotes for s in re.findall(r"`([^`]+)`", q[2])}
    missing = [c for c in rec.raw_scope if not _has_run(tokens, _quote_tokens(c))]
    for party, evidence, _ in rec.blockers:
        missing += [c for c in (party, evidence) if not _has_run(tokens, _quote_tokens(c))]
    if rec.acceptance and " ".join(rec.acceptance.split()) not in spans:
        missing.append(rec.acceptance)
    return missing


def _apply_trivial_rule(rec: Record, flag_trusted: bool) -> None:
    """Void a trivially-true acceptance unless an owner-authored acceptance-trivial-ok line exists."""
    why = trivially_true(rec.acceptance) if rec.acceptance else ""
    if why and not flag_trusted:
        rec.acceptance_note = (f"trivially-true acceptance rejected ({why}); the owner may add "
                               "`acceptance-trivial-ok: <reason>`")
        rec.acceptance = None


def load_record(git: GitRunner, path: str, rev: str, owners: list,
                allow_quote: bool = False, require_signed: bool = False) -> tuple:
    """Read and authenticate the record at `rev:path`.

    Returns (record | None, trusted: bool, source: str, reasons: list[str]). With no
    record, source is "never" (no commit in the complete history ever touched the
    path), "owner-deleted" (an owner-trusted commit removed it: trusted True), or
    "none"/"deleted" (fail closed). Never raises: a git failure is untrusted/OPEN.
    """
    try:
        git(["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"])
    except GitError:
        return None, False, "none", [f"revision {rev!r} does not resolve (fail closed: OPEN)"]
    try:
        text = git(["show", f"{rev}:{path}"])
    except GitError:
        try:
            last = git(["log", "-1", "--format=%H", rev, "--", path]).strip()
            shallow = git(["rev-parse", "--is-shallow-repository"]).strip() == "true"
        except GitError as exc:
            return None, False, "none", [f"record history unreadable at {rev}:{path}: {exc} (fail closed: OPEN)"]
        if not last:
            if shallow:
                why = (f"no record at {rev}:{path}, and a shallow clone cannot prove none ever existed "
                       "(fail closed: OPEN; fetch full history)")
                return None, False, "none", [why]
            return None, True, "never", [f"no priority record ever existed at {rev}:{path}"]
        if not owners:
            return None, False, "deleted", [f"record deleted at {last[:7]}; no owner configured to verify it"]
        try:
            why = _owner_problem(git, last, owners, require_signed)
        except GitError as exc:
            why = f"deletion {last[:7]} unverifiable: {exc}"
        if why:
            return None, False, "deleted", [f"record deleted at {last[:7]} by a non-owner: {why} (NO-GO)"]
        return None, True, "owner-deleted", [f"priority record deleted by the owner at {last[:7]}"]
    rec = parse_record(text)
    if not owners:
        return rec, False, "untrusted", [
            "no owner email configured (--owner-email, DCR_OWNER_EMAIL, or git config dcr.owner)"]
    reasons: list = []
    owner_ok: set = set()
    line_sha: dict = {}
    last_line = ""
    try:
        last_line = git(["log", "-1", "--format=%H", rev, "--", path]).strip()
        blame = git(["blame", "--porcelain", rev, "--", path])
        for ln in blame.splitlines():
            m = _BLAME_HEADER_RE.match(ln)
            if m:
                line_sha[int(m.group(2))] = m.group(1)
        content_lines = sum(1 for ln in blame.splitlines() if ln.startswith("\t"))
        shas = set(line_sha.values()) | ({last_line} if last_line else set())
        if not shas or not content_lines:
            reasons.append("record has no committed lines")
        for sha in sorted(shas):
            why = _owner_problem(git, sha, owners, require_signed)
            if why:
                reasons.append(f"{'last touch' if sha == last_line else 'line author'} {why}")
            else:
                owner_ok.add(sha)
    except GitError as exc:
        reasons.append(f"authorship unverifiable: {exc}")
        owner_ok.clear()
    flag_trusted = any(line_sha.get(n) in owner_ok for n in rec.trivial_ok_lines)
    if not reasons:
        _apply_trivial_rule(rec, flag_trusted)
        return rec, True, f"owner-commit {last_line[:7]}", []
    if not rec.quotes:
        return rec, False, "untrusted", reasons
    if not allow_quote:
        return rec, False, "untrusted", reasons + ["owner-quote route is off (commit-only default; --allow-quote)"]
    vouched = [q for q in rec.quotes if line_sha.get(q[3]) in owner_ok]
    if not vouched:
        return rec, False, "untrusted", reasons + [
            "no owner-quote line is itself owner-authored (a record cannot vouch for itself)"]
    missing = _quote_claims_missing(rec, vouched)
    if missing:
        return rec, False, "untrusted", reasons + [
            "owner-quote does not contain: " + ", ".join(repr(c) for c in missing[:4])]
    _apply_trivial_rule(rec, flag_trusted)
    d, where, _, _ = vouched[0]
    return rec, True, f"owner-quote {d} ({where})", []


@dataclass
class Status:
    """Computed priority state plus the evidence lines that justify it."""
    state: str
    trusted: bool
    record: Record | None
    source: str
    reasons: list
    acceptance_rc: int | None = None
    acceptance_secs: float | None = None
    tail: list = field(default_factory=list)
    head: str = ""
    tested: str = ""
    cached: bool = False


def _tail(output: str, n: int = 3) -> list:
    """Last `n` non-empty output lines, each capped at 160 chars."""
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    return [ln[:160] for ln in lines[-n:]]


def _cache_read(path: str | None) -> dict:
    """The DONE cache mapping, or {} when absent/unreadable (the cache is only a speed-up)."""
    if not path:
        return {}
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _cache_put(path: str | None, key: str, entry: dict) -> None:
    """Record one DONE result (side effect: rewrites `path` atomically; errors ignored)."""
    if not path:
        return
    doc = _cache_read(path)
    doc.pop(key, None)
    doc[key] = entry
    doc = dict(list(doc.items())[-CACHE_MAX_ENTRIES:])
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".focus_gate-")
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def _run_clean(git: GitRunner, run_cmd: CmdRunner, command: str, sha: str, timeout: float) -> tuple:
    """Run `command` in a throwaway detached worktree of `sha`; always remove it.

    Side effects: `git worktree add --detach` into a temp dir, then `worktree remove
    --force` and `worktree prune`. Raises GitError when the checkout fails, and
    whatever `run_cmd` raises.
    """
    parent = tempfile.mkdtemp(prefix="focus_gate_wt_")
    tree = os.path.join(parent, "tree")
    try:
        git(["worktree", "add", "--detach", tree, sha])
        try:
            return run_cmd(command, tree, timeout)
        finally:
            for args in (["worktree", "remove", "--force", tree], ["worktree", "prune"]):
                try:
                    git(args)
                except GitError:
                    pass
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def evaluate(git: GitRunner, run_cmd: CmdRunner, record_path: str, rev: str, owners: list,
             timeout: float, allow_quote: bool = False, require_signed: bool = False,
             cache_path: str | None = None) -> Status:
    """Compute NONE / OPEN / DONE / BLOCKED. Runs the acceptance command only for a trusted record.

    Fail-closed order: rev resolves -> record present (or provably never existed /
    owner-deleted -> NONE) -> authorship trusted -> grammar sound -> acceptance
    present and not trivially true -> acceptance exits 0 in a clean worktree of the
    resolved rev sha. Any step failing leaves OPEN. A DONE for (record digest, sha)
    found in `cache_path` is reused instead of re-running; a new DONE is stored there.
    """
    rec, trusted, source, reasons = load_record(git, record_path, rev, owners, allow_quote, require_signed)
    try:
        head = git(["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"]).strip()
    except GitError:
        head = ""
    if rec is None and trusted:
        return Status(S_NONE, True, None, source, list(reasons), head=head)
    st = Status(S_OPEN, trusted, rec, source, list(reasons), head=head)
    if rec is None or not trusted:
        return st
    if rec.fatal:
        st.trusted = False
        st.reasons += rec.fatal
        return st
    if rec.acceptance is None:
        st.reasons.append(f"{rec.acceptance_note} -> OPEN, never DONE")
    elif not head:
        st.reasons.append(f"revision {rev!r} does not resolve; acceptance not run")
    else:
        key = f"{rec.digest}:{head}"
        hit = _cache_read(cache_path).get(key)
        if isinstance(hit, dict) and hit.get("exit") == 0:
            st.state, st.tested, st.cached = S_DONE, head, True
            st.acceptance_rc, st.acceptance_secs = 0, hit.get("seconds")
            st.tail = [str(t) for t in hit.get("tail", [])][:3]
            return st
        started = time.monotonic()
        try:
            rc, out = _run_clean(git, run_cmd, rec.acceptance, head, timeout)
            st.acceptance_rc, st.tail, st.tested = rc, _tail(out), head
        except GitError as exc:
            st.reasons.append(f"clean checkout of {head[:12]} failed: {exc}")
        except Exception as exc:  # timeout, spawn failure: never proof of DONE
            st.reasons.append(f"acceptance did not complete: {type(exc).__name__}")
        st.acceptance_secs = round(time.monotonic() - started, 2)
        if st.acceptance_rc == 0:
            st.state = S_DONE
            _cache_put(cache_path, key, {"exit": 0, "seconds": st.acceptance_secs, "tail": st.tail,
                                         "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
            return st
    if rec.blockers:
        st.state = S_BLOCKED
    return st


def status_lines(st: Status) -> list:
    """At most MAX_STATUS_LINES human-readable lines stating the verdict and its evidence."""
    rec = st.record
    pid = rec.priority if rec and rec.priority else "?"
    lines = [f"focus_gate: {st.state} priority={pid} source={st.source}"
             + (f" rev={st.head[:12]}" if st.head else "")]
    if rec and st.trusted:
        lines.append(f"scope: {len(rec.globs)} glob(s), {len(rec.refs)} ref(s): "
                     + " ".join(rec.raw_scope)[:140])
    if rec and st.trusted and rec.acceptance:
        rc = "not run" if st.acceptance_rc is None else f"exit {st.acceptance_rc}"
        where = f" on {st.tested[:12]}" if st.tested else ""
        lines.append(f"acceptance: {rc}{where}{' (cached)' if st.cached else ''} in {st.acceptance_secs}s: "
                     f"{rec.acceptance[:120]}")
        lines += [f"  | {t}" for t in st.tail]
    if rec and st.trusted:
        for party, ev, _ in rec.blockers[:2]:
            lines.append(f"blocker: {party} evidence={ev[:100]}")
        if rec.rejected_blockers:
            lines.append(f"rejected blocker row(s): {len(rec.rejected_blockers)} "
                         f"({rec.rejected_blockers[0][1]})")
    for r in st.reasons:
        lines.append(f"{'notice' if st.state == S_NONE else 'reason'}: {r}")
    return lines[:MAX_STATUS_LINES]


def _range_paths(git: GitRunner, base: str, head: str) -> list:
    """Changed paths of merge-base(base, head)..head (NUL-safe, renames split). Raises GitError."""
    if base == ZERO_SHA:
        raise GitError("--base is the all-zeros SHA; pass the PR base ref")
    mb = git(["merge-base", base, head]).strip()
    if not mb:
        raise GitError(f"no merge base between {base} and {head}")
    out = git(["diff", "-z", "--name-only", "--no-renames", mb, head])
    return [p for p in out.split("\0") if p]


def _dirty_paths(git: GitRunner) -> list:
    """Uncommitted working-tree paths (staged, unstaged, untracked; NUL-safe). Raises GitError."""
    out = git(["status", "--porcelain", "-z", "--untracked-files=all", "--no-renames"])
    return [entry[3:] for entry in out.split("\0") if len(entry) > 3]


def _oracle_paths(command: str) -> set:
    """Repo-relative path tokens named literally in the acceptance command."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    return {_norm_path(t) for t in toks if t and not t.startswith("-") and not t.startswith("/")}


def check(st: Status, item: str | None, paths: list, fcg, dirty: list = ()) -> tuple:
    """GO / NO-GO for one item and/or change set against the computed status. Pure.

    `dirty` (uncommitted working-tree paths) feeds only the DONE oracle guard.
    """
    rec = st.record
    pid = rec.priority if rec and rec.priority else "?"
    label = item or f"{len(paths)} path(s)"
    paths = [_norm_path(p) for p in paths]
    if st.state == S_NONE:
        why = st.reasons[0] if st.reasons else "no priority record"
        return GO, [f"focus_gate: GO {label} — notice: {why}; no owner priority to focus on"]
    compiled = fcg._compile_globs(tuple(rec.globs)) if rec and rec.globs else []
    outside = [p for p in paths if not (compiled and fcg._matches_any(p, compiled))]
    if st.state == S_DONE:
        oracle = _oracle_paths(rec.acceptance or "")
        dirty_out = [p for p in map(_norm_path, dirty) if not (compiled and fcg._matches_any(p, compiled))]
        tampered = sorted(oracle & (set(outside) | set(dirty_out)))
        if tampered:
            return NO_GO, [f"focus_gate: NO-GO {label} — change touches the acceptance oracle outside "
                           f"scope ({', '.join(tampered[:3])}); DONE on the tested sha is unproven for it"]
        return GO, [f"focus_gate: GO {label} — priority {pid} is DONE (acceptance exit 0)"]
    if st.state == S_BLOCKED:
        party = rec.blockers[0][0]
        return GO, [f"focus_gate: GO {label} — priority {pid} is BLOCKED on {party} (evidence recorded)"]
    finish = f"; finish the priority first (acceptance: {rec.acceptance})" if rec and rec.acceptance else ""
    if not st.trusted:
        why = st.reasons[0] if st.reasons else "record untrusted"
        return NO_GO, [f"focus_gate: NO-GO {label} — priority is OPEN and its record is untrusted, "
                       f"so nothing is in scope ({why})"]
    ref_ok = bool(item) and _norm_ref(item) in rec.refs
    paths_ok = bool(paths) and not outside
    if (ref_ok or paths_ok) and not outside:
        return GO, [f"focus_gate: GO {label} — inside the scope of open priority {pid}"]
    if ref_ok and outside:
        detail = "in-scope ref but path(s) outside scope: " + ", ".join(outside[:3])
    elif outside:
        detail = "outside scope: " + ", ".join(outside[:3])
    else:
        detail = f"item {item} is not a scope ref"
    return NO_GO, [f"focus_gate: NO-GO {label} — priority {pid} is OPEN; {detail}{finish}"]


def write_evidence(path: str, st: Status) -> None:
    """Write the status evidence as JSON to `path` (side effect: creates/overwrites the file).

    `tested_sha` is the commit the acceptance command actually ran against (or whose
    cached DONE was reused); empty when the command did not run.
    """
    rec = st.record
    doc = {"state": st.state, "priority": rec.priority if rec else None, "source": st.source,
           "trusted": st.trusted, "head": st.head, "tested_sha": st.tested, "reasons": st.reasons,
           "acceptance": {"command": rec.acceptance if rec else None, "exit": st.acceptance_rc,
                          "seconds": st.acceptance_secs, "tail": st.tail, "cached": st.cached},
           "blockers": [{"party": p, "evidence": e, "note": n} for p, e, n in (rec.blockers if rec else [])],
           "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    Path(path).write_text(json.dumps(doc, indent=2) + "\n")


def _cache_location(git: GitRunner) -> str | None:
    """Absolute path of the DONE cache under the shared git dir, or None when unresolvable."""
    try:
        gitdir = git(["rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
    except GitError:
        return None
    return os.path.join(gitdir, CACHE_FILE) if gitdir else None


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
OWNER, AGENT = "owner@example.com", "lane-bot@example.com"
GOOD = ("# Owner priority\n\npriority: design-alignment\nscope: app/screens/** #12\n"
        "acceptance: `python3 tools/parity_differ.py design.html app/screens/home.html`\n")


def _fake_git(text: str | None, commits: dict, blame_shas: list, last: str | None = None,
              diff: list | None = None, sha: str = "f" * 40, shallow: bool = False,
              bad_rev: bool = False, config_owner: str = "", worktrees: list | None = None) -> GitRunner:
    """Offline git double: `commits` maps sha -> (email, sig, coauthor_value).

    `last` is the last commit touching the record path (default: the last blame sha
    when a record exists, "" = never existed when it does not). `worktrees` collects
    each `worktree` invocation.
    """
    if last is None:
        last = (blame_shas[-1] if blame_shas else "") if text is not None else ""

    def run(args: list) -> str:
        cmd = args[0]
        if cmd == "show" and args[1].startswith("-s"):
            email, sig, co = commits[args[-1]]
            return f"{email}\x1f{sig}\x1f{co}\n"
        if cmd == "show":
            if text is None:
                raise GitError("fatal: path does not exist")
            return text
        if cmd == "log":
            return last + "\n"
        if cmd == "blame":
            lines = (text or "").splitlines()
            out = []
            for i, ln in enumerate(lines):
                out.append(f"{blame_shas[i % len(blame_shas)]} {i + 1} {i + 1} 1")
                out.append(f"\t{ln}")
            return "\n".join(out) + "\n"
        if cmd == "rev-parse" and "--is-shallow-repository" in args:
            return "true\n" if shallow else "false\n"
        if cmd == "rev-parse":
            if bad_rev:
                raise GitError("fatal: bad revision")
            return sha + "\n"
        if cmd == "worktree":
            if worktrees is not None:
                worktrees.append(list(args))
            return ""
        if cmd == "merge-base":
            return "b" * 40 + "\n"
        if cmd == "diff":
            return "\0".join(diff or []) + ("\0" if diff else "")
        if cmd == "config":
            if config_owner:
                return config_owner + "\n"
            raise GitError("unset")
        raise GitError(f"unexpected git {args}")
    return run


def _fake_cmd(rc: int | None, calls: list, out: str = "MISMATCH home: 3 elements\n") -> CmdRunner:
    """Offline acceptance double; rc None simulates a timeout. Records each (command, cwd)."""
    def run(command: str, cwd: str, timeout: float) -> tuple:
        calls.append((command, cwd))
        if rc is None:
            raise subprocess.TimeoutExpired(command, timeout)
        return rc, out
    return run


def _selftest() -> int:
    """Assert every verdict branch on offline fixtures, then end to end on a real throwaway repo."""
    fcg = load_fix_class_gate()
    if fcg is None:
        print("SELFTEST FAILED: sibling deep-code-review/scripts/fix_class_gate.py not found")
        return 1
    failures: list = []
    ran = [0]
    O1, O2, A1 = "1" * 40, "2" * 40, "a" * 40
    owner_c = {O1: (OWNER, "N", ""), O2: (OWNER.upper(), "G", "")}
    agent_c = {A1: (AGENT, "N", "")}
    both_c = {**owner_c, **agent_c}

    def status_of(git, rc=1, owners=(OWNER,), calls=None, **kw):
        calls = [] if calls is None else calls
        return evaluate(git, _fake_cmd(rc, calls), DEFAULT_RECORD, "HEAD", list(owners), 5.0, **kw)

    def case(label, st, want_state=None, item=None, paths=(), want_rc=None, must=(), dirty=()):
        ran[0] += 1
        out = "\n".join(status_lines(st))
        if want_state and st.state != want_state:
            failures.append(f"{label}: state={st.state} want {want_state}: {out}")
        if len(status_lines(st)) > MAX_STATUS_LINES:
            failures.append(f"{label}: status exceeds {MAX_STATUS_LINES} lines")
        if want_rc is not None:
            rc, lines = check(st, item, list(paths), fcg, list(dirty))
            out = "\n".join(lines) + "\n" + out
            if rc != want_rc:
                failures.append(f"{label}: check rc={rc} want {want_rc}: {out}")
        failures.extend(f"{label}: missing {m!r}: {out}" for m in must if m not in out)

    owner_git = _fake_git(GOOD, owner_c, [O1, O2])
    st_open = status_of(owner_git, rc=1)
    case("open-in-scope-ref-go", st_open, S_OPEN, item="#12", want_rc=GO, must=("exit 1", "MISMATCH home"))
    case("open-in-scope-paths-go", st_open, S_OPEN, paths=["app/screens/home.html"], want_rc=GO)
    # Planted drift: a cosmetic item outside the open priority FIRES.
    case("outside-scope-no-go", st_open, S_OPEN, item="#99", paths=["web/theme.css"], want_rc=NO_GO,
         must=("NO-GO #99", "outside scope: web/theme.css", "finish the priority first"))
    case("item-not-ref-no-go", st_open, S_OPEN, item="#99", want_rc=NO_GO, must=("not a scope ref",))
    case("ref-does-not-carry-paths", st_open, S_OPEN, item="#12",
         paths=["app/screens/home.html", "web/theme.css"], want_rc=NO_GO, must=("in-scope ref but path",))
    case("ref-normalized", st_open, S_OPEN, item="12", want_rc=GO)
    # Refs-only scope: the outside-path rule still applies to changed paths.
    st = status_of(_fake_git("priority: p\nscope: #12\nacceptance: python3 tools/check.py\n", owner_c, [O1]))
    case("refs-only-paths-no-go", st, S_OPEN, item="#12", paths=["web/theme.css"], want_rc=NO_GO,
         must=("in-scope ref but path(s) outside scope: web/theme.css",))
    case("refs-only-item-go", st, S_OPEN, item="#12", want_rc=GO)
    # Agent-authored record: rejected, acceptance never executed, nothing in scope.
    calls: list = []
    st = status_of(_fake_git(GOOD, agent_c, [A1]), rc=0, calls=calls)
    case("agent-record-rejected", st, S_OPEN, item="#12", want_rc=NO_GO, must=("is not the owner",))
    if calls:
        failures.append(f"agent-record-rejected: acceptance of an untrusted record was executed: {calls}")
    case("agent-widened-line-rejected", status_of(_fake_git(GOOD, both_c, [O1, A1, O1], last=O1)),
         S_OPEN, item="#12", want_rc=NO_GO, must=("line author aaaaaaa",))
    case("coauthored-commit-rejected",
         status_of(_fake_git(GOOD, {O1: (OWNER, "N", "Assistant <bot@example.com>")}, [O1])),
         S_OPEN, item="#12", want_rc=NO_GO, must=("Co-authored-by",))
    case("unsigned-rejected-when-required", status_of(owner_git, require_signed=True), S_OPEN,
         item="#12", want_rc=NO_GO, must=("no good signature",))
    case("no-owner-configured", status_of(owner_git, owners=()), S_OPEN, item="#12", want_rc=NO_GO,
         must=("no owner email configured",))
    # No record: never existed -> NONE (GO, notice); deleted by a non-owner -> NO-GO;
    # deleted by the owner -> NONE; a shallow clone or an unresolvable rev -> OPEN.
    case("never-existed-go", status_of(_fake_git(None, owner_c, [O1])), S_NONE, item="#99",
         paths=["web/theme.css"], want_rc=GO, must=("no priority record ever existed", "notice:"))
    case("deleted-by-agent-no-go", status_of(_fake_git(None, both_c, [O1], last=A1)), S_OPEN,
         item="#99", want_rc=NO_GO, must=("deleted at aaaaaaa by a non-owner",))
    case("deleted-no-owner-no-go", status_of(_fake_git(None, owner_c, [O1], last=O1), owners=()), S_OPEN,
         item="#99", want_rc=NO_GO, must=("no owner configured",))
    case("deleted-by-owner-go", status_of(_fake_git(None, owner_c, [O1], last=O1)), S_NONE, item="#99",
         want_rc=GO, must=("deleted by the owner at 1111111",))
    case("deleted-coauthored-no-go",
         status_of(_fake_git(None, {O1: (OWNER, "N", "Assistant <bot@example.com>")}, [O1], last=O1)),
         S_OPEN, item="#99", want_rc=NO_GO, must=("Co-authored-by",))
    case("shallow-no-record-no-go", status_of(_fake_git(None, owner_c, [O1], shallow=True)), S_OPEN,
         item="#99", want_rc=NO_GO, must=("shallow clone",))
    case("bad-rev-no-go", status_of(_fake_git(GOOD, owner_c, [O1], bad_rev=True)), S_OPEN, item="#12",
         want_rc=NO_GO, must=("does not resolve",))
    case("malformed-no-priority", status_of(_fake_git("scope: app/**\n", owner_c, [O1])), S_OPEN,
         item="#12", want_rc=NO_GO, must=("exactly one non-empty `priority:`",))
    case("malformed-two-priorities", status_of(_fake_git(GOOD + "priority: other\n", owner_c, [O1]), rc=0),
         S_OPEN, item="#12", want_rc=NO_GO, must=("found 2",))
    for broad in ("**", "*", "**/*", "./**"):
        calls = []
        case(f"too-broad-scope-{broad}",
             status_of(_fake_git(GOOD.replace("#12", f"#12 {broad}"), owner_c, [O1]), rc=0, calls=calls),
             S_OPEN, item="#12", want_rc=NO_GO, must=("too broad",))
        if calls:
            failures.append(f"too-broad-scope-{broad}: acceptance ran for an untrusted scope")
    # Acceptance exit 0 in a clean detached worktree of the rev sha -> DONE; the oracle guard still fires.
    calls, wts = [], []
    st_done = status_of(_fake_git(GOOD, owner_c, [O1, O2], sha="c" * 40, worktrees=wts), rc=0, calls=calls)
    case("done-go-everything", st_done, S_DONE, item="#99", paths=["web/theme.css"], want_rc=GO,
         must=("is DONE", "exit 0 on cccccccccccc"))
    ran[0] += 1
    added = [w for w in wts if w[1] == "add"]
    if not (added and added[0][2] == "--detach" and added[0][-1] == "c" * 40 and calls
            and calls[0][1] == added[0][3] and any(w[1] == "remove" for w in wts) and st_done.tested == "c" * 40):
        failures.append(f"clean-worktree: add/run/remove not on the rev sha: wts={wts} calls={calls}")
    case("done-oracle-tamper-no-go", st_done, S_DONE, paths=["tools/parity_differ.py"], want_rc=NO_GO,
         must=("acceptance oracle",))
    case("done-oracle-dirty-no-go", st_done, S_DONE, paths=["app/screens/home.html"],
         dirty=["tools/parity_differ.py"], want_rc=NO_GO, must=("acceptance oracle",))
    case("done-in-scope-oracle-ok", st_done, S_DONE, paths=["app/screens/home.html"], want_rc=GO)
    calls = []
    case("acceptance-missing-open", status_of(_fake_git(GOOD.replace("acceptance", "accept"), owner_c, [O1]),
                                              rc=0, calls=calls), S_OPEN, must=("acceptance command missing",))
    if calls:
        failures.append("acceptance-missing-open: a command ran with no acceptance line")
    case("acceptance-ambiguous-open",
         status_of(_fake_git(GOOD + "acceptance: python3 x.py\n", owner_c, [O1]), rc=0), S_OPEN,
         must=("ambiguous",))
    case("acceptance-timeout-open", status_of(owner_git, rc=None), S_OPEN, item="#99", want_rc=NO_GO,
         must=("TimeoutExpired",))
    # Trivially-true acceptance -> OPEN and never run, unless an owner line allows it.
    for cmd in ("true", ":", "exit 0", "exit", "ls", "echo done", "`true`", "pytest || true",
                "pytest | cat", "FOO=1 true", "pytest; echo ok", "true && echo ok", "printf ok"):
        calls = []
        rec_text = f"priority: p\nscope: app/**\nacceptance: {cmd}\n"
        case(f"trivial-{cmd!r}", status_of(_fake_git(rec_text, owner_c, [O1]), rc=0, calls=calls), S_OPEN,
             must=("trivially-true acceptance rejected",))
        if calls:
            failures.append(f"trivial-{cmd!r}: a trivially-true acceptance was executed")
    for cmd in ("false", "pytest -q", "test -f app/x", "pytest && echo ok", "echo go; pytest",
                "python3 -c \"import sys; sys.exit(0)\"", "grep -q ok out.txt || exit 1", "pytest | cat -n; false",
                "pytest -q 2>&1", "make check >&2", "pytest 2>&1 || exit 1"):
        ran[0] += 1
        if trivially_true(cmd):
            failures.append(f"non-trivial {cmd!r} flagged: {trivially_true(cmd)}")
    ok_text = "priority: p\nscope: app/**\nacceptance: true\nacceptance-trivial-ok: smoke priority\n"
    case("trivial-owner-allowed", status_of(_fake_git(ok_text, owner_c, [O1]), rc=0), S_DONE)
    # Blockers: another party + evidence -> BLOCKED -> GO for others; without evidence -> still OPEN.
    blocked = GOOD + "blocker: design vendor | https://example.com/t/42 | spec pending\n"
    case("blocked-with-evidence-go", status_of(_fake_git(blocked, owner_c, [O1])), S_BLOCKED,
         item="#99", paths=["web/theme.css"], want_rc=GO, must=("BLOCKED on design vendor",))
    case("blocked-without-evidence-open",
         status_of(_fake_git(GOOD + "blocker: design vendor | waiting on them\n", owner_c, [O1])), S_OPEN,
         item="#99", want_rc=NO_GO, must=("no http(s) evidence link",))
    case("blocked-on-self-open",
         status_of(_fake_git(GOOD + "blocker: agent | https://example.com/x\n", owner_c, [O1])), S_OPEN,
         item="#99", want_rc=NO_GO, must=("names no other party",))
    case("done-beats-blocked", status_of(_fake_git(blocked, owner_c, [O1]), rc=0), S_DONE)
    # Quote route: off by default; with --allow-quote the quote LINE must be owner-blamed,
    # and claims match as whole tokens / an exact backtick span, never substrings.
    quote = ('owner-quote: 2026-09-20 | planning call | "finish design-alignment: app/screens/** and #12, '
             'done when `python3 tools/parity_differ.py design.html app/screens/home.html` passes"\n')
    mixed = [A1] * 5 + [O1]  # record lines by the agent, the quote line (line 6) by the owner
    q_git = _fake_git(GOOD + quote, both_c, mixed, last=A1)
    case("quote-route-off-by-default", status_of(q_git), S_OPEN, item="#12", want_rc=NO_GO,
         must=("owner-quote route is off",))
    case("quote-route-owner-line-trusted", status_of(q_git, allow_quote=True), S_OPEN, item="#12", want_rc=GO,
         must=("owner-quote 2026-09-20",))
    case("quote-self-vouching-rejected", status_of(_fake_git(GOOD + quote, agent_c, [A1]), allow_quote=True),
         S_OPEN, item="#12", want_rc=NO_GO, must=("cannot vouch for itself",))
    case("quote-route-widened-rejected",
         status_of(_fake_git(GOOD.replace("#12", "#12 web/**") + quote, both_c, mixed, last=A1), allow_quote=True),
         S_OPEN, item="#99", paths=["web/theme.css"], want_rc=NO_GO, must=("does not contain: 'web/**'",))
    sub_scope = quote.replace("app/screens/** and", "app/screens/**/legacy.html and")
    case("quote-scope-substring-rejected",
         status_of(_fake_git(GOOD + sub_scope, both_c, mixed, last=A1), allow_quote=True),
         S_OPEN, item="#12", want_rc=NO_GO, must=("does not contain: 'app/screens/**'",))
    sub_cmd = GOOD.replace(" app/screens/home.html`", "`")
    case("quote-acceptance-substring-rejected",
         status_of(_fake_git(sub_cmd + quote, both_c, mixed, last=A1), allow_quote=True),
         S_OPEN, item="#12", want_rc=NO_GO, must=("does not contain: 'python3 tools/parity_differ.py design.html'",))
    # Owner identity: env wins; the git config fallback warns it is unprotected.
    ran[0] += 1
    cfg_git = _fake_git(GOOD, owner_c, [O1], config_owner=OWNER)
    got, warn = resolve_owners(None, cfg_git, env={})
    if got != [OWNER] or "unprotected owner identity" not in warn:
        failures.append(f"owner-git-config-warns: {got} {warn!r}")
    got, warn = resolve_owners(None, cfg_git, env={"DCR_OWNER_EMAIL": f"{OWNER.upper()}, b@example.com"})
    if got != ["b@example.com", OWNER] or warn:
        failures.append(f"owner-env-protected: {got} {warn!r}")
    # DONE is cached per (record digest, tested sha): same sha skips the command, a new sha re-runs it.
    with tempfile.TemporaryDirectory(prefix="focus_gate_cache_") as ctmp:
        cache = os.path.join(ctmp, CACHE_FILE)
        calls = []
        status_of(_fake_git(GOOD, owner_c, [O1]), rc=0, calls=calls, cache_path=cache)
        st = status_of(_fake_git(GOOD, owner_c, [O1]), rc=0, calls=calls, cache_path=cache)
        case("done-cached-same-sha", st, S_DONE, must=("(cached)",))
        st = status_of(_fake_git(GOOD, owner_c, [O1], sha="d" * 40), rc=1, calls=calls, cache_path=cache)
        case("cache-new-sha-reruns", st, S_OPEN, must=("exit 1",))
        st = status_of(_fake_git(GOOD + "\n", owner_c, [O1]), rc=1, calls=calls, cache_path=cache)
        case("cache-new-record-reruns", st, S_OPEN, must=("exit 1",))
        ran[0] += 1
        if len(calls) != 3:
            failures.append(f"done-cache: want 3 acceptance runs (cached once), got {len(calls)}")
    ran[0] += 1
    try:
        got = _range_paths(_fake_git(GOOD, owner_c, [O1], diff=["a b.txt", "c.txt"]), "base", "head")
        if got != ["a b.txt", "c.txt"]:
            failures.append(f"range-paths: {got}")
        _range_paths(owner_git, ZERO_SHA, "head")
        failures.append("zero-base: no error")
    except GitError:
        pass
    _selftest_e2e(failures, ran)
    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"focus_gate selftest: OK ({ran[0]} cases)")
    return 0


def _selftest_e2e(failures: list, ran: list) -> None:
    """End to end through the CLI on a real throwaway repo (local git only; no network)."""
    env = {k: v for k, v in os.environ.items() if k != "DCR_OWNER_EMAIL"}
    with tempfile.TemporaryDirectory(prefix="focus_gate_selftest_") as tmp:
        repo = Path(tmp)
        git = real_git(tmp)
        git(["init", "-q"])
        git(["config", "commit.gpgsign", "false"])

        def commit(email: str, rel: str, body: str, msg: str = "chore: record") -> str:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(body)
            git(["add", rel])
            git(["-c", f"user.email={email}", "-c", "user.name=Jane Smith", "commit", "-q", "-m", msg])
            return git(["rev-parse", "HEAD"]).strip()

        def cli(*args: str, owner: bool = True) -> subprocess.CompletedProcess:
            ran[0] += 1
            extra = ["--owner-email", OWNER] if owner else []
            return subprocess.run([sys.executable, __file__, *args, *extra],
                                  cwd=tmp, capture_output=True, text=True, env=env)

        acceptance = f"{shlex.quote(sys.executable)} -c \"import sys; sys.exit(int(open('flag.txt').read()))\""
        base = commit(OWNER, "flag.txt", "1", "chore: init")
        p = cli("check", "--item", "#5", "--paths", "web/x.css")
        if p.returncode != GO or "ever existed" not in p.stdout:
            failures.append(f"e2e-never-existed-go: rc={p.returncode} {p.stdout}{p.stderr}")
        open_sha = commit(OWNER, DEFAULT_RECORD, f"priority: p1\nscope: app/**\nacceptance: {acceptance}\n")
        p = cli("check", "--item", "#5", "--paths", "web/x.css")
        if p.returncode != NO_GO or "is OPEN" not in p.stdout:
            failures.append(f"e2e-open-fires: rc={p.returncode} {p.stdout}{p.stderr}")
        # An uncommitted flip of the oracle input never proves DONE: the command runs on the rev.
        (repo / "flag.txt").write_text("0")
        p = cli("status")
        if p.returncode != STATUS_EXIT[S_OPEN] or "source=owner-commit" not in p.stdout:
            failures.append(f"e2e-dirty-tree-not-done: rc={p.returncode} {p.stdout}{p.stderr}")
        done_sha = commit(OWNER, "flag.txt", "0", "feat: finish priority")
        ev = repo / "evidence.json"
        p = cli("status", "--evidence", str(ev))
        doc = json.loads(ev.read_text()) if ev.is_file() else {}
        if p.returncode != STATUS_EXIT[S_DONE] or doc.get("state") != S_DONE or doc.get("tested_sha") != done_sha:
            failures.append(f"e2e-done: rc={p.returncode} {doc} {p.stdout}{p.stderr}")
        p = cli("status")
        if p.returncode != STATUS_EXIT[S_DONE] or "(cached)" not in p.stdout:
            failures.append(f"e2e-done-cached: rc={p.returncode} {p.stdout}{p.stderr}")
        # check --base/--head tests head, not the checked-out tree.
        p = cli("check", "--base", base, "--head", open_sha)
        if p.returncode != NO_GO:
            failures.append(f"e2e-range-tests-head: rc={p.returncode} {p.stdout}{p.stderr}")
        head = commit(OWNER, "web/x.css", "x\n", "style: tweak")
        p = cli("check", "--base", base, "--head", head)
        if p.returncode != GO:
            failures.append(f"e2e-done-range-go: rc={p.returncode} {p.stdout}{p.stderr}")
        git(["config", "dcr.owner", OWNER])
        p = cli("status", owner=False)
        if p.returncode != STATUS_EXIT[S_DONE] or "unprotected owner identity" not in p.stderr:
            failures.append(f"e2e-git-config-owner-warns: rc={p.returncode} {p.stdout}{p.stderr}")
        commit(AGENT, DEFAULT_RECORD, f"priority: p1\nscope: app/** web/**\nacceptance: {acceptance}\n",
               "chore: widen scope")
        p = cli("check", "--paths", "web/x.css")
        if p.returncode != NO_GO or "untrusted" not in p.stdout:
            failures.append(f"e2e-agent-widen-fires: rc={p.returncode} {p.stdout}{p.stderr}")
        git(["rm", "-q", DEFAULT_RECORD])
        git(["-c", f"user.email={AGENT}", "-c", "user.name=Jane Smith", "commit", "-q", "-m", "chore: drop"])
        p = cli("check", "--paths", "web/x.css")
        if p.returncode != NO_GO or "by a non-owner" not in p.stdout:
            failures.append(f"e2e-agent-delete-fires: rc={p.returncode} {p.stdout}{p.stderr}")
        ran[0] += 1
        if len(git(["worktree", "list", "--porcelain"]).strip().split("\n\n")) != 1:
            failures.append("e2e-worktree-cleanup: a throwaway acceptance worktree was left registered")


def main(argv: list | None = None) -> int:
    """CLI entry point: `status`, `check`, or `--selftest` (see module docstring)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--selftest"]:
        return _selftest()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--record", default=DEFAULT_RECORD, help="record path (default .claude/PRIORITY.md)")
    common.add_argument("--rev", help="revision to read the record at (default HEAD, or --head when given)")
    common.add_argument("--owner-email", action="append", help="owner author email; repeatable")
    common.add_argument("--allow-quote", action="store_true",
                        help="enable the owner-quote route (the quote line itself must be owner-blamed)")
    common.add_argument("--commit-only", action="store_true", help="the default; accepted for compatibility")
    common.add_argument("--require-signed", action="store_true", help="record commits need a good signature")
    common.add_argument("--no-cache", action="store_true", help="always re-run the acceptance command")
    common.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="acceptance timeout seconds")
    common.add_argument("--repo", default=".", help="repository directory (default .)")
    parser = argparse.ArgumentParser(description="Block work outside an OPEN owner priority.")
    parser.add_argument("--selftest", action="store_true", help="run the built-in selftest and exit")
    sub = parser.add_subparsers(dest="cmd")
    p_status = sub.add_parser("status", parents=[common], help="print NONE/OPEN/DONE/BLOCKED with evidence")
    p_status.add_argument("--evidence", help="also write the evidence as JSON to this file")
    p_check = sub.add_parser("check", parents=[common], help="GO/NO-GO for an item and/or changed paths")
    p_check.add_argument("--item", help="item ref, e.g. #123")
    p_check.add_argument("--paths", nargs="*", default=[], help="changed repo-relative paths")
    p_check.add_argument("--base", help="range base (changed paths = merge-base..head)")
    p_check.add_argument("--head", help="range head (the sha whose tree is tested)")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.cmd is None:
        parser.error("a subcommand is required: status or check")
    git = real_git(args.repo)
    try:
        git(["rev-parse", "--show-toplevel"])
    except GitError as exc:
        print(f"focus_gate: error: not a git repository: {exc}", file=sys.stderr)
        return ERROR
    paths = list(getattr(args, "paths", []) or [])
    dirty: list = []
    if args.cmd == "check":
        if bool(args.base) != bool(args.head):
            parser.error("--base and --head go together")
        try:
            if args.base:
                paths += _range_paths(git, args.base, args.head)
            else:
                dirty = _dirty_paths(git)
        except GitError as exc:
            print(f"focus_gate: error: {exc}", file=sys.stderr)
            return ERROR
        if not args.item and not paths and not args.base:
            parser.error("check needs --item, --paths, or --base/--head")
        if args.base and not paths and not args.item:
            print("focus_gate: GO — 0 paths changed in range")
            return GO
    rev = args.rev or getattr(args, "head", None) or "HEAD"
    owners, warning = resolve_owners(args.owner_email, git)
    if warning:
        print(f"focus_gate: warning: {warning}", file=sys.stderr)
    st = evaluate(git, real_cmd, args.record, rev, owners, args.timeout, args.allow_quote,
                  args.require_signed, None if args.no_cache else _cache_location(git))
    if args.cmd == "status":
        for line in status_lines(st):
            print(line)
        if args.evidence:
            write_evidence(args.evidence, st)
        return STATUS_EXIT[st.state]
    code, lines = check(st, args.item, paths, load_fix_class_gate(), dirty)
    for line in lines + [f"  {ln}" for ln in status_lines(st)[1:4]]:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
