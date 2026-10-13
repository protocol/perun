#!/usr/bin/env bash
# Contract: a test id emitted with trailing whitespace or CRLF still matches its clean form everywhere train_flake.sh /
# train_land.sh compare ids (one normalizer: `train_flake.sh --norm`). Stubs only; writes under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-norm.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

printf 'a b \r\n c\t\n' | bash "$SC/train_flake.sh" --norm >"$WORK/n"; [ "$(cat "$WORK/n")" = "$(printf 'a b\n c')" ]; ok $? "--norm strips trailing space/CR/tab only (inner and leading kept)"

# --base: runner prints the id with a trailing space + CR; the clean id must still be proven failing there (exit 0 = pre-existing)
export RERUN_CMD='printf "FAIL t1 \r\n"; exit 1'
bash "$SC/train_flake.sh" --base 't1' >/dev/null 2>&1; ok $? "--base: id emitted with trailing space+CRLF matches clean id"
bash "$SC/train_flake.sh" --base 't1 ' >/dev/null 2>&1; ok $? "--base: id passed with trailing space matches clean emit"
bash "$SC/train_flake.sh" --base 't2' >/dev/null 2>&1; [ $? -eq 1 ]; ok $? "--base: a different id is still not matched (exit 1)"

# list mode: failed id has trailing space+CR, baseline lists it clean -> skipped, no REAL
printf 't1 \r\n' >"$WORK/fails"; : >"$WORK/base0"
hdr="# baseline host=$(hostname -s) inv=$(printf %s inv | { shasum -a 256 2>/dev/null || sha256sum; } | cut -c1-16)"
printf '%s\nt1\n' "$hdr" >"$WORK/base"
out=$(FLAKE_INVOCATION=inv RERUN_CMD=false bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/base" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ]; ok $? "list: trailing-space failed id matches clean baseline id (skipped, not blamed)"
printf '%s\r\nt1 \r\n' "$hdr" >"$WORK/base"; printf 't1\n' >"$WORK/fails"
out=$(FLAKE_INVOCATION=inv RERUN_CMD=false bash "$SC/train_flake.sh" "$WORK/fails" "$WORK/base" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ]; ok $? "list: CRLF baseline (header and id) matches clean failed id"
printf 't1 \r\n' >"$WORK/fails"
out=$(RERUN_CMD=false bash "$SC/train_flake.sh" "$WORK/fails" 2>/dev/null); [ "$out" = "REAL t1" ]; ok $? "list: REAL id is printed normalized (no trailing space)"

# non-vacuous: without the normalizer the raw id really does miss its clean twin (this is the field bug)
printf 'FAIL t1 \r\n' | sed -nE 's/^FAIL +//p' | grep -qxF -- t1; [ $? -ne 0 ]; ok $? "raw (un-normalized) emit does NOT match the clean id"
printf 'FAIL t1 \r\n' | sed -nE 's/^FAIL +//p' | bash "$SC/train_flake.sh" --norm | grep -qxF -- t1; ok $? "normalized emit matches the clean id"

# train_land.sh path (where the bug lived): browser prints "FAIL bx <CR>", the baseline lists clean "bx" -> pre-existing, lands
R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U13=$(g rev-parse HEAD)
mkdir -p "$WORK/bin"; cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo "merged $3" >>"$WORK/merged.log" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH" WORK B U13 H1=$(g rev-parse pr1) H3=$(g rev-parse pr3)
echo 'echo "GREEN base=$B union=$U13"' >"$WORK/verify.sh"
printf 'printf "FAIL bx \\r\\n"; echo "FAILURES 1"; exit 1\n' >"$WORK/b.sh"
BCMD="bash $WORK/b.sh"
printf 'echo "FAIL bx"; exit 1\n' >"$WORK/rerun.sh"
cd "$R" || exit 2
land() { VERIFY_CMD="bash $WORK/verify.sh" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="$BCMD" PUSH_WAIT_SECS=0 RERUN_CMD="bash $WORK/rerun.sh" "$@" bash "$SC/train_land.sh" t 1 3 2>&1; }
: >"$WORK/merged.log"; out=$(land env); rc=$?
[ $rc -eq 0 ] && grep -q '^BASE RED: 1 pre-existing: bx$' <<<"$out" && [ "$(sort "$WORK/merged.log" | tr '\n' ' ')" = "merged 1 merged 3 " ]; ok $? "train_land: browser 'FAIL bx<space><CR>' matches the clean 'FAIL bx' re-run on the base (BASE RED, lands)"
: >"$WORK/merged.log"; out=$(land env BASELINE_FAILS="$WORK/missing"); rc=$?
[ $rc -eq 0 ] && grep -q '^BASE RED: 1 pre-existing: bx$' <<<"$out"; ok $? "train_land: unreadable BASELINE_FAILS behaves as an empty baseline (no crash)"
echo "id-normalize: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
