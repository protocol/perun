#!/usr/bin/env bash
# review_checks.sh collapses bandit B101 (assert) hits per FILE when one file has more than 3 (one B101-summary row, first hit as line, message "N B101 hits in this file");
# 3 or fewer stay per row, every other bandit rule in the same file (B105) stays per row, a B101 hit under a test directory is per-file (no fixture bucket),
# REVIEW_FIXTURE_ROWS=all keeps every row, and the added-line "new" flag and "added: N" naming apply. Stub bandit on PATH, hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-bac.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/bandit" <<'STUB'
#!/usr/bin/env python3
import os, sys
sys.stdout.write(open(os.environ["STUB_BANDIT_JSON"]).read())
STUB
chmod +x "$T/bin/bandit"; export PATH="$T/bin:$PATH" STUB_BANDIT_JSON="$T/stub.json"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base
# base: pkg/app.py has 14 lines so the HEAD edit to line 13 is a real added line
mkdir pkg; printf 'line %s\n' $(seq 1 14) >pkg/app.py; g add -A; g commit -q -m base1; git branch -f base
sed '13s/.*/changed 13/' pkg/app.py >pkg/app.tmp && mv pkg/app.tmp pkg/app.py
for f in pkg/three.py pkg/mixed.py tests/unit/test_x.py; do mkdir -p "$(dirname "$f")"; echo 'x = 1' >"$f"; done
g add -A; g commit -q -m change
python3 - "$STUB_BANDIT_JSON" <<'PY'
import json, sys
def hit(f, t, n): return {"filename": f"./{f}", "line_number": n, "test_id": t, "issue_text": "stub"}
hits = [hit("pkg/app.py", "B101", n) for n in (3, 7, 9, 11, 13)]  # 5 in one file: collapse
hits += [hit("pkg/three.py", "B101", n) for n in (1, 2, 4)]  # 3 in one file: stays per row
hits += [hit("pkg/mixed.py", "B101", n) for n in (5, 6, 8, 10)] + [hit("pkg/mixed.py", "B105", 12)]  # other rule stays per row
hits += [hit("tests/unit/test_x.py", "B101", n) for n in (1, 2, 3, 4)]  # test dir: per-file summary, untagged
json.dump({"results": hits}, open(sys.argv[1], "w"))
PY
run() { env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true; }
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); b=[x for x in r if x["tool"]=="bandit"]; sm=[x for x in b if x["rule"]=="B101-summary"]; '"$1" <<<"$out"; }
out=$(run X=1)
r=0; q 'm=[x for x in sm if x["file"]=="pkg/app.py"]; e="5 B101 hits in this file (showing 3 of 5; REVIEW_FIXTURE_ROWS=all for every row): 3, 7, 9; added: 13"; sys.exit(0 if len(sm)==3 and len(m)==1 and m[0]["message"]==e and m[0]["line"]==3 and m[0]["text"]=="bandit: "+e and m[0]["new"] is True and "hint" not in m[0] else 1)' || r=$?; chk $r "5 B101 in one file -> one B101-summary row, line = first hit, showing 3 of 5, new + added: 13"
r=0; q 'x=[x for x in b if x["file"]=="pkg/app.py"]; sys.exit(0 if len(x)==1 and x[0]["rule"]=="B101-summary" else 1)' || r=$?; chk $r "collapsed file leaves no per-row B101 rows"
r=0; q 'x=[x for x in b if x["file"]=="pkg/three.py"]; sys.exit(0 if len(x)==3 and all(y["rule"]=="B101" and y["line"] in (1,2,4) and "hint" not in y for y in x) else 1)' || r=$?; chk $r "3 B101 in one file stay 3 per-row findings"
r=0; q 'x=[x for x in b if x["file"]=="pkg/mixed.py"]; sys.exit(0 if len(x)==2 and sorted(y["rule"] for y in x)==["B101-summary","B105"] and [y for y in x if y["rule"]=="B105"][0]["line"]==12 else 1)' || r=$?; chk $r "4 B101 + 1 B105 in one file: summary for B101, B105 row per-row"
r=0; q 'x=[y for y in sm if y["file"]=="tests/unit/test_x.py"]; sys.exit(0 if len(x)==1 and x[0]["message"].startswith("4 B101 hits in this file") and "hint" not in x[0] and not [y for y in b if y["rule"]=="likely-fixture-summary"] else 1)' || r=$?; chk $r "B101 under a test dir -> per-file summary, not a fixture bucket, untagged"
out=$(run REVIEW_FIXTURE_ROWS=all)
r=0; q 'sys.exit(0 if not sm and len(b)==17 and len([x for x in b if x["file"]=="pkg/app.py"])==5 and len([x for x in b if x["rule"]=="B105"])==1 else 1)' || r=$?; chk $r "REVIEW_FIXTURE_ROWS=all: 17 bandit rows, every B101 a row, no summary"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
