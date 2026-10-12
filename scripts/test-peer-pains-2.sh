#!/usr/bin/env bash
# Tests for peer-pains-2: train_land CANT rule (unattributed browser failures land nothing; flaky-only bisects blame nobody),
# reap_own.sh --report never prints a false orphans=0, session_brief.py prints NOT CHECKED instead of silence.
# Every runner is a stub; gh is a PATH stub. Plain bash; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-peerpains2.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
mkunion() { g checkout -q --detach "$B"; for n in "$@"; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; g rev-parse HEAD; }
U123=$(mkunion 1 2 3); export B U123 H1=$(g rev-parse pr1) H2=$(g rev-parse pr2) H3=$(g rev-parse pr3)
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
echo 'case " $* " in *" 2 "*) echo "GREEN base=$B union=$U123" ;; *) echo "RED" ;; esac' >"$WORK/verify.sh"
echo 'if [ "$UNION_SHA" = "$U123" ]; then echo "FAIL t1"; echo "FAIL t2"; echo "FAILURES 2"; exit 1; fi; exit 0' >"$WORK/browser.sh"
cd "$R" || exit 2
run() { : >"$WORK/merged.log"; VERIFY_CMD="bash $WORK/verify.sh \"\$@\"" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/rerun.sh" FLAKE_RUNS=3 FLAKE_REAL_AT=2 bash "$SC/train_land.sh" tt 1 2 3 2>&1; }

# (1a) both ids fail only with all three PRs present (union-only interaction), pass alone: flaky/interaction, no culprit -> CANT, no blame
echo '[ ! -e f1 ] || [ ! -e f2 ] || [ ! -e f3 ]' >"$WORK/rerun.sh"
out=$(run); rc=$?
[ $rc -eq 3 ] && grep -q '^CANT' <<<"$out" && grep -q '^FLAKY #' <<<"$out" && ! grep -q '^DROP' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: failures that pass alone per PR blame nobody (FLAKY), exit CANT, nothing landed"
# (1b) t2 pinned to #2 but t1 not pinned to any PR alone -> CANT, even though a culprit was found
echo 'if [ "$TEST" = t2 ]; then [ ! -e f2 ]; else [ ! -e f1 ] || [ ! -e f3 ]; fi' >"$WORK/rerun.sh"
out=$(run); rc=$?
[ $rc -eq 3 ] && grep -q '^DROP #2 ' <<<"$out" && grep -q '^CANT: real failure(s) not pinned.*t1' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: a real failure not pinned to any PR lands nothing even when another is pinned"
# (1c) a real failure that also fails on the bare base is pre-existing, never blamed on a PR
echo 'false' >"$WORK/rerun.sh"
out=$(run); rc=$?
[ $rc -eq 1 ] && grep -q '^BASE RED' <<<"$out" && ! grep -q '^DROP' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "train_land: failure pre-existing on the base is BASE RED, no PR blamed, nothing landed"
# (1d) one real culprit alone still isolates: t1 flaky at the union, t2 pinned to #2 -> #2 dropped, #1 and #3 re-verify and land
echo 'echo "GREEN base=$B union=$U123"' >"$WORK/verify.sh"
U13=$(mkunion 1 3); export U13
echo 'case " $* " in *" 2 "*) echo "GREEN base=$B union=$U123" ;; *) echo "GREEN base=$B union=$U13" ;; esac' >"$WORK/verify.sh"
echo 'if [ "$TEST" = t1 ]; then [ -e "$WORK/t1.seen" ] || { touch "$WORK/t1.seen"; exit 1; }; exit 0; fi; [ ! -e f2 ]' >"$WORK/rerun.sh"
out=$(run); rc=$?
[ $rc -eq 0 ] && grep -q '^DROP #2 ' <<<"$out" && ! grep -q 'DROP #[13]' <<<"$out" && [ "$(sort "$WORK/merged.log" | tr '\n' ' ')" = "merged 1 merged 3 " ]
ok $? "train_land: a pinned culprit is dropped, the rest land"

# (2) reap_own --report: pgrep failure is COULD_NOT_CHECK (exit 2), never orphans=0
mkdir "$WORK/fakebin"; printf '#!/bin/sh\nexit 3\n' >"$WORK/fakebin/pgrep"; chmod +x "$WORK/fakebin/pgrep"
out=$(ROOT="$WORK" PATH="$WORK/fakebin:$PATH" bash "$SC/reap_own.sh" --report 2>/dev/null); rc=$?
[ $rc -eq 2 ] && grep -q '^orphans=COULD_NOT_CHECK' <<<"$out" && ! grep -q '^orphans=0' <<<"$out"; ok $? "reap_own --report: pgrep failure prints COULD_NOT_CHECK, not orphans=0"
printf '#!/bin/sh\nexit 1\n' >"$WORK/fakebin/pgrep"
out=$(ROOT="$WORK" PATH="$WORK/fakebin:$PATH" bash "$SC/reap_own.sh" --report 2>/dev/null)
grep -q '^orphans=' <<<"$out" && ! grep -q 'COULD_NOT_CHECK' <<<"$out"; ok $? "reap_own --report: pgrep no-match (rc 1) is a real zero, not an error"

# (3) session_brief: unreadable origin/main version and a failed lsof are NOT CHECKED lines, not silence
out=$(python3 - <<PY
import sys, subprocess, tempfile, pathlib
sys.path.insert(0, "$SC")
import session_brief as sb
d = pathlib.Path(tempfile.mkdtemp(dir="$WORK")); (d/".claude/skills/deep-code-review").mkdir(parents=True); (d/".claude/skills/deep-code-review/VERSION").write_text("1.0.0")
import os; os.environ["PERUN_SOURCE"] = str(d / "nosuchsource")
sb._deadline[0] = float("inf")
print(sb.version_line(d))
sb.dev_servers = lambda paths: None
sb._git = lambda *a, **k: "worktree $WORK/a\n" if a[1:2] == ("worktree",) or "worktree" in a else None
print(sb.hygiene_line(d))
PY
)
grep -q 'perun version NOT CHECKED' <<<"$out" && grep -q 'NOT CHECKED (git/lsof' <<<"$out" && grep -q 'dev servers' <<<"$out"; ok $? "session_brief: failed reads print NOT CHECKED, never silence"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
