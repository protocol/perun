#!/usr/bin/env bash
# run_ledger.sh — report-only teardown list: the finished worktrees and still-running dev servers that EARLIER runs recorded creating, plus the exact owner-run lines to remove them.
# Usage: run_ledger.sh record-worktree <abs path> | record-pid <pid>   (call right after creating the worktree / starting the server; needs a run id)
#        run_ledger.sh [--count]    report: removes, kills and writes nothing (--count prints just the number; session_brief uses it)
# Run id: PERUN_RUN_ID, else CLAUDE_SESSION_ID (letters, digits, . _ -). Each run writes only its own file under
# ${PERUN_LEDGER_DIR:-${XDG_STATE_HOME:-~/.local/state}/perun/runs}/<id>.tsv; the report skips the CURRENT run's file, so a live run is never listed.
# A recorded worktree is listed only when clean_finished.sh's own checks pass (REPORT=1 ONLY=<recorded paths>): PR MERGED/CLOSED or in HANDED_BACK,
# no unpushed commits, nothing holding it, and no uncommitted or untracked files. HEAD being in origin/main is NOT enough: a fresh worktree sits there.
# A recorded pid is listed when it is alive and reap_own.sh's alive/age helpers plus the recorded command and cwd agree it is the same process (a reused pid
# started after the record never matches). Where ps is denied the age check is skipped and only command + cwd must match.
# Deleting stays the owner's decision: copy the printed lines to act. Unrecorded paths and pids are never listed.
# Prints "leftover=N"; exit 2 with "leftover=COULD_NOT_CHECK" when a check could not run (never a false 0).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); GH=${GH:-$HERE/gh_rest.py}; export GH
LD=${PERUN_LEDGER_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/perun/runs}; RUN=${PERUN_RUN_ID:-${CLAUDE_SESSION_ID:-}}
nl=$'\n'; tab=$'\t'
case "$RUN" in *[!A-Za-z0-9._-]*) echo "run_ledger: run id has characters outside A-Za-z0-9._-" >&2; exit 1 ;; esac
common() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
linked() { [ -n "${1:-}" ] && [ "${1#/}" != "$1" ] && [ -d "$1" ] && [ "$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null)" != "$(common "$1")" ]; }  # absolute, exists, not a main checkout
ident() { lsof -a -p "$1" -d cwd -Fcn 2>/dev/null | tr '\n\t' '  ' || true; }  # command + cwd of a live pid; empty when not running
case "${1:-}" in record-worktree|record-pid)
  [ -n "$RUN" ] || { echo "run_ledger: set PERUN_RUN_ID (or CLAUDE_SESSION_ID); refusing to record without a run id" >&2; exit 1; }
  mkdir -p "$LD"; F="$LD/$RUN.tsv" ;;
esac
case "${1:-}" in
  record-worktree)
    p=${2:-}; case "$p" in ''|*"$tab"*|*"$nl"*) echo "run_ledger: refusing an empty path or one with tab/newline" >&2; exit 1 ;; esac
    p=$(cd "$p" 2>/dev/null && pwd -P) || { echo "run_ledger: not a directory: ${2:-}" >&2; exit 1; }
    linked "$p" || { echo "run_ledger: not a linked git worktree: $p" >&2; exit 1; }
    printf 'wt\t%s\n' "$p" >>"$F"; exit 0 ;;
  record-pid)
    p=${2:-}; case "$p" in ''|*[!0-9]*) echo "run_ledger: pid must be a number" >&2; exit 1 ;; esac
    s=$(ident "$p"); [ -n "$s" ] || { echo "run_ledger: cannot identify pid $p (not running or lsof denied)" >&2; exit 1; }
    printf 'pid\t%s\t%s\t%s\n' "$p" "$(date +%s)" "$s" >>"$F"; exit 0 ;;
  ""|--count) ;;
  *) echo "usage: run_ledger.sh [--count] | record-worktree PATH | record-pid PID" >&2; exit 1 ;;
esac
MODE=${1:-report}
files=(); for f in "$LD"/*.tsv; do [ -f "$f" ] && [ "$f" != "$LD/$RUN.tsv" ] && files+=("$f"); done
[ ${#files[@]} -gt 0 ] || { [ "$MODE" = --count ] && echo 0 || echo "leftover=0"; exit 0; }
command -v lsof >/dev/null || { echo "run_ledger: lsof missing; cannot tell if a worktree is in use" >&2; echo "leftover=COULD_NOT_CHECK"; exit 2; }
export REAP_OWN_SOURCE_ONLY=1; . "$HERE/reap_own.sh"   # alive, age
n=0; out=""; now=$(date +%s)
only=$(mktemp "${TMPDIR:-/tmp}/run-ledger.XXXXXX"); trap '[ -z "${only:-}" ] || rm -f "$only"' EXIT
mains=""
while IFS=$'\t' read -r kind a b c; do
  case "$kind" in
  wt) linked "$a" || continue   # gone, or never a linked worktree: nothing to list
      printf '%s\n' "$a" >>"$only"
      mains="$mains$(git -C "$a" worktree list --porcelain | sed -n '1s/^worktree //p')$nl" ;;
  pid) case "$a" in ''|*[!0-9]*|0|1) continue ;; esac
      [ "$a" != "$$" ] && [ "$a" != "$PPID" ] && alive "$a" || continue
      [ "$(ident "$a")" = "$c" ] || continue                                  # another command or cwd now owns this pid
      e=$(age "$a"); [ -z "$e" ] || [ "$e" -ge $((now - b - 5)) ] || continue  # started after it was recorded: a reused pid
      n=$((n+1)); out="${out}kill $a   # ${c}$nl" ;;
  esac
done < <(cat "${files[@]}")
while read -r m; do
  [ -n "$m" ] || continue
  r=$(cd "$m" && ONLY="$only" REPORT=1 bash "$HERE/clean_finished.sh") || { echo "leftover=COULD_NOT_CHECK"; exit 2; }
  while read -r k w; do
    [ "$k" = would-remove ] || continue
    n=$((n+1)); out="$out$(printf 'git --git-dir=%q worktree remove %q' "$(common "$w")" "$w")$nl"
  done <<<"$r"
done < <(printf '%s' "$mains" | sort -u)
if [ "$MODE" = --count ]; then echo "$n"; exit 0; fi
[ -z "$out" ] || printf '# owner-run lines; this script removes and kills nothing:\n%s' "$out"
echo "leftover=$n"
