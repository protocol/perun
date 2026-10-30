#!/usr/bin/env bash
# provision_tools.sh: the local semgrep p/default snapshot counts as warm only when it holds a top-level `rules:` key. An empty file,
# an HTML error page and a YAML file of another shape are cold (--cache semgrep exits 1 and prints nothing; the dry run says COLD), so
# review_checks.sh falls back to the registry pack instead of handing semgrep a file that is not a config. Hermetic: env -i, a throwaway
# HOME and cache root; nothing is installed or downloaded.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PT=$ROOT/.claude/skills/deep-code-review/scripts/provision_tools.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sgwarm.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
BASH_BIN=$(type -P bash)
sg() { env -i PATH="/usr/bin:/bin" HOME="$T/home" DCR_CACHE_ROOT="$T/cache" DCR_USER_BIN= "$BASH_BIN" "$PT" "$@"; }
snap=$T/cache/dcr-tools/semgrep/p-default.yml; mkdir -p "$(dirname "$snap")"

# check LABEL warm|cold: --cache semgrep and the dry run agree on the snapshot as it is now
check() {
  local rc=0 o d; o=$(sg --cache semgrep 2>&1) || rc=$?; d=$(sg 2>&1)
  if [ "$2" = warm ]; then
    if [ "$rc" = 0 ] && [ "$o" = "$snap" ] && grep -q '^warm     semgrep p/default snapshot' <<<"$d"; then ok "$1: warm"; else bad "$1: expected warm (rc=$rc, out=$o)"; fi
  elif [ "$rc" = 1 ] && [ -z "$o" ] && grep -q '^COLD     semgrep p/default snapshot' <<<"$d"; then ok "$1: cold"
  else bad "$1: expected cold (rc=$rc, out=$o)"; fi
}

rm -f "$snap"; check "no snapshot" cold
: >"$snap"; check "empty file" cold
printf '<!doctype html>\n<html><body><h1>403 Forbidden</h1><p>the rules: none apply</p></body></html>\n' >"$snap"; check "html error page" cold
printf 'version: 2\nrulesets:\n  - id: x\n' >"$snap"; check "yaml without a rules key" cold
printf '  rules:\n  - id: x\n' >"$snap"; check "indented rules, not top level" cold
printf 'rules:\n- id: acme.demo\n  message: demo\n  languages: [python]\n  severity: WARNING\n  pattern: eval(...)\n' >"$snap"; check "rules snapshot" warm
printf '# fetched for Acme\nrules: []\n' >"$snap"; check "comment line, then rules" warm

if [ "$fail" = 0 ]; then echo "ok: semgrep snapshot warm check"; else echo "FAILED"; exit 1; fi
