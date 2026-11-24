#!/usr/bin/env bash
# review_checks.sh: codeql is opt-in (REVIEW_CODEQL=1; its license allows OSI-licensed code only), so without the env the stub codeql is
# never run and one not-checked row says why; with it the stub runs. osv-scanner exit 128 (no package sources) is a skipped row with that reason.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/cqopt.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'print(1)\n' >a.py; printf '{}\n' >package-lock.json; G add . && G commit -q -m code
cat >"$T/bin/codeql" <<'S'
#!/usr/bin/env bash
echo "codeql $*" >>"$HUB_LOG"
for a in "$@"; do case $a in --output=*) printf '{"version":"2.1.0","runs":[{"results":[]}]}' >"${a#--output=}" ;; esac; done
exit 0
S
cat >"$T/bin/osv-scanner" <<'S'
#!/usr/bin/env bash
echo "No package sources found" >&2; exit 128
S
chmod +x "$T/bin/codeql" "$T/bin/osv-scanner"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"; chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep seq; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
: >"$HUB_LOG"; run
! grep -q '^codeql' "$HUB_LOG" && jq -e 'any(.[]; .tool=="codeql" and .rule=="not-checked" and (.message|test("off by default \\(license: OSI-licensed code only\\); set REVIEW_CODEQL=1")))' "$T/out" >/dev/null && grep -qF 'NOT CHECKED: codeql (off by default' "$T/err" && ok "codeql off by default: never run, not-checked row and stderr line" || bad "default: $(cat "$HUB_LOG") $(jq -c '[.[]|select(.tool=="codeql")]' "$T/out") $(grep codeql "$T/err")"
: >"$HUB_LOG"; REVIEW_CODEQL=1 run
grep -q '^codeql database create' "$HUB_LOG" && grep -q '^codeql database analyze' "$HUB_LOG" && ok "REVIEW_CODEQL=1: codeql runs" || bad "opt-in: $(cat "$HUB_LOG")"
REVIEW_OSV=1 run
jq -e 'any(.[]; .tool=="osv-scanner" and .rule=="not-checked" and (.message|test("no package sources")))' "$T/out" >/dev/null && grep -q 'not run: osv-scanner (no package sources)' "$T/err" && ok "osv-scanner exit 128: skipped, reason no package sources" || bad "osv128: $(grep osv "$T/err")"
[ "$fail" = 0 ]
