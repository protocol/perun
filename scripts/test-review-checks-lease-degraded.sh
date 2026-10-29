#!/usr/bin/env bash
# review_checks.sh with the heavy lease FULL after the wait: heavy scanners must run degraded (nice 19, semgrep --jobs 1,
# trivy --parallel 1, labelled in the "analyzers ran" summary, lease never taken) instead of being skipped, unless
# REVIEW_LEASE_FULL=skip restores the skip. Light tools (hadolint) are never niced. A free lease changes nothing.
# Degraded edge cases: nice missing or warning (sandbox setpriority EPERM) -> run without nice and without the label; an
# unsupported single-worker flag -> one retry without it; the perl timebox (no timeout(1)) must report an exec failure.
# Hermetic: PATH is $T/bin (stubs) plus $T/sys (symlinks to only the system binaries the script needs), so no host scanner,
# nice, timeout or gtimeout is ever picked up and the perl timebox path is always the one under test.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-lease-degraded.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/repo"
mkdir "$T/sys" "$T/nonice" "$T/nicewarn" "$T/bad"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl true sort uniq tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") && ln -s "$p" "$T/sys/$b" # type -P: path only (command -v names builtins like true bare)
done
# nice shim: assert the exact "-n 19" prefix, log it, then run the wrapped command. NICE_WARN=1 mimics the sandbox
# setpriority EPERM warning (stderr noise, rc 0). The shim sits in its own dir so a case can leave nice off PATH.
cat >"$T/nice-shim" <<'S'
#!/usr/bin/env bash
[ "$1 $2" = "-n 19" ] || { echo "bad nice args: $*" >&2; exit 99; }
shift 2; echo "$*" >>"$NICE_LOG"; [ -z "${NICE_WARN:-}" ] || echo "nice: setpriority: Operation not permitted" >&2; exec "$@"
S
chmod +x "$T/nice-shim"; ln -s "$T/nice-shim" "$T/bin/nice"
# stub scanners; with REJECT_FLAGS set they refuse the degraded single-worker flags like an old version would
for t in semgrep trivy hadolint; do
  out='{"results":[]}'; [ "$t" = trivy ] && out='{"Results":[]}'; [ "$t" = hadolint ] && out='[]'
  printf '#!/usr/bin/env bash\necho "$*" >>"$LOG_%s"\ncase " $* " in *" --jobs "*|*" --parallel "*) [ -z "${REJECT_FLAGS:-}" ] || { echo "error: unrecognized arguments" >&2; exit 2; } ;; esac\necho %q\n' "$t" "$out" >"$T/bin/$t"
done
# gitleaks whose interpreter does not exist: found by command -v, but exec fails
printf '#!/nonexistent/interp\n' >"$T/bad/gitleaks"
chmod +x "$T/bin"/* "$T/bad/gitleaks"
export NICE_LOG="$T/nice.log" LOG_semgrep="$T/sg.log" LOG_trivy="$T/tv.log" LOG_hadolint="$T/hl.log" PP_LOG="$T/pp.log"
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
echo x >app.txt && echo 'FROM scratch' >Dockerfile && g add . && g commit -q -m files

# Stub policy tree: FULL is exit 1 AND stdout FULL; exit 0 is a free lease. Every call is logged to $PP_LOG.
SK="$T/sk"; mkdir -p "$SK/deep-code-review/scripts" "$SK/agentic-delivery/scripts"
cp "$RC" "$SK/deep-code-review/scripts/"; cp -R "$(dirname "$RC")/../templates" "$SK/deep-code-review/templates"
stubrun() { # $1 = policy python body; remaining env goes through `env`
  : >"$NICE_LOG"; : >"$LOG_semgrep"; : >"$LOG_trivy"; : >"$LOG_hadolint"; : >"$PP_LOG"
  printf 'import os, sys\nopen(os.environ["PP_LOG"], "a").write(sys.argv[1] + "\\n")\n%s\n' "$1" >"$SK/agentic-delivery/scripts/perun_policy.py"; shift
  env PATH="$T/bin:$T/sys" REVIEW_LEASE_WAIT=0 "$@" bash "$SK/deep-code-review/scripts/review_checks.sh" --base base 2>"$T/err" >"$T/out"; }
FULL='print("FULL"); sys.exit(1)'
summary() { grep '^review_checks: .*analyzers ran:' "$T/err"; }

stubrun "$FULL"
r=0; grep -q -- '--jobs 1' "$LOG_semgrep" && ! grep -q 'semgrep (heavy lease full)' "$T/err" || r=1; chk $r "lease FULL: semgrep ran with --jobs 1, not skipped"
r=0; grep -q -- '--parallel 1' "$LOG_trivy" || r=1; chk $r "lease FULL: trivy ran with --parallel 1"
r=0; grep -q ' semgrep ' "$NICE_LOG" && grep -q '^trivy ' "$NICE_LOG" || r=1; chk $r "lease FULL: semgrep and trivy ran under nice -n 19"
r=0; [ -s "$LOG_hadolint" ] && ! grep -q hadolint "$NICE_LOG" || r=1; chk $r "lease FULL: light tool (hadolint) ran, not niced"
r=0; s=$(summary); [[ $s == *"semgrep (degraded: lease full, nice 19, 1 worker)"* && $s == *"trivy (degraded: lease full, nice 19, 1 worker)"* ]] || r=1; chk $r "lease FULL: summary labels semgrep and trivy degraded"
r=0; [[ $s == *"hadolint"* && $s != *"hadolint ("* ]] || r=1; chk $r "lease FULL: hadolint listed without a degraded label"
r=0; [ "$(grep -c . "$PP_LOG")" = 1 ] && [ "$(cat "$PP_LOG")" = heavy-acquire ] || r=1; chk $r "lease FULL: one acquire, no re-acquire, no release (lease never taken)"
r=0; grep -q 'heavy scanners run degraded without the lease' "$T/err" || r=1; chk $r "lease FULL: degraded mode announced on stderr"

stubrun "$FULL" REVIEW_LEASE_FULL=skip
r=0; [ ! -s "$LOG_semgrep" ] && [ ! -s "$LOG_trivy" ] && [ ! -s "$NICE_LOG" ] && grep -q 'semgrep (heavy lease full)' "$T/err" || r=1; chk $r "REVIEW_LEASE_FULL=skip: scanners skipped as 'heavy lease full'"
r=0; ! summary | grep -q degraded || r=1; chk $r "REVIEW_LEASE_FULL=skip: no degraded label"
r=0; [ -s "$LOG_hadolint" ] || r=1; chk $r "REVIEW_LEASE_FULL=skip: light tool still ran"

stubrun 'import os; print(os.getppid())'
r=0; [ -s "$LOG_semgrep" ] && [ -s "$LOG_trivy" ] && [ ! -s "$NICE_LOG" ] && ! grep -q -e '--jobs' -e '--parallel' "$LOG_semgrep" "$LOG_trivy" || r=1; chk $r "free lease: scanners run at normal priority with no single-worker flags"
r=0; ! summary | grep -q degraded && grep -qx heavy-release "$PP_LOG" || r=1; chk $r "free lease: no degraded label, lease released"
# nice absent from PATH (and a probe that fails): scanners still run, single-worker flags stay, no "nice 19" in the label.
rm "$T/bin/nice"
stubrun "$FULL"
r=0; grep -q -- '--jobs 1' "$LOG_semgrep" && grep -q -- '--parallel 1' "$LOG_trivy" && [ ! -s "$NICE_LOG" ] || r=1; chk $r "nice missing: scanners ran, no nice wrapper"
r=0; s=$(summary); [[ $s == *"semgrep (degraded: lease full, 1 worker)"* && $s == *"trivy (degraded: lease full, 1 worker)"* && $s != *"nice 19"* ]] || r=1; chk $r "nice missing: label drops nice 19, keeps 1 worker"

# nice prints a setpriority warning: the probe sees stderr noise, so nice is dropped (only the probe itself ran through it).
ln -s "$T/nice-shim" "$T/bin/nice"
stubrun "$FULL" NICE_WARN=1
r=0; [ -s "$LOG_semgrep" ] && [ -s "$LOG_trivy" ] && ! grep -qE 'semgrep|trivy' "$NICE_LOG" || r=1; chk $r "nice warns: scanners ran without nice (probe only)"
r=0; s=$(summary); [[ $s == *"semgrep (degraded: lease full, 1 worker)"* && $s != *"nice 19"* ]] || r=1; chk $r "nice warns: label drops nice 19"

# stub scanners reject the single-worker flags: one retry without the flag, scanner not reported not-run, label drops 1 worker.
stubrun "$FULL" REJECT_FLAGS=1
r=0; [ "$(grep -c -- '--jobs 1' "$LOG_semgrep")" = 1 ] && [ "$(grep -vc -- '--jobs' "$LOG_semgrep")" -ge 1 ] || r=1; chk $r "flag rejected: semgrep retried once without --jobs 1"
r=0; [ "$(grep -c -- '--parallel 1' "$LOG_trivy")" = 1 ] && [ "$(grep -vc -- '--parallel' "$LOG_trivy")" -ge 1 ] || r=1; chk $r "flag rejected: trivy retried once without --parallel 1"
r=0; ! grep -qE 'not run: (semgrep|trivy)' "$T/err" || r=1; chk $r "flag rejected: retry succeeded, no not-run line"
r=0; s=$(summary); [[ $s == *"semgrep (degraded: lease full, nice 19)"* && $s == *"trivy (degraded: lease full, nice 19)"* ]] || r=1; chk $r "flag rejected: label keeps nice 19, drops 1 worker"

# perl timebox (no timeout(1) on PATH): a scanner that cannot be exec'd must read as not-run, never as a clean scan.
stubrun 'import os; print(os.getppid())' PATH="$T/bad:$T/bin:$T/sys"
r=0; grep -q 'not run: gitleaks (exit 127)' "$T/err" || r=1; chk $r "perl timebox exec failure: gitleaks reported not run (exit 127), not clean"
r=0; grep -q . "$LOG_semgrep" && [ -s "$LOG_trivy" ] || r=1; chk $r "perl timebox exec failure: other scanners unaffected"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
