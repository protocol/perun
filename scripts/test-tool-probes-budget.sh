#!/usr/bin/env bash
# A slow external probe must report "NOT RUN <tool> (timeout)" within PROBE_TIMEOUT, and a spent PROBE_BUDGET must report
# "NOT RUN <tool> (budget)"; neither may stall test-tool-probes.sh nor count as a FAIL (issue protocol/perun#2489).
set -u
here=$(cd "$(dirname "$0")" && pwd)
w=$(mktemp -d "${TMPDIR:-/tmp}/probe-budget.XXXXXX") || exit 2
trap 'rm -rf "${w:?}"' EXIT
printf '#!/bin/sh\nsleep 30\n' >"$w/semgrep"; chmod +x "$w/semgrep"  # shim: installed, but slower than the probe limit
fail=0
chk() { grep -q "$2" <<<"$1" || { echo "FAIL: expected '$2' in: $1"; fail=1; }; ! grep -q '^FAIL ' <<<"$1" || { echo "FAIL: probe reported FAIL: $1"; fail=1; }; }
s=$SECONDS
o=$(PATH="$w:$PATH" PROBE_TIMEOUT=2 bash "$here/test-tool-probes.sh" --only semgrep --out "$w/a.tsv" 2>&1); chk "$o" 'NOT RUN semgrep (timeout)'
[ $((SECONDS - s)) -lt 20 ] || { echo "FAIL: slow probe stalled the test"; fail=1; }
o=$(PATH="$w:$PATH" PROBE_BUDGET=0 bash "$here/test-tool-probes.sh" --only semgrep --out "$w/b.tsv" 2>&1); chk "$o" 'NOT RUN semgrep (budget)'
[ "$fail" -eq 0 ] && echo "ok: slow probe bounded"
exit $fail
