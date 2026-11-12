#!/usr/bin/env bash
# review_checks.sh hub routing for trufflehog-fs (filesystem, --no-verification --json, detector/file/line only) and cosign (verify-blob offline)
# with stub binaries on a hermetic PATH (no real tool, no network). Missing tool = NOT CHECKED; crash, empty or whitespace output = not run, never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubss.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'k=1\n' >app.cfg; printf 'blob\n' >art.tgz; printf '{}\n' >art.tgz.bundle; printf 'sig\n' >raw.sig
G add . && G commit -q -m files
cat >"$T/bin/trufflehog" <<'S'
#!/usr/bin/env bash
echo "trufflehog $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_tf"
exit 0
S
cat >"$T/bin/cosign" <<'S'
#!/usr/bin/env bash
echo "cosign $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$CS_OUT"
exit "${CS_RC:-0}"
S
chmod +x "$T/bin/trufflehog" "$T/bin/cosign"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
SECRET='SUPERSECRETVALUE123'
export J_tf='2026-01-01T00:00:00Z	info-0	trufflehog	running source
{"SourceMetadata":{"Data":{"Filesystem":{"file":"./app.cfg","line":4}}},"DetectorName":"AWS","Verified":false,"Raw":"'$SECRET'","RawV2":"'$SECRET'","Redacted":"SUPER***"}
2026-01-01T00:00:01Z	info-0	trufflehog	finished scanning'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
tf() { jq -e --arg f "$1" --arg r "$2" 'any(.[]; .tool=="trufflehog-fs" and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; CS_OUT='Verified OK' run
tf app.cfg AWS && ok "trufflehog-fs: row = detector, file, line on a changed file" || bad "tf row: $(jq -c '[.[]|select(.tool=="trufflehog-fs")]' "$T/out")"
jq -e 'any(.[]; .tool=="trufflehog-fs" and .line==4)' "$T/out" >/dev/null && ok "line carried" || bad "line"
! grep -rqF "$SECRET" "$T/out" "$T/err" && ! grep -qF 'SUPER***' "$T/out" "$T/err" && ok "secret value never printed (stdout, stderr)" || bad "secret leaked"
grep -q '^trufflehog filesystem --no-verification --no-update --json ' "$HUB_LOG" && ! grep -q 'verif' <(grep '^trufflehog' "$HUB_LOG" | sed 's/--no-verification//') && ok "always --no-verification --json, never a verify flag" || bad "flags: $(grep ^trufflehog "$HUB_LOG")"
ran trufflehog-fs && ok "trufflehog-fs: ran" || bad "tf ran: $(grep -E "ran|trufflehog-fs" "$T/err")"
for c in '' $' \n\t\n' '2026 info-0 only log lines' 'not json' '{"x":1}'; do
  J_tf=$c run; notrun trufflehog-fs && ok "trufflehog-fs: not run on $(printf %q "$c")" || bad "tf not run: $(printf %q "$c")"
done
J_tf='{"SourceMetadata":{"Data":{"Filesystem":{"file":"other.txt","line":1}}},"DetectorName":"Slack","Raw":"x"}' run; grep -q 'not run: trufflehog-fs (1 of 1 rows named a file outside' "$T/err" && ok "trufflehog-fs: a row for a file outside the scanned list is not run, never clean" || bad "outside row"
HUB_MODE=crash run; notrun trufflehog-fs && ok "trufflehog-fs: crash is not run" || bad "tf crash"
# cosign: only a .bundle with a cosign.pub and its signed file; nothing else is verified
: >"$HUB_LOG"; CS_OUT='Verified OK' run
grep -q 'NOT CHECKED: cosign (raw.sig: only a .bundle' "$T/err" && grep -q 'NOT CHECKED: cosign (art.tgz.bundle: no cosign.pub' "$T/err" && ok "cosign: raw .sig and a bundle with no key: NOT CHECKED" || bad "cosign gates: $(grep cosign "$T/err")"
! grep -q '^cosign' "$HUB_LOG" && ok "cosign: nothing run without a key" || bad "cosign ran keyless"
printf 'pub\n' >cosign.pub; G add . && G commit -q -m key; : >"$HUB_LOG"; CS_OUT='Verified OK' run
grep -qx 'cosign verify-blob --key ./cosign.pub --bundle ./art.tgz.bundle --insecure-ignore-tlog=true ./art.tgz' "$HUB_LOG" && [ "$(grep -c ^cosign "$HUB_LOG")" = 1 ] && ok "cosign: verify-blob offline (key, bundle, ignore-tlog), one call for the bundle" || bad "cosign argv: $(grep ^cosign "$HUB_LOG")"
ran cosign && jq -e 'any(.[]; .tool=="cosign" and .rule!="not-checked")|not' "$T/out" >/dev/null && ok "cosign: ran, no finding rows" || bad "cosign ran"
for c in '' $' \n'; do CS_OUT=$c run; notrun cosign && ok "cosign: exit 0 with $(printf %q "$c") output is not run" || bad "cosign empty"; done
CS_RC=1 CS_OUT='error: invalid signature' run; notrun cosign && ok "cosign: exit 1 is not run, never clean" || bad "cosign exit 1"
HUB_MODE=crash run; notrun cosign && ok "cosign: crash is not run" || bad "cosign crash"
git rm -q art.tgz && G commit -q -m noblob; CS_OUT='Verified OK' run
grep -q 'NOT CHECKED: cosign (art.tgz.bundle: signed file ./art.tgz is missing\|NOT CHECKED: cosign (art.tgz.bundle: signed file art.tgz is missing' "$T/err" && ok "cosign: missing signed file: NOT CHECKED" || bad "cosign blob gate"
# missing tools
rm "$T/bin/trufflehog" "$T/bin/cosign"; run
grep -q 'NOT CHECKED: trufflehog-fs (install: brew install trufflehog)' "$T/err" && grep -q 'NOT CHECKED: cosign (install: brew install cosign)' "$T/err" && jq -e 'any(.[]; .tool=="cosign" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tools"
[ "$fail" = 0 ] && echo "PASS" || { echo "FAILED"; exit 1; }
