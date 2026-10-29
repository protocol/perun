#!/usr/bin/env bash
# The matrix runs in both modes: REVIEW_FIXTURE_ROWS=all and the default (one hit per path never reaches the >3 collapse; see test-review-checks-gitleaks-fixture-bucket.sh).
# review_checks.sh tags gitleaks findings under sample/fixture/test/mock/docs paths with hint "likely-fixture" (one hit per path stays a row here);
# real-path findings stay untagged. Stub gitleaks on PATH emits fixed JSON, so the cases always run in CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-glfx.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/gitleaks" <<'STUB'
#!/usr/bin/env python3
import json, sys
a = sys.argv[1:]
rep, src = a[a.index("-r") + 1], a[a.index("-s") + 1].removeprefix("./")
d = json.load(open(__import__("os").environ["STUB_JSON"]))
if "--no-git" in a: d = [r for r in d if r["File"] == src]
json.dump(d, open(rep, "w"))
STUB
chmod +x "$T/bin/gitleaks"; export PATH="$T/bin:$PATH" STUB_JSON="$T/stub.json"
FILES=(public/data/prices.sample.json tests/a.py src/foo.test.js docs/guide.md fixtures/x.json app/__mocks__/m.js .env.example src/config.py src/latest.json lib/contest.py spec-parser/config.py sample-service/app.py test-runner/config.py example-app/main.py)
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
for f in "${FILES[@]}"; do mkdir -p "$(dirname "$f")"; echo '{}' >"$f"; done
g add -A; g commit -q -m files
python3 - "${FILES[@]}" >"$STUB_JSON" <<'PY'
import json, sys
print(json.dumps([{"File": f, "RuleID": "generic-api-key", "StartLine": 1, "Description": "d", "Secret": "x"} for f in sys.argv[1:]]))
PY
# hint FILE 1|0: exactly one row for FILE; tagged (hint + text suffix) iff $2 is 1
hint() { python3 -c 'import json,sys; r=[x for x in json.loads(sys.stdin.read()) if x["file"]==sys.argv[1] and x["tool"]=="gitleaks"]; t=sys.argv[2]=="1"; sys.exit(0 if len(r)==1 and (r[0].get("hint")=="likely-fixture")==t and r[0]["text"].endswith("[likely-fixture]")==t else 1)' "$1" "$2" <<<"$out"; }
for M in all default; do
out=$(REVIEW_FIXTURE_ROWS=$M REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true)
for f in public/data/prices.sample.json tests/a.py src/foo.test.js docs/guide.md fixtures/x.json app/__mocks__/m.js .env.example; do
  r=0; hint "$f" 1 || r=$?; chk $r "[$M] tagged, still reported: $f"; done
for f in src/config.py src/latest.json lib/contest.py spec-parser/config.py sample-service/app.py test-runner/config.py example-app/main.py; do
  r=0; hint "$f" 0 || r=$?; chk $r "[$M] real path untagged: $f"; done
done
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
