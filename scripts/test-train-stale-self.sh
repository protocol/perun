#!/usr/bin/env bash
# Tests: stale-script self-exit (train_land.sh run for real, merge_train.py), unique run tag (train_land.sh), SHA-bound verdict stamp (already tested elsewhere).
# Plain bash; gh is a PATH stub; the script under test is a tracked copy inside a throwaway clone; writes only under $WORK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-stale.XXXXXX")"
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "mktemp failed" >&2; exit 2; }
trap 'chmod -R u+rw "$WORK" 2>/dev/null; rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

# --- merge_train.py: check_stale ---
cp "$SC/merge_train.py" "$WORK/mt_copy.py"
rc=0; python3 -I - <<'P' || rc=$?
import importlib.util, os, sys
sys.path.insert(0, os.environ["SC"])
spec = importlib.util.spec_from_file_location("mt", os.path.join(os.environ["SC"], "merge_train.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.SRC = os.path.join(os.environ["WORK"], "mt_copy.py")
t = m.Train.__new__(m.Train); t.src_h = m.src_hash(); said = []; t.say = said.append
os.environ["STALE_SELF_EXIT"] = "enforce"; t.check_stale()  # unchanged file: quiet
open(m.SRC, "a").write("\n# edit\n")
os.environ["STALE_SELF_EXIT"] = "shadow"; t.check_stale(); t.check_stale()
assert len(said) == 1 and "SHADOW stale-self-exit" in said[0], said
os.environ["STALE_SELF_EXIT"] = "off"; t.check_stale()
os.environ["STALE_SELF_EXIT"] = "enforce"
try: t.check_stale(); raise SystemExit("no Stale raised")
except m.Stale: pass
assert m.STALE == 6
os.remove(m.SRC); assert m.src_hash() is None
t.stale_said = False; said.clear()
os.environ["STALE_SELF_EXIT"] = "shadow"; t.check_stale()  # deleted file: shadow only logs, never crashes
assert said and "cannot be read" in said[0], said
os.environ["STALE_SELF_EXIT"] = "enforce"
try: t.check_stale(); raise SystemExit("no Stale on unreadable")
except m.Stale: pass
P
ok $rc "merge_train check_stale: shadow logs once, off skips, enforce raises Stale; a deleted SRC never crashes (shadow logs, enforce raises)"

# --- train_land.sh, the real script, tracked inside a throwaway clone ---
R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g config core.fileMode false; cp -R "$SC" "$R/sc"; g add sc; g commit -q -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U=$(g rev-parse HEAD)
export B U H1=$(g rev-parse pr1) H2=$(g rev-parse pr2)
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
echo 'echo "GREEN base=$B union=$U"' >"$WORK/green.sh"
# paths baked in: the verify stage runs with a scrubbed environment
echo "echo \"GREEN base=\$B union=\$U\"; echo '# edit' >>'$R/sc/train_land.sh'" >"$WORK/edit.sh"
echo "echo \"GREEN base=\$B union=\$U\"; chmod 000 '$R/sc/train_land.sh'" >"$WORK/unread.sh"
echo 'echo "GREEN base=$B union=$U"; cut -d" " -f1 "$LOG_DIR/traintt.log.pid" >"$WORK/seen"' >"$WORK/mark.sh"
echo 'echo "GREEN base=$B union=$U"; [ ! -e "$LOG_DIR/traintt.log.pid" ] && echo NOMARK >"$WORK/seen"' >"$WORK/nomark.sh"
export R; cd "$R"
run() { : >"$WORK/merged.log"; git -C "$R" checkout -q --detach "$B"; git -C "$R" checkout -q -- sc; chmod 644 "$R/sc/train_land.sh"
  env "$@" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD=true bash "$R/sc/train_land.sh" tt 1 2 2>&1; }
landed() { [ "$(wc -l <"$WORK/merged.log" | tr -d ' ')" = 2 ]; }

out=$(run VERIFY_CMD="bash $WORK/green.sh" STALE_SELF_EXIT=enforce) && rc=0 || rc=$?
[ $rc -eq 0 ] && landed && ! grep -q 'STALE\|SHADOW stale' <<<"$out"
ok $? "train_land: HEAD moves (base, union) with the script file unchanged: enforce does not exit and the train lands"
out=$(run VERIFY_CMD="bash $WORK/edit.sh" STALE_SELF_EXIT=enforce) && rc=0 || rc=$?
[ $rc -eq 6 ] && grep -q '^STALE: train_land.sh changed on disk' <<<"$out" && [ ! -s "$WORK/merged.log" ] && [ ! -e "$WORK/traintt.log.pid" ]
ok $? "train_land: the script edited mid-run, enforce exits 6, lands nothing, marker removed"
out=$(run VERIFY_CMD="bash $WORK/edit.sh") && rc=0 || rc=$?
[ $rc -eq 0 ] && grep -q 'SHADOW stale-self-exit: train_land.sh changed' <<<"$out" && landed
ok $? "train_land: the default (shadow) logs the stale script and runs on"
out=$(run VERIFY_CMD="bash $WORK/edit.sh" STALE_SELF_EXIT=off) && rc=0 || rc=$?
[ $rc -eq 0 ] && ! grep -q 'stale-self-exit\|STALE' <<<"$out" && landed
ok $? "train_land: STALE_SELF_EXIT=off never checks"
out=$(run VERIFY_CMD="bash $WORK/unread.sh" STALE_SELF_EXIT=enforce) && rc=0 || rc=$?
chmod 644 "$R/sc/train_land.sh"
[ $rc -eq 0 ] && grep -q 'cannot read train_land.sh' <<<"$out" && landed
ok $? "train_land: an unreadable script file is log-only even under enforce (no false exit 6)"
n0=$(ls "${TMPDIR:-/tmp}" | grep -c '^train_land\.' || true); run VERIFY_CMD="bash $WORK/green.sh" >/dev/null || true
[ "$(ls "${TMPDIR:-/tmp}" | grep -c '^train_land\.' || true)" = "$n0" ]
ok $? "train_land: the private script copy is removed at exit"

# --- unique run tag ---
sleep 30 & LIVE=$!
echo "$LIVE" >"$WORK/traintt.log.pid"
out=$(run VERIFY_CMD="bash $WORK/green.sh" TRAIN_UNIQUE_RUN=enforce) && rc=0 || rc=$?
[ $rc -eq 2 ] && grep -q "REFUSE tag tt: a live train (pid $LIVE)" <<<"$out" && [ "$(cat "$WORK/traintt.log.pid")" = "$LIVE" ] && [ ! -s "$WORK/merged.log" ]
ok $? "unique tag: enforce refuses a live owner, exit 2, the owner's marker untouched"
out=$(run VERIFY_CMD="bash $WORK/green.sh") && rc=0 || rc=$?
[ $rc -eq 0 ] && grep -q 'REFUSE tag tt' <<<"$out" && landed && [ "$(cat "$WORK/traintt.log.pid")" = "$LIVE" ]
ok $? "unique tag: shadow warns, runs on, and does not delete the live owner's marker"
kill "$LIVE" 2>/dev/null || true; wait "$LIVE" 2>/dev/null || true
rm -f "$WORK/seen"; out=$(run VERIFY_CMD="bash $WORK/mark.sh" TRAIN_UNIQUE_RUN=enforce) && rc=0 || rc=$?
seen=$(cat "$WORK/seen" 2>/dev/null || true)
[ $rc -eq 0 ] && ! grep -q REFUSE <<<"$out" && [ -n "$seen" ] && [ "$seen" != "$LIVE" ] && [ ! -e "$WORK/traintt.log.pid" ]
ok $? "unique tag: a dead owner's marker is reaped, the new run's marker holds its own pid (not the dead one) and is removed at exit"
rm -f "$WORK/seen"; out=$(run VERIFY_CMD="bash $WORK/nomark.sh" TRAIN_UNIQUE_RUN=off) && rc=0 || rc=$?
[ $rc -eq 0 ] && [ "$(cat "$WORK/seen" 2>/dev/null)" = NOMARK ]
ok $? "unique tag: off writes no marker"

# --- SHA-bound verdicts: already enforced; stale-stamp refusal is tested in test-train-liveness.sh ---
grep -q 'a red set stamped with another sha is refused' "$ROOT/scripts/test-train-liveness.sh"
ok $? "base-red verdict is SHA-stamped (stale stamp refusal test present)"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
