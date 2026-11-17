#!/usr/bin/env bash
# review_checks.sh drops a ruff-security Snnn row when bandit has Bnnn (same number) on the same file:line and tags the kept bandit row
# "[corroborated: bandit+ruff]". A non-twin rule on the same line, the same rule on a different line, and the B101-summary row stay untouched.
# Stub bandit and ruff on PATH, hermetic, fictional files only.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-brt.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/bandit" <<'STUB'
#!/usr/bin/env python3
import os, sys
sys.stdout.write(open(os.environ["STUB_BANDIT_JSON"]).read())
STUB
cat >"$T/bin/ruff" <<'STUB'
#!/usr/bin/env python3
import os, sys
sys.stdout.write(open(os.environ["STUB_RUFF_JSON"]).read() if "S" in sys.argv else "[]")
STUB
chmod +x "$T/bin/bandit" "$T/bin/ruff"; export PATH="$T/bin:$PATH" STUB_BANDIT_JSON="$T/b.json" STUB_RUFF_JSON="$T/r.json"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
mkdir pkg; for f in app asserts; do for i in $(seq 1 12); do echo 'x = 1'; done >"pkg/$f.py"; done; g add -A; g commit -q -m change
python3 - "$T" <<'PY'
import json, sys
t = sys.argv[1]
b = lambda f, r, n: {"filename": f"./{f}", "line_number": n, "test_id": r, "issue_text": "stub"}
s = lambda f, r, n: {"filename": f"./{f}", "location": {"row": n}, "code": r, "message": "stub"}
A, Z = "pkg/app.py", "pkg/asserts.py"
bh = [b(A, "B603", 3), b(A, "B603", 9)] + [b(Z, "B101", n) for n in (1, 2, 3, 4)]
rh = [s(A, "S603", 3), s(A, "S105", 3), s(A, "S603", 6)] + [s(Z, "S101", n) for n in (1, 2, 3, 4)]
json.dump({"results": bh}, open(t + "/b.json", "w")); json.dump(rh, open(t + "/r.json", "w"))
PY
out=$(REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --full 2>/dev/null || true)
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); a=[x for x in r if x["file"]=="pkg/app.py"]; z=[x for x in r if x["file"]=="pkg/asserts.py"]; at=lambda t,l,u: [x for x in a if x["tool"]==t and x["line"]==l and x["rule"]==u]; '"$1" <<<"$out"; }
r=0; q 'k=at("bandit",3,"B603"); sys.exit(0 if len(k)==1 and " [corroborated: bandit+ruff]" in k[0]["message"] and " [corroborated: bandit+ruff]" in k[0]["text"] and not at("ruff-security",3,"S603") else 1)' || r=$?; chk $r "twin pair B603+S603 same line: ruff dropped, bandit row tagged"
r=0; q 'k=at("bandit",3,"B603"); sys.exit(0 if k[0].get("also")==["ruff-security S603: stub"] and "also" not in at("bandit",9,"B603")[0] else 1)' || r=$?; chk $r "dropped ruff twin rides on the kept bandit row as also"
r=0; q 'k=at("ruff-security",3,"S105"); sys.exit(0 if len(k)==1 and "corroborated: bandit+ruff" not in k[0]["message"] else 1)' || r=$?; chk $r "non-twin S105 on the same line stays, untagged"
r=0; q 'k=at("bandit",9,"B603"); m=at("ruff-security",6,"S603"); sys.exit(0 if len(k)==1 and "bandit+ruff" not in k[0]["message"] and len(m)==1 else 1)' || r=$?; chk $r "same rule on a different line: both rows stay, untagged"
r=0; q 'sm=[x for x in z if x["rule"]=="B101-summary"]; sys.exit(0 if len(z)==1 and len(sm)==1 and "bandit+ruff" not in sm[0]["message"] else 1)' || r=$?; chk $r "B101-summary untouched, its S101 twins dropped"
r=0; q 'sys.exit(0 if len([x for x in a+z if x["tool"]=="ruff-security"])==2 else 1)' || r=$?; chk $r "ruff-security rows 7 -> 2 (5 saved)"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
