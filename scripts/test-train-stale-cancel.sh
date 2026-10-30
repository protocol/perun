#!/usr/bin/env bash
# Tests: train_land.sh clears a leftover "$LOG.cancel" (urgent stop) from an earlier run of the same tag when a fresh run starts, still honors one
# that arrives after the start, and leaves it alone while a live same-tag twin may own it (#2142).
# Plain bash; gh is a PATH stub; the script under test is a tracked copy inside a throwaway clone; writes only under $WORK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-cancel.XXXXXX")"
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "mktemp failed" >&2; exit 2; }
trap '[ -z "${LIVE:-}" ] || kill "$LIVE" 2>/dev/null; chmod -R u+rw "$WORK" 2>/dev/null; rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

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
C="$WORK/traintt.log.cancel" P="$WORK/traintt.log.pid"
echo 'echo "GREEN base=$B union=$U"' >"$WORK/green.sh"
echo "echo \"GREEN base=\$B union=\$U\"; touch '$C'" >"$WORK/cancel.sh"  # paths baked in: the verify stage runs with a scrubbed environment
export R; cd "$R"
run() { : >"$WORK/merged.log"; git -C "$R" checkout -q --detach "$B"; git -C "$R" checkout -q -- sc
  env "$@" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD=true bash "$R/sc/train_land.sh" tt 1 2 2>&1; }
landed() { [ "$(wc -l <"$WORK/merged.log" | tr -d ' ')" = 2 ]; }

touch "$C"  # left by an earlier run of tag tt: it ended before its next tick, or the stop came after it had finished
out=$(run VERIFY_CMD="bash $WORK/green.sh") && rc=0 || rc=$?
[ $rc -eq 0 ] && ! grep -q '^CANCEL:' <<<"$out" && landed && [ ! -e "$C" ] && [ ! -e "$P" ] && s=0 || s=1
ok $s "a leftover cancel file from an earlier run is cleared at start: the fresh run lands (exit 0, file and marker removed)"

out=$(run VERIFY_CMD="bash $WORK/cancel.sh") && rc=0 || rc=$?
[ $rc -eq 6 ] && grep -q '^CANCEL:' <<<"$out" && [ ! -s "$WORK/merged.log" ] && [ ! -e "$C" ] && [ ! -e "$P" ] && s=0 || s=1
ok $s "a cancel that arrives after the run started still stops it (exit 6, lands nothing, file and marker removed)"

touch "$C"
out=$(run VERIFY_CMD="bash $WORK/green.sh" TRAIN_UNIQUE_RUN=off) && rc=0 || rc=$?
[ $rc -eq 0 ] && landed && [ ! -e "$C" ] && s=0 || s=1
ok $s "TRAIN_UNIQUE_RUN=off clears a leftover cancel file too (no marker to tell a twin apart)"

sleep 30 & LIVE=$!
echo "$LIVE" >"$P"; touch "$C"  # a live train of the same tag; the shadow default warns and goes on
out=$(run VERIFY_CMD="bash $WORK/green.sh") && rc=0 || rc=$?
[ $rc -eq 6 ] && grep -q '^CANCEL:' <<<"$out" && [ ! -s "$WORK/merged.log" ] && [ "$(cat "$P")" = "$LIVE" ] && s=0 || s=1
ok $s "a live same-tag twin keeps the cancel file: the newer run does not swallow it (exit 6, lands nothing, the twin's marker untouched)"
kill "$LIVE" 2>/dev/null || true; wait "$LIVE" 2>/dev/null || true; LIVE=

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
