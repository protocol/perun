#!/usr/bin/env bash
# review_checks.sh trufflehog step, with a fake `trufflehog` on a hermetic PATH: a finding row (detector, file, line), a clean run, the offline
# flags, changed files in diff mode vs every tracked file under --full, 200-file chunks, fail-closed cases (crash, unparseable output, a result
# with no location), a failed call retried file by file (passing files keep their rows, a file that still fails is a not-checked row, none passing is not run after 3 failed retries), the gitleaks template's skip
# paths filtered from the file list, a missing binary (not-checked row, missing-tools hint, fixable), heavy-lease handling (degraded nice 19, REVIEW_LEASE_FULL=skip,
# a free lease), the likely-fixture hint, the method doc row, and the no-secret guarantee: --sarif, never --json (the default and --json outputs print the secret; JSON as Raw, RawV2,
# Redacted and SecretParts), so no secret value reaches stdout, stderr, the record or a file under TMPDIR. The last cases run the real trufflehog
# on small fixtures (a token-shaped value, the noise rules, an unreadable file) when it is installed (skipped otherwise: the CI runner has none).
# shellcheck disable=SC2164,SC2319 # every chk reads the $? of the test line before it, by design; each cd targets a directory this file just made
set -uo pipefail # no -e: every case reports, a failing one never aborts the run
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-trufflehog.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/sys" "$T/tmp" "$T/heavy"
# Hermetic PATH: the fake plus symlinks to only the system binaries the script needs, so no host scanner is ever run. No timeout(1): the perl timebox runs.
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl true sort uniq tr cut wc awk date cp mv ls find touch tee readlink sleep uname paste; do
  p=$(type -P "$b") && ln -s "$p" "$T/sys/$b"
done
# Fake trufflehog: logs its argv, then prints what the real one prints for the format asked. SARIF (--sarif) has no secret anywhere; --json prints one object
# per finding with the secret in Raw, RawV2, Redacted and SecretParts. TF_MODE: clean | crash | garbage | noloc (a result without a location) | hostile
# (SARIF that carries the secret in odd places). TF_BAD=NAME: a call naming a file of that basename exits 1 with no output (an unreadable file); TF_HANGN=N: a call
# naming N or more files hangs. After printing, a witness records whether any file under TMPDIR holds the secret (a stored copy).
cat >"$T/bin/trufflehog" <<'S'
#!/usr/bin/env python3
import json, os, sys, time
a = sys.argv[1:]
open(os.environ["TF_LOG"], "a").write(" ".join(a) + "\n")
mode, can = os.environ.get("TF_MODE", ""), os.environ["TF_CANARY"]
files = a[a.index("filesystem") + 1:]
if mode == "crash": sys.exit(9)
if mode == "garbage": print("not json at all"); sys.exit(0)
if os.environ.get("TF_BAD") in [os.path.basename(p) for p in files]: sys.exit(1)  # an unreadable file fails the whole call under --fail-on-scan-errors and prints nothing
if len(files) >= int(os.environ.get("TF_HANGN", "99999")): time.sleep(5)  # a call naming this many files hangs until the script's timebox kills it
hits = [os.path.normpath(p) for p in files if os.path.basename(p).startswith("leak") and mode != "clean"]
if "--json" in a:
    for h in hits:
        print(json.dumps({"SourceMetadata": {"Data": {"Filesystem": {"file": h, "line": 3}}}, "DetectorName": "Github", "Verified": False,
                          "Raw": can + "-raw", "RawV2": can + "-rawv2", "Redacted": can + "-red", "SecretParts": {"key": can + "-part"}}))
else:
    res = [{"ruleId": "Github", "level": "warning", "message": {"text": "Found unverified result for detector Github."},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": h}, "region": {"startLine": 3}}}],
            "partialFingerprints": {"trufflehogFingerprint/v1": "0" * 64}} for h in hits]
    for r in res:
        if mode == "hostile": r.update(Raw=can + "-raw", RawV2=can + "-rawv2", Redacted=can + "-red", properties={"k": can + "-prop"}); r["message"]["text"] = can + "-msg"
        if mode == "noloc": del r["locations"]
    print(json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "trufflehog", "rules": []}}, "results": res}]}, indent=2))
sys.stdout.flush()
stored = any(can in open(os.path.join(d, f), errors="replace").read() for d, _, fs in os.walk(os.environ["TMPDIR"]) for f in fs)
open(os.environ["TF_WITNESS"], "a").write("STORED\n" if stored else "clean\n")
S
chmod +x "$T/bin/trufflehog"
CAN="tfcanary-$$-$RANDOM" # stands for the secret value; no secret-shaped string is ever written to this file
R="$T/repo"; mkdir "$R"; cd "$R" || exit 1
git init -q . && g commit -q --allow-empty -m init
mkdir old node_modules; echo x >old/leak-old.txt; echo x >node_modules/leak-dep.js; g add . && g commit -q -m old && git branch base
mkdir -p tests; printf 'a\nb\nc\n' >leak.txt; echo ok >ok.txt; echo x >tests/leak.env; g add . && g commit -q -m change
# run [VAR=val...] [ARGS]: one hermetic review_checks.sh run in $R (stdout $T/out, stderr $T/err, fake's argv log $T/log, witness $T/wit); ARGS default to --base base
run() {
  local e=(); while [[ ${1:-} == *=* ]]; do e+=("$1"); shift; done; [ $# -gt 0 ] || set -- --base base
  : >"$T/log"; : >"$T/wit"
  (cd "$R" && env PATH="$T/bin:$T/sys" DCR_USER_BIN= TMPDIR="$T/tmp" PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 TF_LOG="$T/log" TF_WITNESS="$T/wit" TF_CANARY="$CAN" ${e[@]+"${e[@]}"} \
    bash "$RC" "$@" >"$T/out" 2>"$T/err") || true
}
J() { jq -e "$1" "$T/out" >/dev/null; } # a jq predicate over the findings array
rec() { jq -e "$1" "$R/.git/review-checks-last.json" >/dev/null; } # ... over the last-run record

run
J '[.[] | select(.tool=="trufflehog" and .file=="leak.txt" and .line==3 and .rule=="Github" and (.message|startswith("secret detected")))] | length == 1'; chk $? "finding row: tool trufflehog, rule = detector, file, line"
J '[.[] | select(.tool=="trufflehog")] | map(.file) | sort == ["leak.txt","tests/leak.env"]'; chk $? "only the changed files with a hit are reported (diff mode)"
J '.[] | select(.tool=="trufflehog" and .file=="tests/leak.env") | .hint=="likely-fixture" and (.text|endswith("[likely-fixture]"))'; chk $? "a hit under a fixture path carries the likely-fixture hint"
J '.[] | select(.file=="leak.txt") | .hint == null'; chk $? "a hit outside fixture paths has no hint"
grep -q '^review_checks: .*analyzers ran: [^;]*trufflehog' "$T/err" && ! grep -q 'not run: trufflehog' "$T/err"; chk $? "summary lists trufflehog under analyzers ran, not under not run"
rec '.wired | index("trufflehog") != null' && rec '.not_run | index("trufflehog") == null'; chk $? "record: trufflehog wired and ran"
grep -q -- '--no-verification' "$T/log" && grep -q -- '--no-update' "$T/log" && grep -q -- '--fail-on-scan-errors' "$T/log" && grep -q ' filesystem ' "$T/log"; chk $? "argv: offline (--no-verification --no-update), --fail-on-scan-errors, filesystem"
grep -q -- '--sarif' "$T/log" && ! grep -qE -- '--json|--json-legacy|--github-actions' "$T/log"; chk $? "argv: --sarif output, never --json (it carries the secret) or another format"
[ "$(grep -c . "$T/log")" = 1 ] && grep -q -- '\./leak.txt \./ok.txt \./tests/leak.env$' "$T/log"; chk $? "diff mode: one call naming only the changed files as ./path"
! grep -qE 'old/|node_modules' "$T/log"; chk $? "diff mode: an untouched or vendored file is not scanned"
w=$(cat "$T/wit"); [ "$w" = clean ]; chk $? "no file under TMPDIR holds the secret during the run (nothing stored)"
! grep -rq "tfcanary-" "$T/out" "$T/err" "$R/.git/review-checks-last.json"; chk $? "secret canary absent from stdout, stderr and the record"
# the existing heavy/light classification (heavy_gate.py) covers the exact argv this step ran, and a --version probe stays light
env PERUN_HEAVY_PATTERNS= python3 -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import heavy_gate as hg; p = hg.heavy_patterns()
sys.exit(0 if hg.is_heavy("trufflehog " + open(sys.argv[2]).read().strip(), p) and not hg.is_heavy("trufflehog --version", p) else 1)' "$ROOT/.claude/skills/agentic-delivery/scripts" "$T/log"
chk $? "heavy_gate.py classifies the argv this step ran as heavy, trufflehog --version as light"

# --json is what carries the secret: the witness must catch a copy of it under TMPDIR (proves the witness above is not vacuous)
mkdir "$T/sim"; TMPDIR="$T/sim" TF_LOG="$T/log" TF_WITNESS="$T/wit2" TF_CANARY="$CAN" "$T/bin/trufflehog" --json filesystem ./leak.txt >"$T/sim/out"
[ "$(cat "$T/wit2")" = STORED ] && grep -q '"Raw"' "$T/sim/out" && grep -q '"SecretParts"' "$T/sim/out"; chk $? "witness self-check: --json output stored under TMPDIR is caught"

run TF_MODE=hostile
J '[.[] | select(.tool=="trufflehog" and .file=="leak.txt")] | length == 1 and (.[0].message | startswith("secret detected"))'; chk $? "hostile SARIF: row still has our message, not the tool's"
! grep -rq "tfcanary-" "$T/out" "$T/err" "$R/.git/review-checks-last.json"; chk $? "hostile SARIF (secret in message, Raw, RawV2, Redacted, properties): no value printed or recorded"

run TF_MODE=clean
J '[.[] | select(.tool=="trufflehog")] | length == 0' && grep -q 'analyzers ran: [^;]*trufflehog' "$T/err"; chk $? "clean run: no trufflehog row, listed as ran"

run TF_MODE=crash
J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | length == 1' && grep -q 'review_checks: not run: trufflehog (exit 9)' "$T/err"; chk $? "crash: not-checked row and 'not run: trufflehog (exit 9)', never clean"
! grep -q 'analyzers ran: [^;]*trufflehog' "$T/err" && grep -q 'NOT RUN: .*trufflehog (exit 9)' "$T/err" && rec '.not_run | index("trufflehog") != null'; chk $? "crash: listed under NOT RUN and not_run, not under ran"
run TF_MODE=garbage
J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | length == 1' && grep -q 'not run: trufflehog (unparseable output' "$T/err"; chk $? "unparseable output: not run with a not-checked row, never clean"
run TF_MODE=noloc
J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | length == 1' && grep -q 'not run: trufflehog (unparseable output' "$T/err"; chk $? "a result with no location fails closed (not dropped)"

# missing binary: hermetic PATH without the fake
mv "$T/bin/trufflehog" "$T/trufflehog.off"; run
grep -q 'review_checks: not run: trufflehog (not installed)' "$T/err" && grep -q 'skipped (not installed): .*trufflehog' "$T/err"; chk $? "missing binary: 'not run: trufflehog (not installed)' and listed as skipped"
J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked" and (.message|test("not installed")))] | length == 1'; chk $? "missing binary: a not-checked row (secrets were not scanned)"
grep -q 'review_checks: missing tools: .*trufflehog (install: brew install trufflehog)' "$T/err"; chk $? "missing binary: the missing-tools row names the install hint"
rec '.fixable | index("trufflehog") != null' && grep -q 'fixable: .*trufflehog' "$T/err"; chk $? "missing binary: fixable (provision_tools.sh --print installs it)"
mv "$T/trufflehog.off" "$T/bin/trufflehog"

# --full: every tracked file (the untouched one too), never the vendored dir
run --full
J '[.[] | select(.tool=="trufflehog")] | map(.file) | sort == ["leak.txt","old/leak-old.txt","tests/leak.env"]'; chk $? "--full reports an untouched tracked file"
grep -q -- '\./old/leak-old.txt' "$T/log" && ! grep -q node_modules "$T/log"; chk $? "--full names every tracked file, minus node_modules"

# 200 files per call: 450 changed files -> 200 + 200 + 50, findings from the last chunk kept
B="$T/big"; mkdir "$B"; cd "$B"; git init -q . && g commit -q --allow-empty -m init && git branch base
for i in $(seq 1 449); do echo "$i" >"f$i.txt"; done; echo x >leak450.txt; g add . && g commit -q -m many
R="$B" run
[ "$(grep -c . "$T/log")" = 3 ] && [ "$(awk '{print gsub(/\.\/[^ ]+/, "&")}' "$T/log" | paste -sd, -)" = "200,200,50" ]; chk $? "450 changed files: three calls of 200, 200 and 50"
J '[.[] | select(.tool=="trufflehog" and .file=="leak450.txt")] | length == 1'; chk $? "450 changed files: the last chunk's finding is kept"
cd "$R"

# a failed call is retried file by file, so one bad file costs only itself (TF_BAD: the fake fails any call that names that file and prints nothing, like --fail-on-scan-errors on an unreadable file)
calls() { awk '{print gsub(/\.\/[^ ]+/, "&")}' "$T/log" | paste -sd, -; } # files named per call, in order: 3,1,1,1 is one 3-file call then one call per file
mkrepo() { local d=$1 f; shift; mkdir -p "$d"; (cd "$d" && git init -q . && g commit -q --allow-empty -m init && git branch base && for f in "$@"; do mkdir -p "$(dirname "$f")"; echo x >"$f"; done && g add . && g commit -q -m change); } # an empty base, then one commit adding each FILE
run TF_BAD=ok.txt
[ "$(calls)" = 3,1,1,1 ]; chk $? "a failed 3-file call is retried once per file (3,1,1,1 files per call)"
J '[.[] | select(.tool=="trufflehog" and .rule=="Github")] | map(.file) | sort == ["leak.txt","tests/leak.env"]'; chk $? "failed call: the files that pass alone keep their findings"
J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | length == 1 and .[0].file == "ok.txt" and (.[0].message | test("not scanned for secrets"))'; chk $? "failed call: the file that still fails is one not-checked row naming it"
! grep -q 'not run: trufflehog' "$T/err" && grep -q 'review_checks: partial: trufflehog could not scan 1 of 3 file' "$T/err" && grep -q 'partial: [^;]*trufflehog(errors)' "$T/err"; chk $? "failed call: partial (1 of 3 files) on stderr and the closing line, never not run"
rec '.partial | index("trufflehog(errors)") != null' && rec '.not_run | index("trufflehog") == null' && rec '.wired | index("trufflehog") != null'; chk $? "failed call: the record lists trufflehog(errors) under partial, wired, and not under not_run"
grep -q 'review_checks: not run: semgrep (not installed)' "$T/err"; chk $? "failed call: a skip reported after the retry still prints (the quiet probe is reset)"
run TF_MODE=crash
[ "$(calls)" = 3,1,1,1 ]; chk $? "crash: the call is retried per file; no file passes, so the tool is still not run (the crash checks above)"
run TF_HANGN=2 --base base --timeout 1
[ "$(calls)" = 3,1,1,1 ] && J '[.[] | select(.tool=="trufflehog" and .rule=="Github")] | map(.file) | sort == ["leak.txt","tests/leak.env"]' && ! grep -q 'not run: trufflehog' "$T/err" && grep -q 'analyzers ran: [^;]*trufflehog' "$T/err"; chk $? "timed-out 3-file call: the per-file retry completes, findings kept, trufflehog not reported as not run"
mkrepo "$T/one" leak.txt
R="$T/one" run TF_MODE=crash
[ "$(calls)" = 1 ] && grep -q 'review_checks: not run: trufflehog (exit 9)' "$T/err"; chk $? "a one-file call that fails is not retried (the retry would be the same call): not run"
R="$B" run TF_BAD=f99.txt
[ "$(grep -c . "$T/log")" = 53 ] && [ "$(calls | cut -d, -f1-3)" = 200,200,50 ]; chk $? "450 files, one bad: the two passing chunks run once, only the failed 50-file chunk is retried per file (3 + 50 calls)"
J '[.[] | select(.tool=="trufflehog" and .rule=="Github")] | map(.file) == ["leak450.txt"]' && J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | map(.file) == ["f99.txt"]'; chk $? "450 files, one bad: the retried chunk keeps its finding, the bad file is the only not-checked row"

# a tool that fails every call: while no single file has passed, 3 failed single-file retries end the chunk as not run (a hung tool would otherwise cost up to 200 timeboxed runs per chunk)
R="$B" run TF_MODE=crash
[ "$(calls)" = 200,1,1,1,200,1,1,1,50,1,1,1 ] && [ "$(grep -c '^review_checks: not run: trufflehog (exit 9)$' "$T/err")" = 3 ] && ! grep -q 'partial: trufflehog' "$T/err" && R="$B" rec '.not_run | index("trufflehog") != null'; chk $? "450 files, tool crashes on every call: each chunk gets its call plus 3 single-file retries (12 calls, not 453), then is not run with its reason"
mkrepo "$T/ten" f{1..10}.txt
R="$T/ten" run TF_HANGN=1 --base base --timeout 1
[ "$(calls)" = 10,1,1,1 ] && grep -q '^review_checks: not run: trufflehog (timeout 1s)$' "$T/err"; chk $? "tool hangs on every call: the 10-file call plus 3 timeboxed single-file retries, then not run with the timeout reason"
mkrepo "$T/mix" a.txt d1/bad.txt d2/bad.txt d3/bad.txt d4/bad.txt z.txt
R="$T/mix" run TF_BAD=bad.txt
[ "$(calls)" = 6,1,1,1,1,1,1 ] && J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | map(.file) | sort == ["d1/bad.txt","d2/bad.txt","d3/bad.txt","d4/bad.txt"]' && grep -q 'review_checks: partial: trufflehog could not scan 4 of 6 file' "$T/err" && ! grep -q 'not run: trufflehog' "$T/err"; chk $? "the cap ends only a chunk where no file has passed: once one does, all 4 bad files of 6 are retried and named, partial and not not run"

# noise rules: with no repo .gitleaks.toml the gitleaks template's skip paths are filtered from the file list (trufflehog's own --exclude-paths is ignored for named files) and counted on stderr
mkrepo "$T/noise" src/leak.txt fixtures/leak.txt testdata/leak.txt .history/leak.txt registry.json package-lock.json
R="$T/noise" run
[ "$(grep -c . "$T/log")" = 1 ] && grep -q ' filesystem \./src/leak\.txt$' "$T/log"; chk $? "template paths (fixtures/, testdata/, .history/, registry JSON, a lockfile) are not passed to trufflehog"
J '[.[] | select(.tool=="trufflehog")] | map(.file) == ["src/leak.txt"]'; chk $? "template paths: only the file outside them is reported"
grep -q 'review_checks: trufflehog template skipped 5 changed file(s) under .history/, fixtures/, testdata/' "$T/err"; chk $? "template paths: stderr counts the skipped files in gitleaks' wording"
mkrepo "$T/own" src/leak.txt fixtures/leak.txt testdata/leak.txt .history/leak.txt registry.json package-lock.json .gitleaks.toml
R="$T/own" run
[ "$(calls)" = 7 ] && ! grep -q 'template skipped' "$T/err" && J '[.[] | select(.tool=="trufflehog")] | map(.file) | sort == [".history/leak.txt","fixtures/leak.txt","src/leak.txt","testdata/leak.txt"]'; chk $? "a repo .gitleaks.toml turns the template off: every changed file is scanned, none skipped"
mkrepo "$T/hidden" fixtures/leak.txt package-lock.json
R="$T/hidden" run
[ ! -s "$T/log" ] && J '[.[] | select(.tool=="trufflehog")] | length == 0' && grep -q 'trufflehog template skipped 2 changed file(s)' "$T/err" && ! grep -q 'not run: trufflehog' "$T/err"; chk $? "only template paths changed: trufflehog is never called, no rows, not reported as not run"
R="$T/hidden" rec '.wired | index("trufflehog") == null' && R="$T/hidden" rec '.not_run | index("trufflehog") == null'; chk $? "only template paths changed: trufflehog had no work, so it is neither wired nor not_run"

# heavy lease (same stub policy tree as test-review-checks-lease-degraded.sh): FULL -> degraded nice 19, labelled; skip -> not run; free -> leased, plain
mkdir "$T/nicebin"; cat >"$T/nicebin/nice" <<'S'
#!/usr/bin/env bash
[ "$1 $2" = "-n 19" ] || { echo "bad nice args: $*" >&2; exit 99; }
shift 2; echo "$*" >>"$NICE_LOG"; exec "$@"
S
chmod +x "$T/nicebin/nice"
SK="$T/sk"; mkdir -p "$SK/deep-code-review/scripts" "$SK/agentic-delivery/scripts"
cp "$RC" "$SK/deep-code-review/scripts/"; cp -R "$(dirname "$RC")/../templates" "$SK/deep-code-review/templates"
stubrun() { # $1 = policy python body; the rest is env
  printf 'import os, sys\nopen(os.environ["PP_LOG"], "a").write(sys.argv[1] + "\\n")\n%s\n' "$1" >"$SK/agentic-delivery/scripts/perun_policy.py"; shift
  : >"$T/nice.log"; : >"$T/pp.log"; : >"$T/log"; : >"$T/wit"
  (cd "$R" && env PATH="$T/bin:$T/nicebin:$T/sys" DCR_USER_BIN= TMPDIR="$T/tmp" REVIEW_LEASE_WAIT=0 NICE_LOG="$T/nice.log" PP_LOG="$T/pp.log" TF_LOG="$T/log" TF_WITNESS="$T/wit" TF_CANARY="$CAN" "$@" \
    bash "$SK/deep-code-review/scripts/review_checks.sh" --base base >"$T/out" 2>"$T/err") || true
}
stubrun 'print("FULL"); sys.exit(1)'
[ -s "$T/log" ] && grep -q '^trufflehog ' "$T/nice.log"; chk $? "lease FULL: trufflehog ran, under nice -n 19, not skipped"
grep -q 'analyzers ran: [^;]*trufflehog (degraded: lease full, nice 19)' "$T/err" && ! grep -q 'trufflehog (degraded[^)]*1 worker' "$T/err"; chk $? "lease FULL: summary labels trufflehog degraded (no single-worker flag claimed)"
[ "$(cat "$T/pp.log")" = heavy-acquire ]; chk $? "lease FULL: one acquire, lease never taken"
stubrun 'print("FULL"); sys.exit(1)' REVIEW_LEASE_FULL=skip
[ ! -s "$T/log" ] && grep -q 'not run: trufflehog (heavy lease full)' "$T/err" && J '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | length >= 1'; chk $? "REVIEW_LEASE_FULL=skip: trufflehog skipped as 'heavy lease full' with a not-checked row"
stubrun 'import os; print(os.getppid())'
[ -s "$T/log" ] && [ ! -s "$T/nice.log" ] && ! grep -q degraded "$T/err" && grep -qx heavy-release "$T/pp.log"; chk $? "free lease: trufflehog ran at normal priority under the lease, then released it"

# the method doc row and the provisioning list
grep -q trufflehog "$ROOT/.claude/skills/deep-code-review/references/method-situational.md" && grep -q trufflehog "$ROOT/.claude/skills/deep-code-review/references/tool-hub.md"; chk $? "method-situational.md and tool-hub.md name trufflehog"
TH="$ROOT/.claude/skills/deep-code-review/references/tool-hub.md"
grep -q 'trufflehog:ignore' "$TH" && grep -q 'hashes do not apply to it' "$TH"; chk $? "tool-hub.md: .gitleaksignore fingerprints do not apply to trufflehog, an inline trufflehog:ignore comment does"
prov=$(env PATH="$T/sys" DCR_USER_BIN= bash "$(dirname "$RC")/provision_tools.sh" 2>&1) # captured first: `grep -q` closing the pipe early would SIGPIPE the script and trip pipefail
grep -q 'MISSING  trufflehog (brew install trufflehog)' <<<"$prov"; chk $? "provision_tools.sh lists trufflehog with its brew installer"

# real binary, tiny fixture only (2 files, 2 workers): a real token-shaped value is found and never printed or stored; swapping --sarif for --json would store it
REAL=$(command -v trufflehog || true)
if [ -n "$REAL" ]; then
  tok="gh""p_$(printf 'aZ3kQ9%.0s' 1 2 3 4 5 6)" # built at runtime: no source line looks like a token
  X="$T/real"; mkdir "$X" "$X/rbin" "$X/rtmp"; cd "$X"; git init -q . && g commit -q --allow-empty -m init && git branch base
  printf 'token = %s\n' "$tok" >leak.txt; echo 'nothing here' >plain.txt; g add . && g commit -q -m files
  cat >"$X/rbin/trufflehog" <<'S'
#!/usr/bin/env bash
# real trufflehog, 2 workers; RT_JSON=1 swaps --sarif for --json (a regression drill). The witness then looks for the token under TMPDIR.
a=(); for x in "$@"; do if [ "$x" = --sarif ] && [ -n "${RT_JSON:-}" ]; then a+=(--json); else a+=("$x"); fi; done
"$REAL_TF" --concurrency=2 "${a[@]}"; rc=$?
if grep -rqF "$TOKEN" "$TMPDIR"; then echo STORED >>"$RT_WIT"; else echo clean >>"$RT_WIT"; fi
exit $rc
S
  chmod +x "$X/rbin/trufflehog"
  rrun() { : >"$X/wit"; (cd "$X" && env PATH="$X/rbin:$T/sys" DCR_USER_BIN= TMPDIR="$X/rtmp" PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REAL_TF="$REAL" TOKEN="$tok" RT_WIT="$X/wit" "$@" \
    bash "$RC" --base base >"$X/out" 2>"$X/err") || true; }
  rrun
  jq -e '[.[] | select(.tool=="trufflehog" and .file=="leak.txt" and .line==1)] | length == 1' "$X/out" >/dev/null; chk $? "real trufflehog: the token-shaped value is found (file and line)"
  jq -e '[.[] | select(.tool=="trufflehog" and .file=="plain.txt")] | length == 0' "$X/out" >/dev/null; chk $? "real trufflehog: a clean file has no row"
  ! grep -rqF "$tok" "$X/out" "$X/err" "$X/.git/review-checks-last.json" && [ "$(cat "$X/wit")" = clean ]; chk $? "real trufflehog: the token is never printed, recorded or stored under TMPDIR"
  rrun RT_JSON=1
  [ "$(cat "$X/wit")" = STORED ]; chk $? "real trufflehog, --json drill: the token would sit under TMPDIR (the witness is sensitive)"
  # noise rules and the per-file retry: distinct tokens per file (a repeated secret may be deduplicated), a fixtures/ copy, an inline-ignored line, a .gitleaksignore naming leak.txt, one unreadable file
  t2="gh""p_$(printf 'bY4mR8%.0s' 1 2 3 4 5 6)"; t3="gh""p_$(printf 'cX5nS7%.0s' 1 2 3 4 5 6)"; t4="gh""p_$(printf 'dW6pT2%.0s' 1 2 3 4 5 6)"
  mkdir fixtures; printf 'a = %s\nb = %s # trufflehog:ignore\n' "$t2" "$t4" >ign.txt; printf 'token = %s\n' "$t3" >fixtures/leak.env
  echo 'leak.txt:github-pat:1' >.gitleaksignore; echo y >bad.txt; g add . && g commit -q -m more; chmod 000 bad.txt
  nosecret() { ! grep -qF -e "$tok" -e "$t2" -e "$t3" -e "$t4" "$X/out" "$X/err" "$X/.git/review-checks-last.json" && ! grep -q STORED "$X/wit"; }
  rrun
  jq -e '[.[] | select(.tool=="trufflehog" and (.file|startswith("fixtures/")))] | length == 0' "$X/out" >/dev/null && grep -q 'review_checks: trufflehog template skipped 1 changed file(s)' "$X/err"; chk $? "real trufflehog, no repo .gitleaks.toml: a fixtures/ file is skipped and counted on stderr"
  if [ -r bad.txt ]; then chk 0 "real trufflehog, unreadable file (skipped: the file stays readable, e.g. running as root)"
  else
    jq -e '[.[] | select(.tool=="trufflehog" and .rule=="not-checked")] | map(.file) == ["bad.txt"]' "$X/out" >/dev/null && jq -e '[.[] | select(.tool=="trufflehog" and .file=="leak.txt")] | length == 1' "$X/out" >/dev/null \
      && grep -q 'partial: trufflehog could not scan 1 of' "$X/err" && ! grep -q 'not run: trufflehog' "$X/err"; chk $? "real trufflehog, one unreadable file: it alone is a not-checked row, the other findings are kept (partial, not not run)"
  fi
  nosecret; chk $? "real trufflehog, template and retry run: no token printed, recorded or stored"
  chmod 644 bad.txt; echo '# own config' >.gitleaks.toml; g add . && g commit -q -m toml
  rrun
  jq -e '[.[] | select(.tool=="trufflehog")] | map(.file) | sort == ["fixtures/leak.env","ign.txt","leak.txt"]' "$X/out" >/dev/null && ! grep -q 'template skipped' "$X/err"; chk $? "real trufflehog, repo has its own .gitleaks.toml: fixtures/ is scanned, and a .gitleaksignore entry does not hide leak.txt"
  jq -e '[.[] | select(.tool=="trufflehog" and .file=="ign.txt")] | map(.line) == [1]' "$X/out" >/dev/null; chk $? "real trufflehog: an inline trufflehog:ignore comment hides the finding on its line only"
  nosecret; chk $? "real trufflehog, own-config run: no token printed, recorded or stored"
else chk 0 "real trufflehog cases (skipped: trufflehog not installed)"; fi
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
