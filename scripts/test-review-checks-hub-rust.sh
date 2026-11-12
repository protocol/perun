#!/usr/bin/env bash
# review_checks.sh hub routing for cargo-deny and cargo-audit (Rust, offline, local advisory DB only) with stub binaries on a hermetic PATH
# (no real tool, no network): error diagnostics and advisories land as rows on Cargo.lock, a missing tool, cargo or local DB is "NOT CHECKED",
# and a crash, empty or whitespace output, an exit 1 with no finding, or wrong-shape output is "not run" (never clean).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubrs.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" CARGO_HOME="$T/ch"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/ch/advisory-db" "$T/ch/advisory-dbs" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf '# lock\n' >Cargo.lock; G add . && G commit -q -m lock
cat >"$T/bin/cargo-deny" <<'S'
#!/usr/bin/env bash
echo "cargo-deny $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_deny"
exit "${DENY_RC:-2}"
S
cat >"$T/bin/cargo-audit" <<'S'
#!/usr/bin/env bash
echo "cargo-audit $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_audit"
exit "${AUDIT_RC:-1}"
S
printf '#!/bin/sh\nexit 0\n' >"$T/bin/cargo"; chmod +x "$T/bin/cargo-deny" "$T/bin/cargo-audit" "$T/bin/cargo"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
export J_deny='{"type":"diagnostic","fields":{"code":"banned","message":"crate foo = 1.0.0 is explicitly banned","severity":"error","labels":[]}}
{"type":"diagnostic","fields":{"code":"duplicate","message":"found 2 duplicate entries for crate bar","severity":"warning"}}
{"type":"diagnostic","fields":{"code":"vulnerability","message":"RUSTSEC-2099-0001 in baz","severity":"error"}}'
export J_audit='{"database":{"advisory-count":1},"lockfile":{"dependency-count":3},"vulnerabilities":{"found":true,"count":1,"list":[{"advisory":{"id":"RUSTSEC-2099-0001","title":"Memory unsafety in baz"},"package":{"name":"baz","version":"0.1.0"}}]},"warnings":{}}'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg r "$2" 'any(.[]; .tool==$t and .file=="Cargo.lock" and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row cargo-deny banned && row cargo-deny vulnerability && ! row cargo-deny duplicate && ok "cargo-deny: error diagnostics are rows on Cargo.lock, warnings dropped" || bad "deny rows: $(jq -c '[.[]|select(.tool=="cargo-deny")|.rule]' "$T/out")"
row cargo-audit RUSTSEC-2099-0001 && ok "cargo-audit: advisory row on Cargo.lock" || bad "audit rows"
grep -qx 'cargo-deny --offline --format json check bans licenses sources advisories' "$HUB_LOG" && [ "$(grep -c ^cargo-deny "$HUB_LOG")" = 1 ] && ok "cargo-deny offline, one call, advisories with a local DB" || bad "deny argv: $(cat "$HUB_LOG")"
grep -qx "cargo-audit audit --no-fetch --stale --json --file Cargo.lock --db $T/ch/advisory-db" "$HUB_LOG" && ok "cargo-audit --no-fetch --stale --json on the local DB" || bad "audit argv"
ran cargo-deny && ran cargo-audit && ok "both ran" || bad "ran list"
# no advisory-dbs: cargo-deny skips the advisories check; no advisory-db: cargo-audit is NOT CHECKED
rmdir "$T/ch/advisory-dbs"; : >"$HUB_LOG"; run
grep -qx 'cargo-deny --offline --format json check bans licenses sources' "$HUB_LOG" && ok "cargo-deny: no local advisory DB, no advisories check" || bad "deny no-db argv"
rmdir "$T/ch/advisory-db"; run
grep -q 'NOT CHECKED: cargo-audit (no local advisory DB' "$T/err" && jq -e 'any(.[]; .tool=="cargo-audit" and .rule=="not-checked")' "$T/out" >/dev/null && ok "no local advisory-db: cargo-audit NOT CHECKED" || bad "audit db gate"
mkdir "$T/ch/advisory-db" "$T/ch/advisory-dbs"
# never clean: empty, whitespace, exit 1 with no finding, wrong shape, text, a crash
DENY_RC=0 J_deny= AUDIT_RC=0 J_audit= run
notrun cargo-deny && notrun cargo-audit && ok "empty output: not run" || bad "empty"
DENY_RC=0 J_deny=$' \n\t\n' AUDIT_RC=0 J_audit=$' \n' run
notrun cargo-deny && notrun cargo-audit && ok "whitespace-only output: not run" || bad "whitespace"
DENY_RC=1 J_deny='{"type":"summary","fields":{}}' AUDIT_RC=1 J_audit='{"vulnerabilities":{"found":false,"count":0,"list":[]}}' run
notrun cargo-deny && notrun cargo-audit && ok "exit 1 with no finding: not run" || bad "exit 1 no row"
DENY_RC=0 J_deny='{"type":"summary","fields":{}}' AUDIT_RC=0 J_audit='{"vulnerabilities":{"found":false,"count":0,"list":[]}}' run
ran cargo-deny && ran cargo-audit && ! grep -q 'not run: cargo-' "$T/err" && ok "exit 0 with a typed stream / empty list: clean, ran" || bad "clean"
# a real clean cargo-deny run ends with a text summary line (stderr is merged); a bracketed stderr log line may precede the JSON
DENY_RC=0 J_deny=$'{"type":"summary","fields":{}}\nadvisories ok, bans ok, licenses ok, sources ok\n' AUDIT_RC=0 J_audit=$'[INFO] scanning Cargo.lock\n{"vulnerabilities":{"found":false,"count":0,"list":[]}}' run
ran cargo-deny && ran cargo-audit && ! grep -q 'not run: cargo-' "$T/err" && ok "trailing ok-summary line and a leading bracketed log line: clean, ran" || bad "summary/log line"
DENY_RC=2 J_deny=$'[WARN] log\n{"type":"diagnostic","fields":{"code":"banned","message":"m","severity":"error"}}\nbans FAILED\n' run
ran cargo-deny && row cargo-deny banned && ok "cargo-deny: text lines around diagnostics are skipped" || bad "deny text lines"
DENY_RC=0 J_deny=$'bans ok\n' run
ran cargo-deny && ok "cargo-deny: rc0 with only the ok-summary line is clean" || bad "deny ok-only"
AUDIT_RC=1 J_audit='{"vulnerabilities":{"found":true,"count":1,"list":[]}}' run
notrun cargo-audit && ok "cargo-audit: found:true with an empty list: not run" || bad "found/list mismatch"
AUDIT_RC=1 J_audit='{"vulnerabilities":{"found":false,"count":0,"list":[{"advisory":{"id":"X"},"package":{"name":"a"}}]}}' run
notrun cargo-audit && ok "cargo-audit: count 0 with a non-empty list: not run" || bad "count/list mismatch"
DENY_RC=2 J_deny='{"x":1}' AUDIT_RC=1 J_audit='{"x":1}' run
notrun cargo-deny && notrun cargo-audit && ok "wrong-shape JSON: not run" || bad "wrong shape"
DENY_RC=2 J_deny='some text' AUDIT_RC=1 J_audit='some text' run
notrun cargo-deny && notrun cargo-audit && ok "plain text: not run" || bad "text"
HUB_MODE=crash run
notrun cargo-deny && notrun cargo-audit && ok "crash: not run" || bad "crash"
# gates: no cargo, no tool
rm "$T/bin/cargo"; run
grep -q 'NOT CHECKED: cargo-deny (cargo toolchain missing)' "$T/err" && ok "no cargo: cargo-deny NOT CHECKED" || bad "cargo gate"
rm "$T/bin/cargo-deny" "$T/bin/cargo-audit"; run
grep -q 'NOT CHECKED: cargo-deny (install: cargo install cargo-deny --locked)' "$T/err" && grep -q 'NOT CHECKED: cargo-audit (install: cargo install cargo-audit --locked)' "$T/err" && jq -e 'any(.[]; .tool=="cargo-audit" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tool"
# no Cargo.lock in the diff: not routed
git rm -q Cargo.lock && G commit -q -m nolock; run
! grep -q 'cargo-deny\|cargo-audit' "$T/err" && ok "no Cargo.lock: not routed" || bad "no lock"
exit $fail
