#!/usr/bin/env bash
# pipefail_sigpipe.py: positives (multi-write producer into grep -q/-m/head in a condition under pipefail), decoys that must stay quiet,
# and the review_checks.sh pipefail-sigpipe step. Offline, hermetic temp dir.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.claude/skills/deep-code-review/scripts/pipefail_sigpipe.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/dcr-pipefail.XXXXXX")"; trap 'rm -rf "$T"' EXIT
pass=0 fail=0
# row <body-line>: run the check on a one-line pipefail script; print its stdout
row() { printf '#!/usr/bin/env bash\nset -euo pipefail\n%s\n' "$1" >"$T/t.sh"; [ -f "$PY" ] && python3 -I "$PY" <<<"$T/t.sh" 2>/dev/null; }
pos() { if row "$2" | grep -q "pipefail-sigpipe"; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL positive: $1"; fi; }
neg() { if [ -z "$(row "$2")" ] && [ -f "$PY" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL negative: $1"; fi; }
pos ls-files 'if git ls-files | grep -qE "\.sh$"; then echo y; fi'
pos log 'if git log -5 --format=%s | grep -q fix; then echo y; fi'
pos find-head 'if find . -name "*.md" | head -1 | grep -q .; then echo y; fi'
pos cat-and 'cat "$f" | grep -q needle && echo found'
pos curl-or 'curl -s "$u" | grep -qi ok || exit 1'
pos negated 'if ! git diff --name-only | grep -q "^src/"; then echo none; fi'
pos gh-api 'if gh api repos/acme/example/pulls | grep -q open; then echo y; fi'
pos git-branch 'if git branch -a | grep -q main; then echo y; fi'
pos git-diff 'if git diff --name-only | grep -q "^src/"; then echo y; fi'
pos find-grep-q 'if find . -name "*.md" | grep -q README; then echo y; fi'
pos grep-r 'if grep -r needle src | grep -q example.com; then echo y; fi'
pos grep-R-flags 'if grep -rn needle . | head -1 | grep -q x; then echo y; fi'
pos grep-recursive 'if grep --recursive needle . | grep -q x; then echo y; fi'
pos rg-default 'if rg -n PAT . | grep -q x; then :; fi'
pos rg-files 'if rg --files | head -1 >/dev/null; then :; fi'
pos fgrep-r 'if fgrep -r x . | grep -q y; then :; fi'
pos case-arm 'case $t in x) git ls-files | grep -q foo || y= ;; esac'
pos case-arm-w46 "case \$t in mobsfscan) git ls-files | grep -qE '\.(java|kt)\$' || hf= ;; esac"
pos seq 'if seq 1 100000 | grep -q 1; then echo y; fi'
pos zgrep 'if zgrep x f.gz | head -1 | grep -q x; then echo y; fi'
pos ps 'if ps aux | grep -q foo; then echo y; fi'
pos command-wrap 'if command git ls-files | grep -q x; then echo y; fi'
pos env-nice 'if env LC_ALL=C nice -n 5 find . | grep -q x; then echo y; fi'
pos git-C 'if git -C "$d" --no-pager -c a=b log | grep -q x; then echo y; fi'
pos trailing-pipe "$(printf 'if git ls-files |\n  grep -q x; then echo y; fi')"
neg filter-grep 'if grep needle "$f" | grep -q example.com; then echo y; fi'
neg filter-sed 'if sed -n 1p "$f" | grep -q Acme; then echo y; fi'
neg filter-cut 'if cut -d, -f1 "$f" | grep -q Acme; then echo y; fi'
neg filter-sort 'while sort "$f" | grep -q dup; do break; done'
neg filter-jq 'if jq -r ".[]" "$f" | grep -m1 -q x; then echo y; fi'
neg filter-wc 'if wc -l "$f" | grep -q 0; then echo y; fi'
neg filter-awk 'if awk "{print}" "$f" | head -1 | grep -q x; then echo y; fi'
neg cat-stdin 'if cat | grep -q x; then echo y; fi'
neg here-string 'if grep -q needle <<<"$(git ls-files)"; then echo y; fi'
neg echo 'if echo "$x" | grep -q needle; then echo y; fi'
neg printf 'if printf "%s\n" "$x" | grep -q needle; then echo y; fi'
neg or-true 'git ls-files | grep -q x || true'
neg pipestatus 'if git ls-files | grep -q x; [ "${PIPESTATUS[0]}" -ne 0 ]; then echo y; fi'
neg in-subst 'v="$(git log | head -1)"; if [ "$v" = x ]; then echo y; fi'
neg marker 'if git ls-files | grep -q x; then echo y; fi # sigpipe-ok'
neg trailing-pipe-echo "$(printf 'if echo x |\n  grep -q x; then echo y; fi')"
neg set-plus 'set +o pipefail; if git ls-files | grep -q x; then echo y; fi'
neg heredoc "$(printf 'cat <<EOF\nif git ls-files | grep -q x; then :; fi\nEOF')"
neg no-condition 'git ls-files | grep -q x'
neg rev-parse 'if git rev-parse HEAD | grep -q abc; then echo y; fi'
neg grep-not-q 'if git ls-files | grep -c x; then echo y; fi'
# `set -e -o pipefail` (split options) counts as pipefail
printf '#!/usr/bin/env bash\nset -e -o pipefail\nif git ls-files | grep -q x; then :; fi\n' >"$T/s.sh"
if python3 -I "$PY" <<<"$T/s.sh" 2>/dev/null | grep -q pipefail-sigpipe; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL positive: set -e -o pipefail"; fi
# no pipefail set: nothing flagged
printf '#!/bin/sh\nif git ls-files | grep -q x; then :; fi\n' >"$T/n.sh"
if [ -z "$(python3 -I "$PY" <<<"$T/n.sh" 2>/dev/null)" ] && [ -f "$PY" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL negative: no pipefail"; fi
# review_checks.sh step: a changed .sh with the pattern yields a pipefail-sigpipe row
R="$T/repo"; mkdir -p "$R"; (
  cd "$R" && git init -q -b main && git -c user.email=a@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
  printf '#!/usr/bin/env bash\nset -euo pipefail\nif git ls-files | grep -q x; then :; fi\n' >a.sh && git add a.sh && git -c user.email=a@example.com -c user.name=t commit -q -m a
)
out="$(cd "$R" && bash "$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh" --base base 2>/dev/null)"
if grep -q '"tool": *"pipefail-sigpipe"' <<<"$out"; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL review_checks step row"; fi
echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
