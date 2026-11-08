#!/usr/bin/env bash
# review_checks.sh trufflehog rows: a hit on a line inside a long unbroken base64/hex blob (notebook image output, asset digest) is dropped; a hit on an ordinary
# assignment line, or on a line the scan cannot re-read, is kept. Fake trufflehog on a hermetic PATH; synthetic fixtures only.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-thblob.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/sys" "$T/tmp" "$T/heavy"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl true sort uniq tr cut wc awk date cp mv ls find touch tee readlink sleep uname paste; do
  p=$(type -P "$b") && ln -s "$p" "$T/sys/$b"
done
# Fake: one SARIF result per "file:line" in TF_HITS that is among the named files.
cat >"$T/bin/trufflehog" <<'S'
#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]; files = [os.path.normpath(p) for p in a[a.index("filesystem") + 1:]]
res = []
for h in os.environ["TF_HITS"].split():
    f, n = h.rsplit(":", 1)
    if f in files: res.append({"ruleId": "Box", "level": "warning", "message": {"text": "x"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": f}, "region": {"startLine": int(n)}}}]})
print(json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "trufflehog", "rules": []}}, "results": res}]}))
S
chmod +x "$T/bin/trufflehog"
R="$T/repo"; mkdir "$R"; cd "$R" || exit 1
git init -q . && g commit -q --allow-empty -m init && git branch base
blob=$(printf 'QUJD%.0s' $(seq 1 80)) # 320 base64 chars, no spaces
printf '   "image/png": "%s",\n' "$blob" >nb.ipynb # notebook output mime key at line start: dropped
printf 'x = 1\nBOX_TOKEN = "%s"\n' "$(printf 'a1B2%.0s' 1 2 3 4 5 6 7 8)" >cfg.py
printf 'short line\n' >short.txt
printf '"%s\\n",\n' "$(printf 'QUJD%.0s' $(seq 1 20))" >wrap.ipynb # 80-char wrapped base64 chunk
printf 'apiVersion: v1\n  tls.key: %s\n' "$(printf 'QUJD%.0s' $(seq 1 80))" >k8s.yaml # 320 base64 chars on a yaml line: kept
printf '    "key = '"'"'%s'"'"'\\n",\n' "$blob" >cell.ipynb # code-cell base64 literal: kept
printf '%s\n' '    "    h = {\"Content-Type\": \"image/png\", \"Authorization\": \"Bearer TOKENPLACEHOLDER\"}\n",' >code.ipynb # code-cell line naming an image mime: kept
printf '<img src="data:image/png;base64,%s"/>\n' "$blob" >html.ipynb # data: URI in a notebook: dropped
printf '    "    \\"%s\\"\\n",\n' "$(printf 'ab12%.0s' $(seq 1 16))" >hex.ipynb # bare 64-hex code-cell literal: kept
printf 'x = 1\n%s' "$blob" >zero.css # no trailing newline, last line a blob: startLine 0 must keep the row
printf 'x = 1\n' >gzdiff.css; printf 'y = 2\n' | gzip >gzdiff.css.gz # gz content differs from its X: kept
printf '%s\n' "$blob" >src.map # source-map blob line: kept
mkdir -p public/assets; printf '{"x": "%s"}\n' "$blob" >public/assets/.sprockets-manifest-0123456789abcdef0123.json
printf '{"k": "%s"}\n' "$(printf 'ab cd %.0s' $(seq 1 400))" >cfg.json # >2000-char json line, no base64 run: kept
printf '.a{background:url(/x-%s.png)}%s\n' "$(printf 'ab12%.0s' 1 2 3 4 5 6 7 8)" "$(printf ' .b{c:d}%.0s' $(seq 1 300))" >app.css # >2000-char minified line
printf 'x = 1\n' >dig.css; printf 'x = 1\n' | gzip >dig.css.gz
g add . && g commit -q -m change
run() { (env PATH="$T/bin:$T/sys" DCR_USER_BIN= TMPDIR="$T/tmp" PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 TF_HITS="$1" bash "$RC" --base base >"$T/out" 2>"$T/err") || true; }
run "nb.ipynb:1 cfg.py:2 short.txt:99 wrap.ipynb:1 app.css:1 dig.css.gz:1 dig.css:1 k8s.yaml:2 public/assets/.sprockets-manifest-0123456789abcdef0123.json:1 cfg.json:1 cell.ipynb:1 html.ipynb:1 code.ipynb:1 hex.ipynb:1 zero.css:0 gzdiff.css.gz:1 src.map:1"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="nb.ipynb")] | length == 0' "$T/out" >/dev/null; chk $? "hit inside a long base64 blob line is dropped"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="cfg.py" and .line==2)] | length == 1' "$T/out" >/dev/null; chk $? "hit on a BOX_TOKEN assignment line is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="short.txt")] | length == 1' "$T/out" >/dev/null; chk $? "hit on a line that cannot be re-read (past EOF) is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="wrap.ipynb")] | length == 1' "$T/out" >/dev/null; chk $? "hit on a wrapped base64 chunk line in a notebook is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="app.css")] | length == 0' "$T/out" >/dev/null; chk $? "hit on a >2000-char minified css line is dropped"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="dig.css.gz")] | length == 0' "$T/out" >/dev/null; chk $? "hit in X.gz beside X is dropped"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="dig.css")] | length == 1' "$T/out" >/dev/null; chk $? "hit on a short css line is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="k8s.yaml" and .line==2)] | length == 1' "$T/out" >/dev/null; chk $? "base64 line in a yaml file is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="public/assets/.sprockets-manifest-0123456789abcdef0123.json")] | length == 0' "$T/out" >/dev/null; chk $? "digest manifest is dropped"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="cfg.json" and .line==1)] | length == 1' "$T/out" >/dev/null; chk $? "long line in a json file is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="cell.ipynb" and .line==1)] | length == 1' "$T/out" >/dev/null; chk $? "base64 literal in a notebook code cell is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="html.ipynb")] | length == 0' "$T/out" >/dev/null; chk $? "data:image base64 URI in a notebook is dropped"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="code.ipynb")] | length == 1' "$T/out" >/dev/null; chk $? "notebook code-cell line naming image/png is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="hex.ipynb")] | length == 1' "$T/out" >/dev/null; chk $? "bare 64-hex notebook code-cell line is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="zero.css" and .line==0)] | length == 1' "$T/out" >/dev/null; chk $? "startLine 0 keeps the row, never reads the last line"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="gzdiff.css.gz")] | length == 1' "$T/out" >/dev/null; chk $? "gz whose content differs from its X is kept"
jq -e '[.[] | select(.tool=="trufflehog" and .file=="src.map")] | length == 1' "$T/out" >/dev/null; chk $? "base64 blob line in a .map file is kept"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
