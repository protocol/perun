#!/usr/bin/env bash
# lane_worktree.sh <name> [base] — make a lane worktree outside the repo tree.
# Root: ${PERUN_WT_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/perun-wt}/<repo>. Worktrees inside the repo dir make file watchers
# (fseventsd) scan every lane's tree (one host: 129 worktrees, 49GB, fseventsd at 158% CPU).
# Branch lane/<name> off <base> (default origin/main); prints the path. <name> is one path segment: no "/", no "..".
# Writes the marker <git-dir>/perun-lane (branch, repo, path, optional agent=$PERUN_AGENT_ID) that handback_cap.py requires
# before it removes the tree when its lane stops. Never forces; refuses an existing path or branch. Needs no recent git.
set -euo pipefail
name=${1:?usage: lane_worktree.sh <name> [base]}; base=${2:-origin/main}
case "$name" in */*|*..*|-*|.*) echo "lane_worktree: bad name '$name' (no '/', '..', leading '-' or '.')" >&2; exit 2 ;; esac
common=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
repo=$(basename "$common"); [ "$repo" != .git ] || repo=$(basename "$(dirname "$common")")
root=${PERUN_WT_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/perun-wt}
case "$root" in /|"") echo "lane_worktree: refusing root '$root'" >&2; exit 2 ;; esac
mkdir -p "$root/$repo"; dir=$(cd "$root/$repo" && pwd -P)/$name
git worktree add -b "lane/$name" "$dir" "$base" >&2
gd=$(cd "$dir" && cd "$(git rev-parse --git-dir)" && pwd -P)
printf 'branch=lane/%s\nrepo=%s\npath=%s\nagent=%s\n' "$name" "$common" "$dir" "${PERUN_AGENT_ID:-}" >"$gd/perun-lane"
echo "$dir"
