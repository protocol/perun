#!/usr/bin/env bash
# review_checks.sh [--base REF] [--tests] [--history] [--full] [--timeout SECS] — run local, read-only analyzers over the files
# changed since REF (default origin/main, compared as REF...HEAD) and print findings as a JSON array on
# stdout: [{"file","line","rule","message","text","tool"}]. `text` ("rule: message") is the key
# scripts/score_review.py matches on. Findings are LEADS: verify each against the code before reporting.
#
# Tools (linters, gitleaks, osv-scanner, semgrep, trivy): see references/method-situational.md. Each runs only when
# installed and only on matching changed files. Secrets are redacted and never printed; osv-scanner runs offline on a warm DB (env REVIEW_OSV_DB_DIR, an exported OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY that already holds a seeded database,
# else the cache provision_tools.sh --print warms; no flag needed), or against the OSV API with env REVIEW_OSV=1 (network), and is not run with neither;
# a lockfile with no osv-scanner/trivy result falls back to npm/pnpm/pip-audit (opt-in: REVIEW_OSV=1 or REVIEW_OSV_DB_DIR; it queries the registry), else a not-checked row; trivy is offline.
# semgrep uses repo rules, else the bundled taint rules plus the p/default pack (never `--config auto`; the local snapshot provision_tools.sh --print warms stands in for the registry pack when present).
# If that pack errors or hangs to the timeout, that 200-file chunk reruns with the bundled rules alone (the later chunks too, unless an earlier pack run succeeded) and the run says so, so it never reads as a
# full clean: `semgrep(bundled-only)` under analyzers ran (and under partial and fixable in the closing line), `semgrep p/default pack (<why>)` under NOT RUN and a not-checked row, with the fix named (a warm
# snapshot: provision_tools.sh --print). That is the only report of the gap: no separate "missing tools" row.
# Tool hub: zizmor, actionlint, bandit, gosec, grype, checkov, hadolint (snyk-agent-scan is unverified, skipped) run from one registry
# (`hub=`); a matching changed file with the tool missing prints "NOT CHECKED: <tool> (install: <hint>)" on stderr, never a silent clean.
# Built-in, always on, no install: invisible_chars.py flags NUL/C0 control characters and bidi/zero-width/tag characters in changed text files (tool `invisible-chars`, with line and col;
# rows under fixture/test paths carry `[likely-fixture]`; third_party/, Pods/, bower_components/ and *.min.js are skipped; a `not-checked` row is unchecked surface).
# Built-in too: committed_personal_data.py counts the distinct non-reserved email addresses in each changed file (third_party/, Pods/, bower_components/ and *.min.js are skipped, as for invisible-chars), binary data included,
# and reports a file with 10 or more (tool `committed-data`, rule `email-addresses`; the row carries the count only, never an address). Addresses spread thin are summed over the files that stay below 10: 50 or more
# distinct give one `email-addresses` row with the path `.`. `not-checked` = unreadable, over the 32 MiB read cap, or, under the threshold, a file in a format whose pages can hide addresses (parquet, arrow, orc, zip, gzip,
# zstd, xz, 7z, lz4, bzip2, avro, pdf, zlib; the list and its ceilings are in committed_personal_data.py). gitleaks looks for secrets, not for exported personal data.
# `--full` scans every tracked file (base = git's empty tree) instead of a diff; it also runs tenant_scope_check.py (SKIPPED without a *.prisma). gitleaks runs once over the working tree. gitleaks drops
# fingerprints listed in the repo's .gitleaksignore (as of BASE, HEAD under --full).
# gitleaks generic-api-key hits tagged likely-fixture collapse to one summary row per top fixture dir when it has >3 (every other rule, and name-only matches, stay rows); REVIEW_FIXTURE_ROWS=all lists every hit.
# `--history` also runs gitleaks over BASE..HEAD (`--full-history`: the whole history). node_modules, vendor, build
# dirs and .claude/worktrees are never scanned; each heavy scanner takes the heavy lease only when it runs (waits
# REVIEW_LEASE_WAIT s, default 120) and releases it afterwards. If the lease is still full after the wait the scanners
# run degraded without the lease (`nice -n 19` when nice works, plus `--jobs 1` for semgrep and `--parallel 1` for trivy,
# dropped on a crash and retried once) and the summary labels them "(degraded: lease full, ...)"; REVIEW_LEASE_FULL=skip restores the old skip.
# A summary "N findings; N files excluded; analyzers ran: ...; skipped (not installed): ..." goes to stderr, then "NOT RUN: <tool> (<why>), ..." (or "none"); a tool
# that timed out, crashed or (REVIEW_LEASE_FULL=skip) lost the lease is listed there (once, with a not-checked row on stdout) and never under "ran", so it cannot read as zero findings; a tool that is merely not installed stays under "skipped (not installed)". `--tests` also runs the command
# declared in env REVIEW_TEST_CMD (opt-in; it executes project code). Never installs anything. A missing tool
# or a timeout prints "review_checks: not run: <tool> (<why>)" on stderr and is not a failure. A semgrep scan that emitted findings but
# reported errors prints "review_checks: partial: semgrep ran ..." instead (never "not run"). A semgrep chunk with errors and zero results is "partial" when some scanned file raised no error (the unscanned part is a not-checked row), and "not run" only when every scanned file errored. A hub tool that reports a file outside its scanned list is "not run" (paths do not line up), never a clean. tsc also resolves the repo-local node_modules/.bin/tsc (cwd or git toplevel only), run only when REVIEW_TEST_CMD is set.
# Offline caches that scripts/provision_tools.sh --print warms once, outside the sandbox, are used when present: the osv-scanner offline DB
# (unless REVIEW_OSV_DB_DIR or REVIEW_OSV=1 choose a mode), the trivy DB (trivy always runs offline) and a local semgrep p/default snapshot.
# A closing "ran X / wired Y scanners" stderr line names the scanners that had work this run, those that did not run, those that ran with a partial
# scope (trivy secret-only, semgrep with errors or bundled-only) and which a provision fixes (a missing tool, a cold cache, semgrep bundled-only); wired also counts shellcheck, ruff/pyflakes and (with --history) gitleaks-history,
# which provision_tools.sh cannot install, so they can be "not run" but never "fixable". The same summary is recorded best-effort in
# <git-common-dir>/review-checks-last.json for perun_doctor.py.
# All temp files live in one private mktemp -d dir per run, removed on exit.
# Each tool run is timeboxed (default 60s); a semgrep chunk whose p/default pack hangs spends a second timebox on the bundled-rules rerun. Exit 0 even with findings; 2 on usage/unresolvable base.
set -euo pipefail
# pipx and `uv tool` install into ~/.local/bin, which a sandboxed shell's PATH may lack: append it so provisioned scanners are found (DCR_USER_BIN overrides; empty disables)
lb=${DCR_USER_BIN-${HOME:-/nonexistent}/.local/bin}
case ":$PATH:" in *":$lb:"*) ;; *) [ -z "$lb" ] || [ ! -d "$lb" ] || PATH=$PATH:$lb ;; esac

repo=. base=origin/main tests=0 hist=0 tmo=60 ran="" nr="" failed="" missing="" gap="" dg="" w1="" nice19=0 lease=ok leased=0 full=0 wr=0 cov="" wired="" wiredx=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base=${2:?--base needs a ref}; case "$base" in -*) echo "review_checks: --base must not start with '-'" >&2; exit 2 ;; esac; shift 2 ;;
    --timeout) tmo=${2:?--timeout needs seconds}; shift 2 ;;
    --tests) tests=1; shift ;;
    --repo) repo=${2:?--repo needs a dir}; [ -d "$repo" ] || { echo "review_checks: --repo: not a directory: $repo" >&2; exit 2; }; shift 2 ;; # replaces `cd DIR && review_checks.sh` (bash guards block chains)
    --history) hist=1; shift ;;
    --full) wr=1 full=1; shift ;;
    --full-history) hist=1 full=1; shift ;;
    *) echo "usage: review_checks.sh [--repo DIR] [--base REF] [--tests] [--history] [--full] [--timeout SECS]" >&2; exit 2 ;;
  esac
done
case "$tmo" in ''|*[!0-9]*) echo "review_checks: --timeout must be an integer" >&2; exit 2 ;; esac
here=$(cd "$(dirname "$0")" && pwd)
cd "$repo"
if [ "$wr" = 1 ]; then base=$(git hash-object -t tree /dev/null); ref=HEAD # whole repo: every tracked file against the empty tree
else ref=$base; git rev-parse --verify -q "$base^{commit}" >/dev/null || { echo "review_checks: unresolvable base '$base'" >&2; exit 2; }; fi
cd "$(git rev-parse --show-toplevel)"

# One private per-run dir (mode 700) holds every temp file, so concurrent runs sharing $TMPDIR never touch each other's files.
td=$(mktemp -d "${TMPDIR:-/tmp}/review.XXXXXX") && trap 'rm -rf "$td"' EXIT INT TERM HUP || exit 2
raw=$td/raw out=$td/out tsv=$td/tsv lf=$td/lf rep=$td/rep gla=$td/gla gli=$td/gli
sgh=$(mktemp -d "$td/review-sg.XXXXXX") # semgrep HOME: the macOS agent sandbox denies writes to ~/.semgrep
: >"$raw"; : >"$out"; : >"$tsv"; : >"$lf"; : >"$rep"; : >"$gla"; : >"$gli"
# Vendored, build and worktree dirs are never scanned (a changed file under them is dropped here, for every tool).
XRE='(^|/)(node_modules|\.claude/worktrees|vendor|dist|build|\.git|\.venv|venv|target|__pycache__)/'
if [ "$wr" = 1 ]; then all=$(git -c core.quotePath=false diff --name-only --diff-filter=ACMR "$base" HEAD); else all=$(git -c core.quotePath=false diff --name-only --diff-filter=ACMR "$base"...HEAD); fi
files=$(printf '%s\n' "$all" | grep -Ev "$XRE" || true)
# One-per-line copy of $files for exact-line membership tests: grep reads this file, never a pipe (a `printf | grep -q` that matches early
# SIGPIPEs the writer, and pipefail then drops the match once the list outgrows the pipe buffer).
printf '%s\n' "$files" >"$td/files"
nex=$(( $(printf '%s\n' "$all" | grep -c . || true) - $(printf '%s\n' "$files" | grep -c . || true) )) # grep -c exits 1 at a count of 0, which set -e would turn into a silent exit
[ -n "$files" ] || echo "review_checks: 0 files in diff (empty, or only excluded paths); nothing to scan" >&2
rc=0
[ -z "$files" ] || wired+=" gitleaks semgrep trivy" # scanners with work this run (any changed file); osv-scanner and the hub add theirs below
# wiredx: scanners that count toward "wired" but that provision_tools.sh cannot install, so they are never "fixable": shellcheck, ruff/pyflakes, gitleaks-history
[ "$hist" = 0 ] || wiredx+=" gitleaks-history"

# Existing changed files matching extended regex $1, one per line.
changed() { { printf '%s\n' "$files" | grep -E "$1" || true; } | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done; true; }
# A skip also lands in the JSON as a not-checked row (hub: under $hubtool; else under the tool) so `[]` never hides a tool that did not run.
# Unless merely not installed (that has its own list) it joins the failed set (subtracted from "ran" at print, so a later good file cannot
# re-list it) and the deduped "NOT RUN" list.
# ponytail: per-file tools (shellcheck) leave "ran" when any one file fails, the safe direction.
skip() {
  echo "review_checks: not run: $1 ($2)" >&2; [ -z "${hubtool:-}" ] || add "$hubtool" "" 0 not-checked "$2"
  [ "$2" = "not installed" ] && return 0
  [ -n "${hubtool:-}" ] || add "$1" "" 0 not-checked "$2"
  case " $missing " in *" $1 "*) return 0 ;; esac
  failed+=" $1"; case ", $nr, " in *", $1 ($2), "*) ;; *) nr+="${nr:+, }$1 ($2)" ;; esac
}
# Run "$@" under a timebox; stdout+stderr -> $out. perl alarm when no timeout(1) (stock macOS); a failed exec exits 127 (never a silent 0).
tbox() {
  if command -v timeout >/dev/null; then timeout "$tmo" "$@" >"$out" 2>&1
  elif command -v gtimeout >/dev/null; then gtimeout "$tmo" "$@" >"$out" 2>&1
  else perl -e 'alarm shift; exec @ARGV or exit 127' "$tmo" "$@" >"$out" 2>&1; fi
}
# have TOOL: 0 when installed, else prints the not-run line.
# Heavy scanners take the machine-wide heavy lease (held by this shell) lazily, only once installed and about to run, so
# concurrent sessions queue instead of piling on; lease_drop frees it after the last one. Waits REVIEW_LEASE_WAIT s
# (default 120) then runs the scanner degraded and unleased (REVIEW_LEASE_FULL=skip: reports it skipped instead), so a
# busy host never leaves a security coverage hole. Fail open: no perun_policy.py (review-only install) or an
# unexpected exit from it (reported once) means no gate.
pp="$here/../../agentic-delivery/scripts/perun_policy.py"
lease_take() {
  [ "$leased" = 1 ] && return 0
  case $lease in none|degraded) return 0 ;; full) return 1 ;; esac # none: policy unusable (reported once), the scanner runs; degraded/full: already waited REVIEW_LEASE_WAIT
  [ -f "$pp" ] && command -v python3 >/dev/null || return 0
  local w=${REVIEW_LEASE_WAIT:-120} r
  while :; do
    # stdout to a file, not $(...): the lease pid is the caller's parent, which must stay this shell. A full lease is
    # exit 1 AND stdout "FULL"; python also exits 1 on any uncaught exception (traceback, no FULL), which is a policy failure.
    r=0; python3 "$pp" heavy-acquire >"$lf" 2>/dev/null || r=$?
    [ "$r" != 1 ] || [ "$(cat "$lf")" = FULL ] || r=70
    case "$r" in
      0) leased=1; return 0 ;;
      1) if [ "$w" -le 0 ]; then
           [ "${REVIEW_LEASE_FULL:-}" != skip ] || { lease=full; return 1; }
           echo "review_checks: heavy lease full after ${REVIEW_LEASE_WAIT:-120}s; heavy scanners run degraded without the lease (set REVIEW_LEASE_FULL=skip to skip them)" >&2; lease=degraded
           # nice unusable (missing, or sandbox setpriority EPERM warns on stderr): run degraded without it and without the "nice 19" label
           if np=$(nice -n 19 true 2>&1) && [ -z "$np" ]; then nice19=1; fi; return 0
         fi; sleep 5; w=$((w - 5)) ;;
      *) echo "review_checks: not run: lease (policy rc=$r); heavy scanners run without a lease" >&2; lease=none; return 0 ;;
    esac
  done
}
lease_drop() { [ "$leased" = 1 ] && { python3 "$pp" heavy-release >/dev/null 2>&1 || true; leased=0; }; true; }
# miss TOOL HINT: queue a tool that could not run (not installed, or its DB is blocked) for the closing "missing tools" row.
miss() { gap+="${gap:+; }$1 ($2)"; }
have() {
  command -v "$1" >/dev/null || {
    skip "$1" "not installed"; missing+=" $1"
    case "$1" in semgrep) miss "$1" "install: pipx install semgrep" ;; tsc) miss "$1" "install: npm install -g typescript" ;; *) miss "$1" "install: brew install $1" ;; esac
    return 1; }
  case "$1" in gitleaks|osv-scanner|semgrep|trivy) lease_take || { skip "$1" "heavy lease full"; return 1; } ;; esac
}
# add TOOL FILE LINE RULE MSG -> one TSV row.
add() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" >>"$raw"; }
# run_one TOOL CMD... : sets rc; returns 1 on timeout, with a not-run line unless it is semgrep with the p/default pack in its config (sgreg=1: the caller reruns with the bundled rules and reports that).
run_one() {
  local tool=$1 nz=(); shift; rc=0
  # lease full: heavy scanners run at lowest priority and are named in the summary (never take the lease while degraded)
  if [ "$lease" = degraded ]; then case $tool in gitleaks*|osv-scanner|semgrep|trivy|grype|checkov|gosec) [ "$nice19" != 1 ] || nz=(nice -n 19); case " $dg " in *" $tool "*) ;; *) dg+=" $tool" ;; esac ;; esac; fi
  [ -n "${hubtool:-}" ] || case " $ran " in *" $tool "*) ;; *) ran+=" $tool" ;; esac # hub tools count as ran only after a good parse
  tbox ${nz[@]+"${nz[@]}"} "$@" || rc=$?
  # degraded single-worker flag (semgrep --jobs 1, trivy --parallel 1) may be unsupported: after a crash retry once without it;
  # a good retry blames the flag, so the summary drops "1 worker" for this tool (--jobs/--parallel after a `--` are file names)
  case "$rc" in 0|124|142) ;; *) case " $w1 " in *" $tool "*)
    local a=(); while [ $# -gt 0 ]; do case "$1 ${2:-}" in "--jobs 1"|"--parallel 1") shift 2 ;; "-- "*) a+=("$@"); break ;; *) a+=("$1"); shift ;; esac; done
    rc=0; tbox ${nz[@]+"${nz[@]}"} "${a[@]}" || rc=$?
    [ "$rc" != 0 ] || w1=${w1/ $tool/} ;; esac ;; esac
  # a timed-out semgrep that still carries the registry pack is not "not run": the caller reruns with the bundled rules alone
  case "$rc" in 124|142) [ "$tool ${sgreg:-0}" = "semgrep 1" ] || skip "$tool" "timeout ${tmo}s"; return 1 ;; esac
  return 0
}
# scan_ok TOOL [OKRC...]: false (with a not-run line) when the last run_one exit code is not 0 or an OKRC (findings), i.e. a crash.
scan_ok() { local t=$1 c; shift; for c in 0 "$@"; do [ "$rc" = "$c" ] && return 0; done; skip "$t" "exit $rc"; return 1; }
# Findings parsed from $out by a sed script (TSV columns) land via `add`.
sh_files=$(changed '\.(sh|bash)$')
if [ -n "$sh_files" ]; then
  wiredx+=" shellcheck"
  if have shellcheck; then
    while IFS= read -r f; do
      run_one shellcheck shellcheck -f gcc "./$f" || continue
      scan_ok shellcheck 1 || continue
      sed -nE 's/^.*:([0-9]+):[0-9]+: [a-z]+: (.*) \[(SC[0-9]+)\]$/\1\t\3\t\2/p' "$out" |
        while IFS=$'\t' read -r l r m; do add shellcheck "$f" "$l" "$r" "$m"; done
    done <<<"$sh_files"
  fi
  while IFS= read -r f; do
    run_one bash-n bash -n "./$f" || continue
    [ "$rc" = 0 ] || add bash-n "$f" "$(sed -nE 's/.*line ([0-9]+):.*/\1/p' "$out" | head -n1)" syntax "$(head -n1 "$out")"
  done <<<"$sh_files"
fi

py_files=$(changed '\.py$')
if [ -n "$py_files" ]; then
  if have python3; then
    while IFS= read -r f; do
      run_one py_compile python3 -c 'import sys;compile(open(sys.argv[1],"rb").read(),sys.argv[1],"exec")' "./$f" || continue
      [ "$rc" = 0 ] || add py_compile "$f" "$(sed -nE 's/.*[(,] ?line ([0-9]+).*/\1/p' "$out" | head -n1)" SyntaxError "$(tail -n1 "$out")"
    done <<<"$py_files"
  fi
  lint=()
  if command -v ruff >/dev/null; then lint=(ruff check --output-format concise --no-cache) ln=ruff
  elif command -v pyflakes >/dev/null; then lint=(pyflakes) ln=pyflakes
  elif python3 -m pyflakes --version >/dev/null 2>&1; then lint=(python3 -m pyflakes) ln=pyflakes
  else skip "ruff/pyflakes" "not installed"; ln=; fi
  wiredx+=" ${ln:-ruff/pyflakes}"
  if [ -n "$ln" ]; then
    while IFS= read -r f; do
      run_one "$ln" "${lint[@]}" "./$f" || continue
      scan_ok "$ln" 1 || continue
      sed -nE 's/^.*:([0-9]+):[0-9]+:? ([A-Z]+[0-9]+ )?(.*)$/\1\t\2\t\3/p' "$out" |
        while IFS=$'\t' read -r l r m; do add "$ln" "$f" "$l" "${r% }" "$m"; done
    done <<<"$py_files"
  fi
fi

js_files=$(changed '\.(js|mjs|cjs)$')
if [ -n "$js_files" ] && have node; then
  while IFS= read -r f; do
    run_one node-check node --check "./$f" || continue
    [ "$rc" = 0 ] || add node-check "$f" "$(sed -nE 's/^.*:([0-9]+)$/\1/p' "$out" | head -n1)" SyntaxError "$(grep -m1 'Error' "$out" || head -n1 "$out")"
  done <<<"$js_files"
fi

# tsc: PATH first, else $PWD or the git toplevel's node_modules/.bin/tsc (never a parent above it: that is an unrelated binary).
# A repo-local tsc is project code (plugins, tsconfig), same class as REVIEW_TEST_CMD: it runs only when REVIEW_TEST_CMD is set.
tscbin=tsc
if ! command -v tsc >/dev/null; then
  top=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)
  for d in "$PWD" "$top"; do [ -n "$d" ] && [ -x "$d/node_modules/.bin/tsc" ] && { tscbin=$d/node_modules/.bin/tsc; break; }; done
  if [ "$tscbin" != tsc ] && [ -z "${REVIEW_TEST_CMD:-}" ] && [ -n "$(changed '\.(ts|tsx)$')" ] && [ -f tsconfig.json ]; then
    skip tsc "repo-local tsc not run (set REVIEW_TEST_CMD to run it: it executes project code)"; tscbin=
  fi
fi
if [ -n "$(changed '\.(ts|tsx)$')" ] && [ -f tsconfig.json ] && [ -n "$tscbin" ] && have "$tscbin"; then
  if run_one tsc "$tscbin" --noEmit -p tsconfig.json && scan_ok tsc 1 2; then
    sed -nE 's/^(.*)\(([0-9]+),[0-9]+\): error (TS[0-9]+): (.*)$/\1\t\2\t\3\t\4/p' "$out" |
      while IFS=$'\t' read -r f l r m; do add tsc "$f" "$l" "$r" "$m"; done
  fi
fi

if [ -n "$(changed '\.go$')" ] && [ -f go.mod ] && have go; then
  if run_one go-vet go vet ./... && scan_ok go-vet 1; then
    sed -nE 's/^([^#[:space:]][^:]*\.go):([0-9]+):[0-9]+: (.*)$/\1\t\2\t\3/p' "$out" |
      while IFS=$'\t' read -r f l m; do add go-vet "$f" "$l" vet "$m"; done
  fi
fi

json_files=$(changed '\.json$')
if [ -n "$json_files" ] && have jq; then
  while IFS= read -r f; do
    run_one jq jq empty "./$f" || continue
    [ "$rc" = 0 ] || add jq "$f" "$(sed -nE 's/.*line ([0-9]+).*/\1/p' "$out" | head -n1)" invalid-json "$(head -n1 "$out")"
  done <<<"$json_files"
fi

# Scanner JSON (file $2, may have log noise before the JSON) of kind $1 -> TSV: file, line, rule, message.
# Fails closed: missing, empty or malformed JSON exits non-zero instead of reading as "no findings".
sjson() {
  python3 - "$1" "$2" <<'PY'
import hashlib, json, os, pathlib, re, sys
kind = sys.argv[1]
def nf(f):  # scanners echo the path they were given ("./.github/..."); rows must carry the changed-file form
    return os.path.normpath(f) if f else f
t = open(sys.argv[2], encoding="utf-8", errors="replace").read()
i = min([x for x in (t.find("{"), t.find("[")) if x >= 0], default=-1)
if i < 0:
    sys.exit("sjson: no JSON in scanner output")
d = json.JSONDecoder().raw_decode(t[i:])[0]
# Wrong-shape JSON must not read as clean: gitleaks is a list, semgrep and osv an object with a "results" list.
if kind == "gitleaks":
    if not isinstance(d, list):
        sys.exit("sjson: gitleaks report is not a list")
elif kind.startswith("trivy"):
    if not isinstance(d, dict):
        sys.exit("sjson: trivy output is not an object")
elif kind == "audit":  # npm audit (vulnerabilities), pnpm audit (advisories), pip-audit (dependencies)
    if not isinstance(d, dict) or not any(isinstance(d.get(k), (dict, list)) for k in ("vulnerabilities", "advisories", "dependencies")):
        sys.exit("sjson: audit output has no vulnerabilities, advisories or dependencies")
elif kind in ("zizmor", "hadolint", "actionlint"):
    if not isinstance(d, list):
        sys.exit(f"sjson: {kind} output is not a list")
elif kind in ("gosec", "grype"):
    k = "Issues" if kind == "gosec" else "matches"
    if not isinstance(d, dict) or not (isinstance(d.get(k), list) or (kind == "gosec" and k in d and d[k] is None)):
        sys.exit(f"sjson: {kind} output has no {k} list")
    if kind == "gosec" and d.get("Golang errors"):  # package load errors leave Issues empty: -no-fail hides them
        sys.exit("sjson: gosec reported Golang errors")
elif kind == "checkov":
    ds = d if isinstance(d, list) else [d]
    # Nothing applicable to check (empty or variables-only .tf): checkov prints a flat summary with no "results", which is a clean file, not unparseable output.
    ds = [{"results": {}} if isinstance(x, dict) and "results" not in x and x.get("parsing_errors") == 0 and x.get("failed") == 0 else x for x in ds]
    if not ds or not all(isinstance(x, dict) and isinstance(x.get("results"), dict) for x in ds):
        sys.exit("sjson: checkov output has no results object")
    if any(x["results"].get("parsing_errors") for x in ds):  # an unparsed file must not read as clean
        sys.exit("sjson: checkov could not parse the file")
elif not isinstance(d, dict) or not isinstance(d.get("results"), list):
    sys.exit(f"sjson: {kind} output has no results list")
rows = []
if kind == "gitleaks":  # Secret/Match fields are deliberately never read
    # Rewrite-proof allowlist: "rule path-glob sha256(secret)" lines (not the commit fingerprint, which a history rewrite breaks).
    # Fail closed: any unreadable or malformed line voids the whole list and every finding is kept.
    al = []
    try:
        for l in open(os.environ.get("GL_ALLOW") or os.devnull, encoding="utf-8"):
            if l.strip() and not l.lstrip().startswith("#"):
                a = l.split()
                if len(a) != 3 or not re.fullmatch(r"[0-9a-fA-F]{64}", a[2]) or a[2].lower() == hashlib.sha256(b"").hexdigest():
                    raise ValueError(l.strip()[:40])
                al.append((a[0], a[1], a[2].lower()))
    except (ValueError, OSError) as e:  # UnicodeDecodeError is a ValueError
        print(f"review_checks: .gitleaks-allow ignored, malformed ({type(e).__name__}); all findings kept", file=sys.stderr)
        al = []
    def rx(g):  # segment-aware: * and ? stop at /, ** crosses it
        return re.compile(re.sub(r"\*\*|\*|\?|[^*?]+", lambda m: {"**": ".*", "*": "[^/]*", "?": "[^/]"}.get(m[0]) or re.escape(m[0]), g) + r"\Z")
    def allowed(r):
        sec = r.get("Secret") or ""
        if not sec:
            return False
        h = hashlib.sha256(sec.encode()).hexdigest()
        f = (r.get("File") or "").removeprefix("./")
        return any(a[0] == r.get("RuleID") and a[2] == h and rx(a[1]).match(f) for a in al)
    ign = set()  # .gitleaksignore: one fingerprint per line, "#" comments; unreadable -> keep every finding
    try:
        ign = {l.strip().removeprefix("./") for l in open(os.environ.get("GL_IGNORE") or os.devnull, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")}
    except (ValueError, OSError):
        print("review_checks: .gitleaksignore unreadable; all findings kept", file=sys.stderr)
    kept = [r for r in d if not allowed(r) and (r.get("Fingerprint") or "").removeprefix("./") not in ign]
    if len(kept) < len(d):
        print(f"review_checks: .gitleaks-allow/.gitleaksignore suppressed {len(d) - len(kept)} finding(s)", file=sys.stderr)
    rows = [(r.get("File"), r.get("StartLine"), r.get("RuleID"), r.get("Description") or "secret detected") for r in kept]
elif kind.startswith("trivy"):
    for r in d.get("Results") or []:  # Secrets only in the secret-only fallback, and never the Match (it would leak the value)
        if kind == "trivy-secret": rows += [(r["Target"], s.get("StartLine", 0), s.get("RuleID"), s.get("Title", "secret detected")) for s in r.get("Secrets") or []]
        rows += [(r["Target"], 0, v.get("VulnerabilityID"), f"{v.get('PkgName')}@{v.get('InstalledVersion')}: {v.get('Title', '')}") for v in r.get("Vulnerabilities") or []]
        rows += [(r["Target"], (m.get("CauseMetadata") or {}).get("StartLine", 0), m.get("ID"), m.get("Title", "")) for m in r.get("Misconfigurations") or []]
elif kind == "audit":
    # "-" placeholders: the caller's `read` collapses empty leading TSV fields; it supplies the lockfile path itself
    rows += [("-", 0, k, f"{v.get('severity')}: {v.get('name', k)}") for k, v in (d.get("vulnerabilities") or {}).items()]
    rows += [("-", 0, a.get("github_advisory_id") or k, f"{a.get('severity')}: {a.get('module_name')}: {a.get('title', '')}") for k, a in (d.get("advisories") or {}).items()]
    rows += [("-", 0, v.get("id"), f"{p.get('name')}@{p.get('version')}") for p in d.get("dependencies") or [] for v in p.get("vulns") or []]
elif kind == "zizmor":  # row is 0-based in json-v1; fixes and snippets are never read
    for x in d:
        l = ((x.get("locations") or [{}])[0])
        f = (((l.get("symbolic") or {}).get("key") or {}).get("Local") or {}).get("verbatim_path")
        r = (((l.get("concrete") or {}).get("location") or {}).get("start_point") or {}).get("row", -1)
        rows.append((nf(f), r + 1, x.get("ident"), x.get("desc", "")))
elif kind == "bandit":  # issue_text (B105 embeds the secret) and code are never read
    rows = [(os.path.relpath(r["filename"]), r.get("line_number", 0), r.get("test_id"), "potential issue (see the bandit docs for this test id)") for r in d["results"]]
elif kind == "gosec":
    for r in d["Issues"] or []:
        ln = str(r.get("line", "0")).split("-")[0]
        rows.append((os.path.relpath(r["file"]), int(ln) if ln.isdigit() else 0, r.get("rule_id"), r.get("details", "")))
elif kind == "grype":  # file comes from the caller (it scanned one target); "-" placeholder: the caller's `read` collapses an empty leading field
    for m in d["matches"]:
        v, a = m.get("vulnerability") or {}, m.get("artifact") or {}
        rows.append(("-", 0, v.get("id"), f"{a.get('name')}@{a.get('version')}: {(v.get('description') or '')[:200]}"))
elif kind == "checkov":  # code_block is never read; "-" placeholder as for grype
    for x in ds:
        for c in x["results"].get("failed_checks") or []:
            rows.append(("-", (c.get("file_line_range") or [0])[0], c.get("check_id"), c.get("check_name", "")))
elif kind == "hadolint":
    rows = [(r.get("file"), r.get("line", 0), r.get("code"), r.get("message", "")) for r in d]
elif kind == "actionlint":  # snippet is never read; the rule is actionlint's error kind
    rows = [(nf(r.get("filepath")), r.get("line", 0), r.get("kind"), r.get("message", "")) for r in d]
elif kind == "semgrep":
    # semgrep prefixes every rule id with the dotted directory of the config file that defines it, which leaks the local path into reports: strip it.
    # pfx mirrors semgrep's own convert_config_id_to_prefix; ids with no such prefix (registry rules) never match, so nothing is cut.
    def pfx(f):
        p = pathlib.Path(f)
        try: p = p.relative_to(pathlib.Path.cwd())
        except ValueError: pass
        s = ".".join(p.parts[:-1]).lstrip("./").lstrip(".")
        return re.sub(r"[^a-zA-Z0-9._-]", "", s + "." if s else "")
    fs = []
    for c in filter(None, os.environ.get("SG_CFG", "").split("\n")):
        fs += [os.path.join(a, "x") for a, _, _ in os.walk(c)] if os.path.isdir(c) else [c]
    ps = sorted({pfx(f) for f in fs} - {""}, key=len, reverse=True)
    cid = lambda i: next((i[len(q):] for q in ps if isinstance(i, str) and i.startswith(q)), i)
    rows = [(r["path"], r["start"]["line"], cid(r.get("check_id")), (r.get("extra") or {}).get("message", "")) for r in d["results"]]
else:
    for r in d["results"]:
        for p in r.get("packages") or []:
            pk = p.get("package") or {}
            rows += [(r["source"]["path"], 0, v.get("id"), f"{pk.get('name')}@{pk.get('version')}: {v.get('summary', '')}")
                     for v in p.get("vulnerabilities") or []]
for row in rows:
    print("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in row))
err = kind == "semgrep" and d.get("errors")
if err and not rows:  # errors and no findings: partial when some scanned file raised no error, else exit 4 (nothing usable was scanned)
    bad = {e.get("path") if isinstance(e, dict) else None for e in err}
    sys.exit(3 if None not in bad and len(set((d.get("paths") or {}).get("scanned") or [])) > len(bad) else 4)
sys.exit(3 if err else 0)  # 3 = the scan was partial (rows may be empty); 4 = errors on every scanned file and no rows
PY
}

if have gitleaks; then
  # Content-hash allowlist (templates/gitleaks.toml): trusted only as of BASE, so a change cannot approve its own secret.
  # A missing file or unresolvable base means an empty list; an entry the change adds or edits is itself a finding.
  export GL_ALLOW=$gla; git show "$ref:.gitleaks-allow" >"$gla" 2>/dev/null || : >"$gla"
  if [ -f .gitleaks-allow ] && ! cmp -s .gitleaks-allow "$gla"; then add gitleaks .gitleaks-allow 0 allowlist-changed "allowlist differs from $ref; the change's entries are NOT applied, review them"; fi
  # .gitleaksignore (fingerprints) is likewise read as of BASE (HEAD under --full), never from the working tree.
  export GL_IGNORE=$gli; git show "$ref:.gitleaksignore" >"$gli" 2>/dev/null || : >"$gli"
  glcfg=(); [ -f .gitleaks.toml ] || glcfg=(--config "$here/../templates/gitleaks.toml") # no repo config: use the allowlist template
  if [ ${#glcfg[@]} -gt 0 ]; then # say what the template hides, so a skipped file is never silent
    skipped=$(printf '%s\n' "$files" | grep -cE "$(sed -n "s/^  '''\(.*\)''',\$/\1/p" "$here/../templates/gitleaks.toml" | paste -sd'|' -)" || true)
    [ "${skipped:-0}" -eq 0 ] || echo "review_checks: gitleaks template skipped $skipped changed file(s) under .history/, fixtures/, testdata/ or generated registry JSON" >&2
  fi
  if [ "$wr" = 1 ]; then # one batched scan of the working tree; only tracked, non-vendored files are reported
    : >"$rep"; glw=$td/glw # extend the config; skip vendored trees at scan time
    printf '[extend]\npath = "%s"\n[allowlist]\npaths = [\x27\x27\x27(^|/)(node_modules|vendor|\\.claude/worktrees)/\x27\x27\x27]\n' "${glcfg[1]:-$PWD/.gitleaks.toml}" >"$glw"
    if run_one gitleaks gitleaks detect --config "$glw" --gitleaks-ignore-path "$gli" --no-git --no-banner --exit-code 0 -f json -r "$rep" -s . && scan_ok gitleaks; then
      [ -s "$rep" ] || echo '[]' >"$rep"
      if sjson gitleaks "$rep" >"$tsv"; then
        while IFS=$'\t' read -r f l r m; do f=${f#./}; grep -qxF -- "$f" "$td/files" && add gitleaks "$f" "$l" "$r" "$m"; done <"$tsv"
      else skip gitleaks "unparseable report; secrets were not scanned"; fi
    fi
  else
    while IFS= read -r f; do
      [ -f "$f" ] || continue
      : >"$rep" # a stale report from the previous file must never be read for this one
      run_one gitleaks gitleaks detect ${glcfg[@]+"${glcfg[@]}"} --gitleaks-ignore-path "$gli" --no-git --no-banner --exit-code 0 -f json -r "$rep" -s "./$f" || continue
      scan_ok gitleaks || continue
      [ -s "$rep" ] || echo '[]' >"$rep" # gitleaks may leave an empty report for a clean file
      sjson gitleaks "$rep" >"$tsv" || { skip gitleaks "unparseable report for $f"; continue; }
      while IFS=$'\t' read -r _ l r m; do add gitleaks "$f" "$l" "$r" "$m"; done <"$tsv"
    done <<<"$files"
  fi
  if [ "$hist" = 1 ]; then # history: the commits BASE..HEAD adds, not just the final file state (never BASE...HEAD: that also scans every BASE-only commit when HEAD is behind)
    : >"$rep"
    lo=(--log-opts "$base..HEAD"); [ "$full" = 0 ] || lo=() # default: only the commits since BASE (default origin/main, never a possibly stale local main)
    if run_one gitleaks-history gitleaks detect --no-banner --exit-code 0 -f json -r "$rep" ${lo[@]+"${lo[@]}"} -s . && scan_ok gitleaks-history; then
      [ -s "$rep" ] || echo '[]' >"$rep"
      if sjson gitleaks "$rep" >"$tsv"; then while IFS=$'\t' read -r f l r m; do [[ $f =~ $XRE ]] || add gitleaks-history "$f" "$l" "$r" "$m"; done <"$tsv"
      else skip gitleaks-history "unparseable report"; fi
    fi
  fi
elif [ -n "$files" ]; then add gitleaks "" 0 not-checked "not installed or heavy lease full; secrets were not scanned"; fi

lock_files=$(changed '(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|Cargo\.lock|poetry\.lock|requirements[^/]*\.txt|composer\.lock)$')
[ -z "$lock_files" ] || wired+=" osv-scanner"
# osvdb: REVIEW_OSV_DB_DIR, else (unless REVIEW_OSV=1 picked the online API) the provisioned osv-scanner cache once it holds a DB (provision_tools.sh --cache osv also honours an exported OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY). A cache without a DB is never used: osv-scanner then prints empty results, not an error, which would read as clean. Only this block reads it, so the registry-audit fallback below stays opt-in.
osvdb=${REVIEW_OSV_DB_DIR:-} osvcold=
if [ -n "$osvdb" ]; then [ -n "$(find "$osvdb" -type f -name '*.zip' 2>/dev/null | head -n1)" ] || osvcold=1
elif [ "${REVIEW_OSV:-}" != 1 ]; then osvdb=$(bash "$here/provision_tools.sh" --cache osv 2>/dev/null) || osvdb=; fi
if [ -z "$lock_files" ]; then :
elif [ "${REVIEW_OSV:-}" != 1 ] && [ -z "$osvdb" ]; then miss osv-scanner "warm the offline DB: provision_tools.sh --print"; skip osv-scanner "REVIEW_OSV not set; osv-scanner queries the OSV API"
elif [ -n "$osvcold" ]; then
  miss osv-scanner "warm the DB: osv-scanner --offline-vulnerabilities --download-offline-databases"
  skip osv-scanner "NOT CHECKED: no pre-seeded DB in REVIEW_OSV_DB_DIR=$osvdb; warm it once: OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$osvdb osv-scanner --offline-vulnerabilities --download-offline-databases ."
elif have osv-scanner; then
  # osvdb: pre-seeded DB, offline run (no TLS to api.osv.dev); the cache-dir env is osv-scanner's documented one.
  osvx=(); [ -z "$osvdb" ] || { export OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$osvdb; osvx=(--offline-vulnerabilities); }
  while IFS= read -r f; do
    run_one osv-scanner osv-scanner ${osvx[@]+"${osvx[@]}"} --format json -L "./$f" || continue
    if [ "$rc" = 127 ] && grep -q 'no offline version' "$out"; then case "$gap" in *"osv-scanner ("*) ;; *) miss osv-scanner "no offline DB for the ecosystem of $f: run bash $here/provision_tools.sh --print $PWD" ;; esac; fi
    scan_ok osv-scanner 1 || continue # exit 1 = vulnerabilities found
    sjson osv "$out" >"$tsv" || { skip osv-scanner "unparseable output for $f"; continue; }
    cov+="$f"$'\n'; while IFS=$'\t' read -r _ l r m; do add osv-scanner "$f" "$l" "$r" "$m"; done <"$tsv"
  done <<<"$lock_files"
fi

sgc=${REVIEW_SEMGREP_CONFIG:-}
[ -n "$sgc" ] || for c in .semgrep.yml .semgrep; do [ -e "$c" ] && { sgc=$c; break; }; done
sgcfg=(--config "$sgc") sgsnap=
if [ -z "$sgc" ]; then # no repo rules: bundled taint rules, plus the p/default registry pack unless REVIEW_SEMGREP_REGISTRY=0 (never --config auto)
  sgc=$here/../templates/semgrep-taint; sgcfg=(--config "$sgc")
  # the provisioned snapshot (a local file) stands in for p/default when present, so it loads without the network
  [ "${REVIEW_SEMGREP_REGISTRY:-1}" = 0 ] || { sgsnap=$(bash "$here/provision_tools.sh" --cache semgrep 2>/dev/null || echo p/default); sgcfg+=(--config "$sgsnap"); }
fi
sgnorm=$sgc; [ ! -f "$sgsnap" ] || sgnorm+=$'\n'$sgsnap # semgrep prefixes rule ids with each local config's directory (the bundled rules, a warm snapshot): sjson strips every one listed
if [ ! -e "$sgc" ]; then
  if [ -z "${REVIEW_SEMGREP_CONFIG:-}" ] && [ "$sgc" = "$here/../templates/semgrep-taint" ]; then skip semgrep "bundled rules missing at $sgc (reinstall the skill)"
  else skip semgrep "REVIEW_SEMGREP_CONFIG must be an existing local path"; fi
elif have semgrep; then
  sg=() sgwas=$ran sgok=0 sgerr=0 sgj=() sgb=0 sgrx=0 sgbun=(--config "$sgc"); [ "$lease" != degraded ] || { sgj=(--jobs 1); w1+=" semgrep"; }
  while IFS= read -r f; do [ -f "$f" ] && sg+=("$f"); done <<<"$files"
  # sgrun CONFIG...: scan one chunk. sgreg=1 (seen by run_one) while the p/default pack (registry or snapshot) is in CONFIG (4 args, not 2), so its timeout is soft: the loop reruns with the bundled rules.
  sgrun() { local sgreg=0; [ $# -le 2 ] || sgreg=1; run_one semgrep env HOME="$sgh" XDG_CACHE_HOME="$sgh" SEMGREP_USER_HOME="$sgh" semgrep "$@" ${sgj[@]+"${sgj[@]}"} --json --quiet --metrics=off --disable-version-check -- "${sg[@]:i:200}"; }
  # One call per 200 files: typically a single run, but bounded argv and a timeout that is not shared by everything.
  for ((i = 0; i < ${#sg[@]}; i += 200)); do
    sgr=0; [ ${#sgcfg[@]} -le 2 ] || sgr=1 # the p/default pack (the registry, or the provisioned snapshot standing in for it) is still in this chunk's config
    sgrun "${sgcfg[@]}" || [ "$sgr" = 1 ] || continue
    if [ "$sgr" = 1 ] && [ "$rc" = 0 ]; then sgrx=1
    elif [ "$sgr" = 1 ]; then # pack not loaded (error, offline, a bad snapshot, or a proxy that hangs to the timeout): the one report of the gap, then rerun this chunk with the bundled rules alone
      case $rc in 124|142) sgwhy="timeout ${tmo}s" ;; *) sgwhy="exit $rc" ;; esac
      sgfix="warm a local snapshot: bash $here/provision_tools.sh --print"
      echo "review_checks: not run: semgrep p/default pack ($sgwhy); bundled rules only ($sgfix)" >&2
      add semgrep "" 0 not-checked "p/default registry pack not run ($sgwhy); bundled rules only for the affected files ($sgfix)"
      case ", $nr, " in *", semgrep p/default pack ($sgwhy), "*) ;; *) nr+="${nr:+, }semgrep p/default pack ($sgwhy)" ;; esac
      sgb=1; [ "$sgrx" = 1 ] || sgcfg=("${sgbun[@]}") # later chunks skip the pack only while no pack run has succeeded
      sgrun "${sgbun[@]}" || continue
    fi
    scan_ok semgrep || continue
    [ "$sgb" = 0 ] || case " $ran " in *" semgrep(bundled-only) "*) ;; *) ran+=" semgrep(bundled-only)" ;; esac
    e=0; SG_CFG=$sgnorm sjson semgrep "$out" >"$tsv" || e=$?
    if [ "$e" = 4 ]; then sgerr=$((sgerr + 1)) # errors on every scanned file and no results: nothing usable from this chunk; judged after the loop
    elif [ "$e" = 0 ] || [ "$e" = 3 ]; then
      sgok=1
      while IFS=$'\t' read -r p l r m; do add semgrep "$p" "$l" "$r" "$m"; done <"$tsv"
      # a "(note)" token in ran is a partial scope: the closing line and the record list it apart from a full run
      [ "$e" = 0 ] || { echo "review_checks: partial: semgrep ran but reported errors (coverage incomplete; findings above are real)" >&2; case " $ran " in *" semgrep(errors) "*) ;; *) ran+=" semgrep(errors)" ;; esac; }
    else skip semgrep "unparseable output"; fi
  done
  if [ "$sgerr" -gt 0 ] && [ "$sgok" = 1 ]; then # other chunks scanned fine: partial coverage, not a voided tool
    echo "review_checks: partial: semgrep errored with no findings on $sgerr chunk(s) of up to 200 files (those files were not scanned)" >&2
    add semgrep "" 0 not-checked "semgrep errored on $sgerr chunk(s) of up to 200 files; those files were not scanned"
  elif [ "$sgerr" -gt 0 ]; then ran=$sgwas; skip semgrep "scan errored, no findings"; fi
fi

# trivy: offline against the cached DB (no download); no DB or any crash reads as not-run, never as clean.
# If the vuln+misconfig scan fails (check bundle unreachable in the sandbox), retry secret-only and say so.
if [ -n "$files" ] && have trivy; then
  tv=(trivy fs --quiet --format json --skip-version-check --skip-db-update --offline-scan --skip-dirs node_modules,.claude/worktrees,vendor,dist,build,.git,.venv,venv,target)
  tk=trivy; [ "$lease" != degraded ] || { tv+=(--parallel 1); w1+=" trivy"; }
  # REVIEW_TRIVY_CACHE: pre-seeded --cache-dir. A missing DB stays "not run" (never clean) and prints the one-line warm command.
  # Else the cache provision_tools.sh --print warms, once it holds a DB (DCR_CACHE_ROOT moves it off trivy's own default dir, so it must be passed).
  if [ -n "${REVIEW_TRIVY_CACHE:-}" ]; then tv+=(--cache-dir "$REVIEW_TRIVY_CACHE")
  elif tvc=$(bash "$here/provision_tools.sh" --cache trivy 2>/dev/null); then tv+=(--cache-dir "$tvc"); fi
  trivy_hint="warm the DB once: trivy ${REVIEW_TRIVY_CACHE:+--cache-dir $REVIEW_TRIVY_CACHE }image --download-db-only (or bash $here/provision_tools.sh --print)"
  if run_one trivy "${tv[@]}" --scanners vuln,misconfig . && { [ "$rc" = 0 ] || {
    if ! grep -Eqi 'vulnerability db|trivy-db|download.* db( |$)' "$out" && grep -Eqi 'dial |no such host|connection (refused|reset)|unreachable|x509|TLS|failed to download|download.*(bundle|check)|(bundle|check).*download' "$out"; then
      echo "review_checks: trivy: secret-only (misconfig bundle unreachable)" >&2; tk=trivy-secret; ran+=" trivy(secret-only)"
      run_one trivy "${tv[@]}" --skip-check-update --scanners secret .
    fi; }; } && { scan_ok trivy || { grep -qi 'DB' "$out" && { echo "review_checks: trivy: NOT CHECKED, $trivy_hint" >&2; miss trivy "$trivy_hint"; }; false; }; }; then
    if sjson "$tk" "$out" >"$tsv"; then
      if [ "$tk" = trivy ]; then # covered = lockfiles trivy reported a Target for (a secret-only run covers none)
        while IFS= read -r f; do grep -Fq "\"Target\":\"$f\"" "$out" || grep -Fq "\"Target\": \"$f\"" "$out" && cov+="$f"$'\n'; done <<<"$lock_files"
      fi
      while IFS=$'\t' read -r f l r m; do grep -qxF -- "$f" "$td/files" && add trivy "$f" "$l" "$r" "$m"; done <"$tsv"
    else skip trivy "unparseable output"; fi
  fi
fi

# Dependency-scan fallback: per lockfile with no osv-scanner/trivy result (DB unreachable, not installed, lease full) -> the
# ecosystem's own audit (opt-in like osv: REVIEW_OSV=1 or REVIEW_OSV_DB_DIR; it queries the registry). The audit runs on a
# copy of the lockfile in an empty temp dir with the public registry and no user/global npmrc, so a repo .npmrc registry or
# credentials are never read; pip-audit gets --no-deps --disable-pip (no resolver, no venv, no target code). The row names
# the tool that ran; a lockfile with no dependency scan at all is a not-checked row, never silent clean.
# npm_config_cache defaults to a per-run dir under that temp dir (a root-owned ~/.npm cache makes npm audit fail EPERM; pnpm keeps its own store/cache-dir, so this covers npm only); an exported value wins.
# ponytail: a temp-dir copy drops workspace context (pnpm-workspace.yaml, -r includes); such audits fail into not-checked.
if [ -n "$lock_files" ]; then
  while IFS= read -r f; do
    ! printf '%s' "$cov" | grep -qxF -- "$f" || continue
    at=(); case ${f##*/} in
      package-lock.json) at=(npm audit --package-lock-only --json) ;;
      pnpm-lock.yaml) at=(pnpm audit --json) ;;
      requirements*.txt) at=(pip-audit -r "${f##*/}" --no-deps --disable-pip --format json) ;;
    esac
    if [ ${#at[@]} -eq 0 ]; then add dep-scan "$f" 0 not-checked "no dependency scan ran for this lockfile (no osv-scanner/trivy result and no fallback for its ecosystem)"
    elif [ "${REVIEW_OSV:-}" != 1 ] && [ -z "${REVIEW_OSV_DB_DIR:-}" ]; then add dep-scan "$f" 0 not-checked "no dependency scan ran; set REVIEW_OSV=1 to scan (osv-scanner, else ${at[0]})"
    elif ! command -v "${at[0]}" >/dev/null; then miss "${at[0]}" "install it: dependency-scan fallback for $f"; add dep-scan "$f" 0 not-checked "no dependency scan ran: osv-scanner/trivy gave no result and ${at[0]} is not installed"
    else
      ad=$(mktemp -d "$td/review-aud.XXXXXX"); cp "$f" "$ad/"; [ ! -f "$(dirname "$f")/package.json" ] || cp "$(dirname "$f")/package.json" "$ad/"
      was=$ran ok=0 # stdout only (stderr dropped in the wrapper, so noise cannot break the JSON parse); ran counts only after a good parse
      if run_one "${at[0]}" bash -c 'cd "$1" && shift && exec env npm_config_cache="${npm_config_cache:-$PWD/.npm-cache}" npm_config_userconfig=/dev/null npm_config_globalconfig=/dev/null npm_config_registry=https://registry.npmjs.org/ "$@" 2>/dev/null </dev/null' _ "$ad" "${at[@]}" && scan_ok "${at[0]}" 1 && sjson audit "$out" >"$tsv"; then ok=1; fi
      rm -rf "$ad"
      if [ "$ok" = 1 ]; then
        echo "review_checks: dependency scan: ${at[0]} ran for $f (fallback: osv-scanner/trivy gave no result)" >&2
        while IFS=$'\t' read -r _ l r m; do add "${at[0]}" "$f" "$l" "$r" "$m"; done <"$tsv"
      else ran=$was; add dep-scan "$f" 0 not-checked "no dependency scan ran: ${at[0]} failed or was unreachable"; fi
    fi
  done <<<"$lock_files"
fi

# Tool hub registry: name;flags status;mode;match (ERE on changed files);license class;install hint. One row per routed tool.
# Flags were checked against each tool's official docs (verified) or not (unverified: skipped by default). License class:
# route-only = never bundled, only run when the user installed it (licenses unchecked, so nothing is bundle-ok yet).
hub=(
  'zizmor;verified;batch;^\.github/workflows/[^/]+\.ya?ml$;route-only;pipx install zizmor'
  'actionlint;verified;batch;^\.github/workflows/[^/]+\.ya?ml$;route-only;brew install actionlint'
  'bandit;verified;batch;\.py$;route-only;pipx install bandit'
  'gosec;verified;batch;\.go$;route-only;go install github.com/securego/gosec/v2/cmd/gosec@latest'
  'grype;verified;each;(^|/)([^/]*[-_.])?(sbom|bom|cdx|spdx)([-_.][^/]*)?\.json$;route-only;brew install grype'
  'checkov;verified;each;(^|/)(Dockerfile[^/]*|[^/]+\.tf)$;route-only;pipx install checkov'
  'hadolint;verified;each;(^|/)(Dockerfile[^/]*|[^/]+\.dockerfile)$;route-only;brew install hadolint'
  'snyk-agent-scan;unverified;each;(^|/)(\.mcp\.json|mcp[^/]*\.json|SKILL\.md)$;route-only;uvx snyk-agent-scan'
)
# hubcmd TOOL TARGET...: sets cmd (argv), okrc (extra non-crash exit codes) and jf (file the JSON lands in).
hubcmd() {
  local t=$1; shift; jf=$out okrc=""
  case $t in
    zizmor) cmd=(zizmor --format=json --offline "$@"); okrc="11 12 13 14" ;; # 11-14 = findings (docs.zizmor.sh/usage)
    actionlint) cmd=(actionlint -format '{{json .}}' "$@"); okrc="1" ;; # exit 1 = findings, 2 = bad flag, 3 = fatal (actionlint -h; checked against a real run)
    bandit) cmd=(bandit -q -f json --exit-zero "$@") ;;
    gosec) jf=$rep; : >"$rep"; cmd=(env GOPROXY=off gosec -fmt=json -no-fail -out "$rep" ./...) ;;
    grype) cmd=(env GRYPE_DB_AUTO_UPDATE=false grype "sbom:$1" -o json) ;; # SBOM only: dir: scans the whole tree (unverified for lockfiles)
    checkov) cmd=(checkov -f "$1" -o json --quiet --skip-download --soft-fail) ;;
    hadolint) cmd=(hadolint -f json --no-fail "$1") ;;
  esac
}
while IFS=';' read -r hn hs hm hre _ hh; do
  hf=$(changed "$hre"); [ -n "$hf" ] || continue
  [ "$hs" != verified ] || wired+=" $hn"
  nc() { echo "NOT CHECKED: $hn ($1)" >&2; add "$hn" "" 0 not-checked "$1"; }
  if [ "$hs" != verified ]; then nc "$hs flags: skipped by default"; continue; fi
  command -v "$hn" >/dev/null || { nc "install: $hh"; missing+=" $hn"; miss "$hn" "install: $hh"; continue; }
  hubtool=$hn
  # zizmor, actionlint, bandit and hadolint are light (single-file static checks), so they are intentionally unleased.
  case $hn in grype|checkov|gosec) lease_take || { skip "$hn" "heavy lease full"; continue; } ;; esac
  [ "$hn" != gosec ] || [ -f go.mod ] || { nc "no go.mod at repo root"; continue; }
  targets=()
  if [ "$hm" = batch ]; then while IFS= read -r f; do targets+=("./$f"); done <<<"$hf"; fi
  # ponytail: batch tools get every matching file in one call (argv/timeout ceiling); chunk like semgrep if it bites.
  while IFS= read -r f; do
    if [ "$hm" = batch ]; then hubcmd "$hn" "${targets[@]}"; else
      hubcmd "$hn" "./$f"
    fi
    run_one "$hn" "${cmd[@]}" || { [ "$hm" = batch ] && break; continue; }
    scan_ok "$hn" $okrc || { [ "$hm" = batch ] && break; continue; }
    if sjson "$hn" "$jf" >"$tsv"; then
      case " $ran " in *" $hn "*) ;; *) ran+=" $hn" ;; esac
      if [ "$hm" = batch ]; then
        printf '%s\n' "$hf" >"$td/hf"; nraw=0 nout=0
        while IFS=$'\t' read -r p l r m; do
          nraw=$((nraw + 1)); grep -qxF -- "$p" "$td/hf" || continue
          nout=$((nout + 1)); add "$hn" "$p" "$l" "$r" "$m"
        done <"$tsv"
        # A tool given explicit files reports only those, so a row for any other file means the paths do not line up and findings may be lost:
        # name it instead of reading as clean. gosec scans ./... and legitimately reports files outside the changed list.
        [ "$hn" = gosec ] || [ "$nraw" = "$nout" ] || skip "$hn" "$((nraw - nout)) of $nraw rows named a file outside the scanned list; findings may be missing"
      else while IFS=$'\t' read -r _ l r m; do add "$hn" "$f" "$l" "$r" "$m"; done <"$tsv"; fi
    else skip "$hn" "unparseable output"; fi
    [ "$hm" != batch ] || break
  done <<<"$([ "$hm" = batch ] && echo x || printf '%s\n' "$hf")"
done < <(printf '%s\n' "${hub[@]}")
hubtool=

# Optional, --full only: tenant_scope_check.py (Prisma id-only where in server code); SKIPPED when the tree has no *.prisma.
if [ "$full" = 1 ]; then
  if [ -z "$(changed '\.prisma$')" ]; then skip tenant-scope "SKIPPED: no *.prisma"
  elif have python3 && run_one tenant-scope python3 -I "$here/tenant_scope_check.py" "$PWD" && scan_ok tenant-scope; then
    echo "tenant-scope: heuristic; scanned $(sed -nE 's/.*"server_files": ([0-9]+).*/\1/p' "$out" | tail -n1) server files; silence is not proof of tenant isolation" >&2
    while IFS=$'\t' read -r p l r m; do add tenant-scope "$p" "$l" "$r" "$m"; done < <(sed -nE 's/^(.+):([0-9]+): (HIGH|MED): ([^:]+): (.*)$/\1\t\2\t\4\t\5/p' "$out" | awk -F'\t' 'BEGIN{OFS=FS}{gsub(/ /,"-",$3)}1')
  fi
fi

lease_drop

# Built-in, no tool to install: NUL/C0 control and hidden/bidi characters in the changed text files (invisible_chars.py, the code
# scripts/audit_skills.py also uses). Cheap, so unleased. Rows: tool invisible-chars, rule control-char|hidden-unicode|not-checked, message has the codepoint and col.
ic="$here/invisible_chars.py"; cf=$(changed '.' | grep -Ev '(^|/)(third_party|Pods|bower_components)/|\.min\.js$' || true)
if [ -n "$cf" ]; then
  if [ ! -f "$ic" ]; then skip invisible-chars "invisible_chars.py missing"  # skip adds the not-checked row
  else
    icok=0; run_one invisible-chars python3 "$ic" <<<"$cf" && scan_ok invisible-chars && icok=1
    # rows are flushed per row, so a timeout still yields the findings made so far (a crash leaves a traceback in $out, not rows); the timeout/crash not-checked row comes from skip
    if [ "$icok" = 1 ] || [ "$rc" = 124 ] || [ "$rc" = 142 ]; then while IFS=$'\t' read -r f l r m; do add invisible-chars "$f" "$l" "$r" "$m"; done <"$out"; fi
  fi
fi

# Built-in, no tool to install: distinct non-reserved email addresses per changed file, binary data files included (committed_personal_data.py), over the same $cf as invisible-chars (vendored paths skipped). Cheap, so
# unleased: it reads each file's bytes once (capped at 32 MiB). Rows: tool committed-data, rule email-addresses|not-checked (the row with path `.` is the repository total over files below the file threshold); the message has the count or the container format, never a value. Not tagged likely-fixture: a real address in a fixture is still a leak.
pd="$here/committed_personal_data.py"
if [ -n "$cf" ]; then
  if [ ! -f "$pd" ]; then skip committed-data "committed_personal_data.py missing"
  else
    pdok=0; run_one committed-data python3 "$pd" --stdin <<<"$cf" && scan_ok committed-data && pdok=1
    # flushed per row, as above: a timeout still yields the findings made so far
    if [ "$pdok" = 1 ] || [ "$rc" = 124 ] || [ "$rc" = 142 ]; then while IFS=$'\t' read -r f l r m; do add committed-data "$f" "$l" "$r" "$m"; done <"$out"; fi
  fi
fi

if [ "$tests" = 1 ]; then
  if [ -z "${REVIEW_TEST_CMD:-}" ]; then skip tests "REVIEW_TEST_CMD not set"
  elif run_one tests bash -c "$REVIEW_TEST_CMD"; then
    [ "$rc" = 0 ] || add tests "" 0 test-failed "REVIEW_TEST_CMD exited $rc: $(tail -n1 "$out")"
  fi
fi

r=; for t in $ran; do case " $failed " in *" ${t%%(*} "*) ;; *) r+=" $t" ;; esac; done; ran=$r
REVIEW_STATE="$(git rev-parse --git-common-dir)/review-checks-last.json" HERE="$here" python3 - "$raw" "$ran" "$missing" "$nex" "$dg" "$w1" "$nice19" "$wired" "$gap" "$wiredx" <<'PY'
import json, os, re, shlex, sys, time
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8", errors="replace")]
rows = [t for i, t in enumerate(rows) if t[3:4] != ["not-checked"] or t not in rows[:i]]  # a tool failing on N files is one not-checked row
# Triage hint, not a verdict (only big generic-api-key fixture groups collapse, below): a secret or hidden-character finding under a sample/fixture/test/mock/docs path is usually dummy data.
FXD = re.compile(r"(^|/)(fixtures?|samples?|examples?|tests?|__tests__|testdata|mocks?|__mocks__|docs?)/", re.I)  # whole directory segment
FXB = re.compile(r"(^|[._-])(fixture|sample|example|mock|test)s?([._-]|$)", re.I)  # file name only, so test-runner/ or sample-service/ stay untagged
def fx(p): return FXD.search(p) or FXB.search(p.rsplit("/", 1)[-1])
def row(t):
    d = {"file": t[1], "line": int(t[2]) if t[2].isdigit() else 0, "rule": t[3], "message": t[4], "text": f"{t[3]}: {t[4]}", "tool": t[0]}
    if t[0] in ("gitleaks", "gitleaks-history", "invisible-chars") and fx(t[1]):
        d["hint"] = "likely-fixture"; d["text"] += " [likely-fixture]"
    return d
# Low-confidence bucket: only generic-api-key (the low-signal rule) hits under a fixture DIRECTORY collapse, and only when a (tool, top fixture dir)
# group has more than 3; every other rule (stripe, github-pat, openai, anthropic, private-key, ...) and every name-only match stays a per-row finding.
# REVIEW_FIXTURE_ROWS=all (or ALL, 1, true) keeps every row.
LOW = {"generic-api-key"}
opt = os.environ.get("REVIEW_FIXTURE_ROWS", "").lower() in ("all", "1", "true")
def top(p):
    s = p.split("/")[:-1]; j = next(i for i, x in enumerate(s) if FXD.search(x + "/"))
    while j < len(s) and FXD.search(s[j] + "/"): j += 1
    return "/".join(s[:j]) + "/"
def summ(k, g):
    n = len(g); r = sorted((t[1], row(t)["line"]) for t in g)[:3]
    m = f"{n} generic-api-key hits under {k[1]} tagged likely-fixture (showing 3 of {n}; REVIEW_FIXTURE_ROWS=all for every row): {', '.join(f'{f}:{l}' for f, l in r)}"
    return {"file": k[1], "line": 0, "rule": "likely-fixture-summary", "message": m, "text": f"{k[0]}: {m} [likely-fixture]", "tool": k[0], "hint": "likely-fixture"}
data = [t for t in rows if len(t) == 5]
key = lambda t: not opt and t[0] in ("gitleaks", "gitleaks-history") and t[3] in LOW and FXD.search(t[1]) and (t[0], top(t[1]))
groups = {}
for t in data:
    if key(t): groups.setdefault(key(t), []).append(t)
out, done = [], set()
for t in data:
    k = key(t)
    if not k or len(groups[k]) <= 3: out.append(row(t))
    elif k not in done: done.add(k); out.append(summ(k, groups[k]))
print(json.dumps(out, indent=1))
n = len(out)
dg, w1 = sys.argv[5].split(), sys.argv[6].split()  # lease full: "1 worker" only for tools whose single-worker flag ran; "nice 19" only when nice worked
def lab(t):
    b = t.split("(")[0]
    return t + (f" (degraded: lease full{', nice 19' if sys.argv[7] == '1' else ''}{', 1 worker' if b in w1 else ''})" if b in dg else "")
print(f"review_checks: {n} findings; {sys.argv[4]} files excluded; analyzers ran: {', '.join(lab(t) for t in sys.argv[2].split()) or 'none'}; skipped (not installed): {', '.join(sys.argv[3].split()) or 'none'}", file=sys.stderr)
# "ran X / wired Y": wired = scanners with work in this run (their files matched); fixable = wired and either missing or running without a cache a provision warms.
# argv[10] (shellcheck, ruff/pyflakes, gitleaks-history) is wired too, but provision_tools.sh cannot install it, so it is never fixable.
wired = sys.argv[8].split()
allw = wired + sys.argv[10].split()
ranned = {t.split("(")[0] for t in sys.argv[2].split()}
notrun = [t for t in allw if t not in ranned]
partial = list(dict.fromkeys(t for t in sys.argv[2].split() if "(" in t))  # ran with a narrower scope: "trivy(secret-only)", "semgrep(errors)"
fixset = set(sys.argv[3].split()) | {g.split(" (")[0] for g in sys.argv[9].split("; ")}
if "semgrep(bundled-only)" in partial: fixset.add("semgrep")  # the p/default pack did not load (already reported under NOT RUN): a provisioned snapshot fixes it
fixable = [t for t in wired if t in fixset]
# a DIR makes the provision re-download the osv DB for this repo's ecosystems: a bare --print sees any one ecosystem's zip as warm and may emit nothing
prov = f"bash {os.environ['HERE']}/provision_tools.sh --print" + (f" {shlex.quote(os.getcwd())}" if "osv-scanner" in fixable else "")
print(f"review_checks: ran {len(allw) - len(notrun)} / wired {len(allw)} scanners" + (f"; not run: {', '.join(notrun)}" if notrun else "")
      + (f"; partial: {', '.join(partial)}" if partial else "") + (f"; fixable: {', '.join(fixable)} (run: {prov})" if fixable else ""), file=sys.stderr)
try:  # best effort: the sandbox may deny the write; perun_doctor.py reads this record
    with open(os.environ["REVIEW_STATE"], "w") as f:
        json.dump({"ts": int(time.time()), "wired": allw, "not_run": notrun, "fixable": fixable, "partial": partial}, f)
except OSError:
    pass
PY
echo "review_checks: NOT RUN: ${nr:-none}" >&2
[ -z "$gap" ] || echo "review_checks: missing tools: $gap" >&2
