#!/usr/bin/env bash
# veche.py --packet resolution: a relative packet is found from the current directory, else under --root;
# a packet found in neither fails before any seat is called, and the error names both paths tried.
# Hermetic: a throwaway root and cwd under TMPDIR; the seat is a local fake script.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VECHE=$ROOT/.claude/skills/idea-critic/scripts/veche.py
D=${TMPDIR:-/tmp}; T=$(mktemp -d "${D%/}/dcr-test-veche-root.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
mkdir -p "$T/root" "$T/elsewhere" || exit 1
printf 'alpha\nbeta\n' >"$T/root/evidence.txt"
cat >"$T/fake.py" <<'EOF'
import sys
open(sys.argv[1], "a").write(sys.stdin.read())
print('{"verdict": "PASS_TO_USER", "claims": [], "would_change_it": "w", "kill_criterion": "M below 5 by day 30"}')
EOF
seat="python3 $T/fake.py $T/seen.txt"
cd "$T/elsewhere" || exit 1

# 1. relative packet that exists only under --root, run from another directory: seats see it, no internal error
rc=0; python3 "$VECHE" --cmd "$seat" --claim c --steelman s --packet evidence.txt --root "$T/root" >"$T/out" 2>"$T/err" || rc=$?
if grep -q "COULD_NOT_DECIDE" "$T/out"; then bad "root-relative packet: COULD_NOT_DECIDE (rc=$rc)"; else ok "root-relative packet decided (rc=$rc)"; fi
if grep -q "WARN packet is outside --root" "$T/err"; then bad "root-relative packet: spurious outside-root warning"; else ok "root-relative packet: no outside-root warning"; fi
if grep -q "(file evidence.txt)" "$T/seen.txt" 2>/dev/null; then ok "seats see the packet with its path under --root"; else bad "seats do not see '(file evidence.txt)'"; fi

# 2. packet missing from cwd and --root: 0 seat calls, error names both paths
rm -f "$T/seen.txt"; rc=0; python3 "$VECHE" --cmd "$seat" --claim c --steelman s --packet nope.txt --root "$T/root" >"$T/out2" 2>"$T/err2" || rc=$?
if [ -e "$T/seen.txt" ]; then bad "missing packet: a seat was called"; else ok "missing packet: 0 seat calls"; fi
if grep -qF "$T/elsewhere/nope.txt" "$T/out2" && grep -qF "$T/root/nope.txt" "$T/out2"; then ok "missing packet: reason names both paths"; else bad "missing packet: reason lacks a path (rc=$rc)"; fi

# 3. a directory named like the packet in cwd must not hide the file under --root
mkdir -p "$T/elsewhere/evidence.txt"; rm -f "$T/seen.txt"; rc=0
python3 "$VECHE" --cmd "$seat" --claim c --steelman s --packet evidence.txt --root "$T/root" >"$T/out3" 2>"$T/err3" || rc=$?
if grep -q "(file evidence.txt)" "$T/seen.txt" 2>/dev/null; then ok "cwd directory of the same name: packet found under --root"; else bad "cwd directory of the same name hid the --root packet (rc=$rc)"; fi

[ "$fail" -eq 0 ] && echo "all veche packet-root checks passed" || { echo "veche packet-root checks FAILED" >&2; exit 1; }
