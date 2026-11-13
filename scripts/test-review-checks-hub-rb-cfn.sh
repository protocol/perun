#!/usr/bin/env bash
# review_checks.sh routes bundler-audit (Gemfile.lock vs a LOCAL ruby-advisory-db only) and cfn-lint (CloudFormation templates, JSON) through the tool hub.
# Stub binaries only: no install, no network. Never clean on empty output, wrong shape, a bad exit or a crash.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubrbcfn.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
unset BUNDLER_AUDIT_DB # the caller env must not decide the no-db case
mkdir -p "$T/repo" "$T/bin" "$T/keep" "$T/base" "$T/sys" "$T/tmp" "$T/home" "$T/db" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p app
printf 'GEM\n  specs:\n    rack (2.0.0)\n' >app/Gemfile.lock
printf 'AWSTemplateFormatVersion: "2010-09-09"\nResources: {}\n' >stack.yaml
printf 'name: not-cloudformation\n' >other.yaml
G add . && G commit -q -m code
cat >"$T/bin/bundle-audit" <<'S'
#!/usr/bin/env bash
echo "bundle-audit $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_ba"; exit "${BA_RC:-1}"
S
cat >"$T/bin/cfn-lint" <<'S'
#!/usr/bin/env bash
echo "cfn-lint $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_cfn"; exit "${CFN_RC:-2}"
S
chmod +x "$T/bin/"*; cp "$T/bin/"* "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
BA='{"version":"0.9.2","created_at":"2026-01-01 00:00:00 UTC","results":[{"type":"unpatched_gem","gem":{"name":"rack","version":"2.0.0"},"advisory":{"id":"CVE-2000-0001","title":"Demo issue","criticality":"high"}},{"type":"insecure_source","source":"http://rubygems.org/"}]}'
BAC='{"version":"0.9.2","created_at":"x","results":[]}'
CFN='[{"Filename":"stack.yaml","Id":"1","Level":"Error","Location":{"Start":{"ColumnNumber":1,"LineNumber":2},"End":{"ColumnNumber":2,"LineNumber":2},"Path":null},"Message":"bad","ParentId":null,"Rule":{"Id":"E3002","Description":"d","ShortDescription":"s","Source":"u"}},{"Filename":"stack.yaml","Id":"2","Level":"Informational","Location":{"Start":{"ColumnNumber":1,"LineNumber":1},"End":{"ColumnNumber":2,"LineNumber":1},"Path":null},"Message":"fyi","ParentId":null,"Rule":{"Id":"I3011","Description":"d","ShortDescription":"s","Source":"u"}}]'
export J_ba=$BA J_cfn=$CFN
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
# no local advisory db: bundler-audit would download one, so it is NOT CHECKED and never run
: >"$HUB_LOG"; run
grep -q 'NOT CHECKED: bundler-audit (no local ruby-advisory-db' "$T/err" && ! grep -q '^bundle-audit ' "$HUB_LOG" && ok "bundler-audit: no local db, NOT CHECKED, stub never run" || bad "no-db"
# an empty BUNDLER_AUDIT_DB gates alone: a populated default db must not let the run through on the unchecked env path
mkdir -p "$T/emptydb" "$HOME/.local/share/ruby-advisory-db"; printf 'x\n' >"$HOME/.local/share/ruby-advisory-db/advisory"
: >"$HUB_LOG"; BUNDLER_AUDIT_DB="$T/emptydb" run
grep -q 'NOT CHECKED: bundler-audit (no local ruby-advisory-db' "$T/err" && ! grep -q '^bundle-audit ' "$HUB_LOG" && ok "bundler-audit: empty BUNDLER_AUDIT_DB, NOT CHECKED even with a default db" || bad "empty env db"
rm -r "$HOME/.local/share/ruby-advisory-db"
# cfn-lint runs regardless; only the CloudFormation template is passed
row cfn-lint stack.yaml E3002 && ! row cfn-lint stack.yaml I3011 && grep -q '^cfn-lint --format json -- ./stack.yaml$' "$HUB_LOG" && ok "cfn-lint: Error row, Informational dropped, only the template passed" || bad "cfn rows: $(cat "$HUB_LOG")"
# a local db (env override) lets bundler-audit run: rows on the lockfile
printf 'x\n' >"$T/db/advisory"; export BUNDLER_AUDIT_DB="$T/db"
: >"$HUB_LOG"; run
row bundler-audit app/Gemfile.lock CVE-2000-0001 && row bundler-audit app/Gemfile.lock insecure-source && grep -q '^bundle-audit check ./app --gemfile-lock Gemfile.lock --format json$' "$HUB_LOG" && ok "bundler-audit: unpatched gem and insecure source rows, no --update" || bad "ba rows: $(cat "$HUB_LOG") $(grep -i bundler "$T/err")"
J_ba=$BAC BA_RC=0 run
ran bundler-audit && ! jq -e 'any(.[]; .tool=="bundler-audit")' "$T/out" >/dev/null && ok "bundler-audit clean: ran, no rows" || bad "ba clean"
# never clean: empty, wrong shape, exit/rows mismatch, crash
J_ba= J_cfn= run
notrun bundler-audit && notrun cfn-lint && ok "empty output: not run" || bad "empty"
J_ba='{"results":[{"type":"unpatched_gem"}]}' J_cfn='{"x":1}' run
notrun bundler-audit && notrun cfn-lint && ok "wrong shape: not run" || bad "wrong shape"
J_ba=$BAC BA_RC=1 CFN_RC=1 run
notrun bundler-audit && notrun cfn-lint && ok "exit 1 with a clean report, or a crash exit for cfn-lint: not run" || bad "exit"
J_ba=$BA BA_RC=0 run
notrun bundler-audit && ok "rows with exit 0: not run" || bad "ba rc0 rows"
HUB_MODE=crash run
notrun bundler-audit && notrun cfn-lint && ok "crash: not run" || bad "crash"
rm "$T/bin/"*; run
for t in bundler-audit cfn-lint; do
  grep -q "NOT CHECKED: $t (install: " "$T/err" && jq -e --arg t $t 'any(.[]; .tool==$t and .rule=="not-checked")' "$T/out" >/dev/null && ok "$t missing: NOT CHECKED with install hint" || bad "$t missing"
done
exit $fail
