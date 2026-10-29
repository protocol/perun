#!/usr/bin/env bash
# review_checks.sh collapses only generic-api-key hits (>3 per top fixture dir) to one summary row; every other rule (stripe, github-pat,
# openai, anthropic, private-key), small groups, name-only matches and real paths stay per-row; REVIEW_FIXTURE_ROWS=all/ALL/1/true restores
# every row, a bad value keeps the default. Stub gitleaks on PATH, hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-glfb.XXXXXX"); trap 'rm -rf "$T"' EXIT
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
hits = [(f"tests/fixtures/k{i:02d}.json", G, i + 1) for i in reversed(range(10))]  # reversed: samples must come out sorted
hits += [(f"tests/fixtures/{r}-{i}.json", r, 1) for r in ("stripe-access-token", "github-pat", "openai-api-key", "anthropic-api-key", "private-key") for i in range(4)]
hits += [(f"examples/e{i}.json", G, 1) for i in range(3)] + [(f"docs/d{i}.md", G, 1) for i in range(2)]  # groups of <=3 stay rows
hits += [("src/payment_test.py", G, 1)] + [(f"src/p{i}.sample.json", G, 1) for i in range(5)]  # name-only matches stay rows
hits += [("src/config.py", G, 1)]
json.dump([{"File": f, "RuleID": r, "StartLine": n, "Description": "d", "Secret": "x"} for f, r, n in hits], open("stub.json", "w"))
print("\n".join(f for f, _, _ in hits))
PY
mv stub.json "$STUB_JSON"
while IFS= read -r f; do mkdir -p "$(dirname "$f")"; echo '{}' >"$f"; done <"$T/files"
g add -A; g commit -q -m files
run() { env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true; }
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); g=[x for x in r if x["tool"]=="gitleaks"]; sm=[x for x in g if x["rule"]=="likely-fixture-summary"]; '"$1" <<<"$out"; }
out=$(run X=1)
r=0; q 'sys.exit(0 if len(sm)==1 and sm[0]["file"]=="tests/fixtures/" and sm[0]["line"]==0 and sm[0]["hint"]=="likely-fixture" else 1)' || r=$?; chk $r "10 generic hits under tests/fixtures -> one summary row"
r=0; q 'm=sm[0]; e="gitleaks: 10 generic-api-key hits under tests/fixtures/ tagged likely-fixture (showing 3 of 10; REVIEW_FIXTURE_ROWS=all for every row): tests/fixtures/k00.json:1, tests/fixtures/k01.json:2, tests/fixtures/k02.json:3 [likely-fixture]"; sys.exit(0 if m["text"]==e and m["message"]==e[len("gitleaks: "):-len(" [likely-fixture]")] else 1)' || r=$?; chk $r "summary text: count, dir, showing 3 of N, opt-out hint, sorted samples"
r=0; q 'sys.exit(0 if len(g)==33 else 1)' || r=$?; chk $r "33 rows: 1 summary + 20 other-rule + 5 small-group + 6 name-only + 1 real"
for rule in stripe-access-token github-pat openai-api-key anthropic-api-key private-key; do
  r=0; q 'x=[x for x in g if x["rule"]=="'$rule'"]; sys.exit(0 if len(x)==4 and all(y["hint"]=="likely-fixture" and y["text"].endswith("[likely-fixture]") for y in x) else 1)' || r=$?; chk $r "$rule fixture hits stay 4 tagged rows"; done
r=0; q 'x=[x for x in g if x["file"].startswith(("examples/", "docs/"))]; sys.exit(0 if len(x)==5 and all(y["rule"]=="generic-api-key" for y in x) else 1)' || r=$?; chk $r "groups of 3 and 2 generic hits stay rows"
r=0; q 'x=[x for x in g if x["file"]=="src/payment_test.py" or x["file"].endswith(".sample.json")]; sys.exit(0 if len(x)==6 and all(y["rule"]=="generic-api-key" and y["hint"]=="likely-fixture" for y in x) else 1)' || r=$?; chk $r "name-only matches (payment_test.py, *.sample.json) stay tagged rows even at 6"
r=0; q 'x=[x for x in g if x["file"]=="src/config.py"]; sys.exit(0 if len(x)==1 and "hint" not in x[0] and "likely" not in x[0]["text"] else 1)' || r=$?; chk $r "real-path hit kept, untagged"
out=$(run REVIEW_FIXTURE_ROWS=bogus)
r=0; q 'sys.exit(0 if len(sm)==1 and len(g)==33 else 1)' || r=$?; chk $r "bad REVIEW_FIXTURE_ROWS value keeps the default collapse"
for v in all ALL 1 true; do
  out=$(run REVIEW_FIXTURE_ROWS=$v)
  r=0; q 'sys.exit(0 if len(g)==42 and not sm else 1)' || r=$?; chk $r "REVIEW_FIXTURE_ROWS=$v: 42 per-row findings, no summary"; done
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
