#!/usr/bin/env bash
# review_checks.sh: semgrep NOT CHECKED when every chunk scanned 0 files (paths.scanned empty, no findings): one not-checked row,
# "NOT CHECKED: semgrep scanned 0 files" on stderr, semgrep out of the "ran" list. When another chunk scanned files normally, semgrep
# is not reported as NOT CHECKED. Stub semgrep (one JSON per call) on a hermetic PATH, fictional content only.
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the test fails against the pre-fix script).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/sgzero.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
fail=0
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b" # only the system binaries review_checks.sh needs, never the host PATH
done
# stub: call N (1-based) prints $SG_DIR/N.json
cat >"$T/bin/semgrep" <<'S'
#!/usr/bin/env bash
n=$(cat "$SG_DIR/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" >"$SG_DIR/n"; cat "$SG_DIR/$n.json"
S
chmod +x "$T/bin/semgrep"
mkdir -p "$T/repo" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
mkdir src; for i in $(seq 1 201); do printf 'x = %s\n' "$i" >"src/f$i.py"; done
G add -A && G commit -q -m change
ZERO='{"results":[],"errors":[],"paths":{"scanned":[]}}'
OKJ='{"results":[],"errors":[],"paths":{"scanned":["src/f1.py"]}}'
# go J1 J2: run the hub (201 changed files = two semgrep chunks of 200 + 1); call 1 prints J1, call 2 prints J2
go() {
  mkdir -p "$T/sg"; rm -f "$T/sg/n"; printf '%s\n' "$1" >"$T/sg/1.json"; printf '%s\n' "$2" >"$T/sg/2.json"
  PATH="$T/bin:$T/sys" SG_DIR="$T/sg" bash "$RC" --base base >"$T/out" 2>"$T/err" || true
}
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }
nc() { jq '[.[] | select(.tool=="semgrep" and .rule=="not-checked")] | length' "$T/out"; }
msg() { grep -c '^review_checks: not run: semgrep (NOT CHECKED: semgrep scanned 0 files)' "$T/err" || true; }

go "$ZERO" "$ZERO" # every chunk scanned nothing
eq "$(msg)" 1 "all chunks zero: one NOT CHECKED line (not one per chunk)"
eq "$(nc)" 1 "all chunks zero: one semgrep not-checked row"

go "$ZERO" "$OKJ" # one chunk zero, one scanned normally
eq "$(msg)" 0 "mixed chunks: semgrep not reported as scanning 0 files"
eq "$(nc)" 0 "mixed chunks: no semgrep not-checked row"
exit $fail
