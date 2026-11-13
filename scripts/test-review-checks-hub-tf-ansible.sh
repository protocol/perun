#!/usr/bin/env bash
# review_checks.sh hub routing for tfsec (Terraform, one directory per changed file) and ansible-lint (Ansible YAML) with stub binaries on a
# hermetic PATH (no real tool, no network): rows keep findings, a missing tool is "NOT CHECKED", and a crash, empty output, wrong-shape output
# or (ansible-lint) a non-zero exit with no row is "not run", never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubtfa.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p infra/tf playbooks roles/web/tasks k8s
printf 'resource "x" "y" {}\n' >infra/tf/a.tf; printf 'resource "x" "z" {}\n' >main.tf
printf -- '- hosts: all\n  tasks:\n    - ping:\n' >playbooks/site.yml; printf -- '- name: t\n  ping:\n' >roles/web/tasks/main.yml
printf -- '- hosts: web\n  roles:\n    - web\n' >deploy.yml; printf 'a: 1\n' >k8s/plain.yml; printf 'name: ci\non: push\n' >ci.yml
G add . && G commit -q -m code
# stubs print the canned SARIF on stdout; tfsec logs the directory it runs in
cat >"$T/bin/tfsec" <<'S'
#!/usr/bin/env bash
echo "tfsec cwd=${PWD##*/} $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_tf"
S
cat >"$T/bin/ansible-lint" <<'S'
#!/usr/bin/env bash
echo "ansible-lint $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_al"
exit "${AL_RC:-2}"
S
chmod +x "$T/bin/tfsec" "$T/bin/ansible-lint"; mkdir "$T/keep"; cp "$T/bin/tfsec" "$T/bin/ansible-lint" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
sarif() { printf '{"version":"2.1.0","runs":[{"results":[%s]}]}' "$1"; }
res() { printf '{"ruleId":"%s","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
export J_tf="$(sarif "$(res aws-x-1 a.tf 3),$(res aws-x-2 other.tf 5)")"
export J_al="$(sarif "$(res yaml-x playbooks/site.yml 2),$(res no-changed-when roles/web/tasks/main.yml 1),$(res name-x deploy.yml 1)")"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row tfsec infra/tf/a.tf aws-x-1 && ! row tfsec infra/tf/other.tf aws-x-2 && ! row tfsec main.tf aws-x-1 && ran tfsec && ok "tfsec: row for the changed file only, other file in its directory dropped" || bad "tf rows: $(jq -c '[.[]|select(.tool=="tfsec")|[.file,.rule]]' "$T/out")"
grep -q 'tfsec cwd=tf . --format sarif --no-colour --soft-fail --no-module-downloads --exclude-downloaded-modules' "$HUB_LOG" && grep -q 'tfsec cwd=repo ' "$HUB_LOG" && ok "tfsec argv: run in the file's directory, no module download, soft-fail" || bad "tf argv: $(grep tfsec "$HUB_LOG")"
row ansible-lint playbooks/site.yml yaml-x && row ansible-lint roles/web/tasks/main.yml no-changed-when && row ansible-lint deploy.yml name-x && ran ansible-lint && ok "ansible-lint: exit 2 with rows, rows kept for playbook, role task file and hosts+roles file" || bad "al rows: $(jq -c '[.[]|select(.tool=="ansible-lint")|[.file,.rule]]' "$T/out")"
grep -q -- 'ansible-lint --offline --nocolor -q -f sarif ' "$HUB_LOG" && grep -q 'playbooks/site.yml' "$HUB_LOG" && ! grep -qE 'ci.yml|k8s/plain.yml' "$HUB_LOG" && ok "ansible-lint argv: offline, only Ansible-looking YAML" || bad "al argv: $(grep ansible-lint "$HUB_LOG")"
# fail-open regressions: never clean
AL_RC=2 J_tf= J_al= run
notrun tfsec && notrun ansible-lint && ok "empty output: not run" || bad "empty"
J_tf=$' \n' J_al=$' \n' run
notrun tfsec && notrun ansible-lint && ok "whitespace-only output: not run" || bad "whitespace"
J_tf='{"x":1}' J_al='{"x":1}' run
notrun tfsec && notrun ansible-lint && ok "wrong-shape JSON: not run" || bad "wrong shape"
J_tf='{"runs":[]}' J_al='{"runs":[]}' run
notrun tfsec && notrun ansible-lint && ok "SARIF with no runs: not run" || bad "no runs"
HUB_MODE=crash run
notrun tfsec && notrun ansible-lint && ok "crash: not run" || bad "crash"
J_tf="$(sarif "")" J_al="$(sarif "")" AL_RC=2 run
notrun ansible-lint && ok "ansible-lint: exit 2 with no row (fail-open guard): not run, not clean" || bad "al exit2 empty"
AL_RC=1 J_tf="$(sarif "")" J_al="$(sarif "")" run
notrun ansible-lint && ok "ansible-lint: exit 1 with no row: not run" || bad "al exit1 empty"
AL_RC=0 J_tf="$(sarif "")" J_al="$(sarif "")" run
ran ansible-lint && ran tfsec && ! grep -q 'not run: ansible-lint' "$T/err" && ok "exit 0 and an empty results list: clean, ran" || bad "clean"
AL_RC=7 J_al="$(sarif "$(res yaml-x playbooks/site.yml 2)")" run
notrun ansible-lint && ok "ansible-lint: undocumented exit 7: not run" || bad "al exit7"
AL_RC=2 J_al="$(sarif "$(res yaml-x playbooks/elsewhere.yml 2)")" run
notrun ansible-lint && ok "ansible-lint: a row for a file outside the changed list: not run" || bad "al outside"
# gates
cp "$T/keep/tfsec" "$T/keep/ansible-lint" "$T/bin/"; rm "$T/bin/tfsec" "$T/bin/ansible-lint"; run
grep -q 'NOT CHECKED: tfsec (install: brew install tfsec)' "$T/err" && grep -q 'NOT CHECKED: ansible-lint (install: pipx install ansible-lint)' "$T/err" && jq -e 'any(.[]; .tool=="tfsec" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tools"
cp "$T/keep/tfsec" "$T/keep/ansible-lint" "$T/bin/"
printf 'rules: 1\n' >.ansible-lint; G add . && G commit -q -m cfg; : >"$HUB_LOG"; run
grep -q 'NOT CHECKED: ansible-lint (.ansible-lint or ansible.cfg changed' "$T/err" && ! grep -q '^ansible-lint' "$HUB_LOG" && ok ".ansible-lint changed in the diff: NOT CHECKED, not run" || bad "ansible config"
[ "$fail" = 0 ]
