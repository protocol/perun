#!/usr/bin/env bash
# review_checks.sh --full skips a path matching REVIEW_NOISE_RE (here docs/bench/, a bench output corpus) for semgrep and the jq JSON check and reports each file NOT CHECKED; by default docs/bench/ is scanned, and diff mode never skips. Stub tools log argv; hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-benchnoise.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/semgrep" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$STUB_LOG.semgrep"; echo '{"results":[],"errors":[],"paths":{"scanned":["x"]}}'
STUB
cat >"$T/bin/jq" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$STUB_LOG.jq"
STUB
chmod +x "$T/bin/"*; export PATH="$T/bin:$PATH" STUB_LOG="$T/log"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
for f in docs/bench/run1/a.json docs/bench/run1/b.py app/c.json app/d.py docs/benchmark.json; do mkdir -p "$(dirname "$f")"; echo '{}' >"$f"; done
g add -A; g commit -q -m change
run() { rm -f "$T"/log.*; env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" $MODE --base base 2>"$T/err" >"$T/out" || true; }
has() { grep -qF -- "$1" "$T/log.$2"; }
NR='REVIEW_NOISE_RE=(^|/)docs/bench/'
MODE=--full run X=1
r=0; has docs/bench/run1/b.py semgrep && has docs/bench/run1/a.json jq || r=1; chk $r "--full by default: docs/bench/ is scanned like any other path"
MODE=--full run "$NR"
r=0; has app/d.py semgrep && ! has docs/bench/run1/b.py semgrep || r=1; chk $r "--full with REVIEW_NOISE_RE: semgrep scans app/, skips docs/bench/"
r=0; has app/c.json jq && has docs/benchmark.json jq && ! has docs/bench/run1/a.json jq || r=1; chk $r "--full with REVIEW_NOISE_RE: jq skips docs/bench/ only (docs/benchmark.json still checked)"
r=0; for f in docs/bench/run1/a.json docs/bench/run1/b.py; do grep -q "\"file\": \"$f\"" "$T/out" || r=1; done; chk $r "--full with REVIEW_NOISE_RE: skipped bench files are NOT CHECKED rows"
r=0; grep -q 'jq skipped 1 file' "$T/err" || r=1; chk $r "--full with REVIEW_NOISE_RE: jq names its skipped count on stderr"
MODE= run "$NR"
r=0; has docs/bench/run1/a.json jq && has docs/bench/run1/b.py semgrep || r=1; chk $r "diff mode: a changed docs/bench file is never skipped"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
