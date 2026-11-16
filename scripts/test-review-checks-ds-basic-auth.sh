#!/usr/bin/env bash
# detect-secrets "Basic Auth Credentials": a row is demoted to a likely-fixture hint only when every URI password on the line is a literal placeholder
# (same strict rule as trufflehog's URI rows); a real password, or a mixed line, keeps the plain row. The row is never dropped. Stub detect-secrets, hermetic PATH.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubdsba.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export REAL_HOME="$HOME" PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
RP=Zq8v3Lr2
printf 'DB=postgres://user:pass@db.internal/app\n' >ph.env
printf 'DB=postgres://user:%s@db.internal/app\n' "$RP" >real.env
printf 'A=postgres://user:pass@a.internal/app\nB=postgres://user:%s@b.internal/app\n' "$RP" >mixed.env
printf 'C=curl -H "Authorization: Basic dXNlcjpSZWFsUGFzczE=" http://user:pass@h.internal/x\n' >hdr.env
printf 'C=http://user:pass@h.internal/x?token=%s\n' "$RP" >tok.env
printf 'C=http://user:pass@h.internal/x?token=changeme\n' >tokph.env
G add . && G commit -q -m code
printf '#!/usr/bin/env bash\nprintf "%%s" "$J_ds"\n' >"$T/bin/detect-secrets"
e() { printf '{"type": "Basic Auth Credentials", "filename": "./%s", "hashed_secret": "H", "is_verified": false, "line_number": %s}' "$1" "$2"; }
export J_ds="{\"results\": {\"./ph.env\": [$(e ph.env 1)], \"./real.env\": [$(e real.env 1)], \"./mixed.env\": [$(e mixed.env 1), $(e mixed.env 2)], \"./hdr.env\": [$(e hdr.env 1)], \"./tok.env\": [$(e tok.env 1)], \"./tokph.env\": [$(e tokph.env 1)]}}"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/bin/detect-secrets" "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep xargs; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
hint() { jq -r --arg f "$1" --argjson l "$2" '[.[]|select(.tool=="detect-secrets" and .file==$f and .line==$l)|(.hint // "none")]|first // "ABSENT"' "$T/out"; }
[ "$(hint ph.env 1)" = likely-fixture ] && ok "all-placeholder password: demoted, row kept" || bad "ph: $(hint ph.env 1)"
[ "$(hint real.env 1)" = none ] && ok "real password: plain row" || bad "real: $(hint real.env 1)"
[ "$(hint mixed.env 1)" = likely-fixture ] && [ "$(hint mixed.env 2)" = none ] && ok "per line: placeholder demoted, real kept" || bad "mixed: $(hint mixed.env 1) $(hint mixed.env 2)"
[ "$(hint hdr.env 1)" = none ] && ok "placeholder URL plus a real-looking Basic header: not demoted" || bad "hdr: $(hint hdr.env 1)"
[ "$(hint tok.env 1)" = none ] && [ "$(hint tokph.env 1)" = likely-fixture ] && ok "token= value must be a placeholder too" || bad "tok: $(hint tok.env 1) $(hint tokph.env 1)"
! grep -q "$RP" "$T/out" && ok "no password in output" || bad "password leaked"
exit $fail
