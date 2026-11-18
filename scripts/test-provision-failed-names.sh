#!/usr/bin/env bash
# provision_tools.sh --print: a failing install prints `FAILED <name>` and does not stop the rest of the line; with brew absent the dry run
# says gems fall back to the system ruby. Hermetic: stub node/npm/gem/uv/curl on PATH, throwaway HOME and cache root; nothing is installed.
set -euo pipefail
P=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.claude/skills/deep-code-review/scripts/provision_tools.sh
t=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-failed.XXXXXX"); trap 'rm -rf "$t"' EXIT
mkdir "$t/bin" "$t/home"; fail=0
for x in node trivy osv-scanner curl true; do printf '#!/bin/sh\nexit 0\n' >"$t/bin/$x"; chmod +x "$t/bin/$x"; done
for x in npm gem uv pipx; do printf '#!/bin/sh\nexit 1\n' >"$t/bin/$x"; chmod +x "$t/bin/$x"; done
E=(env -i HOME="$t/home" PATH="$t/bin:/usr/bin:/bin" DCR_CACHE_ROOT="$t/cache" DCR_USER_BIN="$t/home/.local/bin" TMPDIR="$t")
line=$("${E[@]}" bash "$P" --print 2>"$t/err")
if grep -q '^note: brew not found.*system ruby.*may fail' "$t/err"; then echo "ok - no brew: note says gems fall back to system ruby"; else echo "FAIL - no gem/brew note"; fail=1; fi
out=$("${E[@]}" bash -c "$line" 2>&1 || true)
for n in retire brakeman skillspector; do
  if grep -qx "FAILED $n" <<<"$out" || grep -q "^FAILED $n\$" <<<"$out"; then echo "ok - FAILED $n printed"; else echo "FAIL - no 'FAILED $n'"; echo "$out" | tail -8; fail=1; fi
done
grep -q 'FAILED solhint' <<<"$out" && echo "ok - a failing row does not stop the next (solhint)" || { echo "FAIL - line stopped early"; fail=1; }
exit $fail
