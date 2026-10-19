#!/usr/bin/env bash
# Regression tests for the ultrareview fixes: operating-layer placeholder matcher, reap_own vanished PID,
# update-installed hook inference, subagent_start_inject non-object JSON. Writes only under a temp dir.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-ur.XXXXXX")"; trap 'rm -rf "$W"' EXIT
fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }

# 1) a fresh install wires the SubagentStop cap with no placeholder entry and no placeholder warning (scripts/test_peer_learnings_1019.py).
cp "$ROOT/.claude/skills/agentic-delivery/templates/operating-layer.settings.json" "$W/raw.json"
python3 "$SC/operating_selfcheck.py" --settings "$W/raw.json" 2>&1 | grep -i "handback-cap-two-tier" | grep -q PRESENT
ok $? "operating_selfcheck: the template's handback cap is PRESENT"

# 2) reap_own: age() of a PID that already exited must be empty, not abort under set -e.
sleep 0.3 & gone=$!; wait "$gone" 2>/dev/null
out="$(bash -c 'set -euo pipefail; eval "$(sed -n "/^age()/p" "$1")"; e=$(age "$2"); echo "e=[$e]"' _ "$SC/reap_own.sh" "$gone" 2>&1)"
grep -q "^e=\[\]$" <<<"$out"; ok $? "reap_own: age() of a vanished PID is empty, not fatal"

# 3) update-installed: an unrelated SubagentStart hook must not infer --apply-operating-layer.
mkdir -p "$W/h/scripts" "$W/h/.claude/skills/deep-code-review" "$W/u/.claude/skills/deep-code-review"
cp "$ROOT/scripts/update-installed.sh" "$W/h/scripts/"; echo 1.0.0 >"$W/h/.claude/skills/deep-code-review/VERSION"
printf '#!/usr/bin/env bash\ntrue\n' >"$W/h/install.sh"
echo '{"hooks":{"SubagentStart":[{"hooks":[{"type":"command","command":"echo other"}]}]}}' >"$W/u/.claude/settings.local.json"
DCR_NO_PULL=1 bash "$W/h/scripts/update-installed.sh" "$W/u" >/dev/null 2>&1
! grep -qs apply-operating-layer "$W/u/.claude/.dcr-install-flags" "$W/u/.claude/.dcr-install-flags.local"; ok $? "update-installed: unrelated SubagentStart hook not inferred as operating layer"
rm -f "$W/u/.claude/.dcr-install-flags" "$W/u/.claude/.dcr-install-flags.local"
echo '{"hooks":{"SubagentStart":[{"hooks":[{"type":"command","command":"python3 x/subagent_start_inject.py"}]}]}}' >"$W/u/.claude/settings.local.json"
DCR_NO_PULL=1 bash "$W/h/scripts/update-installed.sh" "$W/u" >/dev/null 2>&1
grep -q apply-operating-layer "$W/u/.claude/.dcr-install-flags.local"; ok $? "update-installed: injector hook inferred as operating layer"

# 3b) update-installed: a bad first target must not stop the second; exit non-zero at the end.
mkdir -p "$W/bad/.claude" "$W/good/.claude/skills/deep-code-review"
printf '#!/usr/bin/env bash\ntouch "${@: -1}/.claude/ran"\n' >"$W/h/install.sh"
DCR_NO_PULL=1 bash "$W/h/scripts/update-installed.sh" "$W/bad" "$W/good" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && [ -f "$W/good/.claude/ran" ]; ok $? "update-installed: bad target does not abort the rest, exits non-zero"

# 4) subagent_start_inject: non-object JSON exits 0 with no output.
echo "house" >"$W/house.md"
for j in null '[]' 5; do
  o="$(echo "$j" | HOUSE_DEFAULTS_FILE="$W/house.md" python3 "$SC/subagent_start_inject.py" 2>/dev/null)"; rc=$?
  [ "$rc" -eq 0 ] && [ -z "$o" ]; ok $? "subagent_start_inject: input $j exits 0 silently"
done
exit "$fail"
