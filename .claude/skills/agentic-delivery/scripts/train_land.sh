#!/usr/bin/env bash
# train_land.sh <tag> <pr> <pr> [pr...] — union-verify a train from the fresh base, then land every PR of a
# GREEN union via land_train.sh. Never a single-PR train: one PR goes through the normal merge path.
#
# Stacked children of each member are retargeted to the base by land_train.sh before the merge.
#
# Refuses the whole train when any PR's base is not BASE_BRANCH. Linked worktrees in UNION_DIRS are removed on
# every exit (_clean_union.sh); the current worktree is kept.
#
# Run it from a detached tools worktree on the base branch; it re-detaches that worktree onto the fresh base.
# Env: VERIFY_CMD (required; run via bash -c as `$VERIFY_CMD <tag> <pr...>`, must print a final line
# "GREEN base=<sha> union=<sha>" on success, e.g. a merge_train.py wrapper), UNION_DIRS (required, passed on
# to land_train.sh), BASE_BRANCH (default main), REMOTE (default origin), LOG_DIR (default .).
# Takes a per-worktree lock (<git-dir>/train-land.lock, pid-checked; a dead holder's lock is reclaimed), so two
# trains cannot share this worktree or a log. UNION_DIRS: space-separated, or newline-separated when a path has a space.
# Base-red guard: when BROWSER_CMD fails, BASELINE_FAILS is unset and RERUN_CMD is set, each failing id is re-run alone at BASE_SHA
# (train_flake.sh --base: FLAKE_REAL_AT (default FLAKE_RUNS) of FLAKE_RUNS failures, each printing `FAIL <id>` so a test absent on the base is NOT excused); those are pre-existing ("BASE RED: <n> pre-existing: ids") and never block, only new failures do.
# A FLAKE-only red lands only when every flaked id also fails >= 1 of FLAKE_RUNS solo runs on the base; one that passes N of N there is CANT (exit 3).
# Flake triage (see train_flake.sh; BROWSER_CMD must print `FAIL <id>` per failure and `FAILURES <n>`): RERUN_CMD (TEST=<id>), BASELINE_FAILS (ids failing on the base); LOCK_TIMEOUT_MIN (30), PUSH_WAIT_SECS (600).
# Exit: 0 landed, 1 base/browser red or lock held, 2 usage/refused, 3 no GREEN union or CANT (nothing landed; CANT = a real browser failure
# not attributed: not re-failing alone, pre-existing on the base, or not pinned to a culprit PR; flaky-only bisects print FLAKY, never blame).
# Optional: CLEAN_ROOT (your own worktree tree: runs reap_own.sh and clean_finished.sh on it first), BASE_AUDIT_CMD (run via bash -c on the bare fresh base before verifying; non-zero prints
# "BASE RED" and exits 1, so a red base is never blamed on a PR; a PASS is cached by the base tree through gate_cache.py, shared with
# pre-commit/pre-push, so a base that already passed this command skips it: PERUN_GATE_CACHE=0 opts out), RATCHET_CMD (run via bash -c on each PR
# merged alone onto the base, with PR=<n>; when no union is GREEN, prints "CULPRIT #n" for each PR that fails it),
# BROWSER_CMD (run via bash -c in this worktree checked out at the GREEN union, with UNION_SHA and BASE_SHA set,
# before anything lands: the AFFECTED browser specs plus the smoke set, NEVER the full suite (a full run against a base that
# is already red blocks every train for nothing); non-zero prints "BROWSER RED" and lands
# nothing. Unset = loud "WARN" that the union's browser specs were NOT run; BROWSER_CMD=skip is the explicit opt-out).
set -euo pipefail
[ $# -ge 3 ] || { echo "usage: train_land.sh <tag> <pr> <pr> [pr...] (a train is >= 2 PRs)" >&2; exit 2; }
: "${VERIFY_CMD:?set VERIFY_CMD}" "${UNION_DIRS:?set UNION_DIRS}"
T=$1; shift
BASE_BRANCH=${BASE_BRANCH:-main} REMOTE=${REMOTE:-origin} LOG=${LOG_DIR:-.}/train$T.log
HERE=$(cd "$(dirname "$0")" && pwd) GH=${GH:-$(dirname "$0")/gh_rest.py}
. "$HERE/_clean_union.sh"
. "$HERE/_dirty_guard.sh"
echo "train_land: this lands to $BASE_BRANCH: if the host classifier denies the merge, stop and park for the owner; do not retry or route around." >&2
require_clean_tree . || exit 2
# .perun/policy.json: PERUN_JOBS (parallelism from local_cpu) and PERUN_GITHUB_ACTIONS reach VERIFY_CMD and
# BROWSER_CMD. github_actions=off: this script never waits on or re-runs CI (it has no CI wait at all), and
# land_train.sh adds [skip ci] to every merge-commit body only; it never suppresses PR-head checks or
# tag-triggered releases. A malformed policy fails closed (exit 2).
PERUN_GITHUB_ACTIONS=$(python3 "$HERE/perun_policy.py" get github_actions) && PERUN_JOBS=$(python3 "$HERE/perun_policy.py" lanes) \
  || { echo "train_land: bad .perun/policy.json" >&2; exit 2; }
export PERUN_GITHUB_ACTIONS PERUN_JOBS
. "$HERE/_lock.sh"
LOCK=$(git rev-parse --git-dir)/train-land.lock
lock_take "$LOCK" 0 "${LOCK_TIMEOUT_MIN:-30}" || exit 1
# Exclusive machine-wide heavy lease while the gate runs: heavy_gate.py denies other heavy commands ("gate running: wait").
xrc=0; python3 "$HERE/perun_policy.py" heavy-exclusive >/dev/null 2>&1 || xrc=$?
[ "$xrc" -ne 1 ] || { echo "train_land: another gate holds the exclusive heavy lease" >&2; lock_drop "$LOCK"; exit 1; }
[ "$xrc" -eq 0 ] || echo "WARN: exclusive heavy lease unavailable (rc=$xrc); gate runs without it" >&2
PQ=$(git rev-parse --git-common-dir)/train-push.lock
trap 'clean_union_dirs; lock_drop "$PQ"; python3 "$HERE/perun_policy.py" heavy-exclusive-release >/dev/null 2>&1 || true; lock_drop "$LOCK"' EXIT
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
GC="$HERE/../../deep-code-review/scripts/gate_cache.py"  # shared tree-keyed PASS cache (gate_cache.py): absent = run uncached
audit=(bash -c "${BASE_AUDIT_CMD:-}"); [ ! -f "$GC" ] || audit=(python3 "$GC" run --stage train --no-pipefail --ignore 'train*.log*' -c "${BASE_AUDIT_CMD:-}")
if [ -n "${BASE_AUDIT_CMD:-}" ] && ! "${audit[@]}" >"$LOG.base" 2>&1 </dev/null; then
  echo "BASE RED: audit fails on bare $REMOTE/$BASE_BRANCH (see $LOG.base); no PR to blame, nothing landed" >&2; exit 1
fi
PRS=("$@")
renew() { python3 "$HERE/perun_policy.py" heavy-exclusive-renew >/dev/null 2>&1 || true; }  # keep the lease fresh (TTL by mtime)
while :; do
renew
rc=0; "$(dirname "$0")/scrub_env.sh" bash -c "$VERIFY_CMD" _ "$T" "${PRS[@]}" >"$LOG" 2>&1 </dev/null || rc=$?
# Filter by verdict prefix, never by position; `|| true` keeps pipefail from aborting on no match.
grep -E '^(DEFER|DROP|GREEN|RED|STALE|CONFLICT)' "$LOG" | tail -4 || true
L=$(grep -E '^GREEN' "$LOG" | tail -1 || true)
# A GREEN line from a verify step that exited non-zero (killed, timed out after printing) is not a pass.
[ -z "$L" ] || [ "$rc" -eq 0 ] || { echo "could not check: verify printed GREEN but exited rc=$rc; treating as no GREEN union" >&2; L=; }
if [ -z "$L" ]; then
  if [ -n "${RATCHET_CMD:-}" ]; then  # attribute: merge each PR alone onto the base, run the ratchet
    base=$(git rev-parse HEAD)
    for n in "${PRS[@]}"; do
      git checkout -q --detach "$base"
      if git fetch -q "$REMOTE" "pull/$n/head" && git merge -q --no-edit FETCH_HEAD >/dev/null 2>&1 \
        && ! PR=$n bash -c "$RATCHET_CMD" >/dev/null 2>&1 </dev/null; then echo "CULPRIT #$n fails the ratchet alone on the base"; fi
      git merge --abort 2>/dev/null || true
    done
    git checkout -q --detach "$base"
  fi
  echo "no GREEN union (verify rc=$rc; last log line: $(tail -1 "$LOG" 2>/dev/null)); nothing landed"; exit 3
fi
B=$(sed -E 's/.*base=([0-9a-f]+).*/\1/' <<<"$L"); U=$(sed -E 's/.*union=([0-9a-f]+).*/\1/' <<<"$L")
if [ -z "${BROWSER_CMD:-}" ] || [ "$BROWSER_CMD" = skip ]; then
  echo "WARN: browser specs NOT run on union $U (BROWSER_CMD unset or skip); UI breakage can land unproven" >&2
  break
fi
renew; git checkout -q --detach "$U"
rc=0; UNION_SHA=$U BASE_SHA=$B bash -c "$BROWSER_CMD" >"$LOG.browser" 2>&1 </dev/null || rc=$?
if [ $rc -eq 0 ]; then git checkout -q --detach "$REMOTE/$BASE_BRANCH"; break; fi
# Red browser gate. With RERUN_CMD, "FAIL <id>" lines (minus BASELINE_FAILS) are re-run alone; flakes never block, only
# REAL failures do, and only the PR(s) that fail them alone on the base are dropped. Without RERUN_CMD it stays all-or-nothing.
BR="BROWSER RED: union $U fails browser specs (see $LOG.browser); nothing landed"
[ -n "${RERUN_CMD:-}" ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "$BR" >&2
  [ -n "${BASELINE_FAILS:-}" ] || echo "hint: set RERUN_CMD (TEST=<id>) so failures already red on the base are detected and ignored; keep BROWSER_CMD to affected specs + smoke, not the full suite" >&2; exit 1; }
norm() { bash "$HERE/train_flake.sh" --norm; }  # the one id normalizer: emit and match share it
sed -nE 's/^FAIL +//p' "$LOG.browser" | norm >"$LOG.fails"
if [ -r "${BASELINE_FAILS:-/dev/null}" ]; then norm <"${BASELINE_FAILS:-/dev/null}" >"$LOG.baseline"; else : >"$LOG.baseline"; fi
pre=0
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
renew; t=0; RERUN_CMD=$RERUN_CMD FLAKE_INVOCATION=${FLAKE_INVOCATION:-$BROWSER_CMD} bash "$HERE/train_flake.sh" "$LOG.fails" "$LOG.baseline" >"$LOG.flake" || t=$?
git checkout -q --detach "$REMOTE/$BASE_BRANCH"  # isolated re-runs above ran at the union; bisect below starts from the base
cat "$LOG.flake"
# Landable only when at least one NEW failure was listed and every new one re-ran and classified FLAKE: a red run with no
# attributable new failure (empty list, baseline-only, crash before any FAIL line) never lands.
newn=$(grep -vxFf "$LOG.baseline" "$LOG.fails" 2>/dev/null | grep -c . || true)
flk=$(grep -c '^FLAKE ' "$LOG.flake" || true)
# The runner must also print "FAILURES <n>" (its own count): missing, or more than the listed FAIL lines = an unlisted crash.
listed=$(( $(grep -c . "$LOG.fails" || true) + pre )); rn=$(sed -nE 's/^FAILURES +([0-9]+) *$/\1/p' "$LOG.browser" | tail -1)
if [ "$t" -eq 0 ] && [ -n "$rn" ] && [ "$rn" -le "$listed" ]; then
  if [ "$newn" -ge 1 ] && [ "$flk" -eq "$newn" ]; then
    # A FLAKE lands only if the test is also flaky on the base (fails >= 1 of FLAKE_RUNS there): an intermittent regression
    # also passes a solo re-run now and then, and would otherwise land. Passing N of N on the base = CANT: park, no blame, no land.
    renew; git checkout -q --detach "$B"
    while IFS= read -r id; do
      br=0; FLAKE_REAL_AT=1 RERUN_CMD=$RERUN_CMD bash "$HERE/train_flake.sh" --base "$id" || br=$?
      [ "$br" -ne 125 ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "fresh store or FLAKE_SETUP_CMD failed re-running $id on the base; nothing landed" >&2; exit 1; }
      [ "$br" -eq 0 ] || { git checkout -q --detach "$REMOTE/$BASE_BRANCH"; echo "CANT: flake $id never fails on the base, so it may be an intermittent regression; no PR blamed, nothing landed" >&2; exit 3; }
    done < <(sed -nE 's/^FLAKE (.*) \(failed [0-9]+ of [0-9]+ alone\)$/\1/p' "$LOG.flake")
    echo "browser failures were flakes only, each also flaky on the base; landing" >&2; break
  fi
  if [ "$newn" -eq 0 ] && [ "$pre" -ge 1 ]; then echo "browser failures all pre-existing on the base; landing" >&2; break; fi
fi
[ "$t" -eq 1 ] || { echo "$BR" >&2; exit 1; }
# Bisect (CANT rule): a failure lands nothing unless it is attributed, i.e. it re-fails in isolation (train_flake.sh,
# FLAKE_RUNS/FLAKE_REAL_AT) AND is not pre-existing on the base (the guard above) AND is pinned to a PR that fails it alone. Flaky-only -> "FLAKY", no blame.
cant() { git merge --abort 2>/dev/null || true; git checkout -q --detach "$base"; echo "CANT: $1; nothing landed" >&2; exit 3; }
tri() { local rc=0; RERUN_CMD=$RERUN_CMD FLAKE_INVOCATION=${FLAKE_INVOCATION:-$BROWSER_CMD} bash "$HERE/train_flake.sh" "$1" >"$2.t" || rc=$?; [ "$rc" -ne 2 ] || cant "re-run setup failed in the bisect"; sed -n 's/^REAL //p' "$2.t" >"$2"; }
keep=() ; base=$(git rev-parse HEAD); sed -n 's/^REAL //p' "$LOG.flake" >"$LOG.real"; : >"$LOG.pinned"
renew
for n in "${PRS[@]}"; do
  renew  # per-PR bisect: merge alone onto the base, re-run each REAL id with the same triage
  git checkout -q --detach "$base"
  git fetch -q "$REMOTE" "pull/$n/head" && git merge -q --no-edit FETCH_HEAD >/dev/null 2>&1 || cant "#$n does not merge alone onto the base, so it cannot be attributed"
  tri "$LOG.real" "$LOG.alone"; git merge --abort 2>/dev/null || true
  if [ -s "$LOG.alone" ]; then cat "$LOG.alone" >>"$LOG.pinned"; echo "DROP #$n fails the real browser failures alone on the base"
  else keep+=("$n"); echo "FLAKY #$n: no real failure alone on the base; not blamed"; fi
done
git checkout -q --detach "$base"
[ "${#keep[@]}" -lt "${#PRS[@]}" ] || cant "no culprit pinned for the real failures"
grep -vxFf "$LOG.pinned" "$LOG.real" | grep -q . && cant "real failure(s) not pinned to any PR: $(grep -vxFf "$LOG.pinned" "$LOG.real" | tr '\n' ' ')"
[ "${#keep[@]}" -ge 2 ] || cant "<2 PRs left after dropping culprits"
PRS=("${keep[@]}")
done
# Pushes go through one serial queue across worktrees (mkdir lock under the git common dir).
lock_take "$PQ" "${PUSH_WAIT_SECS:-600}" "${LOCK_TIMEOUT_MIN:-30}" || exit 1
bash "$HERE/land_train.sh" "$B" "$U"; lrc=$?  # not exec: the EXIT trap must still fire
lock_drop "$PQ"; exit $lrc
