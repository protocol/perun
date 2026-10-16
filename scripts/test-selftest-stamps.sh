#!/usr/bin/env bash
#
# Tests the DCR_SELFTEST_STAMPS verdict cache of the shipped gate runner
# (.claude/skills/deep-code-review/templates/dcr-gates.sh).
#
# WHY: the runner proves every gate script fires (`--selftest`) on EVERY invocation. A suite that calls the runner
# dozens of times therefore re-runs the same idempotent selftests dozens of times: on CI that repetition was most of
# the 10m27s "Gate helper self-tests" step (docs/bench/pipeline-1016/). With DCR_SELFTEST_STAMPS set, a selftest that
# PASSED for a script with the same bytes is not run again under that stamp directory. Unset, behaviour is unchanged.
#
# The runner runs against a throwaway fixture whose gate scripts are stubs that log each call, so this proves the
# cache logic itself (fast, hermetic), not the gates.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT/.claude/skills/deep-code-review/templates/dcr-gates.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-selftest-stamps.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null

pass=0
fail=0
record() { # record <0|1> <label>
  if [ "$1" -eq 0 ]; then printf 'PASS  %s\n' "$2"; pass=$((pass + 1)); else printf 'FAIL  %s\n' "$2"; fail=$((fail + 1)); fi
}

STUBS="fix_class_gate binaries_gate parity_differ token_differ"
fx="$WORK/repo"
mkdir -p "$fx/scripts" "$fx/.claude/skills/deep-code-review/scripts"
cp "$RUNNER" "$fx/scripts/dcr-gates.sh"
printf '# stub skill\n' >"$fx/.claude/skills/deep-code-review/SKILL.md"
for s in $STUBS; do
  cat >"$fx/.claude/skills/deep-code-review/scripts/$s.py" <<'PY'
import os
import sys

name = os.path.basename(sys.argv[0])
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(name + " " + " ".join(sys.argv[1:]) + "\n")
fail_var = "STUB_FAIL_" + name.split(".")[0].upper()
sys.exit(int(os.environ.get(fail_var, "0")) if "--selftest" in sys.argv else 0)
PY
done

# run_gates <log> [VAR=value ...]: run the runner, set RC to its exit code, log every stub call.
run_gates() {
  local log="$1"
  shift
  if env STUB_LOG="$log" "$@" bash "$fx/scripts/dcr-gates.sh" >"$WORK/out.txt" 2>&1; then RC=0; else RC=$?; fi
}
calls() { # calls <log> <stub>: how many times <stub>.py ran its --selftest
  grep -c "^$2.py --selftest" "$1" || true
}
all_once() { # all_once <log>: every stub selftested exactly once
  local s
  for s in $STUBS; do [ "$(calls "$1" "$s")" -eq 1 ] || return 1; done
}

# 1) Unset: behaviour is unchanged, every invocation proves every gate.
: >"$WORK/l1"
run_gates "$WORK/l1"
r1=$RC
run_gates "$WORK/l1"
ok=1
[ "$r1" -eq 0 ] && [ "$RC" -eq 0 ] || ok=0
for s in $STUBS; do [ "$(calls "$WORK/l1" "$s")" -eq 2 ] || ok=0; done
record $((1 - ok)) "unset: two runs selftest every gate twice (behaviour unchanged)"

# 2) Set: the second run reuses the first run's passing verdicts.
: >"$WORK/l2"
run_gates "$WORK/l2" DCR_SELFTEST_STAMPS="$WORK/stamps2"
r1=$RC
run_gates "$WORK/l2" DCR_SELFTEST_STAMPS="$WORK/stamps2"
if [ "$r1" -eq 0 ] && [ "$RC" -eq 0 ] && all_once "$WORK/l2" && [ "$(find "$WORK/stamps2" -type f | wc -l | tr -d ' ')" -eq 4 ]; then
  record 0 "set: a second run skips every selftest that already passed (4 stamps)"
else
  record 1 "set: a second run skips every selftest that already passed (4 stamps)"
fi

# 3) The real gate checks still run on the stamped run (only the selftest is skipped).
if [ "$(grep -c '^fix_class_gate.py --base\|^binaries_gate.py ' "$WORK/l2" || true)" -ge 1 ] || grep -q 'fix_class_gate skipped\|binaries_gate PASS' "$WORK/out.txt"; then
  record 0 "set: the gate checks themselves still run on a stamped run"
else
  record 1 "set: the gate checks themselves still run on a stamped run"
fi

# 4) A failing selftest is never stamped: it re-runs, and fails, every time.
: >"$WORK/l4"
run_gates "$WORK/l4" DCR_SELFTEST_STAMPS="$WORK/stamps4" STUB_FAIL_PARITY_DIFFER=1
r1=$RC
run_gates "$WORK/l4" DCR_SELFTEST_STAMPS="$WORK/stamps4" STUB_FAIL_PARITY_DIFFER=1
if [ "$r1" -ne 0 ] && [ "$RC" -ne 0 ] && [ "$(calls "$WORK/l4" parity_differ)" -eq 2 ] \
  && [ "$(calls "$WORK/l4" fix_class_gate)" -eq 1 ] && ! compgen -G "$WORK/stamps4/*-parity_differ.py" >/dev/null \
  && compgen -G "$WORK/stamps4/*-fix_class_gate.py" >/dev/null; then
  record 0 "set: a failing selftest is re-run and fails closed every time, never stamped"
else
  record 1 "set: a failing selftest is re-run and fails closed every time, never stamped"
fi

# 5) Changing a script's bytes invalidates its stamp; the unchanged scripts stay skipped.
: >"$WORK/l5"
run_gates "$WORK/l5" DCR_SELFTEST_STAMPS="$WORK/stamps5"
printf '# edited\n' >>"$fx/.claude/skills/deep-code-review/scripts/token_differ.py"
run_gates "$WORK/l5" DCR_SELFTEST_STAMPS="$WORK/stamps5"
if [ "$RC" -eq 0 ] && [ "$(calls "$WORK/l5" token_differ)" -eq 2 ] && [ "$(calls "$WORK/l5" fix_class_gate)" -eq 1 ]; then
  record 0 "set: editing a gate script re-proves it; unchanged scripts stay skipped"
else
  record 1 "set: editing a gate script re-proves it; unchanged scripts stay skipped"
fi

# 6) An unusable stamp directory degrades to running everything, never to skipping.
: >"$WORK/l6"
printf 'a file, not a directory\n' >"$WORK/notadir"
run_gates "$WORK/l6" DCR_SELFTEST_STAMPS="$WORK/notadir/stamps"
r1=$RC
run_gates "$WORK/l6" DCR_SELFTEST_STAMPS="$WORK/notadir/stamps"
if [ "$r1" -eq 0 ] && [ "$RC" -eq 0 ] && [ "$(calls "$WORK/l6" fix_class_gate)" -eq 2 ]; then
  record 0 "set but unusable: every selftest still runs, the runner still passes"
else
  record 1 "set but unusable: every selftest still runs, the runner still passes"
fi

# 7) A stamp directory we do not own with mode 700 is ignored (a shared or planted directory is never trusted).
: >"$WORK/l7"
mkdir -m 755 "$WORK/stamps7"
run_gates "$WORK/l7" DCR_SELFTEST_STAMPS="$WORK/stamps7"
run_gates "$WORK/l7" DCR_SELFTEST_STAMPS="$WORK/stamps7"
if [ "$RC" -eq 0 ] && [ "$(calls "$WORK/l7" fix_class_gate)" -eq 2 ] && [ -z "$(ls -A "$WORK/stamps7")" ]; then
  record 0 "set: a mode-755 stamp directory is ignored, nothing is read or written there"
else
  record 1 "set: a mode-755 stamp directory is ignored, nothing is read or written there"
fi
: >"$WORK/l7b"
run_gates "$WORK/l7b" DCR_SELFTEST_STAMPS="$WORK/stamps7b"
if [ "$(stat -c %a "$WORK/stamps7b" 2>/dev/null || stat -f %Lp "$WORK/stamps7b")" = 700 ]; then
  record 0 "set: a missing stamp directory is created with mode 700"
else
  record 1 "set: a missing stamp directory is created with mode 700"
fi

# 8) The key carries the python version: a stamp from another interpreter does not skip the selftest.
: >"$WORK/l8"
mkdir -p "$WORK/shim"
real_py="$(command -v python3)"
printf '#!/bin/sh\n[ "$1" = "-V" ] && { echo "Python 9.9.9"; exit 0; }\nexec "%s" "$@"\n' "$real_py" >"$WORK/shim/python3"
chmod +x "$WORK/shim/python3"
run_gates "$WORK/l8" DCR_SELFTEST_STAMPS="$WORK/stamps8"
run_gates "$WORK/l8" DCR_SELFTEST_STAMPS="$WORK/stamps8" PATH="$WORK/shim:$PATH"
if [ "$RC" -eq 0 ] && [ "$(calls "$WORK/l8" fix_class_gate)" -eq 2 ]; then
  record 0 "set: a stamp made under another python version is not reused"
else
  record 1 "set: a stamp made under another python version is not reused"
fi

# 9) The key hashes raw bytes: a .gitattributes eol rule must not make an edited (CRLF) script look unchanged.
fx9="$WORK/repo9"
cp -R "$fx" "$fx9"
printf '*.py text eol=lf\n' >"$fx9/.gitattributes"
git -C "$fx9" init -q
: >"$WORK/l9"
run9() { (cd "$fx9" && env STUB_LOG="$WORK/l9" DCR_SELFTEST_STAMPS="$WORK/stamps9" bash "$fx9/scripts/dcr-gates.sh" >"$WORK/out9.txt" 2>&1); }
run9
sed 's/$/\r/' "$fx9/.claude/skills/deep-code-review/scripts/token_differ.py" >"$WORK/crlf.py"
cp "$WORK/crlf.py" "$fx9/.claude/skills/deep-code-review/scripts/token_differ.py"
run9
if [ "$(calls "$WORK/l9" token_differ)" -eq 2 ]; then
  record 0 "set: raw bytes are hashed, an eol-only edit re-proves the script"
else
  record 1 "set: raw bytes are hashed, an eol-only edit re-proves the script"
fi

# 10) The suite case that asserts SELFTEST OK must not depend on stamps left by earlier cases.
if grep -q 'env -u DCR_SELFTEST_STAMPS bash "\$gates_runner"' "$ROOT/scripts/test-ci-gates.sh"; then
  record 0 "test-ci-gates: the SELFTEST OK case runs with DCR_SELFTEST_STAMPS unset"
else
  record 1 "test-ci-gates: the SELFTEST OK case runs with DCR_SELFTEST_STAMPS unset"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
