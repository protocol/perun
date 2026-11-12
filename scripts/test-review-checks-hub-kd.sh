#!/usr/bin/env bash
# review_checks.sh never routes detekt or security-code-scan (not-routed rows in tool-hub.md): with stub binaries that would emit findings on PATH
# and changed .kt / .cs files, neither stub is run and no row appears. Control: the routed devskim stub IS run on the same .cs file, so the harness is live.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubkd.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'fun main() {}\n' >A.kt; printf 'class B {}\n' >B.cs; G add . && G commit -q -m code
SARIF='{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"x"}},"results":[{"ruleId":"R1","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"B.cs"},"region":{"startLine":1}}}]}]}]}'
for b in detekt security-scan security-code-scan devskim; do
  printf '#!/usr/bin/env bash\necho "%s $*" >>"$HUB_LOG"\nprintf %%s "$J"\n' "$b" >"$T/bin/$b"
done
chmod +x "$T/bin/"*
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/"*
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
: >"$HUB_LOG"; export J="$SARIF"
PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
grep -q '^devskim analyze --source-code ./B.cs ' "$HUB_LOG" && ok "control: routed devskim runs on the changed .cs file" || bad "control did not run"
! grep -qE '^(detekt|security-scan|security-code-scan) ' "$HUB_LOG" && ok "detekt and security-code-scan stubs are never run" || bad "not-routed tool ran: $(cat "$HUB_LOG")"
! grep -qiE 'detekt|security-?code-?scan|security-scan' "$T/err" && ! jq -e 'any(.[]; (.tool // "") | test("detekt|security-code-scan|security-scan"))' "$T/out" >/dev/null && ok "no row, no NOT CHECKED line for them" || bad "unexpected mention"
exit $fail
