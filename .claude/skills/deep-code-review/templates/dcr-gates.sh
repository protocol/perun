#!/usr/bin/env bash
# dcr-gates.sh — run the INSTALLED deep-code-review skill's own gate scripts
# in THIS repo's CI (or locally). Copied verbatim by `install.sh --with-gates`
# to <target>/scripts/dcr-gates.sh; never modified by the installer once
# copied — edit it in place if this project's test-glob or allowlist needs
# differ from the defaults below.
#
# WHY THIS EXISTS: the skillset's mechanisms (fix_class_gate.py,
# binaries_gate.py, and friends) only enforce anything inside the
# deep-code-review repository's own CI. A project that installs the skill
# gets the doctrine as prose an agent may or may not follow, and the
# mechanism itself never runs here. This script is the opt-in bridge:
# `install.sh --with-gates` + `.github/workflows/dcr-gates.yml` wires it into
# this repo's CI so the same enforcement fires on every push/PR.
#
# ONE IMPLEMENTATION — no duplicated gate logic. Every check below calls a
# script living INSIDE the installed skill tree (resolved dynamically below);
# this file only resolves paths and wires exit codes together. Upgrading the
# skill (re-running install.sh) upgrades the checks this file runs, with zero
# edits here.
#
# Configuration (env vars, all optional):
#   DCR_TEST_GLOBS         space-separated globs a fix commit's test-surface
#                           touch must match (passed to fix_class_gate.py
#                           --test-glob, once per glob, as literal patterns —
#                           never expanded against this directory). Unset ->
#                           the script's own defaults (tests/** etc; see its
#                           --help).
#   DCR_TRIGGER_GLOBS      space-separated globs (literal patterns, as
#                           above). Set -> fix_class_gate.py runs a second
#                           time in trigger mode on the same range: a commit
#                           touching a matching path must also touch a
#                           DCR_TEST_GLOBS path or carry a non-empty
#                           No-Mechanism-Reason: trailer. Unset -> skipped.
#   DCR_BINARIES_ALLOWLIST path to the binaries-gate allowlist file. Unset ->
#                           <repo-root>/scripts/binaries-allowlist.tsv if it
#                           exists, else no exemptions.
#   BASE_SHA / HEAD_SHA     the commit range fix_class_gate.py (and the
#                           opt-in refix_gate.py) checks. In CI, set these
#                           from the event (see the shipped workflow
#                           template). Locally, defaults to HEAD~1..HEAD when
#                           both are unset.
#   DCR_SELFTEST_STAMPS    a directory for selftest verdict stamps. Unset (the
#                           default) -> every run proves every gate script
#                           fires (`--selftest`), as always. Set -> a selftest
#                           that PASSED for a script with the same raw bytes
#                           (`git hash-object --no-filters`) under the same
#                           `python3 -V` is not run again, so a caller that
#                           invokes this runner many times in one run (a test
#                           suite) pays each selftest once. Only a pass is
#                           stamped; a failing selftest re-runs and fails
#                           closed every time. The directory must be private to
#                           ONE run of the caller (a fresh throwaway directory,
#                           never shared, committed or reused across runs): it
#                           is created with mode 700 and ignored (every
#                           selftest runs) unless it is a real directory we own
#                           with mode 700.
#
#   DCR_DERIVED_NUMBERS     ON BY DEFAULT. Set to 0 to turn off (any value other
#                           than unset, 0, or 1 fails closed). Runs derived_numbers.py
#                           over the repo's tracked *.md files: a number bound to a
#                           counter with `<!-- derived: COUNTER ARGS -->N` must equal
#                           the counter's result (a stale "N tests" fails). Counters
#                           are a fixed allowlist computed in Python (files, lines,
#                           grep-count, json-len); doc text is never run as a shell
#                           command. A repo with no markers passes. Fix a failure with
#                           `python3 <skill>/scripts/derived_numbers.py --fix`.
#
# OPT-IN gates (off unless the flag is exactly 1; any value other than unset,
# 0, or 1 fails closed).
#   DCR_REAPER_LINT=1       run deep-code-review's reaper_lint.py over
#                           DCR_REAPER_LINT_PATHS (space-separated files/dirs,
#                           literal — never glob-expanded; relative entries
#                           resolve against the repo root; default: the whole
#                           repo root; set but whitespace-only fails) for a
#                           bulk/fleet-wide process-reaper pattern (issue
#                           #1101; doctrine: concurrency-shared-state.md
#                           "Terminating work you own"). A heuristic lint:
#                           a PASS means no known shape matched, not that
#                           every kill is scoped. Needs no other skill
#                           installed.
#   DCR_SOURCE_SCAN_LINT=1  run deep-code-review's source_scan_tests.py over
#                           DCR_SOURCE_SCAN_LINT_PATHS (space-separated
#                           files/dirs, literal — never glob-expanded;
#                           relative entries resolve against the repo root;
#                           default: the whole repo root; set but
#                           whitespace-only fails): flags a test file that
#                           reads a UI source file (.tsx/.jsx/.vue/.svelte) as
#                           TEXT and regex/includes it, with no render/mount/
#                           screen call in the same file — a source scan
#                           proves the author typed certain characters, never
#                           that conditional rendering works (issue #1105;
#                           doctrine: testing-ui.md, "A conditional-render
#                           behaviour needs a rendered-DOM assertion, not a
#                           source scan"). A heuristic lint: a PASS means no
#                           known shape matched, not that every conditional
#                           path has rendered-DOM coverage. Needs no other
#                           skill installed.
#   DCR_CLOSES_LINT=1       run deep-code-review's closes_lint.py over the
#                           same BASE_SHA..HEAD_SHA range: a `close[sd]?` /
#                           `fix(e[sd])?` / `resolve[sd]?` + `#N` /
#                           `owner/repo#N` / issue-or-PR-URL closing keyword
#                           in any commit in range may only reference a
#                           (repository, number) in the allowed set from
#                           DCR_CLOSES_ALLOW (comma-separated `N`, `#N`, or
#                           `owner/repo#N`) and/or DCR_CLOSES_PR_BODY (a file
#                           holding the landing PR's own body — its own
#                           closing keywords also define the set); at least
#                           one of the two is required. Optional
#                           DCR_CLOSES_REPO=owner/repo names this repository,
#                           so a qualified self-reference counts as `#N`.
#                           Catches a stray closing keyword left
#                           over from a different lane's commit message
#                           silently auto-closing a ready PR when the range
#                           reaches the default branch (issue #1121;
#                           doctrine: merge-operations.md, "A squash or
#                           amend that collects several lanes' work must
#                           keep each closing keyword scoped to its own
#                           PR"). A heuristic lint (see the script's own
#                           HONESTY section for what it can't see). Needs no
#                           other skill installed.
# The next three need the agentic-delivery skill installed; a set flag with
# that skill or its script missing is a failure, never a skip.
#   DCR_REFIX_GATE=1        run agentic-delivery's refix_gate.py over the same
#                           range: re-touching a file a fix: commit touched
#                           within DCR_REFIX_WINDOW_HOURS (default 72) needs a
#                           DCR_TEST_GLOBS-matching test/eval change or a
#                           Refix-Reason: trailer.
#   DCR_PRIORITY_GATE=1     run agentic-delivery's priority_gate.py on the PR
#                           under review, from DCR_PRIORITY_JSON (a JSON file)
#                           or DCR_PRIORITY_REPO=owner/repo + DCR_PRIORITY_PR=N
#                           (`gh api`; the job needs GH_TOKEN). Optional
#                           DCR_PRIORITY_BUDGET (0..1) and DCR_PRIORITY_ARGS
#                           (extra options, whitespace-split, never
#                           glob-expanded, e.g. "--priority-label sev1").
#   DCR_FOCUS_GATE=1        run agentic-delivery's focus_gate.py `check` on the
#                           BASE_SHA..HEAD_SHA changed paths (plus the optional
#                           DCR_FOCUS_ITEM ref, e.g. "#123"): while the
#                           owner-authored priority record (DCR_FOCUS_RECORD,
#                           default .claude/PRIORITY.md) is OPEN, a change
#                           outside its scope fails; the acceptance command
#                           runs on a clean checkout of HEAD_SHA. The owner
#                           email comes from DCR_OWNER_EMAIL (set it from
#                           protected CI config; `git config dcr.owner` is an
#                           unprotected local fallback); none configured, an
#                           agent-authored or agent-deleted record, or no range
#                           and no item fails closed. A record that never
#                           existed passes with a notice. Optional
#                           DCR_FOCUS_ARGS (extra options, whitespace-split,
#                           never glob-expanded, e.g. "--require-signed").
#
# Exit code: 0 iff every gate below passed. Fails closed — an unresolvable
# skill install, a gate or selftest script missing from that install, or any
# gate script itself failing to run, is a failure, not a skip.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf 'dcr-gates: %s\n' "$*" >&2; exit 1; }

# Every host root install.sh can write a skill into, in the same order
# install.sh tries them. The first host carrying deep-code-review's SKILL.md
# is treated as THE install location for every skill this runner looks for.
HOST_CANDIDATES=(.claude .agents .cursor .codex .gemini .opencode .github .windsurf .hermes .kiro .cline .roo .factory .qwen .grok)

# find_skill_root <skill-name> — print the first host's copy of <skill-name>
# with a real SKILL.md, or print nothing (caller checks for empty).
find_skill_root() {
  local skill="$1" host
  for host in "${HOST_CANDIDATES[@]}"; do
    if [ -f "${REPO_ROOT}/${host}/skills/${skill}/SKILL.md" ]; then
      printf '%s/%s/skills/%s' "${REPO_ROOT}" "${host}" "${skill}"
      return 0
    fi
  done
  return 1
}

REVIEW_ROOT="$(find_skill_root deep-code-review)" \
  || die "no installed deep-code-review skill found under ${REPO_ROOT} (checked: ${HOST_CANDIDATES[*]}). Run install.sh first."
printf 'dcr-gates: using deep-code-review at %s\n' "${REVIEW_ROOT}"

DELIVERY_ROOT="$(find_skill_root agentic-delivery || true)"
if [ -n "${DELIVERY_ROOT}" ]; then
  printf 'dcr-gates: using agentic-delivery at %s\n' "${DELIVERY_ROOT}"
fi

FAIL=0

# ---------------------------------------------------------------------------
# The commit range the range-based gates check. RANGE_STATE is one of:
#   ok      BASE_SHA and HEAD_SHA are both set
#   partial the caller supplied half a range (a misconfiguration, never a pass)
#   none    nothing supplied and HEAD~1 unresolvable (single-commit repo)
# ---------------------------------------------------------------------------
BASE_SHA="${BASE_SHA:-}"
HEAD_SHA="${HEAD_SHA:-}"
CALLER_RANGE="${BASE_SHA}${HEAD_SHA}"
if [ -z "${BASE_SHA}" ] && [ -z "${HEAD_SHA}" ]; then
  # `--verify` (not a bare `rev-parse <ref>`): on an unresolvable ref, plain
  # `git rev-parse HEAD~1` still prints the literal ref text to STDOUT
  # (alongside the fatal error on stderr) despite its non-zero exit — a
  # known git quirk. `--verify` never does that, so a failure here is
  # reliably empty, not the poisoned literal string "HEAD~1".
  HEAD_SHA="$(git -C "${REPO_ROOT}" rev-parse --verify -q HEAD 2>/dev/null || true)"
  BASE_SHA="$(git -C "${REPO_ROOT}" rev-parse --verify -q 'HEAD~1' 2>/dev/null || true)"
fi
if [ -n "${BASE_SHA}" ] && [ -n "${HEAD_SHA}" ]; then
  RANGE_STATE=ok
elif [ -n "${CALLER_RANGE}" ]; then
  RANGE_STATE=partial
else
  RANGE_STATE=none
fi

# DCR_TEST_GLOBS as an array. `read -ra` splits on whitespace WITHOUT pathname
# expansion, so a glob like `tests/*` reaches a gate script as a pattern, not
# as whatever files it happens to match in the current directory.
test_globs=()
if [ -n "${DCR_TEST_GLOBS:-}" ]; then
  read -r -a test_globs <<<"${DCR_TEST_GLOBS}"
fi

# ---------------------------------------------------------------------------
# 1) fix_class_gate — every fix(...) commit in range touches a pinned test,
#    or carries a non-empty No-Test-Reason: trailer.
# ---------------------------------------------------------------------------
FIX_CLASS_GATE="${REVIEW_ROOT}/scripts/fix_class_gate.py"
if [ -f "${FIX_CLASS_GATE}" ]; then
  if [ "${RANGE_STATE}" = partial ]; then
    printf 'dcr-gates: FAIL fix_class_gate (caller supplied an incomplete BASE_SHA/HEAD_SHA range)\n'
    FAIL=1
  elif [ "${RANGE_STATE}" = none ]; then
    printf 'dcr-gates: fix_class_gate skipped (no range supplied and HEAD~1 unresolvable: single-commit repo?)\n'
  else
    glob_args=()
    for g in "${test_globs[@]+"${test_globs[@]}"}"; do
      glob_args+=(--test-glob "$g")
    done
    # fix_class_gate.py resolves the range against its OWN process cwd (it
    # takes no --repo flag), so this must run with cwd == REPO_ROOT — never
    # wherever dcr-gates.sh itself happened to be invoked from.
    if (cd "${REPO_ROOT}" && python3 "${FIX_CLASS_GATE}" --base "${BASE_SHA}" --head "${HEAD_SHA}" "${glob_args[@]+"${glob_args[@]}"}"); then
      printf 'dcr-gates: fix_class_gate PASS\n'
    else
      printf 'dcr-gates: fix_class_gate FAIL\n' >&2
      FAIL=1
    fi
    # Optional trigger mode (lesson -> mechanism): same script, same range,
    # same test globs; any failure (including a script error) fails closed.
    if [ -n "${DCR_TRIGGER_GLOBS:-}" ]; then
      trig_args=()
      read -r -a trigger_globs <<<"${DCR_TRIGGER_GLOBS}"
      for g in "${trigger_globs[@]+"${trigger_globs[@]}"}"; do
        trig_args+=(--trigger-glob "$g")
      done
      if [ "${#trig_args[@]}" -eq 0 ]; then
        # Whitespace-only value: set but names no glob — a misconfiguration.
        printf 'dcr-gates: FAIL fix_class_gate trigger mode (DCR_TRIGGER_GLOBS names no glob)\n' >&2
        FAIL=1
      elif (cd "${REPO_ROOT}" && python3 "${FIX_CLASS_GATE}" --base "${BASE_SHA}" --head "${HEAD_SHA}" "${glob_args[@]+"${glob_args[@]}"}" "${trig_args[@]}"); then
        printf 'dcr-gates: fix_class_gate trigger mode PASS\n'
      else
        printf 'dcr-gates: fix_class_gate trigger mode FAIL\n' >&2
        FAIL=1
      fi
    fi
  fi
else
  printf 'dcr-gates: fix_class_gate.py not found at %s (FAIL, fail closed)\n' "${FIX_CLASS_GATE}" >&2
  FAIL=1
fi

# ---------------------------------------------------------------------------
# 2) binaries_gate — no git-tracked file at a banned image/media/archive/
#    build-output extension.
# ---------------------------------------------------------------------------
BINARIES_GATE="${REVIEW_ROOT}/scripts/binaries_gate.py"
if [ -f "${BINARIES_GATE}" ]; then
  allow_args=()
  if [ -n "${DCR_BINARIES_ALLOWLIST:-}" ]; then
    allow_args=(--allowlist "${DCR_BINARIES_ALLOWLIST}")
  fi
  if python3 "${BINARIES_GATE}" "${allow_args[@]+"${allow_args[@]}"}" "${REPO_ROOT}"; then
    printf 'dcr-gates: binaries_gate PASS\n'
  else
    printf 'dcr-gates: binaries_gate FAIL\n' >&2
    FAIL=1
  fi
else
  printf 'dcr-gates: binaries_gate.py not found at %s (FAIL, fail closed)\n' "${BINARIES_GATE}" >&2
  FAIL=1
fi

# ---------------------------------------------------------------------------
# 2b) derived_numbers — a doc number bound to a counter must equal the
#     counter's result. ON by default (a repo with no markers passes); set
#     DCR_DERIVED_NUMBERS=0 to turn off. Its selftest runs in section 3.
# ---------------------------------------------------------------------------
case "${DCR_DERIVED_NUMBERS:-1}" in
  0) ;;
  1)
    DERIVED_NUMBERS="${REVIEW_ROOT}/scripts/derived_numbers.py"
    if [ ! -f "${DERIVED_NUMBERS}" ]; then
      printf 'dcr-gates: derived_numbers.py not found at %s (FAIL, fail closed)\n' "${DERIVED_NUMBERS}" >&2
      FAIL=1
    elif python3 "${DERIVED_NUMBERS}" "${REPO_ROOT}"; then
      printf 'dcr-gates: derived_numbers PASS\n'
    else
      printf 'dcr-gates: derived_numbers FAIL\n' >&2
      FAIL=1
    fi
    ;;
  *) printf 'dcr-gates: FAIL DCR_DERIVED_NUMBERS=%s (want unset, 0, or 1)\n' "${DCR_DERIVED_NUMBERS}" >&2; FAIL=1 ;;
esac

# ---------------------------------------------------------------------------
# 3) selftests of every shipped gate script this runner knows how to call —
#    proves each fires on a planted violation before its result is trusted,
#    independent of this repo's own history/content.
# ---------------------------------------------------------------------------
# selftest_ok <script> — `python3 <script> --selftest`. With DCR_SELFTEST_STAMPS
# set, a PASS for these exact script bytes under this python is remembered there
# and a later call skips the run. The key is `git hash-object --no-filters` (the
# raw bytes, never an attribute-normalised copy) plus `python3 -V`. The cache can
# only skip a selftest that already passed, never invent a pass: a failure is not
# stamped, and no git, or a stamp directory we do not own with mode 700, falls
# back to running it (a shared or foreign directory could hold planted stamps).
selftest_ok() {
  local script="$1" key="" stamp="" dir="${DCR_SELFTEST_STAMPS:-}" mode=""
  if [ -n "${dir}" ]; then
    [ -e "${dir}" ] || mkdir -p -m 700 "${dir}" 2>/dev/null || true
    mode="$(stat -c %a "${dir}" 2>/dev/null || stat -f %Lp "${dir}" 2>/dev/null || true)"
    if [ -d "${dir}" ] && [ ! -L "${dir}" ] && [ -O "${dir}" ] && [ "${mode}" = 700 ]; then
      key="$(git hash-object --no-filters -- "${script}" 2>/dev/null || true)"
      [ -z "${key}" ] || stamp="${dir}/${key}-$(python3 -V 2>&1 | tr -c 'A-Za-z0-9.\n' _ | tr -d '\n')-$(basename "${script}")"
    fi
  fi
  if [ -n "${stamp}" ] && [ -f "${stamp}" ]; then
    return 0
  fi
  python3 "${script}" --selftest || return 1
  if [ -n "${stamp}" ]; then
    : >"${stamp}" 2>/dev/null || true
  fi
  return 0
}

SELFTEST_SCRIPTS=(
  "${REVIEW_ROOT}/scripts/fix_class_gate.py"
  "${REVIEW_ROOT}/scripts/binaries_gate.py"
  "${REVIEW_ROOT}/scripts/derived_numbers.py"
  "${REVIEW_ROOT}/scripts/parity_differ.py"
  "${REVIEW_ROOT}/scripts/token_differ.py"
)
if [ -n "${DELIVERY_ROOT}" ]; then
  SELFTEST_SCRIPTS+=(
    "${DELIVERY_ROOT}/scripts/serial_gate.py"
    "${DELIVERY_ROOT}/scripts/handback_cap.py"
    "${DELIVERY_ROOT}/scripts/surface_check.py"
  )
fi
for script in "${SELFTEST_SCRIPTS[@]}"; do
  if [ ! -f "${script}" ]; then
    # Every listed script ships with its skill; a missing one means a partial
    # or tampered install, never a reason to skip its selftest.
    printf 'dcr-gates: selftest script not found at %s (FAIL, fail closed)\n' "${script}" >&2
    FAIL=1
    continue
  fi
  if selftest_ok "${script}"; then
    :
  else
    printf 'dcr-gates: selftest FAILED for %s\n' "${script}" >&2
    FAIL=1
  fi
done

# opt_in <FLAG_NAME> — succeed iff the flag is exactly 1; unset or 0 is off;
# any other value is a misconfiguration and fails closed. Defined here (ahead
# of every OPT-IN section below) so each section can call it in order.
opt_in() {
  local value="${!1:-0}"
  case "${value}" in
    0) return 1 ;;
    1) return 0 ;;
    *) printf 'dcr-gates: FAIL %s=%s (want unset, 0, or 1)\n' "$1" "${value}" >&2; FAIL=1; return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# 4) OPT-IN reaper_lint — flags a bulk/fleet-wide process-reaper pattern
#    (issue #1101: a port-range reap loop, a terse+network lsof selector left
#    unfiltered to the listener, a broad process-name-matching pkill/killall,
#    or a hard-coded protected-port list) before it takes down every parallel
#    lane on the host. Runs its own --selftest first (a gate that cannot
#    prove it fires is not trusted).
# ---------------------------------------------------------------------------
if opt_in DCR_REAPER_LINT; then
  REAPER_LINT="${REVIEW_ROOT}/scripts/reaper_lint.py"
  if [ ! -f "${REAPER_LINT}" ]; then
    printf 'dcr-gates: reaper_lint.py not found at %s (FAIL, fail closed)\n' "${REAPER_LINT}" >&2
    FAIL=1
  elif ! selftest_ok "${REAPER_LINT}"; then
    printf 'dcr-gates: selftest FAILED for %s\n' "${REAPER_LINT}" >&2
    FAIL=1
  else
    # Relative DCR_REAPER_LINT_PATHS entries resolve against REPO_ROOT (the
    # scan runs with cwd == REPO_ROOT), never against the caller's cwd.
    reaper_paths=()
    if [ -n "${DCR_REAPER_LINT_PATHS:-}" ]; then
      read -r -a reaper_paths <<<"${DCR_REAPER_LINT_PATHS}"
    else
      reaper_paths=(.)
    fi
    if [ "${#reaper_paths[@]}" -eq 0 ]; then
      printf 'dcr-gates: FAIL reaper_lint (DCR_REAPER_LINT_PATHS names no path)\n' >&2
      FAIL=1
    # "${arr[@]+"${arr[@]}"}": bash 3.2 treats an empty array as unset
    # under `set -u`; this form expands to nothing instead of aborting.
    elif (cd "${REPO_ROOT}" && python3 "${REAPER_LINT}" "${reaper_paths[@]+"${reaper_paths[@]}"}"); then
      printf 'dcr-gates: reaper_lint PASS\n'
    else
      printf 'dcr-gates: reaper_lint FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 5) OPT-IN source_scan_tests — flags a test file that reads a UI source file
#    (.tsx/.jsx/.vue/.svelte) as TEXT and regex/includes it, with no render/
#    mount/screen call in the same file: a source scan proves the author
#    typed certain characters, never that conditional rendering works (issue
#    #1105; doctrine: testing-ui.md). Runs its own --selftest first (a gate
#    that cannot prove it fires is not trusted).
# ---------------------------------------------------------------------------
if opt_in DCR_SOURCE_SCAN_LINT; then
  SOURCE_SCAN_LINT="${REVIEW_ROOT}/scripts/source_scan_tests.py"
  if [ ! -f "${SOURCE_SCAN_LINT}" ]; then
    printf 'dcr-gates: source_scan_tests.py not found at %s (FAIL, fail closed)\n' "${SOURCE_SCAN_LINT}" >&2
    FAIL=1
  elif ! selftest_ok "${SOURCE_SCAN_LINT}"; then
    printf 'dcr-gates: selftest FAILED for %s\n' "${SOURCE_SCAN_LINT}" >&2
    FAIL=1
  else
    # Relative DCR_SOURCE_SCAN_LINT_PATHS entries resolve against REPO_ROOT
    # (the scan runs with cwd == REPO_ROOT), never against the caller's cwd.
    scan_paths=()
    if [ -n "${DCR_SOURCE_SCAN_LINT_PATHS:-}" ]; then
      read -r -a scan_paths <<<"${DCR_SOURCE_SCAN_LINT_PATHS}"
    else
      scan_paths=(.)
    fi
    if [ "${#scan_paths[@]}" -eq 0 ]; then
      printf 'dcr-gates: FAIL source_scan_tests (DCR_SOURCE_SCAN_LINT_PATHS names no path)\n' >&2
      FAIL=1
    # "${arr[@]+"${arr[@]}"}": bash 3.2 treats an empty array as unset
    # under `set -u`; this form expands to nothing instead of aborting.
    # --allow-empty: a caller-scoped DCR_SOURCE_SCAN_LINT_PATHS may
    # legitimately name a path with no test files yet (source_scan_tests.py
    # itself fails closed, exit 2, on zero test files by default — the
    # correct behaviour for its own bare CLI, not for a narrower opt-in
    # scan this gate already selftested).
    elif (cd "${REPO_ROOT}" && python3 "${SOURCE_SCAN_LINT}" --allow-empty "${scan_paths[@]+"${scan_paths[@]}"}"); then
      printf 'dcr-gates: source_scan_tests PASS\n'
    else
      printf 'dcr-gates: source_scan_tests FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 6) OPT-IN closes_lint — a close[sd]?/fix(e[sd])?/resolve[sd]? + #N closing
#    keyword in BASE_SHA..HEAD_SHA may only reference a number this change
#    owns (issue #1121: a stray keyword from an unrelated commit auto-closes
#    a ready PR when it reaches the default branch). Runs its own --selftest
#    first (a gate that cannot prove it fires is not trusted).
# ---------------------------------------------------------------------------
if opt_in DCR_CLOSES_LINT; then
  CLOSES_LINT="${REVIEW_ROOT}/scripts/closes_lint.py"
  if [ ! -f "${CLOSES_LINT}" ]; then
    printf 'dcr-gates: closes_lint.py not found at %s (FAIL, fail closed)\n' "${CLOSES_LINT}" >&2
    FAIL=1
  elif ! selftest_ok "${CLOSES_LINT}"; then
    printf 'dcr-gates: selftest FAILED for %s\n' "${CLOSES_LINT}" >&2
    FAIL=1
  elif [ "${RANGE_STATE}" = partial ]; then
    printf 'dcr-gates: FAIL closes_lint (caller supplied an incomplete BASE_SHA/HEAD_SHA range)\n'
    FAIL=1
  elif [ "${RANGE_STATE}" = none ]; then
    printf 'dcr-gates: closes_lint skipped (no range supplied and HEAD~1 unresolvable: single-commit repo?)\n'
  else
    closes_args=()
    if [ -n "${DCR_CLOSES_ALLOW:-}" ]; then
      closes_args+=(--allow "${DCR_CLOSES_ALLOW}")
    fi
    if [ -n "${DCR_CLOSES_PR_BODY:-}" ]; then
      closes_args+=(--pr-body "${DCR_CLOSES_PR_BODY}")
    fi
    # --repo is checked apart: it names an identity, never an allowed set.
    closes_repo=()
    if [ -n "${DCR_CLOSES_REPO:-}" ]; then
      closes_repo=(--repo "${DCR_CLOSES_REPO}")
    fi
    if [ "${#closes_args[@]}" -eq 0 ]; then
      printf 'dcr-gates: FAIL closes_lint (DCR_CLOSES_LINT=1 needs DCR_CLOSES_ALLOW and/or DCR_CLOSES_PR_BODY)\n'
      FAIL=1
    # closes_lint.py resolves the range against its OWN process cwd (its
    # --repo is an owner/repo identity, not a path), so this must run with
    # cwd == REPO_ROOT.
    elif (cd "${REPO_ROOT}" && python3 "${CLOSES_LINT}" --base "${BASE_SHA}" --head "${HEAD_SHA}" "${closes_args[@]}" "${closes_repo[@]+"${closes_repo[@]}"}"); then
      printf 'dcr-gates: closes_lint PASS\n'
    else
      printf 'dcr-gates: closes_lint FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 7-9) OPT-IN delivery gates. Each runs its own --selftest first (a gate that
#      cannot prove it fires is not trusted), then the real check.
# ---------------------------------------------------------------------------

# delivery_script <name> — print the installed agentic-delivery script's path
# once its selftest passes; exit non-zero (caller sets FAIL) when it is
# missing or its selftest fails. Runs in a command substitution, so it
# reports failure by exit code, never by setting FAIL itself.
delivery_script() {
  local path="${DELIVERY_ROOT:+${DELIVERY_ROOT}/scripts/$1}"
  if [ -z "${path}" ] || [ ! -f "${path}" ]; then
    printf 'dcr-gates: %s not found (agentic-delivery not installed?) (FAIL, fail closed)\n' "$1" >&2
    return 1
  fi
  if ! selftest_ok "${path}" >&2; then
    printf 'dcr-gates: selftest FAILED for %s\n' "${path}" >&2
    return 1
  fi
  printf '%s' "${path}"
}

if opt_in DCR_REFIX_GATE; then
  if ! REFIX_GATE="$(delivery_script refix_gate.py)"; then
    FAIL=1
  elif [ "${RANGE_STATE}" = partial ]; then
    printf 'dcr-gates: FAIL refix_gate (caller supplied an incomplete BASE_SHA/HEAD_SHA range)\n'
    FAIL=1
  elif [ "${RANGE_STATE}" = none ]; then
    printf 'dcr-gates: refix_gate skipped (no range supplied and HEAD~1 unresolvable: single-commit repo?)\n'
  else
    class_args=()
    for g in "${test_globs[@]+"${test_globs[@]}"}"; do
      class_args+=(--class-glob "$g")
    done
    # Like fix_class_gate.py, refix_gate.py resolves the range against its own
    # cwd, so it runs with cwd == REPO_ROOT.
    if (cd "${REPO_ROOT}" && python3 "${REFIX_GATE}" --base "${BASE_SHA}" --head "${HEAD_SHA}" \
        --window-hours "${DCR_REFIX_WINDOW_HOURS:-72}" "${class_args[@]+"${class_args[@]}"}"); then
      printf 'dcr-gates: refix_gate PASS\n'
    else
      printf 'dcr-gates: refix_gate FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

if opt_in DCR_PRIORITY_GATE; then
  prio_args=()
  if [ -n "${DCR_PRIORITY_JSON:-}" ]; then
    prio_args=(--labels-json "${DCR_PRIORITY_JSON}")
  elif [ -n "${DCR_PRIORITY_REPO:-}" ] && [ -n "${DCR_PRIORITY_PR:-}" ]; then
    prio_args=(--repo "${DCR_PRIORITY_REPO}" --pr "${DCR_PRIORITY_PR}")
  fi
  if ! PRIORITY_GATE="$(delivery_script priority_gate.py)"; then
    FAIL=1
  elif [ "${#prio_args[@]}" -eq 0 ]; then
    printf 'dcr-gates: FAIL priority_gate (DCR_PRIORITY_GATE=1 needs DCR_PRIORITY_JSON, or DCR_PRIORITY_REPO + DCR_PRIORITY_PR)\n'
    FAIL=1
  else
    if [ -n "${DCR_PRIORITY_BUDGET:-}" ]; then
      prio_args+=(--budget "${DCR_PRIORITY_BUDGET}")
    fi
    extra_prio=()
    if [ -n "${DCR_PRIORITY_ARGS:-}" ]; then
      read -r -a extra_prio <<<"${DCR_PRIORITY_ARGS}"
    fi
    if python3 "${PRIORITY_GATE}" "${prio_args[@]}" "${extra_prio[@]+"${extra_prio[@]}"}"; then
      printf 'dcr-gates: priority_gate PASS\n'
    else
      printf 'dcr-gates: priority_gate FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

if opt_in DCR_FOCUS_GATE; then
  focus_args=(--repo "${REPO_ROOT}")
  if [ -n "${DCR_FOCUS_RECORD:-}" ]; then
    focus_args+=(--record "${DCR_FOCUS_RECORD}")
  fi
  if [ -n "${DCR_FOCUS_ITEM:-}" ]; then
    focus_args+=(--item "${DCR_FOCUS_ITEM}")
  fi
  if [ "${RANGE_STATE}" = ok ]; then
    focus_args+=(--base "${BASE_SHA}" --head "${HEAD_SHA}")
  fi
  if ! FOCUS_GATE="$(delivery_script focus_gate.py)"; then
    FAIL=1
  elif [ "${RANGE_STATE}" = partial ]; then
    printf 'dcr-gates: FAIL focus_gate (caller supplied an incomplete BASE_SHA/HEAD_SHA range)\n'
    FAIL=1
  elif [ "${RANGE_STATE}" = none ] && [ -z "${DCR_FOCUS_ITEM:-}" ]; then
    printf 'dcr-gates: FAIL focus_gate (no commit range and no DCR_FOCUS_ITEM: nothing to check)\n'
    FAIL=1
  else
    extra_focus=()
    if [ -n "${DCR_FOCUS_ARGS:-}" ]; then
      read -r -a extra_focus <<<"${DCR_FOCUS_ARGS}"
    fi
    if python3 "${FOCUS_GATE}" check "${focus_args[@]}" "${extra_focus[@]+"${extra_focus[@]}"}"; then
      printf 'dcr-gates: focus_gate PASS\n'
    else
      printf 'dcr-gates: focus_gate FAIL\n' >&2
      FAIL=1
    fi
  fi
fi

[ "${FAIL}" -eq 0 ] || die "one or more gates failed (see above)"
printf 'dcr-gates: all gates passed\n'
