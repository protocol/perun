#!/usr/bin/env bash
# review_checks.sh hygiene tier + zizmor primary-location row. Shims on a hermetic PATH print canned scanner JSON, so no real scanner runs.
# 1) trivy LOW, hadolint info/style and listed checkov ids leave the findings by default (one stderr count line); --hygiene keeps them.
# 2) a zizmor finding lists a Related span (the enclosing job, a line above) before the Primary one: the row must sit on the Primary line.
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hyg.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
t() { local d=$1 o; shift; if o=$("$@" 2>&1); then echo "ok - $d"; else echo "FAIL - $d"; fail=1; [ -z "$o" ] || printf '%s\n' "$o" | sed 's/^/    /'; fi; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= REVIEW_TRIVY_CACHE="$T/tc"
mkdir -p "$T/repo" "$T/bin" "$T/sys" "$T/tc/db" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
mkdir -p .github/workflows && printf 'name: x\non: push\njobs:\n  a:\n    permissions: write-all\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n' >.github/workflows/ci.yml
printf 'FROM alpine\n' >Dockerfile
G add . && G commit -q -m files
sh() { printf '#!/usr/bin/env bash\ncat <<'"'"'J'"'"'\n%s\nJ\nexit %s\n' "$2" "${3:-0}" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
sh zizmor '[{"ident":"excessive-permissions","desc":"d","locations":[{"symbolic":{"key":{"Local":{"verbatim_path":"./.github/workflows/ci.yml"}},"kind":"Related"},"concrete":{"location":{"start_point":{"row":3}}}},{"symbolic":{"key":{"Local":{"verbatim_path":"./.github/workflows/ci.yml"}},"kind":"Primary"},"concrete":{"location":{"start_point":{"row":4}}}}]}]' 13
sh hadolint '[{"file":"./Dockerfile","line":1,"code":"DL3006","level":"warning","message":"keep"},{"file":"./Dockerfile","line":1,"code":"DL3059","level":"info","message":"hide"},{"file":"./Dockerfile","line":1,"code":"DL3000","level":"style","message":"hide"}]'
sh checkov '{"check_type":"dockerfile","results":{"failed_checks":[{"check_id":"CKV_DOCKER_2","check_name":"HEALTHCHECK","file_line_range":[1,1]},{"check_id":"CKV_DOCKER_3","check_name":"user","file_line_range":[1,1]}]}}'
sh trivy '{"Results":[{"Target":"Dockerfile","Misconfigurations":[{"ID":"DS026","Title":"keep","Severity":"HIGH"},{"ID":"DS002","Title":"hide","Severity":"LOW"}]}]}'
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
touch "$T/tc/db/trivy.db"
run() { PATH="$T/bin:$T/sys" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out" || { cat "$T/err" >&2; exit 1; }; }
# shellcheck disable=SC2329
has() { jq -e --arg r "$1" 'any(.[]; .rule==$r)' "$T/out" >/dev/null; }
# shellcheck disable=SC2329
default_hides() { run; ! has DL3059 && ! has DL3000 && ! has CKV_DOCKER_2 && ! has DS002 && has DL3006 && has CKV_DOCKER_3 && has DS026 && grep -q 'review_checks: hygiene: 4 rows hidden (--hygiene shows them)' "$T/err"; }
# shellcheck disable=SC2329
flag_keeps() { run --hygiene; has DL3059 && has DL3000 && has CKV_DOCKER_2 && has DS002 && ! grep -q 'hygiene:' "$T/err"; }
# shellcheck disable=SC2329
zizmor_primary() { run --hygiene; jq -e 'any(.[]; .tool=="zizmor" and .rule=="excessive-permissions" and .line==5)' "$T/out" >/dev/null; }
t "hygiene rows hidden by default, one count line" default_hides
t "--hygiene keeps them" flag_keeps
t "zizmor row sits on the Primary line (5), not the Related job span" zizmor_primary
[ "$fail" = 0 ]
