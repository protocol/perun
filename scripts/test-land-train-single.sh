#!/usr/bin/env bash
# Tests that train_land.sh lands a one-PR train (any batch-size floor is launcher policy, not a lander refusal), on the union
# path and on the default TRAIN_UNION=auto disjoint path; re-gates a lone innocent PR left after a culprit drop; and still
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

# Fixture: origin + clone with base B, member heads H1 and H2 (each pushed as refs/pull/<n>/head), the one-member
# union U ("merge-train: #1") and the two-member union U12.
git init -q --bare "$WORK/origin.git" -b main
R="$WORK/clone"; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
H1=$(g rev-parse pr1) H2=$(g rev-parse pr2)
g checkout -q --detach "$B"; g merge -q --no-ff -m "merge-train: #1" pr1; U=$(g rev-parse HEAD)
g merge -q --no-ff -m "merge-train: #2" pr2; U12=$(g rev-parse HEAD); g checkout -q --detach "$B"

mkdir -p "$WORK/bin"
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "${5#.}" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
             mergeable) echo MERGEABLE ;; headRefName) echo br1 ;; *) exit 1 ;; esac ;;
  "pr diff") echo changelog.d/1.md ;;
  "pr merge") echo "merged $3 $*" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export H1 H2 U12 VB=$B VU=$U PATH="$WORK/bin:$PATH"  # not B/U: train_land assigns those, an exported one would leak into verify.sh
cd "$R" || exit 2

out=$(VERIFY_CMD=: UNION_DIRS="$R" bash "$SC/train_land.sh" t0 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q '^usage: train_land.sh <tag> <pr> \[pr...\]' <<<"$out"; ok $? "train_land: a call with no PR is refused (exit 2, usage)"

out=$(VERIFY_CMD='echo "GREEN base='"$B"' union='"$U"'"' UNION_DIRS="$R" LOG_DIR="$WORK" BACKFILL_FILE="$WORK/backfill.txt" WAIT_SECS=0 \
  bash "$SC/train_land.sh" t1 1 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^GREEN" <<<"$out" && grep -q "merged 1 pr merge 1 --merge --match-head-commit $H1" <<<"$out"
ok $? "train_land: a one-PR train is union-verified and lands pinned to its proven head (rc=$rc)"

# Default TRAIN_UNION=auto: one PR always passes the disjoint check (nothing to overlap), so it lands with no union proof
# and no VERIFY_CMD run; CI on its exact head is the gate. GEN_RE stands in for land-release.sh's generated-file list.
rm -f "$WORK/verify-ran"
out=$(TRAIN_UNION=auto GEN_RE='SHA256SUMS' VERIFY_CMD="touch $WORK/verify-ran; exit 1" UNION_DIRS="$R" LOG_DIR="$WORK" \
  BACKFILL_FILE="$WORK/backfill.txt" WAIT_SECS=0 bash "$SC/train_land.sh" ta 1 2>&1); rc=$?
[ $rc -eq 0 ] && [ ! -e "$WORK/verify-ran" ] && grep -q '^train_land: #1 is a one-PR train; landing it with no union proof' <<<"$out" \
  && grep -q "merged 1 pr merge 1 --merge" <<<"$out"
ok $? "train_land: under TRAIN_UNION=auto a one-PR train takes the disjoint path, VERIFY_CMD not run (rc=$rc)"

# Culprit drop: the union of #1 and #2 fails t2 in the browser; t2 re-fails alone only where f2 exists, so #2 is dropped and
# the lone innocent #1 is re-gated as a one-PR train (verify, browser on U) and lands. Zero innocents left stays CANT.
cat >"$WORK/verify.sh" <<'V'
case " $* " in *" 2 "*) echo "GREEN base=$VB union=$U12" ;; *) echo "GREEN base=$VB union=$VU" ;; esac
V
echo 'if [ "$UNION_SHA" = "$U12" ]; then echo "FAIL t2"; echo "FAILURES 1"; exit 1; fi; exit 0' >"$WORK/browser.sh"
drop() { VERIFY_CMD="bash $WORK/verify.sh \"\$@\"" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" \
  RERUN_CMD="bash $WORK/rerun.sh" FLAKE_RUNS=3 BACKFILL_FILE="$WORK/backfill.txt" WAIT_SECS=0 bash "$SC/train_land.sh" "$1" 1 2 2>&1; }
echo '[ ! -e f2 ]' >"$WORK/rerun.sh"
out=$(drop td); rc=$?
[ $rc -eq 0 ] && grep -q '^DROP #2 ' <<<"$out" && grep -q "merged 1 pr merge 1 --merge --match-head-commit $H1" <<<"$out" \
  && ! grep -q 'pr merge 2' <<<"$out"
ok $? "train_land: one innocent PR left after a culprit drop is re-gated as a one-PR train and lands (rc=$rc)"
echo '[ ! -e f1 ] && [ ! -e f2 ]' >"$WORK/rerun.sh"
out=$(drop tz); rc=$?
[ $rc -eq 3 ] && grep -q '^CANT: no PR left after dropping culprits' <<<"$out" && ! grep -q 'pr merge' <<<"$out"
ok $? "train_land: no PR left after dropping culprits stays CANT, nothing landed (rc=$rc)"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
