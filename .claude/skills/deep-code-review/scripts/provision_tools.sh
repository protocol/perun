#!/usr/bin/env bash
# provision_tools.sh [--print] [DIR] — make review_checks.sh scanners actually run. The agent sandbox denies the network and installs, so
# the tools and their offline caches are provisioned ONCE by the owner, outside the sandbox.
# Default (dry run): list the scanner binaries not on PATH and the cold caches (trivy DB, osv-scanner offline DB, local semgrep p/default
# snapshot). Installs nothing, writes nothing, exit 0.
# --print: emit ONE copy-paste line (type it yourself outside the sandbox, with the `!` prefix) that installs what is missing (brew, brew --cask on macOS only, pipx, gem;
# pins are unverified, see tool-hub.md; brew formulae cannot be pinned) and warms the cold caches; it ends with this script's
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
# binary installer spec: BIN how SPEC. how = brew|cask|pipx|gem (SPEC is the package), cmd (SPEC is the whole install command: cargo, go, npm,
# dotnet, composer, mix, uv) or blocked (SPEC is the reason no install line is printed). Every review_checks.sh --list-tools name is covered here or listed with a reason in scripts/test-provision-covers-list-tools.sh.
tools='gitleaks brew gitleaks
trufflehog brew trufflehog
semgrep pipx semgrep==1.186.0
trivy brew trivy
osv-scanner brew osv-scanner
actionlint brew actionlint
zizmor pipx zizmor==1.32.0
bandit pipx bandit==1.9.4
scorecard brew scorecard
gosec brew gosec
grype brew grype
checkov pipx checkov==3.4.5
hadolint brew hadolint
ruff pipx ruff==0.17.5
syft brew syft
kube-linter brew kube-linter
kube-score brew kube-score
tflint brew terraform-linters/tap/tflint
staticcheck brew staticcheck
brakeman gem brakeman -v 8.1.0
kics brew kics
licensee brew licensee
cosign brew cosign
nuclei brew nuclei
ansible-lint pipx ansible-lint==26.11.0
cfn-lint pipx cfn-lint==1.60.1
detect-secrets pipx detect-secrets==1.5.0
flawfinder brew flawfinder
guarddog pipx guarddog==3.2.0
mobsfscan pipx mobsfscan==1.2.0
njsscan pipx njsscan==1.0.2
pyflakes pipx pyflakes==4.1.0
slither brew slither-analyzer
codeql cask codeql
cppcheck brew cppcheck
jq brew jq
kubescape brew kubescape
pmd brew pmd
shellcheck brew shellcheck
tfsec brew tfsec
node brew node
go brew go
bundler-audit gem bundler-audit -v 0.9.3
rubocop gem rubocop -v 1.92.3
cargo-audit brew cargo-audit
cargo-deny brew cargo-deny
govulncheck brew govulncheck
retire cmd npm install -g retire@6.1.1
solhint cmd npm install -g solhint@6.2.5
tsc cmd npm install -g typescript@7.0.2
devskim cmd dotnet tool install --global Microsoft.CST.DevSkim.CLI --version 1.0.103
psalm cmd composer global require vimeo/psalm:7.10.0
sobelow cmd mix escript.install --force hex sobelow 0.19.0
opengrep blocked no Homebrew formula and the upstream installer is an unpinned script on main with no checksummed release pin verified: install it yourself from a release you verified
uv brew uv
skillspector cmd uv tool install git+https://github.com/NVIDIA/skillspector.git@e2674da339b0bddc6e565d059c0577c6d9cd25da'
lb=${DCR_USER_BIN-${HOME:-/nonexistent}/.local/bin} # pipx and `uv tool` install here; a sandboxed PATH may lack it
# dotnet/composer/mix installs land in their own dirs; probe them too (same dirs review_checks.sh adds to PATH; empty DCR_USER_BIN disables all)
dirs=(); [ -z "$lb" ] || for d in "$lb" "${HOME:-/nonexistent}/.dotnet/tools" "${HOME:-/nonexistent}/.composer/vendor/bin" "${HOME:-/nonexistent}/.config/composer/vendor/bin" "${HOME:-/nonexistent}/.mix/escripts"; do [ -d "$d" ] && dirs+=("$d"); done
have() { local d; for d in ${dirs[@]+"${dirs[@]}"}; do [ -x "$d/$1" ] && { echo "$d"; return 0; }; done; return 1; }
miss=0 cold=0 brew=() cask=() pipx=() gem=() oth=() othb=() fix=()
while read -r bin how spec; do
  if command -v "$bin" >/dev/null; then echo "ok       $bin"; continue; fi
  if d=$(have "$bin"); then echo "ok       $bin ($d/$bin, not on PATH; review_checks.sh adds $d)"; continue; fi
  # a cmd entry needs its own toolchain (first word of the command); without it the line would fail, so name the blocker instead
  if [ "$how" = blocked ]; then echo "BLOCKED  $bin ($spec)"; miss=$((miss + 1)); continue; fi
  if [ "$how" = cask ] && [ "$(uname)" != Darwin ]; then echo "BLOCKED  $bin (cask install is macOS-only: install it yourself)"; miss=$((miss + 1)); continue; fi
  tc=${spec%% *}; [ "$tc" != npm ] || tc=node # npm ships with Homebrew's node
  if [ "$how" = cmd ] && ! command -v "$tc" >/dev/null && ! have "$tc" >/dev/null && [[ " ${brew[*]-} " != *" $tc "* ]]; then echo "BLOCKED  $bin (needs $tc: install it first, then re-run)"; miss=$((miss + 1)); continue; fi
  if [ "$how" = cmd ]; then echo "MISSING  $bin (run: $spec)"; else echo "MISSING  $bin ($how install $spec)"; fi; miss=$((miss + 1))
  case $how in brew) brew+=("$spec") ;; cask) cask+=("$spec") ;; gem) gem+=("$spec") ;; cmd) oth+=("$spec"); othb+=("$bin") ;; *) pipx+=("$spec") ;; esac
done <<<"$tools"
[ ${#gem[@]} -eq 0 ] || brew=(ruby ${brew[@]+"${brew[@]}"})
[ ${#pipx[@]} -eq 0 ] || command -v pipx >/dev/null || brew=(pipx ${brew[@]+"${brew[@]}"})
[ ${#brew[@]} -eq 0 ] && [ ${#cask[@]} -eq 0 ] || command -v brew >/dev/null || echo "note: brew not found; install Homebrew (https://brew.sh) or use each tool's own installer${gem[0]+"; without it the gem rows fall back to the system ruby, which is too old and may fail"}"
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
# every package installs on its own, so one unknown name or failed install prints FAILED and does not stop the rest; groups join with ;
[ ${#brew[@]} -eq 0 ] || cmd+=("for f in ${brew[*]}; do brew install \"\$f\" || echo \"FAILED \$f\"; done")
[ ${#cask[@]} -eq 0 ] || cmd+=("if [ \"\$(uname)\" = Darwin ]; then for f in ${cask[*]}; do brew install --cask \"\$f\" || echo \"FAILED \$f\"; done; fi") # casks are macOS-only
[ ${#pipx[@]} -eq 0 ] || cmd+=("for f in ${pipx[*]}; do pipx install \"\$f\" || echo \"FAILED \$f\"; done")
# system ruby is too old for these gems: use Homebrew's when brew exists, installing into $DCR_USER_BIN (default ~/.local/bin, on review_checks.sh's PATH)
for p in ${gem[@]+"${gem[@]}"}; do cmd+=("\$(command -v brew >/dev/null && echo \$(brew --prefix ruby)/bin/)gem install $p${lb:+ -n $(q "$lb")} || echo FAILED ${p%% *}"); done
for i in ${!oth[@]}; do cmd+=("${oth[i]} || echo FAILED ${othb[i]}"); done
[ ${#fix[@]} -eq 0 ] || cmd+=("${fix[@]}")
[ ${#cmd[@]} -gt 0 ] || { echo "# nothing to provision" >&3; exit 0; }
cmd+=("bash $(q "$self")") # re-check at the end so the owner sees what is still missing
line=; for c in "${cmd[@]}"; do line+="${line:+; }$c"; done
printf '%s\n' "$line" >&3
