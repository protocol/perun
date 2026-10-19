#!/usr/bin/env bash
# Tests for waiting instead of refusing in train_land.sh (issue #1777): a held exclusive heavy lease is waited out then DEFERs
# (exit 4, nothing built); a held push lock is checked BEFORE the compose, never after a green gate; the lease is released once the
# push lock is held. Stub gh/verify; plain bash; writes only under $WORK and a private PERUN_HEAVY_DIR.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-lease.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U=$(g rev-parse HEAD); g checkout -q --detach "$B"
export B U H1=$(g rev-parse pr1) H3=$(g rev-parse pr3)
mkdir -p "$WORK/bin"; cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo '{"tool_input":{"command":"pytest tests"}}' | PERUN_GATE_LOAD1=0 PERUN_GATE_CORES=8 PERUN_GATE_FREE_RAM_PCT=80 python3 "$SC/heavy_gate.py" >>"$WORK/land-gate.log"; echo "merged $3" >>"$WORK/merged.log" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
echo 'echo ran >>"$WORK/verify.ran"; echo "GREEN base=$B union=$U"' >"$WORK/verify.sh"
reset() { : >"$WORK/merged.log"; : >"$WORK/land-gate.log"; rm -f "$WORK/verify.ran" "$WORK/hv/heavy.exclusive"; mkdir -p "$WORK/hv"; }
run() { (cd "$R" && env VERIFY_CMD="bash $WORK/verify.sh" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD=skip GH="$WORK/bin/gh" "$@" bash "$SC/train_land.sh" tl 1 3 2>&1); }
hold() { echo "$$ $(date +%s)" >"$WORK/hv/heavy.exclusive"; }
PQ="$R/.git/train-push.lock"; holdpq() { mkdir "$PQ"; echo $$ >"$PQ/pid"; date +%s >"$PQ/ts"; }
freepq() { rm -f "$PQ/pid" "$PQ/ts"; rmdir "$PQ" 2>/dev/null; }

reset; hold; out=$(run LEASE_WAIT_SECS=0); rc=$?
[ $rc -eq 4 ] && grep -q '^DEFER' <<<"$out" && [ ! -e "$WORK/verify.ran" ]; ok $? "lease held, no wait: DEFER exit 4 with no compose run"

reset; hold; (sleep 2; rm -f "$WORK/hv/heavy.exclusive") & out=$(run LEASE_WAIT_SECS=20); rc=$?; wait
[ $rc -eq 0 ] && [ "$(sort "$WORK/merged.log" | tr '\n' ' ')" = "merged 1 merged 3 " ]; ok $? "lease held then freed: the gate waits and lands (not refused)"

reset; holdpq; out=$(run PUSH_WAIT_SECS=0); rc=$?
[ $rc -eq 1 ] && grep -q "lock held by pid $$" <<<"$out" && [ ! -e "$WORK/verify.ran" ]; ok $? "push lock held: fails before the compose, never after a green gate"
freepq

reset; holdpq; (sleep 2; freepq) & out=$(run PUSH_WAIT_SECS=20); rc=$?; wait
[ $rc -eq 0 ] && [ -e "$WORK/verify.ran" ] && [ -s "$WORK/merged.log" ]; ok $? "push lock held then freed: the compose waits for the landing, then lands"

reset; out=$(run); rc=$?
[ $rc -eq 0 ] && [ -s "$WORK/merged.log" ] && [ ! -s "$WORK/land-gate.log" ]; ok $? "lease is released before the merges run (heavy commands allowed while landing)"
[ ! -e "$PQ" ] && [ ! -e "$WORK/hv/heavy.exclusive" ]; ok $? "no push lock or lease left behind"

python3 -I "$ROOT/scripts/test_train_lease_replay.py"; ok $? "replay: fewer refused composes, lower idle-green, merges/day not worse"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
