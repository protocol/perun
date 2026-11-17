#!/usr/bin/env bash
# review_checks.sh hub: gitleaks rows (redacted by the hub) carry a value-free " [shape: X]" hint read from the flagged source line:
# env-ref, marker-word, localhost, real-looking; a real-looking token (12+ chars, 3+ character classes) wins over marker words and over test paths.
# The raw value never appears in the output.
# Fixtures are assembled at runtime (no literal credentials in this file); stub gitleaks on a hermetic PATH.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubshape.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
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
mkdir -p "$T/repo/src" "$T/repo/tests" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
V=$(python3 -c 'import secrets; print("A" + secrets.token_hex(16) + "z9")') # the raw value: random per run, upper+lower+digit, never written literally
KW=tok; KW+=en
printf 'a = 1\n%s = "${DEPLOY_VAL}"\n' "$KW" >src/env.py
printf 'a = 1\n%s = "<%s>"\n' "$KW" "your-$KW" >src/ph.py
printf 'a = 1\n%s = "http://localhost:8080/path"\n' "$KW" >src/local.py
printf 'a = 1\n%s = "%s"\n' "$KW" "$V" >src/real.py
printf 'a = 1\n%s = "%s"\n' "$KW" "$V" >tests/test_real.py
printf 'a = 1\n%s = "%s"  # example changeme xxx localhost ${HOME}\n' "$KW" "$V" >src/ex.py
H=$(python3 -c 'import secrets; print(secrets.token_hex(20))') # 40 lowercase-hex chars, random per run
printf 'a = 1\n%s = "%s"  # example\n' "$KW" "$H" >src/hex.py
M=$(python3 -c 'import secrets; print("Q" + secrets.token_hex(6) + "z")') # 14 chars, upper+lower+digit
printf 'a = 1\n%s = "%s"  # example\n' "$KW" "$M" >src/short.py
G add -A && G commit -q -m change
python3 - "$T/gl.json" "$V" <<'PY'
import json, sys
rows = [{"RuleID": "acme-token", "Description": "d", "File": f, "StartLine": 2, "Fingerprint": f"fp:{f}", "Secret": sys.argv[2], "Match": sys.argv[2]}
        for f in ("src/env.py", "src/ph.py", "src/local.py", "src/real.py", "tests/test_real.py", "src/ex.py", "src/hex.py", "src/short.py")]
json.dump(rows, open(sys.argv[1], "w"))
PY
PATH="$T/bin:$T/sys" GL_JSON="$T/gl.json" bash "$RC" --base base >"$T/out" 2>"$T/err" || true
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }
sh() { jq -r --arg f "$1" '[.[] | select(.file==$f and .tool=="gitleaks")][0].message | capture("\\[shape: (?<s>[a-z-]+)\\]$").s' "$T/out"; }
eq "$(sh src/env.py)" env-ref "\${...} line -> env-ref"
eq "$(sh src/ph.py)" marker-word "<...> value -> marker-word"
eq "$(sh src/local.py)" localhost "localhost URL -> localhost"
eq "$(sh src/real.py)" real-looking "plain random value -> real-looking"
eq "$(sh tests/test_real.py)" real-looking "same value under tests/ -> real-looking (paths never soften the class)"
eq "$(sh src/ex.py)" real-looking "real value beside example/changeme/xxx/localhost/\${...} words -> real-looking"
eq "$(sh src/hex.py)" real-looking "40-char hex value beside an example comment -> real-looking"
eq "$(sh src/short.py)" real-looking "14-char mixed token beside an example comment -> real-looking"
eq "$(grep -c -- "$V" "$T/out" "$T/err" | tr '\n' ' ')" "$T/out:0 $T/err:0 " "raw value absent from stdout and stderr"
exit $fail
