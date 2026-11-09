#!/usr/bin/env bash
# review_checks.sh collapses ruff F821 (undefined name) hits per FILE when one file has more than 3 (one F821-summary row, first hit as line, message "N F821 hits in this file"
# and "; names: a, b, c" = the distinct backticked names in first-appearance order, first 5 then "…" if more); 3 or fewer stay per row, other ruff rules in the same file
# (F401) stay per row and a file of other-rule hits is never collapsed, REVIEW_FIXTURE_ROWS=all keeps every row. Stub ruff on PATH, hermetic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rfc.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/ruff" <<'STUB'
#!/usr/bin/env python3
import os, sys
path = sys.argv[-1][2:]  # last argument is "./<file>"; print only that file's concise lines
lines = [l for l in open(os.environ["STUB_RUFF_OUT"]) if l.startswith(path + ":")]
sys.stdout.write("".join(lines))
sys.exit(1 if lines else 0)
STUB
chmod +x "$T/bin/ruff"; export PATH="$T/bin:$PATH" STUB_RUFF_OUT="$T/ruff.txt"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base
git branch -f base
for f in pkg/names.py pkg/three.py pkg/mixed.py pkg/unused.py pkg/many.py; do mkdir -p "$(dirname "$f")"; echo 'x = 1' >"$f"; done
g add -A; g commit -q -m change
python3 - "$STUB_RUFF_OUT" <<'PY'
import sys
def hit(f, n, r, m): return f"{f}:{n}:1: {r} {m}"
out = [hit("pkg/names.py", n, "F821", f"Undefined name `{nm}`") for n, nm in ((3, "js"), (7, "cdp"), (9, "js"), (11, "goto_url"), (13, "sleep"))]  # 5 in one file: collapse
out += [hit("pkg/three.py", n, "F821", f"Undefined name `x{n}`") for n in (1, 2, 4)]  # 3 in one file: stays per row
out += [hit("pkg/mixed.py", n, "F821", f"Undefined name `{nm}`") for n, nm in ((5, "js"), (6, "cdp"), (8, "wait_for"), (10, "js"))]  # 4 F821 + 1 F401
out += [hit("pkg/mixed.py", 12, "F401", "`os` imported but unused")]
out += [hit("pkg/unused.py", n, "F401", "`re` imported but unused") for n in (1, 2, 3, 4)]  # other rule, 4 in one file: stays per row
out += [hit("pkg/many.py", n, "F821", f"Undefined name `n{n}`") for n in range(1, 8)]  # 7 distinct names: first 5 then "…"
open(sys.argv[1], "w").write("\n".join(out) + "\n")
PY
run() { env "$@" REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true; }
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); ru=[x for x in r if x["tool"]=="ruff"]; f8=[x for x in ru if x["rule"]=="F821-summary"]; '"$1" <<<"$out"; }
out=$(run X=1)
r=0; q 'm=[x for x in f8 if x["file"]=="pkg/names.py"]; p="5 F821 hits in this file (showing 3 of 5; REVIEW_FIXTURE_ROWS=all for every row): 3, 7, 9; names: js, cdp, goto_url, sleep"; sys.exit(0 if len(f8)==3 and len(m)==1 and m[0]["message"].startswith(p) and m[0]["line"]==3 and m[0]["text"]=="ruff: "+m[0]["message"] and "hint" not in m[0] else 1)' || r=$?; chk $r "5 F821 in one file -> one F821-summary row naming the distinct names, line = first hit, showing 3 of 5"
r=0; q 'x=[x for x in ru if x["file"]=="pkg/names.py"]; sys.exit(0 if len(x)==1 and x[0]["rule"]=="F821-summary" else 1)' || r=$?; chk $r "collapsed file leaves no per-row F821 rows"
r=0; q 'x=[x for x in ru if x["file"]=="pkg/three.py"]; sys.exit(0 if len(x)==3 and all(y["rule"]=="F821" and y["line"] in (1,2,4) and "summary" not in y["message"] for y in x) else 1)' || r=$?; chk $r "3 F821 in one file stay 3 per-row findings"
r=0; q 'x=[x for x in ru if x["file"]=="pkg/mixed.py"]; s=[y for y in x if y["rule"]=="F821-summary"]; sys.exit(0 if len(x)==2 and len(s)==1 and s[0]["message"].endswith("; names: js, cdp, wait_for") and [y for y in x if y["rule"]=="F401"][0]["line"]==12 else 1)' || r=$?; chk $r "4 F821 + 1 F401 in one file: F821 summary naming 3 distinct names, F401 row per-row"
r=0; q 'x=[x for x in ru if x["file"]=="pkg/unused.py"]; sys.exit(0 if len(x)==4 and all(y["rule"]=="F401" for y in x) else 1)' || r=$?; chk $r "4 F401 in one file (other ruff rule) stay per row"
r=0; q 'm=[x for x in f8 if x["file"]=="pkg/many.py"]; p="7 F821 hits in this file (showing 3 of 7; REVIEW_FIXTURE_ROWS=all for every row): 1, 2, 3; names: n1, n2, n3, n4, n5…"; sys.exit(0 if len(m)==1 and m[0]["message"].startswith(p) else 1)' || r=$?; chk $r "7 distinct F821 names -> first 5 then … in the summary"
r=0; q 'sys.exit(0 if len(ru)==11 and len(f8)==3 else 1)' || r=$?; chk $r "default: 11 ruff rows (3 F821 summaries, 3 F821 rows, 1 F401 row in mixed.py, 4 F401 rows)"
out=$(run REVIEW_FIXTURE_ROWS=all)
r=0; q 'sys.exit(0 if not f8 and len(ru)==24 and len([x for x in ru if x["rule"]=="F821"])==19 and len([x for x in ru if x["rule"]=="F401"])==5 else 1)' || r=$?; chk $r "REVIEW_FIXTURE_ROWS=all: 24 ruff rows, every F821 a row, no summary"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
