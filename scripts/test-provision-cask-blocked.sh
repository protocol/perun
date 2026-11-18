#!/usr/bin/env bash
# provision_tools.sh: on a non-Darwin host a missing cask tool (codeql) prints BLOCKED and adds no cask install to the --print line.
# Hermetic: stub uname=Linux, throwaway HOME/cache; nothing is installed.
set -euo pipefail
P=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.claude/skills/deep-code-review/scripts/provision_tools.sh
t=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-cask.XXXXXX"); trap 'rm -rf "$t"' EXIT
mkdir "$t/bin" "$t/home"; fail=0
printf '#!/bin/sh\necho Linux\n' >"$t/bin/uname"; chmod +x "$t/bin/uname"
E=(env -i HOME="$t/home" PATH="$t/bin:/usr/bin:/bin" DCR_CACHE_ROOT="$t/cache" DCR_USER_BIN="$t/home/.local/bin" TMPDIR="$t")
out=$("${E[@]}" bash "$P" 2>&1 || true)
line=$("${E[@]}" bash "$P" --print 2>/dev/null)
grep -q '^BLOCKED  codeql (cask install is macOS-only' <<<"$out" && echo "ok - codeql BLOCKED off macOS" || { echo "FAIL - no BLOCKED codeql"; fail=1; }
grep -q -- '--cask' <<<"$line" && { echo "FAIL - cask install line printed"; fail=1; } || echo "ok - no cask install line"
exit $fail
