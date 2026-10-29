#!/usr/bin/env bash
# Tests for review_checks.sh's invisible-chars step hardening: third_party/, Pods/, bower_components/ and *.min.js are skipped; rows
# under fixture/test paths carry [likely-fixture] (whole directory segments, as for gitleaks); locale files keep only bidi overrides;
# a missing invisible_chars.py gives a not-checked row; a timeout keeps the rows found so far plus a not-checked row. Hermetic: temp git repo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcich.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
REAL_PY=$(command -v python3); export REAL_PY

mkdir "$T/bin" "$T/shim" "$T/noic" "$T/repo"
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc sleep timeout; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
# A python3 stand-in: invisible_chars.py prints one row then hangs; any other script runs for real.
printf '#!/bin/sh\ncase "$1" in *invisible_chars.py) printf "a.txt\\t1\\tcontrol-char\\tcontrol character U+001B at col 1\\n"; exec sleep 8 ;; *) exec "$REAL_PY" "$@" ;; esac\n' >"$T/shim/python3"; chmod +x "$T/shim/python3"
cp "$RC" "$T/noic/review_checks.sh"  # no invisible_chars.py beside it
cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
git branch base
mkdir -p third_party Pods bower_components lib tests/fixtures test-runner src locales
for f in third_party/a.js Pods/b.m bower_components/c.js lib/x.min.js tests/fixtures/f.txt test-runner/y.py src/ok.js src/sample.txt; do printf 'x = "\033[0m"\n' >"$f"; done
printf 'msg = "a\xe2\x80\x8f\xe2\x80\x8bb"\n' >locales/en.json      # RLM + ZWSP only: quiet in a locale file
printf 'msg = "a\xe2\x80\xaeb"\n' >locales/de.json                 # RLO: kept
printf 'msg = "a\xe2\x80\x8fb"\n' >src/rlm.js                      # RLM outside a locale file: kept
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export PERUN_HEAVY_DIR="$T/heavy"
PATH="$T/bin" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
rows() { jq -r '[.[] | select(.tool=="invisible-chars") | .file] | sort | join(" ")' "$T/out"; }

[ "$(rows)" = "locales/de.json src/ok.js src/rlm.js src/sample.txt test-runner/y.py tests/fixtures/f.txt" ] && ok "vendored dirs, *.min.js and quiet locale file skipped" || bad "row files: $(rows)"
jq -e 'all(.[] | select(.tool=="invisible-chars" and (.file|test("^tests/fixtures/|sample.txt$"))); .hint=="likely-fixture" and (.text|endswith(" [likely-fixture]")))' "$T/out" >/dev/null && ok "fixture rows tagged likely-fixture" || bad "fixture tag"
jq -e 'all(.[] | select(.tool=="invisible-chars" and (.file|test("^(src/ok.js|src/rlm.js|test-runner/y.py|locales/de.json)$"))); (has("hint")|not) and (.text|contains("likely-fixture")|not))' "$T/out" >/dev/null && ok "other rows and test-runner/ untagged" || bad "untagged rows"
jq -e 'any(.[]; .file=="locales/de.json" and .rule=="hidden-unicode" and (.message|contains("U+202E")))' "$T/out" >/dev/null && ok "locale RLO kept" || bad "locale RLO"

PATH="$T/bin" bash "$T/noic/review_checks.sh" --base base 2>"$T/err2" >"$T/out2" || true
jq -e '[.[] | select(.tool=="invisible-chars")] | length == 1 and .[0].rule=="not-checked" and .[0].file=="" and (.[0].message|contains("invisible_chars.py missing"))' "$T/out2" >/dev/null && ok "script missing gives one not-checked row" || bad "missing-script row"
grep -q 'not run: invisible-chars' "$T/err2" && ! grep -Eq 'analyzers ran:.* invisible-chars' "$T/err2" && ok "missing script reported on stderr, not listed as ran" || bad "missing-script stderr"

PATH="$T/shim:$T/bin" bash "$RC" --base base --timeout 2 2>"$T/err3" >"$T/out3" || true
jq -e '[.[] | select(.tool=="invisible-chars")] | length == 2 and (map(.rule) | sort == ["control-char","not-checked"]) and any(.[]; .file=="a.txt" and .line==1)' "$T/out3" >/dev/null && ok "timeout keeps rows found so far plus a not-checked row" || bad "timeout rows: $(jq -c '[.[]|select(.tool=="invisible-chars")]' "$T/out3")"

[ "$fail" = 0 ]
