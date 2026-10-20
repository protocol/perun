#!/usr/bin/env bash
# Tests for conflict-free lane PRs: two PRs that touch different skills merge without a conflict, because a lane
# commits no derived file (SHA256SUMS, size-budgets.tsv rows, INDEX.md), no shared ci.yml list and no CHANGELOG
# edit. Also pins that the derived files are still checked: rebuilt for an unlanded tree, byte-for-byte on a land
# commit. Plain bash; works on an rsync copy of this repo (the temp dir is left for the OS tmp cleaner).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-conflict-free.XXXXXX")"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
R="$WORK/repo"; mkdir "$R"
rsync -a --exclude=.git --exclude=.claude/worktrees --exclude=changelog.d "$ROOT/" "$R/"
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git -C "$R" init -q -b main
g add -A; g commit -q -m base
SK=.claude/skills

# lane <branch> <skill> <registration> [regen]: edit one existing reference, add one new reference, add a
# changelog fragment and a CI test registration; with `regen`, also commit the derived files (the old flow).
lane() {
  g checkout -q -b "$1" main
  ref=$(cd "$R" && ls "$SK/$2/references/"*.md | head -1)
  printf '\nlane %s note.\n' "$1" >>"$R/$ref"
  printf '# lane %s\n\nBody.\n' "$1" >"$R/$SK/$2/references/zz-lane-$1.md"
  mkdir -p "$R/changelog.d" "$R/scripts/ci-tests.d"
  printf '### Added\n- lane %s change.\n' "$1" >"$R/changelog.d/$3.md"
  printf 'bash scripts/test-lane-%s.sh\n' "$1" >"$R/scripts/ci-tests.d/$3.sh"
  [ "${4:-}" = regen ] && (cd "$R" && bash scripts/land-release.sh --regen >/dev/null)
  g add -A; g commit -q -m "lane $1"
}

# Control: the old flow, each lane committing its regenerated derived files, DOES conflict (proves this test can fail).
lane old-a deep-code-review a regen
lane old-b idea-critic b regen
g checkout -q old-a; g merge -q --no-edit old-b >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "control: lanes that commit derived files conflict"
g merge --abort 2>/dev/null; g checkout -q main

# New flow: lanes commit only their own skill files, a fragment and a CI test registration.
lane a deep-code-review a
lane b idea-critic b
g checkout -q a; g merge -q --no-edit b >/dev/null 2>&1; ok $? "two PRs on different skills merge cleanly"
changed=$(git -C "$R" diff --name-only main HEAD | grep -E '^(SHA256SUMS|scripts/size-budgets\.tsv|\.github/|\.claude/skills/(.*/)?INDEX\.md|CHANGELOG\.md)' | wc -l | tr -d ' ')
[ "$changed" -eq 0 ]; ok $? "the merged lanes touch no derived or shared file"

# Unlanded tree: the CI step rebuilds the derived files, so every gate reads them current.
(cd "$R" && bash scripts/regen-unlanded.sh main >/dev/null); ok $? "regen-unlanded rebuilds an unlanded tree"
(cd "$R" && python3 scripts/skill_index.py --check >/dev/null); ok $? "INDEX.md current after the rebuild"
(cd "$R" && bash scripts/ci-gates.sh size --config scripts/size-budgets.tsv . >/dev/null 2>&1); ok $? "both new files have a size row after the rebuild"
(cd "$R" && bash scripts/write-checksums.sh "$WORK/sums" >/dev/null && cmp -s "$WORK/sums" SHA256SUMS); ok $? "SHA256SUMS current after the rebuild"
(cd "$R" && bash scripts/regen-unlanded.sh --check main); ok $? "--check reports the tree unlanded"

# The size ratchet still bites on the rebuilt rows: a raise needs its marker, and a changelog.d fragment carries it.
ratchet() { (cd "$R" && bash scripts/ci-gates.sh size-ratchet --base main --config scripts/size-budgets.tsv . >/dev/null 2>&1); }
ratchet; [ $? -ne 0 ]; ok $? "size-ratchet refuses the rebuilt raises without a marker"
g show main:scripts/size-budgets.tsv >"$WORK/old.tsv"
awk -F'\t' 'NR==FNR{o[$1]=$2;next} ($1 in o)&&($2>o[$1]){print "- size-budget-raise: "$1" "o[$1]"→"$2" test"}' \
  "$WORK/old.tsv" "$R/scripts/size-budgets.tsv" >>"$R/changelog.d/a.md"
g add changelog.d; g commit -q -m "markers in the fragment"
ratchet; ok $? "size-ratchet passes when the fragment carries the markers"

# Land commit (VERSION moved): nothing is rebuilt, so a stale committed file stays visible to the strict check.
g checkout -q -f -b land main
printf '\nstale\n' >>"$R/$SK/idea-critic/SKILL.md"
echo 9.9.9 >"$R/$SK/deep-code-review/VERSION"; g add -A; g commit -q -m land
(cd "$R" && bash scripts/regen-unlanded.sh main >/dev/null); ok $? "regen-unlanded on a land commit succeeds"
(cd "$R" && bash scripts/write-checksums.sh "$WORK/sums" >/dev/null && cmp -s "$WORK/sums" SHA256SUMS); [ $? -ne 0 ]; ok $? "land commit: stale SHA256SUMS is not rebuilt (strict check fails)"
(cd "$R" && bash scripts/regen-unlanded.sh --check main); [ $? -ne 0 ]; ok $? "--check reports a land commit as landed"
(cd "$R" && bash scripts/regen-unlanded.sh --check no-such-ref); [ $? -ne 0 ]; ok $? "unresolvable base counts as landed (fail closed)"

# Shared lists are derived, not enumerated.
grep -qE 'for d in \.claude/skills/\*/' "$ROOT/.github/workflows/ci.yml"; ok $? "ci.yml routes every skill by glob"
grep -qF 'find .claude/skills/*/' "$ROOT/scripts/write-checksums.sh"; ok $? "write-checksums.sh pins every skill dir by glob"
(cd "$ROOT" && bash scripts/ci-gates.sh enumeration . >/dev/null 2>&1); ok $? "enumeration gate accepts the glob forms"

# Fail-open controls: a comment that names a glob must not satisfy the enumeration gate.
printf '# find .claude/skills/*/\nfind .claude/skills/deep-code-review/ -type f\n' >"$R/scripts/write-checksums.sh"
o=$(cd "$R" && bash scripts/ci-gates.sh enumeration . 2>&1); grep -q 'absent from write-checksums.sh find-list' <<<"$o"; ok $? "enumeration: a commented find-glob does not pin skills"
g checkout -q -f -- scripts/write-checksums.sh
sed -i.bak 's|^\( *\)for d in \.claude/skills/\*/; do|\1# for d in .claude/skills/*/; do|' "$R/.github/workflows/ci.yml"
o=$(cd "$R" && bash scripts/ci-gates.sh enumeration . 2>&1); grep -q 'has no ci.yml routing line' <<<"$o"; ok $? "enumeration: a commented routing loop does not route skills"
g checkout -q -f -- .github/workflows/ci.yml; rm -f "$R/.github/workflows/ci.yml.bak"
grep -qF 'bash -e "$t"' "$ROOT/.github/workflows/ci.yml"; ok $? "ci-tests.d files run under bash -e (an early failure is not masked)"
grep -qF '*.bg.sh) continue' "$ROOT/.github/workflows/ci.yml" && grep -qF '[ "$(cat "$f.rc")" = 0 ]' "$ROOT/.github/workflows/ci.yml"; ok $? "a *.bg.sh test runs in the background and its exit code still fails the Per-PR step"
grep -qF 'regen-unlanded.sh --check "${fg_base}"' "$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh"; ok $? "pre-push hook decides landed-vs-unlanded against the merge-base"

echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
