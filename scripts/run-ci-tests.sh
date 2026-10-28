#!/usr/bin/env bash
# run-ci-tests.sh — local full ci-tests suite (every scripts/ci-tests.d/*.sh, as the CI "Per-PR tests" step runs them).
# Also runs the privacy gate and the trigger lint (CI's "Prose lessons carry a mechanism") before the tests.
# Exit 0 only when all pass; then records the last-known-good pointer (lkg.py record, HEAD). A failure records nothing.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# PERUN_RUN_DIR (optional): this run's log dir; plain mkdir refuses a dir that already exists, so a rerun never overwrites an earlier run's evidence.
[ -z "${PERUN_RUN_DIR:-}" ] || mkdir "$PERUN_RUN_DIR" || { echo "run-ci-tests: run dir $PERUN_RUN_DIR already exists; pick a fresh one" >&2; exit 1; }
# The two cheap CI gates a push is most often rejected on, run first (a missing privacy input or an unresolvable base fails closed).
echo "== privacy"
[ -f scripts/ci-gates.sh ] && [ -f .banlist.txt ] || { echo "run-ci-tests: FAIL privacy: scripts/ci-gates.sh or .banlist.txt missing (fail closed)" >&2; exit 1; }
bash scripts/ci-gates.sh privacy --banlist .banlist.txt . || { echo "run-ci-tests: FAIL privacy" >&2; exit 1; }
gate=.claude/skills/deep-code-review/scripts/fix_class_gate.py
if [ -f "$gate" ]; then
  echo "== trigger lint"
  base="${RUN_CI_BASE:-$(git merge-base HEAD origin/main 2>/dev/null)}"
  [ -n "$base" ] || { echo "run-ci-tests: FAIL trigger lint: no base (no origin/main; set RUN_CI_BASE)" >&2; exit 1; }
  python3 "$gate" --base "$base" --head HEAD \
    --trigger-glob '.claude/skills/*/references/*.md' --trigger-glob '.claude/skills/*/SKILL.md' \
    --test-glob '.claude/skills/*/evals/evals.json' --test-glob '.claude/skills/*/scripts/*' \
    --test-glob 'scripts/test-ci-gates.sh' --test-glob 'scripts/test-*.sh' --test-glob 'scripts/test_*.py' \
    || { echo "run-ci-tests: FAIL trigger lint" >&2; exit 1; }
fi
for t in scripts/ci-tests.d/*.sh; do
  echo "== $t"
  # (a ci-test that truly needs the network exports PERUN_ALLOW_NET=1 itself; see scrub_env.sh)
  # scrubbed child env: no real gh login/token/network, no git hook vars, no CLAUDE* session vars (scrub_env.sh)
  SCRUB_PREFIXES="${SCRUB_PREFIXES:-CLAUDE}" bash .claude/skills/agentic-delivery/scripts/scrub_env.sh bash -e "$t" || { echo "run-ci-tests: FAIL $t" >&2; exit 1; }
done
python3 .claude/skills/agentic-delivery/scripts/lkg.py record >/dev/null || echo "run-ci-tests: lkg record failed (ignored)" >&2
python3 .claude/skills/agentic-delivery/scripts/lkg.py verdict "$(python3 .claude/skills/agentic-delivery/scripts/lkg.py path)" >/dev/null || echo "run-ci-tests: lkg receipt does not verify against HEAD (ignored)" >&2
