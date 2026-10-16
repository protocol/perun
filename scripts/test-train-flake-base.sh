#!/usr/bin/env bash
# End-to-end test for the train_land flake-on-base rule: a FLAKE verdict (the test passed at least once in the solo re-runs)
# lands only when the same test also fails >= 1 of 3 solo runs on the base. A test that passes 3 of 3 on the base may be an
# intermittent regression: exit 3 (CANT), no PR blamed, nothing landed. Every runner is a stub; gh is a PATH stub.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-flake-base.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U123=$(g rev-parse HEAD)
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
echo 'if [ "$UNION_SHA" = "$U123" ]; then echo "FAIL t1"; echo "FAILURES 1"; exit 1; fi; exit 0' >"$WORK/browser.sh"
# rerun.sh: solo re-run of t1. On the union (f1 present) it pops $WORK/useq, on the base (f1 absent) $WORK/bseq; F = fail.
cat >"$WORK/rerun.sh" <<'STUB'
f=$WORK/useq; [ -e f1 ] || f=$WORK/bseq
r=$(head -c1 "$f"); tail -c +2 "$f" >"$f.n"; mv "$f.n" "$f"; [ "$r" != F ] || { echo "FAIL $TEST"; exit 1; }
STUB
cd "$R" || exit 2
run() { : >"$WORK/merged.log"; printf %s "$1" >"$WORK/useq"; printf %s "$2" >"$WORK/bseq"
  VERIFY_CMD="bash $WORK/verify.sh \"\$@\"" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/rerun.sh" FLAKE_RUNS=3 bash "$SC/train_land.sh" tt 1 2 3 2>&1; }

# (1) intermittent regression: fails 2 of 3 solo runs (a FLAKE under the all-N rule), never fails on the base (guard 1 run, check 3 runs)
out=$(run FFP PPPP); rc=$?
[ $rc -eq 3 ] && grep -q '^FLAKE t1' <<<"$out" && grep -q '^CANT: flake t1 never fails on the base' <<<"$out" && ! grep -q '^DROP' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a flake that passes 3 of 3 on the base is CANT (exit 3), no blame, nothing landed"
# (2) genuine flake: the same union failures, and the test also fails once on the base -> lands
out=$(run FFP PF); rc=$?
[ $rc -eq 0 ] && grep -q '^FLAKE t1' <<<"$out" && grep -q 'each also flaky on the base; landing' <<<"$out" && [ -s "$WORK/merged.log" ]
ok $? "train_land: a flake that also fails on the base lands"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
