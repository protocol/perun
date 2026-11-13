#!/usr/bin/env bash
# review_checks.sh routes rubocop (Security cops, built-in default config) through the tool hub. Stub binary only: no install, no network.
# Never clean on empty output, wrong shape, summary/list disagreement, a skipped file, a bad exit or a crash.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubrubocop.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p app
printf 'eval(params[:x])\n' >app/a.rb
printf 'puts 1\n' >app/b.rb
printf 'plain text\n' >notes.txt
G add . && G commit -q -m code
cat >"$T/bin/rubocop" <<'S'
#!/usr/bin/env bash
echo "rubocop $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_rc"; exit "${RC_RC:-1}"
S
chmod +x "$T/bin/rubocop"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
off='{"severity":"warning","message":"The use of Kernel#eval is a serious security risk.","cop_name":"Security/Eval","corrected":false,"correctable":false,"location":{"start_line":1,"start_column":1,"last_line":1,"last_column":5,"length":4,"line":1,"column":1}}'
RB="{\"metadata\":{\"rubocop_version\":\"1.0\"},\"files\":[{\"path\":\"app/a.rb\",\"offenses\":[$off]},{\"path\":\"app/b.rb\",\"offenses\":[]}],\"summary\":{\"offense_count\":1,\"target_file_count\":2,\"inspected_file_count\":2}}"
RBC='{"metadata":{},"files":[{"path":"app/a.rb","offenses":[]},{"path":"app/b.rb","offenses":[]}],"summary":{"offense_count":0,"target_file_count":2,"inspected_file_count":2}}'
RB1='{"metadata":{},"files":[{"path":"app/a.rb","offenses":[]}],"summary":{"offense_count":0,"target_file_count":1,"inspected_file_count":1}}'
RBM=${RBC/\"offense_count\":0/\"offense_count\":3}
export J_rc=$RB
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row rubocop app/a.rb Security/Eval && grep -q '^rubocop --force-default-config --only Security --format json --cache false -- ./app/a.rb ./app/b.rb$' "$HUB_LOG" && ! grep -q notes.txt "$HUB_LOG" && ok "rubocop: Security row, default config, only Ruby files passed" || bad "rows: $(cat "$HUB_LOG") $(grep -i rubocop "$T/err")"
J_rc=$RBC RC_RC=0 run
ran rubocop && ! jq -e 'any(.[]; .tool=="rubocop")' "$T/out" >/dev/null && ok "rubocop clean: ran, no rows" || bad "clean"
# never clean (each of these failed open before the guards)
J_rc= run; notrun rubocop && ok "empty output: not run" || bad "empty"
J_rc='{"files":[{"path":"app/a.rb"}],"summary":{}}' run; notrun rubocop && ok "wrong shape: not run" || bad "wrong shape"
J_rc=$RBM RC_RC=0 run; notrun rubocop && ok "summary disagrees with list: not run" || bad "summary mismatch"
J_rc=$RB1 RC_RC=0 run; notrun rubocop && ok "one of two changed files not inspected: not run, never clean" || bad "skipped file"
J_rc=$RBC RC_RC=1 run; notrun rubocop && ok "exit 1 with a clean report: not run" || bad "exit1 clean"
J_rc=$RB RC_RC=0 run; notrun rubocop && ok "offenses with exit 0: not run" || bad "rc0 rows"
J_rc=$RB RC_RC=2 run; notrun rubocop && ok "exit 2 (abnormal end): not run" || bad "exit2"
HUB_MODE=crash run; notrun rubocop && ok "crash: not run" || bad "crash"
rm "$T/bin/rubocop"; run
grep -q 'NOT CHECKED: rubocop (install: ' "$T/err" && jq -e 'any(.[]; .tool=="rubocop" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing: NOT CHECKED with install hint" || bad "missing"
exit $fail
