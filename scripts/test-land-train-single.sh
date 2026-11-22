#!/usr/bin/env bash
# Tests that train_land.sh lands a one-PR train (any batch-size floor is launcher policy, not a lander refusal) and still
# refuses a call that names no PR. Plain bash; gh is a PATH stub. Writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-land-train-single.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" PERUN_TRAIN_LEDGER="$WORK/ledger.jsonl" TRAIN_UNION=always
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }

# Fixture: origin + clone with base B, one member head H1, and a one-member union U ("merge-train: #1").
git init -q --bare "$WORK/origin.git" -b main
R="$WORK/clone"; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
g checkout -q -b pr1; echo 1 >"$R/f1"; g add f1; g commit -q -m "pr 1"; H1=$(g rev-parse HEAD)
g checkout -q --detach "$B"; g merge -q --no-ff -m "merge-train: #1" pr1; U=$(g rev-parse HEAD)

mkdir -p "$WORK/bin"
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "${5#.}" in headRefOid) echo "$H1" ;; baseRefName) echo main ;; isDraft) echo false ;;
             mergeable) echo MERGEABLE ;; headRefName) echo br1 ;; *) exit 1 ;; esac ;;
  "pr diff") echo changelog.d/1.md ;;
  "pr merge") echo "merged $3 $*" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export H1 PATH="$WORK/bin:$PATH"
cd "$R" || exit 2

out=$(VERIFY_CMD=: UNION_DIRS="$R" bash "$SC/train_land.sh" t0 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q '^usage: train_land.sh <tag> <pr> \[pr...\]' <<<"$out"; ok $? "train_land: a call with no PR is refused (exit 2, usage)"

out=$(VERIFY_CMD='echo "GREEN base='"$B"' union='"$U"'"' UNION_DIRS="$R" LOG_DIR="$WORK" BACKFILL_FILE="$WORK/backfill.txt" WAIT_SECS=0 \
  bash "$SC/train_land.sh" t1 1 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^GREEN" <<<"$out" && grep -q "merged 1 pr merge 1 --merge --match-head-commit $H1" <<<"$out"
ok $? "train_land: a one-PR train is union-verified and lands pinned to its proven head (rc=$rc)"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
