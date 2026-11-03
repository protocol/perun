#!/usr/bin/env bash
# review_checks.sh offending-key line anchoring and Dockerfile chmod. Shims on a hermetic PATH print canned scanner JSON (synthetic fixtures).
# 1) trivy k8s row moves from the container start to the line of the key its Message quotes (names of the resource and container are skipped).
# 2) checkov row moves to the last evaluated_keys segment inside file_line_range.
# 3) trivy KSV-0125 is hygiene: hidden by default, kept with --hygiene.
# 4) a world-writable chmod in a Dockerfile RUN is a finding; chmod 755 is not.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/kl.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
t() { local d=$1 o; shift; if o=$("$@" 2>&1); then echo "ok - $d"; else echo "FAIL - $d"; fail=1; [ -z "$o" ] || printf '%s\n' "$o" | sed 's/^/    /'; fi; }
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= REVIEW_TRIVY_CACHE="$T/tc"
mkdir -p "$T/repo" "$T/bin" "$T/sys" "$T/tc/db" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
printf 'apiVersion: v1\nkind: Pod\n---\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  containers:\n    - name: app\n      image: img\n      securityContext:\n        privileged: false\n        runAsNonRoot: false\n' >k8s.yaml
printf 'resource "x" "y" {\n  name = "n"\n  open = true\n}\n' >main.tf
printf 'FROM alpine\nRUN chmod 755 /a\nRUN mkdir /d && chmod -R 777 /d\nRUN chmod a+w /e\n' >Dockerfile
G add . && G commit -q -m files
sh() { printf '#!/usr/bin/env bash\ncat <<'"'"'J'"'"'\n%s\nJ\nexit 0\n' "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
sh trivy '{"Results":[{"Target":"k8s.yaml","Misconfigurations":[{"ID":"KSV012","Severity":"MEDIUM","Title":"non-root","Message":"Container '"'app'"' of Deployment '"'web'"' should set '"'securityContext.runAsNonRoot'"' to true","CauseMetadata":{"Resource":"Deployment/web","StartLine":9,"EndLine":13}},{"ID":"KSV-0125","Severity":"MEDIUM","Title":"registry","Message":"x","CauseMetadata":{"StartLine":9}}]}]}'
sh checkov "{\"check_type\":\"terraform\",\"results\":{\"failed_checks\":[{\"check_id\":\"CKV_X_1\",\"check_name\":\"open\",\"file_abs_path\":\"$T/repo/main.tf\",\"file_line_range\":[1,4],\"check_result\":{\"evaluated_keys\":[\"rule/[0]/open\"]}}]}}"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
touch "$T/tc/db/trivy.db"
run() { PATH="$T/bin:$T/sys" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out" || { cat "$T/err" >&2; exit 1; }; }
# shellcheck disable=SC2329
trivy_key() { run; jq -e 'any(.[]; .tool=="trivy" and .rule=="KSV012" and .line==13)' "$T/out" >/dev/null; }
# shellcheck disable=SC2329
checkov_key() { run; jq -e 'any(.[]; .tool=="checkov" and .rule=="CKV_X_1" and .line==3)' "$T/out" >/dev/null; }
# shellcheck disable=SC2329
ksv0125() { run; ! jq -e 'any(.[]; .rule=="KSV-0125")' "$T/out" >/dev/null && run --hygiene && jq -e 'any(.[]; .rule=="KSV-0125")' "$T/out" >/dev/null; }
# shellcheck disable=SC2329
chmod_rule() { run; jq -e '[.[] | select(.rule=="world-writable-chmod") | .line] == [3,4]' "$T/out" >/dev/null; }
t "trivy row sits on the quoted key line (13), not the container start" trivy_key
t "checkov row sits on the evaluated key line (3), not the resource start" checkov_key
t "trivy KSV-0125 hidden by default, kept with --hygiene" ksv0125
t "Dockerfile world-writable chmod flagged (lines 3, 4), chmod 755 not" chmod_rule
[ "$fail" = 0 ]
