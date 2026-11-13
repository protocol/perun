#!/usr/bin/env bash
# Guard for .gitleaks.toml: the fixture allowlist must not blind gitleaks.
# Skips (exit 0) when gitleaks is absent. Otherwise requires that
# (1) a fake AWS key in a temp file outside the allowlisted paths is detected
# as an aws-access-token finding, both with the repo config and (control) with
# the default config, and (2) the allowlisted fixture tree scans clean.
set -uo pipefail
cd "$(dirname "$0")/.."
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed: SKIP test_gitleaks_allowlist"
  exit 0
fi
tmp=$(mktemp -d "${TMPDIR:-/tmp}/gl-allow.XXXXXX") || { echo "FAIL: mktemp"; exit 1; }
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/probe"
# Fictional key assembled at runtime so this file holds no literal. Default rules
# ignore keys containing EXAMPLE, so the probe key must not contain it.
printf 'aws_access_key_id = %s\n' "AKIA""QYLPMN5HHH""FPZAM2" > "$tmp/probe/leak.txt"

# detects <label> [extra gitleaks args]: exit 1 and an aws-access-token finding.
detects() {
  local label=$1; shift
  rm -f "$tmp/r.json"  # a stale report from an earlier run must never satisfy this one
  gitleaks dir --no-banner --report-format json --report-path "$tmp/r.json" "$@" "$tmp/probe" >/dev/null 2>&1
  local rc=$?
  if [ "$rc" -ne 1 ] || ! grep -q '"RuleID": *"aws-access-token"' "$tmp/r.json" 2>/dev/null; then
    echo "FAIL: probe not detected as aws-access-token ($label, exit $rc)"
    exit 1
  fi
}
detects "default config control"
detects "repo config" --config .gitleaks.toml

shopt -s nullglob
heldout=(docs/bench/secrets-heldout*/)
if [ "${#heldout[@]}" -lt 12 ]; then
  echo "FAIL: expected >=12 secrets-heldout dirs, found ${#heldout[@]}"
  exit 1
fi
fixtures=("${heldout[@]}" docs/bench/g1-matrix/heldout/ scripts/test_secret_extra_rules_w5.py scripts/test_secret_precision.py)
for p in "${fixtures[@]}"; do
  if [ ! -e "$p" ]; then
    echo "FAIL: fixture path missing: $p"
    exit 1
  fi
  if ! gitleaks dir --no-banner --config .gitleaks.toml "$p" >/dev/null 2>&1; then
    echo "FAIL: allowlisted fixture path still flagged: $p"
    exit 1
  fi
done
echo "PASS: test_gitleaks_allowlist"
