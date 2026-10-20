#!/usr/bin/env bash
# Tests for the Teardown and cleanup rules (operating-discipline.md item 11): (a) reap_own.sh --report lists an orphan under
# ROOT (stubbed ps/pgrep/lsof) and fails closed on an unreadable cwd, (f) scrub_env.sh drops SCRUB_PREFIXES vars,
# (b) teardown_lint.py selftest + shipped scripts clean.
# Plain bash; writes only under $WORK; starts and kills no process.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-teardown.XXXXXX")" && [ -n "$WORK" ] && [ -d "$WORK" ] || { echo "FAIL  mktemp"; exit 1; }
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

# item 11a: reap_own --report lists an orphan (ppid 1) whose cwd or command line is under ROOT. ps/pgrep/lsof are stubs, so
# it runs where a sandbox denies the real ones. The "orphan" is this test shell ($$): alive, and not reap_own's own pid.
mkdir -p "$WORK/wt" "$WORK/fake"; WT=$(cd "$WORK/wt" && pwd -P)
printf '#!/bin/sh\nexit 1\n' >"$WORK/fake/pgrep"
# lsof: per-pid form (-p) answers for the one stub process; the single bulk form lists an unrelated process plus the stub (no cwd line = unreadable)
cat >"$WORK/fake/lsof" <<'STUB'
#!/bin/sh
echo "$*" >>"$STUB_LOG"
case "$*" in
  *"-p "*"-d cwd"*) echo "n$STUB_CWD" ;;
  *"-d cwd"*) [ "$STUB_FAIL" != lsof ] || exit 1; printf 'p1\nn/\np%s\n' "$STUB_PID"; [ -z "$STUB_CWD" ] || printf "%s\n" "n$STUB_CWD" ;;
esac
STUB
cat >"$WORK/fake/ps" <<'STUB'
#!/bin/sh
echo "$*" >>"$STUB_LOG"
case "$*" in
  *"-o pid= -o ppid="*) [ "$STUB_FAIL" != ps ] || exit 1; printf "%s\n" "$STUB_PID $STUB_PPID $STUB_ARGS" ;;
  *"stat="*) echo S ;;
  *"etime="*) echo 00:05 ;;
esac
STUB
export STUB_LOG="$WORK/calls.log"
chmod +x "$WORK/fake/pgrep" "$WORK/fake/lsof" "$WORK/fake/ps"
orph() { STUB_PID=$$ STUB_PPID=$1 STUB_CWD=$2 STUB_ARGS=$3 ROOT="${R:-$WT}" PATH="${XP:-}$WORK/fake:$PATH" bash "$SC/reap_own.sh" --report 2>/dev/null; }
out=$(orph 1 "$WT/sub" "sleep 300"); grep -q '^orphans=1$' <<<"$out" && grep -q "pid=$$ " <<<"$out"; ok $? "11a reap_own --report: orphan with cwd under ROOT is listed"
out=$(orph 1 / "bash -c while :; do cd $WT; sleep 1; done"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: orphan with ROOT in its command line is listed"
out=$(orph 1 / "sleep 300"); grep -q '^orphans=0$' <<<"$out"; ok $? "11a reap_own --report: orphan with a readable cwd outside ROOT is not listed (orphans=0)"
out=$(orph 4242 "$WT" "sleep 300"); grep -q '^orphans=0$' <<<"$out"; ok $? "11a reap_own --report: a process whose parent is alive (ppid != 1) is not an orphan"
out=$(orph 1 "" "sleep 300"); rc=$?; grep -q '^orphans=COULD_NOT_CHECK$' <<<"$out" && ! grep -q '^orphans=0' <<<"$out"; ok $? "11a reap_own --report: orphan with unreadable cwd and no ROOT in its command line is COULD_NOT_CHECK, never orphans=0"
out=$(orph 1 "" "sleep 1 $WT"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: orphan with unreadable cwd but ROOT in its command line is listed"
out=$(orph 1 / "sleep 1 ${WT}2/x"); grep -q '^orphans=0$' <<<"$out"; ok $? "11a reap_own --report: ROOT in a command line needs a path boundary (wt2 is not wt)"
out=$(orph 1 "${WT}2/sub" "sleep 1"); grep -q '^orphans=0$' <<<"$out"; ok $? "11a reap_own --report: cwd /x/wt2 is not under ROOT /x/wt"
out=$(orph 1 / "bash -c cd $WT; sleep 1"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: ROOT followed by ; in a command line is listed"
for f in ps lsof; do out=$(STUB_FAIL=$f orph 1 / "sleep 1"); grep -q '^orphans=COULD_NOT_CHECK$' <<<"$out"; ok $? "11a reap_own --report: failing $f is COULD_NOT_CHECK, never orphans=0"; done
mkdir -p "$WORK/fakeawk" "$WORK/sp ace/wt" "$WORK/bs\\tx"; printf '#!/bin/sh\nexit 1\n' >"$WORK/fakeawk/awk"; chmod +x "$WORK/fakeawk/awk"
out=$(XP="$WORK/fakeawk:" orph 1 "$WT" "sleep 1"); grep -q '^orphans=COULD_NOT_CHECK$' <<<"$out" && ! grep -q '^orphans=0' <<<"$out"; ok $? "11a reap_own --report: failing awk parse is COULD_NOT_CHECK, never orphans=0"
SP=$(cd "$WORK/sp ace/wt" && pwd -P); out=$(R="$SP" orph 1 "$SP/sub dir" "sleep 1"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: ROOT and cwd containing spaces are listed"
out=$(orph 1 / "sleep 1 /z$WT/run"); grep -q '^orphans=0$' <<<"$out"; ok $? "11a reap_own --report: ROOT needs a path start (/z/x/wt is not /x/wt)"
out=$(orph 1 / "sleep 1 --dir=$WT/run"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: ROOT after = in a command line is listed"
BS=$(cd "$WORK/bs\\tx" && pwd -P); out=$(R="$BS" orph 1 / "sleep 1 $BS/run"); grep -q '^orphans=1$' <<<"$out"; ok $? "11a reap_own --report: backslash in ROOT is not expanded as an escape"
: >"$STUB_LOG"; orph 1 / "sleep 1" >/dev/null
[ "$(grep -c . "$STUB_LOG")" -le 4 ]; ok $? "11a reap_own --report: scan cost is constant calls, not one per ppid-1 process"

# item 11f: SCRUB_PREFIXES drops matching vars; default scrub still drops GIT_*
out=$(TD_MODE_X=1 TD_KEEP=1 GIT_DIR=/nope SCRUB_PREFIXES="TD_MODE_" bash "$SC/scrub_env.sh" env)
! grep -q '^TD_MODE_X=' <<<"$out" && grep -q '^TD_KEEP=1' <<<"$out" && ! grep -q '^GIT_DIR=' <<<"$out"; ok $? "11f scrub_env: SCRUB_PREFIXES drops prefixed vars, keeps others, still drops GIT_*"
out=$(TD_MODE_X=1 bash "$SC/scrub_env.sh" env); grep -q '^TD_MODE_X=1' <<<"$out"; ok $? "11f scrub_env: no prefixes set leaves other vars alone"

# item 11b: lint selftest, and every shipped script is clean
python3 "$SC/teardown_lint.py" --selftest >/dev/null; ok $? "11b teardown_lint: selftest"
python3 "$SC/teardown_lint.py" >/dev/null; ok $? "11b teardown_lint: shipped agentic-delivery scripts are clean"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
