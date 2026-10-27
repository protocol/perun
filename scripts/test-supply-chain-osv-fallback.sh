#!/usr/bin/env bash
# osv API fallback reads only lockfiles osv-scanner -r would (not gitignored stale copies); curl is stubbed, no network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SC="$ROOT/.claude/skills/deep-code-review/scripts/supply_chain_check.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-osvfb.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
mkdir -p "$T/bin"
printf '#!/usr/bin/env bash\nexit 2\n' >"$T/bin/osv-scanner"
# fake curl: querybatch marks next@14.0.0 vulnerable; vulns/ID returns a critical advisory
cat >"$T/bin/curl" <<'S'
#!/usr/bin/env bash
case "$*" in
  *querybatch*) python3 -c 'import json,sys
q=json.loads(sys.argv[1])["queries"]
print(json.dumps({"results":[{"vulns":[{"id":"GHSA-fake"}]} if x["version"]=="14.0.0" else {} for x in q]}))' "${@: -1}" ;;
  *) echo '{"id":"GHSA-fake","database_specific":{"severity":"CRITICAL"},"affected":[{"ranges":[{"events":[{"introduced":"0"},{"fixed":"15.0.0"}]}]}]}' ;;
esac
S
chmod +x "$T/bin"/*
lock() { mkdir -p "$(dirname "$1")"; printf '{"lockfileVersion":3,"packages":{"":{},"node_modules/next":{"version":"%s"}}}' "$2" >"$1"; }
run() { (cd "$1" && PATH="$T/bin:$PATH" bash "$SC" --online --fail-on high "$1" 2>&1) && echo "RC=0" || echo "RC=$?"; }
chk() { printf '%s' "$2" | grep -q -- "$3" && printf 'ok   %s\n' "$1" || { printf 'FAIL %s\n%s\n' "$1" "$2"; fail=1; }; }

req() { mkdir -p "$(dirname "$1")"; printf 'next==%s\n' "$2" >"$1"; }
mkdir -p "$T/patched" "$T/vuln" "$T/nogit" "$T/tracked" "$T/req" "$T/g128" "$T/gbin"
lock "$T/patched/package-lock.json" 15.0.0
lock "$T/patched/dist/package-lock.json" 14.0.0   # stale gitignored copy
printf 'dist/\n' >"$T/patched/.gitignore"
lock "$T/vuln/package-lock.json" 14.0.0
lock "$T/nogit/dist/package-lock.json" 14.0.0      # not a git repo: nothing ignored
lock "$T/tracked/dist/package-lock.json" 14.0.0    # tracked despite matching .gitignore
printf 'dist/\n' >"$T/tracked/.gitignore"
req "$T/req/dist/requirements.txt" 14.0.0 # ignored vulnerable requirements
printf 'dist/\n' >"$T/req/.gitignore"
lock "$T/g128/package-lock.json" 14.0.0
printf '#!/usr/bin/env bash\nexit 128\n' >"$T/gbin/git"; chmod +x "$T/gbin/git"
for d in patched vuln tracked req g128; do git -C "$T/$d" init -q; done
git -C "$T/tracked" add -f dist/package-lock.json

o=$(run "$T/patched"); chk "patched lock + ignored stale copy: no critical, skip noted" "$o" "skipped gitignored: .*dist/package-lock.json"
nochk() { printf '%s' "$2" | grep -q -- "$3" && { printf 'FAIL %s\n%s\n' "$1" "$2"; fail=1; } || printf 'ok   %s\n' "$1"; }
nochk "patched: no critical" "$o" "critical="
o=$(run "$T/vuln"); chk "vulnerable lock: critical finding" "$o" "critical=1"
o=$(run "$T/nogit"); chk "non-git dir: dist lock still flagged" "$o" "critical=1"
o=$(run "$T/tracked"); chk "tracked lock matching .gitignore still scanned" "$o" "critical=1"
o=$(run "$T/req"); nochk "ignored dist/requirements.txt skipped" "$o" "critical="
chk "ignored requirements skip noted" "$o" "skipped gitignored: .*requirements.txt"
o=$(PATH="$T/gbin:$PATH" run "$T/g128"); chk "git rc 128: lock still scanned" "$o" "critical=1"
exit $fail
