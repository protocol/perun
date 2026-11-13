#!/usr/bin/env bash
# Real-tool smoke for the review_checks.sh hub: runs the REAL tfsec, ansible-lint, rubocop, cfn-lint, pmd, solhint, hadolint, bandit, ruff (ruff-security) and actionlint (no stubs) on one tiny
# known-bad canary each, in a throwaway repo, and asserts each is reported as RAN (stderr "analyzers ran:", no "not run:" line)
# with its expected rule id in the JSON rows. The stub tests (scripts/test-review-checks-hub-*.sh) pin routing and failure
# handling; this pins the real flags, SARIF/JSON shapes and exit codes. Not covered: bundler-audit, kubescape and retire need a
# network-fetched advisory DB or rule set (they are NOT CHECKED without one), so a real run would need a download.
# A tool absent from PATH is skipped (exit 0) unless REQUIRE_REAL_HUB=1 (the ci.yml real-hub job sets it), then it FAILs.
# Read-only on the repo; writes only under a temp dir. Fixtures are fictional canaries.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
fail=0; tools=
bin() { [ "$1" = ruff-security ] && echo ruff || echo "$1"; }  # the hub tool name ruff-security runs the ruff binary
for t in tfsec ansible-lint rubocop cfn-lint pmd solhint hadolint bandit ruff-security actionlint; do
  if command -v "$(bin "$t")" >/dev/null 2>&1; then tools+=" $t"
  elif [ "${REQUIRE_REAL_HUB:-}" = 1 ]; then echo "FAIL - $t not installed (REQUIRE_REAL_HUB=1)"; fail=1
  else echo "skip - $t not installed"; fi
done
[ -n "$tools" ] || { [ "$fail" = 0 ] && echo "no real hub tool installed: SKIP test-review-checks-real-hub"; exit "$fail"; }
T=$(mktemp -d "${TMPDIR:-/tmp}/realhub.XXXXXX") && [ -d "$T" ] || { echo "FAIL - mktemp" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
mkdir "$T/repo" && cd "$T/repo" || exit 1
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G init -q . && printf 'x\n' >README.md && G add . && G commit -q -m base && G branch base
mkdir -p infra playbooks app docker .github/workflows contracts
printf 'resource "aws_s3_bucket" "acme" {\n  bucket = "acme-canary"\n}\n' >infra/main.tf
printf -- '---\n- hosts: all\n  tasks:\n    - ansible.builtin.shell: echo hello\n' >playbooks/site.yml
printf 'eval(params)\n' >app/canary.rb  # Security/Eval skips a plain string literal argument (cop source: pattern $!str), so the argument must not be one
printf 'AWSTemplateFormatVersion: "2010-09-09"\nResources:\n  Acme:\n    Type: AWS::S3::Bucket\n    Properties:\n      NoSuchProperty: 1\n' >infra/stack.yaml
printf 'public class Canary {\n  void f() throws Exception {\n    javax.crypto.spec.SecretKeySpec k = new javax.crypto.spec.SecretKeySpec("0123456789abcdef".getBytes(), "AES");\n  }\n}\n' >app/Canary.java
printf 'pragma solidity ^0.8.0;\ncontract Canary { function f() public view returns (bool) { return tx.origin == msg.sender; } }\n' >contracts/Canary.sol
printf 'FROM ubuntu:latest\n' >docker/Dockerfile
printf 'import subprocess\n\nsubprocess.call("ls", shell=True)\n' >app/canary.py
printf 'on: push\njobs:\n  acme:\n    steps:\n      - run: echo hello\n' >.github/workflows/canary.yml  # no runs-on: actionlint syntax-check
G add . && G commit -q -m canaries
rc=0; bash "$RC" --base base >"$T/out" 2>"$T/err" || rc=$?
echo "review_checks exit $rc; stderr tail:"; tail -n 15 "$T/err"
# tool -> rule id regex (rubocop and ansible-lint ids are exact; tfsec and cfn-lint match the rule family, unpinned ids)
want() { case $1 in tfsec) echo '^aws-s3-' ;; ansible-lint) echo '^no-changed-when' ;; rubocop) echo '^Security/Eval$' ;; cfn-lint) echo '^E3' ;;
  pmd) echo '^(HardCodedCryptoKey|InsecureCryptoIv)$' ;; solhint) echo '^avoid-tx-origin$' ;; hadolint) echo '^DL3007$' ;; bandit) echo '^B602$' ;; ruff-security) echo '^S602$' ;; actionlint) echo '^syntax-check$' ;; esac; }
# tool -> its canary path (a row must be on this file, not just carry the rule id)
cany() { case $1 in tfsec) echo infra/main.tf ;; ansible-lint) echo playbooks/site.yml ;; rubocop) echo app/canary.rb ;; cfn-lint) echo infra/stack.yaml ;;
  pmd) echo app/Canary.java ;; solhint) echo contracts/Canary.sol ;; hadolint) echo docker/Dockerfile ;; bandit|ruff-security) echo app/canary.py ;; actionlint) echo .github/workflows/canary.yml ;; esac; }
# the hub's own capture is private to its run: on a failure, rerun the tool's hub argv here and show its raw output head
raw() { case $1 in tfsec) (cd infra && tfsec . --format sarif --no-colour --soft-fail --no-module-downloads) ;; ansible-lint) ansible-lint --offline --nocolor -q -f sarif ./playbooks/site.yml ;;
  rubocop) rubocop --force-default-config --fail-level fatal --format json --cache false -- ./app/canary.rb ;; cfn-lint) cfn-lint --format json -- ./infra/stack.yaml ;;
  pmd) pmd check --no-cache --no-progress -R category/java/security.xml -f sarif -d ./app/Canary.java ;; solhint) printf '{"extends":"solhint:recommended"}\n' >"$T/solhint.json"; solhint --config "$T/solhint.json" -f sarif --noPoster --disc ./contracts/Canary.sol ;;
  hadolint) hadolint -f json --no-fail ./docker/Dockerfile ;; bandit) bandit -q -f json --exit-zero ./app/canary.py ;; ruff-security) ruff check --select S --output-format json --no-cache --exit-zero ./app/canary.py ;;
  actionlint) actionlint -format '{{json .}}' ./.github/workflows/canary.yml ;; esac; }
for t in $tools; do
  re=$(want "$t"); cf=$(cany "$t")
  if grep -qE "analyzers ran:.*\b$t\b" "$T/err" && ! grep -q "not run: $t" "$T/err" && ! grep -q "NOT CHECKED: $t" "$T/err" \
     && jq -e --arg t "$t" --arg re "$re" --arg cf "$cf" 'any(.[]; .tool==$t and (.rule|test($re)) and (.file|tostring|endswith($cf)))' "$T/out" >/dev/null; then
    echo "ok - $t: RAN, rule matching $re reported"
  else
    echo "FAIL - $t: not RAN or no rule matching $re; its rows: $(jq -c --arg t "$t" '[.[]|select(.tool==$t)|{file,rule}]' "$T/out" 2>&1 | head -c 400)"; fail=1
    echo "--- raw $t output (first 40 lines, exit via rerun) ---"; { raw "$t" 2>&1 || echo "[exit $?]"; } >"$T/raw" || true; head -n 40 "$T/raw"; echo "--- end raw $t ---"
  fi
done
[ "$fail" = 0 ] && echo "PASS: test-review-checks-real-hub"
exit "$fail"
