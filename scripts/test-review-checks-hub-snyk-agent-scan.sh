#!/usr/bin/env bash
# snyk-agent-scan (verified 2026-11-15: Apache-2.0, 0.6.11, needs SNYK_TOKEN and calls the Agent Scan API, can start MCP servers)
# stays route-only: even with a changed .mcp.json, uvx and snyk-agent-scan on PATH, and SNYK_TOKEN set, it is never run and emits no finding rows.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/snyk.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" SNYK_TOKEN=fake-token-example
mkdir -p "$T/repo" "$T/s" "$T/base" "$T/sys" && cd "$T/repo" && : >"$HUB_LOG"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
echo '{}' >.mcp.json; mkdir s1; echo '# s' >s1/SKILL.md; G add . && G commit -q -m f
for t in uvx snyk-agent-scan; do printf '#!/bin/sh\necho "%s $*" >>"$HUB_LOG"\necho '"'"'{"scan_path_responses":[{"issues":[{"code":"E001","message":"m"}]}]}'"'"'\n' "$t" >"$T/s/$t"; chmod +x "$T/s/$t"; done
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"; chmod +x "$T/base/"*
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
PATH="$T/s:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
[ ! -s "$HUB_LOG" ] && ok "uvx and snyk-agent-scan never invoked" || bad "uvx and snyk-agent-scan never invoked"
jq -e 'all(.[]; .tool!="snyk-agent-scan" or .rule=="not-checked")' "$T/out" >/dev/null && ok "no finding rows" || bad "no finding rows"
grep -q '^NOT CHECKED: snyk-agent-scan (unverified' "$T/err" && ok "reported NOT CHECKED" || bad "reported NOT CHECKED"
exit $fail
