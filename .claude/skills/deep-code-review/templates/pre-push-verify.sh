#!/usr/bin/env bash
# pre-push-verify.sh — pre-push hook template: reruns the project's fast
# lint+unit tier on the pushed range before `git push` is allowed to proceed.
#
# WHY THIS EXISTS (issue #1093): a rebase or merge-conflict resolution is
# unverified code even when the branch's earlier commits were hook-checked —
# `git rebase --continue` does not re-invoke pre-commit on the replayed
# commits, and a conflict resolved by hand can carry a fresh lint/test defect
# that only surfaces once it reaches CI. This hook shortens that feedback
# loop locally. It is still SELF-REPORT, not the control: `git push
# --no-verify` bypasses it with no trace, and it never runs at all unless
# `core.hooksPath` points at the directory holding it. CI on the reviewed SHA
# stays the trusted gate — see
# `.claude/skills/deep-code-review/references/branch-and-merge-hygiene.md`'s
# "Self-report ≠ control" (not restated here).
#
# CONFLICT-MARKER CHECK (issue #1094): a raw `<<<<<<<`/`=======`/`>>>>>>>`
# marker left in a conflict resolution is a lint-tier failure that a cheap
# model tier can miss and DCR_PREPUSH_CMD may not catch (e.g. a lint config
# that doesn't flag it). So this hook runs `git diff --check` over the pushed
# range itself, before and independently of DCR_PREPUSH_CMD -- it fires even
# when that command is unset and DCR_PREPUSH_ALLOW_UNSET=1 lets the push
# through otherwise. Only lines reporting "leftover conflict marker" fail the
# push; other `git diff --check` whitespace complaints (trailing whitespace,
# space-before-tab) are ignored -- this hook is not a whitespace linter, and
# failing pushes on pre-existing whitespace would be friction nobody asked
# for. The check is range-scoped (base_sha..local_sha), so a marker-shaped
# line already sitting in the base never blocks. KNOWN FALSE POSITIVE: a
# Markdown setext-style H1 underlined with exactly 7 `=` characters reads as
# a conflict marker to `git diff --check`. Escape hatch: mark the file (or
# extension) `conflict-marker-size=32` in `.gitattributes`, which raises the
# marker-run threshold above what a real marker (7 chars) ever reaches and
# silences the false positive without disabling the real check.
#
# INSTALL: `install.sh --with-gates` copies this file to
# `<target>/.githooks/pre-push` (never overwrites an existing file there —
# writes `.new` instead) and prints, but does not run, the one-time opt-in:
#   git config core.hooksPath .githooks
# Without that `git config` line, Git never looks in `.githooks/` and this
# file is inert.
#
# MECHANISM GATE (refs #1380): CI's "Fix commits carry a pinned test" and
# "Prose lessons carry a mechanism" steps judge the WHOLE PR range, so a
# follow-up commit that edits a SKILL.md/reference without a test/eval in
# the same commit fails CI even when the lane's earlier gate run was green.
# When the repo has .github/workflows/ci.yml, this hook extracts those two
# steps' `run:` blocks (single source: the globs are never copied here, so
# they cannot drift) and runs them over merge-base(default branch)..HEAD,
# not just the pushed delta. No ci.yml: skipped.
#
# VERDICT CACHE (issue #1153; shared and tree-keyed since the gate-cache
# change): under heavy concurrent load (many agent lanes committing and
# pushing on one host), re-running DCR_PREPUSH_CMD every time the identical
# push is retried or re-invoked -- or again after pre-commit, a precheck
# script and the train gate already ran it on the same tree -- pays the full
# gate's cost again (13-16 minutes per push). Before running DCR_PREPUSH_CMD
# this hook asks scripts/gate_cache.py, the one PASS cache every stage
# shares. Its header owns the mechanism: key = (git tree of the pushed
# commit, gate-set version, config hash), stored under
# `$(git rev-parse --git-common-dir)/perun-gate-cache/`, entries at most 7
# days old, only an exit 0 is ever recorded (never a FAIL, never a run that
# edited tracked files), and editing any hook file, the cache script or a
# $PERUN_GATE_FILES path is a new gate set that misses every older entry.
# The command runs under `bash -c` with `set -o pipefail` (see
# DCR_PREPUSH_CMD below), so a piped command's real failure can never be
# cached as a pass.
#
# RANGE-AWARE BY DEFAULT: DCR_PREPUSH_CMD may itself consult BASE_SHA/HEAD_SHA
# -- e.g. to run only diff-affected tests, or `dcr-gates.sh`, whose fix-class
# check reads commit messages -- so its verdict is a function of the pushed
# range, not the tree alone (the rule #1153 established). By default the
# range (this ref's BASE_SHA and the pushed commit sha) therefore joins the
# config hash: a reworded commit or a different base never shares a verdict.
# When the tier is a pure function of the tree (lint, unit tests), declare
# DCR_PREPUSH_TREE_PURE=1: the range leaves the key, so the verdict is then
# shared across amends, rebases that keep the tree, and every other stage
# (pre-commit, precheck, the train gate) that runs the same command text
# through `gate_cache.py run`. `gate_map.py` lists which suites each stage
# runs and flags the ones that run more than once per tree.
#
# This cache never replaces CI: CI runs the reviewed SHA independently
# regardless of any local entry (see "Self-report ≠ control" above). The
# conflict-marker, mechanism and fast CI-parity checks below are range- or
# commit-message-based and cheap: they run on every push, never from cache.
# Without python3 or gate_cache.py the command simply runs uncached.
#
# CI MODE: when agentic-delivery's perun_policy.py is installed and `ci` resolves
# to `local-first`, a push of a branch that already exists on the remote prints
# a one-line notice (one push per PR; review fixes and conflicts are legitimate
# re-pushes). Warn-only: it never fails the push.
#
# CONFIGURATION (env vars):
#   DCR_PREPUSH_CMD             the fast tier to run before allowing the
#                                push, e.g. "make lint test-unit". Run through
#                                `bash -c` with `set -o pipefail` and its
#                                stdin from /dev/null (so it can never consume
#                                the ref list this hook is still reading off
#                                its own stdin, and a `cmd | tee log`-style
#                                pipeline's real failure can't be hidden by
#                                the last stage's own exit code and cached as
#                                a pass), so it may be a `&&`-chain or a
#                                pipeline. A non-zero exit REFUSES the push.
#                                Whitespace-only (e.g. exported but blank) is
#                                treated the same as unset, not as an
#                                empty-but-passing command.
#   DCR_PREPUSH_ALLOW_UNSET      when DCR_PREPUSH_CMD is unset (or
#                                whitespace-only), "1" lets the push through
#                                with a warning instead of failing closed.
#                                Unset, "0", or any other value: fails closed
#                                (the default — an unconfigured hook must not
#                                silently pass every push).
#   DCR_PREPUSH_DEFAULT_BRANCH   override the remote default branch used to
#                                compute the base for a brand-new branch
#                                push. Unset -> resolved from
#                                refs/remotes/<remote>/HEAD, falling back to
#                                "main" if that ref is not set locally (run
#                                `git remote set-head <remote> --auto` once
#                                to set it).
#   DCR_PREPUSH_SKIP_CACHE       "1" ignores an existing verdict-cache entry
#                                and always reruns DCR_PREPUSH_CMD (see
#                                VERDICT CACHE above); a passing run still
#                                writes a fresh entry. Unset/"0": use the
#                                cache.
#   PERUN_GATE_CACHE             "0"/"off" turns the shared verdict cache off
#                                entirely (no read, no write) for this push
#                                and every other gate_cache.py caller.
#   DCR_PREPUSH_TREE_PURE        "1" declares DCR_PREPUSH_CMD a pure function
#                                of the tree, so its verdict is shared across
#                                commits with the same tree and across stages
#                                (see RANGE-AWARE BY DEFAULT above). Unset:
#                                the pushed range joins the cache key.
#   DCR_PREPUSH_CACHE_KEY        optional extra text folded into the verdict-
#                                cache key (see VERDICT CACHE above) --
#                                widen it with a toolchain/environment
#                                fingerprint (e.g. a language runtime
#                                version) whenever DCR_PREPUSH_CMD's real
#                                behavior depends on something this hook
#                                cannot otherwise see. Unset: the key is
#                                tree + gate set + command (+ the range
#                                unless DCR_PREPUSH_TREE_PURE=1).
#
# For each pushed ref this script exports BASE_SHA / HEAD_SHA (the same
# convention `dcr-gates.sh` uses) describing the commit range being pushed,
# so DCR_PREPUSH_CMD may consult them (e.g. to invoke `dcr-gates.sh` itself,
# range-scoped) — a flat command that ignores them, like `make lint
# test-unit`, works unchanged.
#
# Git feeds the pushed refs to this hook's STDIN, one line per ref:
#   <local ref> <local sha> <remote ref> <remote sha>
# A deleted ref (local sha all zeros — 40 hex for SHA-1 or 64 for a
# SHA-256 repo, matched by `^0+$`, not a hardcoded 40-char literal) is
# skipped: nothing local to verify. A brand-new branch (remote sha all
# zeros, same either-length match) has no remote-side commit to diff
# against, so BASE_SHA becomes the merge-base of the local head and the
# remote's default branch (falling back to the local branch's root commit if
# no merge-base is found — e.g. an unrelated-history remote).
#
# PUSHED-RANGE HONESTY: this hook can only ever run DCR_PREPUSH_CMD against
# the tree that is actually checked out on disk right now — it cannot check
# out each pushed ref's exact commit first. So for every non-deleted pushed
# ref it refuses (clear message, fails closed) unless the pushed local sha
# equals `git rev-parse HEAD` AND the working tree is clean; otherwise a
# "pass" would silently verify a tree that is not the code being pushed.
#
# HOLD: while `$(git rev-parse --git-common-dir)/DCR_HOLD` or a repo-root
# `.dcr-hold` exists, this hook refuses EVERY push (deletes and empty ref
# lists included) and prints the file's first line as the reason. An
# operator creates one to freeze pushes (`echo "owner review" >
# "$(git rev-parse --git-common-dir)/DCR_HOLD"`) and deletes it to lift the
# hold. The common-dir file is shared by every linked worktree and is not
# a tracked file, so a lane cannot commit it away. A lane that repoints or
# "self-heals" `core.hooksPath` to this template does not escape the hold,
# because the check is in the hook itself. Like the rest of this hook it is
# self-report: `git push --no-verify`, or a `core.hooksPath` that points
# somewhere without this hook, skips it.
#
# Exit code: 0 iff every non-deleted pushed ref's tier run passed (or was
# explicitly allowed through unset/blank). Fails closed on every other path.
set -euo pipefail

remote_name="${1:-origin}"

die() {
  printf 'pre-push-verify: %s\n' "$*" >&2
  exit 1
}

# HOLD check (see HOLD above): runs before any ref is read.
hold_common="$(git rev-parse --git-common-dir 2>/dev/null || true)"
hold_top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
for hold_file in "${hold_common:+${hold_common}/DCR_HOLD}" "${hold_top:+${hold_top}/.dcr-hold}"; do
  if [ -n "${hold_file}" ] && [ -e "${hold_file}" ]; then
    hold_reason="$(head -n 1 "${hold_file}" 2>/dev/null || true)"
    die "HOLD -- ${hold_file} exists, so every push is refused until it is removed. Reason: ${hold_reason:-(none given)}"
  fi
done

# is_zero_sha <sha> — true iff <sha> is non-empty and every char is '0'.
# Matches `^0+$` without hardcoding a length, so a 40-hex SHA-1 zero id and a
# 64-hex SHA-256 zero id (a SHA-256 repo's "no commit" sentinel) both count.
is_zero_sha() {
  case "$1" in
    ''|*[!0]*) return 1 ;;
    *) return 0 ;;
  esac
}

# is_blank <str> — true iff <str> is empty or contains only whitespace.
is_blank() {
  case "$1" in
    *[![:space:]]*) return 1 ;;
    *) return 0 ;;
  esac
}

# resolve_default_branch — print the remote's default branch name.
# DCR_PREPUSH_DEFAULT_BRANCH wins if set; otherwise read
# refs/remotes/<remote>/HEAD (set by `git clone` / `git remote set-head
# --auto`); otherwise fall back to "main".
resolve_default_branch() {
  if [ -n "${DCR_PREPUSH_DEFAULT_BRANCH:-}" ]; then
    printf '%s' "${DCR_PREPUSH_DEFAULT_BRANCH}"
    return 0
  fi
  head_ref="$(git symbolic-ref -q "refs/remotes/${remote_name}/HEAD" 2>/dev/null || true)"
  if [ -n "${head_ref}" ]; then
    printf '%s' "${head_ref#refs/remotes/${remote_name}/}"
    return 0
  fi
  printf 'main'
}

# find_gate_cache — print the path of gate_cache.py (next to this template's
# own scripts/ dir when run from the skill tree, else the installed skill
# path under the repo root), or nothing when python3 or the script is absent.
find_gate_cache() {
  command -v python3 >/dev/null 2>&1 || return 0
  for gc_try in "$(dirname "$0")/../scripts/gate_cache.py" ".claude/skills/deep-code-review/scripts/gate_cache.py"; do
    if [ -f "${gc_try}" ]; then printf '%s' "${gc_try}"; return 0; fi
  done
}

print_unset_help() {
  cat >&2 <<EOF
pre-push-verify: DCR_PREPUSH_CMD is not set (or whitespace-only) -- refusing to push (fail closed).
Configure the fast tier this hook must run before every push, e.g. in your
shell profile or a project-local env file your shell sources:
  export DCR_PREPUSH_CMD="make lint test-unit"
To push anyway with no configured tier (not recommended), set:
  export DCR_PREPUSH_ALLOW_UNSET=1
EOF
}

fail=0
saw_ref=0

# Captured once, before reading any ref: the tree this hook is actually able
# to verify. Every non-deleted pushed ref is checked against this snapshot
# (see PUSHED-RANGE HONESTY above) rather than re-read per ref, so a
# DCR_PREPUSH_CMD invocation that itself dirties the tree can't change the
# answer mid-loop.
current_head="$(git rev-parse HEAD 2>/dev/null || true)"
tree_is_dirty=1
if git diff-index --quiet HEAD -- 2>/dev/null && [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  tree_is_dirty=0
fi

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -n "${local_ref:-}" ] || continue
  saw_ref=1

  if is_zero_sha "${local_sha}"; then
    printf 'pre-push-verify: %s is a delete -- skipping\n' "${remote_ref}"
    continue
  fi

  if [ -z "${current_head}" ] || [ "${local_sha}" != "${current_head}" ]; then
    die "refusing ${local_ref} (${local_sha}) -- this hook can only verify the tree currently checked out (HEAD is ${current_head:-unknown}), and that does not match the commit being pushed. Check out ${local_sha} (or push from that commit) before pushing, or run DCR_PREPUSH_CMD yourself against the right tree."
  fi
  if [ "${tree_is_dirty}" -eq 1 ]; then
    die "refusing ${local_ref} -- the working tree is dirty, so this hook's checked-out tree no longer matches HEAD (${current_head}), which is what it verifies. Commit or stash your changes before pushing."
  fi

  if is_zero_sha "${remote_sha}"; then
    default_branch="$(resolve_default_branch)"
    default_ref="refs/remotes/${remote_name}/${default_branch}"
    base_sha=""
    if git rev-parse --verify -q "${default_ref}" >/dev/null 2>&1; then
      base_sha="$(git merge-base "${default_ref}" "${local_sha}" 2>/dev/null || true)"
    fi
    if [ -z "${base_sha}" ]; then
      printf 'pre-push-verify: %s is a new branch with no merge-base against %s -- verifying its full local history\n' \
        "${local_ref}" "${default_ref}" >&2
      base_sha="$(git rev-list --max-parents=0 "${local_sha}" | tail -n1)"
    fi
  else
    base_sha="${remote_sha}"
    # Policy `ci: local-first` expects one push per PR: a branch that already exists on the remote is a re-push.
    # Warn-only (a review fix or a conflict is a legitimate re-push); the default branch and a missing
    # perun_policy.py (agentic-delivery not installed) are skipped.
    ci_policy=".claude/skills/agentic-delivery/scripts/perun_policy.py"
    if [ -f "${ci_policy}" ] && [ "${remote_ref}" != "refs/heads/$(resolve_default_branch)" ] \
      && [ "$(python3 "${ci_policy}" ci 2>/dev/null || true)" = "local-first" ]; then
      printf 'pre-push-verify: ci=local-first expects one push per PR and %s already exists on the remote: re-push only for review feedback or a conflict, and run every gate locally first (perun_policy.py ci)\n' "${remote_ref}" >&2
    fi
  fi

  export BASE_SHA="${base_sha}"
  export HEAD_SHA="${local_sha}"

  # Conflict-marker check (#1094): runs before, and independently of, the
  # DCR_PREPUSH_CMD unset check below, so it fires even when that command is
  # unset and DCR_PREPUSH_ALLOW_UNSET=1 would otherwise let the push through.
  # `git diff --check` exits 2 on any issue (marker or whitespace) -- the
  # trailing `|| true` on its command substitution keeps `set -e` from
  # aborting on that non-zero exit, then its stdout is filtered down to
  # marker lines only.
  marker_check_output="$(git diff --check "${base_sha}" "${local_sha}" 2>/dev/null || true)"
  marker_lines="$(printf '%s\n' "${marker_check_output}" | grep -F 'leftover conflict marker' || true)"
  if [ -n "${marker_lines}" ]; then
    printf '%s\n' "${marker_lines}" >&2
    printf 'pre-push-verify: FAIL -- rejecting push of %s (leftover conflict marker)\n' "${local_ref}" >&2
    fail=1
    continue
  fi

  # Mechanism gate (#1380): CI's fix-class steps over the whole branch range.
  ci_yml=".github/workflows/ci.yml"
  if [ -f "${ci_yml}" ]; then
    mg_base="${base_sha}"
    default_ref="refs/remotes/${remote_name}/$(resolve_default_branch)"
    if git rev-parse --verify -q "${default_ref}" >/dev/null 2>&1; then
      mg_base="$(git merge-base "${default_ref}" "${local_sha}" 2>/dev/null || printf '%s' "${base_sha}")"
    fi
    if ! command -v python3 >/dev/null 2>&1 || [ ! -f .claude/skills/deep-code-review/scripts/fix_class_gate.py ]; then
      die "pre-push: python3 (or fix_class_gate.py) missing — cannot verify mechanism rule; install python3 or push with --no-verify knowingly"
    fi
    mg_fail=0
    for mg_step in "Fix commits carry a pinned test" "Prose lessons carry a mechanism"; do
      # awk-v-ok: one CI step name
      mg_script="$(awk -v n="- name: ${mg_step}" 'index($0,n){f=1;next} f&&/run: \|/{r=1;next} r&&/^ {0,9}[^ ]/{exit} r' "${ci_yml}")"
      [ -n "${mg_script}" ] || continue
      if ! BASE_SHA="${mg_base}" HEAD_SHA="${local_sha}" bash -c "${mg_script}" </dev/null >&2; then
        printf 'pre-push-verify: FAIL -- "%s" would fail CI for %s..%s. Fix: add the test/eval to the same commit, or squash onto %s.\n' \
          "${mg_step}" "${mg_base}" "${local_sha}" "${default_ref}" >&2
        mg_fail=1
      fi
    done
    [ "${mg_fail}" -eq 0 ] || { fail=1; continue; }
  fi

  # Fast CI-parity gates (each <1s; only when this repo ships them): the cheap deterministic CI steps lanes
  # kept skipping because the full scripts/test-ci-gates.sh is slow. Each failure names the exact fix.
  if [ -f scripts/ci-gates.sh ] && command -v python3 >/dev/null 2>&1; then
    fg_base="${base_sha}"
    fg_ref="refs/remotes/${remote_name}/$(resolve_default_branch)"
    git rev-parse --verify -q "${fg_ref}" >/dev/null 2>&1 && fg_base="$(git merge-base "${fg_ref}" "${local_sha}" 2>/dev/null || printf '%s' "${base_sha}")"
    fg_fail=0
    fg() { # fg <name> <fix> <cmd...>: run quietly, print output only on failure
      fg_name="$1"; fg_fix="$2"; shift 2
      if ! fg_out="$("$@" 2>&1 </dev/null)"; then
        printf '%s\npre-push-verify: FAIL -- %s. Fix: %s\n' "${fg_out}" "${fg_name}" "${fg_fix}" >&2
        fg_fail=1
      fi
    }
    in_tree() { (cd "${fg_tree}" && unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE && "$@"); }
    # Removes this gate's throwaway worktree and mktemp dir. Runs on every exit path (EXIT, INT, TERM, failed
    # worktree add, normal end). Guarded: deletes only a non-empty fg_tmp under ${TMPDIR:-/tmp} with the dcr-prepush. prefix.
    fg_cleanup() {
      case "${fg_tmp:-}" in "${TMPDIR:-/tmp}"/dcr-prepush.*) git worktree remove --force "${fg_tmp}/t" >/dev/null 2>&1 || :; rm -rf "${fg_tmp}" ;; esac
      fg_tmp=""; fg_tree="${PWD}"
    }
    # Derived files (INDEX.md, SHA256SUMS) are not committed by lane PRs: they are rebuilt at land time
    # (VERSION moved vs the base) and checked there. Unlanded, CI rebuilds them, so skip the stale checks.
    derived=1; [ -f scripts/regen-unlanded.sh ] && bash scripts/regen-unlanded.sh --check "${fg_base}" && derived=0
    # Unlanded, CI regenerates derived files (INDEX.md, size rows) BEFORE size-ratchet and bench-check, so run
    # both on a throwaway checkout of the pushed commit after the same regen: the user's tree is never touched.
    fg_tree="${PWD}"; fg_tmp=""
    if [ "${derived}" -eq 0 ] && { [ -f scripts/size-budgets.tsv ] || [ -f scripts/bench_check.py ]; }; then
      fg_tmp="$(mktemp -d "${TMPDIR:-/tmp}/dcr-prepush.XXXXXX")"
      trap fg_cleanup EXIT
      trap 'fg_cleanup; exit 130' INT TERM
      # A sandbox that denies writes under .git/worktrees still allows a shared clone in TMPDIR: fall back to it,
      # so a host restriction never turns into "the gate cannot run" (the pressure that ends in --no-verify).
      if git worktree add -q --detach "${fg_tmp}/t" "${local_sha}" >/dev/null 2>&1 \
        || { printf 'pre-push-verify: note -- git worktree add denied; using a shared clone instead.\n' >&2
             # Own git env (an inherited GIT_DIR would point checkout at the host); copy the host's remote-tracking
             # refs so origin/<default> in the clone is the host's, as in a worktree, not the host's local branch.
             (unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
              git clone -q --shared --no-checkout "${PWD}" "${fg_tmp}/t" \
                && git -C "${fg_tmp}/t" fetch -q "${PWD}" '+refs/remotes/*:refs/remotes/*' \
                && git -C "${fg_tmp}/t" checkout -q --detach "${local_sha}") >/dev/null 2>&1; }; then
        fg_tree="${fg_tmp}/t"
        fg "regen-unlanded.sh (CI runs it before the ratchet)" "run 'bash scripts/regen-unlanded.sh ${fg_base}' on a clean checkout and fix what it prints" \
          in_tree bash scripts/regen-unlanded.sh "${fg_base}"
      else
        printf 'pre-push-verify: FAIL -- cannot create a throwaway checkout of %s. Fix: free disk or TMPDIR, then push again.\n' "${local_sha}" >&2
        fg_fail=1
        fg_cleanup
      fi
    fi
    [ -f scripts/size-budgets.tsv ] && fg "size-ratchet vs ${fg_base}" \
      "add the marker line quoted in the RATCHET FAIL above ('size-budget-raise: <path> <old>→<new> <reason>') to a commit message in this range; CI rebuilds derived files first, so growth of INDEX.md or any skill file counts" \
      in_tree bash scripts/ci-gates.sh size-ratchet --base "${fg_base}" --config scripts/size-budgets.tsv .
    [ -f scripts/bench_check.py ] && fg "bench_check --changed ${fg_base}" \
      "fix the bench dir named above (checks: header of scripts/bench_check.py)" \
      in_tree python3 scripts/bench_check.py --changed "${fg_base}"
    fg_cleanup
    [ -f scripts/mustload-budgets.tsv ] && fg "mustload floor/ceiling pin" \
      "shrink the must-load read set, or update the pin in scripts/mustload-budgets.tsv in the same commit with the reason" \
      bash scripts/ci-gates.sh mustload --config scripts/mustload-budgets.tsv .
    [ -f scripts/run-evals.py ] && fg "run-evals --selftest" \
      "tag any chat-unanswerable expectation (e.g. an untagged 'Loads ...') with [needs_files] in the skill's evals/evals.json" \
      python3 scripts/run-evals.py --selftest
    [ "${derived}" -eq 1 ] && [ -f scripts/skill_index.py ] && fg "INDEX.md stale" \
      "run 'bash scripts/land-release.sh --regen' and commit the result (land commits only)" \
      python3 scripts/skill_index.py --check
    [ "${derived}" -eq 1 ] && [ -f scripts/write-checksums.sh ] && fg "SHA256SUMS stale" \
      "run 'bash scripts/land-release.sh --regen' (it pins SHA256SUMS last) and commit the result (land commits only)" \
      bash -c 'o="$(git rev-parse --git-common-dir)/dcr-sums.tmp"; bash scripts/write-checksums.sh "$o" >/dev/null && cmp -s "$o" SHA256SUMS'
    [ -f CHANGELOG.md ] && [ -f scripts/ci-gates.sh ] && fg "CHANGELOG version heading" \
      "put unreleased notes in changelog.d/<slug>.md, not CHANGELOG.md; land-release.sh stamps the heading at land time" \
      bash scripts/ci-gates.sh version .
    [ -d changelog.d ] && [ -f scripts/size-budgets.tsv ] && fg "changelog fragments" \
      "fix the fragment named above (rules: the 'fragments' header in scripts/ci-gates.sh)" \
      bash scripts/ci-gates.sh fragments --config scripts/size-budgets.tsv changelog.d
    [ "${fg_fail}" -eq 0 ] || { fail=1; continue; }
  fi

  # Warn-only scope-creep report (new files/deps/single-impl types); never fails the push.
  scope_check=".claude/skills/agentic-delivery/scripts/scope_creep_check.py"
  if [ -f "${scope_check}" ]; then
    python3 "${scope_check}" "${base_sha}" "${local_sha}" >&2 || true
  fi

  # Warn-only: new scripts with no caller (built but never wired); never fails the push.
  wired_check=".claude/skills/agentic-delivery/scripts/wired_check.py"
  if [ -f "${wired_check}" ]; then
    python3 "${wired_check}" "${base_sha}" "${local_sha}" >&2 || true
  fi

  # Warn-only: tests that read the real clock (red at the next week rollover); never fails the push.
  clock_lint=".claude/skills/agentic-delivery/scripts/clock_lint.py"
  if [ -f "${clock_lint}" ]; then
    python3 "${clock_lint}" --base "${base_sha}" --head "${local_sha}" --deadline 5 >&2 || true
  fi

  if is_blank "${DCR_PREPUSH_CMD:-}"; then
    if [ "${DCR_PREPUSH_ALLOW_UNSET:-0}" = "1" ]; then
      printf 'pre-push-verify: DCR_PREPUSH_CMD is unset -- allowing push through (DCR_PREPUSH_ALLOW_UNSET=1)\n' >&2
      continue
    fi
    print_unset_help
    die "DCR_PREPUSH_CMD unset (see above)"
  fi

  run_msg="$(printf 'pre-push-verify: %s (%s..%s): running: %s' "${local_ref}" "${base_sha}" "${local_sha}" "${DCR_PREPUSH_CMD}")"
  gate_cache="$(find_gate_cache)"
  if [ -n "${gate_cache}" ]; then
    gc_args=(run --stage pre-push --tree "${local_sha}" --key "${DCR_PREPUSH_CACHE_KEY:-}" --say "${run_msg}")
    [ "${DCR_PREPUSH_TREE_PURE:-0}" = "1" ] || gc_args+=(--base "${base_sha}" --head "${local_sha}")
    gc_mode="${PERUN_GATE_CACHE:-}"
    if [ "${DCR_PREPUSH_SKIP_CACHE:-0}" = "1" ]; then
      case "${gc_mode}" in 0|off|false|no) ;; *) gc_mode=refresh ;; esac
    fi
    gate_cmd=(env PERUN_GATE_CACHE="${gc_mode}" python3 "${gate_cache}" "${gc_args[@]}" -c "${DCR_PREPUSH_CMD}")
  else
    printf '%s\n' "${run_msg}"
    gate_cmd=(bash -c "set -o pipefail; ${DCR_PREPUSH_CMD}")
  fi
  if ! "${gate_cmd[@]}" </dev/null; then
    printf 'pre-push-verify: FAIL -- rejecting push of %s (DCR_PREPUSH_CMD exited non-zero)\n' "${local_ref}" >&2
    fail=1
  fi
done

# No ref lines at all (git invoking the hook with an empty stdin) is not a
# failure -- there is nothing to verify.
[ "${saw_ref}" -eq 1 ] || exit 0

[ "${fail}" -eq 0 ] || die "one or more pushed refs failed the pre-push tier (see above)"
exit 0
