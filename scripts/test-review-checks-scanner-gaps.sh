#!/usr/bin/env bash
# review_checks.sh scanner gaps: each block is a way a finding was dropped or mislabelled, or a run read as clean. Stub tools on a
# hermetic PATH and synthetic fixtures only, so it runs offline anywhere. Blocks:
#  zizmor     a ./-prefixed path still lands on the changed file; a row for an unscanned file is NOT RUN, never a silent clean
#  big-list   --full with a file list larger than a pipe buffer keeps gitleaks and trivy findings
#  osv        an exported osv-scanner cache dir holding a seeded DB runs offline by default; an empty one stays opt-in
#  actionlint workflow files are routed to actionlint
#  empty diff exit 0, `[]`, and a line saying nothing was scanned
#  semgrep    errors with no findings on one chunk or file are partial when other files scanned, not a voided tool
#  rows       checkov and grype rows keep rule id, line and message
#  rule ids   semgrep rule ids lose the local config-directory prefix, for the bundled rules and the provisioned p/default snapshot
#  grype      routed to SBOM-like names only
#  checkov    the flat "nothing to check" summary is clean; compose files are not routed to it
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the fixes).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/gaps.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_SEMGREP_REGISTRY REVIEW_TRIVY_CACHE REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # hermetic: a provisioned host cache or ~/.local/bin must not change which branch runs
n=0 fail=0
t() { local d=$1; shift; n=$((n + 1)); if "$@" >/dev/null 2>&1; then echo "ok - $d"; else echo "FAIL - $d"; fail=$((fail + 1)); fi; }
not() { ! "$@"; }
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
stub() { mkdir -p "$1"; cat >"$1/$2"; chmod +x "$1/$2"; } # stub DIR NAME < script
# Hermetic PATH: stub dir plus $T/sys (symlinks to only the system binaries review_checks.sh needs), never the host PATH.
mkdir -p "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
newrepo() { # newrepo NAME: fresh repo under $T with an empty commit tagged `base`; leaves cwd inside it
  mkdir -p "$T/$1" && cd "$T/$1" && git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
  G commit -q --allow-empty -m base && git branch base
}
commit() { G add -A && G commit -q -m change; }
run() { # run STUBDIR [args]: stdout -> $T/out, stderr -> $T/err, exit code -> RCODE (env assignments before the call reach the script)
  local d=$1; shift; RCODE=0
  PATH="$d:$T/sys" PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 bash "$RC" "$@" >"$T/out" 2>"$T/err" || RCODE=$?
}
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out"; } # row TOOL FILE RULE
errhas() { grep -qE -- "$1" "$T/err"; }
ran() { errhas "analyzers ran:.*\\b$1\\b"; }

# --- zizmor: scanners echo the path they were given ("./.github/..."); the row must carry the changed-file form
newrepo zizmor; mkdir -p .github/workflows; echo 'on: push' >.github/workflows/ci.yml; commit
stub "$T/b-zizmor" zizmor <<'S'
#!/usr/bin/env bash
printf '[{"ident":"template-injection","desc":"injectable template","locations":[{"symbolic":{"key":{"Local":{"verbatim_path":"%s"}}},"concrete":{"location":{"start_point":{"row":4}}}}]}]\n' "${ZZ_PATH:-./.github/workflows/ci.yml}"
exit 13
S
run "$T/b-zizmor" --base base
t "zizmor: ./-prefixed path becomes a row on the changed file" row zizmor .github/workflows/ci.yml template-injection
t "zizmor: row line is 1-based" jq -e 'any(.[]; .tool=="zizmor" and .line==5)' "$T/out"
t "zizmor: listed as ran" ran zizmor
ZZ_PATH=./.github/workflows/other.yml run "$T/b-zizmor" --base base
t "zizmor: a row for an unscanned file is NOT RUN" errhas 'NOT RUN:.*zizmor'
t "zizmor: ...with a not-checked row" row zizmor "" not-checked
t "zizmor: ...and not listed as ran" not ran zizmor

# --- big list: a `printf list | grep -q` that matches early SIGPIPEs the writer; under pipefail the match was dropped
newrepo biglist; mkdir aaa pad
echo x >aaa/leak.txt; echo x >aaa/notes.txt
python3 - <<'PY'
for i in range(3000):
    open(f"pad/{i:04d}-" + "p" * 60 + ".txt", "w").write("x\n")
PY
commit
t "big-list: tracked file list is larger than any pipe buffer" test "$(git ls-files | wc -c | tr -d ' ')" -gt 200000
stub "$T/b-big" gitleaks <<'S'
#!/usr/bin/env bash
r=; while [ $# -gt 0 ]; do [ "$1" != -r ] || r=$2; shift; done
printf '[{"File":"aaa/leak.txt","RuleID":"generic-api-key","StartLine":2,"Description":"d","Secret":"fake-secret-value","Fingerprint":"aaa/leak.txt:generic-api-key:2"}]' >"$r"
S
stub "$T/b-big" trivy <<'S'
#!/usr/bin/env bash
echo '{"Results":[{"Target":"aaa/notes.txt","Vulnerabilities":[{"VulnerabilityID":"CVE-2000-0001","PkgName":"p","InstalledVersion":"1","Title":"t"}]}]}'
S
run "$T/b-big" --full --timeout 60
t "big-list: --full keeps the gitleaks finding" row gitleaks aaa/leak.txt generic-api-key
t "big-list: --full keeps the trivy finding" row trivy aaa/notes.txt CVE-2000-0001

# --- osv: an operator-seeded cache dir (exported env) runs offline; no other location is guessed
newrepo osv; echo '{}' >package-lock.json; commit
mkdir -p "$T/osvdb/osv-scanner/npm" "$T/osvempty"; echo x >"$T/osvdb/osv-scanner/npm/all.zip"
stub "$T/b-osv" osv-scanner <<'S'
#!/usr/bin/env bash
echo "$*" >>"$OSV_LOG"
echo '{"results":[{"source":{"path":"x"},"packages":[{"package":{"name":"left-pad","version":"1.0.0"},"vulnerabilities":[{"id":"GHSA-test-0001","summary":"bad pad"}]}]}]}'
exit 1
S
export OSV_LOG=$T/osv.log
: >"$OSV_LOG"; OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$T/osvdb run "$T/b-osv" --base base
t "osv: seeded cache dir runs osv-scanner offline" grep -q -- '--offline-vulnerabilities' "$OSV_LOG"
t "osv: ...and its finding is reported" row osv-scanner package-lock.json GHSA-test-0001
t "osv: ...and it is listed as ran" ran osv-scanner
: >"$OSV_LOG"; OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$T/osvempty run "$T/b-osv" --base base
t "osv: cache dir without a database stays opt-in: NOT RUN" errhas 'NOT RUN:.*osv-scanner \(REVIEW_OSV not set'
t "osv: ...and osv-scanner is not called" test ! -s "$OSV_LOG"
: >"$OSV_LOG"; run "$T/b-osv" --base base
t "osv: no env at all stays opt-in: NOT RUN" errhas 'NOT RUN:.*osv-scanner \(REVIEW_OSV not set'
: >"$OSV_LOG"; REVIEW_OSV=1 OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$T/osvdb run "$T/b-osv" --base base
t "osv: REVIEW_OSV=1 still asks the API (osv-scanner called)" test -s "$OSV_LOG"
t "osv: ...without the offline flag" not grep -q -- '--offline-vulnerabilities' "$OSV_LOG"

# --- actionlint: workflow files are routed (flags: actionlint -h, exit 1 = findings)
newrepo actionlint; mkdir -p .github/workflows; echo 'on: push' >.github/workflows/ci.yml; commit
stub "$T/b-al" actionlint <<'S'
#!/usr/bin/env bash
echo "$*" >>"$AL_LOG"
[ -z "${AL_CLEAN:-}" ] || { echo '[]'; exit 0; }
echo '[{"message":"unexpected key","filepath":"./.github/workflows/ci.yml","line":7,"column":3,"kind":"syntax-check","snippet":"x","end_column":4}]'
exit 1
S
export AL_LOG=$T/al.log; : >"$AL_LOG"
run "$T/b-al" --base base
t "actionlint: finding becomes a row on the changed file" row actionlint .github/workflows/ci.yml syntax-check
t "actionlint: row keeps the line" jq -e 'any(.[]; .tool=="actionlint" and .line==7)' "$T/out"
t "actionlint: asked for JSON on the workflow file" grep -qF -- "-format {{json .}} ./.github/workflows/ci.yml" "$AL_LOG"
t "actionlint: listed as ran" ran actionlint
AL_CLEAN=1 run "$T/b-al" --base base
t "actionlint: [] is clean and listed as ran" ran actionlint
t "actionlint: ...with no row" not jq -e 'any(.[]; .tool=="actionlint")' "$T/out"
run "$T/b-none" --base base
t "actionlint: missing tool prints NOT CHECKED" errhas '^NOT CHECKED: actionlint \(install: .+\)'

# --- empty diff: set -e used to kill the run silently (grep -c exits 1 at a count of 0)
newrepo empty
run "$T/b-none" --base base
t "empty diff: exit 0" test "$RCODE" = 0
t "empty diff: stdout is []" jq -e 'length == 0' "$T/out"
t "empty diff: says nothing was scanned" errhas '0 files in diff'
t "empty diff: still prints the summary line" errhas 'review_checks: 0 findings'
mkdir vendor; echo x >vendor/a.js; commit
run "$T/b-none" --base base
t "only excluded paths: exit 0" test "$RCODE" = 0
t "only excluded paths: stdout is []" jq -e 'length == 0' "$T/out"
t "only excluded paths: summary counts the excluded file" errhas 'review_checks: 0 findings; 1 files excluded'

# --- semgrep: errors and no findings on a chunk voided the whole tool, even when other chunks scanned fine
newrepo sgchunks; mkdir f; python3 - <<'PY'
for i in range(230):
    open(f"f/{i:03d}.txt", "w").write("x\n")
PY
commit
stub "$T/b-sg" semgrep <<'S'
#!/usr/bin/env bash
n=$(( $(cat "$SG_DIR/n" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$SG_DIR/n"
cat "$SG_DIR/$n.json"
S
SG_DIR=$T/sg1; mkdir -p "$SG_DIR"
echo '{"results":[],"errors":[{"path":"f/000.txt","level":"warn","type":"Syntax error"}],"paths":{"scanned":["f/000.txt"]}}' >"$SG_DIR/1.json"
echo '{"results":[{"check_id":"perun.js.sqli","path":"f/229.txt","start":{"line":3},"extra":{"message":"tainted"}}],"errors":[],"paths":{"scanned":["f/229.txt"]}}' >"$SG_DIR/2.json"
SG_DIR=$SG_DIR REVIEW_SEMGREP_REGISTRY=0 run "$T/b-sg" --base base
t "semgrep: 2 chunks, first errored with no findings: finding of the second is kept" row semgrep f/229.txt perun.js.sqli
t "semgrep: ...tool is not voided (no NOT RUN)" not errhas 'NOT RUN:.*semgrep'
t "semgrep: ...still listed as ran" ran semgrep
t "semgrep: ...partial coverage is said on stderr" errhas 'partial: semgrep errored with no findings on 1 chunk'
t "semgrep: ...and is a not-checked row" row semgrep "" not-checked
newrepo sgfiles; echo x >a.txt; echo x >b.txt; commit
SG_DIR=$T/sg2; mkdir -p "$SG_DIR"
echo '{"results":[],"errors":[{"path":"a.txt","level":"warn","type":"Syntax error"}],"paths":{"scanned":["a.txt","b.txt"]}}' >"$SG_DIR/1.json"
SG_DIR=$SG_DIR REVIEW_SEMGREP_REGISTRY=0 run "$T/b-sg" --base base
t "semgrep: errors on 1 of 2 scanned files and no findings is partial, not NOT RUN" not errhas 'NOT RUN:.*semgrep'
t "semgrep: ...said as partial" errhas 'partial: semgrep ran but reported errors'
t "semgrep: ...and listed as ran" ran semgrep
SG_DIR=$T/sg3; mkdir -p "$SG_DIR"
echo '{"results":[],"errors":[{"path":"a.txt","level":"warn","type":"x"},{"path":"b.txt","level":"warn","type":"x"}],"paths":{"scanned":["a.txt","b.txt"]}}' >"$SG_DIR/1.json"
SG_DIR=$SG_DIR REVIEW_SEMGREP_REGISTRY=0 run "$T/b-sg" --base base
t "semgrep: every scanned file errored and no findings stays NOT RUN" errhas 'NOT RUN:.*semgrep \(scan errored, no findings\)'

# --- rows: the caller reads TSV with an IFS-whitespace tab, which collapsed the empty leading file field and shifted every column
newrepo rows; printf 'FROM alpine\nRUN true\nCMD true\n' >Dockerfile; echo '{}' >sbom.json; commit
stub "$T/b-rows" checkov <<'S'
#!/usr/bin/env bash
echo '{"check_type":"dockerfile","results":{"failed_checks":[{"check_id":"CKV_EXAMPLE_1","check_name":"Ensure that the example check passes","file_line_range":[3,3]}]}}'
S
stub "$T/b-rows" grype <<'S'
#!/usr/bin/env bash
echo '{"matches":[{"vulnerability":{"id":"CVE-2000-0001","description":"synthetic advisory"},"artifact":{"name":"pkg","version":"1.0.0"}}]}'
S
run "$T/b-rows" --base base
t "rows: checkov rule is the check id" row checkov Dockerfile CKV_EXAMPLE_1
t "rows: checkov line is kept" jq -e 'any(.[]; .tool=="checkov" and .line==3)' "$T/out"
t "rows: checkov message is the check name" jq -e 'any(.[]; .tool=="checkov" and (.message|test("example check")))' "$T/out"
t "rows: grype rule is the vulnerability id" row grype sbom.json CVE-2000-0001
t "rows: grype message is the package and description" jq -e 'any(.[]; .tool=="grype" and (.message|test("^pkg@1.0.0: synthetic")))' "$T/out"

# --- rule ids: semgrep prefixes ids with the dotted directory of the config file; that local path must not reach the report
stub "$T/b-rid" semgrep <<'S'
#!/usr/bin/env python3
# Stands in for semgrep: one finding per local --config, id = dotted directory of that config + its rule id (rule_lang.convert_config_id_to_prefix).
# A registry pack (p/default) is no local path, so it adds no finding; the provisioned snapshot (p-default.yml) defines its own rule id.
import json, pathlib, re, sys
a = sys.argv[1:]
res = []
for c in [a[i + 1] for i, x in enumerate(a) if x == "--config"]:
    p = pathlib.Path(c)
    if not p.exists(): continue
    rid = "python.lang.demo-eval" if p.name == "p-default.yml" else "perun.js.sqli"
    if p.is_dir(): p = p / "rules.yml"
    try: p = p.relative_to(pathlib.Path.cwd())
    except ValueError: pass
    s = ".".join(p.parts[:-1]).lstrip("./").lstrip(".")
    res.append({"check_id": re.sub(r"[^a-zA-Z0-9._-]", "", s + "." if s else "") + rid, "path": "app.txt", "start": {"line": 1}, "extra": {"message": "tainted"}})
print(json.dumps({"results": res, "errors": [], "paths": {"scanned": ["app.txt"]}}))
S
newrepo ruleid; echo x >app.txt; mkdir -p rules/sub; echo 'rules: []' >rules/team.yml; echo 'rules: []' >.semgrep.yml; commit
REVIEW_SEMGREP_REGISTRY=0 run "$T/b-rid" --base base
t "rule ids: .semgrep.yml at the repo root (no prefix) is untouched" row semgrep app.txt perun.js.sqli
git rm -q --cached .semgrep.yml; rm .semgrep.yml; commit
REVIEW_SEMGREP_REGISTRY=0 run "$T/b-rid" --base base
t "rule ids: bundled rules directory prefix is stripped" row semgrep app.txt perun.js.sqli
REVIEW_SEMGREP_CONFIG=rules/team.yml run "$T/b-rid" --base base
t "rule ids: relative config file prefix is stripped" row semgrep app.txt perun.js.sqli
REVIEW_SEMGREP_CONFIG=rules run "$T/b-rid" --base base
t "rule ids: relative config directory prefix is stripped" row semgrep app.txt perun.js.sqli
REVIEW_SEMGREP_CONFIG=$PWD/rules/team.yml run "$T/b-rid" --base base
t "rule ids: absolute config file prefix is stripped" row semgrep app.txt perun.js.sqli
# warm snapshot: provision_tools.sh --cache semgrep prints a local file, loaded as a second --config, so its ids carry that file's directory
mkdir -p "$T/warm/dcr-tools/semgrep"; printf 'rules:\n- id: python.lang.demo-eval\n' >"$T/warm/dcr-tools/semgrep/p-default.yml"
DCR_CACHE_ROOT=$T/warm run "$T/b-rid" --base base
t "rule ids: provisioned snapshot prefix is stripped" row semgrep app.txt python.lang.demo-eval
t "rule ids: ...and the bundled rules still are" row semgrep app.txt perun.js.sqli
t "rule ids: ...no row keeps the snapshot directory" not jq -e 'any(.[]; .tool=="semgrep" and (.rule|contains("dcr-tools")))' "$T/out"

# --- grype: SBOM-like names only (the old pattern matched any file name containing "bom")
newrepo grype; for f in bomb.json kaboom.json sbom.json bom.json app.cdx.json release-spdx.json; do echo '{}' >"$f"; done; commit
stub "$T/b-grype" grype <<'S'
#!/usr/bin/env bash
echo "$1" >>"$GR_LOG"
echo '{"matches":[]}'
S
export GR_LOG=$T/gr.log; : >"$GR_LOG"
run "$T/b-grype" --base base
for f in sbom.json bom.json app.cdx.json release-spdx.json; do t "grype: $f is scanned" grep -qxF "sbom:./$f" "$GR_LOG"; done
t "grype: bomb.json and kaboom.json are not" not grep -qE 'bomb|kaboom' "$GR_LOG"

# --- checkov: a file with nothing to check prints a flat summary with no "results"; compose is not a checkov framework
newrepo checkov; echo 'variable "x" {}' >variables.tf; echo 'services: {}' >docker-compose.yml; commit
stub "$T/b-ck" checkov <<'S'
#!/usr/bin/env bash
echo "$*" >>"$CK_LOG"
printf '{"passed": 0, "failed": 0, "skipped": 0, "parsing_errors": %s, "resource_count": 0, "checkov_version": "0.0.0"}\n' "${CK_PARSE:-0}"
S
export CK_LOG=$T/ck.log; : >"$CK_LOG"
run "$T/b-ck" --base base
t "checkov: flat summary with nothing to check is clean (no not-run)" not errhas 'not run: checkov'
t "checkov: ...and listed as ran" ran checkov
t "checkov: ...with no row" not jq -e 'any(.[]; .tool=="checkov")' "$T/out"
t "checkov: compose file is not routed to it" not grep -q 'docker-compose' "$CK_LOG"
t "checkov: the Terraform file is" grep -q 'variables.tf' "$CK_LOG"
CK_PARSE=1 run "$T/b-ck" --base base
t "checkov: a flat summary reporting a parse error stays NOT RUN" errhas 'not run: checkov'
echo "Tests: $((n - fail))/$n"
[ "$fail" = 0 ]
