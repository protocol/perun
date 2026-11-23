#!/usr/bin/env bash
# test-tool-probes.sh [--out FILE] — an external tool counts as done only when it yields a row on a seeded fixture.
# External = the hub array and `have X` binaries in review_checks.sh (plus the few named below); in-repo checks are not probed.
# For each external tool in `review_checks.sh --list-tools`:
#   installed + fixture + >=1 real row -> PASS; installed + fixture + 0 rows -> FAIL (exit 1);
#   not installed -> `NOT RUN <tool> (not installed)`; installed without fixture (e.g. nuclei needs a live URL) -> `NOT RUN <tool> (no fixture)`.
# A zero-row tool in the blocked() list (network or vuln DB needed) prints BLOCKED and does not fail. Each probe has a PROBE_TIMEOUT (default 300s) and the run a PROBE_BUDGET (default 780s, under run-ci-tests.sh's 900s per-test bound):
# a probe that times out, or starts after the budget is spent, prints `NOT RUN <tool> (timeout|budget)` (not a pass, not a FAIL), so a loaded host cannot stall the test.
# NOT RUN is never a pass, so a run that probes no tool at all exits 1. A `not-checked` row (tool present but could not scan) is not a row.
# Usage: [--out FILE] [--only TOOL]. Writes TSV tool/installed/rows/status to --out, default $TMPDIR/tool-probes.tsv. Fixtures: scripts/fixtures/tool-probes/<tool>/.
# Fixture files may hold `@@` to split a secret-shaped literal; it is stripped when the fixture is copied.
set -u
here=$(cd "$(dirname "$0")" && pwd)
rc_sh=$here/../.claude/skills/deep-code-review/scripts/review_checks.sh
fx=$here/fixtures/tool-probes
out=${TMPDIR:-/tmp}/tool-probes.tsv
only=
while [ $# -gt 0 ]; do case $1 in --out) out=${2:?--out needs a file}; shift 2 ;; --only) only=${2:?--only needs a tool}; shift 2 ;; *) echo "usage: $0 [--out FILE] [--only TOOL]" >&2; exit 2 ;; esac; done
work=$(mktemp -d "${TMPDIR:-/tmp}/tool-probes.XXXXXX") || exit 2
trap 'rm -rf "${work:?}"' EXIT
printf 'tool\tinstalled\trows\tstatus\n' >"$out"
# binary differs from the review_checks tool name
bin() { case $1 in ruff-security) echo ruff ;; gitleaks-history) echo gitleaks ;; go-vet) echo go ;; *) echo "$1" ;; esac; }
ext=$({ sed -n '/^hub=(/,/^)/p' "$rc_sh" | grep -oE "^  '[a-z0-9_-]+" | tr -d " '"; grep -oE 'have +[a-z][a-z0-9_-]*' "$rc_sh" | awk '{print $2}'
  printf '%s\n' ruff semgrep tsc codeql gitleaks-history go-vet; } | sort -u)
# Tools that cannot yield a row without network or a fresh vuln DB: a zero-row result is BLOCKED (reason shown), not FAIL. Any other zero-row tool FAILs.
blocked() { case $1 in
  gosec) echo "needs network: loads Go module dependencies" ;;
  grype) echo "needs a fresh vulnerability DB; the local one is stale or unreachable" ;;
  osv-scanner) echo "needs network or an offline vulnerability DB" ;;
  trivy) echo "needs a vulnerability DB download (network)" ;;
  *) return 1 ;; esac; }
# Portable timeout (stock macOS has none): kills the whole process group, exit 124 on expiry.
tmo() { python3 -I -c 'import os, signal, subprocess, sys
p = subprocess.Popen(sys.argv[2:], start_new_session=True)
try: sys.exit(p.wait(int(sys.argv[1])))
except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); sys.exit(124)' "$@"; }
fail=0 probed=0 ok=0 zero= blk=
for t in $(bash "$rc_sh" --list-tools | grep -Fx "$ext"); do
  [ -z "$only" ] || [ "$t" = "$only" ] || continue
  if ! command -v "$(bin "$t")" >/dev/null; then echo "NOT RUN $t (not installed)"; printf '%s\tno\t-\tNOT RUN\n' "$t" >>"$out"; continue; fi
  if [ ! -d "$fx/$t" ]; then echo "NOT RUN $t (no fixture)"; printf '%s\tyes\t-\tNOT RUN\n' "$t" >>"$out"; continue; fi
  d=$work/$t; cp -R "$fx/$t" "$d"
  find "$d" -type f | while IFS= read -r f; do sed 's/@@//g' "$f" >"$f.tmp" && mv "$f.tmp" "$f"; done
  git -C "$d" init -q && git -C "$d" add -A && git -C "$d" -c user.name=Probe -c user.email=probe@example.com commit -qm probe
  left=$(( ${PROBE_BUDGET:-780} - SECONDS ))
  if [ "$left" -le 0 ]; then echo "NOT RUN $t (budget)"; printf '%s\tyes\t-\tNOT RUN\n' "$t" >>"$out"; continue; fi
  lim=${PROBE_TIMEOUT:-300}; [ "$left" -ge "$lim" ] || lim=$left
  tmo "$lim" bash "$rc_sh" --full --repo "$d" >"$work/$t.json" 2>"$work/$t.err"
  if [ $? -eq 124 ]; then echo "NOT RUN $t (timeout)"; printf '%s\tyes\t-\tNOT RUN\n' "$t" >>"$out"; continue; fi
  n=$(python3 -I -c '
import json, sys
t = sys.argv[1]
try: rows = json.load(sys.stdin)
except ValueError: rows = []
print(sum(1 for r in rows if r.get("tool") == t and r.get("rule") != "not-checked" and "NOT CHECKED" not in r.get("text", "")))' "$t" <"$work/$t.json")
  probed=$((probed + 1))
  if [ "${n:-0}" -ge 1 ]; then ok=$((ok + 1)); s=PASS; echo "PASS $t ($n rows)"
  elif why=$(blocked "$t"); then blk+="${blk:+,}$t"; s=BLOCKED; echo "BLOCKED $t ($why)"
  else fail=1; zero+="${zero:+,}$t"; s=FAIL; echo "FAIL $t (0 rows)"; grep -iE "$t|timeout|lease" "$work/$t.err" | head -3 | sed 's/^/  stderr: /'; fi
  printf '%s\tyes\t%s\t%s\n' "$t" "${n:-0}" "$s" >>"$out"
done
echo "installed tools probed $probed | rows>0 $ok | blocked: ${blk:-none} | zero-row: ${zero:-none} | tsv $out"
[ "$probed" -gt 0 ] || { echo "FAIL: no installed tool was probed (NOT RUN is never a pass)"; fail=1; }
exit $fail
