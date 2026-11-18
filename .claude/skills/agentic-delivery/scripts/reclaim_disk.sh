#!/usr/bin/env bash
# reclaim_disk.sh — prune finished lane worktrees, merged branches. Lists (default) or removes them, using git state only.
# A linked worktree is listed when it is not locked, has no modified, untracked or ignored files (so .env, venvs and
# build output are never lost), and its HEAD is reachable from origin/main (else main) or from any other local or remote
# branch, so removing it loses no commit. Then local branches merged into that base are listed: ones with no worktree,
# plus ones whose worktree is listed above (never main/master, or a branch checked out in a worktree that stays).
# Dry run by default; it lists what --apply attempts (git may still refuse an item: a skip line). --apply runs
# `git worktree remove <path>` (never --force) and `git branch -D -- <name>`; -D is safe only because each branch was
# just verified merged into the base (plain -d checks HEAD, not the base, and would refuse items the dry run listed).
# No rm -rf, no path built from input.
# Fresh items are protected: a worktree (HEAD reflog) or branch (branch reflog) is listed only when its last reflog move
# is older than RECLAIM_MIN_AGE_HOURS (default 24; values below 1 or non-numeric use 24 with a stderr note; values above 87600 are clamped to 87600); a missing
# or unparsable reflog counts as young and is skipped (fail closed). There is no live-session check beyond the lock: agent worktrees are locked while
# running, so a locked worktree is skipped, and an unlocked, clean worktree older than the age is treated as abandoned. main, master, develop, trunk, release*,
# production, staging, stable, dev and gh-pages are never listed. Do not run it while lanes are being spawned.
# Ineligible worktrees: hidden changes (assume-unchanged or skip-worktree entries) or an unfinished rebase, merge,
# cherry-pick, revert or bisect; a skip-worktree entry whose file is absent (sparse checkout) hides nothing. Inherited
# repo-local GIT_* variables (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, ...) are unset first. Refs are always qualified
# (refs/remotes/origin/main, refs/heads/main), never bare names. Run from inside the repo; the worktree you run from and
# the main checkout are never listed.
# Prints "would-remove ..." / "removed ..." lines, "skip <item> (reason)" on stderr, and "worktrees=N branches=M".
set -euo pipefail
# shellcheck disable=SC2046  # the variable names are meant to word-split
unset $(git rev-parse --local-env-vars)  # an inherited GIT_DIR would make every git -C "$wt" below judge that repo instead
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
top=$(git rev-parse --show-toplevel); top=$(cd "$top" && pwd -P)
base=refs/remotes/origin/main; git rev-parse -q --verify "$base" >/dev/null || base=refs/heads/main
git rev-parse -q --verify "$base" >/dev/null || { echo "reclaim_disk: no origin/main or main to compare against" >&2; exit 2; }
verb=would-remove; [ "$APPLY" = 1 ] && verb=removed
AGE=${RECLAIM_MIN_AGE_HOURS:-24}; case "$AGE" in ''|*[!0-9]*) AGE=0 ;; esac; [ ${#AGE} -le 6 ] || AGE=87600; AGE=$((10#$AGE)); [ "$AGE" -le 87600 ] || AGE=87600
if [ "$AGE" -lt 1 ]; then echo "reclaim_disk: RECLAIM_MIN_AGE_HOURS must be a positive integer, using 24" >&2; AGE=24; fi
young() { local ct; ct=$(git -C "$1" reflog show -1 --date=unix --format=%gd "$2" 2>/dev/null || true); ct=${ct#*@\{}; ct=${ct%\}}; case "$ct" in ''|*[!0-9]*) echo "skip $1 $2 (reflog missing or unparsable, treated as young)" >&2; return 0 ;; esac && [ $(( $(date +%s) - ct )) -lt $((AGE*3600)) ]; }
# NUL-safe capture: \1 stands in for NUL (bash variables cannot hold NUL); failure aborts instead of listing nothing
wl=$(git worktree list --porcelain -z | tr '\0' '\1') || exit 2
refs=$(git for-each-ref refs/heads --format='%(refname)') || exit 2
nw=0 nb=0 first=1 gone=$'\1'  # gone: \1-delimited list of removed worktree paths
wt='' br=- lk=0
flush() {  # decide one worktree record (wt br lk)
  if [ "$first" = 1 ]; then first=0; return 0; fi  # guard:main first entry is the main checkout
  case "$wt" in *$'\n'*|*$'\1'*) echo "skip a worktree whose path has a newline or control character" >&2; return 0 ;; esac
  raw=$wt; wt=$(cd "$wt" 2>/dev/null && pwd -P) || return 0
  [ "$wt" != "$top" ] || return 0  # guard:top
  if [ "$lk" = 1 ]; then echo "skip $wt (locked)" >&2; return 0; fi  # guard:locked
  if [ -n "$(git -C "$wt" status --porcelain --ignored --untracked-files=all 2>/dev/null || echo x)" ]; then echo "skip $wt (modified, untracked or ignored files such as .env or venv)" >&2; return 0; fi  # guard:dirty
  gd=$(git -C "$wt" rev-parse --absolute-git-dir) || return 0
  for m in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do if [ -e "$gd/$m" ]; then echo "skip $wt (unfinished $m)" >&2; return 0; fi; done  # guard:inprogress
  lf=$(git -C "$wt" ls-files -v -z | tr '\0' '\1') || { echo "skip $wt (ls-files failed)" >&2; return 0; }
  hid=0  # assume-unchanged (lowercase tag) always hides changes; skip-worktree (S) only when its file is on disk
  while IFS= read -r -d $'\1' e; do case "$e" in [a-z]\ *) hid=1 ;; S\ *) if [ -e "$wt/${e#S }" ] || [ -L "$wt/${e#S }" ]; then hid=1; fi ;; esac; done <<<"$lf"
  if [ "$hid" = 1 ]; then echo "skip $wt (assume-unchanged or skip-worktree entries hide changes)" >&2; return 0; fi  # guard:hidden
  # refs containing HEAD, minus this worktree's own branch and symbolic origin/HEAD
  safe=$(git -C "$wt" for-each-ref --contains HEAD --format='%(refname)' refs/heads refs/remotes | grep -vxF "$br" | grep -v '/HEAD$' || true)
  if [ -z "$safe" ]; then echo "skip $wt (HEAD not reachable from any other branch)" >&2; return 0; fi  # guard:reach
  if young "$wt" HEAD; then echo "skip $wt (newer than ${AGE}h)" >&2; return 0; fi  # guard:young
  if [ "$APPLY" = 1 ]; then git worktree remove "$wt" 2>/dev/null || { echo "skip $wt (git refused)" >&2; return 0; }; fi
  echo "$verb worktree $wt"; nw=$((nw+1)); gone="$gone$raw"$'\1'
}
while IFS= read -r -d $'\1' f; do  # NUL-separated porcelain: a record ends at an empty field
  case "$f" in
    "worktree "*) wt=${f#worktree }; br=-; lk=0 ;;
    "branch "*) br=${f#branch } ;;
    locked*) lk=1 ;;
    "") flush ;;
  esac
done <<<"$wl"
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  b=${ref#refs/heads/}
  case "$b" in main|master|develop|trunk|release*|production|staging|stable|dev|gh-pages) continue ;; esac  # guard:protected
  git merge-base --is-ancestor "$ref" "$base" || continue  # guard:merged
  # a branch with a worktree is listed only when that worktree was listed above
  wp=$(git for-each-ref "$ref" --format='%(worktreepath)')
  if [ -n "$wp" ]; then case "$gone" in *$'\1'"$wp"$'\1'*) ;; *) continue ;; esac; fi  # guard:checkedout
  if young . "$ref"; then echo "skip $b (newer than ${AGE}h)" >&2; continue; fi  # guard:freshbr
  if [ "$APPLY" = 1 ]; then git branch -D -- "$b" >/dev/null 2>&1 || { echo "skip $b (git refused)" >&2; continue; }; fi
  echo "$verb branch $b"; nb=$((nb+1))
done <<<"$refs"
echo "worktrees=$nw branches=$nb"
