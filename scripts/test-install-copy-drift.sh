#!/usr/bin/env bash
# install.sh writes the same skill into several host dirs; the first host's copy is canonical and any other
# host copy that differs must fail the install naming that copy. A clean install passes.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-copydrift.XXXXXX")"
trap 'find "$WORK" -depth -delete' EXIT
export HOME="$WORK/home" CLAUDE_CONFIG_DIR="$WORK/home/.claude" XDG_CACHE_HOME="$WORK/cache" TMPDIR="$WORK" DCR_NO_PROBE=1
export DCR_COPY_HOSTS=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
mkdir -p "$HOME" "$WORK/shim"
REAL_CP="$(command -v cp)"
# cp shim: after a real copy into a .cursor skill dir, corrupt one script there (a stale/forked vendored copy).
cat >"$WORK/shim/cp" <<EOF
#!/usr/bin/env bash
"$REAL_CP" "\$@" || exit \$?
for a in "\$@"; do :; done
case "\$a" in */.cursor/skills/deep-code-review) echo "# drift" >>"\$a/scripts/review_checks.sh" ;; esac
EOF
chmod +x "$WORK/shim/cp"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

A="$WORK/a"; mkdir "$A"; git -C "$A" init -q
bash "$ROOT/install.sh" "$A" >/dev/null 2>&1; ok $? "clean install exits 0"
B="$WORK/b"; mkdir "$B"; git -C "$B" init -q
err="$(PATH="$WORK/shim:$PATH" bash "$ROOT/install.sh" "$B" 2>&1 >/dev/null)"; rc=$?
[ "$rc" -ne 0 ]; ok $? "drifted host copy fails the install"
grep -q "$B/.cursor/skills/deep-code-review differs" <<<"$err"; ok $? "error names the differing copy"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
