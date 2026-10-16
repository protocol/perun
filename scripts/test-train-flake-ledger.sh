#!/usr/bin/env bash
# End-to-end test for the train_land quarantine wiring (flake_ledger.py via FLAKE_LEDGER_DIR): a test on its ACTIVE quarantine list that
# re-runs alone as a flake is reported `quarantined-flake`, does not block, and skips the flake-on-base check; an unlisted test, an
# EXPIRED entry, a consistent failure (real), and a listed test already failing consistently on this union tree all still block.
# Every runner is a stub; gh is a PATH stub. Without the wiring, case 1 exits 3 (CANT) instead of landing.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-flake-ledger.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
mkdir -p "$WORK/tmp"; export TMPDIR="$WORK/tmp"  # the train's temp files (and PR code poking at them) stay inside this run
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U123=$(g rev-parse HEAD)
TREE=$(g rev-parse "$U123^{tree}")
export B U123 H1=$(g rev-parse pr1) H2=$(g rev-parse pr2) H3=$(g rev-parse pr3)
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
echo 'echo "GREEN base=$B union=$U123"' >"$WORK/verify.sh"
cat >"$WORK/browser.sh" <<'STUB'
echo "${FLAKE_LEDGER_DIR-unset}" >>"$WORK/leak"
env | grep -c '^FLAKE_QUARANTINE\|^_flq' >>"$WORK/leak2"
# PR-controlled code overwriting any train snapshot file in $TMPDIR with a forged quarantine list
[ -z "${FORGE_SNAP:-}" ] || for q in "${TMPDIR:-/tmp}"/flake-quar.*; do [ ! -e "$q" ] || printf '{"t1": {"since": "2026-01-01", "expires": "2999-12-31"}}\n' >"$q"; done
if [ "$UNION_SHA" = "$U123" ]; then echo "FAIL t1"; echo "FAILURES 1"; exit 1; fi; exit 0
STUB
# rerun.sh: solo re-run of t1. On the union (f1 present) it pops $WORK/useq, on the base (f1 absent) $WORK/bseq; F = fail.
cat >"$WORK/rerun.sh" <<'STUB'
echo "${FLAKE_LEDGER_DIR-unset}" >>"$WORK/leak"
env | grep -c '^FLAKE_QUARANTINE\|^_flq' >>"$WORK/leak2"
[ -z "${FORGE_SNAP:-}" ] || for q in "${TMPDIR:-/tmp}"/flake-quar.*; do [ ! -e "$q" ] || printf '{"t1": {"since": "2026-01-01", "expires": "2999-12-31"}}\n' >"$q"; done
# PR-controlled code forging a quarantine entry at a known path (FORGE_Q) while the train runs
[ -z "${FORGE_Q:-}" ] || printf '{"t1": {"since": "2026-01-01", "expires": "2999-12-31"}}\n' >"$FORGE_Q"
f=$WORK/useq; [ -e f1 ] || f=$WORK/bseq
r=$(head -c1 "$f"); tail -c +2 "$f" >"$f.n"; mv "$f.n" "$f"; [ "$r" != F ] || { echo "FAIL $TEST"; exit 1; }
STUB
cd "$R" || exit 2
# run <useq> <bseq>: ledger dir $LED is fresh per case; FLAKE_RUNS=3 (a flake = at least one passing solo run).
run() { : >"$WORK/merged.log"; printf %s "$1" >"$WORK/useq"; printf %s "$2" >"$WORK/bseq"
  FLAKE_LEDGER_DIR="$LED" VERIFY_CMD="bash $WORK/verify.sh \"\$@\"" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/rerun.sh" FLAKE_RUNS=3 bash "$SC/train_land.sh" tt 1 2 3 2>&1; }
newled() { LED="$WORK/led.$1"; mkdir -p "$LED"; }
quar() { printf '{"t1": {"since": "2026-01-01", "expires": "%s"}}\n' "$1" >"$LED/quarantine.json"; }

# (1) active quarantine + a flake on the union -> quarantined-flake, lands, base check skipped (only the 1-run base-red guard read the base sequence)
newled 1; quar 2999-12-31
out=$(run FP PPPP); rc=$?
[ $rc -eq 0 ] && grep -q '^quarantined-flake t1' <<<"$out" && ! grep -q '^FLAKE t1' <<<"$out" && grep -q '1 quarantined (base not checked)' <<<"$out" && ! grep -q 'each also flaky on the base' <<<"$out" && [ -s "$WORK/merged.log" ] && [ "$(cat "$WORK/bseq")" = PPP ]
ok $? "train_land: an actively quarantined flake is quarantined-flake, non-blocking, no base check"
# (2) control: same run, id not on the list -> plain FLAKE, never fails on the base -> CANT (exit 3), nothing landed
newled 2
out=$(run FP PPPP); rc=$?
[ $rc -eq 3 ] && grep -q '^FLAKE t1' <<<"$out" && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: an unlisted flake keeps the old rule (CANT)"
# (3) expired quarantine blocks again
newled 3; quar 2000-01-01
out=$(run FP PPPP); rc=$?
[ $rc -eq 3 ] && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: an expired quarantine blocks (CANT)"
# (4) quarantined but failing every solo re-run: REAL, never relabelled, nothing landed
newled 4; quar 2999-12-31
out=$(run FFF PPPP); rc=$?
[ $rc -ne 0 ] && grep -q '^REAL t1' <<<"$out" && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a quarantined test that fails consistently is REAL, blocks"
# (5) quarantined, but the ledger already shows it failing consistently on THIS union tree: a passing solo run does not excuse it
newled 5; quar 2999-12-31
printf 'SUITE t1\nFAIL t1\nFAIL t1\n' | python3 "$SC/flake_ledger.py" --dir "$LED" record --tree "$TREE" >/dev/null
out=$(run FP PPPP); rc=$?
[ $rc -eq 3 ] && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a quarantined test already consistently failing on this tree still blocks"
# (6) newn/flk accounting: the ledger records the quarantined run's flake verdict, so case 1's evidence is visible afterwards
newled 6; quar 2999-12-31
run FP PPPP >/dev/null
python3 "$SC/flake_ledger.py" --dir "$LED" report --n 1 | grep -q $'^FLAKY\tt1\tflake_trees=1'
ok $? "train_land: the quarantined-flake run is still recorded as a flake in the ledger"

# (7) f=0: the suite failed but every solo re-run passed -> not a quarantined-flake (that needs a solo failure); the base check applies (CANT)
newled 7; quar 2999-12-31
out=$(run PPPP PPPP); rc=$?
[ $rc -eq 3 ] && grep -q '^FLAKE t1' <<<"$out" && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a quarantined test that passes every solo re-run keeps the base check (CANT)"
# (8) forgery: PR-controlled code writes a quarantine entry into the ledger dir while the train runs; the train reads a snapshot taken before
newled 8
out=$(FORGE_Q="$LED/quarantine.json" run FP PPPP); rc=$?
[ $rc -eq 3 ] && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a quarantine entry forged during the run is ignored (snapshot)"
# (8b) PR-controlled code overwrites every $TMPDIR/flake-quar.* file AND quarantine.json mid-run: no effect (the list is held in memory, never in a file)
newled 11
out=$(FORGE_SNAP=1 FORGE_Q="$LED/quarantine.json" run FP PPPP); rc=$?
[ $rc -eq 3 ] && ! grep -q 'quarantined-flake' <<<"$out" && [ ! -s "$WORK/merged.log" ] && [ -z "$(ls "${TMPDIR:-/tmp}"/flake-quar.* 2>/dev/null)" ]
ok $? "train_land: overwriting \$TMPDIR/flake-quar.* and quarantine.json mid-run has no effect, and no snapshot file exists"
# (9) the ledger path and the quarantine list are not handed to PR-controlled code (browser gate, solo re-runs)
newled 9; quar 2999-12-31; : >"$WORK/leak"; : >"$WORK/leak2"
run FP PPPP >/dev/null
[ -s "$WORK/leak" ] && ! grep -qv '^unset$' "$WORK/leak" && [ -s "$WORK/leak2" ] && ! grep -qv '^0$' "$WORK/leak2"
ok $? "train_land: FLAKE_LEDGER_DIR and the quarantine list are not in the environment of BROWSER_CMD and RERUN_CMD"
# (10) a ledger dir inside the worktree / git toplevel (PR-writable) is refused, nothing landed
LED="$R/led.10"; mkdir -p "$LED"; quar 2999-12-31
out=$(run FP PPPP); rc=$?
[ $rc -eq 2 ] && [ ! -s "$WORK/merged.log" ] && grep -q 'FLAKE_LEDGER_DIR' <<<"$out"
ok $? "train_land: a FLAKE_LEDGER_DIR under the worktree is refused (exit 2)"
rm -r "$LED" 2>/dev/null

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
