#!/usr/bin/env bash
# Tests for pre-push-verify.sh's fast CI-parity gates: each planted RED is refused with its named cause and exact
# fix; a clean push passes. Works on a throwaway clone of the committed repo (the host tree is never touched).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-prepush-parity.XXXXXX")"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
R="$WORK/r"
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git clone -q --no-hardlinks "$ROOT" "$R" 2>/dev/null
# the clone holds HEAD; overlay the working-tree hook + gates under test, then pin that as the push base
cp "$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh" "$R/.claude/skills/deep-code-review/templates/"
g add -A; g commit -q --allow-empty -m base; g update-ref refs/remotes/origin/main HEAD
B=$(g rev-parse HEAD)
run() { # run: hook over the current HEAD as a new branch; sets rc, log in $WORK/log
  (cd "$R" && printf 'refs/heads/b %s refs/heads/b 0000000000000000000000000000000000000000\n' "$(git rev-parse HEAD)" |
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

awk -F'\t' 'BEGIN{OFS=FS} !d&&/^\.claude\/skills\//{$2=$2+1;d=1} {print}' "$R/scripts/size-budgets.tsv" >"$WORK/t" && cp "$WORK/t" "$R/scripts/size-budgets.tsv"
red size-ratchet 'size-ratchet'
awk -F'\t' 'BEGIN{OFS=FS} $1=="phase-floor-light"{$2=1} {print}' "$R/scripts/mustload-budgets.tsv" >"$WORK/t" && cp "$WORK/t" "$R/scripts/mustload-budgets.tsv"
red mustload 'mustload'
python3 - "$R/$F/evals/evals.json" <<'PY'
import sys; p = sys.argv[1]; s = open(p).read(); open(p, "w").write(s.replace("[needs_files] Loads", "Loads", 1))
PY
red run-evals 'run-evals --selftest'
# derived files are checked on land commits only (VERSION moved vs base); an unlanded tree defers them to CI
echo "stale" >>"$R/$F/INDEX.md"; g add -A; g commit -q -m "plant unlanded stale index"; run
ok $rc "unlanded tree with a stale INDEX.md passes (rebuilt in CI)"; g reset -q --hard "$B"
echo 9.9.9 >"$R/$F/VERSION"
echo "stale" >>"$R/$F/INDEX.md"
red index 'INDEX.md stale'
echo 9.9.9 >"$R/$F/VERSION"
echo "# drift" >>"$R/.claude/skills/agentic-delivery/scripts/wired_check.py"
red sha256 'SHA256SUMS stale'
awk 'NR==5{print "## [Unreleased]\n"} {print}' "$R/CHANGELOG.md" >"$WORK/t" && cp "$WORK/t" "$R/CHANGELOG.md"
red changelog 'CHANGELOG version heading'
echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
