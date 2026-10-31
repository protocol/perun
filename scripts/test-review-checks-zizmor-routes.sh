#!/usr/bin/env bash
# review_checks.sh zizmor routing: zizmor also audits Dependabot config and action manifests, so the tool hub hands it those files
# as well as workflows. A zizmor shim on a hermetic PATH logs the files it is given, logs each one to stderr the way zizmor does
# ("INFO audit: zizmor: completed ./path", merged into the file the hub reads) and reports one finding on each, so no real zizmor
# runs. The list case compares every file zizmor is given: a missing file and a match that is too broad both fail it. A bracket in
# a path (x/[]/action.yml, x/[id]/action.yml) must not be mistaken for the start of the JSON.
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/zroutes.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
t() { local d=$1 o; shift; if o=$("$@" 2>&1); then echo "ok - $d"; else echo "FAIL - $d"; fail=1; [ -z "$o" ] || printf '%s\n' "$o" | sed 's/^/    /'; fi; } # t DESCRIPTION COMMAND...: shows the command's output when it fails
export ZLOG="$T/zizmor.log" PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # hermetic: no host cache or ~/.local/bin scanner
mkdir -p "$T/repo" "$T/bin" "$T/sys" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
# routed: workflows (already before this change, so only the list case sees them), Dependabot config (.yml and .yaml), action manifests (root, nested, in a bracket dir)
# not routed: a nested workflow, Dependabot config off the repo root's .github/, other YAML
wf=(.github/workflows/ci.yml .github/workflows/odd.yaml)
routed=(.github/dependabot.yml .github/dependabot.yaml .github/actions/setup/action.yml action.yaml 'x/[]/action.yml')
other=(.github/workflows/nested/inner.yml sub/.github/dependabot.yml docs/dependabot.yml config/app.yml config/reaction.yml docs/action.yml.md)
for f in "${wf[@]}" "${routed[@]}" "${other[@]}"; do mkdir -p "$(dirname "$f")"; echo 'name: acme' >"$f"; done
G add . && G commit -q -m files && git branch mid
# zizmor echoes each path as given ("./..."), exit 13 = findings
cat >"$T/bin/zizmor" <<'S'
#!/usr/bin/env bash
j=; sep=
for p; do
  case $p in -*) continue ;; esac
  echo "$p" >>"$ZLOG"; echo "INFO audit: zizmor: completed $p" >&2
  j+=$(printf '%s{"ident":"unpinned-uses","desc":"d","locations":[{"symbolic":{"key":{"Local":{"verbatim_path":"%s"}}},"concrete":{"location":{"start_point":{"row":0}}}}]}' "$sep" "$p"); sep=,
done
printf '[%s]\n' "$j"; exit 13
S
chmod +x "$T/bin/zizmor"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b" # only the system binaries review_checks.sh needs, never the host PATH
done
run() { PATH="$T/bin:$T/sys" bash "$RC" --base "$1" 2>"$T/err" >"$T/out" || { cat "$T/err" >&2; exit 1; }; } # run BASE: the hub's stderr is shown when it crashes
# lands FILE: the report has a zizmor row on FILE (called through t, so SC2329; $f is a jq variable, expanded by jq, so SC2016)
# shellcheck disable=SC2329,SC2016
lands() { jq -e --arg f "$1" 'any(.[]; .tool=="zizmor" and .file==$f)' "$T/out"; }
run base
for f in "${routed[@]}"; do t "zizmor finding lands on $f" lands "$f"; done
printf './%s\n' "${wf[@]}" "${routed[@]}" | sort >"$T/want"; sort "$ZLOG" >"$T/got"
t "zizmor is given the workflows and routed files and nothing else (not ${other[*]})" diff "$T/want" "$T/got"
# the first bracket in the output decides where the reader starts, so x/[id]/ needs a run of its own (x/[]/ above comes first in the list)
mkdir -p 'x/[id]' && echo 'name: acme' >'x/[id]/action.yml' && G add . && G commit -q -m id
run mid
t "zizmor finding lands on x/[id]/action.yml" lands 'x/[id]/action.yml'
exit $fail
