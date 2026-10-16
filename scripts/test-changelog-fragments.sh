#!/usr/bin/env bash
# Tests for the changelog-fragment gate: `ci-gates.sh fragments`, the .githooks/pre-commit hook that runs it on
# staged blobs, and land-release.sh refusing a fragment the gate rejects. Offline; works on a throwaway git repo.
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-frag.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
gate() { bash "$ROOT/scripts/ci-gates.sh" fragments --config "$ROOT/scripts/size-budgets.tsv" "$@"; }
# a real budget row to name in markers, so the cases do not depend on one file staying in the config
P="$(cut -f1 "$ROOT/scripts/size-budgets.tsv" | grep -m1 'SKILL\.md$')"
[ -n "$P" ] || { echo "FAIL  no SKILL.md row in size-budgets.tsv"; exit 1; }

frag() { # <dir> <name> <line>...: write a fragment
  mkdir -p "$1"; local f="$1/$2.md"; shift 2; printf '%s\n' "$@" >"$f"
}
fails() { # <dir> <want-substring>: gate must fail and mention the substring on stderr
  local err; err="$(gate "$1" 2>&1 >/dev/null)"; local rc=$?
  [ "$rc" -ne 0 ] && grep -qF -- "$2" <<<"$err"
}

# --- the gate itself -------------------------------------------------------------------------------------------
D="$WORK/d1"
frag "$D" good '### Added' '- a change; the `size-budget-raise:` marker is documented in CONTRIBUTING' \
  "- size-budget-raise: $P 100→120 one sentence for the new route" \
  'size-budget-raise: review-config.md and review_feedback.py carry the learn lifecycle.'
gate "$D" >/dev/null 2>&1; ok $? "valid marker, bullet, and prose that only names the marker all pass"
gate "$WORK/none" >/dev/null 2>&1; ok $? "a missing fragment directory passes (changelog.d is gone once every fragment landed)"
mkdir "$WORK/empty"; gate "$WORK/empty" >/dev/null 2>&1; ok $? "a directory with no fragment passes"

frag "$WORK/h" head '## Release heading' '- note'
fails "$WORK/h" 'head.md has a "## " heading'; ok $? "a '## ' heading fails and names the fragment"
frag "$WORK/h3" head '### Added' '- note'; gate "$WORK/h3" >/dev/null 2>&1; ok $? "a '### ' heading passes"

# the real incident: a fragment whose marker line used '->' and two bare file names failed only at release (size-ratchet)
frag "$WORK/inc" bad '### Fixed' '- x' 'size-budget-raise: host-enforcement.md 40807->40994, operating-discipline.md 6903->7053 (one sentence each)'
fails "$WORK/inc" 'want "size-budget-raise: <path> <old>→<new> <reason>"'; ok $? "the historical marker line (ASCII arrow, two files, bare names) fails"
frag "$WORK/fix" bad '### Fixed' '- x' "size-budget-raise: $P 40807→40994 one sentence for the PR base key"
gate "$WORK/fix" >/dev/null 2>&1; ok $? "the corrected marker passes"

frag "$WORK/np" bad '- x' 'size-budget-raise: host-enforcement.md 40807→40994 bare name'
fails "$WORK/np" 'marker path host-enforcement.md is not a row'; ok $? "a marker path that is not a config row fails"
frag "$WORK/nr" bad '- x' "size-budget-raise: $P 40807→40994"
fails "$WORK/nr" 'want "size-budget-raise:'; ok $? "a marker with no reason fails"
frag "$WORK/aa" bad '- x' "size-budget-raise: $P 100->120 reason"
fails "$WORK/aa" 'want "size-budget-raise:'; ok $? "an ASCII-arrow marker fails"

frag "$WORK/many" one '## a' ; frag "$WORK/many" two "size-budget-raise: $P 1->2 r"
[ "$(gate "$WORK/many" 2>&1 >/dev/null | grep -c '^FRAGMENT FAIL')" -eq 2 ]; ok $? "every bad fragment is reported in one run, not just the first"

gate --bogus "$D" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "an unknown option fails closed"
bash "$ROOT/scripts/ci-gates.sh" fragments --config "$WORK/absent.tsv" "$D" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "a missing config fails closed"
bash "$ROOT/scripts/ci-gates.sh" fragments >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "no directory fails closed"

# --- the pre-commit hook: validates the STAGED blob ---------------------------------------------------------------
R="$WORK/repo"; mkdir -p "$R/scripts" "$R/.githooks"
cp "$ROOT/scripts/ci-gates.sh" "$ROOT/scripts/land-release.sh" "$ROOT/scripts/size-budgets.tsv" "$R/scripts/"
cp "$ROOT/.githooks/pre-commit" "$R/.githooks/pre-commit"
g() { git -C "$R" -c user.email=t@example.com -c user.name=T -c core.hooksPath=.githooks "$@"; }
git init -q -b main "$R"; echo base >"$R/README.md"; g add -A; g commit -q -m base; ok $? "hook allows a commit with no fragment"
BAD='size-budget-raise: x.md 1->2 r'; GOOD="size-budget-raise: $P 1→2 r"
mkdir "$R/changelog.d"; printf '### Added\n- %s\n' "$BAD" >"$R/changelog.d/a.md"; g add changelog.d/a.md
g commit -q -m frag 2>"$WORK/err"; [ $? -ne 0 ] && grep -q 'FRAGMENT FAIL: a.md' "$WORK/err"; ok $? "hook blocks a staged bad fragment and names it"
[ "$(g log --format=%s | head -1)" = base ]; ok $? "the blocked commit was not created"
printf '### Added\n- %s\n' "$GOOD" >"$R/changelog.d/a.md"
g commit -q -m frag 2>/dev/null; [ $? -ne 0 ]; ok $? "fixing only the working copy does not help: the staged blob is what counts"
g add changelog.d/a.md; g commit -q -m frag; ok $? "restaging the fixed fragment passes"
printf '### Added\n- %s\n' "$BAD" >"$R/changelog.d/a.md"; echo more >>"$R/README.md"; g add README.md
g commit -q -m unrelated; ok $? "an unstaged bad edit of a fragment never blocks an unrelated commit"
git -C "$R" checkout -q -- changelog.d/a.md; g rm -q changelog.d/a.md; g commit -q -m "land"; ok $? "staging a fragment deletion (what land does) passes"

# --- land refuses a bad fragment before it stamps --------------------------------------------------------------------
git init -q --bare -b main "$WORK/origin.git"; g remote add origin "$WORK/origin.git"; g push -q origin main
echo '# Changelog' >"$R/CHANGELOG.md"; g add -A; g commit -q -m changelog; g push -q origin main
mkdir -p "$R/changelog.d"; printf '### Added\n- %s\n' "$BAD" >"$R/changelog.d/b.md"; g add -A; git -C "$R" -c core.hooksPath=/dev/null -c user.email=t@example.com -c user.name=T commit -q -m "lane b"
before="$(g rev-parse HEAD)"
(cd "$R" && bash scripts/land-release.sh) >/dev/null 2>"$WORK/land.err"; [ $? -ne 0 ] && grep -q 'FRAGMENT FAIL: b.md' "$WORK/land.err"; ok $? "land-release refuses the bad fragment"
[ "$(g rev-parse HEAD)" = "$before" ] && [ -f "$R/changelog.d/b.md" ] && ! grep -q '^## \[' "$R/CHANGELOG.md"; ok $? "a refused land stamped nothing and kept the fragment"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
