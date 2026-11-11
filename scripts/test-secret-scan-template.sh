#!/usr/bin/env bash
# Static checks on templates/secret-scan.yml: gitleaks and checkout pinned, weekly schedule, no gitleaks-action, no path allowlist.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
F="$ROOT/.claude/skills/deep-code-review/templates/secret-scan.yml"
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
body=$(grep -v '^ *#' "$F")
grep -qE 'echo "[0-9a-f]{64}  gitleaks.tgz" \| sha256sum -c' <<<"$body"; chk $? "gitleaks pinned with a sha256 check"
grep -qE 'uses: actions/checkout@[0-9a-f]{40}( |$)' <<<"$body"; chk $? "checkout pinned by 40-hex SHA"
grep -q 'persist-credentials: false' <<<"$body"; chk $? "checkout drops credentials"
grep -qE '^  schedule:' <<<"$body"; chk $? "has a schedule trigger"
! grep -qi 'gitleaks-action' <<<"$body"; chk $? "never uses gitleaks-action"
! grep -qiE 'allowlist|--config|\[\[allowlists|paths *=|--gitleaks-ignore-path' <<<"$body"; chk $? "no path allowlist"
grep -q 'BASE_SHA..\$HEAD_SHA' <<<"$body"; chk $? "PR scan limited to base..head"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
