# Sourced by scripts that run `git checkout|switch|reset` on a caller-given tree.
# require_clean_tree [dir]: returns 0 when the tree has no tracked changes (untracked files survive a checkout); otherwise prints the
# exact fix to stderr and returns 1 (callers `|| exit 2`), so uncommitted edits are never silently wiped.
require_clean_tree() {
  local d=${1:-.}
  [ -z "$(git -C "$d" status --porcelain --untracked-files=no 2>/dev/null)" ] && return 0
  echo "REFUSE: $d has uncommitted changes and this script would check out over them. Fix: commit or stash them (git -C $d stash), or run from a throwaway worktree (git worktree add --detach <dir> origin/main)." >&2
  return 1
}
