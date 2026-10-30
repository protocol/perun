#!/usr/bin/env bash
# run-ci-tests.sh — local full ci-tests suite (every scripts/ci-tests.d/*.sh, as the CI "Per-PR tests" step runs them).
# Also runs the privacy gate and the trigger lint (CI's "Prose lessons carry a mechanism") before the tests.
# Exit 0 only when all pass; then records the last-known-good pointer (lkg.py record, HEAD). A failure records nothing.
# --affected [BASE]: run only the tests a changed file can reach. BASE = the argument, else RUN_CI_BASE, else BASE_SHA (the pre-push
#   hook's resolved base), else merge-base with origin/main; none resolves: prints "affected: NOT RUN (no base)", exit 0 (never blocks a push).
#   changed = BASE vs the working tree plus untracked files (NUL-delimited, unquoted names; a path that is not a file, symlink or deleted
#   fails closed). A ci-tests.d test is selected when it, or a scripts/test-*.sh / test_*.py it invokes (one level), names a changed file
#   (whole-name match; SKILL.md, ci.yml, README.md, INDEX.md, CHANGELOG.md need the repo-relative path). A changed .sh/.py no test names
#   gets one reverse-dependency hop (scripts that source/import it); still none: "UNCOVERED: <file> (no test names it; CI only)".
#   scripts/test-ci-gates.sh is left to CI (sharded there) unless it or scripts/ci-gates.sh changed.
#   always= (below): whole-tree gates of CI's "cheap" job flag files no test names, so selection by name never reaches them; they run first on every
#   non-empty --affected run (a violation fails in seconds, before the suites), a changed one is not UNCOVERED, and each is in --list-affected and the receipt (a .py entry runs under python3).
#   Privacy scans only the changed files (the whole tree when a .banlist*.txt, ci-gates.sh or secret_scan.py changed). Not the full
#   suite, so it never records the last-known-good pointer. It records a kind=affected receipt instead (lkg.record_affected_cli, no CLI subcommand: HEAD, the
#   working-tree tree hash taken before the suites run, base, each selected suite's rc, overall rc; a failure records too, with the suites
#   fail-fast skipped as "-"; the runner's own blob; none when the suites changed the tree), which handback.py --body-file checks a
#   "run-ci-tests/affected pass" claim against. No changed files: runs nothing, exit 0.
# --list-affected [BASE]: the dry form of --affected: prints "affected: N of M tests" and one "selected: <suite>" line per suite it would run,
#   then exits 0 without the privacy/trigger gates, any suite or any receipt (lkg.py affected-check re-derives the selection with it).
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
affected=0 list=0 base="${RUN_CI_BASE:-}" arg=
case "${1:-}" in
  --affected) affected=1; arg="${2:-}" ;;
  --list-affected) affected=1 list=1; arg="${2:-}" ;;
  "") ;;
  *) echo "usage: run-ci-tests.sh [--affected [BASE] | --list-affected [BASE]]" >&2; exit 2 ;;
esac
[ "$affected" -eq 1 ] || [ -n "$base" ] || base="$(git merge-base HEAD origin/main 2>/dev/null)"
changed= full_privacy=0
if [ "$affected" -eq 1 ]; then
  [ -z "$arg" ] || git cat-file -e "$arg^{commit}" 2>/dev/null || { echo "run-ci-tests: FAIL --affected: BASE '$arg' is not a commit" >&2; exit 1; }
  base=; for c in "$arg" "${RUN_CI_BASE:-}" "${BASE_SHA:-}" "$(git merge-base HEAD origin/main 2>/dev/null)"; do
    if [ -n "$c" ] && git cat-file -e "$c^{commit}" 2>/dev/null; then base="$c"; break; fi
  done
  [ -n "$base" ] || { echo "affected: NOT RUN (no base)"; exit 0; }  # no base to diff against: never block a push
  chg="$(mktemp "${TMPDIR:-/tmp}/run-ci-tests.XXXXXX")" tsv="$(mktemp "${TMPDIR:-/tmp}/run-ci-tests.XXXXXX")" pats="$(mktemp "${TMPDIR:-/tmp}/run-ci-tests.XXXXXX")" || exit 1
  trap 'rm -f "$chg" "$tsv" "$pats"' EXIT
  { git -c core.quotepath=false diff --no-renames --name-only -z "$base" && git -c core.quotepath=false ls-files -o --exclude-standard -z; } | LC_ALL=C sort -zu >"$chg" || { echo "run-ci-tests: FAIL --affected: cannot list changed files" >&2; exit 1; }
  pt=()  # changed regular files the privacy scan reads (the tree holds ~90k fixture files: a whole-tree scan takes minutes; CI still scans it all)
  while IFS= read -r -d '' f; do
    case "$f" in *$'\n'*|*$'\t'*) echo "run-ci-tests: FAIL --affected: refusing a changed path with a newline or tab: $f" >&2; exit 1 ;; esac
    case "$f" in .banlist*.txt|scripts/ci-gates.sh|scripts/secret_scan.py) full_privacy=1 ;; esac  # the privacy rules themselves changed
    if [ -L "$f" ] || [ ! -e "$f" ]; then :  # symlink, or deleted (still named: a test may reference it)
    elif [ -f "$f" ]; then pt+=("$f")
    else echo "run-ci-tests: FAIL --affected: changed path is neither file, symlink nor deleted: $f" >&2; exit 1; fi
    changed="$changed$f"$'\n'
  done <"$chg"
  [ -n "$changed" ] || { echo "affected: 0 of $(ls scripts/ci-tests.d/*.sh | wc -l | tr -d ' ') tests (no changed files vs $base; nothing to run)"; exit 0; }
fi
if [ "$list" -eq 0 ]; then  # (--list-affected is dry: no run dir, no gates)
  # PERUN_RUN_DIR (optional): this run's log dir; plain mkdir refuses a dir that already exists, so a rerun never overwrites an earlier run's evidence.
  [ -z "${PERUN_RUN_DIR:-}" ] || mkdir "$PERUN_RUN_DIR" || { echo "run-ci-tests: run dir $PERUN_RUN_DIR already exists; pick a fresh one" >&2; exit 1; }
  # The two cheap CI gates a push is most often rejected on, run first (a missing privacy input or an unresolvable base fails closed).
  echo "== privacy"
  [ -f scripts/ci-gates.sh ] && [ -f .banlist.txt ] || { echo "run-ci-tests: FAIL privacy: scripts/ci-gates.sh or .banlist.txt missing (fail closed)" >&2; exit 1; }
  if [ "$affected" -eq 0 ] || [ "$full_privacy" -eq 1 ]; then pt=(.); fi  # (--affected declared pt above)
  if [ "${#pt[@]}" -gt 0 ]; then
    bash scripts/ci-gates.sh privacy --banlist .banlist.txt -- "${pt[@]}" || { echo "run-ci-tests: FAIL privacy" >&2; exit 1; }
  fi
  gate=.claude/skills/deep-code-review/scripts/fix_class_gate.py
  if [ -f "$gate" ]; then
    echo "== trigger lint"
    [ -n "$base" ] || { echo "run-ci-tests: FAIL trigger lint: no base (no origin/main; set RUN_CI_BASE)" >&2; exit 1; }
    python3 "$gate" --base "$base" --head HEAD \
      --trigger-glob '.claude/skills/*/references/*.md' --trigger-glob '.claude/skills/*/SKILL.md' \
      --test-glob '.claude/skills/*/evals/evals.json' --test-glob '.claude/skills/*/scripts/*' \
      --test-glob 'scripts/test-ci-gates.sh' --test-glob 'scripts/test-*.sh' --test-glob 'scripts/test_*.py' \
      || { echo "run-ci-tests: FAIL trigger lint" >&2; exit 1; }
  fi
fi
sel='scripts/ci-tests.d/*.sh'  # unquoted below: the glob expands (full suite); --affected replaces it with the picked paths
if [ "$affected" -eq 1 ]; then
  esc() { printf '%s' "$1" | sed -E 's/[].[\\(){}*+?^$|]/\\&/g'; }
  rx() { printf '(^|[^A-Za-z0-9_.-])%s($|[^A-Za-z0-9_.-])' "$(esc "$1")"; }  # whole-name match: no name character on either side
  # hits TSV FILE...: print the label (column 1) of every "label<TAB>ERE" row whose ERE matches the text of FILE...
  hits() { local l e t="$1"; shift; while IFS=$'\t' read -r l e; do LC_ALL=C grep -qE -e "$e" -- "$@" && echo "$l"; done <"$t"; }
  # pick TSV SELF: select each test whose text, or a scripts/test-*.sh / test_*.py it invokes (one level), matches a TSV row
  # (SELF=1: a changed test selects itself); sets nhit = tests matched; appends the matched labels to hitl
  pick() {
    local t i inv lab; nhit=0; cut -f2 "$1" >"$pats"
    for t in $tests; do
      inv="$(grep -oE 'scripts/test[-_][A-Za-z0-9._-]+\.(sh|py)' "$t" | sort -u | while read -r i; do if [ -f "$i" ] && [ "$i" != "$gates" ]; then echo "$i"; fi; done)"
      lab=; if LC_ALL=C grep -qE -f "$pats" -- "$t" $inv; then lab="$(hits "$1" "$t" $inv)"; hitl="$hitl$lab"$'\n'; fi
      if [ "$2" = 1 ] && grep -qxF "$t" <<<"$changed"; then lab="$t"; hitl="$hitl${t##*/}"$'\n'; fi
      [ -n "$lab" ] || continue
      nhit=$((nhit + 1))
      case " $sel " in *" $t "*) ;; *) sel="$sel $t" why_all="$why_all  ${lab%%$'\n'*}→${t}"$'\n' ;; esac
    done
  }
  tests= total=0 gates=scripts/test-ci-gates.sh sel= why_all= hitl= unc=
  for t in scripts/ci-tests.d/*.sh; do if [ -f "$t" ]; then tests="$tests $t"; total=$((total + 1)); fi; done
  if [ -f "$gates" ]; then  # CI runs it sharded and its text names nearly every file: only a change to it or to ci-gates.sh selects it
    g="$(grep -xE 'scripts/(test-)?ci-gates\.sh' <<<"$changed" | head -1)"
    if [ -n "$g" ]; then sel=" $gates" total=$((total + 1)) why_all="  ${g##*/}→${gates}"$'\n' hitl="ci-gates.sh"$'\n'"test-ci-gates.sh"$'\n'; else echo "test-ci-gates: left to CI"; fi
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n="${f##*/}"; case "$n" in SKILL.md|ci.yml|README.md|INDEX.md|CHANGELOG.md) n="$f" ;; esac  # ubiquitous basenames: require the repo-relative path
    printf '%s\t%s\n' "$n" "$(rx "$n")"
  done <<<"$changed" >"$tsv"
  pick "$tsv" 1
  # Gates CI's "cheap" job runs on every PR over the whole tree, so no test names the file one of them flags (a line ending in a bare mktemp in
  # comms_lint.py failed CI after a 59/59 affected pass). Seconds each, need no regenerated file (skill_index.py --check does: left to CI).
  always='scripts/test-mktemp-tmpdir.sh scripts/check_section_pointers.py .claude/skills/deep-code-review/scripts/derived_numbers.py'
  al=
  for t in $always; do
    [ -f "$t" ] || continue  # absent (a fixture repo): skipped
    al="$al $t" total=$((total + 1)) why_all="$why_all  always→${t}"$'\n'
    hitl="$hitl${t##*/}"$'\n'
  done
  sel="$al$sel"  # first: seconds each, and the run is fail-fast
  # one reverse-dependency hop for a changed script no test names: scripts that source/import it, then the tests naming those
  while IFS= read -r f; do
    case "$f" in *.sh|*.py) ;; *) continue ;; esac
    n="${f##*/}"; stem="${n%.*}"
    if grep -qxF "$n" <<<"$hitl"; then continue; fi
    deps="$(LC_ALL=C grep -lsE -e "$(rx "$n")" -e "^[[:space:]]*(import|from)[[:space:]]+$(esc "$stem")([^A-Za-z0-9_]|\$)" -- scripts/*.sh scripts/*.py .claude/skills/*/scripts/*.sh .claude/skills/*/scripts/*.py | grep -vxF "$f")"
    nhit=0
    if [ -n "$deps" ]; then
      while IFS= read -r d; do printf '%s\t%s\n' "${n}→${d##*/}" "$(rx "${d##*/}")"; done <<<"$deps" >"$tsv"
      pick "$tsv" 0
    fi
    [ "$nhit" -gt 0 ] || unc="${unc}UNCOVERED: $f (no test names it; CI only)"$'\n'
  done <<<"$changed"
  echo "affected: $(echo $sel | wc -w | tr -d ' ') of $total tests (selected by: file→test)"
  printf '%s%s' "$why_all" "$unc"
  if [ "$list" -eq 1 ]; then for t in $sel; do echo "selected: $t"; done; exit 0; fi
  tree="$(python3 .claude/skills/agentic-delivery/scripts/lkg.py tree 2>/dev/null)" || tree=  # the scanned state, before any suite can touch the tree
  res=(); for t in $sel; do res+=("$t=-"); done  # "-" = selected, not run (the loop below is fail-fast)
fi
i=0 fail=
for t in $sel; do
  echo "== $t"
  # (a ci-test that truly needs the network exports PERUN_ALLOW_NET=1 itself; see scrub_env.sh)
  # scrubbed child env: no real gh login/token/network, no git hook vars, no CLAUDE* session vars (scrub_env.sh)
  case "$t" in
    *.py) SCRUB_PREFIXES="${SCRUB_PREFIXES:-CLAUDE}" bash .claude/skills/agentic-delivery/scripts/scrub_env.sh python3 "$t"; r=$? ;;
    *) SCRUB_PREFIXES="${SCRUB_PREFIXES:-CLAUDE}" bash .claude/skills/agentic-delivery/scripts/scrub_env.sh bash -e "$t"; r=$? ;;
  esac
  [ "$affected" -eq 0 ] || res[$i]="$t=$r"
  i=$((i + 1))
  [ "$r" -eq 0 ] || { echo "run-ci-tests: FAIL $t" >&2; fail=1; break; }
done
if [ "$affected" -eq 1 ]; then  # a partial run proves nothing about HEAD: a receipt for the tree, never the last-known-good pointer
  after="$(python3 .claude/skills/agentic-delivery/scripts/lkg.py tree 2>/dev/null)"  # a suite that edits the tree makes the scanned state unknowable: no receipt
  if [ -n "$tree" ] && [ "$after" = "$tree" ]; then
    python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import lkg; sys.exit(lkg.record_affected_cli(sys.argv[2:]))' .claude/skills/agentic-delivery/scripts "$base" "$tree" ${res[@]+"${res[@]}"} || echo "run-ci-tests: affected receipt not recorded (ignored)" >&2
  else echo "run-ci-tests: affected receipt not recorded (the suites changed the working tree, or it could not be hashed)" >&2; fi
  exit "${fail:-0}"
fi
[ -z "$fail" ] || exit 1
python3 .claude/skills/agentic-delivery/scripts/lkg.py record >/dev/null || echo "run-ci-tests: lkg record failed (ignored)" >&2
python3 .claude/skills/agentic-delivery/scripts/lkg.py verdict "$(python3 .claude/skills/agentic-delivery/scripts/lkg.py path)" >/dev/null || echo "run-ci-tests: lkg receipt does not verify against HEAD (ignored)" >&2
