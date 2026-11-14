#!/usr/bin/env bash
# review_checks.sh posture and DAST routes, with stub binaries on a hermetic PATH (no real tool, docker or network):
# opengrep stands in when semgrep is absent; REVIEW_SCORECARD=1 routes scorecard (low checks become rows); REVIEW_DAST_URL routes nuclei and
# zap-baseline.py against a localhost target only. Each case: missing tool = NOT CHECKED, opt-in off = never run, remote target refused,
# findings parsed, crash = not run (never clean).
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/posture.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; [ ! -s "${T:-/x}/err" ] || sed "s/^/  | /" "$T/err" | head -12; [ ! -s "$T/out" ] || jq -c ".[]|select(.rule==\"not-checked\")" "$T/out" | sed "s/^/  > /" | head -8; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN=
mkdir -p "$T/repo" "$T/sg" "$T/og" "$T/sc" "$T/nu" "$T/zap" "$T/base" "$T/sys" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
git remote add origin https://github.com/acme/demo.git
printf 'print(1)\n' >a.py; G add . && G commit -q -m code
stub() { printf '#!/usr/bin/env bash\necho "%s $*" >>"$HUB_LOG"\n%s\n' "$2" "$3" >"$T/$1/$2" && chmod +x "$T/$1/$2"; }
stub og opengrep '[ "${HUB_MODE:-}" != crash ] || exit 9
printf "%s\n" "{\"results\":[{\"check_id\":\"r.sqli\",\"path\":\"a.py\",\"start\":{\"line\":1},\"extra\":{\"message\":\"bad sql\",\"severity\":\"ERROR\"}}],\"errors\":[],\"paths\":{\"scanned\":[\"a.py\"]}}"'
stub sc scorecard '[ "${HUB_MODE:-}" != crash ] || exit 9
echo "token=${GITHUB_AUTH_TOKEN:-}" >>"$HUB_LOG"
printf "%s\n" "Starting [x]" >&2
printf "%s\n" "{\"score\":5,\"checks\":[{\"name\":\"Fuzzing\",\"score\":0,\"reason\":\"no fuzzer\"},{\"name\":\"License\",\"score\":10,\"reason\":\"ok\"},{\"name\":\"SAST\",\"score\":-1,\"reason\":\"inconclusive\"}]}"'
stub nu nuclei '[ "${HUB_MODE:-}" != crash ] || exit 9
echo "gt=${GITHUB_TOKEN:-}" >>"$HUB_LOG"
case " $* " in *" -tl "*) printf "%s" "${TL_OUT-tpl1}"; exit 0 ;; esac
[ -z "${EMPTY_SCAN:-}" ] || exit 0
printf "%s\n" "{\"template-id\":\"missing-xfo\",\"info\":{\"name\":\"X-Frame-Options missing\",\"severity\":\"low\"},\"matched-at\":\"http://localhost:3000/\"}"
printf "%s\n" "{\"template-id\":\"tech-detect\",\"info\":{\"name\":\"Wappalyzer\",\"severity\":\"info\"},\"matched-at\":\"http://localhost:3000/\"}"'
stub sg semgrep 'printf "%s\n" "{\"results\":[],\"errors\":[],\"paths\":{\"scanned\":[\"a.py\"]}}"'
stub zap zap-baseline.py '[ "${HUB_MODE:-}" != crash ] || exit 9
while [ $# -gt 0 ]; do [ "$1" != -J ] || j=$2; shift; done
[ -z "${ZAP_WS:-}" ] || { printf " \n\t\n" >"$j"; exit 2; }
printf "%s\n" "{\"site\":[{\"alerts\":[{\"pluginid\":\"10038\",\"riskdesc\":\"Medium (High)\",\"alert\":\"CSP Header Not Set\",\"instances\":[{\"uri\":\"http://localhost:3000/\"}]}]}]}" >"$j"
exit 2'
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"; printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"; chmod +x "$T/base/trivy" "$T/base/gitleaks"
printf '#!/bin/sh\necho "$*" >>%s/curl.log\n[ -z "${CURL_FAIL:-}" ]\n' "$T" >"$T/sys/curl"; chmod +x "$T/sys/curl"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep chmod; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { local p=$1; shift; : >"$HUB_LOG"; PATH="$p:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out" || true; }
row() { jq -e "any(.[]; $1)" "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
# opengrep fallback
run "$T/og:$T/sg"; grep -q "^semgrep " "$HUB_LOG" && ! grep -q "^opengrep" "$HUB_LOG" && ok "both present: semgrep wins" || bad "semgrep precedence"
run "$T/og"
row '.tool=="semgrep" and .rule=="r.sqli" and .file=="a.py"' && ran opengrep && grep -q 'opengrep scan --config' "$HUB_LOG" && ! grep -q 'p/default' "$HUB_LOG" && ok "opengrep stands in: findings parsed, no registry pack" || bad "opengrep fallback"
run ""; row '.rule=="not-checked" and (.message|test("not installed"))' && grep -q 'NOT CHECKED\|not run: semgrep (not installed)' "$T/err" && ! ran opengrep && ok "no semgrep, no opengrep: not checked" || bad "opengrep missing"
HUB_MODE=crash run "$T/og"; grep -q 'not run: semgrep' "$T/err" && ! ran opengrep && ok "opengrep crash is not clean" || bad "opengrep crash"
# scorecard
run "$T/sc"; [ ! -s "$HUB_LOG" ] && ok "scorecard opt-in off: not run" || bad "scorecard ran without opt-in"
REVIEW_SCORECARD=1 run "$T/sc"; grep -q 'needs GITHUB_TOKEN' "$T/err" && [ ! -s "$HUB_LOG" ] && row '.tool=="scorecard" and .rule=="not-checked"' && ok "scorecard without token: not run" || bad "scorecard token gate"
REVIEW_SCORECARD=1 GITHUB_TOKEN=tok run ""; grep -q '^NOT CHECKED: scorecard (install' "$T/err" && row '.tool=="scorecard" and .rule=="not-checked"' && ok "scorecard missing: NOT CHECKED" || bad "scorecard missing"
REVIEW_SCORECARD=1 GITHUB_TOKEN=tok run "$T/sc"
[ "$(jq '[.[]|select(.tool=="scorecard")]|length' "$T/out")" = 1 ] && row '.tool=="scorecard" and .rule=="scorecard-Fuzzing"' && grep -q 'scorecard --repo=github.com/acme/demo --format=json' "$HUB_LOG" && grep -q 'token=tok' "$HUB_LOG" && ran scorecard && ok "scorecard: only the score<5 check is a row; stderr noise ignored" || bad "scorecard findings"
REVIEW_SCORECARD=1 GITHUB_TOKEN=tok HUB_MODE=crash run "$T/sc"; grep -q 'not run: scorecard (exit 9)' "$T/err" && ! ran scorecard && ok "scorecard crash: not run" || bad "scorecard crash"
# scorecard that concluded nothing is not-checked, never a clean run
for J in '{"score":-1,"checks":[]}' '{"score":-1,"checks":[{"name":"SAST","score":-1,"reason":"inconclusive"}]}'; do
  stub sc scorecard "printf '%s\n' '$J'"
  REVIEW_SCORECARD=1 GITHUB_TOKEN=tok run "$T/sc"; grep -q 'not run: scorecard (unparseable' "$T/err" && row '.tool=="scorecard" and .rule=="not-checked"' && ! ran scorecard && ok "scorecard with no concluded check: not-checked" || bad "scorecard empty: $J"
done
# DAST
REVIEW_SCORECARD= run "$T/nu:$T/zap"; [ ! -s "$HUB_LOG" ] && ok "DAST opt-in off: nuclei and zap not run" || bad "DAST ran without opt-in"
# refused targets: nothing runs, a not-run line and a not-checked row
while IFS= read -r u; do
  REVIEW_DAST_URL=$u run "$T/nu:$T/zap"
  grep -q 'refused' "$T/err" && [ ! -s "$HUB_LOG" ] && row '.tool=="dast" and .rule=="not-checked"' && ok "refused: $u" || bad "not refused: $u"
done <<'U'
http://example.com/
http://127.0.0.1.evil.com/
http://localhost.evil.com/
http://0x7f.0.0.1/
http://localhost@example.com/
http://localhost\@example.com/
http://localhost\.evil.com/
--help
-u http://localhost/
file:///etc/passwd
ftp://localhost/
http://localhost/ x
http://localhost:80evil/
HTTP://localhost/
http://localhost./
http://localhost?x
http://localhost#x
http://[::1%25eth0]/
http://localhost%2f@x/
U
REVIEW_DAST_URL=$'http://localhost/\n-x' run "$T/nu:$T/zap"; grep -q refused "$T/err" && [ ! -s "$HUB_LOG" ] && ok "newline refused" || bad "newline"
REVIEW_DAST_URL=http://example.com/ REVIEW_DAST_ALLOW_REMOTE=1 run "$T/nu:$T/zap"; grep -q 'nuclei -u http://example.com/' "$HUB_LOG" && ok "REVIEW_DAST_ALLOW_REMOTE=1 allows a remote target" || bad "allow remote"
REVIEW_DAST_URL='file:///etc/passwd' REVIEW_DAST_ALLOW_REMOTE=1 run "$T/nu:$T/zap"; [ ! -s "$HUB_LOG" ] && ok "ALLOW_REMOTE still needs http(s)" || bad "allow remote file://"
REVIEW_DAST_URL=http://localhost:3000/ run ""; grep -q '^NOT CHECKED: nuclei (install' "$T/err" && grep -q '^NOT CHECKED: zap-baseline.py' "$T/err" && row '.tool=="nuclei" and .rule=="not-checked"' && row '.tool=="zap-baseline.py" and .rule=="not-checked"' && ok "DAST tools missing: NOT CHECKED" || bad "DAST missing"
CURL_FAIL=1 REVIEW_DAST_URL=http://localhost:3000/ run "$T/nu:$T/zap"; [ ! -s "$HUB_LOG" ] && grep -q '^NOT CHECKED: dast (target did not answer' "$T/err" && row '.tool=="dast" and .rule=="not-checked"' && ok "probe fails: not-checked, no scan" || bad "probe failure"
TL_OUT= EMPTY_SCAN=1 REVIEW_DAST_URL=http://localhost:3000/ run "$T/nu"; grep -q '^NOT CHECKED: nuclei (no templates matched' "$T/err" && row '.tool=="nuclei" and .rule=="not-checked"' && ! ran nuclei && ok "empty nuclei output, no template count: not-checked" || bad "empty nuclei"
EMPTY_SCAN=1 REVIEW_DAST_URL=http://localhost:3000/ run "$T/nu"; ran nuclei && ok "templates matched, no findings: ran clean" || bad "clean nuclei"
GITHUB_TOKEN=tok REVIEW_DAST_URL=http://localhost:3000/ run "$T/nu:$T/zap"
row '.tool=="nuclei" and .rule=="missing-xfo" and .file=="http://localhost:3000/"' && ! row '.tool=="nuclei" and .rule=="tech-detect"' && row '.tool=="zap" and .rule=="zap-10038"' && ran nuclei && ran zap && grep -q -- '-s info,low -type http -tags tech,exposure -etags default-login,xss,ssrf,oast,fuzz,fuzzing,takeover,cve,intrusive,dos' "$HUB_LOG" && grep -q -- ' -ni ' "$HUB_LOG" && ! grep -q 'gt=tok' "$HUB_LOG" && ok "nuclei and zap findings parsed, allowlist and exclusions, no interactsh, no GitHub token" || bad "DAST findings"
grep -q -- "-g --noproxy \* -sf" "$T/curl.log" && ok "probe: curl -g --noproxy '*'" || bad "curl flags"
mkdir -p "$T/dk"; stub dk docker ':'
REVIEW_DAST_URL=http://localhost:3000/ run "$T/dk"; grep -q '^docker run --rm --pull=never ' "$HUB_LOG" && ok "ZAP docker run never auto-pulls the image" || bad "docker pull"
REVIEW_DAST_URL=http://[::1]:3000/ run "$T/nu:$T/zap"; grep -q 'nuclei -u http://\[::1\]:3000/' "$HUB_LOG" && ok "IPv6 loopback allowed" || bad "ipv6 loopback"
HUB_MODE=crash REVIEW_DAST_URL=http://127.0.0.1:3000/ run "$T/nu:$T/zap"; grep -q 'not run: nuclei (exit 9)' "$T/err" && grep -q 'not run: zap (exit 9)' "$T/err" && ! ran nuclei && ! ran zap && ok "DAST crash: not run, not clean" || bad "DAST crash"
ZAP_WS=1 REVIEW_DAST_URL=http://localhost:3000/ run "$T/nu:$T/zap"; grep -q 'not run: zap (no report written)' "$T/err" && ! ran zap && ok "ZAP whitespace-only report: not run, not clean" || bad "zap whitespace report"
H=$ROOT/.claude/skills/deep-code-review/references/tool-hub.md
for t in opengrep scorecard nuclei zap-baseline; do grep -q "^| \`$t" "$H" && ok "$t documented in tool-hub.md" || bad "$t documented"; done
exit $fail
