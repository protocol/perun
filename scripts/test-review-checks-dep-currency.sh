#!/usr/bin/env bash
# Tests for review_checks.sh's built-in dep-currency step (dependency_currency.py): with every registry unreachable (HTTPS proxy on a
# closed port) a changed lockfile gives a not-checked "NOT RUN" row per package and never a clean one; a repo with no manifest gets no
# dep-currency row; a missing script gives one not-checked row; the step is listed under "analyzers ran". Hermetic: temp git repo,
# pruned PATH, fictional data, no network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcdc.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
mkdir "$T/bin" "$T/nodc" "$T/repo"
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc sleep timeout mkdir paste sort uniq cut awk find ls date id uname xargs; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
cp "$RC" "$T/nodc/review_checks.sh"  # no dependency_currency.py beside it
cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m empty
git branch base
echo '{"lockfileVersion":3,"packages":{"":{},"node_modules/fict-npm":{"version":"1.0.0","resolved":"https://r.example.com/x.tgz"}}}' >package-lock.json
printf 'FROM scratch\n' >Dockerfile
printf 'runs:\n  using: composite\n  steps:\n    - uses: acme/fict-action@v3\n' >action.yml
printf 'services:\n  a:\n    image: node:18\n' >docker-compose.yml
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export PERUN_HEAVY_DIR="$T/heavy" HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9
PATH="$T/bin" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
jq -e '[.[] | select(.tool=="dep-currency" and .file=="package-lock.json")] | length == 1 and .[0].rule=="not-checked" and (.[0].message|contains("NOT RUN")) and (.[0].message|contains("fict-npm"))' "$T/out" >/dev/null && ok "unreachable registry gives a NOT RUN row, not a clean one" || bad "unreachable row: $(jq -c '[.[]|select(.tool=="dep-currency")]' "$T/out")"
jq -e '[.[] | select(.tool=="dep-currency" and (.file=="action.yml" or .file=="docker-compose.yml") and .rule=="not-checked")] | length == 2' "$T/out" >/dev/null && ok "action.yml and compose files trigger the step" || bad "action.yml/compose trigger: $(jq -c '[.[]|select(.tool=="dep-currency")]' "$T/out")"
jq -e 'all(.[] | select(.tool=="dep-currency"); .rule != "current" and .rule != "outdated")' "$T/out" >/dev/null && ok "no outdated or current claim without a lookup" || bad "claim without lookup"
grep -Eq 'analyzers ran:.* dep-currency' "$T/err" && ok "listed under analyzers ran" || bad "analyzers ran"
git checkout -q -b noman && git rm -q package-lock.json Dockerfile action.yml docker-compose.yml && git -c user.email=t@example.com -c user.name=t commit -q -m rm && echo hi >readme.txt && git add . && git -c user.email=t@example.com -c user.name=t commit -q -m readme
PATH="$T/bin" bash "$RC" --base base 2>"$T/err1" >"$T/out1" || true
jq -e 'any(.[]; .tool=="dep-currency") | not' "$T/out1" >/dev/null && ok "no manifest in the diff: no dep-currency row" || bad "unexpected row"
git checkout -q master 2>/dev/null || git checkout -q main
PATH="$T/bin" bash "$T/nodc/review_checks.sh" --base base 2>"$T/err2" >"$T/out2" || true
jq -e '[.[] | select(.tool=="dep-currency")] | length == 1 and .[0].rule=="not-checked" and (.[0].message|contains("dependency_currency.py missing"))' "$T/out2" >/dev/null && ok "script missing gives one not-checked row" || bad "missing-script row"
exit $fail
