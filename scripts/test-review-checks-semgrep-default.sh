#!/usr/bin/env bash
# review_checks.sh with no repo semgrep rules: bundled taint rules + p/default; REVIEW_SEMGREP_REGISTRY=0 drops p/default;
# a failed registry run reruns with the bundled rules alone. Stub semgrep, no network.
set -euo pipefail
RC=${REVIEW_CHECKS:-$(cd "$(dirname "$0")/.." && pwd)/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/sgd.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'rm -rf "$T"' EXIT; fail=0
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # a semgrep snapshot or ~/.local/bin provisioned on the host must not change what this asserts
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
mkdir -p "$T/stub" "$T/repo"
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
echo "semgrep $*" >>"$SG_LOG"
case "$*" in *p/default*) [ -z "${SG_FAIL:-}" ] || exit 2 ;; esac
echo '{"results":[{"path":"app.py","start":{"line":2},"check_id":"perun.py.sqli","extra":{"message":"m"}}],"errors":[]}'
S
chmod +x "$T/stub/semgrep"; export SG_LOG="$T/sg.log" PERUN_HEAVY_DIR="$T/heavy"; : >"$SG_LOG"
cd "$T/repo" || exit 1
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
printf 'x\ny\n' >app.py; git add . && git -c user.email=t@example.com -c user.name=t commit -q -m f
run() { PATH="$T/stub:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
run
[ "$(wc -l <"$SG_LOG")" -eq 1 ] && grep -q 'semgrep-taint --config p/default' "$SG_LOG" && ! grep -q auto "$SG_LOG" && ok "bundled + p/default" || bad "bundled + p/default"
jq -e 'any(.[]; .tool=="semgrep" and .rule=="perun.py.sqli")' "$T/out" >/dev/null && ok "finding reported" || bad "finding reported"
: >"$SG_LOG"; REVIEW_SEMGREP_REGISTRY=0 run
! grep -q p/default "$SG_LOG" && grep -q semgrep-taint "$SG_LOG" && ok "registry opt-out" || bad "registry opt-out"
: >"$SG_LOG"; SG_FAIL=1 run
[ "$(wc -l <"$SG_LOG")" -eq 2 ] && ! tail -1 "$SG_LOG" | grep -q p/default && jq -e 'any(.[]; .tool=="semgrep")' "$T/out" >/dev/null && ok "offline fallback to bundled" || bad "offline fallback"
exit $fail
