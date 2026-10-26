#!/usr/bin/env bash
# Tests for file_finding.py with a fake `gh` on PATH: a closed-issue repeat and a recently merged PR are refused (exit 1) with
# the match printed; --force REASON overrides and logs; an unrelated title passes; a failing gh fails closed (exit 2).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FF="$ROOT/.claude/skills/agentic-delivery/scripts/file_finding.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-file-finding.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"; export PERUN_FINDING_LOG="$WORK/force.log"
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
[ -z "${GH_FAIL:-}" ] || { echo "boom" >&2; exit 1; }
[ -z "${GH_ONLY_TERM:-}" ] || [ "${6%% *}" = "$GH_ONLY_TERM" ] || { echo '[]'; exit 0; }  # the fake index only knows the one term
case "$1" in
  issue) echo '[{"number":7,"title":"Train holds heavy slot forever","state":"CLOSED","url":"https://example.com/i/7"}]' ;;
  pr) echo '[{"number":9,"title":"Fix flaky browser gate retries","state":"MERGED","url":"https://example.com/p/9"}]' ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

out=$(python3 "$FF" "Train holds the heavy slot forever"); rc=$?
[ "$rc" -eq 1 ] && grep -q 'REFUSE: #7 \[CLOSED\]' <<<"$out"; ok $? "closed-issue repeat refused and the match printed"
out=$(python3 "$FF" "Browser gate is flaky" retries); rc=$?
[ "$rc" -eq 1 ] && grep -q 'REFUSE: #9 \[MERGED\]' <<<"$out"; ok $? "keyword match on a recently merged PR refused"
out=$(python3 "$FF" --force "different root cause, see log" "Train holds the heavy slot forever"); rc=$?
[ "$rc" -eq 0 ] && grep -q 'different root cause' "$PERUN_FINDING_LOG"; ok $? "--force overrides and logs the reason"
out=$(python3 "$FF" "Docs link checker misses anchors"); rc=$?
[ "$rc" -eq 0 ] && grep -q '^OK' <<<"$out"; ok $? "unrelated title passes"
out=$(GH_ONLY_TERM=slot python3 "$FF" "Train holds the heavy slot forever"); rc=$?
[ "$rc" -eq 1 ] && grep -q 'REFUSE: #7' <<<"$out"; ok $? "one search per term: a repeat only one word finds is still found"
out=$(python3 "$FF" "Heavy"); rc=$?
[ "$rc" -eq 0 ] && grep -q '^OK' <<<"$out"; ok $? "a single shared keyword is not enough for the overlap rule"
GH_FAIL=1 python3 "$FF" "anything at all" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "gh failure fails closed (exit 2)"

echo "file-finding: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
