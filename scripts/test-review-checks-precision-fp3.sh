#!/usr/bin/env bash
# review_checks.sh hub precision, three false-positive classes (rows are tagged or collapsed, never silently dropped):
#  1. gitleaks aws-access-token inside a presigned URL query (X-Amz-Credential=) -> hint non-secret-lead, tagged low; a bare key line is untouched.
#  2. shell=True rows from semgrep + bandit + ruff-security on a line with a justified suppression (# noqa: S602 / # nosec + reason) -> one
#     "suppressed-with-reason" row; a bare "# nosec" (no reason) and an unsuppressed line keep their rows.
#  3. zizmor template-injection where every ${{ }} is a non-attacker context -> hint low-risk-context; step outputs and mixed lines are untouched.
# Stub tools on PATH (assertions filter by tool), fictional files only; the key ID is assembled at runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-fp3.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
mkdir "$T/bin"
cat >"$T/bin/gitleaks" <<'STUB'
#!/usr/bin/env bash
rep=; a=("$@"); for i in "${!a[@]}"; do [ "${a[$i]}" = -r ] && rep=${a[$((i + 1))]}; done
cat "$STUB_GL_JSON" >"$rep"
STUB
cat >"$T/bin/semgrep" <<'STUB'
#!/usr/bin/env bash
cat "$STUB_SG_JSON"
STUB
cat >"$T/bin/zizmor" <<'STUB'
#!/usr/bin/env bash
cat "$STUB_ZZ_JSON"; exit 13
STUB
cat >"$T/bin/bandit" <<'STUB'
#!/usr/bin/env bash
cat "$STUB_BANDIT_JSON"
STUB
cat >"$T/bin/ruff" <<'STUB'
#!/usr/bin/env bash
case " $* " in *" S "*|*S,*|*" --select S"*) cat "$STUB_RUFF_JSON" ;; *) echo '[]' ;; esac
STUB
chmod +x "$T/bin/"*; export PATH="$T/bin:$PATH" STUB_GL_JSON="$T/gl.json" STUB_SG_JSON="$T/sg.json" STUB_ZZ_JSON="$T/zz.json" STUB_BANDIT_JSON="$T/b.json" STUB_RUFF_JSON="$T/r.json"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
KID="AK"; KID+="IA0123456789ABCDEF"
mkdir -p src .github/workflows
printf 'a = 1\nurl = "https://files.example.com/o?X-Amz-Credential=%s%%2F20260101%%2Fus-east-1%%2Fs3%%2Faws4_request"\nkey = "%s"\n' "$KID" "$KID" >src/presign.py
{ echo 'import subprocess'
  echo 'subprocess.run(a, shell=True)  # noqa: S602  # nosec B602 - operator command, run by design'
  echo 'subprocess.run(b, shell=True)  # nosec'
  echo 'subprocess.run(c, shell=True)'
  echo 'subprocess.run(d, shell=True)  # noqa: S602 - trusted record only'
  echo 'subprocess.run(e, shell=True)  # noqa: E501 - long line is fine here'
  echo 'subprocess.run(f, shell=True)  # nosec - trusted operator input only'
  echo 'subprocess.run(g, shell=True)  # nosemgrep: perun.py.command-injection - trusted operator input only'
  echo 'subprocess.run(h, shell=True)  # nosemgrep - trusted operator input only'; } >src/run.py
K2="AK"; K2+="IA9876543210ZYXWVU"
printf 'a = 1\nurl = "https://files.example.com/o?X-Amz-Credential=%s%%2F20260101%%2Fs3" ; other = "%s"\nurl = "https://files.example.com/o?X-Amz-Credential=%s%%2F1%%2Fs3" ; same = "%s"\n' "$KID" "$K2" "$KID" "$KID" >src/presign2.py
{ echo 'name: acme'; echo 'on: push'; echo 'jobs:'; echo '  b:'; echo '    strategy:'; echo '      matrix: ${{ fromJSON(needs.plan.outputs.m) }}'
  echo '    steps:'; echo '      - run: echo ${{ matrix.os }}'; } >.github/workflows/dyn.yml
{ echo 'name: acme'; echo 'on: push'; echo 'jobs:'; echo '  b:'; echo '    runs-on: ubuntu-latest'; echo '    steps:'
  echo '      - run: echo ${{ matrix.os }} ${{ github.sha }} ${{ github.event.pull_request.head.sha }}'
  echo '      - run: echo ${{ steps.x.outputs.sha }}'
  echo '      - run: echo ${{ matrix.os }} ${{ github.event.pull_request.title }}'
  echo '      - run: echo ${{ inputs.sha }}'
  echo '      - run: echo ${{ github.event.inputs.sha }}'
  echo '      - run: echo ${{ github.event.client_payload.sha }}'; } >.github/workflows/ci.yml
{ echo 'name: acme'; echo 'on: push'; echo 'jobs:'; echo '  b:'; echo '    strategy:'; echo '      matrix:'; echo '        os: ${{ github.head_ref }}'
  echo '    steps:'; echo '      - run: echo ${{ matrix.os }}'; } >.github/workflows/dyn2.yml
g add -A; g commit -q -m change
python3 - "$T" <<'PY'
import json, sys
t = sys.argv[1]
json.dump([{"RuleID": "aws-access-token", "Description": "d", "File": f, "StartLine": n, "Fingerprint": f"fp{f}{n}", "Secret": "x", "Match": "x"} for f, n in (("src/presign.py", 2), ("src/presign.py", 3), ("src/presign2.py", 2), ("src/presign2.py", 3))], open(t + "/gl.json", "w"))
sg = lambda n: {"check_id": "python.lang.security.audit.subprocess-shell-true", "path": "src/run.py", "start": {"line": n}, "extra": {"message": "shell true"}}
tg = lambda n: {"check_id": "perun.py.command-injection", "path": "src/run.py", "start": {"line": n}, "extra": {"message": "taint"}}
b = lambda n: {"filename": "./src/run.py", "line_number": n, "test_id": "B602", "issue_text": "stub"}
s = lambda n: {"filename": "./src/run.py", "location": {"row": n}, "code": "S602", "message": "stub"}
json.dump({"results": [sg(n) for n in (2, 3, 4, 5, 6)] + [tg(n) for n in (7, 8, 9)], "errors": [], "paths": {"scanned": ["src/run.py"]}}, open(t + "/sg.json", "w"))
json.dump({"results": [b(n) for n in (2, 3, 4, 5, 6)]}, open(t + "/b.json", "w"))
json.dump([s(n) for n in (2, 3, 4, 5, 6)], open(t + "/r.json", "w"))
z = lambda row, f=".github/workflows/ci.yml": {"ident": "template-injection", "desc": "d", "locations": [{"symbolic": {"kind": "Primary", "key": {"Local": {"verbatim_path": f}}}, "concrete": {"location": {"start_point": {"row": row}}}}]}
json.dump([z(6), z(7), z(8), z(9), z(10), z(11), z(7, ".github/workflows/dyn.yml"), z(8, ".github/workflows/dyn2.yml")], open(t + "/zz.json", "w"))
PY
out=$(bash "$RC" --full 2>"$T/err" || true)
[ -z "${DBG:-}" ] || { python3 -c 'import json,sys; [print(x["tool"], x["file"], x["line"], x["rule"], x.get("hint"), x["message"][:100]) for x in json.load(sys.stdin)]' <<<"$out"; cat "$T/err"; }
q() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); at=lambda f,l,t=None: [x for x in r if x["file"].removeprefix("./")==f and x["line"]==l and x["rule"]!="not-checked" and (t is None or x["tool"]==t)]; '"$1" <<<"$out"; }
r=0; q 'k=at("src/presign.py",2,"gitleaks"); sys.exit(0 if len(k)==1 and k[0].get("hint")=="non-secret-lead" and "non-secret-lead" in k[0]["message"] and "low" in k[0]["message"] else 1)' || r=$?; chk $r "aws key in presigned X-Amz-Credential URL: row kept, tagged non-secret-lead low"
r=0; q 'k=at("src/presign.py",3,"gitleaks"); sys.exit(0 if len(k)==1 and k[0].get("hint")!="non-secret-lead" and "non-secret" not in k[0]["message"] else 1)' || r=$?; chk $r "bare aws key line is untouched"
r=0; q 'k=at("src/run.py",2); sys.exit(0 if len(k)==1 and k[0].get("hint")=="suppressed-with-reason" and "suppressed-with-reason" in k[0]["message"] and len(k[0].get("also",[]))==2 else 1)' || r=$?; chk $r "noqa+nosec with reason: semgrep+bandit+ruff collapse to one suppressed-with-reason row naming the twins"
r=0; q 'k=at("src/run.py",2); sys.exit(0 if k and "low" in k[0]["message"] else 1)' || r=$?; chk $r "collapsed row is marked low"
r=0; q 'k=at("src/run.py",5); b=[x for x in k if x["tool"]=="bandit"]; sg=[x for x in k if x["tool"]=="semgrep"]; sys.exit(0 if len(b)==1 and b[0].get("hint")=="suppressed-with-reason" and len(sg)==1 and "hint" not in sg[0] else 1)' || r=$?; chk $r "noqa: S602 with reason covers the ruff/bandit row, not the semgrep row"
r=0; q 'k=at("src/run.py",6); sys.exit(0 if len(k)>=2 and all("hint" not in x and "suppressed" not in x["message"] for x in k) else 1)' || r=$?; chk $r "NEG: noqa: E501 with reason does not suppress a shell=True row"
r=0; q 'k=at("src/presign2.py",2,"gitleaks"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "non-secret" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: a different key on the same line as a presigned URL is not tagged"
r=0; q 'k=at("src/presign2.py",3,"gitleaks"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "non-secret" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: the same key repeated outside the presigned URL is not tagged"
for ln in 10 11 12; do r=0; q 'k=at(".github/workflows/ci.yml",'$ln',"zizmor"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "downranked" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: attacker-controlled *.sha (ci.yml line $ln) stays as it was"; done
r=0; q 'k=at(".github/workflows/dyn.yml",8,"zizmor"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "downranked" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: matrix.* with a fromJSON-built matrix stays as it was"
r=0; q 'k=at(".github/workflows/dyn2.yml",9,"zizmor"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "downranked" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: matrix.* whose matrix block holds a \${{ }} expression stays as it was"
r=0; q 'k=at("src/run.py",7,"semgrep"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "suppressed" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: bare # nosec with a reason does not downrank a semgrep taint command-injection row"
r=0; q 'k=at("src/run.py",8,"semgrep"); sys.exit(0 if len(k)==1 and k[0].get("hint")=="suppressed-with-reason" else 1)' || r=$?; chk $r "nosemgrep naming the taint rule id with a reason still downranks it"
r=0; q 'k=at("src/run.py",9,"semgrep"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "suppressed" not in k[0]["message"] else 1)' || r=$?; chk $r "NEG: bare nosemgrep with a reason keeps a semgrep taint row and does not crash"
r=0; q 'k=at("src/run.py",3); sys.exit(0 if len(k)>=2 and all(x.get("hint")!="suppressed-with-reason" for x in k) else 1)' || r=$?; chk $r "bare # nosec (no reason) keeps its rows"
r=0; q 'k=at("src/run.py",4); sys.exit(0 if len(k)>=2 and all(x.get("hint")!="suppressed-with-reason" for x in k) else 1)' || r=$?; chk $r "unsuppressed shell=True keeps its rows"
r=0; q 'k=at(".github/workflows/ci.yml",7,"zizmor"); sys.exit(0 if len(k)==1 and k[0].get("hint")=="low-risk-context" and "downranked" in k[0]["message"] else 1)' || r=$?; chk $r "matrix/sha-only expressions: zizmor row kept, downranked low"
r=0; q 'k=at(".github/workflows/ci.yml",8,"zizmor"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "downranked" not in k[0]["message"] else 1)' || r=$?; chk $r "step output expression stays as it was"
r=0; q 'k=at(".github/workflows/ci.yml",9,"zizmor"); sys.exit(0 if len(k)==1 and "hint" not in k[0] and "downranked" not in k[0]["message"] else 1)' || r=$?; chk $r "one attacker-controlled expression among safe ones stays as it was"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
