#!/usr/bin/env bash
# review_checks.sh --full keeps semgrep, bandit and ruff-security off whole files under mocks/, fixtures/, e2e/, __mocks__/ and testdata/ (REVIEW_NOISE_RE replaces the ERE,
# empty turns it off) and reports each skipped file as a not-checked row; a diff review never skips a file. bandit/ruff-security run without B404/S404 only. Stub tools log argv; hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-noise.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/semgrep" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$STUB_LOG.semgrep"; echo '{"results":[],"errors":[],"paths":{"scanned":["x"]}}'
STUB
cat >"$T/bin/bandit" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$STUB_LOG.bandit"; echo '{"results":[]}'
STUB
cat >"$T/bin/ruff" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$STUB_LOG.ruff"; echo '[]'
STUB
chmod +x "$T/bin/"*; export PATH="$T/bin:$PATH" STUB_LOG="$T/log"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
NOISE="mocks/m.py fixtures/f.py e2e/e.py __mocks__/x.py testdata/t.py pkg/mocks/deep.py"
KEEP="app/main.py app/mocks.py fixtures_api.py src/e2e-utils/x.py"
for f in $NOISE $KEEP; do mkdir -p "$(dirname "$f")"; echo 'x = 1' >"$f"; done
g add -A; g commit -q -m change
run() { rm -f "$T"/log.*; env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" $MODE --base base 2>"$T/err" >"$T/out" || true; }
has() { grep -qF -- "$1" "$T/log.$2"; } # has ARG TOOL: the tool's argv log names ARG
NREDEF=$(sed -n "s/^NRE=\${REVIEW_NOISE_RE-'\(.*\)'}.*/\1/p" "$RC")
r=0; [[ -n $NREDEF && ! Testdata/t.py =~ $NREDEF && ! app/mocks.py =~ $NREDEF && ! src/e2e-utils/x.py =~ $NREDEF && ! fixtures_api.py =~ $NREDEF && mocks/m.py =~ $NREDEF ]] || r=1; chk $r "default ERE is case-sensitive and dir-anchored: Testdata/ stays scanned (APFS cannot hold both dirs)"
MODE=--full run X=1
r=0; for f in $KEEP; do has "$f" semgrep && has "$f" bandit || r=1; done; chk $r "--full: normal, mocks.py, fixtures_api.py, e2e-utils/ are all scanned"
r=0; for f in $NOISE; do ! has "$f" semgrep && ! has "$f" bandit || r=1; done; chk $r "--full: semgrep and bandit skip all five noise dirs, nested too"
r=0; grep -q -- '--select S' "$T/log.ruff" && grep -q 'app/main.py' "$T/log.ruff" && ! grep -q -- '--select S.*\(mocks/\|fixtures/\|e2e/\|testdata/\)' "$T/log.ruff" || r=1; chk $r "--full: ruff-security skips the noise dirs"
r=0; for t in semgrep bandit ruff-security; do grep -q "$t skipped 6 file" "$T/err" || r=1; done; chk $r "--full: each tool names its skipped count on stderr"
r=0; for f in $NOISE; do grep -q "\"file\": \"$f\"" "$T/out" || r=1; done; chk $r "--full: every skipped file is a NOT CHECKED row in the report"
r=0; has '-s B404' bandit && ! has B603 bandit && grep -q -- '--ignore S404 ' "$T/log.ruff" || r=1; chk $r "bandit skips only B404 and ruff-security ignores only S404 (B603/S603 stay on)"
MODE=--full run REVIEW_NOISE_RE=
r=0; has mocks/m.py semgrep && has fixtures/f.py bandit && has testdata/t.py bandit || r=1; chk $r "--full: REVIEW_NOISE_RE empty scans the noise dirs too"
MODE=--full run 'REVIEW_NOISE_RE=(^|/)pkg/'
r=0; ! has pkg/mocks/deep.py semgrep && has mocks/m.py semgrep && has fixtures/f.py bandit || r=1; chk $r "--full: REVIEW_NOISE_RE replaces the default ERE"
r=0; grep -q 'not-checked row(s).*not read' "$T/err" || r=1; chk $r "--full: the summary says not-checked files were not read"
MODE=--full-history run X=1
r=0; for f in $NOISE $KEEP; do has "$f" semgrep && has "$f" bandit || r=1; done; chk $r "--full-history: a diff file under testdata/, e2e/, mocks/ is still scanned (no evasion)"
MODE= run X=1
r=0; for f in $NOISE $KEEP; do has "$f" semgrep && has "$f" bandit || r=1; done; chk $r "diff mode: a changed file under testdata/, e2e/, mocks/ is never skipped (no evasion)"
r=0; ! grep -q 'NOT CHECKED$' "$T/err" && ! grep -q 'noise path excluded' "$T/out" || r=1; chk $r "diff mode: nothing is reported skipped"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
