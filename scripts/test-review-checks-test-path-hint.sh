#!/usr/bin/env bash
# review_checks.sh tags a code-pattern scanner row (semgrep, bandit, ruff, gosec, shellcheck, ...) in a test-only file with hint "test-path" and a " [test-path]" suffix.
# Shipped-looking paths (src/, docs/, examples/, *_spec.py, *_test.py, a spec/ dir outside Ruby), secret-class rules (by name or by a numeric id such as bandit B105),
# non-code tools (hadolint) and rows already hinted stay as they were; no row is dropped.
# Stub semgrep, bandit and hadolint on PATH emit fixed JSON, so the cases always run in CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-tph.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
printf '#!/usr/bin/env bash\ncat "$STUB_SG_JSON"\n' >"$T/bin/semgrep"
printf '#!/usr/bin/env bash\necho %s\n' "'{\"results\":[{\"filename\":\"tests/conf.py\",\"line_number\":1,\"test_id\":\"B105\"},{\"filename\":\"tests/b.py\",\"line_number\":1,\"test_id\":\"B307\"}],\"errors\":[]}'" >"$T/bin/bandit"
printf '#!/usr/bin/env bash\necho %s\n' "'[{\"file\":\"tests/Dockerfile\",\"line\":1,\"code\":\"DL3007\",\"level\":\"warning\",\"message\":\"latest tag\"}]'" >"$T/bin/hadolint"
chmod +x "$T/bin/"*; export PATH="$T/bin:$PATH" STUB_SG_JSON="$T/sg.json"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
FILES=(tests/a.py src/a.py tests/s.py tests/f.py test-x.mjs src/foo.test.js spec/models/user_spec.rb docs/a.py examples/a.py lib/contest.py
  app/pod_spec.py svc/ab_test.py openapi/spec/schema.py src/latest/a.py lib/latest_x.py)
for f in "${FILES[@]}" tests/Dockerfile tests/conf.py tests/b.py; do mkdir -p "$(dirname "$f")"; case "$f" in *Dockerfile) echo 'FROM alpine:latest' ;; *) echo 'x = 1' ;; esac >"$f"; done
g add -A; g commit -q -m files
# One semgrep row per file at line 1; tests/s.py carries a secret-class rule and tests/f.py a message an earlier hint already claimed.
python3 - "$STUB_SG_JSON" "${FILES[@]}" <<'PY'
import json, sys
rule = lambda f: "generic.secrets.security.detected-generic-secret" if f == "tests/s.py" else "python.lang.security.audit.eval-detected"
msg = lambda f: "eval [likely-fixture: stub]" if f == "tests/f.py" else "eval"
res = [{"check_id": rule(f), "path": f, "start": {"line": 1}, "extra": {"message": msg(f)}} for f in sys.argv[2:]]
json.dump({"results": res, "errors": [], "paths": {"scanned": sys.argv[2:]}}, open(sys.argv[1], "w"))
PY
out=$(REVIEW_SEMGREP_REGISTRY=0 bash "$RC" --base base 2>/dev/null || true)
# q TOOL FILE WANT: exactly one TOOL row for FILE; its hint is WANT ("-" = none); a test-path hint also ends message and text in " [test-path]"
q() { python3 -c '
import json, sys
r = [x for x in json.loads(sys.stdin.read()) if x["tool"] == sys.argv[1] and x["file"] == sys.argv[2]]
h = r[0].get("hint", "-") if len(r) == 1 else None
tp = h == "test-path"
sys.exit(0 if h == sys.argv[3] and r[0]["message"].endswith(" [test-path]") == tp and r[0]["text"].endswith(" [test-path]") == tp else 1)' "$@" <<<"$out"; }
for f in tests/a.py test-x.mjs src/foo.test.js spec/models/user_spec.rb; do r=0; q semgrep "$f" test-path || r=$?; chk $r "code-pattern row on a test path is hinted: $f"; done
for f in src/a.py docs/a.py examples/a.py lib/contest.py app/pod_spec.py svc/ab_test.py openapi/spec/schema.py src/latest/a.py lib/latest_x.py; do r=0; q semgrep "$f" - || r=$?; chk $r "shipped-looking path is not hinted: $f"; done
r=0; q semgrep tests/s.py - || r=$?; chk $r "secret-class rule in tests/ is not hinted"
r=0; q bandit tests/conf.py - || r=$?; chk $r "numeric secret id (bandit B105) in tests/ is not hinted"
r=0; q bandit tests/b.py test-path || r=$?; chk $r "a non-secret bandit id in tests/ is hinted"
r=0; q hadolint tests/Dockerfile - || r=$?; chk $r "non-code-pattern tool (hadolint) in tests/ is not hinted"
r=0; q semgrep tests/f.py likely-fixture || r=$?; chk $r "an already-hinted row keeps its first hint"
r=0; python3 -c 'import json,sys; sys.exit(0 if sum(x["tool"] == "semgrep" for x in json.loads(sys.stdin.read())) == int(sys.argv[1]) else 1)' "${#FILES[@]}" <<<"$out" || r=$?
chk $r "row count is unchanged: every stub semgrep row is still reported"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
