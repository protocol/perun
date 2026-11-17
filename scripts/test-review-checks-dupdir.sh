#!/usr/bin/env bash
# review_checks.sh --full precision folds, stub semgrep on a hermetic PATH, fictional content only:
#  1. byte-identical copies of a file (a vendored dir copied 3 times): same (tool, rule, line, content hash) rows collapse to the first path with hint "also: <other paths>";
#     a copy whose bytes differ keeps its own row.
#  2. a semgrep path-traversal row in a CLI file (sys.argv, no HTTP framework, no request object) gets hint cli-operator-input and severity low;
#     a file importing an HTTP framework, or reading request.args, is unchanged.
#  3. the same row emitted twice is one row; same rule on another line, or another message, stays.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/dupdir.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
printf '#!/usr/bin/env bash\ncat "$SG_JSON"\n' >"$T/bin/semgrep"; chmod +x "$T/bin/semgrep"
mkdir -p "$T/repo" && cd "$T/repo" && G init -q . && G commit -q --allow-empty -m base
body='import os\n\n\ndef load(p):\n    return open(os.path.join("/srv", p))\n'
for d in vendor/a vendor/b vendor/c; do mkdir -p "$d"; printf "$body" >"$d/lib.py"; done
mkdir -p vendor/d; printf "$body# edited\n" >vendor/d/lib.py
mkdir -p src tests/fixtures; printf "$body# s\n" >src/lib.py; printf "$body# s\n" >tests/fixtures/lib.py
printf 'import argparse\nimport os\n\n\ndef handler(event, context):\n    return open(os.path.join("/srv", event["p"]))\n\n\nif __name__ == "__main__":\n    argparse.ArgumentParser().parse_args()\n' >lambda.py
printf 'import sys\nimport os\n\n\ndef main():\n    return open(os.path.join("/srv", sys.argv[1]))\n' >cli.py
printf 'import flask\nimport sys\nimport os\n\n\ndef main():\n    return open(os.path.join("/srv", sys.argv[1]))\n' >web.py
printf 'import os\nfrom flask import request\n\n\ndef main():\n    return open(os.path.join("/srv", request.args["p"]))\n' >req.py
printf 'import os\n\n\ndef main(p):\n    return open(os.path.join("/srv", p))\n' >plain.py
G add -A && G commit -q -m change
sgr() { local md=; [ -z "${5:-}" ] || md=",\"metadata\":{\"cwe\":[\"$5: x\"]}"; printf '{"check_id":"acme.%s","path":"%s","start":{"line":%s},"extra":{"message":"%s","severity":"WARNING"%s}}' "$1" "$2" "$3" "${4:-m}" "$md"; }
P=("vendor/a/lib.py" "vendor/b/lib.py" "vendor/c/lib.py" "vendor/d/lib.py" src/lib.py tests/fixtures/lib.py lambda.py cli.py web.py req.py plain.py)
rows=()
for f in vendor/a/lib.py vendor/b/lib.py vendor/c/lib.py vendor/d/lib.py; do rows+=("$(sgr path-traversal "$f" 5)"); done
rows+=("$(sgr path-traversal src/lib.py 5)" "$(sgr path-traversal tests/fixtures/lib.py 5)" "$(sgr path-traversal lambda.py 6 m CWE-22)")
rows+=("$(sgr path-traversal cli.py 6)" "$(sgr path-traversal cli.py 6)" "$(sgr path-traversal cli.py 7)" "$(sgr path-traversal cli.py 6 other)")
rows+=("$(sgr path-traversal web.py 7)" "$(sgr path-traversal req.py 6)" "$(sgr path-traversal plain.py 5)" "$(sgr cmdi plain.py 5)")
printf '{"results":[%s],"errors":[],"paths":{"scanned":["%s"]}}\n' "$(IFS=,; echo "${rows[*]}")" "$(IFS=,; echo "${P[*]}" | sed 's/,/","/g')" >"$T/sg.json"
PATH="$T/bin:$T/sys" SG_JSON="$T/sg.json" bash "$RC" --full >"$T/out" 2>"$T/err" || true
q() { python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); f=lambda p,l=None: [x for x in r if x["file"].endswith(p) and x["tool"]=="semgrep" and (l is None or x["line"]==l)]; '"$1" "$T/out"; }
r=0; q 'a=f("vendor/a/lib.py"); sys.exit(0 if len(a)==1 and a[0].get("hint")=="also: vendor/b/lib.py, vendor/c/lib.py" and not f("vendor/b/lib.py") and not f("vendor/c/lib.py") else 1)' || r=$?; chk $r "3 byte-identical copies: one row on first path, hint names the other two"
r=0; q 'd=f("vendor/d/lib.py"); sys.exit(0 if len(d)==1 and "also" not in d[0].get("hint", "") else 1)' || r=$?; chk $r "copy with different bytes keeps its own row"
r=0; q 'c=f("cli.py",6); sys.exit(0 if len(c)==2 and all(x.get("hint")=="cli-operator-input" and "severity" not in x and "low" not in x["message"] for x in c) else 1)' || r=$?; chk $r "CLI file: path-traversal row hinted cli-operator-input, severity and message untouched"
r=0; q 'import re; l=f("lambda.py"); sys.exit(0 if len(l)==1 and "severity" not in l[0] and re.search(r"\[CWE-22, (?i:warning)\]", l[0]["message"]) else 1)' || r=$?; chk $r "Lambda handler with an argparse __main__ keeps its severity tag"
r=0; q 'a=f("src/lib.py",5); b=f("tests/fixtures/lib.py",5); sys.exit(0 if len(a)==1 and len(b)==1 and "also" not in a[0].get("hint", "") and "also" not in b[0].get("hint", "") else 1)' || r=$?; chk $r "fixture copy and src copy stay two rows"
r=0; q 'c=f("cli.py",6); sys.exit(0 if sorted(x["message"] for x in c)==["m","other"] else 1)' || r=$?; chk $r "same line, different message stays a second row"
r=0; q 'sys.exit(0 if len(f("cli.py",7))==1 and len(f("cli.py"))==3 else 1)' || r=$?; chk $r "identical row emitted twice is one; other line stays (3 rows in cli.py)"
r=0; q 'w=f("web.py")[0]; q_=f("req.py")[0]; p=f("plain.py"); sys.exit(0 if all("hint" not in x and "severity" not in x for x in (w,q_,*p)) else 1)' || r=$?; chk $r "HTTP-framework, request-object and plain files unchanged"
r=0; q 'sys.exit(0 if len(f("plain.py"))==2 else 1)' || r=$?; chk $r "unrelated rule on the same line is not dropped"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
