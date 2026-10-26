#!/usr/bin/env bash
# Bash 3.2 portability gate (macOS ships bash 3.2): every shipped shell script must avoid bash-4-only constructs.
# Scans .claude/skills/**/*.sh, install.sh and scripts/*.sh; comment lines and lines carrying `bash4-ok` are skipped.
# Includes a planted-RED fixture proving the scanner fails on a hit. Prints PASS/FAIL per case; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-bash3.XXXXXX")"
trap 'find "$WORK" -depth -delete' EXIT

PAT='(declare|typeset|local)[[:space:]]+-[a-zA-Z]*[An]|(^|[^A-Za-z_])(mapfile|readarray|coproc)([^A-Za-z_]|$)|\$\{[A-Za-z_0-9]+([,^]|@[A-Za-z])|wait[[:space:]]+-n|&>>|\|&'  # bash4-ok
# hits <file>...: print file:line:text for each bash-4-only construct outside comments and bash4-ok lines
hits() { grep -nE -- "$PAT" /dev/null "$@" | grep -vE '^[^:]*:[0-9]+:[[:space:]]*#' | grep -vF 'bash4-ok'; }

pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# planted RED: one line per construct, each must be caught
F="$WORK/bad.sh"
{
  echo 'declare -A m'
  echo 'mapfile -t a < f'
  echo 'readarray -t a < f'
  echo 'x="${v,,}"'
  echo 'x="${v^^}"'
  echo 'cmd &>> log'
  echo 'cmd |& tee log'
  echo 'coproc X { cat; }'
  echo 'local -A m'
  echo 'declare -n r=x'
  echo 'x="${v@U}"'
  echo 'x="${v,}"'
  echo 'x="${v^}"'
  echo 'wait -n'
} > "$F"  # bash4-ok: the echoed lines are the fixture; the scanner reads $F, not this file's source
n="$(hits "$F" | wc -l | tr -d ' ')"
[ "$n" -eq 14 ]; ok $? "planted-RED: scanner flags all 14 bash-4 constructs (got $n)"

# planted GREEN: comments, the opt-out marker and bash-3-safe syntax pass
G="$WORK/good.sh"
{
  echo '# declare -A m is bash 4'
  echo 'declare -a ok; y=${v:-d}; z=$(echo "$v" | tr a-z A-Z)'
  echo 'cmd |& tee log  # bash4-ok: quoted text'
} > "$G"  # bash4-ok: fixture lines
n="$(hits "$G" | wc -l | tr -d ' ')"
[ "$n" -eq 0 ]; ok $? "planted-GREEN: comments, bash4-ok lines and bash-3-safe syntax pass (got $n)"

# the shipped tree (minus this file, whose source holds the planted fixtures)
out="$({ find "$ROOT/.claude/skills" -name '*.sh' -type f; ls "$ROOT"/scripts/*.sh "$ROOT/install.sh"; } | grep -v '/test-bash3-portability.sh$' | xargs grep -nE -- "$PAT" /dev/null | grep -vE '^[^:]*:[0-9]+:[[:space:]]*#' | grep -vF 'bash4-ok')"
[ -z "$out" ]; ok $? "shipped scripts use no bash-4-only constructs${out:+: $out}"
echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
