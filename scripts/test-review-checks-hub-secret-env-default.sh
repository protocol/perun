#!/usr/bin/env bash
# review_checks.sh hub: an env read alone is "[shape: env-ref]"; an env read that also carries a quoted fallback literal of 6+ chars is "[shape: env-default]".
# Fixtures are assembled at runtime (no literal credentials in this file); stub gitleaks on a hermetic PATH.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubenvdef.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
fail=0
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
cat >"$T/bin/gitleaks" <<'S'
#!/usr/bin/env bash
rep=; a=("$@"); for i in "${!a[@]}"; do [ "${a[$i]}" = -r ] && rep=${a[$((i + 1))]}; done
cat "$GL_JSON" >"$rep"
S
chmod +x "$T/bin/gitleaks"
mkdir -p "$T/repo/src" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
D=fall; D+=back
printf 'import os\na = 1\nk = os.environ["DEPLOY_VAL"]\n' >src/ref.py
printf 'import os\na = 1\nk = os.environ.get("DEPLOY_VAL", "%s")\n' "$D" >src/def.py
printf 'a = 1\nk = getenv("DEPLOY_VAL", "%s")\n' "$D" >src/get.js
G add -A && G commit -q -m change
python3 - "$T/gl.json" <<'PY'
import json, sys
rows = [{"RuleID": "acme-token", "Description": "d", "File": f, "StartLine": n, "Fingerprint": f"fp:{f}", "Secret": "x", "Match": "x"}
        for f, n in (("src/ref.py", 3), ("src/def.py", 3), ("src/get.js", 2))]
json.dump(rows, open(sys.argv[1], "w"))
PY
PATH="$T/bin:$T/sys" GL_JSON="$T/gl.json" bash "$RC" --base base >"$T/out" 2>"$T/err" || true
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }
sh() { jq -r --arg f "$1" --argjson l "$2" '[.[] | select(.file==$f and .line==$l and .tool=="gitleaks")][0].message | capture("\\[shape: (?<s>[a-z-]+)\\]$").s' "$T/out"; }
eq "$(sh src/ref.py 3)" env-ref "env read only -> env-ref"
eq "$(sh src/def.py 3)" env-default "os.environ.get with a quoted default -> env-default"
eq "$(sh src/get.js 2)" env-default "getenv with a quoted default -> env-default"
exit $fail
