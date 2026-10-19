#!/usr/bin/env bash
# run_ledger.sh — report-first teardown: list the finished worktrees and dev servers THIS run recorded creating, and the exact owner-run removal lines.
# Usage: run_ledger.sh record-worktree <abs path> | record-pid <pid>   (call right after creating the worktree / starting the server)
#        run_ledger.sh [--count]    report only: changes nothing; --count prints just the leftover number (session_brief uses it)
#        run_ledger.sh --remove     removes only RECORDED leftovers; anything else is refused
# Ledger: ${PERUN_LEDGER:-${XDG_STATE_HOME:-~/.local/state}/perun/run-ledger.tsv}; rows `wt<TAB>path` and `pid<TAB>pid<TAB>identity`.
# A worktree is a leftover when it is a linked worktree whose HEAD is in origin/main or whose PR is MERGED/CLOSED (GH, default gh_rest.py, as
# clean_finished.sh), with no unpushed commits, a clean tree and no process holding it; removal is `git worktree remove` WITHOUT --force.
# A pid is a leftover when it is alive with the recorded identity (start time, command, cwd; a reused pid never matches), owned by you; removal is SIGTERM, then SIGKILL after 5s.
# For sweeping unrecorded servers by cwd use reap_own.sh --report; this script never touches what it did not record.
# Prints "leftover=N"; exit 2 with "leftover=COULD_NOT_CHECK" when a check could not run (never a false 0).
set -euo pipefail
L=${PERUN_LEDGER:-${XDG_STATE_HOME:-$HOME/.local/state}/perun/run-ledger.tsv}; GH=${GH:-$(dirname "$0")/gh_rest.py}
nl=$'\n'; tab=$'\t'
# process identity = start time (ps, empty where ps is denied) + command and cwd (lsof); empty when the pid is not running
ident() { local l; l=$(lsof -a -p "$1" -d cwd -Fcn 2>/dev/null | tr '\n\t' '  ') || true; [ -n "$l" ] || return 0
  { LC_ALL=C ps -o lstart= -p "$1" 2>/dev/null || true; } | tr '\n\t' '  '; printf '|%s' "$l"; }
common() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
linked() { [ -n "${1:-}" ] && [ "${1#/}" != "$1" ] && [ -d "$1" ] && [ "$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null)" != "$(common "$1")" ]; }  # absolute, exists, not a main checkout
case "${1:-}" in
  record-worktree)
    p=${2:-}; case "$p" in ''|*"$tab"*|*"$nl"*) echo "run_ledger: refusing an empty path or one with tab/newline" >&2; exit 1 ;; esac
    p=$(cd "$p" 2>/dev/null && pwd -P) || { echo "run_ledger: not a directory: ${2:-}" >&2; exit 1; }
    linked "$p" || { echo "run_ledger: not a linked git worktree: $p" >&2; exit 1; }
    mkdir -p "$(dirname "$L")"; printf 'wt\t%s\n' "$p" >>"$L"; exit 0 ;;
  record-pid)
    p=${2:-}; case "$p" in ''|*[!0-9]*) echo "run_ledger: pid must be a number" >&2; exit 1 ;; esac
    s=$(ident "$p"); [ -n "$s" ] || { echo "run_ledger: cannot identify pid $p (not running or lsof denied)" >&2; exit 1; }
    mkdir -p "$(dirname "$L")"; printf 'pid\t%s\t%s\n' "$p" "$s" >>"$L"; exit 0 ;;
  ""|--count|--remove) ;;
  *) echo "usage: run_ledger.sh [--count|--remove] | record-worktree PATH | record-pid PID" >&2; exit 1 ;;
esac
MODE=${1:-report}; [ -f "$L" ] || { [ "$MODE" = --count ] && echo 0 || echo "leftover=0"; exit 0; }
command -v lsof >/dev/null || { echo "run_ledger: lsof missing; cannot tell if a worktree is in use" >&2; echo "leftover=COULD_NOT_CHECK"; exit 2; }
n=0 bad=0 keep=""; out=""
while IFS=$'\t' read -r kind a b; do
  case "$kind" in
  wt)
    linked "$a" || continue   # gone, or never a linked worktree: nothing to remove, drop the row
    br=$(git -C "$a" symbolic-ref -q --short HEAD || true); head=$(git -C "$a" rev-parse HEAD)
    inmain=0; git -C "$a" merge-base --is-ancestor "$head" origin/main 2>/dev/null && inmain=1
    state="" ph=""
    [ -z "$br" ] || [ $inmain = 1 ] || read -r state ph < <("$GH" pr view "$br" --json state,headRefOid -q '.state+" "+.headRefOid' </dev/null 2>/dev/null || true) || true
    if [ $inmain = 1 ] || { [ "$state" = MERGED ] && [ "$ph" = "$head" ]; }; then pushed=1
    elif [ "$state" = MERGED ] || [ "$state" = CLOSED ]; then pushed=0
    else keep="$keep$kind$tab$a$nl"; continue; fi   # still active: not a leftover
    why=""
    [ "$pushed" = 1 ] || [ "$(git -C "$a" rev-list --count HEAD --not --remotes)" = 0 ] || why="unpushed commits"
    [ -z "$why" ] && [ -n "$(git -C "$a" status --porcelain)" ] && why="dirty tree"
    lrc=0; held=$(lsof -t +D "$a" 2>&1 </dev/null) || lrc=$?
    [ -z "$why" ] && { [ -n "$held" ] || [ "$lrc" -gt 1 ]; } && why="in use or lsof failed"
    n=$((n+1))
    if [ -n "$why" ]; then out="$out# kept (worktree $a): $why$nl"; keep="$keep$kind$tab$a$nl"; continue; fi
    cd=$(common "$a")
    if [ "$MODE" = --remove ] && git --git-dir="$cd" worktree remove "$a" >/dev/null 2>&1; then out="$out# removed worktree $a$nl"; continue; fi
    out="$out$(printf 'git --git-dir=%q worktree remove %q' "$cd" "$a")$nl"; keep="$keep$kind$tab$a$nl" ;;
  pid)
    case "$a" in ''|*[!0-9]*|0|1) bad=1; continue ;; esac
    [ "$a" != "$$" ] && [ "$a" != "$PPID" ] || continue
    [ "$(ident "$a")" = "$b" ] || continue   # dead, or the pid was reused by another process: not ours
    n=$((n+1))
    if [ "$MODE" = --remove ]; then
      kill "$a" 2>/dev/null || true; for _ in $(seq 20); do kill -0 "$a" 2>/dev/null || break; sleep 0.25; done
      kill -0 "$a" 2>/dev/null && { kill -9 "$a" 2>/dev/null || true; sleep 0.2; }
      if kill -0 "$a" 2>/dev/null; then out="$out# pid $a survived SIGKILL$nl"; keep="$keep$kind$tab$a$tab$b$nl"; else out="$out# stopped pid $a$nl"; fi
    else out="${out}kill $a   # ${b#*|}$nl"; keep="$keep$kind$tab$a$tab$b$nl"; fi ;;
  esac
done <"$L"
if [ "$MODE" = --count ]; then echo "$n"; exit 0; fi
printf '%s' "$out"
if [ "$MODE" = --remove ]; then printf '%s' "$keep" >"$L.tmp.$$" && mv "$L.tmp.$$" "$L"; fi
[ "$bad" = 0 ] || echo "# ignored a ledger row with an invalid pid" >&2
echo "leftover=$n"
