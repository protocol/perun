#!/usr/bin/env bash
# review_checks.sh --full (whole repo against git's empty tree, one batched gitleaks run) and .gitleaksignore. Stub gitleaks
# on PATH emits fixed JSON, so the cases run anywhere. Covers: full mode scans an untouched file in a single spawn; diff mode
# still skips it; a .gitleaksignore fingerprint suppresses a finding (diff and full) while another stays; an entry added by
# the change is not applied; a missing scanner yields a not-checked row, never a clean `[]`.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-full.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/gitleaks" <<'STUB'
#!/usr/bin/env python3
# One finding per scanned file: -s . scans every regular file of the working tree, -s ./f just that file.
import json, os, sys
a = sys.argv[1:]
rep, src = a[a.index("-r") + 1], a[a.index("-s") + 1].removeprefix("./")
open(os.environ["STUB_LOG"], "a").write(src + "\n")
if os.environ.get("STUB_FAIL"): sys.exit(2)
fs = [os.path.join(d, f)[2:] for d, ds, n in os.walk(".") if ".git" not in d.split(os.sep) for f in n] if src in ("", ".") else [src]
json.dump([{"File": f, "RuleID": "generic-api-key", "StartLine": 1, "Description": "d", "Secret": "fake-secret-value",
            "Fingerprint": f"{f}:generic-api-key:1"} for f in fs], open(rep, "w"))
STUB
chmod +x "$T/bin/gitleaks"; export STUB_LOG="$T/log"
cd "$T"; mkdir r; cd r; g init -q .
echo old >old.txt; g add -A; g commit -q -m base; git branch -f base
echo new >new.txt; g add -A; g commit -q -m change
run() { PATH="$T/bin:$PATH" bash "$RC" "$@" 2>"$T/err" || true; }
has() { grep -q "\"file\": \"$1\"" <<<"$out"; }
: >"$T/log"; out=$(run --base base); has new.txt && ! has old.txt; chk $? "diff mode scans only changed files"
: >"$T/log"; out=$(run --full); has new.txt && has old.txt; chk $? "--full scans an untouched file"
[ "$(wc -l <"$T/log")" -eq 1 ] && grep -qx . "$T/log"; chk $? "--full spawns gitleaks once over the working tree"
printf '# c\nold.txt:generic-api-key:1\n' >.gitleaksignore; g add -A; g commit -q -m ignore
out=$(run --full); ! has old.txt && has new.txt; chk $? ".gitleaksignore suppresses its fingerprint in --full"
git branch -f base2 HEAD~1; echo more >new2.txt; g add -A; g commit -q -m more
out=$(run --base base2); ! has old.txt && has new2.txt; chk $? ".gitleaksignore honoured in diff mode, other findings kept"
echo '{}' >edit.txt; printf 'edit.txt:generic-api-key:1\n' >>.gitleaksignore; g add -A; g commit -q -m selfapprove
out=$(run --base HEAD~1); has edit.txt; chk $? "ignore entry added by the change itself is not applied"
# working-tree ignore (uncommitted) must not suppress; non-ASCII name caught in --full; run failure -> not-checked
printf 'new.txt:generic-api-key:1\n' >>.gitleaksignore
r=0; out=$(run --full); has new.txt || r=1; chk $r "uncommitted working-tree .gitleaksignore does not suppress"
git checkout -q .gitleaksignore
echo x >"é.txt"; g add -A; g commit -q -m nonascii
E='\\u00e9.txt' # json.dumps escapes non-ASCII
r=0; out=$(run --full); has "$E" || r=1; chk $r "--full catches a non-ASCII filename"
out=$(STUB_FAIL=1 run --full); grep -q '"rule": "not-checked"' <<<"$out" && grep -q '"tool": "gitleaks"' <<<"$out"; chk $? "--full run failure: not-checked row"
r=0; out=$(run --base base2); { has new2.txt && has "$E" && ! has old.txt; } || r=1; chk $r "diff mode output unchanged"
# fail closed: hide the stub and any real gitleaks -> a not-checked row for gitleaks, so the verdict is not a clean []
out=$(PATH="/usr/bin:/bin" bash "$RC" --full 2>"$T/err" || true)
if ! PATH="/usr/bin:/bin" sh -c 'command -v gitleaks' >/dev/null; then
  grep -q '"rule": "not-checked"' <<<"$out" && grep -q '"tool": "gitleaks"' <<<"$out" && [ "$(tr -d ' \n' <<<"$out")" != "[]" ]; chk $? "missing scanner: not-checked row, non-clean verdict"
else chk 0 "missing scanner (skipped: real gitleaks on the minimal PATH)"; fi
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
