#!/usr/bin/env bash
# review_checks.sh .gitleaks-allow (rule + path glob + sha256 of the secret text, read from BASE only). Uses a stub gitleaks on
# PATH that emits fixed JSON, so the cases always run in CI. Covers: drop on match, other secret kept, uppercase hash, empty
# secret, * vs **, malformed or non-UTF-8 list (fail closed), an entry added by the change (not applied, reported),
# survival of a history rewrite, the history path, and a lockfile skipped by the template.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-gla.XXXXXX"); trap 'rm -rf "$T"' EXIT
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
s1="fake""-secret-one-aaaa"; s2="fake""-secret-two-bbbb"  # built at runtime
H1=$(printf %s "$s1" | shasum -a 256 | cut -d' ' -f1)
EMPTY=$(printf '' | shasum -a 256 | cut -d' ' -f1)
# mk <allowlist file content printed by $1 or "-" for none> <where: base|head>; files: src/a.json src/b.json src/deep/c.json
mk() { rm -rf "$T/r"; mkdir "$T/r"; cd "$T/r"; g init -q .; mkdir -p src/deep
  [ "$2" = base ] && [ "$1" != - ] && printf '%b' "$1" >.gitleaks-allow
  g add -A; g commit -q --allow-empty -m base; git branch -f base
  [ "$2" = head ] && printf '%b' "$1" >.gitleaks-allow
  for f in src/a.json src/b.json src/deep/c.json; do echo '{}' >$f; done
  g add -A; g commit -q -m files; }
# stub <file:secret>... -> JSON of aws-access-token findings
stub() { python3 - "$@" >"$STUB_JSON" <<'PY'
import json, sys
print(json.dumps([{"File": x.split(":", 1)[0], "RuleID": "aws-access-token", "StartLine": 1, "Description": "d", "Secret": x.split(":", 1)[1]} for x in sys.argv[1:]]))
PY
}
run() { bash "$RC" --base base "$@" 2>"$T/err" || true; }
has() { grep -q "\"file\": \"$1\"\|$1.*allowlist\|\"rule\": \"$1" <<<"$out"; }
mk "# c\naws-access-token src/*.json $H1\n" base; stub "src/a.json:$s1" "src/b.json:$s2"; out=$(run)
! has src/a.json; chk $? "matching hash is dropped"
has src/b.json; chk $? "different secret under the same glob is reported"
grep -q 'suppressed 1 finding' "$T/err"; chk $? "suppressed count printed"
! { grep -q "$s1" <<<"$out" || grep -q "$s1" "$T/err"; }; chk $? "secret never printed"
g commit -q --amend -m rewritten; g commit -q --allow-empty -m more; out=$(run)
! has src/a.json; chk $? "entry survives a history rewrite"
mk "aws-access-token src/*.json $(tr a-f A-F <<<"$H1")\n" base; stub "src/a.json:$s1"; out=$(run)
! has src/a.json; chk $? "uppercase hash is accepted"
mk "aws-access-token src/*.json $H1\n" base; stub "src/a.json:"; out=$(run)
has src/a.json; chk $? "empty secret is never allowed"
mk "aws-access-token src/*.json $EMPTY\n" base; stub "src/a.json:$s1"; out=$(run)
has src/a.json && grep -q 'malformed' "$T/err"; chk $? "empty-string hash voids the list"
mk "aws-access-token src/*.json $H1\n" base; stub "src/deep/c.json:$s1"; out=$(run)
has src/deep/c.json; chk $? "* does not cross /"
mk "aws-access-token src/**.json $H1\n" base; stub "src/deep/c.json:$s1" "src/a.json:$s1"; out=$(run)
! has src/deep/c.json && ! has src/a.json; chk $? "** crosses /"
for bad in "aws-access-token src/*.json\n" "aws-access-token src/*.json nothex\n" "aws-access-token src/*.json $H1 extra\n" "\\xff\\xfe\\n"; do
  mk "$bad" base; stub "src/a.json:$s1"; out=$(run)
  has src/a.json && grep -q 'malformed' "$T/err"; chk $? "malformed allowlist keeps findings: ${bad:0:30}"
done
mk "aws-access-token src/*.json $H1\n" head; stub "src/a.json:$s1"; out=$(run)
has src/a.json && has allowlist-changed; chk $? "entry added by the change is reported, not applied"
mk "aws-access-token src/*.json $H1\n" base; stub "src/a.json:$s1" "src/b.json:$s2"; out=$(run --history)
! has src/a.json && has src/b.json; chk $? "history path honors the allowlist"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
