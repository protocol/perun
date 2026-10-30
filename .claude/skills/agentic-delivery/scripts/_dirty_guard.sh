# Sourced by scripts that run `git checkout|switch|reset` on a caller-given tree.
# require_clean_tree [dir]: returns 0 when the tree has no tracked changes (untracked files survive a checkout);
# otherwise prints the exact fix to stderr and returns 1 (callers `|| exit 2`), so uncommitted edits are never
# silently wiped. A failing `git status` (bad dir, broken index) counts as dirty: fail closed.

# rail: owner=agentic-delivery, why=refuse a checkout that would wipe uncommitted edits, review=2027-01-30
require_clean_tree() {
  local d=${1:-.} out
  out=$(git -C "$d" status --porcelain --untracked-files=no 2>&1) && [ -z "$out" ] && return 0
  echo "REFUSE: $d has uncommitted changes (or git status failed) and this script would check out over them. Fix: commit or stash them (git -C \"$d\" stash), or run from a throwaway worktree (git worktree add --detach <dir> origin/main)." >&2
  return 1
}
