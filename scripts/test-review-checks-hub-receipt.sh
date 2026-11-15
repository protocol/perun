#!/usr/bin/env bash
# review_checks.sh receipt: a diff touching .tf, .py and a Dockerfile with only bandit installed must name checkov and hadolint
# as not installed (NOT CHECKED rows, "skipped (not installed)" in the summary, "not run" in the ran/wired line), never a silent clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubreceipt.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'resource "aws_s3_bucket" "b" {}\n' >main.tf; printf 'print(1)\n' >a.py; printf 'FROM alpine:3.19\n' >Dockerfile
G add . && G commit -q -m code
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"metrics\":{}}'" >"$T/bin/bandit"; chmod +x "$T/bin/bandit"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep xargs; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
PATH="$T/bin:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
for t in checkov hadolint; do
  jq -e --arg t "$t" 'any(.[]; .tool==$t and .rule=="not-checked")' "$T/out" >/dev/null && grep -q "NOT CHECKED: $t (install: " "$T/err" \
    && ok "$t: not-checked row and NOT CHECKED line" || bad "$t receipt"
  grep -qE "skipped \(not installed\):.*\b$t\b" "$T/err" && grep -qE "ran [0-9]+ / wired [0-9]+ scanners; not run:.*\b$t\b" "$T/err" \
    && ok "$t: in skipped and not-run summary" || bad "$t summary"
done
! grep -qiE 'clean|no findings' "$T/err" && ok "no clean verdict while tools did not run" || bad "clean verdict"
exit $fail
