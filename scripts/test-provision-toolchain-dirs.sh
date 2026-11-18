#!/usr/bin/env bash
# provision_tools.sh and review_checks.sh must both see tools that dotnet/composer/mix install outside ~/.local/bin.
set -euo pipefail
unset DCR_USER_BIN # scrub_env.sh exports it empty (disables the dirs); the default-dir cases need it unset
P=.claude/skills/deep-code-review/scripts/provision_tools.sh
R=.claude/skills/deep-code-review/scripts/review_checks.sh
t=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-tcd.XXXXXX"); trap 'rm -rf "$t"' EXIT
mkdir -p "$t/home/.local/bin" "$t/home/.dotnet/tools" "$t/home/.config/composer/vendor/bin" "$t/home/.mix/escripts"
for x in .dotnet/tools/devskim .config/composer/vendor/bin/psalm .mix/escripts/sobelow; do printf '#!/bin/sh\n' >"$t/home/$x"; chmod +x "$t/home/$x"; done
fail=0
out=$(HOME=$t/home PATH=/usr/bin:/bin bash "$P")
for n in devskim psalm sobelow; do
  if echo "$out" | grep -q "^ok  *$n "; then echo "ok - provision sees $n"; else echo "FAIL - provision misses $n"; fail=1; fi
done
out=$(HOME=$t/home DCR_USER_BIN= PATH=/usr/bin:/bin bash "$P")
if echo "$out" | grep -qE "^ok  *(devskim|psalm|sobelow)"; then echo "FAIL - empty DCR_USER_BIN must disable extra dirs"; fail=1; else echo "ok - empty DCR_USER_BIN disables extra dirs"; fi
# run review_checks.sh's own PATH prelude (lb= .. first done) and read the resulting PATH
sed -n '/^lb=/,/^done$/p' "$R" >"$t/prelude.sh"
p=$(HOME=$t/home PATH=/usr/bin:/bin bash -c 'set -u; . "$1"; echo "$PATH"' _ "$t/prelude.sh")
case $p in *"$t/home/.dotnet/tools"*"$t/home/.config/composer/vendor/bin"*"$t/home/.mix/escripts"*) echo "ok - review_checks adds toolchain dirs to PATH" ;; *) echo "FAIL - PATH=$p"; fail=1 ;; esac
# --print: gems install into DCR_USER_BIN, and the opengrep blocker is listed (stderr)
line=$(HOME=$t/home DCR_USER_BIN=$t/home/.local/bin PATH=/usr/bin:/bin bash "$P" --print 2>"$t/err")
case $line in *"gem install brakeman -v 8.1.0 -n $t/home/.local/bin"*) echo "ok - gem installs into DCR_USER_BIN" ;; *) echo "FAIL - gem line: $line"; fail=1 ;; esac
if grep -q '^BLOCKED  opengrep (' "$t/err"; then echo "ok - opengrep blocker is printed"; else echo "FAIL - no opengrep BLOCKED line"; fail=1; fi
# npm rows are gated on node (npm ships with it), not on an npm binary
mkdir "$t/nodebin"; printf '#!/bin/sh\n' >"$t/nodebin/node"; chmod +x "$t/nodebin/node"
out=$(HOME=$t/home PATH=$t/nodebin:/usr/bin:/bin bash "$P" 2>&1)
if grep -q '^MISSING  retire ' <<<"$out"; then echo "ok - npm rows follow node"; else echo "FAIL - retire still BLOCKED with node present"; fail=1; fi
exit $fail
