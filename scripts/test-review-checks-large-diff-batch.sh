#!/usr/bin/env bash
# review_checks.sh diff mode over REVIEW_BATCH_MIN changed files: gitleaks runs once (batched, filtered to the changed files) and
# JSON is validated in one process, with the same rows as the per-file path. Stub gitleaks and jq on PATH count their calls.
# Also: a U+0085+space filename (git quotes control chars like \x0c, so they never reach the checks), the exact REVIEW_BATCH_MIN boundary, and a PR-edited .gitleaks.toml that must not hide its own secret in batch mode (stub honors stub-allow in --config or its [extend] path).
# Covers: findings identical in both modes (a secret, an invalid JSON, a .gitleaksignore fingerprint), call counts, small diffs unchanged.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-lgb.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/gitleaks" <<'STUB'
#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[0] == "version": print("8.30.0"); sys.exit(0)
open(os.environ["STUB_COUNT"], "a").write("gitleaks\n")
rep, src = a[a.index("-r") + 1], a[a.index("-s") + 1].removeprefix("./")
ign = set(open(a[a.index("--gitleaks-ignore-path") + 1]).read().split())
al = set()
cfg = a[a.index("--config") + 1] if "--config" in a else None  # real gitleaks 8.30: a FILE source (-s ./f) loads no repo .gitleaks.toml; only --config applies
open(os.environ["STUB_COUNT"] + ".cwd", "w").write(os.getcwd())
if cfg:
    cs = [open(cfg).read()]
    for l in cs[0].splitlines():
        if l.startswith("path = "): cs.append(open(l.split('"')[1]).read())
    al = {l.split('"')[1] for c in cs for l in c.splitlines() if l.startswith("stub-allow")}
d = [r for r in json.load(open(os.environ["STUB_JSON"])) if r["Fingerprint"] not in ign and r["Secret"] not in al]
if src != ".": d = [r for r in d if r["File"] == src]
else: d = [r for r in d if os.path.exists(r["File"])]  # a dir scan sees only what is under cwd
json.dump(d, open(rep, "w"))
STUB
cat >"$T/bin/jq" <<'STUB'
#!/usr/bin/env python3
import json, os, sys
open(os.environ["STUB_COUNT"], "a").write("jq\n")
try: json.load(open(sys.argv[-1]))
except Exception as e: print(f"jq: error: invalid at line 1, column 1 ({e.__class__.__name__})"); sys.exit(2)
STUB
chmod +x "$T/bin/gitleaks" "$T/bin/jq"
export PATH="$T/bin:$PATH" STUB_JSON="$T/stub.json" STUB_COUNT="$T/count"
cd "$T"; mkdir r; cd r; g init -q .; printf 'fp-ignored\n' >.gitleaksignore; g add -A; g commit -q -m base; git branch -f base
mkdir src; for i in 1 2 3 4 5 6; do echo '{}' >src/ok$i.json; done
echo '{bad' >src/bad.json; echo 'x' >src/leak.txt; echo 'y' >src/known.txt; echo 'z' >src/clean.txt
g add -A; g commit -q -m files
python3 - >"$STUB_JSON" <<'PY'
import json
f = lambda n, fp: {"File": "src/" + n, "RuleID": "aws-access-token", "StartLine": 1, "Description": "d", "Secret": "s-" + n, "Fingerprint": fp}
print(json.dumps([f("leak.txt", "fp-leak"), f("known.txt", "fp-ignored")]))
PY
run() { : >"$STUB_COUNT"; bash "$RC" --base base 2>/dev/null || true; }
rows() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(sorted((r["tool"],r["file"],r["line"],r["rule"],r["message"]) for r in d if r["tool"] in ("gitleaks","jq")))' <<<"$1"; }
cnt() { grep -c "^$1\$" "$STUB_COUNT" || true; }
small=$(run); gs=$(cnt gitleaks); js=$(cnt jq)
big=$(REVIEW_BATCH_MIN=3 run); gb=$(cnt gitleaks); jb=$(cnt jq)
[ "$gs" -ge 4 ] && [ "$js" -ge 7 ]; chk $? "default threshold: per-file calls (gitleaks $gs, jq $js)"
[ "$gb" -eq 1 ]; chk $? "over threshold: one gitleaks call ($gb)"
[ "$jb" -le 1 ]; chk $? "over threshold: jq runs only on the invalid file ($jb)"
[ "$(rows "$small")" = "$(rows "$big")" ]; chk $? "rows identical in both modes"
grep -q 'src/leak.txt' <<<"$(rows "$big")" && grep -q 'src/bad.json' <<<"$(rows "$big")" && ! grep -q 'known.txt' <<<"$(rows "$big")"; chk $? "secret + invalid JSON reported, fingerprint dropped"
# new cases: r2 has a U+0085+space filename (git quotes control chars like \x0c, so they never reach the checks), a PR-added .gitleaks.toml allowlisting a secret (stub-allow), and a known change count
cd "$T"; mkdir r2; cd r2; g init -q .; echo base >README; g add -A; g commit -q -m base; git branch -f base
printf 'stub-allow = "s-base.txt"\n' >.gitleaks.toml; g add -A; g commit -q -m base-cfg; git branch -f base   # BASE carries an allowlist for s-base.txt
mkdir src; printf '{bad' >"src/a"$'\xc2\x85'"b c.json"; for i in 1 2 3 4; do echo '{}' >src/ok$i.json; done
printf '\xef\xbb\xbf{}' >src/bom.json; echo '{"n": NaN}' >src/nan.json   # a strict prefilter must hand both to jq
printf 'stub-allow = "s-leak.txt"\n' >.gitleaks.toml; echo x >src/leak.txt; echo y >src/base.txt
g add -A; g commit -q -m files
python3 - >"$STUB_JSON" <<'PY3'
import json
print(json.dumps([{"File": "src/leak.txt", "RuleID": "aws-access-token", "StartLine": 1, "Description": "d", "Secret": "s-leak.txt", "Fingerprint": "fp-l"}, {"File": "src/base.txt", "RuleID": "aws-access-token", "StartLine": 1, "Description": "d", "Secret": "s-base.txt", "Fingerprint": "fp-b"}]))
PY3
n=$(git diff --name-only base | grep -c .)
o=$(REVIEW_BATCH_MIN=$n run); g1=$(cnt gitleaks)
o2=$(REVIEW_BATCH_MIN=$((n - 1)) run); g2=$(cnt gitleaks); j2=$(cnt jq); [ ! "$(cat "$STUB_COUNT.cwd")" -ef . ]; cw=$?
[ "$g1" -gt 1 ]; chk $? "exactly REVIEW_BATCH_MIN files stays per-file ($g1 gitleaks calls)"
[ "$g2" -eq 1 ]; chk $? "REVIEW_BATCH_MIN+1 files batches ($g2 gitleaks call)"
has() { python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if any(r["tool"]==sys.argv[1] and r["file"]==sys.argv[2] for r in d) else 1)' "$1" "$2"; }
has jq $'src/a\xc2\x85b c.json' <<<"$o2" && r=0 || r=1; chk $r "batch: filename with U+0085 (str.splitlines splits it) and a space still gets its jq row"
has gitleaks src/leak.txt <<<"$o2" && r=0 || r=1; chk $r "batch: PR-edited .gitleaks.toml does not allowlist its own secret"
has gitleaks src/base.txt <<<"$o" && r=1 || r=0; chk $r "per-file (small diff): BASE .gitleaks.toml allowlist applied"
has gitleaks src/base.txt <<<"$o2" && r=1 || r=0; chk $r "batch: BASE .gitleaks.toml allowlist applied"
chk $cw "batch: gitleaks scans a temp copy of the changed files, not the whole tree"
[ "$j2" -eq 3 ]; chk $? "batch: BOM and NaN files go to jq like the bad one ($j2 jq calls)"
has gitleaks src/leak.txt <<<"$o" && r=0 || r=1; chk $r "per-file (small diff): PR-edited .gitleaks.toml does not allowlist its own secret"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
