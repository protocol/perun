#!/usr/bin/env bash
# review_checks.sh kics: brew kics exits 126 "unable to find queries" without -q outside its install dir. The wrapper adds -q DIR only when
# BINDIR/../share/kics/assets/queries exists, BINDIR being the directory of the resolved binary. Stub kics: 126 without -q, 50 with -q naming an existing dir.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/kicsq.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home" KLOG="$T/k.log"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" "$T/cellar/bin" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'FROM scratch\n' >Dockerfile; G add . && G commit -q -m code
cat >"$T/cellar/bin/kics" <<'S'
#!/usr/bin/env bash
echo "kics $*" >>"$KLOG"
q=; o=; a=("$@"); for ((i = 0; i < ${#a[@]}; i++)); do [ "${a[i]}" != -q ] || q=${a[i+1]}; [ "${a[i]}" != -o ] || o=${a[i+1]}; done
{ [ -n "$q" ] && [ -d "$q" ]; } || { echo "unable to find queries" >&2; exit 126; }
printf '{"queries":[{"query_name":"Run Using Sudo","severity":"HIGH","files":[{"file_name":"Dockerfile","line":1,"search_key":"k"}]}]}' >"$o/results.json"
exit 50
S
chmod +x "$T/cellar/bin/kics"; ln -s "$T/cellar/bin/kics" "$T/bin/kics"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"; chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink realpath sleep seq; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
: >"$KLOG"; run
grep -q 'not run: kics' "$T/err" && ! grep -q -- ' -q ' "$KLOG" && ok "no share dir: no -q, kics exit 126 is not run" || bad "no share dir: $(cat "$KLOG") $(grep kics "$T/err")"
mkdir -p "$T/cellar/share/kics/assets/queries"; : >"$KLOG"; run
grep -q -- ' -q [^ ]*/cellar/bin/../share/kics/assets/queries ' "$KLOG" && jq -e 'any(.[]; .tool=="kics" and .rule=="Run Using Sudo")' "$T/out" >/dev/null && ok "share dir present: -q DIR added through the symlink, row kept" || bad "share dir: $(cat "$KLOG") $(grep kics "$T/err")"
[ "$fail" = 0 ]
