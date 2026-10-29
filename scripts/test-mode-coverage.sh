#!/usr/bin/env bash
# Tests for per-mode coverage: validate_status_claims.py flags a findings claim for a review mode that has no
# `mode: ran (N files)` / `mode: NOT RUN (reason)` entry (a skipped mode must never read as 0 findings), and
# review_checks.sh lists a timed-out or crashed analyzer under NOT RUN, not under "ran". Hermetic: stubs, temp dirs.
set -uo pipefail
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1  # no host gitconfig (hooks, signing, aliases) in the throwaway repo
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$ROOT/.claude/skills/deep-code-review"
V="$D/scripts/validate_status_claims.py"
RC="$D/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-modecov.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
flags() { printf '%s\n' "$1" >"$T/r.md"; python3 -I "$V" --file "$T/r.md" >"$T/o" 2>&1; }  # rc 1 = flagged
red() { flags "$1"; local rc=$?; [ "$rc" -eq 1 ] && grep -q "$2" "$T/o"; chk $? "flagged: $3"; }
green() { flags "$1"; chk $? "clean: $2"; }

# the incident: perf ran, security was skipped, the hand-back said "security 0 new"
red $'security 0 new\nCoverage: perf: ran (4 files)' "no coverage entry" "security 0 new with only perf covered"
red $'security: NOT RUN (no scanner)\nsecurity: 0 findings' "says NOT RUN" "0 findings beside a NOT RUN entry"
red $'perf: 2 findings' "mode 'perf' with no coverage entry" "a positive count needs coverage too"
red $'No security findings.' "mode 'security'" "'no security findings' with no entry"
red $'privacy clean\nprivacy: ran' "malformed coverage entry" "bare 'ran' is not an entry (and the claim is unbacked)"
red $'security: ran (0 files)' "malformed coverage entry" "ran (0 files) is not coverage"
red $'security: NOT RUN' "malformed coverage entry" "NOT RUN needs a reason"
red $'security: NOT RUN ()' "malformed coverage entry" "NOT RUN needs a non-blank reason"
red $'a11y: ran (3 files) | a11y: NOT RUN (no browser)\na11y none' "says NOT RUN" "partial run is not a clean claim"
red $'| security | 0 new |' "mode 'security'" "a table cell claim"
red $'performance: 0 new\nsecurity: ran (2 files)' "mode 'perf'" "alias: performance is perf"
red $'security: NOT RUN (reason)' "malformed coverage entry" "a placeholder reason is not a reason"
for ph in x n/a none; do red "security: NOT RUN ($ph)" "malformed coverage entry" "placeholder reason '$ph'"; done
# natural phrasings of the same false claim
for c in "security: no issues" "security: no findings" "security: nothing found" "security: 0 critical" "security findings: 0" \
  "Security — all clear" "security: passed" "Findings: security 0, perf 2" "security: **0** new" "0 new security findings" \
  "No new security findings" "No security concerns" "- **Security**: clean" "1. security: ok"; do
  red "$c" "mode 'security' with no coverage entry" "natural claim: $c"
done
red "perf: no regressions" "mode 'perf' with no coverage entry" "natural claim: perf: no regressions"

green $'security 0 new\nCoverage: security: ran (12 files) | perf: NOT RUN (no profiler)' "claim backed by a ran entry"
green $'Coverage: security: NOT RUN (none of the scanners are installed, clean room image)' "NOT RUN reason words are not a claim"
green $'Coverage: perf: ran (4 files), ux: NOT RUN (no browser)\nperf: 2 findings' "comma-joined entries; claim on the ran mode"
green $'performance: 0 new\nCoverage: perf: ran (9 files)' "alias backs performance"
green $'Tests: 12/12 pass. Verdict: Approve.' "no mode claim, no entry needed"
green $'Coverage: security: ran (12 files, 0 findings), perf: ran (1,200 files)\nsecurity: 0 new' "ran (N files, M findings) and thousands separators"
green $'| security | ran (3 files) | perf | NOT RUN (no profiler) |\n| security | 0 new |' "table entries back a table claim"
green $'```\nsecurity: 0 new\n```\nTests: 1/1' "a fenced code block is quoted, not a claim"
green $'### B. Security — application (OWASP Top 10:2025)' "a standard's version number is not a count"
green $'We ran no security scan today, security-sensitive paths untouched.' "prose that is not at a claim start"
green "$(cat "$D/references/example-review-report.md")" "the shipped example report"
green "$(cat "$ROOT/docs/example-review-report.md")" "the canonical example report backs its mode claims"

# review_checks.sh: a timeout or crash lands under NOT RUN and not under "ran"
mkdir "$T/stub" "$T/repo"
printf '#!/usr/bin/env bash\nexit 124\n' >"$T/stub/gitleaks"  # 124 = the timebox's exit
for t in semgrep trivy; do printf '#!/usr/bin/env bash\necho "{\\"results\\":[],\\"Results\\":[]}"\n' >"$T/stub/$t"; done  # no network
chmod +x "$T/stub"/*
echo '{}' >"$T/policy.json"
export PERUN_HEAVY_DIR="$T/heavy0" PERUN_POLICY="$T/policy.json"  # never touch the real lease dir or policy
cd "$T/repo" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base \
  && printf 'x\n' >app.txt && git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
PATH="$T/stub:$PATH" bash "$RC" --base base >"$T/out" 2>"$T/err"
ran=$(sed -n 's/.*analyzers ran: \([^;]*\);.*/\1/p' "$T/err"); [ -n "$ran" ]; chk $? "the ran list is non-empty (the not-ran assertions are not vacuous)"
grep -qw gitleaks <<<"$ran"; [ $? -ne 0 ]; chk $? "timed-out gitleaks is not listed as ran"
grep -qE 'NOT RUN: .*gitleaks \(timeout [0-9]+s\)' "$T/err"; chk $? "timed-out gitleaks is listed under NOT RUN with the reason"
printf '#!/usr/bin/env bash\nexit 2\n' >"$T/stub/gitleaks"
PATH="$T/stub:$PATH" bash "$RC" --base base >"$T/out" 2>"$T/err"
grep -qE 'NOT RUN: .*gitleaks \(exit 2\)' "$T/err"; chk $? "crashed gitleaks is listed under NOT RUN"

# a tool that fails on one file and passes on the next stays NOT RUN; N failing files are one NOT RUN entry and one not-checked row
printf 'y\n' >b.txt && git add . && git -c user.email=t@example.com -c user.name=t commit -q -m more
printf '#!/usr/bin/env bash\ncase "$*" in *app.txt*) exit 124 ;; esac\nexit 0\n' >"$T/stub/gitleaks"
PATH="$T/stub:$PATH" bash "$RC" --base base >"$T/out" 2>"$T/err"
ran=$(sed -n 's/.*analyzers ran: \([^;]*\);.*/\1/p' "$T/err"); grep -qw gitleaks <<<"$ran"; [ $? -ne 0 ]; chk $? "a later good file does not re-list a failed tool as ran"
grep -q 'not-checked' "$T/out" && grep -q '"tool": "gitleaks"' "$T/out"; chk $? "a skipped non-hub tool lands a not-checked row on stdout"
printf '#!/usr/bin/env bash\nexit 124\n' >"$T/stub/gitleaks"
PATH="$T/stub:$PATH" bash "$RC" --base base >"$T/out" 2>"$T/err"
[ "$(grep '^review_checks: NOT RUN:' "$T/err" | grep -o 'gitleaks (timeout' | wc -l)" -eq 1 ] && [ "$(grep -c '"rule": "not-checked"' "$T/out")" -eq 1 ]; chk $? "two failing files give one NOT RUN entry and one not-checked row"
# a tool that is merely not installed is listed under "skipped (not installed)", never under NOT RUN
rm "$T/stub/gitleaks"; printf '#!/usr/bin/env bash\nexit 0\n' >"$T/stub/semgrep"
PATH="$T/stub:/usr/bin:/bin" bash "$RC" --base base >"$T/out" 2>"$T/err"
if PATH="/usr/bin:/bin" sh -c 'command -v gitleaks' >/dev/null; then chk 0 "not-installed split (skipped: real gitleaks on the minimal PATH)"
else grep -q 'skipped (not installed): .*gitleaks' "$T/err" && ! grep -q 'NOT RUN: .*gitleaks' "$T/err"; chk $? "not-installed gitleaks is listed as not installed, not NOT RUN"; fi

echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
