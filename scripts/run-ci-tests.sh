#!/usr/bin/env bash
# run-ci-tests.sh — local full ci-tests suite (every scripts/ci-tests.d/*.sh, as the CI "Per-PR tests" step runs them).
# Exit 0 only when all pass; then records the last-known-good pointer (lkg.py record, HEAD). A failure records nothing.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for t in scripts/ci-tests.d/*.sh; do
  echo "== $t"
  bash -e "$t" || { echo "run-ci-tests: FAIL $t" >&2; exit 1; }
done
python3 .claude/skills/agentic-delivery/scripts/lkg.py record >/dev/null || echo "run-ci-tests: lkg record failed (ignored)" >&2
