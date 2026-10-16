#!/usr/bin/env bash
# train_flake.sh — triage NEW gate failures into REAL vs FLAKE by re-running each alone.
# Usage: train_flake.sh <failed-ids-file> [baseline-ids-file]     (one test id per line)
# Env: RERUN_CMD (required; run via bash -c with TEST=<id>; exit 0 = pass), FLAKE_RUNS (N, default 3), FLAKE_REAL_AT (default = FLAKE_RUNS).
# An id already failing on the base (baseline file) is skipped: it is not new. A new id is REAL only when it fails at least
# FLAKE_REAL_AT of FLAKE_RUNS isolated re-runs, by default ALL of them: a 1-in-3 flake is then blamed (1/3)^3 = 3.7% of the time
# (2-of-3 blamed it 7/27 = 25.9%). Stops early once the verdict is fixed, so a flake that passes once costs one re-run. Prints "REAL <id>" / "FLAKE <id>"
# lines (flakes are reported separately, never blamed on a PR). Exit: 0 no REAL ids, 1 at least one REAL, 2 usage or bad FLAKE_RUNS/FLAKE_REAL_AT (fails closed).
# Optional: FLAKE_LEDGER_DIR=<dir> (outside the worktree and git toplevel, else exit 2) records each id's suite failure and every solo run in
# flake_ledger.py's per-tree ledger (FLAKE_TREE, default HEAD's tree) and prints `quarantined-flake <id> (failed f of n alone)` instead of FLAKE for an
# id on its active quarantine list that failed at least one but not all solo runs and is not consistently failing on the tree (non-blocking). The list is read
# from a snapshot taken before any re-run (FLAKE_QUARANTINE_SNAPSHOT=<file> from the caller, else taken here); both variables are unset for the code under test.
# Same-host baseline: a non-empty baseline file must start with the header `# baseline host=<h> inv=<hash>` written by
# `train_flake.sh --record <failing-ids-file> > baseline` on the machine and invocation that measured it. The current host
# (FLAKE_HOST, default hostname -s) and invocation hash (sha256 of FLAKE_INVOCATION, default BROWSER_CMD) must match, else exit 2:
# a baseline from another machine or another command line makes failures look new (or hides new ones). Missing header = refused.
# Fresh store: FLAKE_SETUP_CMD (optional, via bash -c) runs before EVERY isolated re-run with TEST=<id>, FLAKE_RUN=<n> and
# FLAKE_STORE=<fresh empty dir from mktemp -d under $TMPDIR, left for OS temp cleanup, path printed to stderr>; it must seed that store, and RERUN_CMD sees the same FLAKE_STORE. A re-run that
# reuses the run's own store fakes real failures. Hook failure exits 2 (fails closed). Retries are per test title, never per file.
set -uo pipefail
inv=$(printf %s "${FLAKE_INVOCATION:-${BROWSER_CMD:-}}" | { shasum -a 256 2>/dev/null || sha256sum; } | cut -c1-16)
host=${FLAKE_HOST:-$(hostname -s)}
T=${TMPDIR:-/tmp}
# Ledger env (see the FLAKE_LEDGER_DIR note above): move it into shell variables and unset it so the code under test (RERUN_CMD, FLAKE_SETUP_CMD) never inherits the path.
led=${FLAKE_LEDGER_DIR:-} qsnap=${FLAKE_QUARANTINE_SNAPSHOT:-}; unset FLAKE_LEDGER_DIR FLAKE_QUARANTINE_SNAPSHOT
# norm: the ONE id normalizer (strip trailing whitespace incl. CR, nothing else). Every emit and match of a FAIL/REAL id goes through it
# (`train_flake.sh --norm` filters stdin), so an id printed with a trailing space or CRLF still equals the listed one.
norm() { sed -E 's/[[:space:]]+$//'; }
[ "${1:-}" != --norm ] || { norm; exit $?; }
# one_run <id> <n>: fresh store (mktemp -d, FLAKE_STORE), optional FLAKE_SETUP_CMD hook, then RERUN_CMD alone. rc 125 = hook failed.
one_run() {
  local d rc=0; d=$(mktemp -d "$T/flake-store.XXXXXX") || return 125; echo "train_flake: store $d (left for OS temp cleanup)" >&2
  export TEST=$1 FLAKE_RUN=$2 FLAKE_STORE=$d
  if [ -z "${FLAKE_SETUP_CMD:-}" ] || bash -c "$FLAKE_SETUP_CMD" >/dev/null 2>&1 </dev/null; then bash -c "$RERUN_CMD" >"${RERUN_OUT:-/dev/null}" 2>&1 </dev/null || rc=1; else rc=125; fi
  return $rc
}
if [ "${1:-}" = --one ]; then [ -n "${2:-}" ] && [ -n "${RERUN_CMD:-}" ] || { echo "usage: RERUN_CMD=... train_flake.sh --one <id>" >&2; exit 2; }; one_run "$2" 1; exit $?; fi
# --base <id>: run on the base checkout; exit 0 = pre-existing (fails >= FLAKE_REAL_AT of FLAKE_RUNS alone AND each failing run's
# output has a `FAIL <id>` line, proving the test ran there: a test the PR added is absent on the base and is NOT pre-existing),
# 1 = not pre-existing (RERUN_CMD must print `FAIL <id>` only for tests that actually ran), 125 = fresh store/hook failed or bad bounds (fail closed).
if [ "${1:-}" = --base ]; then
  [ -n "${2:-}" ] && [ -n "${RERUN_CMD:-}" ] || { echo "usage: RERUN_CMD=... train_flake.sh --base <id>" >&2; exit 2; }
  runs=${FLAKE_RUNS:-3} need=${FLAKE_REAL_AT:-$runs}; f=0 p=0; o=$(mktemp "$T/flake-out.XXXXXX") || exit 125
  bid=$(printf %s "$2" | norm)
  case $runs$need in ''|*[!0-9]*) exit 125 ;; esac; [ "$need" -ge 1 ] && [ "$need" -le "$runs" ] || exit 125
  for n in $(seq "$runs"); do
    RERUN_OUT=$o one_run "$bid" "$n"; r=$?
    [ "$r" -ne 125 ] || exit 125
    if [ "$r" -eq 0 ] || ! sed -nE 's/^FAIL +//p' "$o" | norm | grep -qxF -- "$bid"; then p=$((p + 1)); else f=$((f + 1)); fi
    [ "$f" -ge "$need" ] || [ "$p" -gt $((runs - need)) ] && break
  done
  [ "$f" -ge "$need" ]; exit $?
fi
if [ "${1:-}" = --record ]; then
  [ -n "${2:-}" ] && [ -n "${FLAKE_INVOCATION:-${BROWSER_CMD:-}}" ] || { echo "usage: FLAKE_INVOCATION=<cmd> train_flake.sh --record <failing-ids-file>" >&2; exit 2; }
  echo "# baseline host=$host inv=$inv"; cat -- "$2"; exit 0
fi
[ $# -ge 1 ] && [ -n "${RERUN_CMD:-}" ] || { echo "usage: RERUN_CMD=... train_flake.sh <failed-ids> [baseline-ids]" >&2; exit 2; }
[ -r "$1" ] || { echo "could not check: failed-ids file '$1' is missing or unreadable (a missing list is not 'no failures')" >&2; exit 2; }
[ -z "${2:-}" ] || [ -r "$2" ] || { echo "could not check: baseline file '$2' is unreadable (refusing to treat it as empty)" >&2; exit 2; }
runs=${FLAKE_RUNS:-3} need=${FLAKE_REAL_AT:-$runs} real=0
case $runs$need in ''|*[!0-9]*) echo "train_flake: FLAKE_RUNS/FLAKE_REAL_AT must be integers" >&2; exit 2 ;; esac
[ "$runs" -ge 1 ] && [ "$need" -ge 1 ] && [ "$need" -le "$runs" ] || { echo "train_flake: need 1 <= FLAKE_REAL_AT <= FLAKE_RUNS" >&2; exit 2; }
if [ -s "${2:-/dev/null}" ] && [ "$(head -n1 "$2" | norm)" != "# baseline host=$host inv=$inv" ]; then
  echo "train_flake: baseline $2 not recorded on this host with this invocation (want '# baseline host=$host inv=$inv'); refusing to compare" >&2; exit 2
fi
L="$(dirname "$0")/flake_ledger.py"
if [ -n "$led" ]; then
  python3 "$L" --dir "$led" guard >&2 || exit 2  # a ledger dir the code under test can write (under the worktree/toplevel) is refused
  if [ -z "$qsnap" ]; then  # no snapshot from the caller: take one now, before any re-run executes code under test
    qsnap=$(mktemp "$T/flake-quar.XXXXXX") || exit 2; cp "$led/quarantine.json" "$qsnap" 2>/dev/null || echo '{}' >"$qsnap"
  fi
fi
rep() { local i; for ((i = 0; i < $3; i++)); do printf '%s %s\n' "$1" "$2"; done; }  # rep <word> <id> <count>
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [ -z "${2:-}" ] || ! norm <"$2" | grep -qxF -- "$id" 2>/dev/null || continue
  f=0 p=0 qok=0
  # Quarantine (flake_ledger.py): `check` against the pre-run snapshot, exit 0 = actively quarantined and not consistently failing on this tree.
  # Errors (exit 2) leave qok=0 (fail closed). A quarantined id runs ALL its solo re-runs (no early stop on the first pass) so a flake is seen failing.
  [ -z "$led" ] || ! python3 "$L" --dir "$led" check "$id" --quarantine "$qsnap" ${FLAKE_TREE:+--tree "$FLAKE_TREE"} >/dev/null 2>&1 || qok=1
  for n in $(seq "$runs"); do
    one_run "$id" "$n"; r=$?
    [ "$r" -ne 125 ] || { echo "train_flake: fresh store or FLAKE_SETUP_CMD failed for $id" >&2; exit 2; }
    if [ "$r" -eq 0 ]; then p=$((p + 1)); else f=$((f + 1)); fi
    if [ "$f" -ge "$need" ] || { [ "$qok" -eq 0 ] && [ "$p" -gt $((runs - need)) ]; }; then break; fi
  done
  if [ "$f" -ge "$need" ]; then v="REAL $id"; real=1; else v="FLAKE $id (failed $f of $((f + p)) alone)"; fi
  # quarantined-flake needs a solo failure (0 < f < n): a suite failure that passes every solo re-run keeps the plain FLAKE and its base check.
  echo "$v" | { if [ "$qok" -eq 1 ] && [ "$f" -ge 1 ] && [ "$f" -lt "$need" ]; then sed 's/^FLAKE /quarantined-flake /'; else cat; fi; }
  # Evidence is recorded per run (the suite failure, then each solo run), best-effort; verdict labels are never evidence.
  [ -z "$led" ] || { printf 'SUITE %s\n' "$id"; rep FAIL "$id" "$f"; rep PASS "$id" "$p"; } | python3 "$L" --dir "$led" record ${FLAKE_TREE:+--tree "$FLAKE_TREE"} >&2 || true
done < <(norm <"$1")
exit $real
