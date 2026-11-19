#!/usr/bin/env bash
# review_checks.sh runs from the repo root, and `python3 -`, `-c` and `-m` put the working directory first on sys.path, so a committed
# json.py or pyflakes.py would shadow the stdlib or the linter and run with the operator's env. Every inline python3 call in the hub is
# isolated (-I; the pyflakes probe drops the cwd entry from sys.path itself, to keep site-packages on any Python 3): planted modules never run in a diff review or a --full audit.
# Stub scanners on a hermetic PATH with no ruff or pyflakes binary (no real tool, no network). REVIEW_CHECKS=<path> runs another copy
# (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/pyiso.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN='' TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/base" "$T/sys" "$T/tmp" "$T/home" "$T/hit" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
# each planted module leaves a marker named after itself when imported or run
for m in json pyflakes shlex hashlib pathlib; do printf 'open("%s/%s", "w").close()\n' "$T/hit" "$m" >"$m.py"; done
printf 'print(1)\n' >app.py; G add . && G commit -q -m planted
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
hits() { ls "$T/hit"; }

# positive control: the plant works on this python, so silence below means isolation, not a dead plant
python3 -c 'import json' && [ -e "$T/hit/json" ] && ok "control: a bare python3 -c in the repo imports the planted json.py" || bad "control: plant did not run"
rm -f -- "$T/hit/json"

for mode in "--base base" --full; do
  # shellcheck disable=SC2086 # mode is two words on purpose
  PATH="$T/base:$T/sys" bash "$RC" $mode 2>"$T/err" >"$T/out" || true
  [ -z "$(hits)" ] && ok "$mode: no planted module ran" || bad "$mode: planted modules ran: $(hits | tr '\n' ' ')"
  jq -e 'type == "array"' "$T/out" >/dev/null && ok "$mode: the closing step still wrote the JSON report" || bad "$mode: no JSON report: $(tail -n3 "$T/err")"
  # the sites ran: py_compile (-c), semgrep's JSON through sjson (-), the pyflakes probe (-c) finding no linter
  grep -qE 'analyzers ran: py_compile, .*semgrep' "$T/err" && grep -qF 'not run: ruff/pyflakes (not installed)' "$T/err" \
    && ok "$mode: py_compile, sjson and the pyflakes probe ran" || bad "$mode: a python site did not run: $(grep 'analyzers ran\|ruff/pyflakes' "$T/err")"
  rm -f -- "$T"/hit/*
done

# every inline python3 call (-, -c, -m) in the hub is isolated; a script path (python3 "$here/x.py") puts only its own directory first
grep -nE 'python3( +-[A-Za-z]+)* +(-c|-m|-)( |$)' "$RC" | grep -vE "python3( +-[A-Za-z]+)* +-[A-Za-z]*[IP]|python3 -c 'import sys; sys\\.path\\[:\\] = \\[p for p in sys\\.path if p\\]; " >"$T/raw" || true
[ ! -s "$T/raw" ] && ok "every inline python3 call in the hub has -I or -P or first drops the cwd entry" || bad "unisolated python3 calls: $(cat "$T/raw")"
exit "$fail"
