#!/usr/bin/env bash
# Tests for fleet lessons: same-host/same-invocation baselines, per-title fresh-store re-runs (train_flake.sh) and
# process-group timeboxes (merge_train.default_runner). Writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-fleet.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
export RERUN_CMD=true
echo t1 >"$WORK/fails"; echo t1 >"$WORK/ids"

# --- baseline carries host + invocation hash; a mismatch or a headerless file is refused (exit 2) ---
FLAKE_HOST=hostA FLAKE_INVOCATION="npx e2e --all" bash "$SC/train_flake.sh" --record "$WORK/ids" >"$WORK/base"
head -n1 "$WORK/base" | grep -qE '^# baseline host=hostA inv=[0-9a-f]{16}$'; ok $? "record: header has host and invocation hash"
FLAKE_HOST=hostA FLAKE_INVOCATION="npx e2e --all" bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/base" >/dev/null 2>&1; ok $? "same host + same invocation: accepted"
FLAKE_HOST=hostB FLAKE_INVOCATION="npx e2e --all" bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/base" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "different host: refused"
FLAKE_HOST=hostA FLAKE_INVOCATION="npx e2e --smoke" bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/base" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "different invocation: refused"
FLAKE_HOST=hostA FLAKE_INVOCATION="npx e2e --all" bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/ids" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "headerless baseline: refused"
FLAKE_HOST=hostA bash "$SC/train_flake.sh" --record "$WORK/ids" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "record without an invocation: usage error"

# --- each re-run of each test title gets its own fresh FLAKE_STORE, created by FLAKE_SETUP_CMD ---
printf 'a\nb\n' >"$WORK/two"
export WORK
FLAKE_SETUP_CMD='echo "$TEST" >>"$WORK/setups"' RERUN_CMD='[ -d "$FLAKE_STORE" ] && echo "$TEST $FLAKE_STORE" >>"$WORK/runs"; false' \
  FLAKE_RUNS=2 FLAKE_REAL_AT=2 bash "$SC/train_flake.sh" "$WORK/two" >"$WORK/out"
[ "$(wc -l <"$WORK/runs" | tr -d ' ')" = 4 ] && [ "$(cut -d' ' -f2 "$WORK/runs" | sort -u | wc -l | tr -d ' ')" = 4 ] \
  && [ "$(sort "$WORK/setups" | tr '\n' ' ')" = "a a b b " ] && grep -q '^REAL a$' "$WORK/out"; ok $? "fresh store: 4 distinct stores, one setup per re-run, per test title"
FLAKE_SETUP_CMD=false bash "$SC/train_flake.sh" "$WORK/two" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "setup hook failure: fails closed (exit 2)"

# --- the train_land bisect re-run goes through the same helper: a stale shared store fails without it, passes with it ---
mkdir "$WORK/stale"; echo dirty >"$WORK/stale/x"; export STALE="$WORK/stale"
FLAKE_SETUP_CMD='echo seed >"$FLAKE_STORE/s"' RERUN_CMD='[ -n "${FLAKE_STORE:-}" ] && [ ! -e "$FLAKE_STORE/x" ] && [ -e "$FLAKE_STORE/s" ]' bash "$SC/train_flake.sh" --one t1 2>/dev/null
ok $? "bisect helper: --one gives a fresh seeded store (a stale shared store would fail)"
RERUN_CMD='[ -n "${FLAKE_STORE:-}" ]' bash -c 'unset FLAKE_STORE; bash -c "$RERUN_CMD"'; [ $? -ne 0 ]; ok $? "without the helper FLAKE_STORE is unset, so a stale-store re-run fails"
grep -q 'train_flake.sh" "\$1"' "$SC/train_land.sh"; ok $? "train_land bisect re-runs through train_flake.sh triage (fresh store per run)"
rmlines=$(grep -cE '\brm\b' "$SC/train_flake.sh"); trapok=$(grep -cF "do [ -z \"\$x\" ] || rm -rf -- \"\$x\"; done' EXIT" "$SC/train_flake.sh")
[ "$rmlines" -eq 1 ] && [ "$trapok" -eq 1 ]; ok $? "train_flake.sh: only rm is the EXIT trap over its own mktemp paths"

# --- timebox kills the whole process group (grandchild included), only its own ---
python3 -I - "$SC" "$WORK/gc.pid" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1]); import merge_train as m
rc, _, err = m.default_runner(["sh", "-c", f"sleep 60 & echo $! > {sys.argv[2]}; wait"], timeout=1)
assert rc == 124 and "timed out" in err, (rc, err)
pid = int(open(sys.argv[2]).read())
import time; time.sleep(0.3)
try: os.kill(pid, 0)
except ProcessLookupError: sys.exit(0)
os.kill(pid, 9); sys.exit(1)
PY
ok $? "timebox: grandchild stopped with its group on timeout (rc 124)"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
