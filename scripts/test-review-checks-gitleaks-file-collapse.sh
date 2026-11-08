#!/usr/bin/env bash
# review_checks.sh collapses gitleaks generic-api-key hits per FILE when one non-fixture file has more than 3 (one generic-api-key-summary row, first hit as line,
# no likely-fixture hint unless the file name is fixture-like); 3 or fewer stay per row, every other rule in the same file stays per row, fixture-dir buckets
# keep their own summary, and REVIEW_FIXTURE_ROWS=all keeps every row. Stub gitleaks on PATH, hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-glfc.XXXXXX"); trap 'rm -rf "$T"' EXIT
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
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
python3 - >"$T/files" <<'PY'
import json
G = "generic-api-key"
hits = [("config/app.env", G, n) for n in (3, 7, 9, 11, 13)]  # 5 in one non-fixture file: collapse
hits += [("config/three.env", G, n) for n in (1, 2, 4)]  # 3 in one file: stays per row
hits += [("config/mixed.env", G, n) for n in (5, 6, 8, 10)] + [("config/mixed.env", "stripe-access-token", 12)]  # other rule stays per row
hits += [("tests/fixtures/fx.json", G, n) for n in (1, 2, 3, 4)]  # fixture dir: bucket, not per-file
hits += [("src/payment_test.py", G, n) for n in (1, 2, 3, 4)]  # name-only fixture match: per-file summary, tagged
hits += [("src/real.py", "stripe-access-token", 1)]  # real path, other rule: per row
secret = [{"File": f, "RuleID": r, "StartLine": n, "Description": "d", "Secret": "x"} for f, r, n in hits]
json.dump(secret, open("stub.json", "w"))
print("\n".join(sorted({f for f, _, _ in hits})))
PY
mv stub.json "$STUB_JSON"
while IFS= read -r f; do mkdir -p "$(dirname "$f")"; echo '{}' >"$f"; done <"$T/files"
g add -A; g commit -q -m files
run() { env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true; }
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); g=[x for x in r if x["tool"]=="gitleaks"]; sm=[x for x in g if x["rule"]=="generic-api-key-summary"]; '"$1" <<<"$out"; }
out=$(run X=1)
r=0; q 'm=[x for x in sm if x["file"]=="config/app.env"]; e="5 generic-api-key hits in this file (showing 3 of 5; REVIEW_FIXTURE_ROWS=all for every row): 3, 7, 9"; sys.exit(0 if len(sm)==3 and len(m)==1 and m[0]["message"]==e and m[0]["line"]==3 and m[0]["text"]=="gitleaks: "+e and "hint" not in m[0] else 1)' || r=$?; chk $r "5 generic hits in one non-fixture file -> one summary row, line = first hit, showing 3 of 5, no hint"
r=0; q 'x=[x for x in g if x["file"]=="config/app.env"]; sys.exit(0 if len(x)==1 else 1)' || r=$?; chk $r "collapsed file leaves no per-row generic-api-key rows"
r=0; q 'x=[x for x in g if x["file"]=="config/three.env"]; sys.exit(0 if len(x)==3 and all(y["rule"]=="generic-api-key" and "hint" not in y and y["line"] in (1,2,4) for y in x) else 1)' || r=$?; chk $r "3 generic hits in one file stay 3 per-row findings"
r=0; q 'x=[x for x in g if x["file"]=="config/mixed.env"]; sys.exit(0 if len(x)==2 and sorted(y["rule"] for y in x)==["generic-api-key-summary","stripe-access-token"] and [y for y in x if y["rule"]=="stripe-access-token"][0]["line"]==12 else 1)' || r=$?; chk $r "4 generic + 1 stripe in one file: summary for generic, stripe row per-row"
r=0; q 'x=[y for y in g if "tests/fixtures" in y["file"]]; sys.exit(0 if len(x)==1 and x[0]["rule"]=="likely-fixture-summary" and x[0]["file"]=="tests/fixtures/" and not [y for y in sm if "fixtures" in y["file"]] else 1)' || r=$?; chk $r "fixture-dir group of 4 still goes to the likely-fixture bucket, not the per-file summary"
r=0; q 'x=[y for y in sm if y["file"]=="src/payment_test.py"]; sys.exit(0 if len(x)==1 and x[0]["hint"]=="likely-fixture" and x[0]["text"].endswith("[likely-fixture]") and x[0]["message"].startswith("4 generic-api-key hits in this file") else 1)' || r=$?; chk $r "name-only fixture file with 4 hits -> per-file summary tagged likely-fixture"
r=0; q 'x=[y for y in g if y["file"]=="src/real.py"]; sys.exit(0 if len(x)==1 and x[0]["rule"]=="stripe-access-token" and "hint" not in x[0] else 1)' || r=$?; chk $r "other-rule real-path hit stays per row, untagged"
out=$(run REVIEW_FIXTURE_ROWS=all)
r=0; q 'sys.exit(0 if not sm and len([x for x in g if x["file"]=="config/app.env"])==5 and len([x for x in g if x["file"]=="src/payment_test.py"])==4 and len(g)==22 else 1)' || r=$?; chk $r "REVIEW_FIXTURE_ROWS=all: 22 gitleaks rows, every generic hit a row, no summary"
# new flag: the summary is new when ANY member line is on an added line, not only the first hit
mkdir "$T/n"; cd "$T/n"; g init -q .; mkdir config
printf 'line %s\n' 1 2 3 4 5 6 7 8 9 10 >config/diff.env; printf 'line %s\n' $(seq 1 14) >config/five.env; g add -A; g commit -q -m base1; g branch -f base1
printf 'line %s\n' 1 2 3 4 5 6 7 8 9 10 | sed '6s/.*/changed 6/' >config/diff.env
printf 'line %s\n' $(seq 1 14) | sed '13s/.*/changed 13/' >config/five.env; g add -A; g commit -q -m change
python3 - "$T/n.json" <<'PY'
import json, sys
json.dump([{"File": f, "RuleID": "generic-api-key", "StartLine": n, "Description": "d", "Secret": "x"} for f, ls in (("config/diff.env", (2, 4, 6, 8)), ("config/five.env", (3, 7, 9, 11, 13))) for n in ls], open(sys.argv[1], "w"))
PY
out=$(env STUB_JSON="$T/n.json" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base1 2>/dev/null || true)
r=0; q 'x=[y for y in sm if y["file"]=="config/diff.env"]; sys.exit(0 if len(x)==1 and x[0]["line"]==2 and x[0]["new"] is True else 1)' || r=$?; chk $r "4 hits, first old and only 3rd on an added line -> summary new == true"
r=0; q 'x=[y for y in sm if y["file"]=="config/five.env"]; sys.exit(0 if len(x)==1 and x[0]["new"] is True and x[0]["message"].endswith("showing 3 of 5; REVIEW_FIXTURE_ROWS=all for every row): 3, 7, 9; added: 13") and x[0]["text"]=="gitleaks: "+x[0]["message"] else 1)' || r=$?; chk $r "5 hits, only 5th added -> new true, message names added: 13"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
