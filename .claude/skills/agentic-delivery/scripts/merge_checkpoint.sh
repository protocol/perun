#!/usr/bin/env bash
# merge_checkpoint.sh save|status — survive a merge lane that stalls half-done (conflicts resolved but
# unstaged, one denied call) so the next session resumes instead of redoing or aborting.
# save: writes <git-dir>/perun-merge-state (MERGE_HEAD, resolved and unresolved files, next command).
#   Needs an in-progress merge; exit 2 otherwise. status: prints a one-line resume instruction, or nothing
#   when no state file exists (exit 0); a stale file (merge no longer in progress) says so. Run in the merge worktree.
set -u
GD=$(git rev-parse --git-dir) || exit 2
F=$GD/perun-merge-state
case "${1:-}" in
save)
  [ -f "$GD/MERGE_HEAD" ] || { echo "merge_checkpoint: no merge in progress" >&2; exit 2; }
  un= rs=  # ponytail: a file still listing as unmerged is "resolved" once its conflict markers are gone
  for f in $(git diff --name-only --diff-filter=U); do
    if grep -q '^<<<<<<< ' "$f" 2>/dev/null; then un="$un $f"; else rs="$rs $f"; fi
  done
  un=${un# } rs=${rs# }
  if [ -n "$un" ]; then nx="resolve the unresolved files, then git add all"
  else nx="git add -A (resolved files) && git commit --no-edit (let the hooks run; never bypass)"; fi
  { echo "MERGE_HEAD=$(cat "$GD/MERGE_HEAD")"; echo "resolved=$rs"; echo "unresolved=$un"; echo "next=$nx"; } >"$F"
  echo "saved $F" ;;
status)
  [ -f "$F" ] || exit 0
  [ -f "$GD/MERGE_HEAD" ] || { echo "merge checkpoint is stale (no merge in progress); remove $F"; exit 0; }
  v() { sed -n "s/^$1=//p" "$F"; }
  echo "resume merge $(v MERGE_HEAD | cut -c1-8): unresolved [$(v unresolved)], resolved [$(v resolved)]; next: $(v next)" ;;
*) echo "usage: merge_checkpoint.sh save|status" >&2; exit 2 ;;
esac
