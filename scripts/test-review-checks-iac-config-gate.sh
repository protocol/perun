#!/usr/bin/env bash
# review_checks.sh: checkov and tflint never run a repo's own config-as-code unless REVIEW_TEST_CMD is set. checkov loads a
# .checkov.yaml or .checkov.yml from its working directory (the repo root), whose external-checks-dir runs repo Python; tflint loads
# .tflint.hcl or .tflint.json from its --chdir directory, whose plugin_dir and enabled plugins (or a ./.tflint.d/plugins dir) are binaries it runs.
# With such a file the tool is "NOT CHECKED" in a diff review and in a --full audit alike; without one, or with REVIEW_TEST_CMD, it runs as before.
# Stub binaries on a hermetic PATH (no real tool, no network). REVIEW_CHECKS=<path> runs another copy (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/iacgate.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN='' TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p sub; printf 'FROM scratch\n' >Dockerfile; printf 'resource "x" "y" {}\n' >main.tf; printf 'resource "x" "z" {}\n' >sub/b.tf
G add . && G commit -q -m files
cat >"$T/bin/checkov" <<'S'
#!/usr/bin/env bash
echo "checkov $*" >>"$HUB_LOG"
echo '{"check_type":"dockerfile","results":{"failed_checks":[]}}'
S
cat >"$T/bin/tflint" <<'S'
#!/usr/bin/env bash
echo "tflint $*" >>"$HUB_LOG"
echo '{"issues":[],"errors":[]}'
S
chmod +x "$T/bin/checkov" "$T/bin/tflint"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { : >"$HUB_LOG"; PATH="$T/bin:$T/base:$T/sys" bash "$RC" "$@" 2>"$T/err" >"$T/out"; }
ck() { grep -q '^checkov ' "$HUB_LOG"; }
tf() { grep -q "^tflint .*--chdir=$1 --filter=$2" "$HUB_LOG"; }
nck() { jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked")' "$T/out" >/dev/null; }

run --base base
ck && tf . main.tf && tf ./sub b.tf && ok "no repo config: checkov and tflint run" || bad "baseline: $(cat "$HUB_LOG")"

# checkov: a committed .checkov.yaml names Python checks; tflint: a committed sub/.tflint.hcl names plugin binaries
printf 'external-checks-dir:\n  - checks\n' >.checkov.yaml; printf 'plugin_dir = "./p"\n' >sub/.tflint.hcl; G add . && G commit -q -m cfg
run --base base
! ck && grep -q 'NOT CHECKED: checkov (a .checkov.yaml or .checkov.yml in the repo root' "$T/err" && nck checkov \
  && ok "diff: a repo .checkov.yaml is NOT CHECKED, checkov never started" || bad "checkov gate: $(cat "$HUB_LOG")"
tf . main.tf && ! tf ./sub b.tf && grep -q 'NOT CHECKED: tflint (sub/b.tf: a .tflint.hcl, .tflint.json or .tflint.d beside it' "$T/err" && nck tflint \
  && ok "diff: only the file beside a .tflint.hcl is NOT CHECKED" || bad "tflint gate: $(cat "$HUB_LOG")"
run --full
! ck && nck checkov && ! tf ./sub b.tf && nck tflint && tf . main.tf && ok "--full: the same gates hold" || bad "--full gate: $(cat "$HUB_LOG")"
REVIEW_TEST_CMD=true run --full
ck && tf ./sub b.tf && ok "--full with REVIEW_TEST_CMD set: both run the project config" || bad "--full opt-in: $(cat "$HUB_LOG")"
REVIEW_TEST_CMD=true run --base base
ck && tf ./sub b.tf && ok "REVIEW_TEST_CMD set: both run the project config" || bad "opt-in: $(cat "$HUB_LOG")"

# a .checkov.yml spelling and a plugins dir with no config file are gated too
G rm -q .checkov.yaml sub/.tflint.hcl; printf 'x: 1\n' >.checkov.yml; mkdir -p .tflint.d/plugins; printf 'x\n' >.tflint.d/plugins/tflint-ruleset-x
G add . && G commit -q -m cfg2
run --base base
! ck && ! tf . main.tf && tf ./sub b.tf && ok ".checkov.yml and a .tflint.d directory are gated" || bad "variants: $(cat "$HUB_LOG")"
exit "$fail"
