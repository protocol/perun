#!/usr/bin/env bash
# Tests for train_land.sh self-limits: wall-clock budget and gate-round cap (both DEFER, exit 5, not the lease-held 4), base-red fail-fast (shadow by default),
# locks released on every exit. Plain bash; gh is a PATH stub; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-budget.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

cd "$WORK" && [ "$(python3 "$SC/perun_policy.py" get train_budget_min)" = 90 ] && [ "$(python3 "$SC/perun_policy.py" get train_max_bisect_rounds)" = 8 ]
ok $? "policy: defaults are a 90 minute budget and 8 rounds"

R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U=$(g rev-parse HEAD)
export B U H1=$(g rev-parse pr1) H2=$(g rev-parse pr2)
mkdir -p "$WORK/bin"; cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo "merged $3" >>"$WORK/merged.log" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
echo 'echo "GREEN base=$B union=$U"' >"$WORK/green.sh"
echo 'sleep 2; echo "no verdict"; exit 1' >"$WORK/red.sh"   # red verify, slow: spends a 1 second budget
echo 'echo "$PR" >>"$WORK/ratchet.log"; exit 1' >"$WORK/ratchet.sh"
echo 'echo "FAIL $FAILID"; echo "FAILURES 1"; exit 1' >"$WORK/browser.sh"
echo 'echo "$TEST" >>"$WORK/reruns.log"; exit 1' >"$WORK/rerun.sh"
echo base1 >"$WORK/b1"; FLAKE_INVOCATION=x bash "$SC/train_flake.sh" --record "$WORK/b1" >"$WORK/baseline"; export FLAKE_INVOCATION=x
echo "$B" >"$WORK/baseline.base"
cd "$R" || exit 2
run() { : >"$WORK/merged.log"; : >"$WORK/ratchet.log"; : >"$WORK/reruns.log"
  env FAILID=base1 "$@" UNION_DIRS="$R" LOG_DIR="$WORK" BASELINE_FAILS="$WORK/baseline" bash "$SC/train_land.sh" tt 1 2 2>&1; }
clean() { [ ! -e "$R/.git/train-land.lock" ] && [ ! -e "$R/.git/train-push.lock" ] \
  && [ -z "$(echo '{"tool_input":{"command":"pytest tests"}}' | PERUN_GATE_LOAD1=0 PERUN_GATE_CORES=8 PERUN_GATE_FREE_RAM_PCT=80 python3 "$SC/heavy_gate.py")" ]; }

out=$(run VERIFY_CMD="bash $WORK/red.sh" RATCHET_CMD="bash $WORK/ratchet.sh" TRAIN_BUDGET_MIN=1 TRAIN_BUDGET_UNIT_SECS=1); rc=$?
[ $rc -eq 5 ] && grep -q 'DEFER: train budget spent' <<<"$out" && grep -q 'culprit suspects: #1 #2' <<<"$out" && [ ! -s "$WORK/ratchet.log" ] && [ ! -s "$WORK/merged.log" ]
ok $? "budget: a spent wall clock stops the train with DEFER (exit 5), names the suspects, runs and lands nothing more"
clean; ok $? "budget: lock files and the heavy lease are released after the DEFER"

out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/rerun.sh" BASE_RED_FAILFAST=enforce); rc=$?
[ $rc -eq 1 ] && grep -q '^BASE RED: all 1 failing ids are in the measured red set' <<<"$out" && [ ! -s "$WORK/reruns.log" ] && [ ! -s "$WORK/merged.log" ] && ! grep -q 'DROP\|CANT\|SHADOW' <<<"$out"
ok $? "base-red: BASE_RED_FAILFAST=enforce fails fast (exit 1, no solo re-run, no bisect)"
clean; ok $? "base-red: locks and lease released after the fast exit"
out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/rerun.sh"); grep -q 'SHADOW base-red-failfast' <<<"$out" && ! grep -q '^BASE RED: all' <<<"$out"
ok $? "base-red: the default is shadow (logs the would-end, runs on)"

out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="true"); rc=$?
[ $rc -eq 0 ] && [ "$(wc -l <"$WORK/merged.log" | tr -d ' ')" = 2 ] && ! grep -q DEFER <<<"$out"
ok $? "control: a green train under the default budget still lands both PRs"

printf '1\tother\n' >"$WORK/fixmap"
out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="true" FIX_MAP="$WORK/fixmap" FIXES_COVER=enforce); rc=$?
[ $rc -eq 4 ] && grep -q 'DEFER: fixes do not cover.*uncovered (lane these first): base1' <<<"$out" && [ ! -s "$WORK/merged.log" ] && ! grep -q GREEN <<<"$out"
ok $? "fixes-cover: a red base title with no fix PR in the batch starts no train (DEFER, exit 4 nothing built, uncovered titles printed)"
clean; ok $? "fixes-cover: locks and lease released after the DEFER"
out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="true" FIX_MAP="$WORK/fixmap"); rc=$?
[ $rc -eq 0 ] && grep -q 'SHADOW fixes-cover: would DEFER' <<<"$out" && [ "$(wc -l <"$WORK/merged.log" | tr -d ' ')" = 2 ]
ok $? "fixes-cover: default shadow only logs the would-DEFER and the train runs on"
printf '1\tbase1\n' >"$WORK/fixmap"
out=$(run VERIFY_CMD="bash $WORK/green.sh" BROWSER_CMD="true" FIX_MAP="$WORK/fixmap" FIXES_COVER=enforce); rc=$?
ok $? "fixes-cover: full coverage of the base's red titles starts and lands the train"

# round cap counts whole gates, not per-PR bisect steps: 4 PRs, the pair 3+4 only fails together, so gate 1 bisects all 4 PRs alone (no DEFER), splits, and gate 2 is over a cap of 1
R2="$WORK/c2"; O2="$WORK/o2.git"; g2() { git -C "$R2" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$O2" -b main; git clone -q "$O2" "$R2" 2>/dev/null
g2 commit -q --allow-empty -m base; g2 push -q origin HEAD:main; B2=$(g2 rev-parse HEAD)
for n in 1 2 3 4; do g2 checkout -q -b "pr$n" "$B2"; echo "$n" >"$R2/f$n"; g2 add "f$n"; g2 commit -q -m "pr $n"; g2 push -q origin "pr$n:refs/pull/$n/head"; export "H$n=$(g2 rev-parse "pr$n")"; done
cat >"$WORK/gate4.sh" <<'V'
shift
gi() { git -c user.email=t@example.com -c user.name=T -c commit.gpgsign=false "$@"; }
gi fetch -q origin main; gi checkout -q --detach origin/main; echo "$*" >>"$WORK/gates.log"
for n in "$@"; do gi merge -q --no-ff -m "merge-train: #$n" "pr$n" >/dev/null || exit 1; done
echo "GREEN base=$(git rev-parse --short HEAD) union=$(git rev-parse --short HEAD)"
V
echo 'if [ -e f3 ] && [ -e f4 ]; then echo "FAIL t1"; echo "FAILURES 1"; exit 1; fi' >"$WORK/br4.sh"
echo '[ ! -e f3 ] || [ ! -e f4 ]' >"$WORK/rr4.sh"
cd "$R2" || exit 2; : >"$WORK/gates.log"
out=$(env VERIFY_CMD="bash $WORK/gate4.sh \"\$@\"" BROWSER_CMD="bash $WORK/br4.sh" RERUN_CMD="bash $WORK/rr4.sh" UNION_DIRS="$R2" LOG_DIR="$WORK" TRAIN_BUDGET_MIN=0 TRAIN_MAX_BISECT_ROUNDS=1 bash "$SC/train_land.sh" t4 1 2 3 4 2>&1); rc=$?
[ $rc -eq 5 ] && grep -q 'SPLIT: ' <<<"$out" && grep -q 'DEFER: train budget spent (1 gates of 1)' <<<"$out" && [ "$(wc -l <"$WORK/gates.log" | tr -d ' ')" = 1 ]
ok $? "rounds: per-PR bisect steps do not count; the second whole gate over a cap of 1 DEFERs (exit 5) after exactly one gate ran"
[ ! -e "$R2/.git/train-land.lock" ] && [ ! -e "$R2/.git/train-push.lock" ]; ok $? "rounds: locks released after the cap"
: >"$WORK/gates.log"
out=$(env VERIFY_CMD="bash $WORK/gate4.sh \"\$@\"" BROWSER_CMD="bash $WORK/br4.sh" RERUN_CMD="bash $WORK/rr4.sh" UNION_DIRS="$R2" LOG_DIR="$WORK" TRAIN_BUDGET_MIN=0 TRAIN_MAX_BISECT_ROUNDS=8 bash "$SC/train_land.sh" t4 1 2 3 4 2>&1); rc=$?
! grep -q 'DEFER: train budget' <<<"$out" && [ "$(wc -l <"$WORK/gates.log" | tr -d ' ')" -ge 2 ]; ok $? "rounds: control, a cap of 8 lets the split gate run"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
