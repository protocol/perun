#!/usr/bin/env bash
# Guard for .gitleaks.toml: the fixture allowlist must not blind gitleaks.
# Skips (exit 0) when gitleaks is absent. Otherwise requires that
# (1) a fake AWS key in a temp file outside the allowlisted paths is still
# detected, and (2) the allowlisted fixture tree scans clean.
set -uo pipefail
cd "$(dirname "$0")/.."
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed: SKIP test_gitleaks_allowlist"
  exit 0
fi
tmp=$(mktemp -d "${TMPDIR:-/tmp}/gl-allow.XXXXXX") || { echo "FAIL: mktemp"; exit 1; }
trap 'rm -rf "$tmp"' EXIT
# Fictional key assembled at runtime so this file holds no literal. Default rules
# ignore keys containing EXAMPLE, so the probe key must not contain it.
printf 'aws_access_key_id = %s\n' "AKIA""QYLPMN5HHH""FPZAM2" > "$tmp/leak.txt"
if gitleaks dir --no-banner --config .gitleaks.toml "$tmp" >/dev/null 2>&1; then
  echo "FAIL: fake key outside the allowlist was not detected"
  exit 1
fi
fixtures=$(ls -d docs/bench/secrets-heldout* docs/bench/g1-matrix/heldout scripts/test_secret_extra_rules_w5.py scripts/test_secret_precision.py 2>/dev/null)
for p in $fixtures; do
  if ! gitleaks dir --no-banner --config .gitleaks.toml "$p" >/dev/null 2>&1; then
    echo "FAIL: allowlisted fixture path still flagged: $p"
    exit 1
  fi
done
echo "PASS: test_gitleaks_allowlist"
