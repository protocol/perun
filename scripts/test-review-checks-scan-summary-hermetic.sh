#!/usr/bin/env bash
# test-review-checks-scan-summary.sh must not depend on the host's semgrep cache. A host that has a warm p/default snapshot
# makes review_checks.sh load the local file instead of `--config p/default`, which that test's semgrep check rejects; the test
# therefore empties the cache root it runs under. Here the root it inherits holds a warm snapshot, and the test must still pass.
# Hermetic: a throwaway cache root; nothing is installed or downloaded.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcsum-hermetic.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT
mkdir -p "$T/cache/dcr-tools/semgrep"
printf 'rules: []\n' >"$T/cache/dcr-tools/semgrep/p-default.yml"
if DCR_CACHE_ROOT="$T/cache" bash "$ROOT/scripts/test-review-checks-scan-summary.sh" >"$T/out" 2>&1; then
  echo "ok: the scan-summary test passes on a host with a warm semgrep snapshot"
else
  grep '^FAIL' "$T/out" || tail -5 "$T/out"
  echo "FAILED: the scan-summary test depends on the host's semgrep cache"; exit 1
fi
# Same for the checkout path: lanes run from .claude/worktrees/<name>, so "worktrees" sits in every absolute path the tool logs.
mkdir -p "$T/.claude/worktrees/w"; ln -s "$ROOT/scripts" "$T/.claude/worktrees/w/scripts"
mkdir "$T/.claude/worktrees/w/.claude"; ln -s "$ROOT/.claude/skills" "$T/.claude/worktrees/w/.claude/skills"
if bash "$T/.claude/worktrees/w/scripts/test-review-checks-scan-summary.sh" >"$T/out2" 2>&1; then
  echo "ok: the scan-summary test passes from a checkout path containing 'worktrees'"
else
  grep '^FAIL' "$T/out2" || tail -5 "$T/out2"
  echo "FAILED: the scan-summary test depends on the checkout path"; exit 1
fi
