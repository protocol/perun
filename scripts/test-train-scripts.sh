#!/usr/bin/env bash
# Tests for agentic-delivery/scripts/{land_train,train_land,reap_own}.sh. Plain bash; gh is a PATH stub.
# Prints PASS/FAIL lines and "N passed, M failed"; exits non-zero on any failure. Writes only under $WORK.
set -uo pipefail
export TRAIN_UNION=always  # these pin the union gate; the disjoint-path fast path is covered by test-train-disjoint.sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train.XXXXXX")"
# Every background child is bounded (sleep 60) and reaped here via jobs -p (own children only, no pkill).
trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$WORK"' EXIT
# reap_own needs lsof AND working pgrep/ps; a sandbox that denies them would leave the child unreaped.
have_ps() { command -v lsof >/dev/null && pgrep -f . >/dev/null 2>&1 && ps -p $$ >/dev/null 2>&1; }
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }

# --- fixture: origin + clone with base B and 3 member heads merged into a union as "merge-train: #N" ---
git init -q --bare "$WORK/origin.git" -b main
R="$WORK/clone"; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main
B=$(g rev-parse HEAD)
for n in 1 2 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; done
g checkout -q --detach "$B"
for n in 1 2 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done
U=$(g rev-parse HEAD)
H1=$(g rev-parse pr1); H2=$(g rev-parse pr2); H3=$(g rev-parse pr3)

# --- gh stub: state in $STUB/<field>.<n>; logs every call; mergeable of #3 is UNKNOWN on the first read ---
STUB="$WORK/stub"; mkdir -p "$STUB/bin"
cat >"$STUB/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "gh $*" >>"$STUB/calls.log"
[ -t 0 ] && echo "STDIN-IS-TTY" >>"$STUB/calls.log"
n=$3
case "$1 $2" in
  "pr view") f=${5#.}; [ "$f" = headRefName ] && { echo "br$n"; exit 0; }
              if [ "$f" = mergeable ] && [ "$n" = 3 ] && [ ! -e "$STUB/seen3" ]; then touch "$STUB/seen3"; echo UNKNOWN
             else cat "$STUB/$f.$n"; fi ;;
  "pr diff") cat "$STUB/files.$n" ;;
  "pr list") cat "$STUB/children.$4" 2>/dev/null || true ;;
  "pr edit") echo "$*" >>"$STUB/edits.log" ;;
  "pr merge") echo "merged $n $*" ;;
  "pr ready") touch "$STUB/ready.$n" ;;
esac
EOF
chmod +x "$STUB/bin/gh"
echo "$H1" >"$STUB/headRefOid.1"; echo "deadbeef" >"$STUB/headRefOid.2"; echo "$H3" >"$STUB/headRefOid.3"
for n in 1 2 3; do echo false >"$STUB/isDraft.$n"; echo MERGEABLE >"$STUB/mergeable.$n"; done
echo true >"$STUB/isDraft.3"
echo changelog.d/1.md >"$STUB/files.1"; echo src/x >"$STUB/files.2"; echo src/y >"$STUB/files.3"
echo 77 >"$STUB/children.br1"
for n in 1 2 3; do echo main >"$STUB/baseRefName.$n"; done
export STUB PATH="$STUB/bin:$PATH"

cd "$R" || exit 2
out=$(UNION_DIRS="/nonexistent $R" BACKFILL_FILE="$WORK/backfill.txt" WAIT_SECS=0 bash "$SC/land_train.sh" "$B" "$U" 2>&1) && rc=0 || rc=$?
[ $rc -eq 0 ] && grep -q "^#1(MERGEABLE): merged 1 pr merge 1 --merge --match-head-commit $H1" <<<"$out"; ok $? "land_train: lands #1 pinned to its proven head"
grep -q "^SKIP #2 moved" <<<"$out" && ! grep -q "pr merge 2" "$STUB/calls.log"; ok $? "land_train: skips a PR whose head moved, never merges it"
grep -q "^#3(MERGEABLE) last: merged 3 .*$H3" <<<"$out" && [ -e "$STUB/ready.3" ]; ok $? "land_train: waits out UNKNOWN, readies a draft, flags the last PR"
[ "$(cat "$WORK/backfill.txt")" = "3" ] && grep -q "NOTE #3 needs changelog backfill" <<<"$out" ; ok $? "land_train: missing changelog goes on the backfill list (not a skip)"
grep -q "^RETARGET #77: br1 -> main" <<<"$out" && grep -qx "pr edit 77 --base main" "$STUB/edits.log" && [ "$(wc -l <"$STUB/edits.log")" -eq 1 ]; ok $? "land_train: retargets open children of a member's branch before merging it"
grep -q "STDIN-IS-TTY" "$STUB/calls.log"; [ $? -ne 0 ]; ok $? "land_train: every gh call has stdin redirected from /dev/null"
UNION_DIRS="/nonexistent" bash "$SC/land_train.sh" "$B" "$U" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "land_train: no worktree holds the union -> exit 2"

# --- train_land: lands only a GREEN union (the one-PR train is covered by test-land-train-single.sh) ---
: >"$STUB/calls.log"
out=$(VERIFY_CMD='echo "GREEN base='"$B"' union='"$U"'"' UNION_DIRS="$R" LOG_DIR="$WORK" BACKFILL_FILE="$WORK/b2.txt" WAIT_SECS=0 \
  bash "$SC/train_land.sh" t1 1 2 3 2>&1); grep -q "^GREEN" <<<"$out" && grep -q "merged 1" <<<"$out"; ok $? "train_land: GREEN union is landed via land_train"
: >"$STUB/calls.log"
out=$(VERIFY_CMD='echo "RED union bad"; exit 1' UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t2 1 2 2>&1); rc=$?
[ $rc -eq 3 ] && grep -q "nothing landed" <<<"$out" && ! grep -q "pr merge" "$STUB/calls.log"; ok $? "train_land: RED union lands nothing (exit 3)"

# --- base check: refuse a PR targeting the wrong trunk ---
echo wrong >"$STUB/baseRefName.1"; : >"$STUB/calls.log"
out=$(UNION_DIRS="$R" BACKFILL_FILE="$WORK/b3.txt" WAIT_SECS=0 bash "$SC/land_train.sh" "$B" "$U" 2>&1)
grep -q "^REFUSE #1 base is wrong, expected main" <<<"$out" && ! grep -q "pr merge 1" "$STUB/calls.log"; ok $? "land_train: refuses a PR whose base is not the trunk"
: >"$WORK/verified"
out=$(VERIFY_CMD='echo ran >>'"$WORK"'/verified' UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t3 1 2 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q "^REFUSE #1 base is wrong" <<<"$out" && [ ! -s "$WORK/verified" ]; ok $? "train_land: wrong-base PR refuses the train before any union is built"
echo main >"$STUB/baseRefName.1"

# --- train_land: BASE RED audit + per-PR ratchet attribution ---
: >"$WORK/verified"
out=$(BASE_AUDIT_CMD='exit 1' VERIFY_CMD='echo ran >>'"$WORK"'/verified' UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t6 1 2 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "^BASE RED" <<<"$out" && [ ! -s "$WORK/verified" ]; ok $? "train_land: failing bare-base audit prints BASE RED, builds no union"
for n in 1 2 3; do g push -q origin "pr$n:refs/pull/$n/head"; done
out=$(RATCHET_CMD='[ "$PR" != 2 ]' VERIFY_CMD='echo "RED ratchet"; exit 1' UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t7 1 2 3 2>&1)
grep -q "^CULPRIT #2 " <<<"$out" && ! grep -qE "^CULPRIT #[13]" <<<"$out" && grep -q "nothing landed" <<<"$out"; ok $? "train_land: RED union names only the PR that fails the ratchet alone on the base"
out=$(VERIFY_CMD='echo "RED"; exit 1' UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t8 1 2 2>&1)
! grep -q "^CULPRIT" <<<"$out"; ok $? "train_land: no CULPRIT lines when RATCHET_CMD is unset"

# --- train_land: BROWSER_CMD gate on the GREEN union ---
G='echo "GREEN base='"$B"' union='"$U"'"'
out=$(BROWSER_CMD='exit 1' VERIFY_CMD="$G" UNION_DIRS="$R" LOG_DIR="$WORK" bash "$SC/train_land.sh" t9 1 2 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "^BROWSER RED" <<<"$out"; ok $? "train_land: failing BROWSER_CMD prints BROWSER RED and exits 1 before landing"
out=$(VERIFY_CMD="$G" UNION_DIRS="$R" LOG_DIR="$WORK" BACKFILL_FILE="$WORK/b9.txt" WAIT_SECS=0 bash "$SC/train_land.sh" t10 1 2 2>&1)
grep -q "^WARN: browser specs NOT run" <<<"$out"; ok $? "train_land: unset BROWSER_CMD warns loudly"
# --- EXIT trap: scratch (linked) worktrees are removed on every path, the current one is kept ---
W1="$WORK/wt-green"; g worktree add -q --detach "$W1" "$U"
VERIFY_CMD='echo "GREEN base='"$B"' union='"$U"'"' UNION_DIRS="$R $W1" LOG_DIR="$WORK" BACKFILL_FILE="$WORK/b4.txt" WAIT_SECS=0 bash "$SC/train_land.sh" t4 1 2 3 >/dev/null 2>&1
[ ! -e "$W1" ] && [ -d "$R/.git" ]; ok $? "train_land: GREEN path removes the scratch worktree, keeps the current one"
W2="$WORK/wt-red"; g worktree add -q --detach "$W2" "$U"
VERIFY_CMD='echo "RED union bad"; exit 1' UNION_DIRS="$R $W2" LOG_DIR="$WORK" bash "$SC/train_land.sh" t5 1 2 >/dev/null 2>&1
[ ! -e "$W2" ] && [ -d "$R/.git" ]; ok $? "train_land: RED early-return path also removes the scratch worktree"
W3="$WORK/wt-err"; g worktree add -q --detach "$W3" "$U"
UNION_DIRS="$W3" bash "$SC/land_train.sh" "$B" deadbeef >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && [ ! -e "$W3" ]; ok $? "land_train: error exit (union not found) still removes the scratch worktree"

# --- reap_own: kills only own, old, under-ROOT processes ---
if have_ps; then
  mkdir -p "$WORK/mine" "$WORK/other"
  (cd "$WORK/mine" && exec sleep 60) & P1=$!
  (cd "$WORK/other" && exec sleep 60) & P2=$!
  sleep 1
  o=$(ROOT="$WORK/mine" PATTERN='sleep 60' MAX_AGE_S=-1 bash "$SC/reap_own.sh")
  sleep 0.2
  [ "$o" = "reaped=1" ] && ! kill -0 "$P1" 2>/dev/null && kill -0 "$P2" 2>/dev/null; ok $? "reap_own: kills the process under ROOT, spares one outside it"
  kill "$P2" 2>/dev/null; wait "$P1" "$P2" 2>/dev/null
  (cd "$WORK/mine" && exec sleep 60) & P3=$!
  sleep 1
  o=$(ROOT="$WORK/mine" PATTERN='sleep 60' bash "$SC/reap_own.sh")
  [ "$o" = "reaped=0" ] && kill -0 "$P3" 2>/dev/null; ok $? "reap_own: spares a process younger than MAX_AGE_S"
  kill "$P3" 2>/dev/null; wait "$P3" 2>/dev/null
  (cd "$WORK/mine" && exec python3 -m http.server 38417 --bind 127.0.0.1) >/dev/null 2>&1 & P4=$!
  sleep 1
  o=$(ROOT="$WORK/mine" PATTERN='no-such-proc' QA_PORTS=38417 MAX_AGE_S=-1 bash "$SC/reap_own.sh")
  sleep 0.2
  [ "$o" = "reaped=1" ] && ! kill -0 "$P4" 2>/dev/null; ok $? "reap_own: QA_PORTS reaps an own listener on the port under ROOT"
  kill "$P4" 2>/dev/null; wait "$P4" 2>/dev/null
else
  echo "SKIP  reap_own (no lsof, or pgrep/ps unavailable)"
fi

# --- reap_own: SIGKILL escalation, --report ---
if have_ps; then
  (cd "$WORK/mine" && trap '' TERM && exec sleep 61) & P5=$!
  sleep 1
  o=$(ROOT="$WORK/mine" PATTERN='sleep 61' MAX_AGE_S=-1 KILL_WAIT_S=1 bash "$SC/reap_own.sh")
  [ "$o" = "reaped=1" ] && ! kill -0 "$P5" 2>/dev/null; ok $? "reap_own: SIGTERM-proof process is SIGKILLed after the wait and verified dead"
  wait "$P5" 2>/dev/null
  (cd "$WORK/mine" && exec sleep 62) & P6=$!
  sleep 1
  o=$(ROOT="$WORK/mine" PATTERN='sleep 62' bash "$SC/reap_own.sh" --report)
  grep -q "^$(cd "$WORK/mine" && pwd -P) pid=$P6 age=" <<<"$o" && grep -q "^orphans=1$" <<<"$o" && grep -q "^ram_free_mb=" <<<"$o" && kill -0 "$P6" 2>/dev/null; ok $? "reap_own --report: lists the orphan by worktree path, reports RAM, never kills"
  o=$(ROOT="$WORK/other" PATTERN='sleep 62' bash "$SC/reap_own.sh" --report)
  grep -q "^orphans=0$" <<<"$o"; ok $? "reap_own --report: ROOT with no process under it prints orphans=0"
  kill "$P6" 2>/dev/null; wait "$P6" 2>/dev/null
fi

# --- clean_finished: the gh stub says every branch is MERGED with a head that is not HEAD ---
CF="$WORK/cf"; mkdir -p "$CF/bin" "$CF/wts"
cat >"$CF/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$*" in *baseRefName*) echo main ;; *) echo "${CF_STATE:-MERGED} 0000000000000000000000000000000000000000" ;; esac
EOF
chmod +x "$CF/bin/gh"
for w in clean dirty unpushed busy; do g worktree add -q -b "cf-$w" "$CF/wts/$w" "$B"; done
echo scratch >"$CF/wts/dirty/new.txt"; echo tracked >"$CF/wts/dirty/t.txt"; git -C "$CF/wts/dirty" add t.txt
git -C "$CF/wts/unpushed" -c user.email=t@example.com -c user.name=T commit -q --allow-empty -m local-only
(cd "$CF/wts/busy" && exec sleep 63) & PB=$!
mkdir -p "$CF/scratch/x"; sleep 1
o=$(cd "$R" && GH="$CF/bin/gh" ROOT="$CF/wts" ARCHIVE_DIR="$CF/ar" SCRATCH="$CF/scratch" bash "$SC/clean_finished.sh")
[ ! -e "$CF/wts/clean" ] && [ ! -e "$CF/wts/dirty" ]; ok $? "clean_finished: removes finished worktrees (clean and dirty)"
[ -e "$CF/wts/unpushed" ]; ok $? "clean_finished: skips a worktree with unpushed commits"
[ -e "$CF/wts/busy" ]; ok $? "clean_finished: skips a worktree a process still uses"
grep -q "t.txt" "$CF/ar/dirty.patch" && grep -q "new.txt" "$CF/ar/dirty.patch"; ok $? "clean_finished: dirty worktree diff and untracked list archived before removal"
[ ! -e "$CF/scratch" ]; ok $? "clean_finished: deletes SCRATCH"
[ "$o" = "removed=2 skipped=2 archived=1" ]; ok $? "clean_finished: summary line ($o)"
kill "$PB" 2>/dev/null; wait "$PB" 2>/dev/null
o=$(cd "$R" && CF_STATE=OPEN GH="$CF/bin/gh" ROOT="$CF/wts" bash "$SC/clean_finished.sh")
[ "$o" = "removed=0 skipped=0 archived=0" ]; ok $? "clean_finished: an OPEN PR's worktree is never touched"
echo cf-unpushed >"$CF/handed"; o=$(cd "$R" && CF_STATE=OPEN HANDED_BACK="$CF/handed" GH="$CF/bin/gh" ROOT="$CF/wts" bash "$SC/clean_finished.sh")
[ -e "$CF/wts/unpushed" ] && [ "$o" = "removed=0 skipped=1 archived=0" ]; ok $? "clean_finished: a handed-back lane with unpushed commits is kept"
g worktree add -q -b cf-late "$CF/wts/late" "$B"
CLEAN_ROOT="$CF/wts" VERIFY_CMD='echo "RED"; exit 1' UNION_DIRS="$R" LOG_DIR="$WORK" GH="$CF/bin/gh" bash "$SC/train_land.sh" t11 1 2 >/dev/null 2>&1
[ ! -e "$CF/wts/late" ] && [ -e "$CF/wts/unpushed" ]; ok $? "train_land: CLEAN_ROOT cleans finished worktrees at train start, keeps unpushed ones"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
