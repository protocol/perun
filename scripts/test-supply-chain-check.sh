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

mkdir -p "$T/bin" "$T/repo/.github/workflows" "$T/empty" "$T/sys" "$T/nopy" "$T/nowf/.github/workflows"
: >"$T/repo/.github/workflows/ci.yml"
# git fixtures: a repo with tracked files plus a never-tracked one (stands in for node_modules), and a repo with no commit.
# No git repo above $T may leak in (GIT_CEILING_DIRECTORIES), and no hook env (GIT_DIR...) may redirect git.
g() { git -c user.name=Test -c user.email=test@example.com -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }
export GIT_CEILING_DIRECTORIES="$T"; unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
mkdir -p "$T/gitrepo/.github/workflows" "$T/gitrepo/node_modules" "$T/gitrepo/sub" "$T/nocommit" "$T/xtmp"
: >"$T/gitrepo/.github/workflows/ci.yml"; echo tracked >"$T/gitrepo/tracked.txt"; echo inner >"$T/gitrepo/sub/inner.txt"
g -C "$T/gitrepo" init -q; g -C "$T/gitrepo" add -A; g -C "$T/gitrepo" commit -qm fixture
: >"$T/gitrepo/node_modules/untracked.bin"; g -C "$T/nocommit" init -q
for t in cat grep python3 dirname env find head; do ln -s "$(command -v $t)" "$T/sys/$t"; done # PATH without the fake tools
for t in cat grep dirname env bash find head; do ln -s "$(command -v $t)" "$T/nopy/$t"; done       # ... and without python3
for t in zizmor actionlint; do
  printf '#!/usr/bin/env bash\necho "%s $*" >>"$FAKE_LOG"\n[ "${FAKE_FAIL:-}" = %s ] && exit 1\nexit 0\n' "$t" "$t" >"$T/bin/$t"
done
cat >"$T/bin/scorecard" <<'S'
#!/usr/bin/env bash
echo "scorecard $*" >>"$FAKE_LOG"
for a in "$@"; do [ "${a#--local=}" != "$a" ] && (cd "${a#--local=}" && find . -type f | sort | sed 's/^/scorecard-sees /' >>"$FAKE_LOG"); done
[ -n "${FAKE_HANG:-}" ] && { echo $$ >"$FAKE_HANG"; exec sleep 20; }
[ "${FAKE_FAIL:-}" = scorecard ] && exit 1
exit 0
S
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
expect "no workflows dir: ci tools n/a, not skipped" 3 'n/a zizmor: no workflow files' -- env PATH="$P" bash "$SC" "$T/empty"
expect "no workflow files: not-applicable note, no INCOMPLETE" 0 'n/a actionlint: no workflow files, not applicable' -- env PATH="$P" bash "$SC" --allow-skip "$T/nowf"
bash "$SC" "$T/nowf" 2>&1 | grep -q '^INCOMPLETE:.*actionlint' && bad "no workflows counted as skipped" || ok "no workflows not counted as skipped"
expect "zizmor failure beats INCOMPLETE" 1 'FAIL zizmor' -- env PATH="$P" FAKE_FAIL=zizmor bash "$SC" "$T/repo"
expect "actionlint failure fails the gate" 1 'FAIL actionlint' -- env PATH="$P" FAKE_FAIL=actionlint bash "$SC" "$T/repo"
expect "scorecard failure fails the gate" 1 'FAIL scorecard' -- env PATH="$P" FAKE_FAIL=scorecard bash "$SC" --scorecard acme/widget "$T/repo"
expect "scorecard on a non-git DIR without --scorecard is SKIPPED with the reason" 3 'SKIPPED scorecard: DIR is not a git repo' -- env PATH="$P" bash "$SC" "$T/repo"
: >"$FAKE_LOG"; env PATH="$P" bash "$SC" --allow-skip "$T/repo" >/dev/null 2>&1
grep -q '^scorecard' "$FAKE_LOG" && bad "scorecard ran on a non-git DIR" || ok "scorecard not invoked on a non-git DIR"
: >"$FAKE_LOG"
expect "scorecard runs for a named repo" 0 'ok scorecard' -- env PATH="$P" bash "$SC" --scorecard acme/widget --allow-skip "$T/repo"
grep -q 'scorecard --repo=github.com/acme/widget' "$FAKE_LOG" && ok "scorecard got repo arg" || bad "scorecard arg"
grep -q '^actionlint' "$FAKE_LOG" && grep -q '^zizmor' "$FAKE_LOG" && ok "zizmor+actionlint ran" || bad "ci tools ran"
expect "fully run, all clean: exit 0" 0 'ok scorecard' -- env PATH="$P" OSV_JSON='{"results":[]}' OSV_RC=0 bash "$SC" --online --scorecard acme/widget "$T/repo"

# --- scorecard local mode: no --scorecard and DIR is a git repo -> offline subset on an export of HEAD ---
ROOTP=$(cd "$T/gitrepo" && pwd -P)
CHECKS=Binary-Artifacts,Dangerous-Workflow,Dependency-Update-Tool,License,Packaging,Pinned-Dependencies,SAST,Security-Policy,Token-Permissions
: >"$FAKE_LOG"
o=$(env PATH="$P" TMPDIR="$T/xtmp" bash "$SC" --allow-skip "$T/gitrepo" 2>&1) && r=0 || r=$?
[ "$r" = 0 ] && printf '%s' "$o" | grep -q 'ok scorecard (local export of HEAD in' && ok "git DIR without --scorecard: scorecard runs locally" || bad "local run (rc=$r): $o"
printf '%s' "$o" | grep -q "ok scorecard (local export of HEAD in $ROOTP;" && ok "root DIR: ok line names the repo root, no subdirectory note" || bad "root scope line: $o"
printf '%s' "$o" | grep -q 'partial view, not comparable with a public Scorecard score' && ok "ok line says local mode is a partial view" || bad "partial view wording: $o"
sl=$(grep '^scorecard ' "$FAKE_LOG" || true)
[ "$(printf '%s' "$sl" | sed -n 's/.*--checks=\([^ ]*\).*/\1/p')" = "$CHECKS" ] && ok "local mode passes exactly the offline check list" || bad "local check list: $sl"
printf '%s' "$sl" | grep -q 'Vulnerabilities\|Fuzzing' && bad "local mode asked for Vulnerabilities or Fuzzing" || ok "local mode never asks for Vulnerabilities or Fuzzing"
printf '%s' "$sl" | grep -q -- '--show-details' && ok "local mode shows details" || bad "no --show-details"
printf '%s' "$sl" | grep -q -- '--repo' && bad "local mode used the remote --repo" || ok "local mode makes no remote --repo call"
printf '%s' "$sl" | grep -q -- "--local=$T/xtmp/supply-chain-sc\." && ok "export lives under TMPDIR" || bad "export dir: $sl"
grep -qx 'scorecard-sees ./tracked.txt' "$FAKE_LOG" && ok "export holds tracked files" || bad "tracked file missing from export"
grep -q 'untracked.bin' "$FAKE_LOG" && bad "export leaked an untracked file" || ok "export has no untracked file"
[ -z "$(ls -A "$T/xtmp")" ] && ok "export removed after the run" || bad "export left behind"
: >"$FAKE_LOG"
expect "local scorecard failure fails the gate" 1 'FAIL scorecard' -- env PATH="$P" TMPDIR="$T/xtmp" FAKE_FAIL=scorecard bash "$SC" --allow-skip "$T/gitrepo"
[ -z "$(ls -A "$T/xtmp")" ] && ok "export removed after a failed run" || bad "export left behind after failure"
: >"$FAKE_LOG"
expect "subdirectory DIR scores the repo root and says so" 0 "ok scorecard (local export of HEAD in $ROOTP, DIR is a subdirectory so the whole repo is scored;" -- env PATH="$P" bash "$SC" --allow-skip "$T/gitrepo/sub"
grep -qx 'scorecard-sees ./tracked.txt' "$FAKE_LOG" && grep -qx 'scorecard-sees ./sub/inner.txt' "$FAKE_LOG" && ok "subdirectory DIR exports the whole repo" || bad "subdirectory export"
: >"$FAKE_LOG"
expect "git repo with no commit: scorecard SKIPPED" 3 'SKIPPED scorecard: git archive HEAD failed' -- env PATH="$P" TMPDIR="$T/xtmp" bash "$SC" "$T/nocommit"
grep -q '^scorecard' "$FAKE_LOG" && bad "scorecard ran on an empty export" || ok "scorecard not invoked without a commit"
[ -z "$(ls -A "$T/xtmp")" ] && ok "export removed after a skipped run" || bad "export left behind after skip"
expect "unwritable TMPDIR: scorecard SKIPPED, not run" 3 'SKIPPED scorecard: mktemp failed' -- env PATH="$P" TMPDIR="$T/no-such-dir" bash "$SC" "$T/gitrepo"
grep -q '^scorecard' "$FAKE_LOG" && bad "scorecard ran without an export" || ok "scorecard not invoked without an export dir"
expect "git DIR, scorecard not installed: SKIPPED not installed" 3 'SKIPPED scorecard: not installed' -- env PATH="$T/sys" /bin/bash "$SC" "$T/gitrepo"
: >"$FAKE_LOG"
expect "--scorecard in a git DIR stays remote" 0 'ok scorecard' -- env PATH="$P" bash "$SC" --scorecard acme/widget --allow-skip "$T/gitrepo"
grep -q -- '--repo=github.com/acme/widget' "$FAKE_LOG" && ! grep -q -- '--local' "$FAKE_LOG" && ok "--scorecard keeps the remote scan" || bad "remote scan in a git DIR"

# --- interrupted scan: the export dir is a full copy of the tracked files, so a signal must not leave it behind ---
# The fake scorecard hangs after recording its pid; the script is signalled first, then the fake is stopped (our own pid only).
# SIGINT is not testable here: a non-interactive shell starts background jobs with it ignored.
for sig in TERM HUP; do
  env PATH="$P" TMPDIR="$T/xtmp" FAKE_HANG="$T/hang.$sig" bash "$SC" --allow-skip "$T/gitrepo" >/dev/null 2>&1 & spid=$!
  for _ in $(seq 50); do [ -s "$T/hang.$sig" ] && break; sleep 0.1; done
  [ -n "$(ls -A "$T/xtmp")" ] || bad "SIG$sig: no export dir during the scan (fixture broke)"
  kill -"$sig" "$spid" 2>/dev/null || true
  kill "$(cat "$T/hang.$sig")" 2>/dev/null || true
  wait "$spid" 2>/dev/null || true
  [ -z "$(ls -A "$T/xtmp")" ] && ok "export removed after SIG$sig mid-scan" || bad "export left behind after SIG$sig"
done

# --- partial (blobless) clone: git archive would lazy-fetch missing blobs from the promisor remote (network) ---
# The promisor here is a local file:// repo, so old code succeeds by fetching; the fixed script must refuse and skip instead.
mkdir "$T/psrc"; echo data >"$T/psrc/f.txt"; g -C "$T/psrc" init -q; g -C "$T/psrc" add -A; g -C "$T/psrc" commit -qm src
g -C "$T/psrc" config uploadpack.allowFilter true; g -C "$T/psrc" config uploadpack.allowAnySHA1InWant true
g clone -q --no-checkout --filter=blob:none "file://$T/psrc" "$T/partial"
if GIT_NO_LAZY_FETCH=1 git -C "$T/partial" cat-file -e HEAD:f.txt 2>/dev/null; then
  printf 'skip partial-clone tests: this git ignores GIT_NO_LAZY_FETCH\n'
else
  : >"$FAKE_LOG"
  expect "partial clone missing blobs: scorecard SKIPPED, names the partial clone" 3 'SKIPPED scorecard: .*partial clone' -- env PATH="$P" TMPDIR="$T/xtmp" bash "$SC" "$T/partial"
  grep -q '^scorecard' "$FAKE_LOG" && bad "scorecard ran on a partial export" || ok "scorecard not invoked on a partial clone"
  GIT_NO_LAZY_FETCH=1 git -C "$T/partial" cat-file -e HEAD:f.txt 2>/dev/null && bad "the scan lazy-fetched a blob" || ok "no blob was lazy-fetched (stays offline)"
  [ -z "$(ls -A "$T/xtmp")" ] && ok "export removed after a partial-clone skip" || bad "export left behind after partial-clone skip"
fi
exit "$fail"
