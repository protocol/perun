#!/usr/bin/env bash
# Tests for review_checks.sh's built-in invisible-chars step: NUL, ESC and RLO each give one row with file, line, col and
# codepoint; a clean file and a binary file give none; the step is listed under "analyzers ran". Hermetic: temp git repo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcic.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

mkdir "$T/bin" "$T/repo"
# Pruned PATH: no semgrep, trivy or linters, so the run is offline and only built-in steps fire.
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
git branch base
# Control bytes and RLO are built at run time so this file stays plain ASCII.
printf 'ok = 1\nx = "a\0b"\n' >nul.py
printf 'ok = 1\n\ny = "\033[0m"\n' >esc.txt
printf 'name = "user\xe2\x80\xaeevil"\n' >rlo.js
printf 'clean = 1\n\tindented\r\n\f\n' >clean.py
printf 'a\0\033\xe2\x80\xaeb' >logo.png
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export PERUN_HEAVY_DIR="$T/heavy"
PATH="$T/bin" bash "$RC" --base base 2>"$T/err" >"$T/out" || true

jq -e '[.[] | select(.tool=="invisible-chars")] | length == 3' "$T/out" >/dev/null && ok "3 invisible-chars rows" || bad "row count"
jq -e 'any(.[]; .tool=="invisible-chars" and .file=="nul.py" and .line==2 and .rule=="control-char" and .message=="control character U+0000 at col 7")' "$T/out" >/dev/null && ok "NUL file:line:col codepoint" || bad "NUL row"
jq -e 'any(.[]; .tool=="invisible-chars" and .file=="esc.txt" and .line==3 and .rule=="control-char" and .message=="control character U+001B at col 6")' "$T/out" >/dev/null && ok "ESC file:line:col codepoint" || bad "ESC row"
jq -e 'any(.[]; .tool=="invisible-chars" and .file=="rlo.js" and .line==1 and .rule=="hidden-unicode" and .message=="hidden character U+202E at col 13")' "$T/out" >/dev/null && ok "RLO file:line:col codepoint" || bad "RLO row"
jq -e 'all(.[]; .tool!="invisible-chars" or (.file!="clean.py" and .file!="logo.png"))' "$T/out" >/dev/null && ok "clean and binary files skipped" || bad "clean/binary rows"
grep -Eq 'analyzers ran:.* invisible-chars' "$T/err" && ok "listed under analyzers ran" || bad "analyzers ran"
jq -e 'all(.[]; has("file") and has("line") and has("rule") and has("message") and has("text") and has("tool"))' "$T/out" >/dev/null && ok "existing row shape" || bad "row shape"

[ "$fail" = 0 ]
