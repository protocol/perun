#!/usr/bin/env bash
# Tests for scripts/gh-shim/gh: reads retry on a transient error and succeed; a non-transient error returns at once; writes
# (pr merge, api -X POST) run exactly once even when they fail transiently; the shim skips itself when finding the real gh.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-gh-shim.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"
# fake gh: fails with a 502 until the call counter (per command line) reaches $FAIL_UNTIL; "pr view 404" fails non-transiently
cat >"$WORK/bin/gh" <<'FAKE'
#!/bin/sh
echo x >>"$WORK/calls"
n=$(wc -l <"$WORK/calls")
[ "$*" = "pr view 404" ] && { echo "HTTP 404 not found" >&2; exit 1; }
[ "$n" -lt "${FAIL_UNTIL:-1}" ] && { echo "HTTP 502 bad gateway" >&2; exit 1; }
echo "ok $*"
FAKE
chmod +x "$WORK/bin/gh"
export WORK PATH="$ROOT/scripts/gh-shim:$WORK/bin:$PATH" GH_SHIM_SLEEP=0
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
calls() { wc -l <"$WORK/calls" | tr -d ' '; }
run() { : >"$WORK/calls"; FAIL_UNTIL=$1 gh "${@:2}" 2>/dev/null; }

out=$(run 3 pr view 7); [ "$out" = "ok pr view 7" ] && [ "$(calls)" = 3 ]; ok $? "read retried twice then succeeded (3 calls)"
out=$(run 99 pr list); rc=$?; [ "$rc" = 1 ] && [ "$(calls)" = 4 ]; ok $? "read gives up after GH_SHIM_TRIES (4) and keeps the exit code"
out=$(run 1 pr view 404); rc=$?; [ "$rc" = 1 ] && [ "$(calls)" = 1 ]; ok $? "non-transient error is not retried"
out=$(run 99 pr merge 7); [ "$(calls)" = 1 ]; ok $? "write (pr merge) runs once"
out=$(run 99 api -X POST repos/x/y/issues); [ "$(calls)" = 1 ]; ok $? "api -X POST runs once"
out=$(run 99 api repos/x/y -f a=b); [ "$(calls)" = 1 ]; ok $? "api with -f (implicit POST) runs once"
out=$(run 2 api repos/x/y/pulls); [ "$out" = "ok api repos/x/y/pulls" ] && [ "$(calls)" = 2 ]; ok $? "plain api GET is retried"
out=$(run 2 pr view 7 -R o/r); [ "$(calls)" = 2 ]; ok $? "global flag before subcommand (-R) still classified as a read"
out=$(run 99 -R o/r pr merge 7); [ "$(calls)" = 1 ]; ok $? "write behind a global flag runs once"
: >"$WORK/calls"; FAIL_UNTIL=99 GH_SHIM_TRIES=abc GH_SHIM_SLEEP=x gh pr list >/dev/null 2>&1; [ "$(calls)" = 4 ]; ok $? "invalid env falls back to defaults (bounded)"
sed -i.bak 's/HTTP 502 bad gateway/read: EOF/' "$WORK/bin/gh"; out=$(run 2 pr list); [ "$(calls)" = 2 ]; ok $? "EOF is retried"
sed -i.bak 's/read: EOF/API rate limit exceeded/' "$WORK/bin/gh"; out=$(run 2 pr list); [ "$(calls)" = 2 ]; ok $? "rate limit is retried"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
