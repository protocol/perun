#!/usr/bin/env bash
# train_land.sh <tag> <pr> <pr> [pr...] — union-verify a train from the fresh base, then land every PR of a
# GREEN union via land_train.sh. Never a single-PR train: one PR goes through the normal merge path.
#
# Stacked children of each member are retargeted to the base by land_train.sh before the merge.
#
# Refuses the whole train when any PR's base is not BASE_BRANCH. Linked worktrees in UNION_DIRS are removed on
# every exit (_clean_union.sh); the current worktree is kept.
#
# Union proof only when it can find something (path overlap only: a semantic clash between PRs touching different files is left to CI on the
# exact heads; TRAIN_UNION=always restores the proof): PRs that touch pairwise-disjoint paths and at most one generated file (GEN_RE) are
# drained back-to-back via land_train.sh (LAND_PRS), no VERIFY_CMD/BROWSER_CMD; CI on each exact head is their gate. Any overlap or gh failure
# falls through to the union below; TRAIN_UNION=always forces the union.
#
# Run it from a detached tools worktree on the base branch; it re-detaches that worktree onto the fresh base.
# Env: VERIFY_CMD (required; run via bash -c as `$VERIFY_CMD <tag> <pr...>`, must print a final line
# "GREEN base=<sha> union=<sha>" on success, e.g. a merge_train.py wrapper), UNION_DIRS (required, passed on
# to land_train.sh), BASE_BRANCH (default main), REMOTE (default origin), LOG_DIR (default .).
# Takes a per-worktree lock (<git-dir>/train-land.lock, pid-checked; a dead holder's lock is reclaimed), so two
# trains cannot share this worktree or a log. UNION_DIRS: space-separated, or newline-separated when a path has a space.
# Base-red guard: when BROWSER_CMD fails, BASELINE_FAILS is unset and RERUN_CMD is set, each failing id is re-run alone at BASE_SHA
# (train_flake.sh --base: a REAL id re-failed ≥FLAKE_REAL_AT (default FLAKE_RUNS) of FLAKE_RUNS solo re-runs, each printing `FAIL <id>` so a test absent on the base is NOT excused); those are pre-existing ("BASE RED: <n> pre-existing: ids") and never block, only new failures do.
# A FLAKE-only red lands only when every flaked id also fails >= 1 of FLAKE_RUNS solo runs on the base; one that passes N of N there is CANT (exit 3).
# FLAKE_LEDGER_DIR=<dir> (flake_ledger.py): an id on its active quarantine list that re-runs as a flake is reported `quarantined-flake`, does not block, and skips the base check.
# Flake triage (see train_flake.sh; BROWSER_CMD must print `FAIL <id>` per failure and `FAILURES <n>`): RERUN_CMD (TEST=<id>), BASELINE_FAILS (ids failing on the base); LOCK_TIMEOUT_MIN (30), PUSH_WAIT_SECS and LEASE_WAIT_SECS (both default LOCK_TIMEOUT_MIN*60).
# Stage limits: VERIFY_CMD and BROWSER_CMD each run under stage_run.py (heavy-slot lease + wall-clock timeout). TRAIN_STAGE_TIMEOUT_MIN (default 180, a union of N PRs
# outlasts a single pre-push; 0 = none) kills the stage's process group; TRAIN_SLOT_WAIT_SECS (default 1800) bounds the wait for a free heavy slot. A deferred (rc 75)
# or timed-out (rc 124) stage is infrastructure, not RED: the train ends exit 3 "stage did not complete", skips ratchet attribution and solo re-runs, and lands nothing.
# The exclusive lease is NOT held through that slot wait (it is dropped while waiting, retaken after; TRAIN_SLOT_RECHECK_SECS, default 60, is the final short wait), and a
# background heartbeat renews it every PERUN_LEASE_HEARTBEAT_SECS (600) so a stage longer than LEASE_TTL (2h) keeps it. Ratchet attribution runs under stage_run too (TRAIN_RATCHET_TIMEOUT_MIN, 30).
# Waiting, not refusing: a gate that finds the exclusive heavy lease held waits up to LEASE_WAIT_SECS, then DEFERs (exit 4, nothing built, retry later). A landing train's
# push lock is waited out BEFORE the fetch and compose, so the union is built on the base that landing leaves and a held or stale lock fails before any gate work.
# The lease is released once the push lock is held (landing is not heavy). Composing during another train's landing is deliberately not done: that union is stale at its own land.
# TRAIN_SPLIT_DEPTH (default 2): a red train whose culprit cannot be attributed (CANT: "no culprit pinned" / "real failure(s) not pinned") is split into
# halves; each half re-runs the FULL gate stacked on the fresh base and lands only when its own gate is GREEN, a red half splits again until the depth is
# spent, and a leaf keeps CANT/FLAKY exactly as before ("CANT leaf #..." in the log, nothing landed for it). 0 = never split (a non-number also means 0, with a WARN).
# Every later half redoes the push-lock and lease waits first and lands only while the base is still the one it was gated on (else it is a CANT leaf). Only a CANT
# leaf (exit 3, or BROWSER RED exit 1) continues the split; exit 2, 4 and >= 126 abort it (so 4 or 2 may follow halves that already landed: read the SPLIT done line). A split run always prints "SPLIT done: landed #<what land_train merged>;
# CANT (not landed) #<every other PR, dropped culprits included>; gates=<n>" and exits 0 only when every PR landed, else 3 (or the abort code). Flake-on-base CANT never splits.
# A split gives each half one more independent roll of the same full gate (a REAL id already re-failed every solo re-run at the union), never a retry-until-green of one verdict; each half
# still lands only on its own green gate and the depth cap bounds the extra gates.
# Self-limit (no outside stop needed): TRAIN_BUDGET_MIN (policy train_budget_min, default 90, 0 = off) is the whole train's wall clock and TRAIN_MAX_BISECT_ROUNDS (policy
# train_max_bisect_rounds, default 8, 0 = off) caps whole gate rounds (a split re-gates halves; per-PR bisect steps are not counted, only the clock bounds them); each stage timeout is clamped to the budget left. On exhaustion it prints
# "DEFER: train budget spent ...; culprit suspects #...", exits 5 (the EXIT trap frees locks and leases; 5 is not 4, which means the lease was held and nothing was built), lands nothing more. A red base ends the train at once with BASE_RED_FAILFAST=enforce (default shadow: logs only).
# Exit: 0 landed, 1 base/browser red or lock held, 4 DEFER (lease still held after LEASE_WAIT_SECS; nothing built), 5 DEFER (own budget spent; see Self-limit), 6 STALE (this script changed on disk mid-run, STALE_SELF_EXIT=enforce), 2 usage/refused (also a live tag, TRAIN_UNIQUE_RUN=enforce), 3 something not landed (see the SPLIT done line; some PRs may have landed): no GREEN union or CANT
# (CANT = a real browser failure not attributed: not re-failing alone, pre-existing on the base, or not pinned to a culprit PR; flaky-only bisects print FLAKY, never blame). Without a split, 3 means nothing landed.
# Every started train (a gate ran) is appended to the yield ledger on exit (train_yield.py; landing_watchdog.py alarms on low yield or a PR that re-rides). A train ended by BASE RED or CULPRIT is recorded as red and left out of both.
# Optional: CLEAN_ROOT (your own worktree tree: runs reap_own.sh and clean_finished.sh on it first), BASE_AUDIT_CMD (run via bash -c on the bare fresh base before verifying; non-zero prints
# "BASE RED" and exits 1, so a red base is never blamed on a PR; a PASS is cached by the base tree through gate_cache.py, shared with
# pre-commit/pre-push, so a base that already passed this command skips it: PERUN_GATE_CACHE=0 opts out), RATCHET_CMD (run via bash -c on each PR
# merged alone onto the base, with PR=<n>; when no union is GREEN, prints "CULPRIT #n" for each PR that fails it),
# BROWSER_CMD (run via bash -c in this worktree checked out at the GREEN union, with UNION_SHA and BASE_SHA set,
# before anything lands: the AFFECTED browser specs plus the smoke set, NEVER the full suite (a full run against a base that
# is already red blocks every train for nothing); non-zero prints "BROWSER RED" and lands
# nothing. Unset = loud "WARN" that the union's browser specs were NOT run; BROWSER_CMD=skip is the explicit opt-out).
set -euo pipefail
# Run from a private copy: the train's own checkouts rewrite this file (bash reads a script incrementally), and a copy is what STALE_SELF_EXIT compares the repo file against.
if [ -z "${TRAIN_LAND_COPY:-}" ]; then
  _orig=$(cd "$(dirname "$0")" && pwd)/$(basename "$0"); _cp=$(mktemp "${TMPDIR:-/tmp}/train_land.XXXXXX") && [ -n "$_cp" ] || { echo "mktemp failed" >&2; exit 2; }
  cp "$_orig" "$_cp" && TRAIN_LAND_COPY=$_cp TRAIN_LAND_ORIG=$_orig exec bash "$_cp" "$@"; rm -f "$_cp"; exit 2
fi
SELF=${TRAIN_LAND_ORIG:-$0}; trap 'rm -f "$TRAIN_LAND_COPY"' EXIT
unset PERUN_HOLDER_PID  # an inherited value must never name the lease holder; only renew() sets it, for one call
[ $# -ge 3 ] || { echo "usage: train_land.sh <tag> <pr> <pr> [pr...] (a train is >= 2 PRs)" >&2; exit 2; }
: "${VERIFY_CMD:?set VERIFY_CMD}" "${UNION_DIRS:?set UNION_DIRS}"
T=$1; shift
BASE_BRANCH=${BASE_BRANCH:-main} REMOTE=${REMOTE:-origin} LOG=${LOG_DIR:-.}/train$T.log
HERE=$(cd "$(dirname "$SELF")" && pwd) GH=${GH:-$(dirname "$SELF")/gh_rest.py}
SELF_H=$(cksum <"$SELF" 2>/dev/null) || SELF_H=  # stale-script self-exit baseline (STALE_SELF_EXIT, see stale() below)
# Unique tag (TRAIN_UNIQUE_RUN=shadow|enforce|off, default shadow): "$LOG.pid" ("<pid>") is created atomically; a live owner (kill -0 on the pid) makes enforce refuse (exit 2) and shadow warn and go on; a dead owner's marker is reaped. off skips all of it.
OWNP=
if [ "${TRAIN_UNIQUE_RUN:-shadow}" != off ]; then
  mark() { ( set -C; echo "$$" >"$LOG.pid" ) 2>/dev/null; }
  if mark; then OWNP=1; else
    read -r op <"$LOG.pid" 2>/dev/null || op=  # ponytail: pid-only identity; a recycled pid of a dead train reads as live (refuse, safe side), ceiling = pid reuse; add a random token if it bites
    if [ -n "$op" ] && kill -0 "$op" 2>/dev/null; then
      echo "REFUSE tag $T: a live train (pid $op) already owns $LOG; pick a new tag$([ "${TRAIN_UNIQUE_RUN:-shadow}" = enforce ] || echo ' (TRAIN_UNIQUE_RUN=shadow: going on, set enforce to refuse)')" >&2
      [ "${TRAIN_UNIQUE_RUN:-shadow}" != enforce ] || exit 2
    else rm -f "$LOG.pid"; ! mark || OWNP=1; fi
  fi
fi
. "$HERE/_clean_union.sh"
. "$HERE/_dirty_guard.sh"
echo "train_land: this lands to $BASE_BRANCH: if the host classifier denies the merge, park THAT merge for the owner (do not retry or route around it) and keep every other lane, review and build going." >&2
# Flake ledger (FLAKE_LEDGER_DIR, flake_ledger.py): refuse a dir the code under test can write (under this worktree or git toplevel), read the quarantine
# list ONCE NOW (before VERIFY_CMD/BROWSER_CMD/RERUN_CMD run PR code) into an unexported shell variable (never a file), and keep the path out of the
# environment of everything but train_flake.sh, which gets the list on stdin. Same-uid code can still read the path by other means: see flake_ledger.py (KNOWN CEILING).
led=${FLAKE_LEDGER_DIR:-}; unset FLAKE_LEDGER_DIR FLAKE_QUARANTINE_JSON _flq
if [ -n "$led" ]; then
  python3 "$HERE/flake_ledger.py" --dir "$led" guard >&2 || exit 2
  _flq=$(cat "$led/quarantine.json" 2>/dev/null) || _flq=
fi
require_clean_tree . || exit 2
# .perun/policy.json: PERUN_JOBS (parallelism from local_cpu) and PERUN_GITHUB_ACTIONS reach VERIFY_CMD and
# BROWSER_CMD. github_actions=off: this script never waits on or re-runs CI (it has no CI wait at all), and
# land_train.sh adds [skip ci] to every merge-commit body only; it never suppresses PR-head checks or
# tag-triggered releases. A malformed policy fails closed (exit 2).
PERUN_GITHUB_ACTIONS=$(python3 "$HERE/perun_policy.py" get github_actions) && PERUN_JOBS=$(python3 "$HERE/perun_policy.py" lanes) \
  || { echo "train_land: bad .perun/policy.json" >&2; exit 2; }
export PERUN_GITHUB_ACTIONS PERUN_JOBS
. "$HERE/_lock.sh"
rm -f "$LOG.red"
LOCK=$(git rev-parse --git-dir)/train-land.lock
LT=${LOCK_TIMEOUT_MIN:-30}
TB=${TRAIN_BUDGET_MIN:-$(python3 "$HERE/perun_policy.py" get train_budget_min)} TR=${TRAIN_MAX_BISECT_ROUNDS:-$(python3 "$HERE/perun_policy.py" get train_max_bisect_rounds)} T0=$SECONDS UN=${TRAIN_BUDGET_UNIT_SECS:-60}  # UN: seconds per budget minute (a test seam)
[[ $TB =~ ^[0-9]+$ && $TR =~ ^[0-9]+$ ]] || { echo "train_land: TRAIN_BUDGET_MIN / TRAIN_MAX_BISECT_ROUNDS must be integers >= 0" >&2; exit 2; }
lock_take "$LOCK" 0 "$LT" || exit 1
# Exclusive machine-wide heavy lease while the gate runs: heavy_gate.py denies other heavy commands ("gate running: wait").
# Held by another gate: wait for it (up to LEASE_WAIT_SECS), then DEFER with nothing built.
qn=${PERUN_QUEUE_NOTE_SECS:-120}; [[ $qn =~ ^[0-9]+$ ]] && [ "$qn" -gt 0 ] || qn=120  # queue-line gap in seconds; a bad value falls back to 120
take_lease() {  # 0 = held (or unavailable: WARN, the gate runs without it); 1 = still held by another gate after LEASE_WAIT_SECS
  local lw=${LEASE_WAIT_SECS:-$((LT * 60))} q0=$SECONDS ql=$SECONDS xrc
  while :; do
    xrc=0; PERUN_HOLDER_PID=$$ python3 "$HERE/perun_policy.py" heavy-exclusive >/dev/null 2>&1 || xrc=$?
    [ "$xrc" -eq 1 ] && [ "$lw" -gt 0 ] || break
    [ $((SECONDS - ql)) -lt "$qn" ] || { ql=$SECONDS; echo "queued $((SECONDS - q0))s: another gate holds the exclusive heavy lease; ${lw}s of wait left (LEASE_WAIT_SECS)" >&2; }
    lw=$((lw - 1)); sleep 1
  done
  [ "$xrc" -ne 1 ] || return 1
  [ "$xrc" -eq 0 ] || echo "WARN: exclusive heavy lease unavailable (rc=$xrc); gate runs without it" >&2
  return 0
}
take_lease || { echo "DEFER: another gate holds the exclusive heavy lease; nothing built, retry later" >&2; lock_drop "$LOCK"; exit 4; }
# Heartbeat: a stage may run up to TRAIN_STAGE_TIMEOUT_MIN (default 180) but the exclusive lease expires after LEASE_TTL (2h) without a
# renew, so renew it in the background for the life of the gate. Releasing it (slot wait) makes the renew a no-op; the EXIT trap stops it.
( while sleep "${PERUN_LEASE_HEARTBEAT_SECS:-600}"; do PERUN_HOLDER_PID=$$ python3 "$HERE/perun_policy.py" heavy-exclusive-renew >/dev/null 2>&1 || true; done ) >/dev/null 2>&1 </dev/null &
HB=$!
PQ=$(git rev-parse --git-common-dir)/train-push.lock PW=${PUSH_WAIT_SECS:-$((LT * 60))}
# Split bookkeeping, read by the EXIT trap: ALL = the PRs given, landed = what land_train merged, gates = verify passes run.
split=0 landed= gates=0 ALL="$*"
unl() { local n; for n in $ALL; do [[ " $landed " == *" $n "* ]] || printf '%s ' "$n"; done; }  # every PR land_train did not merge
split_report() { [ "$split" -eq 1 ] || return 0; local u; u=$(unl); echo "SPLIT done: landed #${landed# }; CANT (not landed) #${u% }; gates=$gates"; }
trap 'kill "$HB" 2>/dev/null; rm -f "$TRAIN_LAND_COPY"; [ -z "$OWNP" ] || rm -f "$LOG.pid"; [ "$gates" -eq 0 ] || python3 "$HERE/train_yield.py" record "$T" "$ALL" "$landed" "$([ -e "$LOG.red" ] && echo red)" || true; rm -f "$LOG.red"; split_report; clean_union_dirs; lock_drop "$PQ" || true; python3 "$HERE/perun_policy.py" heavy-exclusive-release >/dev/null 2>&1 || true; lock_drop "$LOCK" || true' EXIT  # a loud foreign-claim drop must not abort the rest of the cleanup
# A landing train holds the push lock and is moving the base: wait it out before any gate work (a union composed mid-land is stale at its own land).
lock_take "$PQ" "$PW" "$LT" || exit 1; lock_drop "$PQ"
if [ -n "${CLEAN_ROOT:-}" ]; then  # start-of-train cleanup of your own finished work; never blocks the train
  ROOT=$CLEAN_ROOT bash "$HERE/reap_own.sh" || true; ROOT=$CLEAN_ROOT bash "$HERE/clean_finished.sh" || true
fi
for n in "$@"; do
  bb=$("$GH" pr view "$n" --json baseRefName -q .baseRefName </dev/null) \
    || { echo "could not check: base of #$n (gh pr view failed, cause printed above); nothing built" >&2; exit 1; }
  [ "$bb" = "$BASE_BRANCH" ] || { echo "REFUSE #$n base is $bb, expected $BASE_BRANCH; nothing built" >&2; exit 2; }
done

git fetch -q "$REMOTE" "$BASE_BRANCH"
git checkout -q --detach "$REMOTE/$BASE_BRANCH"
# One generated-file list: scripts/land-release.sh's GENERATED (the derived files whose conflicts it auto-resolves). Absent = unknown = union.
GEN_RE=${GEN_RE:-$(sed -n "s/^GENERATED='\(.*\)'\$/\1/p" scripts/land-release.sh 2>/dev/null || true)}
disjoint() { local n f all= gen=0  # 0 = no shared path and <= 1 PR touches a generated file
  [ -n "$GEN_RE" ] || return 1
  for n; do f=$("$GH" pr diff "$n" --name-only </dev/null) || return 1
    all+=$(sort -u <<<"$f")$'\n'; ! grep -qE "^($GEN_RE)$" <<<"$f" || gen=$((gen + 1)); done
  [ "$gen" -le 1 ] && [ -z "$(sort <<<"$all" | uniq -d | grep . || true)" ]; }
if [ "${TRAIN_UNION:-auto}" != always ] && disjoint "$@"; then
  PQ=$(git rev-parse --git-common-dir)/train-push.lock
  echo "train_land: #$* touch disjoint paths and share no generated file; landing back-to-back, no union proof (CI on each exact head is the gate; TRAIN_UNION=always forces one)" >&2
  lock_take "$PQ" "${PUSH_WAIT_SECS:-$((LT * 60))}" "$LT" || exit 1
  python3 "$HERE/perun_policy.py" heavy-exclusive-release >/dev/null 2>&1 || true
  lrc=0; LAND_PRS="$*" bash "$HERE/land_train.sh" "$(git rev-parse HEAD)" - || lrc=$?
  lock_drop "$PQ"; exit "$lrc"
fi
GC="$HERE/../../deep-code-review/scripts/gate_cache.py"  # shared tree-keyed PASS cache (gate_cache.py): absent = run uncached
audit=(bash -c "${BASE_AUDIT_CMD:-}"); [ ! -f "$GC" ] || audit=(python3 "$GC" run --stage train --no-pipefail --ignore 'train*.log*' -c "${BASE_AUDIT_CMD:-}")
if [ -n "${BASE_AUDIT_CMD:-}" ] && ! "${audit[@]}" >"$LOG.base" 2>&1 </dev/null; then
  : >"$LOG.red"; echo "BASE RED: audit fails on bare $REMOTE/$BASE_BRANCH (see $LOG.base); no PR to blame, nothing landed" >&2; exit 1
fi
# Fixes-only coverage (FIX_MAP=<file of "<pr><TAB><red title>" lines>, BASELINE_FAILS = the base's red titles; FIXES_COVER=shadow|enforce|off, default shadow): a train of fixes lands only if its union fixes EVERY red title on the base (independent of BASE_RED_FAILFAST). A red title with no fix PR among the given PRs is uncovered: enforce prints
# them (lane these first) and DEFERs (exit 4, nothing built); shadow only logs. Absent FIX_MAP or BASELINE_FAILS = no verdict.
if [ "${FIXES_COVER:-shadow}" != off ] && [ -n "${FIX_MAP:-}" ] && [ -r "$FIX_MAP" ] && [ -r "${BASELINE_FAILS:-/dev/null}" ]; then
  covered=$(for n in "$@"; do awk -F'\t' -v n="$n" '$1 == n { sub(/^[^\t]*\t/, ""); print }' "$FIX_MAP"; done | bash "$HERE/train_flake.sh" --norm)
  unc=$(bash "$HERE/train_flake.sh" --norm <"$BASELINE_FAILS" | grep -v "^#" | grep . | grep -vxF -e "${covered:-__none__}" || true)
  if [ -n "$unc" ]; then
    if [ "${FIXES_COVER:-shadow}" = enforce ]; then echo "DEFER: fixes do not cover every red title on $BASE_BRANCH; uncovered (lane these first): $(tr '\n' ';' <<<"$unc"); nothing built" >&2; exit 4
    else echo "SHADOW fixes-cover: would DEFER, uncovered red titles: $(tr '\n' ';' <<<"$unc"); set FIXES_COVER=enforce to act" >&2; fi
  fi
fi
PRS=("$@"); SPLIT=${TRAIN_SPLIT_DEPTH:-2}
[[ $SPLIT =~ ^[0-9]+$ ]] || { echo "WARN: TRAIN_SPLIT_DEPTH='$SPLIT' is not a number; splitting disabled" >&2; SPLIT=0; }
spent() { [ "$TB" -gt 0 ] && [ $((SECONDS - T0)) -ge $((TB * UN)) ]; }
susp() { local x o=; for x in $1; do [[ " ${keep[*]:-} " == *" $x "* ]] || o+="#$x "; done; echo "${o% }"; }  # PRs not yet cleared
defer() { git merge --abort 2>/dev/null || true; git checkout -q --detach "$REMOTE/$BASE_BRANCH" 2>/dev/null || true
  echo "DEFER: train budget spent ($1); culprit suspects: $(susp "$(unl)"); nothing more run, locks and leases released, retry later or drop a suspect" >&2; exit 5; }
stale() {  # STALE_SELF_EXIT=shadow|enforce|off (default shadow): the repo file of this script changed since start -> enforce exits 6 (the EXIT trap frees locks and leases); unreadable = log only
  [ "${STALE_SELF_EXIT:-shadow}" != off ] || return 0
  local now; now=$(cksum <"$SELF" 2>/dev/null) || now=
  [ -z "$now" ] || [ -z "$SELF_H" ] && { [ -n "${STALE_SAID:-}" ] || { STALE_SAID=1; echo "SHADOW stale-self-exit: cannot read $(basename "$SELF") to compare; no exit" >&2; }; return 0; }
  [ "$now" != "$SELF_H" ] || return 0
  if [ "${STALE_SELF_EXIT:-shadow}" = enforce ]; then git merge --abort 2>/dev/null || true; echo "STALE: $(basename "$SELF") changed on disk since this train started; locks and leases released, restart to run the new code" >&2; exit 6; fi
  [ -n "${STALE_SAID:-}" ] || { STALE_SAID=1; echo "SHADOW stale-self-exit: $(basename "$SELF") changed on disk; set STALE_SELF_EXIT=enforce to exit 6" >&2; }; }
tick() { stale; ! spent || defer "$(( (SECONDS - T0) / UN ))m of ${TB}m"; }  # wall clock only: bounds every gate, stage wait and per-PR bisect step
stg() { local m=${TRAIN_STAGE_TIMEOUT_MIN:-180} r; [ "$TB" -gt 0 ] || { echo "$m"; return; }; r=$((TB - (SECONDS - T0) / UN)); [ "$r" -ge 1 ] || r=1; { [ "$m" -eq 0 ] || [ "$r" -lt "$m" ]; } && echo "$r" || echo "$m"; }
green() { printf '%s %s\n' "$B" "$U" >"$LOG.gu"; exit 0; }  # train() success: hand B/U to the lander
# Keep the lease fresh (TTL by mtime). train() runs in a subshell, so name the script's shell as the holder (else getppid() is the subshell and renew is a no-op).
renew() { PERUN_HOLDER_PID=$$ python3 "$HERE/perun_policy.py" heavy-exclusive-renew >/dev/null 2>&1 || true; }
# train: one verify + browser pass over PRS, run in a subshell so every exit below is that pass's result (0 GREEN, 9 split
# requested, else the old exit codes). With TRAIN_SPLIT_DEPTH 0 or no split it is the old script: the first non-zero exit is final.
# slot NAME: be sure a heavy slot is free before the stage starts, WITHOUT holding the exclusive lease through a long wait (it freezes every
# other heavy command). Free now: no change. Full: drop the exclusive lease, wait up to TRAIN_SLOT_WAIT_SECS (default 1800), retake it.
# rc 0 = go; 75 = no slot freed in time (nothing ran; the caller reports "did not complete"). A lost retake DEFERs (exit 4).
slot() {
  local rc=0
  python3 "$HERE/stage_run.py" --name "$1" --probe --wait 0 >/dev/null 2>&1 </dev/null && return 0
  PERUN_HOLDER_PID=$$ python3 "$HERE/perun_policy.py" heavy-exclusive-release >/dev/null 2>&1 || true
  python3 "$HERE/stage_run.py" --name "$1" --probe --wait "${TRAIN_SLOT_WAIT_SECS:-1800}" >/dev/null 2>&1 </dev/null || rc=$?
  [ "$rc" -eq 0 ] || return "$rc"
  take_lease || { echo "DEFER: another gate holds the exclusive heavy lease; split stopped, retry the unlanded PRs later" >&2; exit 4; }
}
train() {
while :; do
renew; tick
rc=0; slot train-verify || rc=$?
[ "$rc" -ne 0 ] || "$HERE/scrub_env.sh" python3 "$HERE/stage_run.py" --name train-verify --timeout "$(stg)" --wait "${TRAIN_SLOT_RECHECK_SECS:-60}" -- bash -c "$VERIFY_CMD" _ "$T" "${PRS[@]}" >"$LOG" 2>&1 </dev/null || rc=$?
# stage_run 75 = no heavy slot freed in time, 124 = stage timeout: the verify never gave a verdict, so it is not RED (no ratchet culprit hunt).
case $rc in 75|124) tick; echo "stage did not complete (train-verify rc=$rc: $([ "$rc" = 75 ] && echo 'no heavy slot' || echo 'timed out'); last log line: $(tail -1 "$LOG" 2>/dev/null)); nothing landed" >&2; exit 3 ;; esac
# Filter by verdict prefix, never by position; `|| true` keeps pipefail from aborting on no match.
grep -E '^(DEFER|DROP|GREEN|RED|STALE|CONFLICT)' "$LOG" | tail -4 || true
L=$(grep -E '^GREEN' "$LOG" | tail -1 || true)
# A GREEN line from a verify step that exited non-zero (killed, timed out after printing) is not a pass.
[ -z "$L" ] || [ "$rc" -eq 0 ] || { echo "could not check: verify printed GREEN but exited rc=$rc; treating as no GREEN union" >&2; L=; }
if [ -z "$L" ]; then
  if [ -n "${RATCHET_CMD:-}" ]; then  # attribute: merge each PR alone onto the base, run the ratchet
    base=$(git rev-parse HEAD)
    for n in "${PRS[@]}"; do
      tick; git checkout -q --detach "$base"
      if git fetch -q "$REMOTE" "pull/$n/head" && git merge -q --no-edit FETCH_HEAD >/dev/null 2>&1; then
        rr=0; PR=$n python3 "$HERE/stage_run.py" --name train-ratchet --timeout "${TRAIN_RATCHET_TIMEOUT_MIN:-30}" --wait "${TRAIN_SLOT_RECHECK_SECS:-60}" -- bash -c "$RATCHET_CMD" >/dev/null 2>&1 </dev/null || rr=$?
        case $rr in 0) ;; 75|124) echo "could not check: ratchet for #$n did not complete (stage rc=$rr: $([ "$rr" = 75 ] && echo 'no heavy slot' || echo 'timed out')); no culprit named" >&2 ;;
          *) : >"$LOG.red"; echo "CULPRIT #$n fails the ratchet alone on the base" ;; esac
      fi
      git merge --abort 2>/dev/null || true
    done
    git checkout -q --detach "$base"
  fi
  echo "no GREEN union (verify rc=$rc; last log line: $(tail -1 "$LOG" 2>/dev/null)); nothing landed"; exit 3
fi
B=$(sed -E 's/.*base=([0-9a-f]+).*/\1/' <<<"$L"); U=$(sed -E 's/.*union=([0-9a-f]+).*/\1/' <<<"$L")
if [ -z "${BROWSER_CMD:-}" ] || [ "$BROWSER_CMD" = skip ]; then
  echo "WARN: browser specs NOT run on union $U (BROWSER_CMD unset or skip); UI breakage can land unproven" >&2
  green
fi
renew; git checkout -q --detach "$U"
rc=0; slot train-browser || rc=$?
[ "$rc" -ne 0 ] || UNION_SHA=$U BASE_SHA=$B python3 "$HERE/stage_run.py" --name train-browser --timeout "$(stg)" --wait "${TRAIN_SLOT_RECHECK_SECS:-60}" -- bash -c "$BROWSER_CMD" >"$LOG.browser" 2>&1 </dev/null || rc=$?
if [ $rc -eq 0 ]; then git checkout -q --detach "$REMOTE/$BASE_BRANCH"; green; fi
case $rc in 75|124) tick; git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "stage did not complete (train-browser rc=$rc: $([ "$rc" = 75 ] && echo 'no heavy slot' || echo 'timed out')); not a browser RED; nothing landed" >&2; exit 3 ;; esac
# Red browser gate. With RERUN_CMD, "FAIL <id>" lines (minus BASELINE_FAILS) are re-run alone; flakes never block, only
# REAL failures do, and only the PR(s) that fail them alone on the base are dropped. Without RERUN_CMD it stays all-or-nothing.
BR="BROWSER RED: union $U fails browser specs (see $LOG.browser); nothing landed"
[ -n "${RERUN_CMD:-}" ] || { : >"$LOG.leaf"; git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "$BR" >&2
  [ -n "${BASELINE_FAILS:-}" ] || echo "hint: set RERUN_CMD (TEST=<id>) so failures already red on the base are detected and ignored; keep BROWSER_CMD to affected specs + smoke, not the full suite" >&2; exit 1; }
norm() { bash "$HERE/train_flake.sh" --norm; }  # the one id normalizer: emit and match share it
sed -nE 's/^FAIL +//p' "$LOG.browser" | norm >"$LOG.fails"
if [ -r "${BASELINE_FAILS:-/dev/null}" ]; then norm <"${BASELINE_FAILS:-/dev/null}" >"$LOG.baseline"; else : >"$LOG.baseline"; fi
pre=0
# Base-red fail-fast (BASE_RED_FAILFAST=shadow|enforce|off, default shadow): every failing id is already in the base's measured red set
# (BASELINE_FAILS, read now, after the lease wait, so a waiter judges the base it will land on). enforce ends the train as BASE RED at once
# (exit 1, no solo re-runs, no bisect; the EXIT trap frees the heavy lease); shadow (the default) only logs the decision and runs on as before.
# Fail closed: the red set must be stamped with the sha it was measured on ("$BASELINE_FAILS.base" holds that sha) and the stamp must equal
# this gate's base $B, which must still be the tip of $REMOTE/$BASE_BRANCH now; a missing, stale or moved-base stamp gives no base-red verdict.
ffs=$(head -1 "${BASELINE_FAILS:-/dev/null}.base" 2>/dev/null || true); fftip=$(git rev-parse "$REMOTE/$BASE_BRANCH" 2>/dev/null || true)
if [ "${BASE_RED_FAILFAST:-shadow}" != off ] && grep -q . "$LOG.fails" && [ -z "$(grep -vxFf "$LOG.baseline" "$LOG.fails" || true)" ]; then
  ffn=$(grep -c . "$LOG.fails" || true)
  if [ -z "$ffs" ] || [ "$ffs" != "$B" ] || [ "$fftip" != "$B" ]; then
    echo "base-red-failfast refused: red set stamp '${ffs:-none}' vs gate base ${B:0:7} vs $REMOTE/$BASE_BRANCH tip '${fftip:0:7}'; no base-red verdict, running on" >&2
  elif [ "${BASE_RED_FAILFAST:-shadow}" = enforce ]; then
    git checkout -q --detach "$REMOTE/$BASE_BRANCH"
    : >"$LOG.red"; echo "BASE RED: all $ffn failing ids are in the measured red set of base ${B:0:7}; no bisect, nothing landed" >&2; exit 1
  else
    echo "SHADOW base-red-failfast: would end BASE RED now ($ffn failing ids all in the measured red set of base ${B:0:7}); set BASE_RED_FAILFAST=enforce to act" >&2
  fi
fi
if :; then  # base-red guard: an id (not already in BASELINE_FAILS) that also fails every one of FLAKE_RUNS solo re-runs on the base (train_flake.sh --base) is pre-existing
  renew; git checkout -q --detach "$B"; : >"$LOG.pre"
  while IFS= read -r id; do
    [ -n "$id" ] || continue; br=0
    [ -z "${BASELINE_FAILS:-}" ] || ! grep -qxF -- "$id" "$LOG.baseline" || continue  # listed ids are handled by the baseline
    RERUN_CMD=$RERUN_CMD bash "$HERE/train_flake.sh" --base "$id" || br=$?
    [ "$br" -ne 125 ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "fresh store or FLAKE_SETUP_CMD failed re-running $id on the base; nothing landed" >&2; exit 1; }
    [ "$br" -ne 0 ] || echo "$id" >>"$LOG.pre"
  done <"$LOG.fails"
  git checkout -q --detach "$U"; pre=$(grep -c . "$LOG.pre" || true)
  if [ "$pre" -gt 0 ]; then
    echo "BASE RED: $pre pre-existing: $(paste -sd' ' "$LOG.pre")"
    grep -vxFf "$LOG.pre" "$LOG.fails" >"$LOG.new" || true; mv "$LOG.new" "$LOG.fails"
  fi
fi
renew; t=0; printf '%s' "${_flq:-}" | FLAKE_LEDGER_DIR=$led FLAKE_QUARANTINE_STDIN=1 RERUN_CMD=$RERUN_CMD FLAKE_INVOCATION=${FLAKE_INVOCATION:-$BROWSER_CMD} bash "$HERE/train_flake.sh" "$LOG.fails" "$LOG.baseline" >"$LOG.flake" || t=$?
git checkout -q --detach "$REMOTE/$BASE_BRANCH"  # isolated re-runs above ran at the union; bisect below starts from the base
cat "$LOG.flake"
# Landable only when at least one NEW failure was listed and every new one re-ran and classified FLAKE: a red run with no
# attributable new failure (empty list, baseline-only, crash before any FAIL line) never lands.
newn=$(grep -vxFf "$LOG.baseline" "$LOG.fails" 2>/dev/null | grep -c . || true)
flk=$(grep -c '^FLAKE ' "$LOG.flake" || true)
# quarantined-flake (FLAKE_LEDGER_DIR, see train_flake.sh): an actively quarantined id that re-ran alone as a flake; it counts toward newn like a
# FLAKE but is exempt from the base check below. Expired entries and consistent failures never get this label (they stay FLAKE or REAL).
qf=$(grep -c '^quarantined-flake ' "$LOG.flake" || true)
[ "$qf" -eq 0 ] || echo "quarantined-flake: $qf non-blocking: $(sed -nE 's/^quarantined-flake (.*) \(failed [0-9]+ of [0-9]+ alone\)$/\1/p' "$LOG.flake" | paste -sd' ' -)" >&2
# The runner must also print "FAILURES <n>" (its own count): missing, or more than the listed FAIL lines = an unlisted crash.
listed=$(( $(grep -c . "$LOG.fails" || true) + pre )); rn=$(sed -nE 's/^FAILURES +([0-9]+) *$/\1/p' "$LOG.browser" | tail -1)
if [ "$t" -eq 0 ] && [ -n "$rn" ] && [ "$rn" -le "$listed" ]; then
  if [ "$newn" -ge 1 ] && [ "$((flk + qf))" -eq "$newn" ]; then
    # A FLAKE lands only if the test is also flaky on the base (fails >= 1 of FLAKE_RUNS there): an intermittent regression
    # also passes a solo re-run now and then, and would otherwise land. Passing N of N on the base = CANT: park, no blame, no land.
    renew; git checkout -q --detach "$B"
    while IFS= read -r id; do
      br=0; FLAKE_REAL_AT=1 RERUN_CMD=$RERUN_CMD bash "$HERE/train_flake.sh" --base "$id" || br=$?
      [ "$br" -ne 125 ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "fresh store or FLAKE_SETUP_CMD failed re-running $id on the base; nothing landed" >&2; exit 1; }
      [ "$br" -eq 0 ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "CANT: flake $id never fails on the base, so it may be an intermittent regression; no PR blamed, nothing landed" >&2; exit 3; }
    done < <(sed -nE 's/^FLAKE (.*) \(failed [0-9]+ of [0-9]+ alone\)$/\1/p' "$LOG.flake")
    [ "$qf" -eq 0 ] || echo "$qf quarantined (base not checked)" >&2
    [ "$flk" -eq 0 ] || echo "browser failures were flakes only, each also flaky on the base; landing" >&2
    [ "$flk" -gt 0 ] || echo "browser failures were quarantined flakes only; landing" >&2; green
  fi
  if [ "$newn" -eq 0 ] && [ "$pre" -ge 1 ]; then echo "browser failures all pre-existing on the base; landing" >&2; green; fi
fi
[ "$t" -eq 1 ] || { : >"$LOG.leaf"; echo "$BR" >&2; exit 1; }  # $LOG.leaf: this exit 1 is a red leaf (the split may go on), not an infra failure
# Bisect (CANT rule): a failure lands nothing unless it is attributed, i.e. it re-fails in isolation (train_flake.sh,
# FLAKE_RUNS/FLAKE_REAL_AT) AND is not pre-existing on the base (the guard above) AND is pinned to a PR that fails it alone. Flaky-only -> "FLAKY", no blame.
cant() { git merge --abort 2>/dev/null || true; git checkout -q --detach "$base"; echo "CANT: $1; nothing landed" >&2; exit 3; }
# Unattributed red (no culprit pinned): when TRAIN_SPLIT_DEPTH allows and >= 2 PRs remain, ask the caller to re-gate halves (exit 9); else CANT.
split_or_cant() { [ "$SPLITD" -gt 0 ] && [ "${#keep[@]}" -ge 2 ] || cant "$1"
  printf '%s\n' "${keep[*]}" >"$LOG.split"; echo "SPLIT: $1; re-gating halves of #${keep[*]}" >&2; git checkout -q --detach "$base"; exit 9; }
tri() { local rc=0; RERUN_CMD=$RERUN_CMD FLAKE_INVOCATION=${FLAKE_INVOCATION:-$BROWSER_CMD} bash "$HERE/train_flake.sh" "$1" >"$2.t" || rc=$?; [ "$rc" -ne 2 ] || cant "re-run setup failed in the bisect"; sed -n 's/^REAL //p' "$2.t" >"$2"; }
keep=() ; base=$(git rev-parse HEAD); sed -n 's/^REAL //p' "$LOG.flake" >"$LOG.real"; : >"$LOG.pinned"
renew
for n in "${PRS[@]}"; do
  renew; tick  # per-PR bisect: merge alone onto the base, re-run each REAL id with the same triage
  git checkout -q --detach "$base"
  git fetch -q "$REMOTE" "pull/$n/head" && git merge -q --no-edit FETCH_HEAD >/dev/null 2>&1 || cant "#$n does not merge alone onto the base, so it cannot be attributed"
  tri "$LOG.real" "$LOG.alone"; git merge --abort 2>/dev/null || true
  if [ -s "$LOG.alone" ]; then cat "$LOG.alone" >>"$LOG.pinned"; echo "DROP #$n fails the real browser failures alone on the base"
  else keep+=("$n"); echo "FLAKY #$n: no real failure alone on the base; not blamed"; fi
done
git checkout -q --detach "$base"
[ "${#keep[@]}" -lt "${#PRS[@]}" ] || split_or_cant "no culprit pinned for the real failures"
grep -vxFf "$LOG.pinned" "$LOG.real" | grep -q . && split_or_cant "real failure(s) not pinned to any PR: $(grep -vxFf "$LOG.pinned" "$LOG.real" | tr '\n' ' ')"
[ "${#keep[@]}" -ge 2 ] || cant "<2 PRs left after dropping culprits"
PRS=("${keep[@]}")
done
}
# Split queue: items "<depth left>:<pr list>", newline-separated. A half lands only when its own full gate (train) is GREEN, stacked on the
# fresh base; a red unattributed half splits again until depth runs out; a leaf keeps the CANT/FLAKY semantics (nothing landed for it).
Q="$SPLIT:${PRS[*]}"
while [ -n "$Q" ]; do
  stale
  it=${Q%%$'\n'*}; Q=${Q#"$it"}; Q=${Q#$'\n'}; SPLITD=${it%%:*}; read -ra PRS <<<"${it#*:}"
  if [ "$gates" -gt 0 ]; then  # a later half: the same waits as the first gate (push lock, then lease), then the base it left
    lock_take "$PQ" "$PW" "$LT" || exit 1; lock_drop "$PQ"
    take_lease || { echo "DEFER: another gate holds the exclusive heavy lease; split stopped, retry the unlanded PRs later" >&2; exit 4; }
    git fetch -q "$REMOTE" "$BASE_BRANCH"; git checkout -q --detach "$REMOTE/$BASE_BRANCH"
  fi
  [ "$TR" -eq 0 ] || [ "$gates" -lt "$TR" ] || defer "$gates gates of $TR"  # the round cap counts gates (first gate + split halves), not per-PR bisect steps
  gates=$((gates + 1)); rm -f "$LOG.leaf"
  rc=0; set +e; ( set -e; train ); rc=$?; set -e
  if [ "$rc" -eq 9 ]; then
    read -ra all <"$LOG.split"; h=$(( ${#all[@]} / 2 )); split=1
    Q="$((SPLITD - 1)):${all[*]:0:h}"$'\n'"$((SPLITD - 1)):${all[*]:h}"${Q:+$'\n'$Q}; continue
  fi
  if [ "$rc" -ne 0 ]; then  # only a CANT leaf (3, or BROWSER RED 1) lets the split go on; 2, 4, >= 126 and other 1s are infra/policy failures
    leaf=0; [ "$rc" -eq 3 ] && leaf=1; [ "$rc" -eq 1 ] && [ -e "$LOG.leaf" ] && leaf=1
    [ "$split" -eq 1 ] && [ "$leaf" -eq 1 ] || exit "$rc"
    echo "CANT leaf #${PRS[*]}: exit $rc, nothing landed for it" >&2; continue
  fi
  read -r B U <"$LOG.gu"
  # Pushes go through one serial queue across worktrees (mkdir lock under the git common dir).
  lock_take "$PQ" "$PW" "$LT" || exit 1
  if [ "$split" -eq 1 ]; then  # a half is proven only against the base it was gated on (stacking): if main moved, it is a CANT leaf
    git fetch -q "$REMOTE" "$BASE_BRANCH"
    [ "$(git rev-parse "$REMOTE/$BASE_BRANCH")" = "$(git rev-parse "$B^{commit}" 2>/dev/null)" ] \
      || { lock_drop "$PQ"; echo "CANT leaf #${PRS[*]}: $BASE_BRANCH moved past its gated base $B; nothing landed for it" >&2; continue; }
  fi
  stale  # the gate may have run for hours: never land with an outdated script
  python3 "$HERE/perun_policy.py" heavy-exclusive-release >/dev/null 2>&1 || true  # push lock held first, so the next gate's wait for it cannot miss this landing
  lrc=0; bash "$HERE/land_train.sh" "$B" "$U" >"$LOG.land" || lrc=$?  # not exec: the EXIT trap must still fire
  cat "$LOG.land"  # landed = what land_train merged (a SKIP/REFUSE exits 0 but lands nothing), not the PR list
  landed="$landed $(sed -nE '/: FAILED rc=/!s/^#([0-9]+)\(.*/\1/p' "$LOG.land" | paste -sd' ' -)"
  lock_drop "$PQ"; [ "$lrc" -eq 0 ] || exit "$lrc"
done
[ "$split" -eq 1 ] || exit 0
[ -z "$(unl)" ] || exit 3  # the trap prints the SPLIT done line
