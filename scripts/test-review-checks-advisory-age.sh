#!/usr/bin/env bash
# review_checks.sh: an offline advisory DB (osv-scanner, trivy) older than REVIEW_ADVISORY_MAX_AGE_DAYS (default 7), or present with an unreadable age,
# gets a not-checked "NOT CHECKED: no local advisory DB ..." row naming the refresh command; an age equal to the limit gets none. The row text is fed
# through audit_sweep.py's own classifier (env_gap), so a text drift from STALE_DB fails here. Stub osv-scanner/trivy on PATH, fake DB dirs with old
# mtimes (touch -t) and a metadata.json UpdatedAt; no network, nothing installed or downloaded.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SD="$ROOT/.claude/skills/deep-code-review/scripts"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-advwire.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT
fail=0
ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
mkdir -p "$T/bin" "$T/repo"
printf '#!/usr/bin/env bash\necho "{\\"results\\":[]}"\n' >"$T/bin/osv-scanner"
printf '#!/usr/bin/env bash\necho "$*" >>"%s/trivy.args"\necho "{\\"Results\\":[]}"\n' "$T" >"$T/bin/trivy"
chmod +x "$T/bin"/*
printf 'flask==0.12.2\n' >"$T/repo/requirements.txt"
git -C "$T/repo" init -q; git -C "$T/repo" add requirements.txt
git -C "$T/repo" -c user.email=jane@example.com -c user.name="Jane Smith" commit -qm init

# ago DAYS FORMAT: now minus DAYS days and one hour (so the whole-day age is exactly DAYS), in strftime FORMAT
ago() { python3 -c 'import sys,time; print(time.strftime(sys.argv[2], (time.gmtime if sys.argv[2].endswith("Z") else time.localtime)(time.time()-float(sys.argv[1])*86400-3600)))' "$1" "$2"; }
mk_osv() { mkdir -p "$1/osv-scalibr/PyPI"; : >"$1/osv-scalibr/PyPI/all.zip"; [ "$2" = 0 ] || touch -t "$(ago "$2" %Y%m%d%H%M)" "$1/osv-scalibr/PyPI/all.zip"; }
mk_tv() { mkdir -p "$1/db"; echo x >"$1/db/trivy.db"; if [ "$2" = bad ]; then echo 'not json' >"$1/db/metadata.json"
  else printf '{"Version":2,"UpdatedAt":"%s"}\n' "$(ago "$2" %Y-%m-%dT%H:%M:%S.123456789Z)" >"$1/db/metadata.json"; fi; }

# classify FILE: one "tool ENVGAP|NOT-ENVGAP stale|unknown" line per advisory-DB row, classified by audit_sweep.py
classify() { python3 -I -c '
import json, sys
sys.path.insert(0, sys.argv[2])
import audit_sweep as a
for r in json.load(open(sys.argv[1])):
    if r.get("rule") == "not-checked" and a.msg(r).startswith("NOT CHECKED: no local advisory DB"):
        print(r["tool"], "ENVGAP" if a.env_gap(r) else "NOT-ENVGAP", "unknown" if "of known age" in a.msg(r) else "stale")
' "$1" "$SD" | sort; }

n=0
# run_case LABEL EXPECTED-ROWS ENV...: review_checks.sh --full in the repo; EXPECTED-ROWS is the sorted rows classify must print ("-" for none)
run_case() {
  local label=$1 want=$2 got; shift 2
  (cd "$T/repo" && env PATH="$T/bin:/usr/bin:/bin" DCR_USER_BIN= DCR_CACHE_ROOT="$T/root$n" "$@" bash "$SD/review_checks.sh" --full >"$T/out$n.json" 2>"$T/err$n.txt") || true
  got=$(classify "$T/out$n.json" | paste -sd, -); [ -n "$got" ] || got=-
  if [ "$got" = "$want" ]; then ok "$label: $got"; else bad "$label: want [$want] got [$got]"; fi
}
OS="osv-scanner ENVGAP stale" TV="trivy ENVGAP stale"
both() { n=$((n + 1)); mk_osv "$T/o$n" "$1"; mk_tv "$T/t$n" "$2"; } # a new case: its own DB dirs and cache root
both 7 7; run_case "age == max (7 days): no row" - REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n"
both 8 8; run_case "age max+1 (8 days): a row for each tool" "$OS,$TV" REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n"
both 5 5; run_case "override 3: a 5-day-old DB is stale" "$OS,$TV" REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n" REVIEW_ADVISORY_MAX_AGE_DAYS=3
both 21 21; run_case "override 30: a 21-day-old DB is fine" - REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n" REVIEW_ADVISORY_MAX_AGE_DAYS=30
both 8 8; run_case "garbage limit falls back to 7" "$OS,$TV" REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n" REVIEW_ADVISORY_MAX_AGE_DAYS=abc
[ "$(grep -c 'REVIEW_ADVISORY_MAX_AGE_DAYS=abc is not a whole number of days; using 7' "$T/err$n.txt")" = 1 ] && ok "garbage limit: one stderr line" || bad "garbage limit: stderr line count"
both 0 bad; run_case "unreadable trivy metadata with a DB present: age-unknown row" "trivy ENVGAP unknown" REVIEW_OSV_DB_DIR="$T/o$n" REVIEW_TRIVY_CACHE="$T/t$n"

# trivy default dir: no REVIEW_TRIVY_CACHE, the cache root's trivy dir is scanned with and age-checked
n=$((n + 1)); mk_osv "$T/o$n" 0; mk_tv "$T/root$n/trivy" 8; : >"$T/trivy.args"
run_case "cache root, stale DB: row" "$TV" REVIEW_OSV_DB_DIR="$T/o$n"
grep -q -- "--cache-dir $T/root$n/trivy" "$T/trivy.args" && ok "cache root: trivy scans the age-checked dir" || bad "cache root: trivy args: $(cat "$T/trivy.args")"
n=$((n + 1)); mk_osv "$T/o$n" 0; : >"$T/trivy.args"
run_case "cold cache root: no age row, scan still pinned to that dir" - REVIEW_OSV_DB_DIR="$T/o$n"
grep -q -- "--cache-dir $T/root$n/trivy" "$T/trivy.args" && ok "cold cache root: trivy gets that dir, not its own default" || bad "cold cache root: trivy args: $(cat "$T/trivy.args")"
exit $fail
