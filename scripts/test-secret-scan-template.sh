#!/usr/bin/env bash
# Static checks on templates/secret-scan.yml, then seeded mutations: each must make a check fail.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
F="$ROOT/.claude/skills/deep-code-review/templates/secret-scan.yml"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-ssc.XXXXXX"); trap 'rm -rf "$T"' EXIT
DIGEST=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
# failing check names for file $1 (empty = all pass)
fails() {
  local b; b=$(grep -v '^ *#' "$1")
  ck() { local d=$1; shift; "$@" <<<"$b" >/dev/null 2>&1 || echo "$d"; }
  ck "digest pinned" grep -qE "^ *echo \"$DIGEST  gitleaks\.tgz\" \| sha256sum -c -\$"
  ck "version in URL" grep -q 'releases/download/v8\.30\.1/gitleaks_8\.30\.1_linux_x64\.tar\.gz'
  ck "checkout SHA" grep -qE 'uses: actions/checkout@[0-9a-f]{40}( |$)'
  ck "persist-credentials" grep -q 'persist-credentials: false'
  ck "permissions only contents read" bash -c "[ \"\$(sed -n '/^permissions:/,/^[a-z]/p' | grep '^  ')\" = '  contents: read' ]"
  ck "no expression in run" bash -c "! awk '/^ *(- )?run: /{r=1;i=match(\$0,/[^ ]/);if(\$0~/\\\$\\{\\{/)f=1;next} r&&/^ *[^ ]/{if(match(\$0,/[^ ]/)<=i)r=0; else if(\$0~/\\\$\\{\\{/)f=1} END{exit !f}'"
  ck "pull_request trigger" grep -qE '^  pull_request:'
  ck "push trigger" grep -qE '^  push:'
  ck "schedule trigger" grep -qE '^  schedule:'
  ck "no gitleaks-action" bash -c '! grep -qi gitleaks-action'
  ck "no path allowlist" bash -c "! grep -qiE 'allowlist|--config|\\[\\[allowlists|paths *=|--gitleaks-ignore-path'"
  ck "--redact" grep -q -- '--redact'
  ck "--exit-code 1" grep -q -- '--exit-code 1'
  ck "sha256sum before tar" bash -c "awk '/sha256sum -c/{s=NR} /tar -x/{t=NR} END{exit !(s&&t&&s<t)}'"
  ck "BASE_SHA guard" grep -qF 'if [ -n "$BASE_SHA" ]'
  ck "else full history" grep -qE '^ +else$'
  ck "PR scan base..head" grep -qF 'BASE_SHA..$HEAD_SHA'
  ck "reset before PR scan" bash -c 'awk '"'"'/git show/{r=NR} /BASE_SHA\.\.\$HEAD_SHA/{p=NR} END{exit !(r&&p&&r<p)}'"'"
  ck "base config reset" grep -qF 'git show "$BASE_SHA:$f"'
}
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
out=$(fails "$F"); [ -z "$out" ]; chk $? "shipped template passes every check${out:+ (failed: $out)}"
mut() { # name, sed args: the mutant must fail some check
  sed "${@:2}" "$F" >"$T/m.yml"; cmp -s "$F" "$T/m.yml" && { chk 1 "mutation $1 changed nothing"; return; }
  [ -n "$(fails "$T/m.yml")" ]; chk $? "mutation caught: $1"
}
mut digest 's/551f6fc8/551f6fc9/'
mut version 's/v8\.30\.1\/gitleaks_8\.30\.1/v8.30.0\/gitleaks_8.30.0/'
mut checkout-tag 's/checkout@[0-9a-f]\{40\}/checkout@v4/'
mut persist 's/persist-credentials: false/persist-credentials: true/'
mut permissions 's/  contents: read/  contents: write/'
mut run-expr 's/tar -xzf gitleaks.tgz gitleaks/echo ${{ github.actor }}/'
mut no-pr 's/^  pull_request:/  pull_request_x:/'
mut no-push 's/^  push:/  pushx:/'
mut no-schedule 's/^  schedule:/  schedulex:/'
mut action 's#./gitleaks git --redact --exit-code 1 -v$#uses: gitleaks/gitleaks-action@v2#'
mut allowlist 's/--redact/--config=allowlist.toml --redact/'
mut redact 's/--redact //g'
mut exit-code 's/--exit-code 1/--exit-code 0/g'
mut order -e '/sha256sum -c/{h;d;}' -e '/tar -xzf/G'
mut guard 's/-n "\$BASE_SHA"/-z "$BASE_SHA"/'
mut else 's/^\( *\)else$/\1elif false; then/'
mut range 's/BASE_SHA\.\.\$HEAD_SHA/HEAD_SHA/'
mut reset 's/git show "\$BASE_SHA:\$f"/git show "HEAD:$f"/'
mut digest-or 's/ | sha256sum -c -$/ | sha256sum -c - || true/'
mut run-dash 's/^      - name: Install gitleaks v8.30.1$/      - run: echo ${{ github.actor }}/'
mut reset-order -e '/git show/{h;d;}' -e '/--log-opts/G'
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
