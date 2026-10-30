#!/usr/bin/env bash
# Tests for pre-push-verify.sh's privacy gate (the one CI gate the hook keeps): a planted hit is refused with its file
# named and content withheld; a clean push passes. Works on a throwaway clone of the committed repo (the host tree is never touched).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-prepush-parity.XXXXXX")"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
R="$WORK/r"
g() { git -C "$R" -c user.email=t@users.noreply.github.com -c user.name=T "$@"; }
git clone -q --no-hardlinks "$ROOT" "$R" 2>/dev/null
# the clone holds HEAD; overlay the working-tree hook + gates under test, then pin that as the push base
cp "$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh" "$R/.claude/skills/deep-code-review/templates/"
cp "$ROOT/scripts/ci-gates.sh" "$R/scripts/"
g add -A; g commit -q --allow-empty -m base; g update-ref refs/remotes/origin/main HEAD
B=$(g rev-parse HEAD)
run() { # run [sha]: hook over sha (default HEAD) as a new branch; sets rc, log in $WORK/log
  (cd "$R" && printf 'refs/heads/b %s refs/heads/b 0000000000000000000000000000000000000000\n' "${1:-$(git rev-parse HEAD)}" |
    DCR_PREPUSH_CMD=true DCR_PREPUSH_DEFAULT_BRANCH=main bash .claude/skills/deep-code-review/templates/pre-push-verify.sh origin) >"$WORK/log" 2>&1
  rc=$?
}
red() { # red <name> <grep>: commit the planted change, expect refusal naming the cause + a Fix:
  g add -A; g commit -q -m "plant $1"; run
  { [ "$rc" -ne 0 ] && grep -q "FAIL -- $2" "$WORK/log" && grep -q 'Fix:' "$WORK/log"; }; ok $? "$1 refused with named cause and fix"
  g reset -q --hard "$B"
}
F=.claude/skills/deep-code-review

run; ok $rc "clean range passes"
# privacy: CI scans the whole tree; the hook scans changed files and must name the file, never the matched text
tok="AKIA""ABCDEFGHIJKLMNOP"; echo "k = $tok" >"$R/zz-secret.txt"
red privacy 'privacy'
! grep -q "$tok" "$WORK/log"; ok $? "privacy refusal withholds the matched content"
g reset -q --hard "$B"
# a hit added then deleted inside the range is not a scan target (no grep-on-missing-path error); the hook itself
# refuses a dirty or mismatched host tree, so the host tree scanned here is always the pushed commit
echo "k = $tok" >"$R/zz-secret.txt"; g add -A; g commit -q -m "plant hit"; g rm -q zz-secret.txt; g commit -q -m "delete the hit"; run
ok $rc "privacy ignores a deleted file"
g reset -q --hard "$B"
# a dangling symlink added in the range is skipped, as CI skips symlinks (grep on it would exit 2 and block the push)
ln -s no-such-target "$R/zz-link"; g add -A; g commit -q -m "dangling link"; run
ok $rc "privacy skips a dangling symlink"
g reset -q --hard "$B"
# a range that edits .banlist.txt scans the whole tree: a pre-existing hit in an untouched file is caught
echo "k = $tok" >"$R/zz-old.txt"; g add -A; g commit -q -m "old hit"; g update-ref refs/remotes/origin/main HEAD
echo "# note" >>"$R/.banlist.txt"; g add -A; g commit -q -m "touch banlist"; run
{ [ "$rc" -ne 0 ] && grep -q 'FAIL -- privacy' "$WORK/log" && grep -q 'zz-old.txt' "$WORK/log"; }; ok $? "banlist edit in range scans the whole tree"
g update-ref refs/remotes/origin/main "$B"; g reset -q --hard "$B"
echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
