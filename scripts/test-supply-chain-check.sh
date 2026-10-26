#!/usr/bin/env bash
# Tests for supply_chain_check.sh with fake zizmor/actionlint/osv-scanner/scorecard binaries on PATH.
# shellcheck disable=SC2015,SC2016
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SC="$ROOT/.claude/skills/deep-code-review/scripts/supply_chain_check.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sc.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
# expect NAME WANT_RC PATTERN -- cmd...
expect() { local n=$1 w=$2 p=$3 o r; shift 4; o=$("$@" 2>&1) && r=0 || r=$?
  [ "$r" = "$w" ] && printf '%s' "$o" | grep -q -- "$p" && ok "$n" || { bad "$n (rc=$r)"; printf '%s\n' "$o"; }; }

mkdir -p "$T/bin" "$T/repo/.github/workflows" "$T/empty" "$T/sys" "$T/nopy"
for t in cat grep python3 dirname env; do ln -s "$(command -v $t)" "$T/sys/$t"; done # PATH without the fake tools
for t in cat grep dirname env bash; do ln -s "$(command -v $t)" "$T/nopy/$t"; done       # ... and without python3
for t in zizmor actionlint scorecard; do
  printf '#!/usr/bin/env bash\necho "%s $*" >>"$FAKE_LOG"\n[ "${FAKE_FAIL:-}" = %s ] && exit 1\nexit 0\n' "$t" "$t" >"$T/bin/$t"
done
cat >"$T/bin/osv-scanner" <<'S'
#!/usr/bin/env bash
echo "osv-scanner $*" >>"$FAKE_LOG"
if [ -n "${OSV_JSON:-}" ]; then printf '%s' "$OSV_JSON"; exit "${OSV_RC:-1}"; fi
echo '{"results":[{"packages":[{"package":{"name":"left-pad","version":"1.0.0"},"groups":[{"ids":["B"],"max_severity":"5.0"}],"vulnerabilities":[
{"id":"A","database_specific":{"severity":"HIGH"},"affected":[{"ranges":[{"events":[{"introduced":"0"},{"fixed":"1.2.3"}]}]}]},
{"id":"B"},{"id":"C","database_specific":{"severity":"LOW"}}]}]}]}'
exit "${OSV_RC:-1}"
S
chmod +x "$T/bin"/*
export FAKE_LOG="$T/log"; : >"$FAKE_LOG"
P="$T/bin:$PATH"
one() { printf '{"results":[{"packages":[{"package":{"name":"p","version":"1"},"groups":[%s],"vulnerabilities":[%s]}]}]}' "$1" "$2"; }
MOD=$(one '' '{"id":"M","database_specific":{"severity":"MODERATE"}}')
VEC=$(one '{"ids":["V"],"max_severity":"CVSS:3.1/AV:N/AC:L"}' '{"id":"V"}')

expect "default run: osv not requested -> INCOMPLETE exit 3, names api.osv.dev" 3 'SKIPPED osv-scanner: opt-in.*api.osv.dev' -- env PATH="$P" bash "$SC" "$T/repo"
expect "INCOMPLETE line lists skipped checks" 3 'INCOMPLETE: skipped osv-scanner scorecard' -- env PATH="$P" bash "$SC" "$T/repo"
expect "--allow-skip accepts a skip-only run" 0 'SKIPPED' -- env PATH="$P" bash "$SC" --allow-skip "$T/repo"
grep -q '^osv-scanner' "$FAKE_LOG" && bad "osv ran without --online" || ok "osv not invoked without --online"
expect "--online: high fails, counts + fixed version printed" 1 'high=1, moderate=1, low=1' -- env PATH="$P" bash "$SC" --online "$T/repo"
expect "fixed version shown" 1 'fixed in: 1.2.3' -- env PATH="$P" bash "$SC" --online "$T/repo"
expect "--fail-on critical passes high" 0 'osv-scanner: high=1' -- env PATH="$P" bash "$SC" --online --fail-on critical --allow-skip "$T/repo"
expect "boundary: moderate fails --fail-on moderate" 1 'moderate=1' -- env PATH="$P" OSV_JSON="$MOD" bash "$SC" --online --fail-on moderate "$T/repo"
expect "boundary: moderate passes --fail-on high" 0 'moderate=1' -- env PATH="$P" OSV_JSON="$MOD" bash "$SC" --online --allow-skip "$T/repo"
expect "CVSS-vector severity is unknown and fails closed even at critical" 1 'unknown=1' -- env PATH="$P" OSV_JSON="$VEC" bash "$SC" --online --fail-on critical "$T/repo"
expect "unparseable osv output fails" 1 'FAIL osv-scanner: unparseable' -- env PATH="$P" OSV_JSON='not json' OSV_RC=0 bash "$SC" --online "$T/repo"
expect "osv hard error (exit 127) fails" 1 'FAIL osv-scanner: exit 127' -- env PATH="$P" OSV_RC=127 OSV_JSON='{}' bash "$SC" --online "$T/repo"
expect "osv exit 128 (no sources) stays a failure" 1 'FAIL osv-scanner: exit 128' -- env PATH="$P" OSV_RC=128 OSV_JSON='{}' bash "$SC" --online "$T/repo"
expect "python3 missing: osv SKIPPED, INCOMPLETE" 3 'SKIPPED osv-scanner: python3 needed' -- env PATH="$T/bin:$T/nopy" /bin/bash "$SC" --online "$T/repo"
expect "bad --fail-on is usage error" 2 'bad --fail-on' -- env PATH="$P" bash "$SC" --fail-on nope
expect "--fail-on without value is usage error" 2 'needs a value' -- env PATH="$P" bash "$SC" --fail-on
expect "--scorecard without value is usage error" 2 'needs a value' -- env PATH="$P" bash "$SC" --scorecard
expect "--scorecard rejects a non owner/repo shape" 2 'bad --scorecard' -- env PATH="$P" bash "$SC" --scorecard 'a b/c;x'
expect "missing tools reported skipped, exit 3" 3 'SKIPPED actionlint: not installed' -- env PATH="$T/sys" /bin/bash "$SC" --online --scorecard o/r "$T/repo"
expect "no workflows dir: ci tools skipped" 3 'SKIPPED zizmor: no .github/workflows' -- env PATH="$P" bash "$SC" "$T/empty"
expect "zizmor failure beats INCOMPLETE" 1 'FAIL zizmor' -- env PATH="$P" FAKE_FAIL=zizmor bash "$SC" "$T/repo"
expect "actionlint failure fails the gate" 1 'FAIL actionlint' -- env PATH="$P" FAKE_FAIL=actionlint bash "$SC" "$T/repo"
expect "scorecard failure fails the gate" 1 'FAIL scorecard' -- env PATH="$P" FAKE_FAIL=scorecard bash "$SC" --scorecard acme/widget "$T/repo"
expect "scorecard only with --scorecard" 3 'SKIPPED scorecard: pass --scorecard' -- env PATH="$P" bash "$SC" "$T/repo"
: >"$FAKE_LOG"
expect "scorecard runs for a named repo" 0 'ok scorecard' -- env PATH="$P" bash "$SC" --scorecard acme/widget --allow-skip "$T/repo"
grep -q 'scorecard --repo=github.com/acme/widget' "$FAKE_LOG" && ok "scorecard got repo arg" || bad "scorecard arg"
grep -q '^actionlint' "$FAKE_LOG" && grep -q '^zizmor' "$FAKE_LOG" && ok "zizmor+actionlint ran" || bad "ci tools ran"
expect "fully run, all clean: exit 0" 0 'ok scorecard' -- env PATH="$P" OSV_JSON='{"results":[]}' OSV_RC=0 bash "$SC" --online --scorecard acme/widget "$T/repo"
exit "$fail"
