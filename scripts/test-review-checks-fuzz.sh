#!/usr/bin/env bash
# review_checks.sh fuzz tool. Fuzzing executes repo test code, so it is explicit opt-in (--fuzz or REVIEW_FUZZ=1), never implied by --full.
# Stub-go cases always run (parse path, cleanup, cap, old go, missing go); a real-go case runs the seeded crashing fixture
# scripts/fixtures/tool-probes/go-fuzz and is skipped when go is not installed. REVIEW_CHECKS=<path> runs another copy of the script.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
GOBIN_=$(type -P go || true)
T=$(mktemp -d "${TMPDIR:-/tmp}/fuzz.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; chmod -R u+w "$T" 2>/dev/null; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
mkdir -p "$T/repo" "$T/sys" "$T/real" "$T/stub" "$T/old" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
cp "$ROOT"/scripts/fixtures/tool-probes/go-fuzz/go.mod .
cp "$ROOT"/scripts/fixtures/tool-probes/go-fuzz/fuzz_test.go.txt fuzz_test.go
mkdir -p fuzz/fuzz_targets && echo 'fn main(){}' >fuzz/fuzz_targets/t1.rs
printf 'import atheris\n' >a.py; printf 'class T { void fuzzerTestOneInput(byte[] d) {} }\n' >J.java
G add . && G commit -q -m fixture
for b in bash env git grep sed head tail cat rm rmdir mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep chmod uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
# stub go: version from $STUB_V; `go -C DIR test ...` plants a crasher like the real tool and fails
cat >"$T/stub/go" <<'S'
#!/usr/bin/env bash
[ "$1" != env ] || { echo "go${STUB_V:-1.22.0}"; exit 0; }
[ "$1" = -C ] || exit 0 # other go uses (go vet) are inert
echo "GOFLAGS=$GOFLAGS go $*" >>"$STUB_LOG"
d=$2; [ "${STUB_MODE:-}" = nofail ] || [ "${STUB_MODE:-}" = trav ] || mkdir -p "$d/testdata/fuzz/FuzzCrash"; printf 'go test fuzz v1\nstring("x")\n' >"$d/testdata/fuzz/FuzzCrash/abc123"
case "${STUB_MODE:-}" in
  nofail) echo "boom"; exit 1 ;;
  trav) echo "    Failing input written to ../../victim/keep"; exit 1 ;;
esac
echo "    Failing input written to testdata/fuzz/FuzzCrash/abc123"; exit 1
S
chmod +x "$T/stub/go"; ln -s "$GOBIN_" "$T/real/go" 2>/dev/null || true
export HOME="$T/home" GOCACHE="$T/gocache" GOFLAGS= DCR_CACHE_ROOT="$T/nocache" PERUN_HEAVY_DIR="$T/heavy" DCR_USER_BIN= STUB_LOG="$T/stub.log"
run() { local p=$1; shift; PATH="$p" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out" || { echo "rc=$? $*"; tail -3 "$T/err"; }; }
frows() { jq -c "[.[]|select(.tool==\"fuzz\" and .rule==\"$1\")]|length" "$T/out"; }

run "$T/stub:$T/sys" --full
[ "$(frows go-fuzz-crash)" = 0 ] && [ ! -e testdata ] && [ ! -e "$T/stub.log" ] && ok "default --full does not fuzz" || bad "--full fuzzed"
for k in atheris:a.py cargo-fuzz:fuzz/fuzz_targets/t1.rs jazzer:J.java; do
  jq -e --arg k "${k%%:*}" --arg f "${k#*:}" 'any(.[];.tool=="fuzz" and .rule=="fuzz-target-inventory" and .file==$f and (.message|startswith($k+" target (detected, not run)")))' "$T/out" >/dev/null \
    && ok "inventory ${k%%:*}" || bad "inventory ${k%%:*}"
done
run "$T/stub:$T/sys" --full-history || true
[ ! -e "$T/stub.log" ] && ok "--full-history does not fuzz" || bad "--full-history fuzzed"

run "$T/stub:$T/sys" --fuzz --timeout 60
jq -e '[.[]|select(.rule=="go-fuzz-crash")]|length==1 and (.[0].file=="testdata/fuzz/FuzzCrash/abc123") and (.[0].message|test("string\\(\"x\"\\)"))' "$T/out" >/dev/null \
  && [ ! -e testdata ] && ok "stub: crasher row, corpus deleted from the tree" || bad "stub crasher row or cleanup"
grep -q -- '-fuzztime=10s' "$T/stub.log" && ok "fuzztime 10s under a 60s budget" || bad "fuzztime"
REVIEW_FUZZ=1 run "$T/stub:$T/sys" --timeout 12
grep -q -- '-fuzztime=7s' "$T/stub.log" && ok "fuzztime = min(10, tmo-5)" || bad "fuzztime cap"
rm -f "$T/stub.log"; REVIEW_FUZZ=1 REVIEW_FUZZ_MAX=0 run "$T/stub:$T/sys"
grep -q 'not run: fuzz (over REVIEW_FUZZ_MAX' "$T/err" && [ "$(frows go-fuzz-crash)" = 0 ] && [ ! -e "$T/stub.log" ] && ok "REVIEW_FUZZ_MAX truncates" || bad "REVIEW_FUZZ_MAX"
rm -f "$T/stub.log"; mkdir sub && printf 'package sub\nfunc FuzzOther(f *testing.F) {}\n' >sub/x_test.go && git add -N sub/x_test.go
REVIEW_FUZZ=1 REVIEW_FUZZ_MAX=1 run "$T/stub:$T/sys" --timeout 60
[ "$(grep -c ' go -C ' "$T/stub.log")" = 1 ] && grep -q 'not run: fuzz (over REVIEW_FUZZ_MAX' "$T/err" && ok "REVIEW_FUZZ_MAX=1 with two targets runs one" || bad "REVIEW_FUZZ_MAX=1 cap"
git rm -q --cached sub/x_test.go; rm -rf sub
rm -f "$T/stub.log"; GOFLAGS=-tags=zz REVIEW_FUZZ=1 run "$T/stub:$T/sys" --timeout 60
grep -q 'GOFLAGS=-tags=zz go -C [^ ]* test -mod=readonly ' "$T/stub.log" && ok "GOFLAGS passed through, -mod=readonly a go arg" || bad "GOFLAGS"
rm -f "$T/stub.log"; run "$T/stub:$T/sys" --fuzz --timeout 5
grep -q 'not run: fuzz (total fuzz time' "$T/err" && [ ! -e "$T/stub.log" ] && ok "time budget spent is skipped" || bad "time budget"
STUB_V=1.19.5 run "$T/stub:$T/sys" --fuzz
grep -q 'not run: fuzz (go 1.19.5 is too old' "$T/err" && ok "old go reported" || bad "old go"
run "$T/sys" --fuzz
grep -q 'not run: fuzz (go missing' "$T/err" && ok "missing go is skipped, named" || bad "missing go"

if [ -n "$GOBIN_" ]; then
  rm -f "$T/stub.log"; run "$T/real:$T/sys" --fuzz --timeout 120
  jq -e '[.[]|select(.tool=="fuzz" and .rule=="go-fuzz-crash")]|length==1 and (.[0].file|test("^testdata/fuzz/FuzzCrash/[0-9a-f]+$"))' "$T/out" >/dev/null \
    && [ ! -e testdata ] && ok "real go: crasher row, tree left clean" || bad "real go crasher"
else echo "SKIP - real go case (go not installed)"; fi

# (a) --full with no jazzer/kotlin/atheris match must not die under pipefail
mkdir -p "$T/solo" && ( cd "$T/solo" && git init -q . && printf 'x=1\n' >a.py && G add . && G commit -q -m s && G branch base )
( cd "$T/solo" && PATH="$T/sys" bash "$RC" --base base --full 2>"$T/err" >"$T/out" ) && jq -e 'type=="array"' "$T/out" >/dev/null && ok "--full on a repo with no fuzz inventory: rc 0 + JSON" || bad "--full pipefail rc"
# (b) go fails without "Failing input": skip row, hub continues
rm -f "$T/stub.log"; STUB_MODE=nofail run "$T/stub:$T/sys" --fuzz --timeout 60
grep -q 'not run: fuzz (FuzzCrash exit 1' "$T/err" && [ "$(frows go-fuzz-crash)" = 0 ] && jq -e 'type=="array"' "$T/out" >/dev/null && ok "no Failing input: skip row, hub continues" || bad "no-failing-input"
# (c) traversal path from go output deletes nothing outside the corpus dir
mkdir -p "$T/victim" && : >"$T/victim/keep"
STUB_MODE=trav run "$T/stub:$T/sys" --fuzz --timeout 60
[ -e "$T/victim/keep" ] && [ "$(frows go-fuzz-crash)" = 0 ] && ok "traversal crasher path: nothing deleted, no row" || bad "traversal delete"
# (d) a tracked file at a valid crasher path is reported but never deleted
mkdir -p testdata/fuzz/FuzzCrash && printf 'go test fuzz v1\nstring("t")\n' >testdata/fuzz/FuzzCrash/abc123 && G add testdata && G commit -q -m tracked
run "$T/stub:$T/sys" --fuzz --timeout 60
[ -e testdata/fuzz/FuzzCrash/abc123 ] && ok "tracked crasher file kept" || bad "tracked crasher deleted"
exit $fail
