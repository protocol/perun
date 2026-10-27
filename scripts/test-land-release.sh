#!/usr/bin/env bash
# Tests for scripts/land-release.sh: two fragment lanes landed back-to-back need no hand rebump.
# Plain bash; works on a rsync copy of this repo in a temp dir. Prints PASS/FAIL and exits non-zero on failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-land.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null RELEASE_DATE=2026-01-01
fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }

git init -q --bare -b main "$WORK/origin.git"
R="$WORK/repo"; mkdir "$R"
# docs/bench (400+ MB, ~90k files) is outside docs/INDEX.md (regen excludes it) and every gate below; copying and committing it cost ~100 s.
rsync -a --exclude=.git --exclude=.claude/worktrees --exclude=changelog.d --exclude=/docs/bench "$ROOT/" "$R/"
git -C "$R" init -q -b main; g remote add origin "$WORK/origin.git"
g add -A; g commit -q -m base; g push -q origin main; BASE=$(g rev-parse HEAD)
V0=$(cat "$R/.claude/skills/deep-code-review/VERSION")
exp1="${V0%%.*}.$(( $(echo "$V0" | cut -d. -f2) + 1)).0"
exp2="${V0%%.*}.$(( $(echo "$V0" | cut -d. -f2) + 2)).0"

lane() { # <branch> <ref-file> <slug>: edit a ref, add a fragment (with its raise marker), regen like a real lane (no bump)
  g checkout -q -b "$1" main
  f=.claude/skills/deep-code-review/references/$2; before=$(wc -c <"$R/$f" | tr -d ' ')
  printf '\nlane %s note.\n' "$1" >>"$R/$f"
  mkdir -p "$R/changelog.d"
  printf '### Added\n- lane %s change.\n- size-budget-raise: %s %s→%s test\n' "$1" "$f" "$before" "$(wc -c <"$R/$f" | tr -d ' ')" >"$R/changelog.d/$3.md"
  (cd "$R" && bash scripts/land-release.sh --regen); g add -A; g commit -q -m "lane $1"
}
lane a a11y-aria.md a
lane b a11y-color-motion.md b
land() { g checkout -q "$1"; (cd "$R" && bash scripts/land-release.sh) && g push -q origin "HEAD:main"; }

land a; ok $? "lane a lands"
land b; ok $? "lane b lands after a with no hand rebump (no conflict stop)"
g checkout -q main; g merge -q --ff-only b
[ "$(cat "$R/.claude/skills/deep-code-review/VERSION")" = "$exp2" ]; ok $? "version is $exp2 after two lands"
[ "$(sed -n 's/^## \[\(.*\)\] .*/\1/p' "$R/CHANGELOG.md" | head -2 | paste -sd' ' -)" = "$exp2 $exp1" ]; ok $? "changelog has both headings in order"
grep -q 'lane a change' "$R/CHANGELOG.md" && grep -q 'lane b change' "$R/CHANGELOG.md"; ok $? "both fragments folded"
[ -z "$(ls "$R/changelog.d" 2>/dev/null)" ]; ok $? "fragments consumed"
(cd "$R" && bash scripts/ci-gates.sh version . >/dev/null && bash scripts/ci-gates.sh size --config scripts/size-budgets.tsv . >/dev/null \
  && python3 scripts/skill_index.py --check >/dev/null && bash scripts/write-checksums.sh "$WORK/sums" >/dev/null && cmp -s "$WORK/sums" SHA256SUMS); ok $? "version, size, index, checksum gates green"
grep -q '^README.md	' "$R/scripts/size-budgets.tsv"; ok $? "hand-kept README.md size row survives regen"
(cd "$R" && bash scripts/ci-gates.sh size-ratchet --base $BASE --config scripts/size-budgets.tsv . >/dev/null); ok $? "size-ratchet green on the landed tree"
(cd "$R" && bash scripts/land-release.sh) >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "land with no fragment refuses"
exit $fail
