#!/usr/bin/env bash
# Write SHA256SUMS for the shipped skill trees (AST02 pin surface).
# Paths are repo-relative, sorted, LC_ALL=C. SHA256SUMS itself is excluded.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${1:-SHA256SUMS}"
export LC_ALL=C
{
  # every .claude/skills/<dir>/ is a shipped skill; globbed so a new skill never edits this list
  find .claude/skills/*/ \
       -name __pycache__ -prune -o -type f ! -name SHA256SUMS ! -name '*.pyc' -print | sort
} | while IFS= read -r f; do
  sha256sum "$f"
done >"$OUT"
printf 'wrote %s (%s files)\n' "$OUT" "$(wc -l <"$OUT" | tr -d ' ')"
