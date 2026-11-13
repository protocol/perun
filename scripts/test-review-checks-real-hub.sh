#!/usr/bin/env bash
# Real-tool smoke for the review_checks.sh hub: runs the REAL tfsec, ansible-lint, rubocop, cfn-lint, pmd, solhint, hadolint, bandit, ruff (ruff-security), actionlint, zizmor, gosec, staticcheck, kube-linter, flawfinder, detect-secrets, gitleaks, trufflehog, checkov, kube-score, kubescape (pinned local frameworks), semgrep (repo rules) and njsscan, tflint, kics, cppcheck, devskim, govulncheck, grype and trivy (no stubs) on one tiny
# known-bad canary each, in a throwaway repo, and asserts each is reported as RAN (stderr "analyzers ran:", no "not run:" line)
# with its expected rule id in the JSON rows. The stub tests (scripts/test-review-checks-hub-*.sh) pin routing and failure
# handling; this pins the real flags, SARIF/JSON shapes and exit codes. Not covered: syft (an inventory the hub never counts as ran), bundler-audit and retire need a
# network-fetched advisory DB or rule set (they are NOT CHECKED without one), so a real run would need a download. codeql is dropped: its CLI bundle is a multi-hundred-MB download plus per-language database builds, too heavy for this per-push job.
# A tool absent from PATH is skipped (exit 0) unless REQUIRE_REAL_HUB=1 (the ci.yml real-hub job sets it), then it FAILs.
# Read-only on the repo; writes only under a temp dir. Fixtures are fictional canaries.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
fail=0; tools=
bin() { [ "$1" = ruff-security ] && echo ruff || echo "$1"; }  # the hub tool name ruff-security runs the ruff binary
for t in tfsec ansible-lint rubocop cfn-lint pmd solhint hadolint bandit ruff-security actionlint zizmor gosec staticcheck kube-linter flawfinder detect-secrets gitleaks trufflehog checkov kube-score kubescape semgrep njsscan tflint kics cppcheck devskim govulncheck grype trivy; do
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
mkdir -p tfl infra playbooks app docker .github/workflows contracts gocanary k8s
printf 'resource "aws_s3_bucket" "acme" {\n  bucket = "acme-canary"\n}\n' >infra/main.tf
printf -- '---\n- hosts: all\n  tasks:\n    - ansible.builtin.shell: echo hello\n' >playbooks/site.yml
printf 'eval(params)\n' >app/canary.rb  # Security/Eval skips a plain string literal argument (cop source: pattern $!str), so the argument must not be one
printf 'AWSTemplateFormatVersion: "2010-09-09"\nResources:\n  Acme:\n    Type: AWS::S3::Bucket\n    Properties:\n      NoSuchProperty: 1\n' >infra/stack.yaml
printf 'public class Canary {\n  void f() throws Exception {\n    javax.crypto.spec.SecretKeySpec k = new javax.crypto.spec.SecretKeySpec("0123456789abcdef".getBytes(), "AES");\n  }\n}\n' >app/Canary.java
printf 'pragma solidity ^0.8.0;\ncontract Canary { function f() public view returns (bool) { return tx.origin == msg.sender; } }\n' >contracts/Canary.sol
printf 'FROM ubuntu:latest\n' >docker/Dockerfile
printf 'import subprocess\n\nsubprocess.call("ls", shell=True)\n' >app/canary.py
printf 'on: push\njobs:\n  acme:\n    steps:\n      - run: echo hello\n' >.github/workflows/canary.yml  # no runs-on: actionlint syntax-check
printf 'on: push\njobs:\n  acme:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n' >.github/workflows/zcanary.yml  # unpinned-uses (zizmor, offline)
printf 'module example.com/canary\n\ngo 1.21\n' >go.mod  # stdlib only: gosec and staticcheck run with GOPROXY=off
printf 'package canary\n\nimport "crypto/md5"\n\nfunc F(a int) bool {\n\t_ = md5.New()\n\treturn a == a\n}\n' >gocanary/canary.go  # gosec G401/G501 (md5), staticcheck SA4000 (identical operands)
printf 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: acme\nspec:\n  containers:\n    - name: app\n      image: example.com/acme/app:latest\n' >k8s/pod.yaml  # kube-linter latest-tag
printf 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: acme-ks\nspec:\n  containers:\n    - name: app\n      image: example.com/acme/app:1.0\n      securityContext:\n        privileged: true\n' >k8s/ks.yaml  # kubescape C-0057 (privileged container)
printf '#include <string.h>\nvoid f(char *s) {\n  char b[8];\n  strcpy(b, s);\n}\n' >app/canary.c
pw=Zq7xV2mK9pLw; printf 'url = %s://admin:%s@example.com/x\n' https "$pw" >app/notes.txt  # Basic Auth Credentials (detect-secrets); a URL secret, not a provider-key shape the privacy grep bans
tk=$(printf 'gh%s_%s' p a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8); printf 'token = %s\n' "$tk" >app/token.cfg  # GitHub-token shape (gitleaks, trufflehog), joined at runtime so no source line matches the privacy grep
printf 'rules:\n  - id: acme-canary\n    languages: [generic]\n    severity: ERROR\n    message: fictional canary marker\n    pattern: ACME_SEMGREP_CANARY\n' >.semgrep.yml  # repo rules: the hub uses them instead of the registry pack, so no network
printf 'ACME_SEMGREP_CANARY\n' >app/sg.txt
printf "var express = require('express');\nvar app = express();\napp.get('/', function (req, res) {\n  eval(req.query.code);\n  res.send('ok');\n});\n" >app/canary.js  # njsscan eval_nodejs (ERROR)
printf 'variable "acme_unused" {\n  type = string\n}\n' >tfl/main.tf  # tflint terraform_unused_declarations (bundled ruleset, recommended preset, no --init)
printf 'void f(void) {\n  char a[4];\n  a[10] = 0;\n}\n' >app/cpp_canary.c  # cppcheck arrayIndexOutOfBounds (default checks)
printf 'import hashlib\n\nh = hashlib.md5(b"acme")\n' >app/ds_canary.py  # devskim DS126858 weak hash
# govulncheck (CI online runs: the Go modules and vuln.go.dev are fetched) needs a called symbol of a vulnerable module: yaml.v2 2.2.2 (GO-2020-0036, GO-2021-0061, GO-2022-0956). Added only when govulncheck is under test, so the other Go canaries stay stdlib-only offline
case " $tools " in *" govulncheck "*)
  mkdir vulncanary && printf 'package vulncanary\n\nimport "gopkg.in/yaml.v2"\n\nfunc F(b []byte) error {\n\tvar v interface{}\n\treturn yaml.Unmarshal(b, &v)\n}\n' >vulncanary/canary.go
  printf 'module example.com/canary\n\ngo 1.21\n\nrequire gopkg.in/yaml.v2 v2.2.2\n' >go.mod
  # go.sum from the module proxy and checksum DB, module cache filled; the hub run itself is GOPROXY=off
  for i in 1 2 3; do GOFLAGS=-mod=mod go mod tidy >"$T/tidy" 2>&1 && break; [ "$i" -lt 3 ] || { cat "$T/tidy"; echo "FAIL - go mod tidy for the govulncheck canary"; exit 1; }; sleep $((i * 10)); done ;;
esac
# grype scans an SBOM (the hub never points it at a lockfile): a CycloneDX file with one known-vulnerable package (lodash 4.17.15, GHSA-35jh-r3h4-6jhm); its vulnerability DB is fetched online by the CI step before this runs
mkdir sbom && printf '{"bomFormat":"CycloneDX","specVersion":"1.5","version":1,"components":[{"type":"library","name":"lodash","version":"4.17.15","purl":"pkg:npm/lodash@4.17.15"}]}\n' >sbom/bom.json
# trivy: misconfig DS-0001/DS-0002 on docker/Dockerfile (above) plus a vuln on a lockfile (lodash 4.17.15). The vuln DB comes from REVIEW_TRIVY_CACHE (the CI step pulls it by digest); TRIVY_SKIP_CHECK_UPDATE keeps the misconfig checks to the bundle embedded in the sha-pinned binary
case " $tools " in *" trivy "*) printf '{"name":"acme-canary","lockfileVersion":3,"requires":true,"packages":{"":{"name":"acme-canary","version":"1.0.0","dependencies":{"lodash":"4.17.15"}},"node_modules/lodash":{"version":"4.17.15"}}}\n' >package-lock.json; export TRIVY_SKIP_CHECK_UPDATE=true ;; esac
G add . && G commit -q -m canaries
# govulncheck (vuln.go.dev) and grype are online: a transient fetch error reads as not run, so retry the hub run up to 3 times while either is not run
for i in 1 2 3; do rc=0; bash "$RC" --base base >"$T/out" 2>"$T/err" || rc=$?; grep -qE 'not run:.*\b(govulncheck|grype|trivy)\b' "$T/err" && [ "$i" -lt 3 ] || break; sleep $((i * 10)); done
echo "review_checks exit $rc; stderr tail:"; tail -n 15 "$T/err"
# tool -> rule id regex (rubocop and ansible-lint ids are exact; tfsec and cfn-lint match the rule family, unpinned ids)
want() { case $1 in tfsec) echo '^aws-s3-' ;; ansible-lint) echo '^no-changed-when' ;; rubocop) echo '^Security/Eval$' ;; cfn-lint) echo '^E3' ;;
  pmd) echo '^(HardCodedCryptoKey|InsecureCryptoIv)$' ;; solhint) echo '^avoid-tx-origin$' ;; hadolint) echo '^DL3007$' ;; bandit) echo '^B602$' ;; ruff-security) echo '^S602$' ;; actionlint) echo '^syntax-check$' ;; zizmor) echo '^unpinned-uses$' ;; gosec) echo '^G(401|501)$' ;; staticcheck) echo '^SA4000$' ;;
  kube-linter) echo '^latest-tag$' ;; flawfinder) echo '^FF1013$' ;; detect-secrets) echo '^Basic Auth Credentials$' ;;
  gitleaks) echo '^github-pat$' ;; trufflehog) echo '^Github$' ;; checkov) echo '^CKV_DOCKER_(3|7)$' ;; kube-score) echo '^container-image-tag$' ;; kubescape) echo '^C-0057$' ;; semgrep) echo '^acme-canary$' ;; njsscan) echo '^eval_nodejs$' ;;
  tflint) echo '^terraform_unused_declarations$' ;; kics) echo "^Image Version Using 'latest'\$" ;; cppcheck) echo '^arrayIndexOutOfBounds$' ;; devskim) echo '^DS126858$' ;;
  govulncheck) echo '^GO-(2020-0036|2021-0061|2022-0956)$' ;; grype) echo '^(GHSA-(35jh-r3h4-6jhm|p6mc-m468-83gw)|CVE-2021-23337|CVE-2020-8203)$' ;; trivy) echo '^DS-000[12]$' ;; esac; }
# tool -> its canary path (a row must be on this file, not just carry the rule id)
cany() { case $1 in tfsec) echo infra/main.tf ;; ansible-lint) echo playbooks/site.yml ;; rubocop) echo app/canary.rb ;; cfn-lint) echo infra/stack.yaml ;;
  pmd) echo app/Canary.java ;; solhint) echo contracts/Canary.sol ;; hadolint) echo docker/Dockerfile ;; bandit|ruff-security) echo app/canary.py ;; actionlint) echo .github/workflows/canary.yml ;; zizmor) echo .github/workflows/zcanary.yml ;; gosec|staticcheck) echo gocanary/canary.go ;;
  kube-linter) echo k8s/pod.yaml ;; flawfinder) echo app/canary.c ;; detect-secrets) echo app/notes.txt ;; gitleaks|trufflehog) echo app/token.cfg ;;
  checkov) echo docker/Dockerfile ;; kube-score) echo k8s/pod.yaml ;; kubescape) echo k8s/ks.yaml ;; semgrep) echo app/sg.txt ;; njsscan) echo app/canary.js ;;
  tflint) echo tfl/main.tf ;; kics) echo docker/Dockerfile ;; cppcheck) echo app/cpp_canary.c ;; devskim) echo app/ds_canary.py ;; govulncheck) echo go.mod ;; grype) echo sbom/bom.json ;; trivy) echo docker/Dockerfile ;; esac; }
# the hub's own capture is private to its run: on a failure, rerun the tool's hub argv here and show its raw output head
raw() { case $1 in tfsec) (cd infra && tfsec . --format sarif --no-colour --soft-fail --no-module-downloads) ;; ansible-lint) ansible-lint --offline --nocolor -q -f sarif ./playbooks/site.yml ;;
  rubocop) rubocop --force-default-config --fail-level fatal --format json --cache false -- ./app/canary.rb ;; cfn-lint) cfn-lint --format json -- ./infra/stack.yaml ;;
  pmd) pmd check --no-cache --no-progress -R category/java/security.xml -f sarif -d ./app/Canary.java ;; solhint) printf '{"extends":"solhint:recommended"}\n' >"$T/solhint.json"; solhint --config "$T/solhint.json" -f sarif --noPoster --disc ./contracts/Canary.sol ;;
  hadolint) hadolint -f json --no-fail ./docker/Dockerfile ;; bandit) bandit -q -f json --exit-zero ./app/canary.py ;; ruff-security) ruff check --select S --output-format json --no-cache --exit-zero ./app/canary.py ;;
  actionlint) actionlint -format '{{json .}}' ./.github/workflows/canary.yml ;;
  zizmor) zizmor --format=json --offline ./.github/workflows/zcanary.yml ;; gosec) GOPROXY=off gosec -fmt=json -no-fail ./... ;; staticcheck) GOPROXY=off GOTOOLCHAIN=local GOFLAGS=-mod=readonly GOWORK=off staticcheck -f json ./... ;;
  kube-linter) kube-linter lint --format json ./k8s/pod.yaml ;; flawfinder) flawfinder --sarif --quiet ./app/canary.c ;; detect-secrets) detect-secrets scan --no-verify ./app/notes.txt ;;
  gitleaks) gitleaks detect --no-git --no-banner --exit-code 0 -f json -r /dev/stdout -s ./app/token.cfg ;; trufflehog) trufflehog filesystem --no-verification --no-update --sarif ./app/token.cfg ;;
  checkov) CKV_SKIP_PACKAGE_UPDATE_CHECK=true checkov -f ./docker/Dockerfile -o json --quiet --skip-download --soft-fail ;; kube-score) kube-score score -o json ./k8s/pod.yaml ;; kubescape) kubescape scan framework nsa,cis-v1.23-t1.0.1 ./k8s/ks.yaml --format json --output "$T/ks-raw.json" --keep-local --logger error --use-artifacts-from "${KUBESCAPE_ARTIFACTS:-$HOME/.kubescape}" >/dev/null && cat "$T/ks-raw.json" ;;
  semgrep) HOME="$T" semgrep --config .semgrep.yml --metrics=off --disable-version-check --json --quiet ./app/sg.txt ;; njsscan) njsscan --json ./app/canary.js ;;
  tflint) tflint --format=json --no-color --call-module-type=none --chdir=./tfl --filter=main.tf ;; kics) kics scan -p ./docker/Dockerfile --no-progress --disable-secrets --report-formats json -o "$T/kics-raw"; cat "$T/kics-raw/results.json" ;;
  cppcheck) cppcheck --xml-version=2 --quiet ./app/cpp_canary.c ;; devskim) devskim analyze --source-code ./app/ds_canary.py --file-format sarif ;;
  govulncheck) GOPROXY=off GOTOOLCHAIN=local govulncheck -format json ./... ;; grype) GRYPE_DB_AUTO_UPDATE=false GRYPE_CHECK_FOR_APP_UPDATE=false grype sbom:./sbom/bom.json -o json ;;
  trivy) trivy ${REVIEW_TRIVY_CACHE:+--cache-dir "$REVIEW_TRIVY_CACHE"} fs --quiet --format json --skip-version-check --skip-db-update --offline-scan --scanners vuln,misconfig . ;; esac; }
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
# trivy: the full scan ran (not the secret-only fallback) and its vuln scan reported the lockfile canary
case " $tools " in *" trivy "*)
  grep -q 'secret-only' "$T/err" && { echo "FAIL - trivy fell back to secret-only"; fail=1; }
  for id in DS-0001 DS-0002; do jq -e --arg id "$id" 'any(.[]; .tool=="trivy" and .rule==$id and (.file|tostring|endswith("docker/Dockerfile")))' "$T/out" >/dev/null || { echo "FAIL - trivy: no $id row on docker/Dockerfile"; fail=1; }; done
  jq -e 'any(.[]; .tool=="trivy" and (.rule|test("^(CVE-2020-8203|CVE-2021-23337|CVE-2020-28500|GHSA-(35jh-r3h4-6jhm|29mw-wpgm-hmr9|p6mc-m468-83gw))$")) and (.file|tostring|endswith("package-lock.json")))' "$T/out" >/dev/null || { echo "FAIL - trivy: no lodash vuln row on package-lock.json"; fail=1; } ;; esac
# the govulncheck canary package must not feed the other Go canaries (its go.mod has to stay at the repo root: the hub runs govulncheck only there)
jq -e 'any(.[]; (.tool=="gosec" or .tool=="staticcheck") and (.file|tostring|test("vulncanary")))' "$T/out" >/dev/null && { echo "FAIL - gosec/staticcheck reported a row on vulncanary"; fail=1; }
[ "$fail" = 0 ] && echo "PASS: test-review-checks-real-hub"
exit "$fail"
