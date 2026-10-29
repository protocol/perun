#!/usr/bin/env bash
# review_checks.sh dependency-scan fallback: when osv-scanner/trivy give no result for a lockfile, the ecosystem's own audit
# (npm, pnpm, pip-audit) runs for that lockfile and is named on stderr; with no dependency scan at all the JSON carries a
# not-checked row, never a silent clean. Also: semgrep gets a writable HOME when the real one is not writable.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-depfb.XXXXXX"); trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/logs" "$T/repo"
export LOGDIR="$T/logs"
unset REVIEW_OSV_DB_DIR REVIEW_TRIVY_CACHE # hermetic: the host's offline-DB env must not change which branch runs
# stub NAME BODY: a fake tool that logs its argv to $LOGDIR/NAME, then runs BODY
stub() { printf '#!/usr/bin/env bash\necho "$*" >>"$LOGDIR/%s"\n%s\n' "$1" "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
NOOSV='echo "dial tcp: lookup api.osv.dev: no such host" >&2; exit 127'
NOTRIVY='echo "FATAL vulnerability DB not found" >&2; exit 1'
stub osv-scanner "$NOOSV"
stub trivy "$NOTRIVY"
stub npm 'echo "npm WARN noise" >&2; echo "PWD=$PWD reg=$npm_config_registry uc=$npm_config_userconfig npmrc=$([ -e .npmrc ] && echo 1 || echo 0)" >>"$LOGDIR/npm-env"; echo "{\"vulnerabilities\":{\"lodash\":{\"name\":\"lodash\",\"severity\":\"high\"}}}"; exit 1'
stub pnpm 'echo "{\"advisories\":{\"7\":{\"github_advisory_id\":\"GHSA-aaaa\",\"severity\":\"low\",\"module_name\":\"left-pad\",\"title\":\"t\"}}}"; exit 1'
stub pip-audit 'echo "{\"dependencies\":[{\"name\":\"flask\",\"version\":\"1.0\",\"vulns\":[{\"id\":\"PYSEC-1\"}]}]}"; exit 1'
stub semgrep 'echo "HOME=$HOME writable=$([ -w "$HOME" ] && echo 1 || echo 0)" >>"$LOGDIR/semgrep-home"; echo "{\"results\":[]}"'
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
mkdir web api
echo '{}' >web/package-lock.json; echo 'registry=https://evil.example.com/' >web/.npmrc; echo 'lockfileVersion: 6' >web/pnpm-lock.yaml; echo flask==1.0 >api/requirements.txt
g add . && g commit -q -m locks
: >"$T/notadir"; export PERUN_HEAVY_DIR="$T/notadir" # lease policy fails -> scanners run unleased, the real lease is untouched
run() { rm -f "$LOGDIR"/*; env "$@" PATH="$T/bin:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out" || true; }
has() { grep -q -- "$2" "$1"; }
nrows() { grep -c '"tool": "dep-scan"' "$T/out" || true; }

run REVIEW_OSV=1
r=0; has "$T/err" 'dependency scan: npm ran for web/package-lock.json' && has "$T/err" 'dependency scan: pnpm ran for web/pnpm-lock.yaml' && has "$T/err" 'dependency scan: pip-audit ran for api/requirements.txt' || r=1; chk $r "osv-scanner unreachable: each ecosystem audit runs and is named (npm stderr noise ignored)"
r=0; has "$LOGDIR/npm" 'audit --package-lock-only --json' || r=1; chk $r "npm audit runs with --package-lock-only --json"
r=0; has "$T/out" '"tool": "npm"' && has "$T/out" 'GHSA-aaaa' && has "$T/out" 'PYSEC-1' || r=1; chk $r "npm, pnpm and pip-audit findings land in the JSON"
r=0; grep -Eq 'analyzers ran:.* npm(,|;|$)' "$T/err" || r=1; chk $r "analyzers-ran line names the fallback tool"
r=0; has "$LOGDIR/pip-audit" '--no-deps --disable-pip' || r=1; chk $r "pip-audit runs with --no-deps --disable-pip (no resolver, no venv)"
r=0; has "$LOGDIR/npm-env" 'reg=https://registry.npmjs.org/ uc=/dev/null npmrc=0' && ! has "$LOGDIR/npm-env" 'PWD=.*/web ' || r=1; chk $r "npm audit: public registry, no user npmrc, repo .npmrc not in its cwd"
r=0; [ "$(nrows)" = 0 ] || r=1; chk $r "no not-checked row when every fallback ran"

run REVIEW_OSV=
r=0; [ "$(nrows)" = 3 ] && has "$T/out" 'not-checked' && [ ! -e "$LOGDIR/npm" ] || r=1; chk $r "REVIEW_OSV unset: no network audit, one not-checked dep-scan row per lockfile"

# fallback tool missing: not-checked row, never clean (skipped when the host has one on the minimal PATH)
if ! PATH="/usr/bin:/bin" sh -c 'command -v npm || command -v pnpm || command -v pip-audit' >/dev/null; then
  mkdir "$T/hold"; mv "$T/bin/npm" "$T/bin/pnpm" "$T/bin/pip-audit" "$T/hold/"
  REVIEW_OSV=1 PATH="$T/bin:/usr/bin:/bin" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
  r=0; [ "$(nrows)" = 3 ] && has "$T/out" 'is not installed' || r=1; chk $r "fallback tool not installed: not-checked row"
  mv "$T/hold"/* "$T/bin/"
else chk 0 "fallback tool missing (skipped: real npm/pnpm/pip-audit on the minimal PATH)"; fi

# unparseable audit output is not clean and not "ran"
stub npm 'echo "<html>502</html>"; exit 1'
run REVIEW_OSV=1
r=0; has "$T/out" 'npm failed or was unreachable' || r=1; chk $r "unparseable npm output: not-checked row"
r=0; ! grep -Eq 'analyzers ran:.* npm(,|;|$)' "$T/err" || r=1; chk $r "failed parse: npm is not listed as ran"

# osv-scanner succeeds for every lockfile: no fallback
stub osv-scanner 'echo "{\"results\":[]}"'
stub npm 'echo "{\"vulnerabilities\":{}}"'
run REVIEW_OSV=1
r=0; [ ! -e "$LOGDIR/npm" ] && [ "$(nrows)" = 0 ] || r=1; chk $r "osv-scanner result for every lockfile: fallback does not run"

# per-lockfile coverage: osv fails for one lockfile and succeeds for the others -> only that one falls back
stub osv-scanner 'case "$*" in *web/package-lock.json*) echo "dial tcp: no such host" >&2; exit 127 ;; *) echo "{\"results\":[]}" ;; esac'
run REVIEW_OSV=1
r=0; [ -e "$LOGDIR/npm" ] && [ ! -e "$LOGDIR/pnpm" ] && [ ! -e "$LOGDIR/pip-audit" ] && has "$T/err" 'dependency scan: npm ran for web/package-lock.json' || r=1; chk $r "2+ lockfiles, osv fails for one: only the uncovered one gets the fallback"
stub npm 'echo "<html>502</html>"'
run REVIEW_OSV=1
r=0; [ "$(nrows)" = 1 ] && grep -A5 '"file": "web/package-lock.json"' "$T/out" | grep -q dep-scan || r=1; chk $r "osv fails for one lockfile and the fallback fails: that one gets a not-checked row, the others none"

# trivy coverage is per lockfile: it reported a Target for web/package-lock.json only
stub osv-scanner "$NOOSV"
stub npm 'echo "{\"vulnerabilities\":{}}"'
stub trivy 'echo "{\"Results\":[{\"Target\":\"web/package-lock.json\",\"Class\":\"lang-pkgs\"}]}"'
run REVIEW_OSV=1
r=0; [ ! -e "$LOGDIR/npm" ] && [ -e "$LOGDIR/pnpm" ] && [ -e "$LOGDIR/pip-audit" ] || r=1; chk $r "trivy covered one lockfile: only the others fall back"
stub trivy "$NOTRIVY"

# no fallback for the ecosystem: not-checked row, never clean
echo x >yarn.lock; echo y >Cargo.lock; g add . && g commit -q -m more-locks
run REVIEW_OSV=1
r=0; grep -A5 '"file": "yarn.lock"' "$T/out" | grep -q 'no fallback' && grep -A5 '"file": "Cargo.lock"' "$T/out" | grep -q 'no fallback' || r=1; chk $r "yarn.lock and Cargo.lock with no scan: not-checked row each"

# semgrep HOME: a read-only real HOME -> semgrep still gets a writable one
mkdir "$T/ro"; chmod 555 "$T/ro"
echo 'x = 1' >app.py; g add . && g commit -q -m py
run HOME="$T/ro"
r=0; has "$LOGDIR/semgrep-home" 'writable=1' && ! has "$LOGDIR/semgrep-home" "HOME=$T/ro " || r=1; chk $r "semgrep runs with a writable HOME when \$HOME is read-only"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
