#!/usr/bin/env bash
# Local pre-merge hook point for the rival harness (scripts/rival_eval_keys.py, a wrapper that adds cost capture and answer keys to the hash-pinned scripts/rival_eval.py): scores only the skills this branch touches
# against their rivals on the frozen held-out sets and prints win rate, 95% CI and cost per skill. Runs on the developer's
# machine with a local PCSS_KEY (environment or repo-root .env); there is no CI secret, so CI never runs it.
# Advisory by default (exit 0, a missing key is a skip); RIVAL_EVAL_STRICT=1 exits 1 when any touched skill FAILs.
# Wire it as the pre-push extra tier:  DCR_PREPUSH_CMD="bash scripts/rival-eval-premerge.sh" git push
# or run it by hand before landing. RIVAL_EVAL_BASE (default origin/main) is the diff base.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
out="$(python3 "$ROOT/scripts/rival_eval_keys.py" run --changed "${RIVAL_EVAL_BASE:-origin/main}" --out "${TMPDIR:-/tmp}/rival-eval" 2>&1)"
rc=$?
printf '%s\n' "$out"
if printf '%s' "$out" | grep -q 'PCSS_KEY missing'; then echo "rival-eval skipped: no PCSS_KEY"; exit 0; fi
[ "$rc" -ne 0 ] && exit "$rc"
[ "${RIVAL_EVAL_STRICT:-0}" = 1 ] && printf '%s' "$out" | grep -q '| FAIL |' && exit 1
exit 0
