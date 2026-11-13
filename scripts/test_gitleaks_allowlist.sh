#!/usr/bin/env bash
# Guard for .gitleaks.toml: the fixture allowlist must not blind gitleaks.
# Skips (exit 0) when gitleaks is absent. Otherwise requires that
# (1) a fake AWS key in a temp file outside the allowlisted paths is detected
# as an aws-access-token finding, both with the repo config and (control) with
# the default config, (2) the allowlisted fixture tree scans clean, and (3) a
# fresh key appended to a copy of each narrowly allowlisted test script, at its
# real relative path, is still detected while the unmodified copy stays clean,
# and (4) a history scan, when in a git checkout, reports 0 findings.
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

# Narrow allowlist: only the fictional values in the 2 scripts are exempt.
cfg=$PWD/.gitleaks.toml
for f in scripts/test_secret_extra_rules_w5.py scripts/test_secret_precision.py; do
  mkdir -p "$tmp/rel/$(dirname "$f")" && cp "$f" "$tmp/rel/$f" || { echo "FAIL: copy $f"; exit 1; }
done
scan_rel() { (cd "$tmp/rel" && gitleaks dir --no-banner --config "$cfg" "$@" . >/dev/null 2>&1); }
if ! scan_rel; then
  echo "FAIL: unmodified script copies flagged at their real relative paths"
  exit 1
fi
for f in scripts/test_secret_extra_rules_w5.py scripts/test_secret_precision.py; do
  printf 'probe_key = "%s"\n' "AKIA""ZXCVBNM3QW""ERTY27" >> "$tmp/rel/$f"
  if scan_rel; then
    echo "FAIL: real key appended to $f not detected"
    exit 1
  fi
  cp "$f" "$tmp/rel/$f"
done
# History scan: .gitleaksignore covers the triaged fictional hits, so 0 findings remain.
if [ -e .git ]; then
  rm -f "$tmp/h.json"
  gitleaks git --no-banner --log-opts=HEAD -c .gitleaks.toml --report-format json --report-path "$tmp/h.json" >/dev/null 2>&1
  if [ "$?" -ne 0 ] || [ "$(grep -c '"Fingerprint"' "$tmp/h.json" 2>/dev/null)" != 0 ]; then
    echo "FAIL: history scan reports findings (extend .gitleaksignore only after triage)"
    exit 1
  fi
fi
echo "PASS: test_gitleaks_allowlist"
