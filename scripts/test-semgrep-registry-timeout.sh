#!/usr/bin/env bash
# Regression test (stub semgrep and trivy: hermetic, offline). When the p/default registry pack hangs to the timeout (a proxy that
# denies semgrep.dev) or errors, review_checks.sh reruns that 200-file semgrep chunk with the bundled rules alone and says so:
# `semgrep(bundled-only)` under analyzers ran, `semgrep p/default pack (<why>)` under NOT RUN (never "none") and a not-checked row
# in the JSON, so a bundled-only run cannot read as a full clean, and not as semgrep NOT RUN entirely. Over 200 files the
# fallback sticks to the later chunks only while no registry run has succeeded.
# shellcheck disable=SC2015
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SK=$ROOT/.claude/skills/deep-code-review/scripts
T=$(mktemp -d "${TMPDIR:-/tmp}/srt.XXXXXX") && [ -d "$T" ] || exit 1
trap 'rm -rf "$T"' EXIT; fail=0 n=0 pass=0
ok() { n=$((n + 1)); pass=$((pass + 1)); echo "ok - $1"; }; bad() { n=$((n + 1)); fail=1; echo "FAIL - $1"; cat "$LOG" "$T/e"; jq -c '.[] | select(.tool=="semgrep")' "$T/o"; }
mkdir -p "$T/stub" "$T/tmp"
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
# SG_MODE: hang = the registry pack hangs; late = it hangs only on the chunk that starts at f200.txt; err = it exits 2;
# allhang = every run hangs; ok = nothing fails. Each run logs "registry|bundled:FIRST_FILE" and reports one finding on that file.
for a; do [ "${seen:-}" = 1 ] && { first=$a; break; }; [ "$a" = -- ] && seen=1; done
case " $* " in *" p/default "*) reg=1 tag=registry ;; *) reg=0 tag=bundled ;; esac
echo "$tag:$first" >>"$LOG"
[ "$SG_MODE" = allhang ] && exec sleep 30
[ "$reg$SG_MODE" = 1hang ] && exec sleep 30
[ "$reg$SG_MODE:$first" = 1late:f200.txt ] && exec sleep 30
[ "$reg$SG_MODE" = 1err ] && { echo "Failed to download p/default" >&2; exit 2; }
printf '{"results":[{"path":"%s","start":{"line":2},"check_id":"perun.%s","extra":{"message":"m"}}],"errors":[]}\n' "$first" "$tag"
S
# trivy would dial check.trivy.dev for its check bundle: stub it clean so the run never leaves the machine
cat >"$T/stub/trivy" <<'S'
#!/usr/bin/env bash
echo '{"Results":[]}'
S
chmod +x "$T/stub/semgrep" "$T/stub/trivy"
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 LOG="$T/log"
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # a semgrep snapshot or ~/.local/bin provisioned on the host must not change what this asserts
# mkrepo DIR N: base commit, then a branch adding N two-line files f000.txt, f001.txt, ... (200-file semgrep chunks start at f000, f200, f400)
mkrepo() ( mkdir -p "$1" && cd "$1" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
  seq -f 'f%03g.txt' 0 $(($2 - 1)) | while IFS= read -r f; do printf 'x\ny\n' >"$f"; done
  git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files )
mkrepo "$T/one" 1; mkrepo "$T/many" 401
run() { : >"$LOG"; (cd "$T/$1" && SG_MODE=$2 PATH="$T/stub:$PATH" TMPDIR="$T/tmp" bash "$SK/review_checks.sh" --base base --timeout 2 ${3+"$3"} >"$T/o" 2>"$T/e"); } # run REPO MODE [--full]
calls() { [ "$(paste -sd' ' "$LOG")" = "$*" ]; }                             # the exact semgrep runs, in order
row() { jq -e --arg r "$1" --arg f "$2" --argjson c "${3:-1}" '[.[] | select(.tool=="semgrep" and .rule==$r and .file==$f)] | length == $c' "$T/o" >/dev/null; } # row RULE FILE [COUNT]
err() { grep -qF -- "$1" "$T/e"; }                                           # stderr has this text
nr() { grep '^review_checks: NOT RUN:' "$T/e" | grep -qF -- "$1"; }          # the NOT RUN line has this text
ran() { grep 'analyzers ran:' "$T/e" | grep -qF -- "$1"; }                   # the analyzers-ran line has this text
# degraded WHY: the fallback is reported everywhere (stderr, NOT RUN, analyzers ran, one not-checked row); semgrep itself is not "NOT RUN"
degraded() {
  err "not run: semgrep p/default pack ($1); bundled rules only" && nr "semgrep p/default pack ($1)" && ! nr 'semgrep (' && ! err 'NOT RUN: none' && ran 'semgrep(bundled-only)' \
    && jq -e --arg w "$1" '[.[] | select(.tool=="semgrep" and .rule=="not-checked" and .file=="" and (.message | contains("p/default registry pack not run (" + $w + "); bundled rules only")))] | length == 1' "$T/o" >/dev/null
}

run one hang
calls registry:f000.txt bundled:f000.txt && row perun.bundled f000.txt && row perun.registry f000.txt 0 && degraded 'timeout 2s' \
  && ok "registry pack hangs to the timeout: bundled rerun, degraded row, NOT RUN names the pack" || bad "registry timeout fallback"

run one err
calls registry:f000.txt bundled:f000.txt && row perun.bundled f000.txt && degraded 'exit 2' \
  && ok "registry pack error: same labelling and row" || bad "registry error fallback"

run one allhang
calls registry:f000.txt bundled:f000.txt && err 'not run: semgrep (timeout 2s)' && nr 'semgrep (timeout 2s)' && ! ran semgrep \
  && ok "bundled rerun hangs too: semgrep is NOT RUN entirely" || bad "bundled timeout is NOT RUN"

run one ok
calls registry:f000.txt && row perun.registry f000.txt && ! err 'p/default pack' && ! err 'bundled-only' \
  && jq -e '[.[] | select(.tool=="semgrep" and .rule=="not-checked")] | length == 0' "$T/o" >/dev/null \
  && ok "healthy registry: one run, no label, no degraded row" || bad "healthy run"

# 401 files = chunks starting f000, f200, f400; --full scans them with one gitleaks call, not one per file
run many hang --full
calls registry:f000.txt bundled:f000.txt bundled:f200.txt bundled:f400.txt && row perun.bundled f000.txt && row perun.bundled f200.txt && row perun.bundled f400.txt \
  && degraded 'timeout 2s' && ok "no registry run ever succeeded: the fallback sticks, later chunks skip the pack" || bad "sticky fallback"

run many late --full
calls registry:f000.txt registry:f200.txt bundled:f200.txt registry:f400.txt && row perun.registry f000.txt && row perun.bundled f200.txt && row perun.registry f400.txt \
  && row perun.registry f200.txt 0 && row perun.bundled f400.txt 0 && degraded 'timeout 2s' \
  && ok "a registry run succeeded earlier: only the hung chunk falls back, the next chunk tries the pack again" || bad "non-sticky fallback"
echo "Tests: $pass/$n"
[ "$fail" = 0 ]
