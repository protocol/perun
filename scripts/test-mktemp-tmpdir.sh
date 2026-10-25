#!/usr/bin/env bash
# Regression: shipped scripts must not call a bare mktemp (no template). macOS bare mktemp ignores TMPDIR,
# which breaks sandboxed runs; every call takes "${TMPDIR:-/tmp}/<name>.XXXXXX". Comment lines are skipped, and so are
# the destructive guard and its corpus tests, which hold mktemp command lines as data to match, never as calls.
# A positive control proves the pattern still matches a bare call, so a broken regex cannot pass silently.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Bare = mktemp, optional flags, then end of command (no template argument follows).
BARE='mktemp( -[dqu]+)*[[:space:]]*($|[);|&}`])'
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

# Positive control: a bare call must match, a templated call must not.
ctl="$(mktemp "${TMPDIR:-/tmp}/dcr-mktemp-ctl.XXXXXX")"; trap 'rm -f "$ctl"' EXIT
printf 'x=$(%s -d)\ny=$(%s -d "${TMPDIR:-/tmp}/a.XXXXXX")\n' "mktemp" "mktemp" >"$ctl"
ctl_hits=$(grep -En "$BARE" "$ctl" || true)
if [ "$(printf '%s\n' "$ctl_hits" | grep -c .)" = 1 ] && printf '%s' "$ctl_hits" | grep -q '^1:'; then
  ok "positive control: bare mktemp matched, templated mktemp did not"
else
  bad "positive control: pattern does not isolate bare mktemp (got: $ctl_hits)"
fi

hits=$(cd "$ROOT" && grep -rEn --include='*.sh' --include='*.py' "$BARE" .claude/skills scripts \
  | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' \
  | grep -vE '^(\.claude/skills/agentic-delivery/scripts/destructive_guard\.py|scripts/test_security_gates[^:]*\.py):' || true)
if [ -z "$hits" ]; then
  ok "no bare mktemp in shipped scripts"
else
  bad "bare mktemp (no template) in shipped scripts; add \"\${TMPDIR:-/tmp}/<name>.XXXXXX\":"
  printf '%s\n' "$hits"
fi

exit "$fail"
