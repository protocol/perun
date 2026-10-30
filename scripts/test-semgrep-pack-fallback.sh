#!/usr/bin/env bash
# review_checks.sh: the semgrep p/default pack (the registry, or the provisioned snapshot standing in for it) does not load. The chunk reruns
# with the bundled rules and the gap is reported ONCE, through one mechanism: the not-run line, the NOT RUN entry and one not-checked row, with the
# fix named (provision_tools.sh --print). The closing "ran X / wired Y" line and review-checks-last.json count semgrep as partial and fixable
# (a snapshot fixes it); there is no second "missing tools" report. Stub semgrep, gitleaks and trivy: hermetic, offline.
# shellcheck disable=SC2015
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SK=$ROOT/.claude/skills/deep-code-review/scripts
T=$(mktemp -d "${TMPDIR:-/tmp}/spf.XXXXXX") && [ -d "$T" ] || exit 1
trap 'rm -rf "$T"' EXIT; fail=0 n=0 pass=0
ok() { n=$((n + 1)); pass=$((pass + 1)); echo "ok - $1"; }; bad() { n=$((n + 1)); fail=1; echo "FAIL - $1"; cat "$LOG" "$T/e"; }
mkdir -p "$T/stub" "$T/tmp" "$T/repo"
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
# SG_MODE: hang = the p/default pack (registry or snapshot) hangs; allhang = every run hangs; ok = nothing fails. Logs "pack:FIRST_FILE" per run.
for a; do [ "${seen:-}" = 1 ] && { first=$a; break; }; [ "$a" = -- ] && seen=1; done
case " $* " in *" p/default "*) tag=registry ;; *p-default.yml*) tag=snapshot ;; *) tag=bundled ;; esac
echo "$tag:$first" >>"$LOG"
[ "$SG_MODE" = allhang ] && exec sleep 30
[ "$SG_MODE" = hang ] && [ "$tag" != bundled ] && exec sleep 30
printf '{"results":[{"path":"%s","start":{"line":2},"check_id":"perun.%s","extra":{"message":"m"}}],"errors":[]}\n' "$first" "$tag"
S
printf '#!/bin/sh\nexit 0\n' >"$T/stub/gitleaks"
cat >"$T/stub/trivy" <<'S'
#!/bin/sh
echo '{"Results":[]}'
S
chmod +x "$T/stub"/*
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 DCR_CACHE_ROOT="$T/cache" DCR_USER_BIN='' LOG="$T/log"
( cd "$T/repo" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base \
  && printf 'x\ny\n' >f000.txt && git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files ) || exit 1
run() { : >"$LOG"; (cd "$T/repo" && SG_MODE=$1 PATH="$T/stub:$PATH" TMPDIR="$T/tmp" bash "$SK/review_checks.sh" --base base --timeout 2 >"$T/o" 2>"$T/e"); } # run MODE
calls() { [ "$(paste -sd' ' "$LOG")" = "$*" ]; }                       # the exact semgrep runs, in order
err() { grep -qF -- "$1" "$T/e"; }                                     # stderr has this text
st() { jq -e "$1" "$T/repo/.git/review-checks-last.json" >/dev/null; } # the record
rows() { jq -e --argjson c "$1" '[.[] | select(.tool=="semgrep" and .rule=="not-checked")] | length == $c' "$T/o" >/dev/null; } # not-checked semgrep rows
once() { # the one report: not-run line (with the fix), one NOT RUN entry, one row naming the fix, the rollup, and no "missing tools" row
  err "review_checks: not run: semgrep p/default pack (timeout 2s); bundled rules only (warm a local snapshot: bash $SK/provision_tools.sh --print)" \
    && err "review_checks: ran 3 / wired 3 scanners; partial: semgrep(bundled-only); fixable: semgrep (run: bash $SK/provision_tools.sh --print)" \
    && st '.not_run == [] and .partial == ["semgrep(bundled-only)"] and .fixable == ["semgrep"]' && ! err 'missing tools:' && rows 1 \
    && [ "$(grep '^review_checks: NOT RUN:' "$T/e" | grep -o 'semgrep p/default pack' | wc -l | tr -d ' ')" = 1 ] \
    && jq -e '[.[] | select(.tool=="semgrep" and .rule=="not-checked" and (.message | contains("provision_tools.sh --print")))] | length == 1' "$T/o" >/dev/null
}

run hang
calls registry:f000.txt bundled:f000.txt && once && ok "cold: the registry pack hangs: bundled rerun, one report naming the fix, partial and fixable" || bad "registry pack hangs"

mkdir -p "$T/cache/dcr-tools/semgrep"; echo 'rules: []' >"$T/cache/dcr-tools/semgrep/p-default.yml"
run ok
calls snapshot:f000.txt && err "review_checks: ran 3 / wired 3 scanners" && ! err 'partial:' && ! err 'fixable:' && st '.partial == [] and .fixable == []' && rows 0 \
  && ok "warm snapshot is the pack: one run, a full run, nothing partial or fixable" || bad "warm snapshot, healthy"

run hang
calls snapshot:f000.txt bundled:f000.txt && once && ok "warm snapshot as the pack fails the same way: one report, bundled rerun, partial and fixable" || bad "snapshot pack hangs"

run allhang
calls snapshot:f000.txt bundled:f000.txt && st '.not_run == ["semgrep"] and .partial == [] and .fixable == []' && ! err 'fixable:' \
  && ok "the bundled rerun hangs too: semgrep is not run, and a snapshot would not fix that" || bad "bundled rerun hangs too"

! grep -q 'p/default pack not loaded' "$SK/review_checks.sh" && ok "no second reporter of the pack gap in review_checks.sh" || bad "second reporter of the pack gap"
echo "Tests: $pass/$n"
[ "$fail" = 0 ]
