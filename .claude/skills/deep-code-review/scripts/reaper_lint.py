#!/usr/bin/env python3
"""reaper_lint.py — a heuristic, opt-in lint that flags a bulk/fleet-wide
process-reaper pattern in a cleanup script before it ships, instead of after it
takes down every parallel agent lane sharing the host.

WHAT THIS IS (AND IS NOT)
--------------------------
A heuristic lint over text, not a proof. It is not a shell, Makefile, YAML, or
JSON parser: it approximates shell quoting and word splitting to find a small
set of known-dangerous shapes. False negatives are possible (a command built
from variables, `eval`, a helper function in another file, a language other
than shell); false positives are possible and are silenced per line with the
allow marker below. A clean run means "none of the shapes below was found",
never "this script only kills what it owns".

WHY THIS EXISTS
----------------
`references/concurrency-shared-state.md`'s "Terminating work you own" section
documents the doctrine: a reaper may only kill processes it can prove are its
own or orphaned (parent PID 1, a cwd inside the caller's own worktree, or a
PID file the caller wrote) and must select the LISTENER only
(`lsof -t -iTCP:PORT -sTCP:LISTEN`), never a bare port or name/command-line
match. That is prose an agent may or may not follow. This script is a
mechanism for the concrete shapes of that bug class (issue #1101).

It also flags a second, unrelated bug class that lives in the same shell
scripts this file already scans: `references/lang-shell.md`'s "a GNU-only
flag piped to 2>/dev/null in a liveness/idle check fails open" (issue
#1158) — a platform-specific flag (`find -newermt`/`-printf`, `stat -c`,
`date -d`, a no-argument `sed -i`) whose invalid-option error is silently
discarded, so the check that depends on it reports the wrong verdict
instead of erroring. `GNU_FLAG_SILENCED_STDERR` below is that rule.

WHAT IT SCANS
--------------
Each argument may be a file (scanned regardless of its name or extension; the
caller explicitly chose it) or a directory, walked recursively (`.git` and
`node_modules` are skipped) and restricted to:
  * `*.sh`, `*.bash`, `*.zsh`, `*.mk`, `*.yml`, `*.yaml`;
  * files named `Makefile`, `makefile`, `GNUmakefile`, `justfile`,
    `.justfile` (any case), or `package.json`;
  * extensionless files whose first line is a `#!` shebang naming a shell
    (`sh`, `bash`, `zsh`, `dash`, `ksh`, `ash`) or `make`;
  * extensionless files inside a known hook directory (`.husky/`,
    `.githooks/`, a `.git/hooks/` directory), with or without a shebang --
    git and husky run a hook file whatever its first line says.
Despite the `.git` skip, a walked directory that contains a `.git` entry
also has that repository's hooks directory scanned explicitly: `.git/hooks/`
for a `.git` directory, or the hooks directory of the common git dir a
`.git` gitfile (linked worktree) points at. Inactive `*.sample` hooks are
skipped. A `core.hooksPath` setting is not read; pass that directory
explicitly.

SCOPE: reaper-named scripts and explicit paths; a hook that runs a test
which calls a reaper is not detected. HOOK_LIVE_REAPER sees only a reaper
named on the hook's own lines (or in a hook config); a reaper reached
indirectly (a hook runs `npm test`, the test calls a reaper) needs its own
review, or its script passed here explicitly.

Before matching, each file is preprocessed: in a `*.json` file, a
`"key": "value"` line is replaced by its decoded string value (a
`package.json` script is shell text); an unquoted `#` comment is stripped;
and a line ending in `\\`, `|`, `&&`, or `||` is joined with the next line
(a YAML block-scalar header such as `run: |` is not joined). Findings are
reported at the first physical line of the joined logical line.

RULES (fail on any match not carrying the allow marker)
--------------------------------------------------------
  LSOF_NO_LISTEN  an `lsof` call with a terse flag (`t` anywhere in a short
                  flag cluster: `-t`, `-ti`, `-nti`, `-Pti`, `-tiTCP:3000`)
                  and any `-i` selector, in either order, whose state filter
                  is not exactly `-sTCP:LISTEN` (or `-s TCP:LISTEN`), when
                  its output reaches a `kill`: on the same logical line,
                  within the next 2 logical lines, or through a variable
                  (`pids=$(lsof ...)`, `for pid in $(lsof ...)`,
                  `lsof ... | while read pid`) that a later line of the same
                  file passes to `kill`. Matches a connected client, not
                  only the listener.
  RANGE_KILL      a port range feeding a `kill` on the same logical line or
                  within the next 5: `seq [-w] A B` / `seq A STEP B`, a brace
                  range `{A..B}`, or `for ((v=A; v<=B; ...))`, where both
                  bounds are port-like (1024-65535). Small counters such as
                  `seq 1 3` are ignored.
  BROAD_PKILL     `pkill` (with or without `-f`), `killall`, or a `pgrep`
                  whose output reaches a `kill`, whose PATTERN argument (not
                  its flags, not a trailing comment) contains, as a whole
                  word, a browser/server/runtime name (chrome, chromium,
                  firefox, webkit, safari, edge, headless, browser, electron,
                  playwright, puppeteer, node, server, http, python, java,
                  deno, uvicorn, gunicorn, next, vite, webpack). A pattern
                  containing a `$` expansion is treated as caller-scoped
                  (for example `"$LANE_ID/.../vite"`) and not flagged.
  PS_GREP_KILL    a `ps ... | grep <PATTERN>` pipeline whose PATTERN matches
                  the same word list, when its output reaches a `kill` (same
                  line, next 2 lines, or a tracked variable).
  FUSER_KILL      `fuser` with `-k` and a `<port>/tcp` or `<port>/udp`
                  operand: kills every process using the port, clients
                  included.
  KILL_PORT       the `kill-port` command (bare, or via `npx`, `pnpm dlx`,
                  `yarn dlx`, `bunx`): kills whatever holds the port.
  HARDCODED_PORTS a protect/exclude/reserved/except/skip/allow/keep/
                  whitelist/allowlist/ignore/safe-named variable assigned
                  (`NAME=`, `NAME:=`, `NAME+=`, `NAME?=`, optionally after
                  `export`/`local`/`readonly`/`declare`) a value holding 2+
                  port-like numbers (1024-65535), including a multi-line
                  `NAME=(` ... `)` array, in a file that also kills. An
                  operator-owned exclusion list living as a script literal
                  goes stale the moment a new backend is added.
  HOOK_LIVE_REAPER a scanned path identified as a git hook (a file under a
                  `.githooks/`, `.husky/`, or `.git/hooks/` directory; named
                  `lefthook.yml`; or named `*pre-commit-config.y*ml`) that
                  invokes something reaper-named (a command/script token whose
                  basename contains "reap", `reaper_lint`/other `*lint*`
                  invocations excluded) with no `--dry-run`, `--dry_run`,
                  `--stub`, `--noop`, `--check-only`, or `--simulate` flag on
                  the same logical line or, in a YAML hook config, on a
                  sibling `args:` key of the same hook item (`args:
                  [--dry-run]` on its own line, flow or block list). A
                  commit/push hook running a live
                  reaper on every commit kills every sibling lane's dev server
                  and headless browser (issue #1113); this is a path-scoped
                  rule, distinct from the shape-based rules above.
  LINUX_ONLY_NO_PREFLIGHT
                  a logical line whose command word is `setsid`, `flock` or
                  `timeout` and has an argument (the command word is the first
                  word after shell keywords, options, `sudo`, `nohup`, `env`,
                  `time`, `nice`, `exec`, `xargs`, `command`, `stdbuf`,
                  `ionice`, `chrt`, `taskset`, `NAME=value` and a Makefile
                  recipe's leading `@`, `-` or `+`, so `grep timeout` or a
                  `for` word list is not a call), or that has a bare
                  `/proc/<path>` word or redirect source (no space, glob or
                  regex character; never a `find` operand, the pattern or
                  script operand of `grep`, `sed` or `awk`, nor a word `echo`
                  or `printf` prints), in a file with no
                  platform preflight for it. A stock macOS install has none of
                  them (other BSDs are not guaranteed to), so the gate exits
                  127 or reads nothing there and fails a check that never ran
                  instead of reporting it as not run. A preflight anywhere in
                  the file clears the line: `command -v`, `type`, `hash` or
                  `which` naming that tool; any `uname`; `$OSTYPE` or
                  `${OSTYPE`; a `-e`, `-d`, `-r`, `-f`, `-s` or `-x` test on a
                  `/proc` path (for `/proc`) or on a path to the tool; the tool
                  run as its own probe (`--version` or `--help` as its only
                  argument, or `true` or `:` as its whole payload: `timeout 1
                  true`). Not commands, so neither a call nor a preflight: a
                  here-document body, the inside of a quoted string that spans
                  lines,
                  package.json outside `scripts`, the text after a `$(...)` or
                  backtick inside double quotes, `(( ))` and `$(( ))`
                  arithmetic, a Makefile or justfile assignment
                  (`timeout := 5`). Skipped in `*.yml`/`*.yaml`, hook YAML
                  (lefthook.yml, .pre-commit-config.yaml) included (a CI step
                  runs on its runner's OS).
                  Residuals, each a quiet miss or a line for the allow marker:
                  `sh -c`, `bash -c` and `eval` strings, `find -exec` tails, a
                  leading redirect, a variable as the command word,
                  `$(shell ...)`, a `/proc` glob, a here-document
                  body (even one that feeds `sh` or holds `$(...)`) and a
                  `$(...)` that spans lines inside double quotes are not read;
                  an option-argument wrapper hides the tool (`nice -n 10`,
                  `env -u FOO`, `exec -a n`, `sudo -u root`); a preflight in a
                  sourced file or a wrapper function is not seen, one later in
                  the file than the call still counts, and clearing is
                  file-wide and mention-blind (`echo uname` clears every
                  line); a stray apostrophe hides the lines up to the next
                  quote; `$(nproc)`-style substitutions and other GNU tools
                  are not covered; another OS probe (`sw_vers`, `$MACHTYPE`)
                  is not a preflight; calls to a function the file defines
                  under the tool's name read as calls; a probe with option
                  values (`timeout -s KILL 1 true`) reads as a call, and a
                  quoted `'/proc/x'` given to a command other than `echo` or
                  `printf` as a read.

ALLOW MARKER
-------------
A finding is suppressed only when a physical line of the SAME logical line
carries the exact token `# reaper-lint: allow` followed by a non-empty reason
(`kill "$(cat lane.pid)"  # reaper-lint: allow lane-owned PID file`). A
marker on the line above, a marker without a reason, or a near-miss spelling
(`allowance`, `allow:`) suppresses nothing. The reason's content is not
validated; review judges whether it holds.

EXIT CODES (fail-closed)
-------------------------
  0  no unsuppressed finding in any scanned file (including "nothing matched
     the scan filters").
  1  at least one unsuppressed finding (each printed as `path:line: [RULE]
     message`), and no error.
  2  the scan could not be completed: a named path does not exist or is
     neither a file nor a directory, a directory could not be listed during
     the walk, a file could not be read, or a file is not decodable as UTF-8
     text (invalid bytes, or NUL bytes such as UTF-16). Findings from files
     that were scanned are still printed; the exit code is 2, never a silent
     pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile

OK = 0
FAIL = 1
ERROR = 2

# ---------------------------------------------------------------------------
# Scan filters.
# ---------------------------------------------------------------------------
_SCAN_EXTS = (".sh", ".bash", ".zsh", ".mk", ".yml", ".yaml")
_SCAN_NAMES = ("makefile", "gnumakefile", "justfile", ".justfile", "package.json")
_SKIP_DIRS = {".git", "node_modules"}
_SHEBANG_RE = re.compile(
    r"^#!\s*\S*?(?:/|\benv\s+(?:-\S+\s+)*)(?:(?:ba|z|da|k|a)?sh|make)\b"
)

# ---------------------------------------------------------------------------
# Shared patterns.
# ---------------------------------------------------------------------------
_ALLOW_RE = re.compile(r"#\s*reaper-lint: allow[ \t]+\S")
_KILL_WORD_RE = re.compile(r"\bkill\b")
_FILE_KILLS_RE = re.compile(r"\b(?:kill|pkill|killall)\b|\bfuser\b[^\n]*\s-\w*k|\bkill-port\b")
_BROAD_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:chrome|chromium|firefox|webkit|safari|edge|headless|"
    r"browser|electron|playwright|puppeteer|node|server|http|python|java|deno|"
    r"uvicorn|gunicorn|next|vite|webpack)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_YAML_BLOCK_HEADER_RE = re.compile(r":\s*[|>][-+0-9]*\s*$")
_JSON_PAIR_RE = re.compile(r'^\s*"(?:[^"\\]|\\.)*"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')

# Variable capture from a selector line.
_ASSIGN_VAR_RE = re.compile(
    r"(?:^|[\s;&(])(?:(?:local|export|readonly)\s+|(?:declare|typeset)\s+(?:-\w+\s+)*)?"
    r"([A-Za-z_]\w*)=[\"']?(?:\$\(|`)"
)
_FOR_VAR_RE = re.compile(r"\bfor\s+([A-Za-z_]\w*)\s+in\b")
_WHILE_READ_RE = re.compile(r"\bwhile\s+(?:IFS=\S*\s+)?read\s+(?:-\w+\s+)*([A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*)")

# Port ranges (rule RANGE_KILL).
_SEQ_RE = re.compile(r"\bseq(?:\s+-[A-Za-z]+)*\s+(\d+)\s+(\d+)(?:\s+(\d+))?\b")
_BRACE_RE = re.compile(r"\{(\d+)\.\.(\d+)(?:\.\.\d+)?\}")
_CFOR_RE = re.compile(r"\(\(\s*[A-Za-z_]\w*\s*=\s*(\d+)\s*;\s*[A-Za-z_]\w*\s*[<>]=?\s*(\d+)")

# Hard-coded protected-port list (rule HARDCODED_PORTS).
_PROTECT_ASSIGN_RE = re.compile(
    r"^\s*(?:(?:local|export|readonly)\s+|(?:declare|typeset)\s+(?:-\w+\s+)*)?"
    r"([A-Za-z_]\w*)\s*(?:::|[:+?])?=\s*(.*)$"
)
_PROTECT_NAME_RE = re.compile(
    r"(?:protect|exclude|reserved|except|skip|allow|keep|whitelist|allowlist|ignore|safe)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(?<![\w.])(\d{4,5})(?![\w.])")

# Git-hook path shapes (rule HOOK_LIVE_REAPER).
_HOOK_DIR_NAMES = {".githooks", ".husky"}
_PRECOMMIT_CONFIG_RE = re.compile(r"pre-commit-config\.ya?ml$", re.IGNORECASE)
_REAPER_NAME_RE = re.compile(r"(?i)reap")
_SCRIPT_EXT_RE = re.compile(r"\.(?:py|sh|bash|zsh|js|ts|rb|mjs|cjs)$", re.IGNORECASE)
_REAPER_SAFE_FLAG_RE = re.compile(
    r"--dry[-_]run|--stub|--noop|--check-only|--simulate", re.IGNORECASE
)
_YAML_ARGS_KEY_RE = re.compile(r"^\s*(?:-\s+)?args\s*:(.*)$")

# GNU-only flags a liveness/idle check can silently trust (rule
# GNU_FLAG_SILENCED_STDERR): each pair verified GNU-vs-BSD/macOS from a man
# page this session (docs/standards-index.md, 2026-09-24). `find -mmin` and
# `find ... -delete` are portable on both and are deliberately never flagged.
_STDERR_DEVNULL_RE = re.compile(r"2>\s*/dev/null|2>&-|&>\s*/dev/null")
_SED_SCRIPT_START_RE = re.compile(r"^['\"]?[sy][/#|,;]")

# BSD/macOS `env` requires every option before the first NAME=value
# assignment; an option placed after one is read as the utility's own name
# instead and fails loudly (rule ENV_OPTION_AFTER_ASSIGNMENT; verified on
# macOS: `env A=1 -u B true` -> "env: -u: No such file or directory", exit
# 127). Some implementations (e.g. GNU env) accept the interleave, which is
# why the script that was authored and tested there ships broken.
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Linux-only tools and procfs (rule LINUX_ONLY_NO_PREFLIGHT; checked on macOS 26:
# no /usr/bin or /bin entry for any of the three tools, and no /proc).
_LINUX_TOOLS = ("setsid", "flock", "timeout")
# A bare /proc/<path> word, or one with a redirect glued on: not `/proc/` alone,
# and nothing with a space, glob or regex character in it.
_PROC_SRC_RE = re.compile(r"^(?:\d*[<>]+)?/proc/[^\s*?\[\]^|()]+$")
_OSTYPE_RE = re.compile(r"\$\{?OSTYPE\b")
# Words that may precede a segment's command word: shell keywords and wrappers
# that run the next command (`then timeout ...`, `sudo flock ...`).
_CMD_PREFIX = frozenset(
    "! { if then else elif do while until time sudo nohup exec env nice xargs "
    "command stdbuf ionice chrt taskset".split())
_PATTERN_CMDS = frozenset(("grep", "egrep", "fgrep", "sed", "awk"))   # first operand: pattern or script
_ASSIGN_OP_RE = re.compile(r"^(?:::?|[?+!])?=")   # `timeout := 5` (Makefile, justfile)
_REDIR_RE = re.compile(r"^\d*[<>]")   # a redirect word: `>`, `2>`, `>/dev/null`, `<in`
# Text with none of these has no use and no guard: the cheap test before the real parse.
_LINUX_HINT_RE = re.compile(r"setsid|flock|timeout|uname|OSTYPE|/proc|\b(?:type|hash|which|command)\b")
_JSON_SCRIPTS_RE = re.compile(r'^\s*"scripts"\s*:\s*\{\s*$')
_HEREDOC_RE = re.compile(r"(?<!<)<<(-?)[ \t]*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][\w.-]*))")

# lsof short options that take a required / optional argument (the rest of the
# cluster, or for a required one the next token when the cluster ends there).
_LSOF_REQ_ARG = set("AcdDekmpu")
_LSOF_OPT_ARG = set("FgorSTxz")

# pkill / killall / pgrep options that consume the next token as an argument.
_PKILL_ARG_OPTS = set("PgGuUtsFJ")
# A signal given as an option (`-TERM`, `-SIGKILL`); single uppercase letters
# such as `-P` / `-U` / `-F` are options, not signals.
_SIGNAL_NAME_RE = re.compile(r"(?:SIG)?[A-Z]{2,}[0-9]*")
_KILLALL_ARG_OPTS = set("utcyon")
_LONG_ARG_OPTS = {"signal", "pidfile", "parent", "group", "euid", "uid", "terminal", "session"}

_MSG = {
    "LSOF_NO_LISTEN": (
        "lsof -t with an -i selector feeds a kill without -sTCP:LISTEN -- "
        "matches a connected client, not only the listener (use "
        "`lsof -t -iTCP:PORT -sTCP:LISTEN`)"
    ),
    "RANGE_KILL": (
        "port-range loop feeds a kill -- reaps every parallel lane's own port "
        "inside the range, not one owned port"
    ),
    "BROAD_PKILL": (
        "pkill/killall/pgrep pattern names a browser/server/runtime -- reaps a "
        "sibling lane's identically named process, not only an orphan"
    ),
    "PS_GREP_KILL": (
        "ps | grep name match feeds a kill -- reaps a sibling lane's "
        "identically named process, not only an orphan"
    ),
    "FUSER_KILL": (
        "fuser -k on a port kills every process using it, connected clients "
        "included -- select the owned listener PID instead"
    ),
    "KILL_PORT": (
        "kill-port kills whatever holds the port, including another lane's "
        "server -- kill a PID you can prove you own instead"
    ),
    "HARDCODED_PORTS": (
        "hard-coded protected-port list in a kill script -- goes stale the "
        "moment an operator adds a real serving port; source exclusions from "
        "operator config instead"
    ),
    "HOOK_LIVE_REAPER": (
        "a reaper invoked from a git hook with no --dry-run/--stub flag -- a "
        "commit/push hook must never run a live reaper (every agent's commit "
        "would kill sibling lanes' dev servers and browsers)"
    ),
    "GNU_FLAG_SILENCED_STDERR": (
        "a GNU-only flag with stderr piped to /dev/null -- on BSD/macOS this "
        "flag errors as invalid, the error is discarded, and the check reads "
        "as a false negative (no match) fleet-wide instead of erroring "
        "(lang-shell.md)"
    ),
    "LINUX_ONLY_NO_PREFLIGHT": (
        "Linux-only setsid/flock/timeout or /proc path and no platform "
        "preflight in this file -- stock macOS has none of them (other BSDs "
        "are not guaranteed to), so the gate exits 127 or reads nothing there "
        "and fails instead of reporting \"not run\"; check `command -v <tool>` "
        "(or `uname`) first and report the check as not run when it is absent "
        "(lang-shell.md)"
    ),
    "ENV_OPTION_AFTER_ASSIGNMENT": (
        "env option placed after a NAME=value assignment -- BSD/macOS env "
        "requires every option before the first assignment and reads a "
        "later one as the utility's own name instead, failing loudly there "
        "(some implementations, e.g. GNU env, accept the interleave, so the "
        "script only breaks on BSD/macOS); put options first: "
        "`env -u B A=1 cmd`, not `env A=1 -u B cmd`"
    ),
}


# ---------------------------------------------------------------------------
# File discovery.
# ---------------------------------------------------------------------------

def _has_shell_shebang(path: str) -> bool:
    """True when an extensionless file starts with a shell/make shebang.

    An unreadable file returns True so the read step reports it (fail closed)
    instead of the walk silently dropping it.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return True
    first = head.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    return bool(_SHEBANG_RE.search(first))


def _in_hook_dir(dirpath: str) -> bool:
    """True when `dirpath` is (inside) a `.husky`/`.githooks` dir or a `.git/hooks` dir."""
    parts = dirpath.replace(os.sep, "/").split("/")
    if any(p in _HOOK_DIR_NAMES for p in parts):
        return True
    return any(parts[k] == ".git" and parts[k + 1] == "hooks" for k in range(len(parts) - 1))


def _matches_scan_filter(dirpath: str, name: str) -> bool:
    """True when a file found by a directory walk should be scanned.

    Extensionless files in a known hook directory are scanned without a
    shebang sniff (a hook runs whatever its first line says); `*.sample`
    hooks are never scanned (git does not run them).
    """
    lower = name.lower()
    if lower.endswith(".sample"):
        return False
    if lower.endswith(_SCAN_EXTS) or lower in _SCAN_NAMES:
        return True
    if "." not in name:
        return _in_hook_dir(dirpath) or _has_shell_shebang(os.path.join(dirpath, name))
    return False


def _hooks_dir_for(git_entry: str) -> str:
    """The hooks directory a `.git` entry points at.

    A `.git` directory -> `<.git>/hooks`. A `.git` gitfile (`gitdir: <path>`,
    as in a linked worktree) -> `<commondir>/hooks` when the linked git dir
    names a `commondir`, else `<gitdir>/hooks`. Raises OSError/ValueError on an
    unreadable or malformed gitfile so the caller fails closed. The returned
    directory may not exist (a repository with no hooks).
    """
    if os.path.isdir(git_entry):
        return os.path.join(git_entry, "hooks")
    with open(git_entry, encoding="utf-8") as fh:
        first = fh.readline().strip()
    if not first.startswith("gitdir:"):
        raise ValueError("not a gitfile (no 'gitdir:' line)")
    gitdir = first[len("gitdir:"):].strip()
    if not os.path.isabs(gitdir):
        gitdir = os.path.join(os.path.dirname(git_entry), gitdir)
    common_file = os.path.join(gitdir, "commondir")
    if os.path.isfile(common_file):
        with open(common_file, encoding="utf-8") as fh:
            common = fh.read().strip()
        base = common if os.path.isabs(common) else os.path.join(gitdir, common)
        return os.path.normpath(os.path.join(base, "hooks"))
    return os.path.join(gitdir, "hooks")


def _iter_targets(paths: list[str]) -> tuple[list[str], list[str]]:
    """Resolve CLI paths to a flat file list. Returns (files, errors).

    A named path that is missing, or a directory the walk cannot list, is an
    error (the caller exits 2), never a silent skip.
    """
    files: list[str] = []
    errors: list[str] = []

    def on_walk_error(exc: OSError) -> None:
        errors.append(
            f"reaper_lint: cannot list {getattr(exc, 'filename', '?')} "
            f"(fail closed): {exc.strerror or exc}"
        )

    seen_hook_dirs: set[str] = set()

    def add_git_hooks(dirpath: str) -> None:
        # The walk skips `.git`, but its hooks run on every commit: scan the
        # (flat) hooks directory explicitly, `*.sample` excluded.
        git_entry = os.path.join(dirpath, ".git")
        try:
            hooks = _hooks_dir_for(git_entry)
        except (OSError, ValueError) as exc:
            errors.append(f"reaper_lint: cannot resolve hooks for {git_entry} (fail closed): {exc}")
            return
        real = os.path.realpath(hooks)
        if real in seen_hook_dirs or not os.path.isdir(hooks):
            return
        seen_hook_dirs.add(real)
        try:
            names = sorted(os.listdir(hooks))
        except OSError as exc:
            errors.append(f"reaper_lint: cannot list {hooks} (fail closed): {exc.strerror or exc}")
            return
        for fn in names:
            full = os.path.join(hooks, fn)
            if os.path.isfile(full) and not fn.lower().endswith(".sample"):
                files.append(full)

    for p in paths:
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p, onerror=on_walk_error):
                if ".git" in dirnames or ".git" in filenames:
                    add_git_hooks(dirpath)
                dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
                for fn in sorted(filenames):
                    if fn != ".git" and _matches_scan_filter(dirpath, fn):
                        files.append(os.path.join(dirpath, fn))
        else:
            errors.append(f"reaper_lint: path not found: {p} (fail closed)")
    return files, errors


def _read_text(path: str) -> str:
    """Read `path` as UTF-8 text; raise ValueError when it is not text."""
    with open(path, "rb") as fh:
        data = fh.read()
    if b"\x00" in data:
        raise ValueError("contains NUL bytes (UTF-16 or binary?); cannot scan as UTF-8 text")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"not valid UTF-8 ({exc.reason} at byte {exc.start})") from None


# ---------------------------------------------------------------------------
# Preprocessing: comments, continuations, logical lines.
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Drop an unquoted shell-style `#` comment (a `#` at a word start)."""
    in_sq = in_dq = False
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if in_sq:
            if ch == "'":
                in_sq = False
        elif ch == "\\":
            i += 2
            continue
        elif in_dq:
            if ch == '"':
                in_dq = False
        elif ch == "'":
            in_sq = True
        elif ch == '"':
            in_dq = True
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            return line[:i]
        i += 1
    return line


def _logical_lines(raw: list[str], is_json: bool) -> list[tuple[int, int, str]]:
    """Return [(first_idx, last_idx, code_text)] — comment-free, joined lines."""
    code: list[str] = []
    for line in raw:
        text = line
        if is_json:
            m = _JSON_PAIR_RE.match(line)
            if m:
                try:
                    text = json.loads('"' + m.group(1) + '"')
                except ValueError:
                    text = m.group(1)
        code.append(_strip_comment(text).rstrip())

    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(code):
        start, parts = i, []
        while True:
            part = code[i]
            if part.endswith("\\") and not part.endswith("\\\\"):
                parts.append(part[:-1])
                cont = True
            elif part.endswith(("|", "&&")) and not _YAML_BLOCK_HEADER_RE.search(part):
                parts.append(part)
                cont = True
            else:
                parts.append(part)
                cont = False
            if cont and i + 1 < len(code):
                i += 1
                continue
            break
        out.append((start, i, " ".join(p.strip() for p in parts)))
        i += 1
    return out


def _segments(text: str, strict: bool = False) -> list[str]:
    """Split a logical line into command segments at unquoted `| ; & ( )`,
    backticks, and `$(` (also inside double quotes). Quotes stay in the text.

    `strict` (rule LINUX_ONLY_NO_PREFLIGHT only) keeps what is not a command
    out of the result: the rest of a double-quoted string after a `$(...)` or
    backtick in it, and `(( ))` / `$(( ))` arithmetic. A `$(...)` after a word
    leaves a `0` word there, so `timeout $(secs) cmd` keeps an argument.
    """
    segs: list[str] = []
    buf: list[str] = []
    stack: list[str] = []  # 'sq' | 'dq' | 'sub' | 'bt' (a backtick in "...", strict only)
    tail = False           # strict: buf is string text that follows a substitution

    def cut() -> None:
        nonlocal tail
        if not tail:
            segs.append("".join(buf))
        buf.clear()
        tail = False

    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        top = stack[-1] if stack else ""
        if top == "sq":
            buf.append(ch)
            if ch == "'":
                stack.pop()
        elif ch == "\\" and i + 1 < n:
            buf.append(text[i:i + 2])
            i += 2
            continue
        elif strict and top != "dq" and (text.startswith("((", i) or text.startswith("$((", i)):
            depth, i = 2, i + (3 if ch == "$" else 2)
            while i < n and depth:
                depth += (text[i] == "(") - (text[i] == ")")
                i += 1
            continue
        elif ch == "$" and i + 1 < n and text[i + 1] == "(" and text[i + 2:i + 3] != "(":
            if strict and top != "dq" and "".join(buf).strip():
                buf.append(" 0")   # an argument of the word before it
            stack.append("sub")
            cut()
            i += 2
            continue
        elif ch == "`":
            if strict and top == "bt":
                stack.pop()
                cut()
                tail = stack[-1:] == ["dq"]
            else:
                if strict and top == "dq":
                    stack.append("bt")
                cut()
        elif top == "dq":
            buf.append(ch)
            if ch == '"':
                stack.pop()
        elif ch == "'":
            stack.append("sq")
            buf.append(ch)
        elif ch == '"':
            stack.append("dq")
            buf.append(ch)
        elif ch == ")" and top == "sub":
            stack.pop()
            cut()
            tail = strict and stack[-1:] == ["dq"]
        elif ch in "|;&()":
            cut()
        else:
            buf.append(ch)
        i += 1
    cut()
    return [s for s in segs if s.strip()]


def _tokens(segment: str) -> list[str]:
    """Shell-like word split; falls back to whitespace split on bad quoting."""
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return [t.strip("\"'") for t in segment.split()]


def _command_at(tokens: list[str], names: tuple[str, ...]) -> int:
    """Index of the first token whose basename is one of `names`, else -1."""
    for idx, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] in names:
            return idx
    return -1


# ---------------------------------------------------------------------------
# Per-command classifiers.
# ---------------------------------------------------------------------------

def _lsof_unsafe(args: list[str]) -> bool:
    """True for `lsof` args with a terse flag and an -i selector but no
    listener-only state filter (`-sTCP:LISTEN`)."""
    has_t = has_i = listen_only = False
    j = 0
    while j < len(args):
        tok = args[j]
        j += 1
        if not tok.startswith("-") or tok.startswith("--") or tok == "-":
            continue
        body = tok[1:]
        for k, ch in enumerate(body):
            rest = body[k + 1:]
            if ch == "i":
                has_i = True
                break
            if ch == "s":
                spec = rest
                if not spec and j < len(args) and ":" in args[j] and not args[j].startswith("-"):
                    spec = args[j]
                    j += 1
                if spec:
                    proto, _, states = spec.partition(":")
                    names = {s.strip().upper() for s in states.split(",") if s.strip()}
                    if proto.upper() == "TCP" and names == {"LISTEN"}:
                        listen_only = True
                break
            if ch == "t":
                has_t = True
                continue
            if ch in _LSOF_REQ_ARG:
                if not rest:
                    j += 1
                break
            if ch in _LSOF_OPT_ARG:
                break
    return has_t and has_i and not listen_only


def _pattern_args(args: list[str], arg_opts: set[str]) -> list[str]:
    """Non-option operands of pkill/killall/pgrep, skipping option arguments."""
    out: list[str] = []
    j = 0
    while j < len(args):
        tok = args[j]
        j += 1
        if tok == "--":
            out.extend(args[j:])
            break
        if tok.startswith("--"):
            if "=" not in tok and tok[2:] in _LONG_ARG_OPTS:
                j += 1
            continue
        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            if body.isdigit() or _SIGNAL_NAME_RE.fullmatch(body):
                continue  # a signal: -9, -TERM, -SIGHUP, -USR1
            for k, ch in enumerate(body):
                if ch in arg_opts:
                    if k == len(body) - 1:
                        j += 1
                    break
            continue
        out.append(tok)
    return out


def _broad(patterns: list[str]) -> bool:
    """True when a pattern names a broad browser/server word and is not
    scoped by a `$` expansion."""
    # `[c]hrome` (the grep-avoids-itself idiom) still names chrome.
    unbracketed = (re.sub(r"\[(\w)\]", r"\1", p) for p in patterns)
    return any("$" not in p and _BROAD_WORD_RE.search(p) for p in unbracketed)


def _grep_patterns(args: list[str]) -> list[str]:
    """The PATTERN operand(s) of a grep invocation; empty for `grep -v`."""
    pats: list[str] = []
    j = 0
    positional_done = False
    while j < len(args):
        tok = args[j]
        j += 1
        if tok.startswith("-") and len(tok) > 1:
            if "v" in tok[1:] and not tok.startswith("--"):
                return []
            if tok in ("-e", "--regexp") and j < len(args):
                pats.append(args[j])
                j += 1
                positional_done = True
            elif tok in ("-f", "-m", "-A", "-B", "-C"):
                j += 1
            continue
        if not positional_done:
            pats.append(tok)
            positional_done = True
    return pats


def _classify(text: str) -> tuple[list[str], list[str]]:
    """Classify one logical line. Returns (direct_rules, selector_rules):
    direct rules are kills in themselves; selector rules pick PIDs and are a
    finding only when their output reaches a kill."""
    direct: list[str] = []
    selectors: list[str] = []
    saw_ps = False
    for seg in _segments(text):
        toks = _tokens(seg)
        if not toks:
            continue
        idx = _command_at(toks, ("lsof",))
        if idx >= 0 and _lsof_unsafe(toks[idx + 1:]):
            selectors.append("LSOF_NO_LISTEN")
        idx = _command_at(toks, ("pkill", "killall"))
        if idx >= 0:
            name = toks[idx].rsplit("/", 1)[-1]
            args = toks[idx + 1:]
            if name == "pkill":
                pats = _pattern_args(args, _PKILL_ARG_OPTS)[:1]
            else:
                pats = _pattern_args(args, _KILLALL_ARG_OPTS)
            if _broad(pats):
                direct.append("BROAD_PKILL")
        idx = _command_at(toks, ("pgrep",))
        if idx >= 0 and _broad(_pattern_args(toks[idx + 1:], _PKILL_ARG_OPTS)[:1]):
            selectors.append("BROAD_PKILL")
        if _command_at(toks, ("ps",)) >= 0:
            saw_ps = True
        idx = _command_at(toks, ("grep", "egrep", "fgrep"))
        if saw_ps and idx >= 0 and _broad(_grep_patterns(toks[idx + 1:])):
            selectors.append("PS_GREP_KILL")
        idx = _command_at(toks, ("fuser",))
        if idx >= 0:
            args = toks[idx + 1:]
            has_k = any(a.startswith("-") and not a.startswith("--") and "k" in a for a in args)
            has_port = any(re.search(r"/(?:tcp|udp)$", a) for a in args) or any(
                args[k] == "-n" and args[k + 1] in ("tcp", "udp") for k in range(len(args) - 1)
            )
            if has_k and has_port:
                direct.append("FUSER_KILL")
        idx = _command_at(toks, ("kill-port",))
        if idx >= 0:
            before = {t.rsplit("/", 1)[-1] for t in toks[:idx]}
            installing = bool(before & {"npm", "yarn", "pnpm", "bun"}) and bool(
                before & {"install", "i", "add", "remove", "uninstall", "rm"}
            )
            if not installing:
                direct.append("KILL_PORT")
    return direct, selectors


def _gnu_only_flag(cmd: str, args: list[str]) -> str | None:
    """Return the GNU-only flag `cmd` was invoked with in `args`, or None.

    Verified GNU-vs-BSD/macOS divergence only (docs/standards-index.md,
    2026-09-24 man-page fetch), never a guess: `find -printf`/`-newermt`
    (absent from BSD/macOS find entirely), `stat -c`/`--format` (BSD/macOS
    `stat` has no `-c`, only `-f`), `date -d`/`--date` (BSD/macOS `date` has
    no `-d` at all), and `sed -i` given no argument (BSD/macOS `sed -i`
    requires one, even `''`; GNU's suffix is optional). `find -mmin` and
    `find ... -delete` are portable on both and are never returned here.
    """
    if cmd == "find":
        for a in args:
            if a in ("-printf", "-newermt"):
                return a
    elif cmd == "stat":
        for a in args:
            if a == "-c" or a.startswith("--format"):
                return a
    elif cmd == "date":
        for a in args:
            if a == "-d" or a.startswith("--date"):
                return a
    elif cmd == "sed":
        for i, a in enumerate(args):
            if a != "-i":
                continue
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt is not None and _SED_SCRIPT_START_RE.match(nxt):
                return "-i (no suffix argument)"
            return None   # an explicit extension argument (even '') is portable
    return None


def _env_option_after_assignment(text: str) -> bool:
    """True when `env` is invoked with a `NAME=value` token followed later by
    an option (`-u`, `-i`, `-S`, ...) -- BSD/macOS `env` stops parsing options
    at the first assignment and reads the option as the utility name instead,
    failing loudly there. Some implementations (e.g. GNU `env`) tolerate the
    interleave, so this breaks only on BSD/macOS (rule
    ENV_OPTION_AFTER_ASSIGNMENT)."""
    for seg in _segments(text):
        toks = _tokens(seg)
        idx = _command_at(toks, ("env",))
        if idx < 0:
            continue
        seen_assign = False
        skip_next = False
        for t in toks[idx + 1:]:
            if skip_next:
                skip_next = False
                continue
            if t.startswith("-"):
                if seen_assign:
                    return True
                if t in ("-u", "-S", "-P", "-C", "-L"):
                    skip_next = True  # these take an argument; don't read it as the utility name
                continue
            if _ENV_ASSIGN_RE.match(t):
                seen_assign = True
                continue
            break  # utility name reached; env's own arg list ends here
    return False


def _gnu_flag_silenced_stderr(text: str) -> bool:
    """True when a logical line invokes `find`/`stat`/`date`/`sed` with a
    verified GNU-only flag (`_gnu_only_flag`) AND pipes that same command's
    stderr to /dev/null (same pipe stage, not a later one) -- the shape that lets an invalid-option error masquerade
    as "no match" (rule GNU_FLAG_SILENCED_STDERR, #1158)."""
    if not _STDERR_DEVNULL_RE.search(text):
        return False
    for seg in _segments(text):
        if not _STDERR_DEVNULL_RE.search(seg):
            continue   # the redirect must silence this command, not a later stage
        toks = _tokens(seg)
        if not toks:
            continue
        idx = _command_at(toks, ("find", "stat", "date", "sed"))
        if idx < 0:
            continue
        cmd = toks[idx].rsplit("/", 1)[-1]
        if _gnu_only_flag(cmd, toks[idx + 1:]):
            return True
    return False


def _command_word(toks: list[str]) -> tuple[int, str]:
    """(index, basename) of a segment's command word, (-1, "") when none: its
    first token that is not a shell keyword, a wrapper (`_CMD_PREFIX`), an
    option or a `NAME=value` assignment. Not `_command_at`'s any-token match:
    a bare `timeout` in `for c in git timeout; do` is a word, not a call, and
    a lint that flags it posts the red gate it exists to prevent. The first
    token loses a Makefile recipe's leading `@`, `-` and `+`."""
    for k, t in enumerate(toks):
        if k == 0:
            t = t.lstrip("@-+")
        n = t.rsplit("/", 1)[-1]
        if t and not (t.startswith("-") or n in _CMD_PREFIX or _ENV_ASSIGN_RE.match(t)):
            return k, n
    return -1, ""


def _args(toks: list[str], k: int) -> list[str]:
    """Tokens after the command word at `k`, up to the first redirect word."""
    rest = toks[k + 1:]
    return rest[:next((j for j, t in enumerate(rest) if _REDIR_RE.match(t)), len(rest))]


def _linux_only(text: str) -> tuple[set[str], set[str]]:
    """(Linux-only things one logical line uses, things it guards) for rule
    LINUX_ONLY_NO_PREFLIGHT. Pure: no I/O.

    Used, from `_segments(strict=True)` minus a `name := value` segment: a
    `_LINUX_TOOLS` name that is a segment's command word (`_command_word`)
    with an argument after it (so not `timeout)` of a `case`, `timeout() {`
    or a Make `$(timeout)`), or "/proc" for a bare `/proc/<path>` word or
    redirect source (`_PROC_SRC_RE`) that is not an operand of `find`, the
    pattern or script operand of `grep`/`sed`/`awk`, nor a word `echo` or
    `printf` prints (an argument before its first redirect). Guarded, from
    every plain segment: a tool named after `command -v`, `type`, `hash` or
    `which`, or by a path in a `-e`/`-d`/`-r`/`-f`/`-s`/`-x` test
    (`[ -x /usr/bin/flock ]`); a tool run as its own probe, with `--version`
    or `--help` as its only argument or `true` or `:` as its whole payload
    (`timeout 1 true`, `flock -n l :`); "/proc" by a test on a `/proc` path;
    "*" (everything) by `uname` or `$OSTYPE`/`${OSTYPE`. The caller unions the
    guards file-wide.
    """
    used: set[str] = set()
    if not _LINUX_HINT_RE.search(text):
        return used, set()
    guarded = {"*"} if _OSTYPE_RE.search(text) else set()
    for seg in _segments(text):
        toks = _tokens(seg)
        names = [t.rsplit("/", 1)[-1] for t in toks]
        if "uname" in names:
            guarded.add("*")
        for i, n in enumerate(names):
            if n in ("type", "hash", "which") or (n == "command" and toks[i + 1:i + 2] == ["-v"]):
                guarded.update(names[i + 1:])
                break   # a later guard word's names are a subset of these
        for i, a in enumerate(toks[:-1]):
            if a in ("-e", "-d", "-r", "-f", "-s", "-x"):   # a test on a path
                b = toks[i + 1]
                if b == "/proc" or b.startswith("/proc/"):
                    guarded.add("/proc")
                elif "/" in b:
                    guarded.add(names[i + 1])   # `[ -x /usr/bin/timeout ]`
        k, cmd = _command_word(toks)
        if cmd in _LINUX_TOOLS:   # run as its own probe: `timeout --version`, `timeout 1 true`
            args = _args(toks, k)
            words = [a for a in args if not a.startswith("-")]
            n = 1 if cmd == "setsid" else 2   # words allowed: `timeout`'s duration or `flock`'s lock, then the payload
            if args in (["--version"], ["--help"]) or (len(words) <= n and words[-1:] in (["true"], [":"])):
                guarded.add(cmd)
    for seg in _segments(text, strict=True):
        toks = _tokens(seg)
        if toks[1:2] and _ASSIGN_OP_RE.match(toks[1]):
            continue
        k, cmd = _command_word(toks)
        if cmd in _LINUX_TOOLS and k + 1 < len(toks):   # a call has an argument
            used.add(cmd)
        if cmd in ("echo", "printf"):   # prints its words: only a redirect target is read
            del toks[k + 1:k + 1 + len(_args(toks, k))]
        if cmd != "find":
            pat = -1
            if cmd in _PATTERN_CMDS:   # its first operand is a pattern or script, not a path
                pat = next((j for j in range(k + 1, len(toks)) if not toks[j].startswith("-")), -1)
            if any(j != pat and _PROC_SRC_RE.match(t) for j, t in enumerate(toks)):
                used.add("/proc")
    return used, guarded


def _non_command_lines(raw: list[str], is_json: bool) -> set[int]:
    """Raw line indexes LINUX_ONLY_NO_PREFLIGHT must not read as commands.

    package.json: every line outside the `"scripts": {` object (a `name` or
    `description` value is prose). Shell: a here-document body with its
    closing delimiter line, and the interior and closing line of a quoted
    string that spans lines. A here-document with no closing delimiter line
    and a quote that never closes mark nothing, so `$(( a << b ))` (a shift)
    and a stray apostrophe cannot hide the rest of the file.
    """
    skip: set[int] = set()
    if is_json:
        depth = 0
        for i, line in enumerate(raw):
            if depth:   # inside "scripts": braces in a string value do not count
                depth += 0 if _JSON_PAIR_RE.match(line) else line.count("{") - line.count("}")
            elif _JSON_SCRIPTS_RE.match(line):
                depth = 1
            else:
                skip.add(i)
        return skip
    quote, span, i = "", [], 0
    while i < len(raw):
        line, j, docs = raw[i], 0, []
        if quote:
            span.append(i)
        while j < len(line):
            c = line[j]
            if c == "\\" and quote != "'":
                j += 2
                continue
            if quote:
                if c == quote:
                    quote = ""
                    skip.update(span)
                    span = []
            elif c in "'\"":
                quote = c
            elif c == "#" and (j == 0 or line[j - 1] in " \t;&|()"):
                break
            else:
                m = _HEREDOC_RE.match(line, j)
                if m:
                    docs.append((m.group(1), m.group(2) or m.group(3) or m.group(4)))
                    j = m.end()
                    continue
            j += 1
        for dash, word in docs if not quote else ():
            end = next((k for k in range(i + 1, len(raw))
                        if (raw[k].lstrip("\t") if dash else raw[k]) == word), -1)
            if end >= 0:
                skip.update(range(i + 1, end + 1))
                i = end
        i += 1
    return skip


def _linux_only_lines(raw: list[str], logical: list[tuple[int, int, str]], is_json: bool) -> set[int]:
    """Logical-line indexes that use a Linux-only thing the file never
    preflights (rule LINUX_ONLY_NO_PREFLIGHT). A preflight anywhere in the
    file clears a line, a later one included; any `uname` or `$OSTYPE`
    clears every line. Lines `_non_command_lines` names use and guard nothing."""
    found = [_linux_only(text) for _, _, text in logical]
    if not any(used for used, _ in found):
        return set()   # no use anywhere: skip the quote scan
    skip = _non_command_lines(raw, is_json)
    found = [(set(), set()) if start in skip else f for (start, _, _), f in zip(logical, found)]
    guarded = set().union(*(g for _, g in found))
    if "*" in guarded:
        return set()
    return {li for li, (used, _) in enumerate(found) if used - guarded}


def _captured_vars(text: str) -> list[str]:
    """Variable names a selector line's output lands in."""
    names: list[str] = []
    m = _ASSIGN_VAR_RE.search(text)
    if m:
        names.append(m.group(1))
    m = _FOR_VAR_RE.search(text)
    if m:
        names.append(m.group(1))
    m = _WHILE_READ_RE.search(text)
    if m:
        names.extend(m.group(1).split())
    return names


def _range_is_portlike(text: str) -> bool:
    """True when the line carries a seq/brace/C-style range whose bounds are
    both port-like (1024-65535)."""
    bounds: list[tuple[int, int]] = []
    for m in _SEQ_RE.finditer(text):
        nums = [int(g) for g in m.groups() if g is not None]
        bounds.append((nums[0], nums[-1]))
    for m in _BRACE_RE.finditer(text):
        bounds.append((int(m.group(1)), int(m.group(2))))
    for m in _CFOR_RE.finditer(text):
        bounds.append((int(m.group(1)), int(m.group(2))))
    return any(1024 <= lo <= 65535 and 1024 <= hi <= 65535 for lo, hi in bounds)


def _portlike_count(value: str) -> int:
    return sum(1 for m in _NUMBER_RE.finditer(value) if 1024 <= int(m.group(1)) <= 65535)


def _is_hook_path(path: str) -> bool:
    """True when `path` is a git-hook-family file (rule HOOK_LIVE_REAPER)."""
    parts = path.replace(os.sep, "/").split("/")
    basename = parts[-1]
    if any(p in _HOOK_DIR_NAMES for p in parts):
        return True
    if ".git" in parts and "hooks" in parts:
        return True
    if basename.lower() == "lefthook.yml":
        return True
    if _PRECOMMIT_CONFIG_RE.search(basename):
        return True
    return False


def _reaper_invocation(text: str) -> bool:
    """True when a logical line's tokens name a reaper-ish command/script
    (basename contains "reap"), excluding a `*lint*` variant such as
    `reaper_lint.py` itself (a read-only check, safe in a hook)."""
    for seg in _segments(text):
        for tok in _tokens(seg):
            base = tok.rsplit("/", 1)[-1]
            stem = _SCRIPT_EXT_RE.sub("", base)
            if _REAPER_NAME_RE.search(stem) and "lint" not in stem.lower():
                return True
    return False


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _yaml_key_col(line: str) -> tuple[int, bool]:
    """(column where the mapping key starts, True if the line opens a `- ` list item)."""
    m = re.match(r"^( *)(-\s+)?", line)
    return len(m.group(0)), bool(m.group(2))


def _yaml_sibling_dry_run(raw: list[str], idx: int) -> bool:
    """True when the YAML hook item holding raw line `idx` has an `args:` key
    (a sibling at the same key column; a flow list such as `[--dry-run]` or a
    block list nested under it) carrying a dry-run/stub flag. A flag on a
    different list item does not count.
    """
    col, opens_item = _yaml_key_col(raw[idx])

    def meaningful(k: int) -> bool:
        return bool(raw[k].strip()) and not raw[k].lstrip().startswith("#")

    lo = idx
    if not opens_item:
        for k in range(idx - 1, -1, -1):
            if not meaningful(k):
                continue
            kc, item = _yaml_key_col(raw[k])
            if item and kc == col:
                lo = k
                break
            if _indent(raw[k]) < col:
                break
            lo = k
    hi = idx
    for k in range(idx + 1, len(raw)):
        if not meaningful(k):
            continue
        if _indent(raw[k]) < col or (_yaml_key_col(raw[k])[1] and _indent(raw[k]) <= col):
            break
        hi = k
    for k in range(lo, hi + 1):
        m = _YAML_ARGS_KEY_RE.match(raw[k])
        if not m or _yaml_key_col(raw[k])[0] != col:
            continue
        text = m.group(1)
        j = k + 1
        while j <= hi and (not raw[j].strip() or _indent(raw[j]) > col):
            text += " " + raw[j]
            j += 1
        if _REAPER_SAFE_FLAG_RE.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Scan.
# ---------------------------------------------------------------------------

def _scan_text(
    raw: list[str], is_json: bool = False, path: str | None = None
) -> list[tuple[int, str, str]]:
    """Return [(1-based line, RULE, message), ...] for one file's lines,
    excluding findings whose logical line carries the allow marker."""
    logical = _logical_lines(raw, is_json)
    texts = [t for _, _, t in logical]
    file_kills = any(_FILE_KILLS_RE.search(t) for t in texts)
    is_hook = path is not None and _is_hook_path(path)
    is_yaml = path is not None and path.lower().endswith((".yml", ".yaml"))
    # A CI step runs on its runner's OS, so YAML is skipped.
    linux_hits = set() if is_yaml else _linux_only_lines(raw, logical, is_json)
    hits: dict[tuple[int, str], None] = {}

    def add(li: int, rule: str) -> None:
        start, end, _ = logical[li]
        if any(_ALLOW_RE.search(raw[k]) for k in range(start, end + 1)):
            return
        hits.setdefault((li, rule), None)

    for li, text in enumerate(texts):
        if not text.strip():
            continue
        direct, selectors = _classify(text)
        for rule in direct:
            add(li, rule)
        if selectors:
            reaches_kill = any(_KILL_WORD_RE.search(t) for t in texts[li:li + 3])
            if not reaches_kill:
                for var in _captured_vars(text):
                    use = re.compile(r"\$\{?" + re.escape(var) + r"\b")
                    if any(_KILL_WORD_RE.search(t) and use.search(t) for t in texts[li + 1:]):
                        reaches_kill = True
                        break
            if reaches_kill:
                for rule in selectors:
                    add(li, rule)

        if _range_is_portlike(text) and any(_KILL_WORD_RE.search(t) for t in texts[li:li + 6]):
            add(li, "RANGE_KILL")

        if _gnu_flag_silenced_stderr(text):
            add(li, "GNU_FLAG_SILENCED_STDERR")

        if li in linux_hits:
            add(li, "LINUX_ONLY_NO_PREFLIGHT")

        if _env_option_after_assignment(text):
            add(li, "ENV_OPTION_AFTER_ASSIGNMENT")

        if (is_hook and _reaper_invocation(text) and not _REAPER_SAFE_FLAG_RE.search(text)
                and not (is_yaml and _yaml_sibling_dry_run(raw, logical[li][0]))):
            add(li, "HOOK_LIVE_REAPER")

        if file_kills:
            m = _PROTECT_ASSIGN_RE.match(text)
            if m and _PROTECT_NAME_RE.search(m.group(1)):
                value = m.group(2)
                if value.lstrip().startswith("(") and ")" not in value:
                    for nxt in texts[li + 1:]:
                        value += " " + nxt
                        if ")" in nxt:
                            break
                if _portlike_count(value) >= 2:
                    add(li, "HARDCODED_PORTS")

    return [(logical[li][0] + 1, rule, _MSG[rule]) for li, rule in hits]


def run_gate(paths: list[str]) -> tuple[int, list[str]]:
    """Scan `paths` (files and/or directories); return (exit_code, lines).

    Exit code: OK (0) when nothing was found, FAIL (1) on any unsuppressed
    finding, ERROR (2) when any path, directory, or file could not be scanned
    (findings from scanned files are still included in the output lines).
    """
    files, errors = _iter_targets(paths)
    all_findings: list[tuple[str, int, str, str]] = []
    for f in files:
        try:
            text = _read_text(f)
        except OSError as exc:
            errors.append(f"reaper_lint: cannot read {f} (fail closed): {exc}")
            continue
        except ValueError as exc:
            errors.append(f"reaper_lint: cannot decode {f} (fail closed): {exc}")
            continue
        is_json = f.lower().endswith(".json")
        for lineno, rule, message in _scan_text(text.splitlines(), is_json, path=f):
            all_findings.append((f, lineno, rule, message))

    out = [f"{f}:{lineno}: [{rule}] {message}" for f, lineno, rule, message in all_findings]
    if errors:
        return ERROR, out + errors
    if all_findings:
        out.append(f"reaper_lint: {len(all_findings)} finding(s) (see above)")
        return FAIL, out
    return OK, [f"reaper_lint: ok ({len(files)} file(s) scanned)"]


# ---------------------------------------------------------------------------
# Selftest — planted RED/GREEN cases, no network, no fixture repo checked in.
# ---------------------------------------------------------------------------

def _write(path: str, content: str | bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


# (name, file name, content, expected exit code, rule that must appear or "")
_SH = "#!/usr/bin/env bash\n"
_CASES: tuple[tuple[str, str, str, int, str], ...] = (
    ("clean-script-ok", "clean.sh", _SH + "echo hello\n", OK, ""),
    # LSOF_NO_LISTEN: every flag order and cluster fires.
    ("lsof-ti-fires", "a.sh", _SH + "kill -9 $(lsof -ti :$port)\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-t-iTCP-fires", "a.sh", "lsof -t -iTCP:3000 | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-tiTCP-fires", "a.sh", "lsof -tiTCP:3000 | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-nti-fires", "a.sh", "lsof -nti :3000 | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-Pti-fires", "a.sh", "lsof -Pti :3000 | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-i-then-t-fires", "a.sh", "lsof -i :3000 -t | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-t-i-attached-fires", "a.sh", "lsof -t -i:3000 | xargs kill\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-established-fires", "a.sh", "lsof -ti :3000 -sTCP:ESTABLISHED | xargs kill\n",
     FAIL, "LSOF_NO_LISTEN"),
    ("lsof-listen-in-comment-fires", "a.sh",
     "lsof -ti :3000 | xargs -r kill -9  # -sTCP:LISTEN would be nice\n", FAIL, "LSOF_NO_LISTEN"),
    ("lsof-continuation-fires", "a.sh", "lsof -ti :3000 \\\n  | xargs \\\n  -r \\\n  kill -9\n",
     FAIL, "LSOF_NO_LISTEN"),
    ("lsof-var-tracked-fires", "a.sh", "pids=$(lsof -ti :3000)\n\n\n\nkill $pids\n",
     FAIL, "LSOF_NO_LISTEN"),
    ("lsof-for-var-fires", "a.sh",
     "for pid in $(lsof -ti :3000); do\n  echo stopping\n  echo \"$pid\"\n  kill \"$pid\"\ndone\n",
     FAIL, "LSOF_NO_LISTEN"),
    ("lsof-var-without-kill-ok", "a.sh",
     "pids=$(lsof -ti :3000)\necho \"$pids\"\necho\necho\nkill \"$(cat my.pid)\"\n", OK, ""),
    ("lsof-listen-after-i-ok", "a.sh",
     _SH + "kill -9 $(lsof -t -iTCP:$port -sTCP:LISTEN)\n", OK, ""),
    ("lsof-listen-before-i-ok", "a.sh", "kill $(lsof -t -sTCP:LISTEN -iTCP:$P)\n", OK, ""),
    ("lsof-listen-before-cluster-ok", "a.sh", "kill $(lsof -sTCP:LISTEN -ti :$P)\n", OK, ""),
    ("lsof-listen-spaced-ok", "a.sh", "kill \"$(lsof -tiTCP:$P -s TCP:LISTEN)\"\n", OK, ""),
    # RANGE_KILL: seq, seq -w, brace, C-style for; small counters do not fire.
    ("range-seq-fires", "a.sh",
     _SH + "for port in $(seq 3110 3200); do\n  kill -9 $(lsof -t -iTCP:$port -sTCP:LISTEN)\ndone\n",
     FAIL, "RANGE_KILL"),
    ("range-seq-w-fires", "a.sh", "for p in $(seq -w 3000 3010); do kill $p; done\n",
     FAIL, "RANGE_KILL"),
    ("range-brace-fires", "a.sh",
     "for p in {3000..3010}; do kill $(lsof -t -iTCP:$p -sTCP:LISTEN); done\n", FAIL, "RANGE_KILL"),
    ("range-cfor-fires", "a.sh",
     "for ((p=3000;p<=3010;p++)); do kill $(lsof -t -iTCP:$p -sTCP:LISTEN); done\n",
     FAIL, "RANGE_KILL"),
    ("range-small-counter-ok", "a.sh",
     "for i in $(seq 1 3); do echo retry; done\nkill \"$(cat my.pid)\"\n", OK, ""),
    # BROAD_PKILL: pattern argument only, whole words.
    ("pkill-browser-fires", "a.sh", _SH + "pkill -f 'chromium.*headless'\n", FAIL, "BROAD_PKILL"),
    ("pkill-no-f-fires", "a.sh", "pkill chromium\n", FAIL, "BROAD_PKILL"),
    ("pkill-signal-quoted-fires", "a.sh", "pkill -9 -f \"next dev\"\n", FAIL, "BROAD_PKILL"),
    ("killall-escaped-space-fires", "a.sh", "killall -9 Google\\ Chrome\n", FAIL, "BROAD_PKILL"),
    ("pkill-substring-ok", "a.sh", "pkill -f ledger-sync\n", OK, ""),
    ("pkill-parent-comment-ok", "a.sh", "pkill -P $$  # stop child server\n", OK, ""),
    ("pkill-scoped-var-ok", "a.sh", "pkill -f \"$LANE_ID/node_modules/.bin/vite\"\n", OK, ""),
    ("killall-own-name-ok", "a.sh", "killall mydaemon\n", OK, ""),
    # New shapes.
    ("ps-grep-kill-fires", "a.sh", "ps aux | grep chrome | awk '{print $2}' | xargs kill -9\n",
     FAIL, "PS_GREP_KILL"),
    ("ps-grep-bracket-var-fires", "a.sh",
     "local pids; pids=$(ps aux | grep [c]hrome | awk '{print $2}')\necho\necho\necho\nkill $pids\n",
     FAIL, "PS_GREP_KILL"),
    ("ps-grep-own-name-ok", "a.sh", "ps aux | grep my-lane-worker | awk '{print $2}' | xargs kill\n",
     OK, ""),
    ("pgrep-kill-fires", "a.sh", "pgrep -f webpack | xargs kill\n", FAIL, "BROAD_PKILL"),
    ("pkill-parent-then-pattern-fires", "a.sh", "pkill -P 1234 node\n", FAIL, "BROAD_PKILL"),
    ("fuser-k-fires", "a.sh", "fuser -k 3000/tcp\n", FAIL, "FUSER_KILL"),
    ("fuser-no-k-ok", "a.sh", "fuser 3000/tcp\n", OK, ""),
    ("npx-kill-port-fires", "a.sh", "npx kill-port 3000 3001\n", FAIL, "KILL_PORT"),
    ("bare-kill-port-fires", "a.sh", "kill-port 3000\n", FAIL, "KILL_PORT"),
    # HARDCODED_PORTS: NAME= assignment of 2+ port-like numbers.
    ("hardcoded-array-fires", "a.sh",
     _SH + "PROTECTED_PORTS=(3000 8080 5432)\nkill -9 $(lsof -t -iTCP:$port -sTCP:LISTEN)\n",
     FAIL, "HARDCODED_PORTS"),
    ("hardcoded-quoted-fires", "a.sh",
     "PROTECTED_PORTS=\"3000,8080\"; for p in $X; do kill $p; done\n", FAIL, "HARDCODED_PORTS"),
    ("hardcoded-multiline-fires", "a.sh", "PROTECTED=(\n  3000\n  8080\n)\nkill 1\n",
     FAIL, "HARDCODED_PORTS"),
    ("hardcoded-comment-ok", "a.sh", "# keep ports 3000 8080 in sync with docs\nkill $PID\n", OK, ""),
    ("hardcoded-small-numbers-ok", "a.sh", "SKIP_TESTS=\"unit 10 20\"\nkill $PID\n", OK, ""),
    # HOOK_LIVE_REAPER: a reaper invoked from a git-hook-family path with no
    # dry-run/stub flag; excluded for non-hook paths and for *lint* variants.
    ("hook-husky-live-fires", ".husky/pre-commit",
     _SH + "python3 scripts/reaper.py --apply\n", FAIL, "HOOK_LIVE_REAPER"),
    ("hook-husky-dry-run-ok", ".husky/pre-commit",
     _SH + "python3 scripts/reaper.py --dry-run\n", OK, ""),
    ("hook-githooks-live-fires", ".githooks/pre-push",
     "#!/bin/sh\n./scripts/reaper.sh\n", FAIL, "HOOK_LIVE_REAPER"),
    ("hook-git-hooks-dir-live-fires", ".git/hooks/pre-commit",
     "#!/bin/sh\nbash reaper_cleanup.sh\n", FAIL, "HOOK_LIVE_REAPER"),
    ("hook-lefthook-yml-live-fires", "lefthook.yml",
     "pre-commit:\n  commands:\n    reap:\n      run: python3 scripts/reaper.py\n",
     FAIL, "HOOK_LIVE_REAPER"),
    ("hook-precommit-config-live-fires", ".pre-commit-config.yaml",
     "repos:\n  - hooks:\n      - id: reaper\n        entry: scripts/reaper.py\n",
     FAIL, "HOOK_LIVE_REAPER"),
    ("hook-reaper-lint-excluded-ok", ".husky/pre-commit",
     _SH + "python3 scripts/reaper_lint.py .\n", OK, ""),
    ("non-hook-live-reaper-ok", "scripts/nightly.sh",
     _SH + "python3 scripts/reaper.py --apply\n", OK, ""),
    # A dry-run flag on a sibling `args:` key of the same YAML hook item counts;
    # one on a different hook item does not.
    ("hook-precommit-args-flow-dry-run-ok", ".pre-commit-config.yaml",
     "repos:\n  - repo: local\n    hooks:\n      - id: reaper\n        entry: scripts/reaper.py\n"
     "        args: [--dry-run]\n        language: system\n", OK, ""),
    ("hook-precommit-args-block-dry-run-ok", ".pre-commit-config.yaml",
     "repos:\n  - repo: local\n    hooks:\n      - id: reaper\n        entry: scripts/reaper.py\n"
     "        args:\n          - --dry-run\n", OK, ""),
    ("hook-precommit-args-other-item-fires", ".pre-commit-config.yaml",
     "repos:\n  - repo: local\n    hooks:\n      - id: reaper\n        entry: scripts/reaper.py\n"
     "        language: system\n      - id: other\n        entry: scripts/other.py\n"
     "        args: [--dry-run]\n", FAIL, "HOOK_LIVE_REAPER"),
    ("hook-precommit-args-live-flag-fires", ".pre-commit-config.yaml",
     "repos:\n  - hooks:\n      - id: reaper\n        entry: scripts/reaper.py\n"
     "        args: [--apply]\n", FAIL, "HOOK_LIVE_REAPER"),
    # Allow marker: exact token, non-empty reason, same line only.
    ("allow-same-line-suppresses", "a.sh",
     "kill -9 $(lsof -ti :$port)  # reaper-lint: allow lane-owned port, verified by caller\n", OK, ""),
    ("allow-line-above-does-not-suppress", "a.sh",
     "# reaper-lint: allow lane-owned port, verified by caller\nkill -9 $(lsof -ti :$port)\n",
     FAIL, "LSOF_NO_LISTEN"),
    ("allow-without-reason-does-not-suppress", "a.sh",
     "lsof -ti :3000 | xargs kill  # reaper-lint: allow\n", FAIL, "LSOF_NO_LISTEN"),
    ("allow-near-miss-does-not-suppress", "a.sh",
     "lsof -ti :3000 | xargs kill; # reaper-lint: allowance\n", FAIL, "LSOF_NO_LISTEN"),
    # Embedded shell: package.json script values and YAML `run: |` blocks.
    ("package-json-scripts-fires", "package.json",
     '{\n  "scripts": {\n    "reap": "for p in $(seq 3110 3200); do kill -9 $p; done"\n  }\n}\n',
     FAIL, "RANGE_KILL"),
    ("package-json-dependency-ok", "package.json",
     ('{\n  "scripts": {\n    "stop": "kill $(cat .pid)"\n  },\n'
      '  "devDependencies": {\n    "kill-port": "^2.0.0"\n  }\n}\n'), OK, ""),
    ("yaml-run-block-fires", "ci.yml",
     ("jobs:\n  e2e:\n    steps:\n      - name: free port\n        run: |\n"
      "          echo freeing\n          lsof -ti :3000 | xargs kill -9\n"), FAIL, "LSOF_NO_LISTEN"),
    # GNU_FLAG_SILENCED_STDERR: a GNU-only flag + stderr-to-/dev/null on the
    # same line (#1158) -- each of the four verified commands, and each
    # command's portable form (or a devnull-free line) staying clean.
    ("gnu-find-newermt-devnull-fires", "a.sh",
     "n=$(find . -newermt '-10 minutes' 2>/dev/null | wc -l)\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-find-printf-devnull-fires", "a.sh",
     "find . -printf '%T@\\n' 2>/dev/null\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-stat-dash-c-devnull-fires", "a.sh",
     "mtime=$(stat -c %Y \"$f\" 2>/dev/null)\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-stat-format-long-devnull-fires", "a.sh",
     "mtime=$(stat --format=%Y \"$f\" 2>/dev/null)\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-date-dash-d-devnull-fires", "a.sh",
     "t=$(date -d '10 minutes ago' +%s 2>/dev/null)\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-sed-i-no-suffix-devnull-fires", "a.sh",
     "sed -i 's/idle/live/' \"$f\" 2>/dev/null\n", FAIL, "GNU_FLAG_SILENCED_STDERR"),
    ("gnu-flag-without-devnull-ok", "a.sh",
     "find . -newermt '-10 minutes' | wc -l\n", OK, ""),
    ("find-mmin-devnull-ok", "a.sh",
     "find . -mmin -10 2>/dev/null | wc -l\n", OK, ""),
    ("find-delete-devnull-ok", "a.sh",
     "find . -name '*.tmp' -delete 2>/dev/null\n", OK, ""),
    ("stat-dash-f-devnull-ok", "a.sh",
     "mtime=$(stat -f %m \"$f\" 2>/dev/null)\n", OK, ""),
    ("date-dash-j-devnull-ok", "a.sh",
     "t=$(date -j -f '%s' \"$epoch\" 2>/dev/null)\n", OK, ""),
    ("sed-i-with-suffix-devnull-ok", "a.sh",
     "sed -i '.bak' 's/idle/live/' \"$f\" 2>/dev/null\n", OK, ""),
    ("sed-i-empty-suffix-devnull-ok", "a.sh",
     "sed -i '' 's/idle/live/' \"$f\" 2>/dev/null\n", OK, ""),
    ("gnu-flag-devnull-on-downstream-stage-ok", "a.sh",
     "find . -newermt '-10 minutes' | wc -l 2>/dev/null\n", OK, ""),
    ("gnu-flag-devnull-on-other-command-ok", "a.sh",
     "find . -newermt '-10 minutes' | wc -l; echo done 2>/dev/null\n", OK, ""),
    # ENV_OPTION_AFTER_ASSIGNMENT: an option after a NAME=value fires; every
    # option before the first assignment (GNU or BSD-safe order) stays clean.
    ("env-option-after-assignment-fires", "a.sh",
     "env A=1 -u B cmd\n", FAIL, "ENV_OPTION_AFTER_ASSIGNMENT"),
    ("env-options-first-ok", "a.sh",
     "env -u B A=1 cmd\n", OK, ""),
    ("env-option-arg-not-mistaken-for-cmd-fires", "a.sh",
     "env -u B A=1 -u C cmd\n", FAIL, "ENV_OPTION_AFTER_ASSIGNMENT"),
    # LINUX_ONLY_NO_PREFLIGHT: setsid/flock/timeout or a /proc path with no
    # platform preflight anywhere in the file fires; a preflight for that tool
    # (any uname/$OSTYPE, or a test on /proc) anywhere in the file clears it.
    ("linux-only-setsid-fires", "a.sh",
     "setsid sh -c 'x'\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-flock-fires", "a.sh",
     "flock /tmp/l cmd\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-timeout-fires", "a.sh",
     "timeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-proc-token-fires", "a.sh",
     "cat /proc/loadavg\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-proc-redirect-fires", "a.sh",
     "read a < /proc/meminfo\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-proc-glued-redirect-fires", "a.sh",
     "read a </proc/meminfo\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-wrapped-tool-fires", "a.sh",
     "sudo -n nohup flock -n /tmp/l cmd &\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-env-assign-prefix-fires", "a.sh",
     "LC_ALL=C timeout 5 cmd\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-makefile-silent-recipe-fires", "Makefile",
     "test:\n\t@timeout 60 make t\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-setsid-command-v-ok", "a.sh",
     "command -v setsid >/dev/null || exit 0\nsetsid sh -c 'x'\n", OK, ""),
    ("linux-only-flock-command-v-ok", "a.sh",
     "command -v flock >/dev/null || exit 0\nflock /tmp/l cmd\n", OK, ""),
    ("linux-only-timeout-command-v-ok", "a.sh",
     "command -v timeout >/dev/null || exit 0\ntimeout 60 make test\n", OK, ""),
    ("linux-only-type-hash-which-ok", "a.sh",
     "type setsid >/dev/null 2>&1 || exit 0\nhash flock 2>/dev/null || exit 0\nwhich timeout || exit 0\n"
     "setsid x\nflock l c\ntimeout 5 y\n", OK, ""),
    ("linux-only-uname-case-ok", "a.sh",
     "case \"$(uname)\" in Linux) setsid x;; esac\n", OK, ""),
    ("linux-only-ostype-ok", "a.sh",
     "[[ \"$OSTYPE\" == linux* ]] || exit 0\nsetsid x\nflock l c\ntimeout 5 y\ncat /proc/loadavg\n", OK, ""),
    ("linux-only-ostype-brace-ok", "a.sh",
     "case \"${OSTYPE}\" in linux*) cat /proc/loadavg;; esac\n", OK, ""),
    ("linux-only-proc-readable-test-ok", "a.sh",
     "[ -r /proc/loadavg ] && cat /proc/loadavg\n", OK, ""),
    ("linux-only-preflight-after-call-ok", "a.sh",
     "timeout 60 make test\ncommand -v timeout >/dev/null || exit 0\n", OK, ""),
    ("linux-only-other-tool-preflight-fires", "a.sh",
     "command -v flock >/dev/null || exit 0\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-tool-preflight-not-for-proc-fires", "a.sh",
     "command -v flock >/dev/null || exit 0\ncat /proc/loadavg\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-yaml-ok", "ci.yml",
     "jobs:\n  t:\n    steps:\n      - run: timeout 60 make test\n      - run: cat /proc/loadavg\n", OK, ""),
    ("linux-only-mention-ok", "a.sh",
     "echo \"use setsid\"\necho 'see /proc/loadavg'\n", OK, ""),
    ("linux-only-word-list-ok", "a.sh",
     "for c in git timeout; do command -v \"$c\" >/dev/null || exit 1; done\n", OK, ""),
    ("linux-only-grep-arg-ok", "a.sh",
     "grep -rn timeout src\n", OK, ""),
    ("linux-only-split-quote-fragment-ok", "a.sh",
     "bad \"timeout rows: $(echo x)\"\n", OK, ""),
    # LINUX_ONLY_NO_PREFLIGHT reads commands only: not a here-document body, a
    # multi-line quoted string, a package.json value outside `scripts`, the text
    # after a `$(...)` in double quotes, arithmetic, a Makefile or justfile
    # assignment, or a `/proc` word that is a pattern, a glob or prose.
    ("linux-only-heredoc-body-ok", "a.sh",
     "cat <<'EOF'\ntimeout 60 is the default\nflock holds the lock\ncat /proc/loadavg\nEOF\n", OK, ""),
    ("linux-only-heredoc-dash-tab-ok", "a.sh",
     "if x; then\n\tcat <<-EOF\n\ttimeout 60 is the default\n\tEOF\nfi\n", OK, ""),
    ("linux-only-after-heredoc-fires", "a.sh",
     "cat <<EOF\nhello\nEOF\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-shift-is-no-heredoc-fires", "a.sh",
     "n=$(( 1 << width ))\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-here-string-is-no-heredoc-fires", "a.sh",
     "read x <<< EOF\ntimeout 5 y\nEOF\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-heredoc-forms-ok", "a.sh",
     "cat <<\"EOF\"\ntimeout 60 is the default\nEOF\ncat <<\\EOF\nflock holds the lock\nEOF\n"
     "cat <<A <<B\ntimeout 1 x\nA\nflock l c\nB\n", OK, ""),
    ("linux-only-multiline-dq-string-ok", "a.sh",
     "msg=\"usage\ntimeout is the default\"\necho \"$msg\"\n", OK, ""),
    ("linux-only-multiline-sq-string-ok", "a.sh",
     "msg='usage:\nflock /tmp/l cmd\ndone'\necho \"$msg\"\n", OK, ""),
    ("linux-only-after-multiline-string-fires", "a.sh",
     "msg=\"a\nb\"\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-stray-quote-hides-nothing-fires", "a.sh",
     "echo don't\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-comment-apostrophe-fires", "a.sh",
     "echo hi # don't\ntimeout 60 make test\necho \"it's\"\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-escaped-quote-fires", "a.sh",
     "echo \"a \\\" b\"\ntimeout 60 x\necho \"x\"\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-backslash-in-single-quotes-fires", "a.sh",
     "echo 'a\\'\ntimeout 60 x\necho 'y'\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-json-prose-value-ok", "package.json",
     "{\n  \"name\": \"timeout helpers\",\n  \"scripts\": {\n    \"test\": \"echo {\"\n  },\n"
     "  \"description\": \"flock helpers\"\n}\n", OK, ""),
    ("linux-only-json-script-value-fires", "package.json",
     "{\n  \"scripts\": {\n    \"test\": \"timeout 60 node t.js\"\n  }\n}\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-dq-subst-tail-ok", "a.sh",
     "echo \"$(date) timeout exceeded\"\nlog \"$(date +%T) flock held\"\n", OK, ""),
    ("linux-only-dq-backtick-tail-ok", "a.sh",
     "echo \"`date` flock held\"\n", OK, ""),
    ("linux-only-dq-subst-body-fires", "a.sh",
     "out=\"$(timeout 5 make t)\"\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-dq-backtick-body-fires", "a.sh",
     "out=\"`flock l c`\"\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-call-after-dq-subst-fires", "a.sh",
     "echo \"$(date) x\"; timeout 5 y\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-arith-command-ok", "a.sh",
     "while (( timeout > 0 )); do (( timeout-- )); done\n(( timeout > 0 )) || exit 1\n", OK, ""),
    ("linux-only-arith-expansion-ok", "a.sh",
     "n=$(( timeout * 2 ))\necho $(( (timeout + 1) * 2 ))\n", OK, ""),
    ("linux-only-call-after-arith-fires", "a.sh",
     "n=$(( 1 + 2 )) && timeout 5 x\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-arith-arg-fires", "a.sh",
     "timeout $(( 2 * 3 )) make t\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-make-assignment-ok", "Makefile",
     "timeout = 5\ntimeout := 5\ntimeout ::= 5\ntimeout ?= 5\ntimeout += 5\ntimeout != date\n", OK, ""),
    ("linux-only-just-assignment-ok", "justfile",
     "timeout := \"5\"\nflock := \"l\"\n", OK, ""),
    ("linux-only-make-var-ref-ok", "Makefile",
     "test:\n\tgo test -timeout $(timeout) ./...\n", OK, ""),
    ("linux-only-make-var-arg-fires", "Makefile",
     "test:\n\ttimeout $(secs) make t\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-case-arm-and-function-def-ok", "a.sh",
     "case \"$c\" in\n  timeout) echo hi;;\nesac\ntimeout() { gtimeout \"$@\"; }\n", OK, ""),
    ("linux-only-proc-grep-sed-awk-pattern-ok", "a.sh",
     "grep '/proc/' f\nsed -n '/proc/p' f\ngrep '/proc/x' f\nawk '/proc/{print}' f\n", OK, ""),
    ("linux-only-proc-find-operand-ok", "a.sh",
     "find / -path '/proc/*' -prune -o -print\nfind / -path /proc/self -prune -o -print\n", OK, ""),
    ("linux-only-proc-glob-or-prose-ok", "a.sh",
     "tar --exclude '/proc/*' -cf x.tar .\ndie \"/proc/stat unreadable\"\nls /proc/\nls '/proc/[0-9]'\n"
     "ls '/proc/?'\nls '/proc/a|b'\nls '/proc/(a)'\nls '/proc/^a'\n", OK, ""),
    ("linux-only-proc-grep-file-operand-fires", "a.sh",
     "grep MemTotal /proc/meminfo\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-proc-sed-file-operand-fires", "a.sh",
     "sed -n 1p /proc/meminfo\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-proc-var-path-fires", "a.sh",
     "cat /proc/$pid/stat\ncat /proc/${pid}/stat\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    *((f"linux-only-proc-test{f}-ok", "a.sh", f"[ {f} /proc/loadavg ] && cat /proc/loadavg\n", OK, "")
      for f in ("-e", "-d", "-f")),
    ("linux-only-guard-names-in-one-segment-ok", "a.sh",
     "command -v setsid flock timeout >/dev/null || exit 0\nsetsid x\nflock l c\ntimeout 5 y\n", OK, ""),
    ("linux-only-path-test-guard-ok", "a.sh",
     "[ -x /usr/bin/timeout ] || exit 0\ntimeout 5 x\n[ -s /proc/loadavg ] && cat /proc/loadavg\n", OK, ""),
    # One case per wrapper and recipe prefix: each must reach the tool word alone.
    *((f"linux-only-{w.split()[0]}-wrapper-fires", "a.sh", f"{w} timeout 5 x\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT")
      for w in ("command", "stdbuf -oL", "ionice -c3", "chrt --idle", "taskset -c0")),
    ("linux-only-make-dash-recipe-fires", "Makefile",
     "test:\n\t-timeout 5 x\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-make-at-dash-plus-recipe-fires", "Makefile",
     "test:\n\t@-+timeout 5 x\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    # A tool run as its own probe is a preflight (file-wide, like `command -v`); a probe of
    # another tool, a call with more arguments and a mere mention are not.
    ("linux-only-self-probe-version-ok", "a.sh",
     "if ! timeout --version >/dev/null 2>&1; then echo \"not run: no timeout\"; exit 0; fi\n", OK, ""),
    ("linux-only-self-probe-true-ok", "a.sh",
     "if timeout 1 true 2>/dev/null; then HAVE=1; fi\n", OK, ""),
    *((f"linux-only-self-probe-{t}-version-clears-call-ok", "a.sh",
       f"{t} --version >/dev/null 2>&1 || exit 0\n{t} 60 make test\n", OK, "")
      for t in _LINUX_TOOLS),
    *((f"linux-only-self-probe-{n}-clears-call-ok", "a.sh", c, OK, "")
      for n, c in (("help", "timeout --help >/dev/null 2>&1 || exit 0\ntimeout 60 make test\n"),
                   ("spaced-redirect", "timeout --version > /dev/null 2>&1 || exit 0\ntimeout 60 make test\n"),
                   ("stdin-redirect", "timeout --version </dev/null || exit 0\ntimeout 60 make test\n"),
                   ("true", "if timeout 1 true 2>/dev/null; then HAVE=1; fi\ntimeout 60 make test\n"),
                   ("colon", "timeout 1 : || exit 0\ntimeout 60 make test\n"),
                   ("setsid-true", "setsid true || exit 0\nsetsid make test\n"),
                   ("option-then-payload","flock -n l true || exit 0\nflock l make test\n"))),
    ("linux-only-self-probe-other-tool-fires", "a.sh",
     "timeout --version >/dev/null 2>&1\nflock l c\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    ("linux-only-self-probe-payload-version-fires", "a.sh",
     "timeout 60 make --version\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    *((f"linux-only-self-probe-{n}-script-argument-fires", "a.sh", c, FAIL, "LINUX_ONLY_NO_PREFLIGHT")
      for n, c in (("timeout", "timeout 60 ./deploy.sh true\n"), ("setsid", "setsid ./deploy.sh true\n"))),
    ("linux-only-self-probe-mention-fires", "a.sh",
     "echo timeout --version\ntimeout 60 make test\n", FAIL, "LINUX_ONLY_NO_PREFLIGHT"),
    # `echo` and `printf` print a /proc word; only a redirect target is read.
    ("linux-only-proc-echo-literal-ok", "a.sh", "echo '/proc/loadavg'\n", OK, ""),
    ("linux-only-proc-printed-words-ok", "a.sh",
     "printf '%s\\n' /proc/loadavg\necho -n /proc/loadavg\necho /proc/loadavg > out.txt\n", OK, ""),
    *((f"linux-only-proc-{n}-redirect-target-fires", "a.sh", c, FAIL, "LINUX_ONLY_NO_PREFLIGHT")
      for n, c in (("echo-spaced", "echo 1 > /proc/sys/vm/drop_caches\n"),
                   ("echo-glued", "echo 1 >/proc/sys/vm/drop_caches\n"),
                   ("printf", "printf 3 > /proc/sys/vm/drop_caches\n"))),
    ("linux-only-allow-marker-suppresses", "a.sh",
     "setsid sh -c 'x'  # reaper-lint: allow linux container only\n", OK, ""),
)


def _selftest() -> int:
    failures: list[str] = []
    passed = 0

    def check(name: str, rc: int, lines: list[str], want_rc: int,
              must_have: tuple[str, ...] = (), must_not_have: tuple[str, ...] = ()) -> None:
        nonlocal passed
        joined = "\n".join(lines)
        ok = (rc == want_rc
              and all(needle in joined for needle in must_have)
              and all(needle not in joined for needle in must_not_have))
        if ok:
            passed += 1
        else:
            failures.append(f"{name}: rc={rc} (want {want_rc}); output={joined!r}")

    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for idx, (name, fname, content, want_rc, rule) in enumerate(_CASES):
            path = os.path.join(tmp, f"case{idx:02d}", fname)
            _write(path, content)
            rc, lines = run_gate([path])
            check(name, rc, lines, want_rc, must_have=(rule,) if rule else ())

        # Directory walk: scans shell/Makefile-family/YAML/package.json and
        # shebang-sniffed extensionless files; skips everything else.
        scandir = os.path.join(tmp, "scandir")
        bad = "pkill -f chromium\n"
        _write(os.path.join(scandir, "reap.sh"), "kill -9 $(lsof -ti :$port)\n")
        _write(os.path.join(scandir, "notes.txt"), bad)
        _write(os.path.join(scandir, "reap.mk"), "reap:\n\t" + bad)
        _write(os.path.join(scandir, "GNUmakefile"), "reap:\n\t" + bad)
        _write(os.path.join(scandir, "justfile"), "reap:\n    " + bad)
        _write(os.path.join(scandir, "bin", "cleanup"), "#!/bin/bash\n" + bad)
        _write(os.path.join(scandir, "bin", "envcleanup"), "#!/usr/bin/env bash\n" + bad)
        _write(os.path.join(scandir, "bin", "README"), bad)
        rc, lines = run_gate([scandir])
        check(
            "dir-scan-filters-and-sniffs", rc, lines, FAIL,
            must_have=("reap.sh", "LSOF_NO_LISTEN", "reap.mk", "GNUmakefile", "justfile",
                       os.path.join("bin", "cleanup"), os.path.join("bin", "envcleanup")),
            must_not_have=("notes.txt", "README"),
        )

        # Hook directories: `.git/hooks/*` is scanned despite the `.git` skip
        # (`*.sample` excluded), and extensionless hooks with no shebang in
        # `.husky/` / `.githooks/` are scanned without a shebang sniff.
        hookrepo = os.path.join(tmp, "hookrepo")
        live = "bash scripts/reaper.sh\n"
        _write(os.path.join(hookrepo, ".git", "hooks", "pre-commit"), "#!/bin/sh\n" + live)
        _write(os.path.join(hookrepo, ".git", "hooks", "pre-push.sample"), "#!/bin/sh\n" + live)
        _write(os.path.join(hookrepo, ".git", "config"), "[core]\n")
        _write(os.path.join(hookrepo, ".husky", "pre-push"), live)
        _write(os.path.join(hookrepo, ".githooks", "commit-msg"), live)
        _write(os.path.join(hookrepo, "docs", "NOTES"), live)
        rc, lines = run_gate([hookrepo])
        check(
            "dir-scan-walks-git-hooks-and-shebangless-hooks", rc, lines, FAIL,
            must_have=(os.path.join(".git", "hooks", "pre-commit") + ":",
                       os.path.join(".husky", "pre-push") + ":",
                       os.path.join(".githooks", "commit-msg") + ":"),
            must_not_have=("pre-push.sample", "NOTES", "config"),
        )

        # A linked worktree's `.git` gitfile resolves to the common dir's hooks.
        common = os.path.join(tmp, "commonrepo", ".git")
        _write(os.path.join(common, "hooks", "pre-commit"), live)
        _write(os.path.join(common, "worktrees", "wt", "commondir"), "../..\n")
        wt = os.path.join(tmp, "wt")
        _write(os.path.join(wt, ".git"), "gitdir: " + os.path.join(common, "worktrees", "wt") + "\n")
        rc, lines = run_gate([wt])
        check("dir-scan-gitfile-resolves-common-hooks", rc, lines, FAIL,
              must_have=(os.path.join("commonrepo", ".git", "hooks", "pre-commit") + ":",
                         "HOOK_LIVE_REAPER"))

        # A `.git` gitfile that does not parse -> ERROR (fail closed).
        badwt = os.path.join(tmp, "badwt")
        _write(os.path.join(badwt, ".git"), "not a gitfile\n")
        rc, lines = run_gate([badwt])
        check("dir-scan-bad-gitfile-errors", rc, lines, ERROR, must_have=("cannot resolve hooks",))

        # A named path that does not exist -> ERROR (fail closed).
        rc, lines = run_gate([os.path.join(tmp, "does-not-exist.sh")])
        check("missing-path-errors", rc, lines, ERROR)

        # Undecodable text -> ERROR, not a silent pass over mojibake.
        u16 = os.path.join(tmp, "u16", "reap.sh")
        _write(u16, "pkill -f chrome\n".encode("utf-16-le"))
        rc, lines = run_gate([u16])
        check("utf16-errors", rc, lines, ERROR, must_have=("cannot decode",))
        latin = os.path.join(tmp, "latin", "reap.sh")
        _write(latin, b"# caf\xe9\npkill -f chrome\n")
        rc, lines = run_gate([latin])
        check("invalid-utf8-errors", rc, lines, ERROR, must_have=("cannot decode",))

        # An unlistable directory during the walk -> ERROR (fail closed).
        locked_root = os.path.join(tmp, "lockroot")
        locked = os.path.join(locked_root, "locked")
        _write(os.path.join(locked, "x.sh"), bad)
        os.chmod(locked, 0)
        try:
            if os.access(locked, os.R_OK):
                skipped.append("unlistable-dir-errors (running with read access to a mode-000 "
                               "directory, e.g. as root; cannot plant the case)")
            else:
                rc, lines = run_gate([locked_root])
                check("unlistable-dir-errors", rc, lines, ERROR, must_have=("cannot list",))
        finally:
            os.chmod(locked, 0o700)

    total = passed + len(failures)
    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    for s in skipped:
        print(f"SELFTEST SKIPPED: {s}")
    print(f"SELFTEST OK: {passed}/{total} cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Heuristic lint: flag bulk/fleet-wide process-reaper patterns "
                    "in shell/Makefile/justfile/package.json-script/CI-YAML text."
    )
    parser.add_argument("paths", nargs="*", help="files and/or directories to scan")
    parser.add_argument("--selftest", action="store_true", help="run the built-in selftest and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.paths:
        parser.error("at least one file or directory is required")
        return ERROR  # pragma: no cover — parser.error() already exits(2)

    code, lines = run_gate(args.paths)
    out = sys.stdout if code == OK else sys.stderr
    for line in lines:
        print(line, file=out)
    return code


if __name__ == "__main__":
    sys.exit(main())
