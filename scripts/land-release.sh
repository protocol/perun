#!/usr/bin/env bash
# land-release.sh [--regen] — stamp a release at merge time so parallel lanes never collide on a version.
#
# Lanes do NOT bump. A lane adds changelog.d/<slug>.md (the body that goes under the release heading,
# e.g. "### Added" + bullets) and commits no generated artifact (INDEX.md and INDEX-scripts.md files incl. docs/INDEX.md, SHA256SUMS, size-budgets.tsv
# rows): committing them makes any two lanes conflict. CI rebuilds them for an unlanded tree with
# `scripts/regen-unlanded.sh` (which calls `--regen`); the land commit below carries them, checked byte-for-byte.
#
# Land mode (no flag), run on the lane branch at merge time, serialized by a lock under the git common
# dir (shared by every worktree): merges origin/main (generated-file conflicts are resolved by
# regenerating; any other conflict aborts), takes the next minor version from main's VERSION, stamps the
# lockstep set (3 VERSION files, 3 SKILL.md metadata.version, the Claude and Codex plugin.json, gemini-extension.json), folds every fragment into
# CHANGELOG.md under a new heading, deletes the fragments, regenerates, and makes one commit. Push/merge
# is the caller's. A lane that lands second just re-runs this: no rebump by hand, no force-push.
#
# size-budgets.tsv rows are rewritten to current sizes; a raise still needs the `size-budget-raise:`
# marker in the fragment (enforced by `ci-gates.sh size-ratchet`). Land refuses a fragment that
# `ci-gates.sh fragments` rejects (a malformed marker, a `## ` heading): the check .githooks/pre-commit runs on staged fragments.
# `land-release.sh tag` (run AFTER the release commit is on origin/main): creates and pushes annotated tag vX.Y.Z
# on the commit that introduced that VERSION on origin/main; refuses if origin/main is not at that version;
# an existing local tag is skipped with a message. Land itself never tags.
# `land-release.sh publish` = `tag` plus a GitHub release (gh release create --verify-tag --latest) whose notes are the
# CHANGELOG section for the version plus a link to the full CHANGELOG. No-op (exit 0) unless origin/main is at this
# checkout's version, or when policy `release_every` (.perun/policy.json, default 1) = N and the minor is not a
# multiple of N. Idempotent: an existing release only gets its notes updated. Never moves a tag: a local or remote
# tag on another commit is refused. Env also: GH (gh), REPO_URL (changelog link base; default from the remote).
# Env: REMOTE (origin), BASE_BRANCH (main), RELEASE_DATE (today). Exit 0 ok, 1 failure, 2 usage.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE=${REMOTE:-origin} BASE_BRANCH=${BASE_BRANCH:-main}
mode=land
case "${1:-}" in "") ;; --regen) mode=regen ;; tag|publish) mode=$1 ;; *) echo "usage: land-release.sh [--regen|tag|publish]" >&2; exit 2 ;; esac

if [ "$mode" = tag ] || [ "$mode" = publish ]; then
  git fetch -q "$REMOTE" "$BASE_BRANCH"
  ver=$(git show "$REMOTE/$BASE_BRANCH:.claude/skills/deep-code-review/VERSION" | tr -d '[:space:]')
  if [ "$mode" = publish ]; then
    [ "$ver" = "$(tr -d '[:space:]' <.claude/skills/deep-code-review/VERSION)" ] \
      || { echo "land-release publish: $REMOTE/$BASE_BRANCH is at $ver, not this checkout; nothing to publish"; exit 0; }
    every=$(python3 .claude/skills/agentic-delivery/scripts/perun_policy.py get release_every) \
      || { echo "land-release publish: bad .perun/policy.json" >&2; exit 1; }
    [ $(( $(cut -d. -f2 <<<"$ver") % every )) -eq 0 ] \
      || { echo "land-release publish: release_every=$every, skipping $ver"; exit 0; }
  fi
  [ "$ver" = "$(tr -d '[:space:]' <.claude/skills/deep-code-review/VERSION)" ] \
    || { echo "land-release tag: $REMOTE/$BASE_BRANCH is at $ver, this checkout is not; merge the release first, then run tag" >&2; exit 1; }
  sha=$(git log -1 --format=%H "$REMOTE/$BASE_BRANCH" -S"$ver" -- .claude/skills/deep-code-review/VERSION)
  [ -n "$sha" ] || { echo "land-release tag: release commit for $ver not found on $REMOTE/$BASE_BRANCH" >&2; exit 1; }
  if git rev-parse -q --verify "refs/tags/v$ver" >/dev/null; then
    echo "land-release tag: v$ver already exists locally; skipping creation"
    [ "$(git rev-parse "v$ver^{commit}")" = "$sha" ] || { echo "land-release tag: local v$ver points elsewhere than $sha" >&2; exit 1; }
  else
    git tag -a "v$ver" -m "release $ver" "$sha"
  fi
  rtag=$(git ls-remote "$REMOTE" "refs/tags/v$ver" "refs/tags/v$ver^{}" | tail -1 | cut -f1)
  if [ -z "$rtag" ]; then
    git push -q "$REMOTE" "refs/tags/v$ver"; echo "land-release tag: pushed v$ver"
  elif [ "$rtag" = "$sha" ]; then
    echo "land-release tag: v$ver already on $REMOTE"
  else
    echo "land-release tag: $REMOTE v$ver points at $rtag, not $sha; never moved" >&2; exit 1
  fi
  [ "$mode" = publish ] || exit 0
  notes=$(mktemp "${TMPDIR:-/tmp}/land-notes.XXXXXX"); trap 'rm -f "$notes"' EXIT
  # awk-v-ok: $ver is a validated single-line VERSION scalar
  git show "$REMOTE/$BASE_BRANCH:CHANGELOG.md" | awk -v h="## [$ver]" 'index($0,h)==1{p=1;next} p&&/^## /{p=0} p' >"$notes"
  grep -q '[^[:space:]]' "$notes" || { echo "land-release publish: no CHANGELOG section for $ver" >&2; exit 2; }
  # repo URL from the remote (ssh or https form, REPO_URL overrides); no link when it is not a web remote
  url=${REPO_URL:-$(git remote get-url "$REMOTE" | sed -E 's#^git@([^:]+):#https://\1/#; s#^ssh://git@([^/]+)/#https://\1/#; s#\.git$##')}
  case "$url" in https://*) printf '\nFull changelog: %s/blob/%s/CHANGELOG.md\n' "$url" "$BASE_BRANCH" >>"$notes" ;; esac
  if "${GH:-gh}" release view "v$ver" >/dev/null 2>&1; then
    "${GH:-gh}" release edit "v$ver" --notes-file "$notes"; echo "land-release publish: updated notes of v$ver"
  else
    "${GH:-gh}" release create "v$ver" --title "Perun v$ver" --notes-file "$notes" --verify-tag --latest
    echo "land-release publish: created release v$ver"
  fi
  exit 0
fi

LOCK="$(git rev-parse --git-common-dir)/land-release.lock"
mkdir "$LOCK" 2>/dev/null || { echo "land-release: lock held ($LOCK); another land is running" >&2; exit 1; }
trap 'rmdir "$LOCK"' EXIT

GENERATED='SHA256SUMS|scripts/size-budgets.tsv|docs/INDEX\.md|\.claude/skills/(.*/)?INDEX(-scripts)?\.md'
SKILLS="deep-code-review agentic-delivery idea-critic"

regen() {
  python3 scripts/skill_index.py >/dev/null   # first: the entry index's own size row below must see the regenerated file
  # Rewrite size rows in place (comments, order and the hand-kept README.md row survive): existing skill
  # rows and the generated entry index's row take the current size, rows of deleted files drop, new files append.
  git ls-files -co --exclude-standard .claude/skills | grep -E '(^|/)(SKILL\.md|references/[^/]*\.md)$|^\.claude/skills/((agentic-delivery|deep-code-review)/INDEX(-scripts)?|INDEX)\.md$' | LC_ALL=C sort |
    while IFS= read -r f; do printf '%s\t%s\n' "$f" "$(LC_ALL=C wc -c <"$f" | tr -d '[:space:]')"; done >sizes.new
  awk -F'\t' -v OFS='\t' 'NR==FNR{sz[$1]=$2; next}
    /^#/||/^$/{print; next}
    $1 in sz{print $1, sz[$1]; next}
    $1 !~ /^\.claude\/skills\//{print}' sizes.new scripts/size-budgets.tsv >scripts/size-budgets.new
  awk -F'\t' 'NR==FNR{have[$1]=1; next} !($1 in have)' scripts/size-budgets.new sizes.new >>scripts/size-budgets.new
  mv scripts/size-budgets.new scripts/size-budgets.tsv; rm sizes.new
  if [ -f docs/INDEX.md ]; then python3 .claude/skills/agentic-delivery/scripts/focus_kit.py docs-index --exclude bench >/dev/null; fi   # the docs map; scripts/ci-tests.d/focus-kit.sh checks it with the same flags
  bash scripts/write-checksums.sh >/dev/null   # pin LAST, after every skill-tree edit
}

if [ "$mode" = regen ]; then regen; exit 0; fi

[ -z "$(git status --porcelain)" ] || { echo "land-release: dirty tree" >&2; exit 1; }
git fetch -q "$REMOTE" "$BASE_BRANCH"
lkg=$(python3 .claude/skills/agentic-delivery/scripts/perun_policy.py get lkg_gate 2>/dev/null || echo shadow)   # shadow|enforce|off
if [ "$lkg" != off ]; then   # origin/main must be the commit the full suite last passed on (lkg.py record, scripts/run-ci-tests.sh)
  rc=0; msg=$(python3 .claude/skills/agentic-delivery/scripts/lkg.py check "$(git rev-parse "$REMOTE/$BASE_BRANCH")" 2>&1) || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "land-release: lkg gate ($lkg): ${msg:-lkg.py failed}" >&2
    if [ "$lkg" = enforce ]; then [ "$rc" -eq 1 ] && exit 1; echo "land-release: lkg.py crashed (rc=$rc); refusing under enforce" >&2; exit 2; fi
  fi
fi

if ! git merge -q --no-edit "$REMOTE/$BASE_BRANCH" >/dev/null 2>&1; then
  conflicts=$(git diff --name-only --diff-filter=U)
  bad=$(printf '%s\n' "$conflicts" | grep -vE "^($GENERATED)$" || true)
  [ -z "$bad" ] || { git merge --abort; printf 'land-release: non-generated conflicts:\n%s\n' "$bad" >&2; exit 1; }
  for f in $conflicts; do git checkout -q --theirs -- "$f"; git add "$f"; done   # regenerated below
  git commit -q --no-edit
fi

shopt -s nullglob; frags=(changelog.d/*.md); shopt -u nullglob
[ "${#frags[@]}" -gt 0 ] || { echo "land-release: no changelog.d/*.md fragment; nothing to land" >&2; exit 1; }
bash scripts/ci-gates.sh fragments --config scripts/size-budgets.tsv changelog.d >/dev/null || exit 1

IFS=. read -r maj min _ <.claude/skills/deep-code-review/VERSION
ver="$maj.$((min + 1)).0"
for s in $SKILLS; do
  d=.claude/skills/$s
  echo "$ver" >"$d/VERSION"
  sed -E "s/^(  version: \")[0-9.]+(\")/\1$ver\2/" "$d/SKILL.md" >"$d/SKILL.md.new" && mv "$d/SKILL.md.new" "$d/SKILL.md"
done
for m in .claude-plugin/plugin.json .codex-plugin/plugin.json gemini-extension.json; do   # host manifests, one version
  sed -E "s/^(  \"version\": \")[0-9.]+(\")/\1$ver\2/" "$m" >p.new && mv p.new "$m"
done

{ printf '## [%s] — %s\n\n' "$ver" "${RELEASE_DATE:-$(date +%F)}"
  for f in "${frags[@]}"; do cat "$f"; echo; done
} >release.new
awk 'NR==FNR{r=r $0 "\n"; next} !d && /^## /{printf "%s", r; d=1} {print}' release.new CHANGELOG.md >CHANGELOG.new
mv CHANGELOG.new CHANGELOG.md; rm release.new
git rm -q "${frags[@]}"
regen
git add -A CHANGELOG.md .claude-plugin .codex-plugin gemini-extension.json .claude/skills SHA256SUMS scripts/size-budgets.tsv docs/INDEX.md
git commit -q -m "release: $ver (stamped at land time)"
echo "land-release: $ver"
