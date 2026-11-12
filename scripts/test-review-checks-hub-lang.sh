#!/usr/bin/env bash
# review_checks.sh hub routing for mobsfscan (Android/iOS source) and psalm (PHP taint, local psalm.xml only) with stub binaries on a hermetic PATH
# (no real tool, no network): rows keep ERROR/WARNING rules and taint issues, a missing tool, project marker or config is "NOT CHECKED", and a crash,
# empty or whitespace output, a found/empty exit mismatch, or wrong-shape output is "not run" (never clean). Stubs print trailing log lines like the real tools.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hublang.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; printf '<manifest/>\n' >AndroidManifest.xml; printf '<psalm/>\n' >psalm.xml; G add . && G commit -q -m base && git branch base
printf 'class A\n' >A.kt; printf '<?php\n' >x.php; G add . && G commit -q -m code
cat >"$T/bin/mobsfscan" <<'S'
#!/usr/bin/env bash
echo "mobsfscan $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_mobs"
exit "${MOBS_RC:-1}"
S
cat >"$T/bin/psalm" <<'S'
#!/usr/bin/env bash
echo "psalm $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_psalm"
exit "${PSALM_RC:-2}"
S
chmod +x "$T/bin/mobsfscan" "$T/bin/psalm"; mkdir "$T/keep"; cp "$T/bin/mobsfscan" "$T/bin/psalm" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
MOBS='{
  "results": {
    "android_hardcoded": {"metadata": {"severity": "ERROR", "description": "Hardcoded secret"}, "files": [{"file_path": "./A.kt", "match_lines": [3, 3]}]},
    "android_logging": {"metadata": {"severity": "WARNING", "description": "Logging"}, "files": [{"file_path": "A.kt", "match_lines": [5, 5]}]},
    "android_info": {"metadata": {"severity": "INFO", "description": "note"}, "files": [{"file_path": "A.kt", "match_lines": [1, 1]}]}
  },
  "errors": [],
  "mobsfscan_version": "0.0.0"
}'
LOG=$'\n[INFO] scan done\n'
PSA='[
  {"severity": "error", "line_from": 4, "type": "TaintedHtml", "message": "Detected tainted HTML", "file_name": "x.php", "is_security": true},
  {"severity": "info", "line_from": 2, "type": "MissingReturnType", "message": "no", "file_name": "x.php", "is_security": false}
]'
export J_mobs="$MOBS$LOG" J_psalm=$'[INFO] Scanning files...\n'"$PSA"$'\nChecks took 0.1 seconds\n'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row mobsfscan A.kt android_hardcoded && row mobsfscan A.kt android_logging && ! row mobsfscan A.kt android_info && ok "mobsfscan: ERROR and WARNING rows, INFO dropped, trailing log line skipped" || bad "mobs rows: $(jq -c '[.[]|select(.tool=="mobsfscan")|.rule]' "$T/out")"
row psalm x.php TaintedHtml && ! row psalm x.php MissingReturnType && ok "psalm: taint row, non-security issue dropped, leading and trailing log lines skipped" || bad "psalm rows: $(jq -c '[.[]|select(.tool=="psalm")|.rule]' "$T/out")"
grep -qx 'mobsfscan --json ./A.kt' "$HUB_LOG" && grep -qx 'psalm --taint-analysis --output-format=json --no-cache --no-progress' "$HUB_LOG" && ok "argv: mobsfscan --json on changed files, psalm taint json no cache" || bad "argv: $(cat "$HUB_LOG")"
ran mobsfscan && ran psalm && ok "both ran" || bad "ran list"
# never clean: empty, whitespace, found/empty mismatch, wrong shape, text, errors, a crash
MOBS_RC=0 J_mobs= PSALM_RC=0 J_psalm= run
notrun mobsfscan && notrun psalm && ok "empty output: not run" || bad "empty"
MOBS_RC=0 J_mobs=$' \n\t\n' PSALM_RC=0 J_psalm=$' \n' run
notrun mobsfscan && notrun psalm && ok "whitespace-only output: not run" || bad "whitespace"
MOBS_RC=1 J_mobs='{"results":{},"errors":[]}'$'\n[WARN] x\n' PSALM_RC=2 J_psalm=$'[]\nChecks took 1s\n' run
notrun mobsfscan && notrun psalm && ok "exit says found, report is empty: not run" || bad "found/empty mismatch"
PSALM_RC=0 run
notrun psalm && ok "psalm exit 0 with taint rows: not run" || bad "exit0 with rows"
MOBS_RC=0 J_mobs='{"results":{},"errors":["boom"]}' run
notrun mobsfscan && ok "mobsfscan: errors list non-empty: not run" || bad "mobs errors"
MOBS_RC=1 J_mobs='{"x":1}' PSALM_RC=2 J_psalm='[{"x":1}]' run
notrun mobsfscan && notrun psalm && ok "wrong-shape JSON: not run" || bad "wrong shape"
MOBS_RC=1 J_mobs='some text' PSALM_RC=2 J_psalm='some text' run
notrun mobsfscan && notrun psalm && ok "plain text: not run" || bad "text"
PSALM_RC=1 run
notrun psalm && ok "psalm exit 1 (problem running): not run" || bad "psalm exit 1"
HUB_MODE=crash run
notrun mobsfscan && notrun psalm && ok "crash: not run" || bad "crash"
MOBS_RC=0 J_mobs='{"results":{"android_info":{"metadata":{"severity":"INFO","description":"n"},"files":[{"file_path":"A.kt","match_lines":[1,1]}]}},"errors":[]}'$LOG PSALM_RC=0 J_psalm=$'[INFO] x\n[]\nChecks took 1s\n' run
ran mobsfscan && ran psalm && ! grep -q 'not run: \(mobsfscan\|psalm\)' "$T/err" && ok "exit 0 with INFO-only and an empty list plus log lines: clean, ran" || bad "clean"
# row for a file outside the scanned list: findings may be lost, so mobsfscan is not run
MOBS_RC=1 J_mobs='{"results":{"android_hardcoded":{"metadata":{"severity":"ERROR","description":"d"},"files":[{"file_path":"B.kt","match_lines":[1,1]}]}},"errors":[]}' run
notrun mobsfscan && ! row mobsfscan B.kt android_hardcoded && ok "mobsfscan: a row for an unscanned file: not run" || bad "mobs unscanned file"
# WARNING-only reports: the exit code does not have to be 1 (-w is not used), so exit 0 and exit 1 both keep the rows
MW='{"results":{"android_logging":{"metadata":{"severity":"WARNING","description":"Logging"},"files":[{"file_path":"A.kt","match_lines":[5,5]}]}},"errors":[]}'
MOBS_RC=0 J_mobs=$MW$LOG run
ran mobsfscan && row mobsfscan A.kt android_logging && ok "mobsfscan: exit 0 with only WARNING rows keeps them" || bad "mobs exit0 warning"
MOBS_RC=1 J_mobs=$MW$LOG run
ran mobsfscan && row mobsfscan A.kt android_logging && ok "mobsfscan: exit 1 with only WARNING rows keeps them" || bad "mobs exit1 warning"
# psalm scans the whole project: a report whose rows are all in unchanged files is clean for this diff, not a failure
PSALM_RC=2 J_psalm='[{"severity":"error","line_from":4,"type":"TaintedHtml","message":"m","file_name":"other.php","is_security":true}]' run
ran psalm && ! row psalm other.php TaintedHtml && ! grep -q 'not run: psalm' "$T/err" && ok "psalm: rows only in unchanged files are dropped, not a failure" || bad "psalm unchanged rows"
# gates
rm "$T/bin/mobsfscan" "$T/bin/psalm"; run
grep -q 'NOT CHECKED: mobsfscan (install: pipx install mobsfscan)' "$T/err" && grep -q 'NOT CHECKED: psalm (install: composer global require vimeo/psalm)' "$T/err" && jq -e 'any(.[]; .tool=="psalm" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tool"
cp "$T/keep/mobsfscan" "$T/keep/psalm" "$T/bin/"
# psalm: no psalm.xml, or a diff that changes it (config is code), is NOT CHECKED
G rm -q psalm.xml && G commit -q -m noconf; run
grep -q 'NOT CHECKED: psalm (no psalm.xml at repo root)' "$T/err" && ok "no psalm.xml: NOT CHECKED" || bad "psalm no config"
printf '<psalm a="1"/>\n' >psalm.xml; G add psalm.xml && G commit -q -m conf; run
grep -q 'NOT CHECKED: psalm (psalm.xml or composer.json changed in this diff' "$T/err" && ok "psalm.xml changed in the diff: NOT CHECKED" || bad "psalm config changed"
# mobsfscan: no mobile marker in the repo is not routed
G rm -q AndroidManifest.xml && G commit -q -m nomobile; run
! grep -q 'mobsfscan' "$T/err" && ok "no mobile marker: mobsfscan not routed" || bad "no marker"
# no matching files in the diff: not routed
git reset -q --hard base; printf 'y\n' >README.md; G commit -qam doc; run
! grep -q 'mobsfscan\|psalm' "$T/err" && ok "no .kt or .php in the diff: not routed" || bad "no files"
exit $fail
