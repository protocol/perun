#!/usr/bin/env bash
# Every tool name `review_checks.sh --list-tools` prints is BUILT-IN (Perun code, listed below), has a provision_tools.sh entry for its binary,
# or is in NOINSTALL with a reason. A new name defaults to EXTERNAL, so it fails here until it is provisioned or justified.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
S=$ROOT/.claude/skills/deep-code-review/scripts
BUILTIN=" agent-injection attempt-limit bash-n committed-data cost-limit csrf-cookie dep-currency dep-risk header-config insecure-defaults invisible-chars literals mcp-config ownership pii-data pipefail-sigpipe privileged-route py_compile route-auth sibling-sweep tenant-scope "
# name:binary where the --list-tools name is not the binary the script runs
ALIAS=" gitleaks-history:gitleaks ruff-security:ruff node-check:node go-vet:go fuzz:go "
# name:reason, no global install path
NOINSTALL=" eslint-security:project-local npm devDependency (eslint plus eslint-plugin-security from the scanned repo's own node_modules), never installed globally snyk-agent-scan:route-only, needs SNYK_TOKEN and calls a remote API, never run by the hub (tool-hub.md) "
bins=$(PATH=/usr/bin:/bin DCR_USER_BIN= bash "$S/provision_tools.sh" 2>&1 | awk '$1=="ok"||$1=="MISSING"||$1=="BLOCKED"{print $2}')
fail=0; n=0
all=$(bash "$S/review_checks.sh" --list-tools)
# every ALIAS and NOINSTALL key must be a real --list-tools name, so a renamed tool cannot leave a dead exemption behind
for k in $(for a in $ALIAS; do echo "${a%%:*}"; done) eslint-security snyk-agent-scan; do
  grep -qxF "$k" <<<"$all" || { echo "FAIL - exemption key $k is not in --list-tools"; fail=1; }
done
for t in $all; do
  case "$BUILTIN" in *" $t "*) continue ;; esac
  case "$NOINSTALL" in *" $t:"*) continue ;; esac
  b=$t; for a in $ALIAS; do [ "${a%%:*}" = "$t" ] && b=${a#*:}; done
  n=$((n + 1))
  grep -qxF "$b" <<<"$bins" || { echo "FAIL - $t (binary $b) has no provision_tools.sh entry"; fail=1; }
done
[ "$n" -gt 40 ] || { echo "FAIL - only $n external names found; --list-tools parse broke"; fail=1; }
[ "$fail" = 0 ] && echo "ok - $n external --list-tools names covered by provision_tools.sh"
exit "$fail"
