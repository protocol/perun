#!/usr/bin/env bash
# review_checks.sh: eslint-security, psalm and (with a project config) ansible-lint execute project code (eslint.config.js and the repo-local
# eslint binary, psalm.xml plugins and autoloader, ansible-lint rulesdir rules), so without REVIEW_TEST_CMD each is "NOT CHECKED" and never
# started, in a diff review and in a --full audit alike. This covers what the diff-only config guards miss: a committed node_modules/.bin/eslint
# (node_modules is outside the hub's file list) and an ansible-lint config at .config/ansible-lint.yml. ansible-lint with no project config
# still runs; with REVIEW_TEST_CMD set every tool runs as before. Stub binaries on a hermetic PATH (no real tool, no network).
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/lintgate.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN='' TMPDIR="$T/tmp" HOME="$T/home"
unset REVIEW_TEST_CMD
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf "module.exports = [require('eslint-plugin-security').configs.recommended];\n" >eslint.config.js; printf '{}\n' >package.json; printf '<psalm/>\n' >psalm.xml
G add . && G commit -q -m base && git branch base
# the PR under review commits its own eslint "binary" next to an ordinary JS, PHP and Ansible change
mkdir -p node_modules/.bin playbooks; printf 'eval(x);\n' >app.js; printf '<?php\n' >x.php; printf -- '- hosts: all\n  tasks:\n    - ping:\n' >playbooks/site.yml
printf '#!/usr/bin/env bash\necho "eslint $*" >>"$HUB_LOG"\necho "[]"\n' >node_modules/.bin/eslint; chmod +x node_modules/.bin/eslint
G add -f . && G commit -q -m pr
printf '#!/usr/bin/env bash\necho "psalm $*" >>"$HUB_LOG"\necho "[]"\n' >"$T/bin/psalm"
printf '#!/usr/bin/env bash\necho "ansible-lint $*" >>"$HUB_LOG"\necho %s\n' "'{\"version\":\"2.1.0\",\"runs\":[{\"results\":[]}]}'" >"$T/bin/ansible-lint"
chmod +x "$T/bin/psalm" "$T/bin/ansible-lint"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { : >"$HUB_LOG"; PATH="$T/bin:$T/base:$T/sys" bash "$RC" "$@" 2>"$T/err" >"$T/out"; }
started() { grep -q "^$1 " "$HUB_LOG"; }
gated() { grep -q "NOT CHECKED: $1 (it executes project code" "$T/err" && jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked")' "$T/out" >/dev/null; }

for mode in "--base base" --full; do
  # shellcheck disable=SC2086 # the mode is two words on purpose
  run $mode
  ! started eslint && gated eslint-security && ok "$mode: a committed node_modules/.bin/eslint is never started" || bad "$mode eslint: $(cat "$HUB_LOG")"
  ! started psalm && gated psalm && ok "$mode: psalm (psalm.xml plugins and autoloader) is NOT CHECKED" || bad "$mode psalm: $(cat "$HUB_LOG")"
  started ansible-lint && ok "$mode: ansible-lint with no project config still runs" || bad "$mode ansible-lint baseline: $(cat "$T/err" | tail -n 3)"
done

# an ansible-lint config at .config/ansible-lint.yml (a documented location the diff guard does not match) can load Python rules
mkdir -p .config rules; printf 'rulesdir:\n  - ./rules\n' >.config/ansible-lint.yml; printf 'x = 1\n' >rules/r.py; G add . && G commit -q -m cfg
run --base base
! started ansible-lint && gated ansible-lint && ok ".config/ansible-lint.yml: ansible-lint is NOT CHECKED" || bad "ansible-lint config: $(cat "$HUB_LOG")"

REVIEW_TEST_CMD=true run --base base
started eslint && started psalm && started ansible-lint && ok "REVIEW_TEST_CMD set: all three run" || bad "opt-in: $(cat "$HUB_LOG")"
exit "$fail"
