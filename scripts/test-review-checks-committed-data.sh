#!/usr/bin/env bash
# Tests for review_checks.sh's built-in committed-data step (committed_personal_data.py): a CSV and a binary-ish file with 12 distinct
# made-up-domain addresses give one email-addresses row each (counts only, never an address; no likely-fixture hint or tag); 9 addresses,
# reserved example.com names and vendor/, node_modules/, third_party/, Pods/ and *.min.js files give none; a small parquet-like file
# gives a not-checked row; six files of 9 addresses each, none reaching the threshold, give one repository-total row (path ".");
# diff mode flags only changed files and --full all tracked files; the step is listed under "analyzers ran"; a missing script gives
# one not-checked row. Hermetic: temp git repo, pruned PATH, fictional data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcpd.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

mkdir "$T/bin" "$T/nopd" "$T/repo"
# Pruned PATH: no semgrep, trivy or linters, so the run is offline and only built-in steps fire.
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc sleep timeout; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
cp "$RC" "$T/nopd/review_checks.sh"  # no committed_personal_data.py beside it
# mk KIND DOMAIN N PATH: N distinct fictional addresses as a CSV or as a parquet-like binary (magic, length-prefixed values, NUL padding).
mk() { python3 - "$@" <<'PY'
import sys
kind, domain, n, path = sys.argv[1], sys.argv[2].encode(), int(sys.argv[3]), sys.argv[4]
a = [b"fixture-user-%04d@%s" % (i, domain) for i in range(1, n + 1)]
if kind == "csv":
    data = b"id,name,email\n" + b"".join(b"%d,Jane Smith,%s\n" % (i, x) for i, x in enumerate(a))
else:
    data = b"PAR1" + b"".join(len(x).to_bytes(4, "little") + x for x in a) + b"\0" * 64 + b"PAR1"
open(path, "wb").write(data)
PY
}
cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m empty
mk csv acme.zz 12 old.csv
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m old
git branch base
mkdir -p third_party Pods vendor node_modules spread lib tests/fixtures
mk csv acme.zz 12 report.csv
mk bin acme.zz 12 export.parquet
mk csv acme.zz 10 ten.csv
mk csv acme.zz 9 nine.csv
mk csv example.com 12 reserved.csv
mk csv acme.zz 12 third_party/vendored.csv
mk csv acme.zz 12 tests/fixtures/people.csv
mk csv acme.zz 12 Pods/people.csv
mk csv acme.zz 12 vendor/people.csv
mk csv acme.zz 12 node_modules/people.csv
mk csv acme.zz 12 lib/app.min.js
mk bin acme.zz 5 small.parquet
for i in 1 2 3 4 5 6; do mk csv "spread$i.zz" 9 "spread/s$i.csv"; done  # 6 domains x 9 addresses: no file reaches 10
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export PERUN_HEAVY_DIR="$T/heavy"
PATH="$T/bin" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
rows() { jq -r '[.[] | select(.tool=="committed-data") | .file] | sort | join(" ")' "$1"; }

[ "$(rows "$T/out")" = ". export.parquet report.csv small.parquet ten.csv tests/fixtures/people.csv" ] && ok "csv and binary flagged; 9 addresses, reserved names, vendored paths and unchanged files are not" || bad "row files: $(rows "$T/out")"
jq -e '[.[] | select(.tool=="committed-data" and .file=="report.csv")] | length == 1 and all(.[]; .rule=="email-addresses" and .line==0 and .message=="12 distinct email addresses (threshold 10); of 12 counting reserved names, 12 with placeholder-style local parts, 0 on reserved domains" and .text=="email-addresses: " + .message)' "$T/out" >/dev/null && ok "row shape: rule, count, fixture signals, text" || bad "row shape"
jq -e 'any(.[]; .tool=="committed-data" and .file=="ten.csv" and (.message|startswith("10 distinct")))' "$T/out" >/dev/null && ok "threshold edge: 10 flagged" || bad "ten.csv row"
jq -e '[.[] | select(.tool=="committed-data")] | length == 6 and all(.[]; (has("hint")|not) and (.text|contains("likely-fixture")|not))' "$T/out" >/dev/null && ok "fixture-path row carries no likely-fixture hint or tag (its message may lead with the content-based label)" || bad "fixture tag"
jq -e '[.[] | select(.tool=="committed-data" and .file==".")] | length == 1 and .[0].rule=="email-addresses" and .[0].line==0 and .[0].message=="63 distinct email addresses across 8 file(s) that each stay below the file threshold 10 (repository threshold 50; --threshold 1 lists the files)"' "$T/out" >/dev/null && ok "addresses spread thin give one repository-total row" || bad "repository-total row"
jq -e '[.[] | select(.tool=="committed-data" and .file=="small.parquet")] | length == 1 and .[0].rule=="not-checked" and (.[0].message|contains("compressed/columnar container (parquet)"))' "$T/out" >/dev/null && ok "small parquet under the threshold is a not-checked row, not a clean pass" || bad "container row"
jq -e 'any(.[]; .tool=="committed-data")' "$T/out" >/dev/null && ! grep -Eq '@|fixture-user|acme|\.zz' "$T/out" "$T/err" && ok "no address, local part or domain in stdout or stderr" || bad "value leaked, or no committed-data rows to check"
grep -Eq 'analyzers ran:.* committed-data' "$T/err" && ok "listed under analyzers ran" || bad "analyzers ran"
jq -e 'any(.[]; .tool=="committed-data") and all(.[]; has("file") and has("line") and has("rule") and has("message") and has("text") and has("tool"))' "$T/out" >/dev/null && ok "existing row shape" || bad "row shape (all rows)"

PATH="$T/bin" bash "$RC" --base base --full 2>"$T/err1" >"$T/out1" || true
[ "$(rows "$T/out1")" = ". export.parquet old.csv report.csv small.parquet ten.csv tests/fixtures/people.csv" ] && ok "--full also flags the file committed before base" || bad "full row files: $(rows "$T/out1")"

PATH="$T/bin" bash "$T/nopd/review_checks.sh" --base base 2>"$T/err2" >"$T/out2" || true
jq -e '[.[] | select(.tool=="committed-data")] | length == 1 and .[0].rule=="not-checked" and .[0].file=="" and (.[0].message|contains("committed_personal_data.py missing"))' "$T/out2" >/dev/null && ok "script missing gives one not-checked row" || bad "missing-script row"
grep -q 'not run: committed-data' "$T/err2" && ! grep -Eq 'analyzers ran:.* committed-data' "$T/err2" && ok "missing script reported on stderr, not listed as ran" || bad "missing-script stderr"

[ "$fail" = 0 ]
