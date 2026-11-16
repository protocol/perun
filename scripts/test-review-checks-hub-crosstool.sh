#!/usr/bin/env bash
# review_checks.sh hub, two behaviours with stub tools on a hermetic PATH and fictional content only:
#  1. Cross-tool duplicates: semgrep, bandit, ruff-security and gosec rows on one file:line with one CWE collapse to a single row that lists every tool;
#     a different CWE on the line, or a row with no CWE tag, stays its own row.
#     The merged row keeps the highest severity any member carried.
#  2. Secret-scanner demotion: trufflehog and gitleaks rows whose password is a literal placeholder, a lockfile hash, a UUID in an id field, a uses: action SHA
#     or a linkedin identifier name get hint likely-fixture (kept, never dropped); the look-alikes (a real-looking password even on localhost, a bare UUID,
#     a SHA outside a uses: line, a plain word) keep no hint.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubxtool.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
fail=0
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
stub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/bin/$1"; }
stub semgrep 'cat "$SG_JSON"'
stub bandit 'cat "$BD_JSON"'
stub ruff 'case "$*" in *json*) cat "$RF_JSON" ;; esac'
stub gosec 'o=; a=("$@"); for i in "${!a[@]}"; do [ "${a[$i]}" = -out ] && o=${a[$((i + 1))]}; done; cat "$GS_JSON" >"$o"'
stub trufflehog 'cat "$TF_JSON"'
stub gitleaks 'rep=; a=("$@"); for i in "${!a[@]}"; do [ "${a[$i]}" = -r ] && rep=${a[$((i + 1))]}; done; case "$*" in *social.conf*) cat "$GL_JSON" ;; *) echo "[]" ;; esac >"$rep"' # the hub scans file by file: only social.conf has findings
chmod +x "$T/bin/"*
mkdir -p "$T/repo" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
PW="Zq8v""3Lr2"; HX=0123456789abcdef0123456789abcdef01234567; U=123e4567-e89b-12d3-a456-426614174000
printf 'import os\nimport subprocess\n\n\ndef run(x):\n    subprocess.call(x, shell=True)\n    os.system(x)\n' >app.py
printf 'package main\n\nfunc main() {\n}\n\nfunc open(p string) {\n}\n' >main.go
printf 'module acme\n\ngo 1.21\n' >go.mod
printf 'DB=postgres://user:pass@db.internal:5432/app\nMONGO=mongodb://root:example@db.internal/app\nREAL=postgres://svc:%s@db.acme.example.net/app\nLOCAL=postgres://svc:%s@localhost/app\nsource_id=%s\nHS=%s\nHSK=pat-na1-%s\nENVV=postgres://svc:${DB_PASS}@db/app\n' "$PW" "$PW" "$U" "$U" "$U" >db.env
printf 'steps:\n  - uses: acme/setup@%s\n  - uses: acme/setup@v3\n    run: echo acme@%s\n' "$HX" "$HX" >deploy.yml
printf '{\n  "integrity": "sha512-%s"\n}\n' "$HX" >package-lock.json
printf '{\n  "integrity": "sha512-%s"\n}\n' "$HX" >notes.json
printf 'linkedin_client_id = linkedinClient\nclient_id = 86ab12cd34ef\nclient_id = Acme\n' >social.conf
G add -A && G commit -q -m change
go() { PATH="$T/bin:$T/sys" SG_JSON="$T/sg.json" BD_JSON="$T/bd.json" RF_JSON="$T/rf.json" GS_JSON="$T/gs.json" TF_JSON="$T/tf.json" GL_JSON="$T/gl.json" bash "$RC" --base base >"$T/out" 2>"$T/err" || true; }
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }
sgr() { local md= sv=; [ -z "${4:-}" ] || md=",\"metadata\":{\"cwe\":[\"$4: x\"]}"; [ -z "${5:-}" ] || sv=",\"severity\":\"$5\""; printf '{"check_id":"acme.%s","path":"%s","start":{"line":%s},"extra":{"message":"m"%s%s}}' "$1" "$2" "$3" "$md" "$sv"; }
EMPTY_SG='{"results":[],"errors":[],"paths":{"scanned":["app.py","main.go"]}}'
echo '[]' >"$T/gl.json"; echo '{"runs":[{"results":[]}]}' >"$T/tf.json"

# 1. cross-tool duplicates
printf '{"results":[%s,%s,%s,%s],"errors":[],"paths":{"scanned":["app.py","main.go"]}}\n' "$(sgr cmdi app.py 6 CWE-78 WARNING)" "$(sgr nocwe app.py 6)" "$(sgr other app.py 7 CWE-78)" "$(sgr trav main.go 6 CWE-22 INFO)" >"$T/sg.json"
echo '{"results":[{"filename":"app.py","line_number":6,"test_id":"B602","issue_cwe":{"id":78},"issue_severity":"HIGH"},{"filename":"app.py","line_number":7,"test_id":"B605","issue_cwe":{"id":77}}]}' >"$T/bd.json"
echo '[{"filename":"app.py","code":"S602","location":{"row":6},"message":"shell"},{"filename":"app.py","code":"S999","location":{"row":7},"message":"no bandit twin"}]' >"$T/rf.json"
echo '{"Issues":[{"file":"main.go","line":"6","rule_id":"G304","details":"d","cwe":{"id":"22"},"severity":"MEDIUM"}]}' >"$T/gs.json"
go
at() { jq -c --arg f "$1" --argjson l "$2" '[.[] | select(.file==$f and .line==$l and .rule!="not-checked")]' "$T/out"; }
eq "$(at app.py 6 | jq 'map(select(.tools != null)) | length')" 1 "semgrep+bandit+ruff-security, one CWE: one row"
eq "$(at app.py 6 | jq -r 'map(select(.tools != null))[0] | .tool + ":" + (.tools | join(","))')" "semgrep:bandit,ruff-security,semgrep" "kept row is semgrep and lists all three tools"
eq "$(at app.py 6 | jq -r 'map(select(.tools != null))[0].message | test("\\[also reported by: bandit B602, ruff-security S602\\]")')" true "message names the other tools' rules"
eq "$(at app.py 6 | jq '[.[] | select(.tools == null)] | length')" 1 "a row with no CWE tag stays separate"
eq "$(at app.py 7 | jq length)" 3 "line 7: semgrep CWE-78, bandit CWE-77, ruff S999 stay three rows (different CWE, no twin)"
eq "$(at main.go 6 | jq 'length')" 1 "semgrep+gosec on one CWE: one row"
eq "$(at main.go 6 | jq -r '.[0].tools | join(",")')" "gosec,semgrep" "go row lists both tools"
eq "$(at app.py 6 | jq -r 'map(select(.tools != null))[0].message | test("\\[CWE-78, high\\]")')" true "merged row keeps the highest severity (semgrep warning, bandit high)"
eq "$(at main.go 6 | jq -r '.[0].message | test("\\[CWE-22, medium\\]")')" true "merged row keeps the highest severity (semgrep info, gosec medium)"

# 2. secret demotion
echo "$EMPTY_SG" >"$T/sg.json"; echo '{"results":[]}' >"$T/bd.json"; echo '[]' >"$T/rf.json"; echo '{"Issues":[]}' >"$T/gs.json"
tr_() { printf '{"ruleId":"%s","locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
printf '{"runs":[{"results":[%s]}]}\n' "$(IFS=,; echo "$(tr_ URI db.env 1),$(tr_ MongoDB db.env 2),$(tr_ Postgres db.env 3),$(tr_ URI db.env 4),$(tr_ HubSpotApiKey db.env 5),$(tr_ HubSpotApiKey db.env 6),$(tr_ HubSpotApiKey db.env 7),$(tr_ URI db.env 8),$(tr_ CloudflareApiToken deploy.yml 2),$(tr_ CloudflareApiToken deploy.yml 3),$(tr_ CloudflareApiToken deploy.yml 4),$(tr_ CircleCI package-lock.json 2),$(tr_ CircleCI notes.json 2)")" >"$T/tf.json"
printf '[{"RuleID":"linkedin-client-id","File":"social.conf","StartLine":1,"Secret":"linkedinClient","Description":"d","Fingerprint":"f1"},{"RuleID":"linkedin-client-id","File":"social.conf","StartLine":2,"Secret":"86ab12cd34ef","Description":"d","Fingerprint":"f2"},{"RuleID":"linkedin-client-id","File":"social.conf","StartLine":3,"Secret":"Acme","Description":"d","Fingerprint":"f3"}]\n' >"$T/gl.json"
go
hint() { jq -r --arg f "$1" --argjson l "$2" --arg t "$3" '[.[] | select(.file==$f and .line==$l and .tool==$t)] | if length == 0 then "MISSING" else (.[0].hint // "none") end' "$T/out"; }
eq "$(hint db.env 1 trufflehog)" likely-fixture "URI user:pass placeholder demoted"
eq "$(hint db.env 2 trufflehog)" likely-fixture "Mongo root:example placeholder demoted"
eq "$(hint db.env 3 trufflehog)" none "real-looking password on a real-looking host keeps no hint"
eq "$(hint db.env 4 trufflehog)" none "real-looking password at localhost keeps no hint (the host never decides)"
eq "$(hint db.env 5 trufflehog)" likely-fixture "HubSpot UUID in an id field demoted"
eq "$(hint db.env 6 trufflehog)" none "HubSpot bare UUID keeps no hint"
eq "$(hint db.env 7 trufflehog)" none "HubSpot pat-prefixed key keeps no hint"
eq "$(hint db.env 8 trufflehog)" likely-fixture "URI with a \${...} password placeholder demoted"
eq "$(hint deploy.yml 2 trufflehog)" likely-fixture "Cloudflare 40-hex action SHA after @ in a uses: line demoted"
eq "$(hint deploy.yml 3 trufflehog)" none "action tag keeps no hint"
eq "$(hint deploy.yml 4 trufflehog)" none "40-hex after @ outside a uses: line keeps no hint"
eq "$(hint package-lock.json 2 trufflehog)" likely-fixture "Circle hash in a lockfile demoted"
eq "$(hint notes.json 2 trufflehog)" none "same hash outside a lockfile or manifest keeps no hint"
eq "$(hint social.conf 1 gitleaks)" likely-fixture "linkedin value that is an identifier name demoted"
eq "$(hint social.conf 2 gitleaks)" none "credential-shaped linkedin value keeps no hint"
eq "$(hint social.conf 3 gitleaks)" none "linkedin value that is a plain word keeps no hint"
eq "$(jq '[.[] | select(.tool=="trufflehog" or .tool=="gitleaks")] | length' "$T/out")" 16 "no secret row is dropped"
eq "$(jq -r '[.[] | select(.hint) | .text | test("\\[likely-fixture: .+\\] \\[likely-fixture\\]$") | not] | all' "$T/out")" true "text carries the reason once"
eq "$(grep -c "$PW\|$HX" "$T/out" || true)" 0 "no matched value is printed"
exit $fail
