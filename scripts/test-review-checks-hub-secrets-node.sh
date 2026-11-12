#!/usr/bin/env bash
# review_checks.sh hub routing for detect-secrets (changed files, no baseline, no network verification, secret values never printed) and njsscan (Node.js)
# with stub binaries on a hermetic PATH (no real tool, no network): rows keep potential secrets and ERROR/WARNING rules, a missing tool is "NOT CHECKED",
# and a crash, empty or whitespace output, a nonzero detect-secrets exit, an njsscan exit that disagrees with the report, or wrong-shape output is "not run".
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubsn.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'var a\n' >a.js; G add . && G commit -q -m code
cat >"$T/bin/detect-secrets" <<'S'
#!/usr/bin/env bash
echo "detect-secrets $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_ds"
exit "${DS_RC:-0}"
S
cat >"$T/bin/njsscan" <<'S'
#!/usr/bin/env bash
echo "njsscan $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_njs"
exit "${NJS_RC:-1}"
S
chmod +x "$T/bin/detect-secrets" "$T/bin/njsscan"; mkdir "$T/keep"; cp "$T/bin/detect-secrets" "$T/bin/njsscan" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
SECRET_VALUE=hunter2-not-a-real-secret
DS='{
  "version": "1.5.0",
  "plugins_used": [{"name": "KeywordDetector"}],
  "results": {
    "./a.js": [{"type": "Secret Keyword", "filename": "./a.js", "hashed_secret": "HASHPLACEHOLDER", "is_verified": false, "line_number": 7}]
  },
  "generated_at": "2026-11-12T00:00:00Z"
}'
NJS='{
  "errors": [],
  "nodejs": {
    "node_eval": {"files": [{"file_path": "./a.js", "match_position": [1, 9], "match_lines": [3, 3], "match_string": "eval(x)"}], "metadata": {"cwe": "CWE-95", "description": "eval of user input", "severity": "ERROR"}},
    "node_log": {"files": [{"file_path": "a.js", "match_position": [1, 9], "match_lines": [5, 5], "match_string": "log"}], "metadata": {"description": "Logging", "severity": "WARNING"}},
    "node_info": {"files": [{"file_path": "a.js", "match_position": [1, 9], "match_lines": [1, 1], "match_string": "i"}], "metadata": {"description": "note", "severity": "INFO"}}
  },
  "templates": {},
  "njsscan_version": "0.0.0"
}'
LOG=$'\n[INFO] scan done\n'
export J_ds="$LOG$DS" J_njs="$NJS$LOG"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row detect-secrets a.js "Secret Keyword" && ok "detect-secrets: one row per potential secret, leading log line skipped" || bad "ds rows: $(jq -c '[.[]|select(.tool=="detect-secrets")|.rule]' "$T/out")"
! grep -q 'HASHPLACEHOLDER' "$T/out" "$T/err" "$HUB_LOG" && ! grep -q "$SECRET_VALUE" "$T/out" "$T/err" && ok "detect-secrets: the hashed secret never reaches the output" || bad "hash leaked"
row njsscan a.js node_eval && row njsscan a.js node_log && ! row njsscan a.js node_info && ok "njsscan: ERROR and WARNING rows, INFO dropped, trailing log line skipped" || bad "njs rows: $(jq -c '[.[]|select(.tool=="njsscan")|.rule]' "$T/out")"
grep -qE '^detect-secrets scan --no-verify \./a\.js' "$HUB_LOG" && ! grep -q -- '--baseline' "$HUB_LOG" && grep -qx 'njsscan --json ./a.js' "$HUB_LOG" && ok "argv: detect-secrets scan --no-verify on changed files, no baseline; njsscan --json" || bad "argv: $(cat "$HUB_LOG")"
ran detect-secrets && ran njsscan && ok "both ran" || bad "ran list"
# never clean: empty, whitespace, exit mismatch, wrong shape, text, errors, a crash
DS_RC=0 J_ds= NJS_RC=0 J_njs= run
notrun detect-secrets && notrun njsscan && ok "empty output: not run" || bad "empty"
J_ds=$' \n\t\n' J_njs=$' \n' run
notrun detect-secrets && notrun njsscan && ok "whitespace-only output: not run" || bad "whitespace"
DS_RC=1 run
notrun detect-secrets && ok "detect-secrets nonzero exit: not run" || bad "ds exit 1"
NJS_RC=1 J_njs='{"errors":[],"nodejs":{},"templates":{}}'$'\n[WARN] x\n' run
notrun njsscan && ok "njsscan exit 1 with an empty report: not run" || bad "njs found/empty"
NJS_RC=1 J_njs='{"errors":[],"nodejs":{"node_log":{"files":[{"file_path":"a.js","match_lines":[5,5]}],"metadata":{"severity":"WARNING","description":"L"}}},"templates":{}}' run
notrun njsscan && ok "njsscan exit 1 with only WARNING rows: not run (exit 1 needs an ERROR rule)" || bad "njs exit1 warning"
NJS_RC=0 run
notrun njsscan && ok "njsscan exit 0 with an ERROR row: not run" || bad "njs exit0 error"
NJS_RC=0 J_njs='{"errors":[],"nodejs":{"node_log":{"files":[{"file_path":"a.js","match_lines":[5,5]}],"metadata":{"severity":"WARNING","description":"L"}}},"templates":{}}'$LOG run
ran njsscan && row njsscan a.js node_log && ok "njsscan exit 0 with only WARNING rows keeps them" || bad "njs exit0 warning"
NJS_RC=1 J_njs='{"errors":["boom"],"nodejs":{},"templates":{}}' run
notrun njsscan && ok "njsscan: errors list non-empty: not run" || bad "njs errors"
NJS_RC=1 J_njs='{"errors":[],"nodejs":{"r":{"files":[{"file_path":"b.js","match_lines":[1,1]}],"metadata":{"severity":"ERROR","description":"d"}}},"templates":{}}' run
notrun njsscan && ok "njsscan: a row for an unscanned file: not run" || bad "njs unscanned file"
J_ds='{"results":{"./a.js":[{"x":1}]}}' NJS_RC=1 J_njs='{"x":1}' run
notrun detect-secrets && notrun njsscan && ok "wrong-shape JSON: not run" || bad "wrong shape"
J_ds='some text' J_njs='some text' run
notrun detect-secrets && notrun njsscan && ok "plain text: not run" || bad "text"
HUB_MODE=crash run
notrun detect-secrets && notrun njsscan && ok "crash: not run" || bad "crash"
DS_RC=0 J_ds=$'[INFO] x\n{"version":"1","results":{}}\n' NJS_RC=0 J_njs='{"errors":[],"nodejs":{},"templates":{}}'$LOG run
ran detect-secrets && ran njsscan && ! grep -q 'not run: \(detect-secrets\|njsscan\)' "$T/err" && ok "empty results with log lines: clean, ran" || bad "clean"
# gates
rm "$T/bin/detect-secrets" "$T/bin/njsscan"; run
grep -q 'NOT CHECKED: detect-secrets (install: pipx install detect-secrets)' "$T/err" && grep -q 'NOT CHECKED: njsscan (install: pipx install njsscan)' "$T/err" && jq -e 'any(.[]; .tool=="njsscan" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tool"
cp "$T/keep/detect-secrets" "$T/keep/njsscan" "$T/bin/"
# no JS file in the diff: njsscan is not routed, detect-secrets still scans the changed file
git reset -q --hard base; printf 'y\n' >README.md; G commit -qam doc; run
! grep -q 'njsscan' "$T/err" && grep -qE '^detect-secrets scan --no-verify \./README\.md$' "$HUB_LOG" && ok "no .js in the diff: njsscan not routed, detect-secrets scans the changed file" || bad "no js"
exit $fail
