#!/usr/bin/env bash
# skill-drift-check.sh — warn when the machine-installed deep-code-review skill
# has drifted from the public repository's main-branch VERSION.
#
# Compares two VERSION strings:
#   installed : ~/.claude/skills/deep-code-review/VERSION
#               (override with DCR_INSTALLED_VERSION_FILE)
#   upstream  : .claude/skills/deep-code-review/VERSION on
#               github.com/protocol/perun @ main
#               (read via the gh CLI; override the repo with DCR_REPO)
#
# Exit codes:
#   0  OK    — versions match.
#   0  SKIP  — no comparison is possible, so the guard stays out of the way and
#              never hard-fails its caller. Skipped cases: gh CLI absent, gh not
#              authenticated, network/API failure, empty upstream response, or
#              the skill not installed locally. Each prints a one-line reason.
#   1  DRIFT — both versions were read and they differ (the only failing case).
#   2  usage error.
#
# Design note: exit 1 fires ONLY on a genuine installed-vs-upstream mismatch.
# Every missing precondition skips (exit 0) rather than reporting false drift, so
# the script is safe to drop into any context (local shell, a warn-only hook, a
# make target) without spurious failures.
#
# This script is intentionally NOT wired into any git hook, CI job, or cron.
# It performs no writes and needs no sudo; its only side effect is one read-only
# HTTPS GET to the GitHub API (through gh).

set -uo pipefail   # deliberately NOT -e: every failure is handled explicitly.

REPO="${DCR_REPO:-protocol/perun}"
UPSTREAM_PATH=".claude/skills/deep-code-review/VERSION"
INSTALLED_FILE="${DCR_INSTALLED_VERSION_FILE:-${HOME}/.claude/skills/deep-code-review/VERSION}"

warn() { printf 'WARN: %s\n' "$*" >&2; }
info() { printf '%s\n' "$*"; }
skip() { printf 'SKIP: %s\n' "$*"; }

case "${1:-}" in
  -h|--help)
    sed -n '2,32p' "$0"
    exit 0
    ;;
  "") : ;;
  *)
    warn "unknown argument: $1 (use -h for help)"
    exit 2
    ;;
esac

# --- installed side ---------------------------------------------------------
if [[ ! -f "${INSTALLED_FILE}" ]]; then
  skip "deep-code-review not installed at ${INSTALLED_FILE} — nothing to compare."
  exit 0
fi
installed="$(tr -d '[:space:]' < "${INSTALLED_FILE}" 2>/dev/null || true)"
if [[ -z "${installed}" ]]; then
  skip "installed VERSION file is empty or unreadable: ${INSTALLED_FILE}."
  exit 0
fi

# --- gh availability (skip, never fail the caller) --------------------------
if ! command -v gh >/dev/null 2>&1; then
  skip "gh CLI not installed — cannot read upstream (installed=${installed})."
  exit 0
fi
if ! gh auth status >/dev/null 2>&1; then
  skip "gh CLI not authenticated — cannot read upstream (installed=${installed})."
  exit 0
fi

# --- upstream side ----------------------------------------------------------
# Prefer the raw media type: it returns the file body directly, sidestepping
# base64 and the BSD (-D) vs GNU (-d) decode-flag portability trap entirely.
upstream=""
if raw="$(gh api -H "Accept: application/vnd.github.raw" \
      "repos/${REPO}/contents/${UPSTREAM_PATH}?ref=main" 2>/dev/null)"; then
  upstream="$(printf '%s' "${raw}" | tr -d '[:space:]')"
fi
# Fallback: decode the base64 JSON payload if the raw type yielded nothing.
if [[ -z "${upstream}" ]]; then
  if b64="$(gh api "repos/${REPO}/contents/${UPSTREAM_PATH}?ref=main" --jq '.content' 2>/dev/null)" \
     && [[ -n "${b64}" ]]; then
    decoded="$(printf '%s' "${b64}" | base64 -D 2>/dev/null \
             || printf '%s' "${b64}" | base64 -d 2>/dev/null \
             || true)"
    upstream="$(printf '%s' "${decoded}" | tr -d '[:space:]')"
  fi
fi
if [[ -z "${upstream}" ]]; then
  skip "could not read upstream VERSION (network/API failure or empty) — installed=${installed}."
  exit 0
fi

# --- compare ----------------------------------------------------------------
if [[ "${installed}" == "${upstream}" ]]; then
  info "OK: deep-code-review ${installed} matches ${REPO}@main."
  exit 0
fi

warn "DRIFT: installed deep-code-review ${installed} != ${REPO}@main ${upstream}."
warn "Refresh: git -C <clone> checkout main && git pull --ff-only && ./install.sh --claude-only \"\$HOME\""
exit 1
