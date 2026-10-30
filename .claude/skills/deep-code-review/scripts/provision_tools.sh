#!/usr/bin/env bash
# provision_tools.sh [--print] [DIR] — make review_checks.sh scanners actually run. The agent sandbox denies the network and installs, so
# the tools and their offline caches are provisioned ONCE by the owner, outside the sandbox.
# Default (dry run): list the scanner binaries not on PATH and the cold caches (trivy DB, osv-scanner offline DB, local semgrep p/default
# snapshot). Installs nothing, writes nothing, exit 0.
# --print: emit ONE copy-paste line (type it yourself outside the sandbox, with the `!` prefix) that installs what is missing (brew, pipx;
# pipx pins are the PyPI versions checked 2026-10-29, brew formulae cannot be pinned) and warms the cold caches; it ends with this script's
# dry run so the result is visible. Nothing missing or cold: a `# nothing to provision` comment. DIR (default: the current dir) is the
# project whose root lockfiles osv-scanner downloads offline databases for (one per ecosystem found there). A DIR given on the command line
# always re-downloads, so `--print OTHER_DIR` adds the ecosystems OTHER_DIR needs.
# --cache trivy|osv|semgrep: internal, used by review_checks.sh. Print where that cache lives and exit 0 when it holds data, else print nothing, exit 1.
# Caches are the tools' own (trivy and osv-scanner use the OS user cache dir; the semgrep snapshot is ours, under dcr-tools/). Overrides:
# REVIEW_TRIVY_CACHE (else TRIVY_CACHE_DIR), REVIEW_OSV_DB_DIR (else OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY), DCR_CACHE_ROOT (the user cache dir).
# A tool found only in ~/.local/bin (pipx, `uv tool`; DCR_USER_BIN overrides, empty disables) counts as installed: review_checks.sh adds that dir to PATH.
# ponytail: a cache counts as warm when its marker file exists (trivy.db, any osv ecosystem zip, a semgrep snapshot with a `rules:` key); no age or per-ecosystem check.
set -euo pipefail
usage() { echo "usage: provision_tools.sh [--print] [DIR] | --cache trivy|osv|semgrep" >&2; exit 2; }
# the OS user cache dir, as Go's os.UserCacheDir (trivy and osv-scanner are Go): Darwin ignores XDG_CACHE_HOME
case $(uname) in Darwin) ucd=${HOME:-/nonexistent}/Library/Caches ;; *) ucd=${XDG_CACHE_HOME:-${HOME:-/nonexistent}/.cache} ;; esac
ucd=${DCR_CACHE_ROOT:-$ucd}
tvd=${REVIEW_TRIVY_CACHE:-${TRIVY_CACHE_DIR:-$ucd/trivy}}
osvd=${REVIEW_OSV_DB_DIR:-${OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY:-$ucd}}
sgf=$ucd/dcr-tools/semgrep/p-default.yml
anyf() { [ -n "$(find "$@" 2>/dev/null | head -n1)" ]; } # any non-empty file matching the find expression
trivy_warm() { anyf "$tvd" -maxdepth 2 -name trivy.db -size +0; }
osv_warm() { anyf "$osvd/osv-scalibr" "$osvd/osv-scanner" -maxdepth 2 -name '*.zip' -size +0; } # v2.x caches under osv-scalibr/, older and the docs say osv-scanner/
sg_warm() { grep -q '^rules:' "$sgf" 2>/dev/null; } # a semgrep config always has a top-level `rules:`; an empty file or an error page is cold
pr=0 dir=. dirset=0 cm=
while [ $# -gt 0 ]; do case "$1" in
  --print) pr=1 ;;
  --cache) cm=${2:-}; [ $# -ge 2 ] || usage; shift ;;
  -*) usage ;;
  *) dir=$1 dirset=1 ;;
esac; shift; done
case "$cm" in
  "") ;;
  trivy) if trivy_warm; then echo "$tvd"; else exit 1; fi; exit 0 ;;
  osv) if osv_warm; then echo "$osvd"; else exit 1; fi; exit 0 ;;
  semgrep) if sg_warm; then echo "$sgf"; else exit 1; fi; exit 0 ;;
  *) usage ;;
esac
[ -d "$dir" ] || { echo "provision_tools: not a directory: $dir" >&2; exit 2; }
dir=$(cd "$dir" && pwd)
exec 3>&1; [ "$pr" = 0 ] || exec 1>&2 # --print: stdout carries only the one owner line, the listing goes to stderr
self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
# binary installer spec
tools='gitleaks brew gitleaks
trufflehog brew trufflehog
semgrep pipx semgrep==1.182.1
trivy brew trivy
osv-scanner brew osv-scanner
actionlint brew actionlint
zizmor pipx zizmor==1.31.1
bandit pipx bandit==1.9.4
scorecard brew scorecard
gosec brew gosec
grype brew grype
checkov pipx checkov==3.4.0
hadolint brew hadolint'
lb=${DCR_USER_BIN-${HOME:-/nonexistent}/.local/bin} # pipx and `uv tool` install here; a sandboxed PATH may lack it
miss=0 cold=0 brew=() pipx=() fix=()
while read -r bin how spec; do
  if command -v "$bin" >/dev/null; then echo "ok       $bin"; continue; fi
  if [ -n "$lb" ] && [ -x "$lb/$bin" ]; then echo "ok       $bin ($lb/$bin, not on PATH; review_checks.sh adds $lb)"; continue; fi
  echo "MISSING  $bin ($how install $spec)"; miss=$((miss + 1))
  if [ "$how" = brew ]; then brew+=("$spec"); else pipx+=("$spec"); fi
done <<<"$tools"
[ ${#pipx[@]} -eq 0 ] || command -v pipx >/dev/null || brew=(pipx ${brew[@]+"${brew[@]}"})
[ ${#brew[@]} -eq 0 ] || command -v brew >/dev/null || echo "note: brew not found; install Homebrew (https://brew.sh) or use each tool's own installer"
q() { printf '%q' "$1"; }
cache() { # NAME WARM-FN PATH COMMAND [FORCE]
  if [ -z "${5:-}" ] && "$2"; then echo "warm     $1 ($3)"; else echo "COLD     $1 ($3)"; cold=$((cold + 1)); fix+=("$4"); fi
}
# trivy's DB download reads ~/.docker/config.json and fails when its credsStore names a missing helper; an empty DOCKER_CONFIG dir avoids that
ed=$ucd/dcr-tools/docker-config-empty
cache "trivy DB" trivy_warm "$tvd" "mkdir -p $(q "$ed") && DOCKER_CONFIG=$(q "$ed") trivy --cache-dir $(q "$tvd") fs --download-db-only"
cache "osv-scanner offline DB" osv_warm "$osvd" "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$(q "$osvd") osv-scanner --offline-vulnerabilities --download-offline-databases $(q "$dir")" "$([ "$dirset" = 0 ] || echo force)"
cache "semgrep p/default snapshot" sg_warm "$sgf" "mkdir -p $(q "$(dirname "$sgf")") && curl -fsSL https://semgrep.dev/c/p/default -o $(q "$sgf.part") && mv $(q "$sgf.part") $(q "$sgf")"
echo "provision_tools: $miss missing, $cold cold; nothing was installed or downloaded (--print emits the one line to run yourself)"
[ "$pr" = 1 ] || exit 0
cmd=()
[ ${#brew[@]} -eq 0 ] || cmd+=("brew install ${brew[*]}")
for p in ${pipx[@]+"${pipx[@]}"}; do cmd+=("pipx install $p"); done
[ ${#fix[@]} -eq 0 ] || cmd+=("${fix[@]}")
[ ${#cmd[@]} -gt 0 ] || { echo "# nothing to provision" >&3; exit 0; }
cmd+=("bash $(q "$self")") # re-check at the end so the owner sees what is still missing
line=; for c in "${cmd[@]}"; do line+="${line:+; }$c"; done
printf '%s\n' "$line" >&3
