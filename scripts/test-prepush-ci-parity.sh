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

# LANDED tree (VERSION moved vs base): the committed row is ratcheted as-is. Raise the first skill row one byte past
# max(its row, its file's size): the ratchet's old value is that max.
echo 9.9.9 >"$R/$F/VERSION"
python3 - "$R" <<'PY'
import os, sys
r = sys.argv[1]; p = os.path.join(r, "scripts/size-budgets.tsv"); out = []; done = False
for ln in open(p).read().split("\n"):
    f = ln.split("\t")
    if not done and f[0].startswith(".claude/skills/") and len(f) > 1:
        f[1] = str(max(int(f[1]), os.path.getsize(os.path.join(r, f[0]))) + 1); done = True; ln = "\t".join(f)
    out.append(ln)
open(p, "w").write("\n".join(out))
PY
red size-ratchet 'size-ratchet'
# UNLANDED tree: CI runs regen-unlanded.sh before the ratchet, so a lane that only GREW a skill file (row never
# committed) is a raise CI refuses. The hook must refuse it too, quote the marker, and leave the user tree alone.
ref="$(cd "$R" && ls $F/references/*.md | head -1)"
head -c 300 /dev/zero | tr '\0' 'x' >>"$R/$ref"; echo >>"$R/$ref"
g add -A; g commit -q -m "plant unlanded growth" -m "No-Mechanism-Reason: planted test growth"; run
{ [ "$rc" -ne 0 ] && grep -q 'FAIL -- size-ratchet' "$WORK/log" && grep -q 'RATCHET FAIL' "$WORK/log"; }; ok $? "unlanded growth refused (size-ratchet after regen, as CI does)"
mk="$(sed -n 's/.*RATCHET FAIL: \([^ ]*\) raised \([0-9]*\)->\([0-9]*\) bytes.*/size-budget-raise: \1 \2→\3/p' "$WORK/log" | head -1)"
[ -z "$(g status --porcelain)" ]; ok $? "user tree untouched by the regen"
[ -z "$(g worktree list | sed 1d)" ]; ok $? "throwaway worktree removed"
g commit -q --amend -m "plant unlanded growth" -m "$mk because the planted growth is deliberate" -m "No-Mechanism-Reason: planted test growth"; run
{ [ "$rc" -eq 0 ] && [ -n "$mk" ]; }; ok $? "unlanded growth with its marker line passes"
g reset -q --hard "$B"
# bench-check: CI runs bench_check.py --changed over new docs/bench dirs; a new bench with no ledger is refused here too
mkdir -p "$R/docs/bench/zz-plant"; echo '[{"id": "a", "prompt": "planted"}]' >"$R/docs/bench/zz-plant/scenarios.json"
red bench-check 'bench_check --changed'
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
# throwaway cleanup: a git shim fails `worktree add` (SHIM=fail; the shared-clone fallback must carry the gate), fails it and
# `clone` (SHIM=failall), or lets it finish then TERMs the hook (SHIM=kill).
# TMPDIR is private so any leftover mktemp dir shows up; the worktree list must be back to the host alone.
mkdir -p "$WORK/shim" "$WORK/tmp"; export REAL_GIT; REAL_GIT="$(command -v git)"
cat >"$WORK/shim/git" <<'SH'
#!/usr/bin/env bash
if [ "$1 $2" = "worktree add" ]; then
  case "${SHIM:-}" in fail|failall) exit 1 ;; esac
  if [ "${SHIM:-}" = kill ]; then "$REAL_GIT" "$@"; kill -TERM "$PPID"; exit 0; fi
fi
[ "$1" = clone ] && [ "${SHIM:-}" = failall ] && exit 1
exec "$REAL_GIT" "$@"
SH
chmod +x "$WORK/shim/git"
shim_run() { # shim_run <mode>: hook over a planted commit with the git shim on PATH
  echo probe >"$R/shim-probe.txt"; g add -A; g commit -q -m "shim probe"
  (cd "$R" && printf 'refs/heads/b %s refs/heads/b 0000000000000000000000000000000000000000\n' "$(git rev-parse HEAD)" |
    SHIM="$1" TMPDIR="$WORK/tmp" PATH="$WORK/shim:$PATH" DCR_PREPUSH_CMD=true DCR_PREPUSH_DEFAULT_BRANCH=main bash .claude/skills/deep-code-review/templates/pre-push-verify.sh origin) >"$WORK/log" 2>&1
  rc=$?; g reset -q --hard "$B"
}
shim_run fail
{ [ "$rc" -eq 0 ] && grep -q 'using a shared clone' "$WORK/log" && ! grep -q 'cannot create a throwaway checkout' "$WORK/log"; }; ok $? "worktree-add denied (sandbox): shared-clone fallback runs the gate"
[ -z "$(ls -A "$WORK/tmp")" ]; ok $? "fallback clone leaves no mktemp dir"
shim_run failall
{ [ "$rc" -ne 0 ] && grep -q 'cannot create a throwaway checkout' "$WORK/log"; }; ok $? "worktree-add and clone both fail: refused with named cause"
[ -z "$(ls -A "$WORK/tmp")" ]; ok $? "throwaway failure leaves no mktemp dir"
shim_run kill
[ "$rc" -ne 0 ]; ok $? "TERM mid-run aborts the hook"
{ [ -z "$(ls -A "$WORK/tmp")" ] && [ -z "$(g worktree list | sed 1d)" ]; }; ok $? "TERM mid-run leaves no throwaway worktree or mktemp dir"
echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
