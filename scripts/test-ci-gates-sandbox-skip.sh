#!/usr/bin/env bash
# Hermetic test for record_sbx in scripts/test-ci-gates.sh: a failed capability probe (ps, pgrep, yaml, bind) AND a case log
# carrying a denial signature turn a case's FAIL into `SKIP (sandbox: <cap>)` off CI; a failed probe with no signature in the
# log, or any failed probe on CI, is a FAIL. Probes are forced by PATH stubs for ps, pgrep and python3, so the result does not
# depend on this host's sandbox. Sources only the `sandbox-probe` block of the suite. Exit 0 = all pass.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sbx-skip.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
SUITE="$ROOT/scripts/test-ci-gates.sh"
sed -n '/^# sandbox-probe:begin$/,/^# sandbox-probe:end$/p' "$SUITE" >"$WORK/block.sh"
[ -s "$WORK/block.sh" ] || { echo "FAIL  sandbox-probe block not found"; exit 1; }
mkdir -p "$WORK/bad" "$WORK/good" "$WORK/p1"
printf '#!/bin/sh\nexit 1\n' >"$WORK/bad/ps"
cp "$WORK/bad/ps" "$WORK/bad/python3"
printf '#!/bin/sh\nexit 3\n' >"$WORK/bad/pgrep"
printf '#!/bin/sh\nexit 1\n' >"$WORK/good/pgrep"
printf '#!/bin/sh\necho Mon Jan 1 00:00:00 2024\n' >"$WORK/good/ps"
printf '#!/bin/sh\nexit 0\n' >"$WORK/good/python3"
cp "$WORK/good/pgrep" "$WORK/good/python3" "$WORK/p1/"
printf '#!/bin/sh\ncase "$*" in *"-p 1") exit 1;; esac\necho Mon Jan 1 00:00:00 2024\n' >"$WORK/p1/ps"
chmod +x "$WORK"/*/ps "$WORK"/*/pgrep "$WORK"/*/python3
printf 'LOGTAIL\nPermissionError: [Errno 1] Operation not permitted\n' >"$WORK/deny.log"
printf 'LOGTAIL\nAssertionError: 1 != 2\n' >"$WORK/plain.log"

n=0 bad=0
# t <label> <expected-output-regex> <stub dir> <env words> <cap> <case rc> [log...]
t() {
  local out
  out="$(env -u CI -u GITHUB_ACTIONS $4 PATH="$WORK/$3:$PATH" bash -c "set -euo pipefail; . '$WORK/block.sh'; record_sbx $5 $6 case ${*:7}; printf 'counts %d/%d/%d\n' \$pass \$fail \$skip")"
  n=$((n + 1))
  if printf '%s\n' "$out" | grep -qE "$2"; then echo "PASS  $1"; else echo "FAIL  $1: $out"; bad=$((bad + 1)); fi
}
D="$WORK/deny.log" P="$WORK/plain.log"
for cap in ps pgrep yaml bind; do
  w=sandbox; [ "$cap" = yaml ] && w=sandbox/missing
  t "$cap: probe fails, not CI, case failed, denial in log -> SKIP, no fail" "^SKIP  case \\($w: $cap\\)\$" bad LOCAL=1 "$cap" 1 "$D"
  t "$cap: SKIP counts 0 pass/0 fail/1 skip" '^counts 0/0/1$' bad LOCAL=1 "$cap" 1 "$D"
  t "$cap: SKIP prints the log tail" '^LOGTAIL$' bad LOCAL=1 "$cap" 1 "$D"
  t "$cap: CI= and GITHUB_ACTIONS= empty are not CI -> SKIP" '^counts 0/0/1$' bad "CI= GITHUB_ACTIONS=" "$cap" 1 "$D"
  t "$cap: probe fails, case passed -> PASS" '^PASS  case$' bad LOCAL=1 "$cap" 0 "$D"
  t "$cap: probe fails, no denial signature in log -> FAIL, not SKIP" '^counts 0/1/0$' bad LOCAL=1 "$cap" 1 "$P"
  t "$cap: probe fails, no log at all -> FAIL" '^counts 0/1/0$' bad LOCAL=1 "$cap" 1
  t "$cap: signature in the second of two logs -> SKIP" '^counts 0/0/1$' bad LOCAL=1 "$cap" 1 "$P" "$D"
  t "$cap: probe fails on CI=true, case failed -> FAIL" "^FAIL  case \\(probe failed: $cap\\)\$" bad CI=true "$cap" 1 "$D"
  t "$cap: probe fails on CI=true, case passed -> still FAIL (fail closed)" '^counts 0/1/0$' bad CI=true "$cap" 0
  t "$cap: probe fails under GITHUB_ACTIONS -> FAIL, never SKIP" '^counts 0/1/0$' bad GITHUB_ACTIONS=true "$cap" 1 "$D"
  t "$cap: probe works, case failed -> real FAIL, not SKIP" '^counts 0/1/0$' good LOCAL=1 "$cap" 1 "$D"
  t "$cap: probe works, FAIL prints the log tail" '^LOGTAIL$' good LOCAL=1 "$cap" 1 "$D"
  t "$cap: probe works, case passed -> PASS" '^counts 1/0/0$' good CI=true "$cap" 0
done
# each denial signature alone is enough; the probe cache is never pre-seeded from the environment
for sig in 'x: Operation not permitted' 'sh: ps: not permitted' 'PermissionError' "ModuleNotFoundError: No module named 'yaml'" 'EPERM' 'orphans=COULD_NOT_CHECK (ps failed)' 'pgrep failed rc=3' 'pgrep: Cannot get process list'; do
  printf '%s\n' "$sig" >"$WORK/sig.log"
  t "signature '$sig' -> SKIP" '^counts 0/0/1$' bad LOCAL=1 ps 1 "$WORK/sig.log"
done
t "env-seeded _cap_ps=ok is ignored (probe still runs)" '^counts 0/0/1$' bad _cap_ps=ok ps 1 "$D"
t "ps probe also reads pid 1: a denied 'ps -p 1' fails the cap" '^counts 0/0/1$' p1 LOCAL=1 ps 1 "$D"
# pgrep probe name fits macOS's 15-char process-name match
pn="$(sed -n 's/.*pgrep -x \([^ ]*\) >.*/\1/p' "$WORK/block.sh" | head -1)"
n=$((n + 1)); if [ -n "$pn" ] && [ "${#pn}" -le 15 ]; then echo "PASS  pgrep probe name '$pn' <= 15 chars"; else echo "FAIL  pgrep probe name '$pn'"; bad=$((bad + 1)); fi
# s <label> <expected-regex> <expected-rc> <pass> <fail> <skip> [DCR_NO_SKIP]: sbx_summary line and exit code
s() {
  local out rc
  out="$(env DCR_NO_SKIP="${7:-}" bash -c ". '$WORK/block.sh'; pass=$4 fail=$5 skip=$6; sbx_summary")"; rc=$?
  n=$((n + 1))
  if printf '%s\n' "$out" | grep -qE "$2" && [ "$rc" -eq "$3" ]; then echo "PASS  $1"; else echo "FAIL  $1: rc=$rc $out"; bad=$((bad + 1)); fi
}
s "summary line, skips alone exit 0" '^3 pass / 0 fail / 2 skipped\(sandbox\)$' 0 3 0 2
s "a fail exits 1" '^3 pass / 1 fail / 0 skipped\(sandbox\)$' 1 3 1 0
s "DCR_NO_SKIP=1 with a skip exits 1" '^3 pass / 0 fail / 2 skipped\(sandbox\)$' 1 3 0 2 1
s "DCR_NO_SKIP=1 with no skip exits 0" '^3 pass / 0 fail / 0 skipped\(sandbox\)$' 0 3 0 0 1
# the suite ends by calling sbx_summary, so its summary line and exit status are the ones tested above
n=$((n + 1)); if [ "$(grep -v '^$' "$SUITE" | tail -1)" = sbx_summary ]; then echo "PASS  suite's last line is sbx_summary"; else echo "FAIL  suite's last line is not sbx_summary"; bad=$((bad + 1)); fi
n=$((n + 1)); if grep -qF "printf '\\n%d pass / %d fail / %d skipped(sandbox)\\n' \"\$pass\" \"\$fail\" \"\$skip\"" "$SUITE"; then echo "PASS  summary printf pinned"; else echo "FAIL  summary printf changed"; bad=$((bad + 1)); fi
echo "Tests: $((n - bad))/$n"
[ "$bad" -eq 0 ]
