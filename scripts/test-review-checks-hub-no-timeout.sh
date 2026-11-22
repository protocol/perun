#!/usr/bin/env bash
# review_checks.sh on a host with no timeout(1) and no gtimeout (stock macOS), with stub binaries on a hermetic PATH (no network). The perl
# timebox fallback must stop a child that ignores SIGALRM, as Go binaries such as gh do: the history scan's `gh repo view` visibility probe
# then gives up at its 10 s bound (visibility unknown, so a default-branch secret ranks exposure-p0) instead of hanging the run. The slither
# gate's `solc --version` probe must run there too, so a working solc is never reported missing.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubnotmo.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q -b main . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
export GL_SECRET=$(printf '%s' q8Zk3Rt7Wm 1Xv5Bn9Lc2 Hd6Jf4Sg0Pa) # assembled at runtime, so no literal here looks like a credential
mkdir contracts; printf 'pragma solidity ^0.8.0;\n' >contracts/T.sol; printf 'API_KEY=%s\n' "$GL_SECRET" >config.env
G add . && G commit -q -m code
# gitleaks stub: the working-tree scan (--no-git) is clean, the history scan reports the committed key
cat >"$T/bin/gitleaks" <<'S'
#!/usr/bin/env bash
r=; a=("$@"); for ((i = 0; i < ${#a[@]}; i++)); do [ "${a[i]}" != -r ] || r=${a[i+1]}; done
case " $* " in *" --no-git "*) echo '[]' >"$r" ;; *) printf '[{"RuleID":"generic-api-key","File":"config.env","StartLine":1,"Secret":"%s","Fingerprint":"config.env:generic-api-key:1"}]' "$GL_SECRET" >"$r" ;; esac
S
# gh stub: ignores SIGALRM like the Go runtime and would hang for 30 s in a grandchild that holds the output pipe, so a timebox that
# TERMs only its direct child leaves `$(gh ...)` waiting for the grandchild; the timebox must kill the whole process group
printf '#!/bin/sh\necho "gh $*" >>"$HUB_LOG"\ntrap "" ALRM\nsleep 30 &\nwait\n' >"$T/bin/gh"
cat >"$T/bin/slither" <<'S'
#!/usr/bin/env bash
echo "slither $*" >>"$HUB_LOG"
while [ $# -gt 0 ]; do [ "$1" != --sarif ] || { printf '{"version":"2.1.0","runs":[{"results":[]}]}' >"$2"; break; }; shift; done
S
printf '#!/bin/sh\nexit 0\n' >"$T/bin/solc"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/bin/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/bin/trivy"
chmod +x "$T"/bin/*
for b in bash sh env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep seq tar; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
PATH="$T/bin:$T/sys" command -v timeout gtimeout >/dev/null && { echo "FAIL - hermetic PATH still has timeout or gtimeout" >&2; exit 1; }
: >"$HUB_LOG"; t0=$SECONDS
PATH="$T/bin:$T/sys" bash "$RC" --base base --history 2>"$T/err" >"$T/out" || true
dt=$((SECONDS - t0))
grep -q '^gh repo view' "$HUB_LOG" && [ "$dt" -lt 25 ] && ok "gh ignoring SIGALRM is stopped at its 10 s bound (run took ${dt}s)" || bad "gh bound: run took ${dt}s; $(grep '^gh' "$HUB_LOG" || echo 'gh never called')"
jq -e 'any(.[]; .tool=="secret-exposure" and .file=="config.env" and .rule=="exposure-p0")' "$T/out" >/dev/null && ok "timed-out gh: visibility unknown, default-branch secret ranks exposure-p0" || bad "exposure: $(jq -c '[.[]|select(.tool=="secret-exposure" or .tool=="gitleaks-history")]' "$T/out" 2>/dev/null)"
grep -q '^slither ' "$HUB_LOG" && ! grep -q 'no working solc' "$T/err" && ok "no timeout(1): a working solc passes the probe and slither runs" || bad "slither: $(grep slither "$T/err")"
[ "$fail" = 0 ]
