#!/usr/bin/env bash
# shellcheck disable=SC2016 # single-quoted backticks below are literal markdown, not command substitution
# references/standards-coverage.md gate. Every row ID appears once, and only the IDs on the WIRED allowlist below may say wired;
# each of them must have a row, and that row must say wired. A wired or partial row names a tool that review_checks.sh routes (a
# `run_one TOOL` call on a line that is not a comment, or a `'TOOL;verified;` hub registry row; a name only mentioned in a comment,
# or an unverified hub row, fails). Every probe path in a probe cell exists (a directory must hold a file). Every backticked
# perun.* rule in a semgrep row exists in templates/semgrep-taint, and when the probe in the same position is a scripts/test_*.py
# file, that file carries a ruleid: fixture for the rule. A wired row does not say "via CWE-" (a check of one slice of a class is
# partial), names a perun.js.* and a perun.py.* semgrep rule, and lists a probe per rule. The per-list row counts hold (10 OWASP
# Top 10:2025, 10 API Top 10 2023, 25 CWE Top 25 2025, 10 LLM Top 10 2026). With no argument it checks the shipped table, then
# mutated copies, each of which must fail with its own check's message. With a path argument it checks only that file.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DOC=$ROOT/.claude/skills/deep-code-review/references/standards-coverage.md
RC=$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh
SG=$ROOT/.claude/skills/deep-code-review/templates/semgrep-taint
# The rows that say wired. Changing a status means changing this list in the same commit.
WIRED=" API7:2023 CWE-79 CWE-89 CWE-22 CWE-78 CWE-918 "

tick() { sed -nE 's/^[^`]*`([^`]+)`.*/\1/p' <<<"$1"; } # first backticked token of a cell
check() { # $1 = table file; prints one FAIL line per problem, returns 1 on any
  local doc=$1 bad=0 line id st tc pc tool rules probes rule p n code seen=" " na=0 napi=0 ncwe=0 nllm=0
  code=$(sed -E '/^[[:space:]]*#/d; s/[[:space:]]#.*$//' "$RC") # review_checks.sh without its comments
  while IFS= read -r line; do
    case "$line" in '| '*) ;; *) continue ;; esac
    IFS='|' read -r _ id _ st tc pc _ <<<"$line"
    id=${id// /}; st=${st// /}
    case "$id" in
      A[0-9][0-9]:2025) na=$((na + 1)) ;;
      API[0-9]:2023 | API10:2023) napi=$((napi + 1)) ;;
      CWE-[0-9]*) ncwe=$((ncwe + 1)) ;;
      LLM[0-9][0-9]:2026) nllm=$((nllm + 1)) ;;
      *) continue ;;
    esac
    case "$seen" in *" $id "*) echo "FAIL $id: duplicate row"; bad=1 ;; esac
    seen="$seen$id "
    case "$st" in wired | partial | none) ;; *) echo "FAIL $id: status '$st' is not wired, partial or none"; bad=1; continue ;; esac
    case "$WIRED" in
      *" $id "*) [ "$st" = wired ] || { echo "FAIL $id: on the wired allowlist but '$st'"; bad=1; } ;;
      *) [ "$st" != wired ] || { echo "FAIL $id: wired but not on the wired allowlist"; bad=1; } ;;
    esac
    probes=$(grep -oE '`[^`]+`' <<<"$pc" | tr -d '`')
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      if [ -d "$ROOT/$p" ]; then [ -n "$(find "$ROOT/$p" -type f | head -n 1)" ] || { echo "FAIL $id: probe dir $p holds no file"; bad=1; }
      elif [ ! -f "$ROOT/$p" ]; then echo "FAIL $id: probe $p does not exist"; bad=1; fi
    done <<<"$probes"
    [ "$st" = none ] && continue
    tool=$(tick "$tc"); rules=
    if ! [[ $tool =~ ^[a-z0-9][a-z0-9-]*$ ]]; then echo "FAIL $id: $st row names no tool"; bad=1
    elif ! grep -Eq "(^|[[:space:];&|(!])run_one $tool |^  '$tool;verified;" <<<"$code"; then echo "FAIL $id: tool '$tool' is not routed by review_checks.sh"; bad=1
    elif [ "$tool" = semgrep ]; then rules=$(grep -oE '`perun\.[^`]+`' <<<"$tc" | tr -d '`'); fi
    while IFS='|' read -r rule p; do # rule i pairs with probe i
      [ -n "$rule" ] || continue
      if ! grep -rqE "id: *[\"']?${rule//./\\.}[\"']?[[:space:]]*\$" "$SG"; then echo "FAIL $id: semgrep rule '$rule' is not in templates/semgrep-taint"; bad=1
      elif [[ $p == scripts/test_*.py ]] && [ -f "$ROOT/$p" ] && ! grep -qE "ruleid: *${rule//./\\.}([^[:alnum:]_.-]|\$)" "$ROOT/$p"; then echo "FAIL $id: $p has no 'ruleid: $rule' fixture"; bad=1; fi
    done < <(paste -d '|' <(printf '%s\n' "$rules") <(printf '%s\n' "$probes"))
    [ "$st" = wired ] || continue
    [[ $tc != *"via CWE-"* ]] || { echo "FAIL $id: wired row checks one weakness (via CWE-); mark it partial"; bad=1; }
    if ! grep -q '^perun\.js\.' <<<"$rules" || ! grep -q '^perun\.py\.' <<<"$rules"; then echo "FAIL $id: wired row needs a perun.js and a perun.py semgrep rule"; bad=1; fi
    n=$(grep -c . <<<"$probes")
    if [ "$n" = 0 ]; then echo "FAIL $id: wired row has no seeded probe"; bad=1
    elif [ "$n" -lt "$(grep -c . <<<"$rules")" ]; then echo "FAIL $id: wired row has fewer probes than rules; each rule needs its own probe"; bad=1; fi
  done <"$doc"
  for id in $WIRED; do case "$seen" in *" $id "*) ;; *) echo "FAIL $id: on the wired allowlist but has no row"; bad=1 ;; esac; done
  [ "$na/$napi/$ncwe/$nllm" = 10/10/25/10 ] || { echo "FAIL row counts OWASP/API/CWE/LLM = $na/$napi/$ncwe/$nllm, want 10/10/25/10"; bad=1; }
  return "$bad"
}

if [ $# -gt 0 ]; then check "$1" || exit 1; exit 0; fi
check "$DOC" || exit 1
echo "ok - shipped table passes"
if ! M=$(mktemp "${TMPDIR:-/tmp}/stdcov.XXXXXX") || ! RCM=$(mktemp "${TMPDIR:-/tmp}/stdcov.XXXXXX"); then echo "no temp file" >&2; exit 1; fi
trap 'rm -f -- "$M" "$RCM"' EXIT
{ cat "$RC"; printf '%s\n' '  # run_one ghost-tool x' 'x=1 # run_one ghost-tool x'; } >"$RCM" # ghost-tool appears only in comments
fail=0
mutant() { # $1 = label, $2 = text the FAIL output must hold, $3 = sed script (or "drop" + $4 row id): the copy must fail with $2
  if [ "$3" = drop ]; then grep -v "^| $4 |" "$DOC" >"$M"; else sed -E "$3" "$DOC" >"$M"; fi
  cmp -s "$DOC" "$M" && { echo "FAIL - mutant '$1' changed nothing"; fail=1; return; }
  local out; if out=$(check "$M"); then echo "FAIL - mutant '$1' passed"; fail=1
  elif [[ $out != *"$2"* ]]; then echo "FAIL - mutant '$1' failed without '$2': $out"; fail=1
  else echo "ok - mutant '$1' fails"; fi
}
mutant "unknown tool" "tool 'no-such-tool' is not routed" '/^\| CWE-79 \|/s/`semgrep`/`no-such-tool`/'
mutant "tool named only in a comment" "tool 'mcp-scanner' is not routed" '/^\| LLM03:2026 \|/s/`mcp-config`/`mcp-scanner`/'
RC=$RCM mutant "run_one only in a comment" "tool 'ghost-tool' is not routed" '/^\| LLM03:2026 \|/s/`mcp-config`/`ghost-tool`/'
mutant "unverified hub tool" "tool 'snyk-agent-scan' is not routed" '/^\| LLM03:2026 \|/s/`mcp-config`/`snyk-agent-scan`/'
mutant "missing probe" "probe bench/class-seeds/vuln/no-such-seed.js does not exist" '/^\| CWE-79 \|/s#vuln/cwe79\.js#vuln/no-such-seed.js#'
mutant "missing second probe" "probe bench/class-seeds/vuln/no-such-seed.js does not exist" '/^\| CWE-79 \|/s#(`bench/class-seeds/vuln/cwe79\.js`)#\1 `bench/class-seeds/vuln/no-such-seed.js`#'
mutant "wired row without probe" "CWE-79: wired row has no seeded probe" '/^\| CWE-79 \|/s/\|[^|]*\|$/| none |/'
mutant "wired row in one language" "CWE-79: wired row needs a perun.js and a perun.py semgrep rule" '/^\| CWE-79 \|/s/ `perun\.py\.xss`//'
mutant "wired rule without its own probe" "CWE-79: wired row has fewer probes than rules" '/^\| CWE-79 \|/s# `scripts/test_semgrep_audit_classes\.py`##'
mutant "unknown semgrep rule" "semgrep rule 'perun.js.no-such-rule'" '/^\| CWE-79 \|/s/perun\.js\.xss/perun.js.no-such-rule/'
mutant "test probe without ruleid" "has no 'ruleid: perun.js.xss' fixture" '/^\| API7:2023 \|/s/perun\.js\.ssrf/perun.js.xss/'
mutant "second rule's test probe without ruleid" "test_semgrep_py_pathtrav.py has no 'ruleid: perun.py.ssrf' fixture" '/^\| CWE-22 \|/s/perun\.py\.path-traversal/perun.py.ssrf/'
mutant "wired row via one CWE" "wired row checks one weakness" '/^\| CWE-79 \|/s/`perun\.js\.xss`/`perun.js.xss` (via CWE-79)/'
mutant "wired row off the allowlist" "CWE-20: wired but not on the wired allowlist" '/^\| CWE-20 \|/s/\| partial \|/| wired |/'
mutant "allowlisted row not wired" "CWE-79: on the wired allowlist but 'partial'" '/^\| CWE-79 \|/s/\| wired \|/| partial |/'
mutant "allowlisted row missing" "CWE-79: on the wired allowlist but has no row" 's/^\| CWE-79 \|(.*)\| wired \|/| CWE-1 |\1| partial |/'
mutant "duplicate row" "CWE-20: duplicate row" 's/^\| CWE-787 \|/| CWE-20 |/'
mutant "dropped row" "row counts" drop CWE-20
[ "$fail" = 0 ] && echo "standards coverage: ok"
exit "$fail"
