#!/usr/bin/env bash
# provision_tools.sh --age trivy|osv DIR: the advisory DB age in whole days (trivy db/metadata.json UpdatedAt, newest osv *.zip mtime), so
# review_checks.sh can mark a DB older than REVIEW_ADVISORY_MAX_AGE_DAYS as not checked instead of clean. Faked old and fresh cache dirs, no
# network; an unreadable DB (none, bad JSON, no zip) exits 1 and prints nothing. Hermetic: nothing is installed or downloaded.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PT=$ROOT/.claude/skills/deep-code-review/scripts/provision_tools.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-advage.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }

# age KIND DIR WANT: prints WANT (a number) or "none" (exit 1, empty output)
age() {
  local rc=0 o; o=$(bash "$PT" --age "$1" "$2" 2>/dev/null) || rc=$?
  if [ "$3" = none ]; then [ "$rc" = 1 ] && [ -z "$o" ] && ok "$4" || bad "$4 (rc=$rc out=$o)"
  else [ "$rc" = 0 ] && [ "$o" = "$3" ] && ok "$4" || bad "$4 (rc=$rc out=$o, want $3)"; fi
}
iso() { python3 -c "import sys,time; print(time.strftime('%Y-%m-%dT%H:%M:%S.123456789Z', time.gmtime(time.time()-float(sys.argv[1])*86400-3600)))" "$1"; }

mkdir -p "$T/tv-old/db" "$T/tv-new/db" "$T/tv-bad/db" "$T/osv-old/osv-scalibr/PyPI" "$T/osv-new/osv-scalibr/PyPI" "$T/osv-empty"
printf '{"Version":2,"UpdatedAt":"%s"}\n' "$(iso 21)" >"$T/tv-old/db/metadata.json"
printf '{"Version":2,"UpdatedAt":"%s"}\n' "$(iso 1)" >"$T/tv-new/db/metadata.json"
printf 'not json' >"$T/tv-bad/db/metadata.json"
: >"$T/osv-old/osv-scalibr/PyPI/all.zip"; touch -t 200001010000 "$T/osv-old/osv-scalibr/PyPI/all.zip"
: >"$T/osv-new/osv-scalibr/PyPI/all.zip"

age trivy "$T/tv-old" 21 "trivy: 21-day-old UpdatedAt reads 21 days"
age trivy "$T/tv-new" 1 "trivy: a DB updated 1 day and 1 hour ago reads 1 day"
age trivy "$T/tv-bad" none "trivy: bad metadata.json is unreadable"
age trivy "$T/nope" none "trivy: no cache dir is unreadable"
age osv "$T/osv-new" 0 "osv: fresh zip reads 0 days"
o=$(bash "$PT" --age osv "$T/osv-old" 2>/dev/null) && [ "$o" -gt 7 ] && ok "osv: year-2000 zip is older than 7 days" || bad "osv: old zip (out=$o)"
age osv "$T/osv-empty" none "osv: no zip is unreadable"
# the newest zip wins when an ecosystem is stale and another is fresh
mkdir -p "$T/osv-mixed/osv-scalibr/PyPI" "$T/osv-mixed/osv-scalibr/npm"
: >"$T/osv-mixed/osv-scalibr/PyPI/all.zip"; touch -t 200001010000 "$T/osv-mixed/osv-scalibr/PyPI/all.zip"; : >"$T/osv-mixed/osv-scalibr/npm/all.zip"
o=$(bash "$PT" --age osv "$T/osv-mixed" 2>/dev/null) && [ "$o" -gt 7 ] && ok "osv: the oldest zip wins, one fresh ecosystem does not hide a stale one" || bad "osv: mixed (out=$o)"
# zips at any depth, and no osv-scalibr/osv-scanner dir: the dir itself is searched
mkdir -p "$T/osv-deep/a/b"; : >"$T/osv-deep/a/b/all.zip"; touch -t 200001010000 "$T/osv-deep/a/b/all.zip"
o=$(bash "$PT" --age osv "$T/osv-deep" 2>/dev/null) && [ "$o" -gt 7 ] && ok "osv: zip at any depth under a plain dir" || bad "osv: deep (out=$o)"
# --cache trivy-dir: the dir with or without a DB (so the scan and the age check share it); trivy-cmd warms that same dir
cd=$(env -i PATH="/usr/bin:/bin" HOME="$T/h" DCR_CACHE_ROOT="$T/root" "$BASH" "$PT" --cache trivy-dir 2>&1) && [ "$cd" = "$T/root/trivy" ] && ok "trivy-dir: cold cache root still names its dir" || bad "trivy-dir ($cd)"
cc=$(env -i PATH="/usr/bin:/bin" HOME="$T/h" DCR_CACHE_ROOT="$T/root" "$BASH" "$PT" --cache trivy-cmd 2>&1) && case $cc in *"DOCKER_CONFIG="*"trivy --cache-dir $T/root/trivy fs --download-db-only") ok "trivy-cmd: empty DOCKER_CONFIG, same dir" ;; *) bad "trivy-cmd ($cc)" ;; esac
rc=0; bash "$PT" --age bogus "$T" >/dev/null 2>&1 || rc=$?; [ "$rc" = 2 ] && ok "unknown kind exits 2" || bad "unknown kind rc=$rc"
rc=0; bash "$PT" --age trivy >/dev/null 2>&1 || rc=$?; [ "$rc" = 2 ] && ok "missing DIR is a usage error" || bad "missing DIR rc=$rc"
exit "$fail"
