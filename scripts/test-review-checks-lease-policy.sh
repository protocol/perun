#!/usr/bin/env bash
# review_checks.sh heavy lease: an unusable lease policy (perun_policy.py exits 2) must mean "run without a lease", never a
# false "heavy lease full" skip for semgrep/trivy, in diff mode and --full. Also covers the closing "missing tools" row (tool + hint).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-lease.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/repo"
cat >"$T/bin/semgrep" <<'S'
#!/usr/bin/env bash
echo ran >>"$SG_LOG"; echo '{"results":[]}'
S
cat >"$T/bin/trivy" <<'S'
#!/usr/bin/env bash
echo ran >>"$TV_LOG"; echo '{"Results":[]}'
S
chmod +x "$T/bin"/*
export SG_LOG="$T/sg.log" TV_LOG="$T/tv.log"
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
echo x >app.txt && g add . && g commit -q -m files
: >"$T/notadir" # a file where the lease dir should be: heavy-acquire raises OSError -> rc=2
export PERUN_HEAVY_DIR="$T/notadir"
run() { : >"$SG_LOG"; : >"$TV_LOG"; PATH="$T/bin:$PATH" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }

for mode in "" --full; do
  run $mode
  r=0; [ -s "$SG_LOG" ] && [ -s "$TV_LOG" ] || r=1; chk $r "policy rc=2 ${mode:-diff}: semgrep and trivy both ran"
  r=0; ! grep -q 'heavy lease full' "$T/err" || r=1; chk $r "policy rc=2 ${mode:-diff}: no false 'heavy lease full'"
done
r=0; [ "$(grep -c 'not run: lease (policy rc=2)' "$T/err")" = 1 ] || r=1; chk $r "policy failure reported once"

# Stub policy tree: "full" is exit 1 AND stdout FULL; a crash (traceback, exit 1) is a policy failure, not a full lease.
SK="$T/sk"; mkdir -p "$SK/deep-code-review/scripts" "$SK/agentic-delivery/scripts"
cp "$RC" "$SK/deep-code-review/scripts/"; cp -R "$(dirname "$RC")/../templates" "$SK/deep-code-review/templates"
stubrun() { : >"$SG_LOG"; : >"$TV_LOG"; printf '%s\n' "$1" >"$SK/agentic-delivery/scripts/perun_policy.py"
  PATH="$T/bin:$PATH" REVIEW_LEASE_WAIT=0 REVIEW_LEASE_FULL=skip bash "$SK/deep-code-review/scripts/review_checks.sh" --base base 2>"$T/err" >"$T/out"; }
stubrun 'raise ModuleNotFoundError("boom")'
r=0; [ -s "$SG_LOG" ] && [ -s "$TV_LOG" ] && ! grep -q 'heavy lease full' "$T/err" || r=1; chk $r "policy traceback (exit 1): scanners run, no 'heavy lease full'"
stubrun 'import sys; print("FULL"); sys.exit(1)'
r=0; [ ! -s "$SG_LOG" ] && [ ! -s "$TV_LOG" ] && grep -q 'semgrep: heavy lease full\|semgrep (heavy lease full)' "$T/err" || r=1; chk $r "explicit FULL (exit 1), REVIEW_LEASE_FULL=skip: scanners skipped as 'heavy lease full'"
stubrun 'import os; print(os.getppid())'
r=0; [ -s "$SG_LOG" ] && [ -s "$TV_LOG" ] || r=1; chk $r "exit 0: scanners run under the lease"

# missing tools: one closing row with a hint per tool (skipped when the host has a real trivy/semgrep on the minimal PATH)
if ! PATH="/usr/bin:/bin" sh -c 'command -v trivy || command -v semgrep' >/dev/null; then
  PATH="/usr/bin:/bin" bash "$RC" --base base 2>"$T/err" >/dev/null || true
  row=$(grep '^review_checks: missing tools:' "$T/err" || true)
  r=0; [ "$(grep -c '^review_checks: missing tools:' "$T/err")" = 1 ] && [[ $row == *"semgrep (install: "* && $row == *"trivy (install: "* ]] || r=1
  chk $r "one 'missing tools' row lists semgrep and trivy with hints"
  r=0; [ "$(tail -n1 "$T/err")" = "$row" ] || r=1; chk $r "'missing tools' row is the last line"
else chk 0 "missing tools (skipped: real scanner on the minimal PATH)"; fi
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
