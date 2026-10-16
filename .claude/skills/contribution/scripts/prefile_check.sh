#!/usr/bin/env bash
# prefile_check.sh <title-file> <body-file> — run BEFORE `gh issue create` on the public repo.
# Refuses (exit 1) when title or body hits the banlist (.banlist.txt + .banlist.local.txt, if
# present, resolved from the git root or $BANLIST_DIR) or a generic pattern: an <org>/<repo>
# reference other than this repo, a #NNNN+ cross-repo issue number, or an absolute home path.
# Exit 2 on usage error or missing/empty banlist (fail closed). Prints pattern NAMES only, never
# the matched text. Side effects: none. Deliberately strict: "and/or" or "src/foo" also match
# the repo-ref pattern; rephrase. A project-only bug belongs in that project's tracker, not here.
set -u
SELF_REPO='protocol/perun'
[ "$#" -eq 2 ] && [ -f "$1" ] && [ -f "$2" ] || { echo "usage: prefile_check.sh <title-file> <body-file>" >&2; exit 2; }
dir="${BANLIST_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -s "$dir/.banlist.txt" ] || { echo "prefile_check: $dir/.banlist.txt missing or empty (fail closed)" >&2; exit 2; }
text="$(cat "$1" "$2")"
hits=0
flag() { echo "prefile_check: REFUSE: $1" >&2; hits=1; }
for f in "$dir/.banlist.txt" "$dir/.banlist.local.txt"; do
  [ -f "$f" ] || continue
  while IFS= read -r p || [ -n "$p" ]; do
    p="${p#"${p%%[![:space:]]*}"}"
    case "$p" in ''|'#'*) continue ;; esac
    printf '%s' "$text" | grep -qE -e "$p" 2>/dev/null; rc=$?
    [ "$rc" -eq 0 ] && flag "banlist pattern hit in $(basename "$f") (content withheld)"
    [ "$rc" -ge 2 ] && flag "invalid regex in $(basename "$f") (fail closed, content withheld)"
  done < "$f"
done
printf '%s\n' "$text" | grep -oE '[A-Za-z0-9-]+/[A-Za-z0-9._-]+' | grep -vxF "$SELF_REPO" | grep -q . \
  && flag "repo-ref or path-like <org>/<repo> other than $SELF_REPO"
printf '%s' "$text" | grep -qE '#[0-9]{4,}' && flag "#NNNN+ issue reference (likely another tracker)"
printf '%s' "$text" | grep -qE '(/Users/|/home/|[A-Za-z]:\\Users\\)[A-Za-z0-9._-]+' && flag "absolute home path"
[ "$hits" -eq 0 ] && echo "prefile_check: clean"
exit "$hits"
