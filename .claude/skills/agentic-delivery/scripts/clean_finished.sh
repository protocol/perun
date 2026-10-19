#!/usr/bin/env bash
# clean_finished.sh — remove your own finished worktrees and scratch. Safe to run on every tick.
# A worktree under ROOT is finished when its branch's PR is MERGED or CLOSED (gh pr view), or its branch is
# listed in HANDED_BACK (optional file, one branch per line: lanes that handed back). It is removed unless:
#   - a process has it open (lsof +D), or
#   - it has unpushed commits (commits not on any remote; a MERGED PR whose head is exactly HEAD counts as
#     pushed, since squash-and-delete-branch leaves no remote ref).
# A dirty worktree is archived first: `git diff HEAD` plus the untracked-file list go to
# ARCHIVE_DIR/<name>.patch, or <name>.N.patch when that exists (default $TMPDIR/worktree-archive), and it is removed only after the write succeeded.
# The main worktree and the one you run from are never removed. Untracked file CONTENTS are listed, not saved.
# Detached-HEAD worktrees have no branch to judge and are left alone.
# SCRATCH (optional, space-separated absolute paths): deleted only when the resolved path is strictly inside
# the resolved $TMPDIR; anything else is skipped with a message (an rm -rf on a variable path once wiped user apps).
# Env: ROOT (required, absolute dir: only worktrees under it are touched), GH (default gh).
# REPORT=1: read-only. Applies the same checks plus "tree is clean" (a dirty worktree is skipped, not archived), prints
# "would-remove <path>" per worktree that passes and "would_remove=N skipped=M"; removes, archives and deletes nothing, SCRATCH included.
# ONLY (a file, one absolute worktree path per line): consider just those worktrees and ignore ROOT (run_ledger.sh uses it); needs REPORT=1, else it exits 2 and removes nothing.
# Prints "removed=N skipped=M archived=K".
set -euo pipefail
: "${ROOT:=${ONLY:+/}}"; : "${ROOT:?set ROOT to your own worktree tree}"
ROOT=$(cd "$ROOT" && pwd -P); REPORT=${REPORT:-0}
[ -z "${ONLY:-}" ] || [ "$REPORT" = 1 ] || { echo "clean_finished: ONLY needs REPORT=1 (report-only); refusing to remove" >&2; exit 2; }
 GH=${GH:-$(dirname "$0")/gh_rest.py}; AR=${ARCHIVE_DIR:-${TMPDIR:-/tmp}/worktree-archive}
top=$(git rev-parse --show-toplevel); top=$(cd "$top" && pwd -P)
command -v lsof >/dev/null || { echo "clean_finished: lsof missing; cannot tell if a worktree is in use, removing nothing" >&2; exit 2; }
rm=0 sk=0 ar=0
while IFS=$'\t' read -r wt br; do
  [ "$wt" != "$top" ] || continue
  if [ -n "${ONLY:-}" ]; then grep -qxF "$wt" "$ONLY" || continue; else case "$wt" in "$ROOT"/*) ;; *) continue ;; esac; fi
  state="" head=""
  read -r state head < <("$GH" pr view "$br" --json state,headRefOid -q '.state+" "+.headRefOid' </dev/null 2>/dev/null || true) || true
  if [ "$state" != MERGED ] && [ "$state" != CLOSED ]; then
    { [ -n "${HANDED_BACK:-}" ] && grep -qxF "$br" "$HANDED_BACK" 2>/dev/null; } || continue
  fi
  # lsof exits 1 with no output when nothing holds the tree; any other outcome (output or error) means in use / could not check.
  lrc=0; held=$(lsof -t +D "$wt" 2>&1 </dev/null) || lrc=$?
  if [ -n "$held" ] || [ "$lrc" -gt 1 ]; then echo "clean_finished: skip $wt: in use or could not check (lsof rc=$lrc ${held%%$'\n'*})" >&2; sk=$((sk+1)); continue; fi
  if [ "$state" != MERGED ] || [ "$head" != "$(git -C "$wt" rev-parse HEAD)" ]; then
    [ "$(git -C "$wt" rev-list --count HEAD --not --remotes)" = 0 ] || { sk=$((sk+1)); continue; }
  fi
  if [ "$REPORT" = 1 ]; then
    if [ -n "$(git -C "$wt" status --porcelain)" ]; then echo "clean_finished: skip $wt: uncommitted or untracked files" >&2; sk=$((sk+1)); else echo "would-remove $wt"; rm=$((rm+1)); fi
    continue
  fi
  if [ -n "$(git -C "$wt" status --porcelain)" ]; then
    mkdir -p "$AR"; f="$AR/$(basename "$wt").patch" i=0
    while [ -e "$f" ]; do i=$((i+1)); f="$AR/$(basename "$wt").$i.patch"; done  # same-named worktrees must not overwrite an archive
    { git -C "$wt" diff HEAD; echo "# untracked:"; git -C "$wt" ls-files --others --exclude-standard; } >"$f" || { sk=$((sk+1)); continue; }
    ar=$((ar+1))
  fi
  if git worktree remove --force "$wt" >/dev/null 2>&1; then rm=$((rm+1)); else sk=$((sk+1)); fi
done < <(git worktree list --porcelain | awk '/^worktree /{w=substr($0,10)} /^branch /{print w "\t" substr($0,19)}')
tmp_root=$(cd "${TMPDIR:-/nonexistent}" 2>/dev/null && pwd -P) || tmp_root=""
for s in $([ "$REPORT" = 1 ] || echo "${SCRATCH:-}"); do
  r=$(cd "$s" 2>/dev/null && pwd -P) || { echo "scratch skip (not a directory): $s" >&2; continue; }
  case "$r" in
    "$tmp_root"/?*) [ -n "$tmp_root" ] && rm -rf "$r" ;;
    *) echo "scratch skip (outside \$TMPDIR): $s" >&2 ;;
  esac
done
if [ "$REPORT" = 1 ]; then echo "would_remove=$rm skipped=$sk"; else echo "removed=$rm skipped=$sk archived=$ar"; fi
