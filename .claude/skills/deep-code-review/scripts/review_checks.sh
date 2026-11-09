#!/usr/bin/env bash
# review_checks.sh [--base REF] [--tests] [--history] [--full] [--hygiene] [--timeout SECS] — run local, read-only analyzers over the files
# changed since REF (default origin/main, compared as REF...HEAD) and print findings as a JSON array on
# stdout: [{"file","line","rule","message","text","tool"}]. `text` ("rule: message") is the key
# scripts/score_review.py matches on. Findings are LEADS: verify each against the code before reporting.
# Diff mode (not --full or --history) adds "new": true|false|null to every row: its file+line is on a line REF...HEAD adds (rename-aware; line 0 and file-level rows are false); null for every row in a file whose working copy differs from HEAD (edited, staged or not, or untracked), since most rows read the working tree and the diff reads commits. No row is ever dropped; if a git read for the flags fails, the key is omitted and stderr says so.
#
# Tools (linters, gitleaks, trufflehog, osv-scanner, semgrep, trivy): see references/method-situational.md. Each runs only when
# installed and only on matching changed files. Secrets are redacted and never printed; trufflehog runs offline (`--no-verification --no-update`) over the changed files (every tracked file under --full),
# 200 per call, with `--sarif`: unlike `--json` that output has no Raw, RawV2, Redacted or SecretParts, so a row carries the detector, file and line only; it skips the same template paths as gitleaks (no repo .gitleaks.toml) and retries a failed call file by file (a file that still fails is a not-checked row); osv-scanner runs offline on a warm DB (env REVIEW_OSV_DB_DIR, an exported OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY that already holds a seeded database,
# else the cache provision_tools.sh --print warms; no flag needed), or against the OSV API with env REVIEW_OSV=1 (network), and is not run with neither;
# a lockfile with no osv-scanner/trivy result falls back to npm/pnpm/pip-audit (opt-in: REVIEW_OSV=1 or REVIEW_OSV_DB_DIR; it queries the registry), else a not-checked row; trivy is offline (TRIVY_DISABLE_TELEMETRY=true stops its telemetry ping).
# semgrep uses repo rules, else the bundled taint rules plus the p/default pack (never `--config auto`; the local snapshot provision_tools.sh --print warms stands in for the registry pack when present).
# If that pack errors or hangs to the timeout, that 200-file chunk reruns with the bundled rules alone (the later chunks too, unless an earlier pack run succeeded) and the run says so, so it never reads as a
# full clean: `semgrep(bundled-only)` under analyzers ran (and under partial and fixable in the closing line), `semgrep p/default pack (<why>)` under NOT RUN and a not-checked row, with the fix named (a warm
# snapshot: provision_tools.sh --print). That is the only report of the gap: no separate "missing tools" row.
# Tool hub: zizmor, actionlint, bandit, gosec, grype, checkov, hadolint (snyk-agent-scan is unverified, skipped) run from one registry
# (`hub=`); a matching changed file with the tool missing prints "NOT CHECKED: <tool> (install: <hint>)" on stderr, never a silent clean.
# Built-in, always on, no install: invisible_chars.py flags NUL/C0 control characters and bidi/zero-width/tag characters in changed text files (tool `invisible-chars`, with line and col;
# rows under fixture/test paths carry `[likely-fixture]`; third_party/, Pods/, bower_components/ and *.min.js are skipped; a `not-checked` row is unchecked surface).
# Built-in too: committed_personal_data.py counts the distinct non-reserved email addresses in each changed file (third_party/, Pods/, bower_components/ and *.min.js are skipped, as for invisible-chars), binary data included,
# and reports a file with 10 or more (tool `committed-data`, rule `email-addresses`; the row carries counts only, never an address or domain, and starts `likely fixture:` for a test path whose addresses are mostly placeholder-style or on reserved domains). Addresses spread thin are summed over the files that stay below 10: 50 or more
# distinct give one `email-addresses` row with the path `.`. `not-checked` = unreadable, over the 32 MiB read cap, or, under the threshold, a file in a format whose pages can hide addresses (parquet, arrow, orc, zip, gzip,
# zstd, xz, 7z, lz4, bzip2, avro, pdf, zlib; the list and its ceilings are in committed_personal_data.py). gitleaks looks for secrets, not for exported personal data.
# Built-in too, base mode only (a --full scan has no diff): sibling_sweep.py lists the unchanged call sites, in non-test code, of a function whose call arguments the diff changed elsewhere (tool `sibling-sweep`,
# rule `unchanged-sibling-call`, message starts "lead:"): the sibling route a fix may have missed. Leads to open, never findings; a name with more than 25 call sites is skipped; scope and ceilings are in its docstring.
# `--full` scans every tracked file (base = git's empty tree) instead of a diff; it also runs tenant_scope_check.py (SKIPPED without a *.prisma) and route_auth_map.py (tool `route-auth`, rule `missing-auth`: a state-changing HTTP handler, raw node:http or fetch-handler pathname-and-method dispatch included, with no authentication evidence; a state-changing route in a language it does not judge (Go, Spring, PHP, Django urlconf) is a not-checked row, SKIPPED only without handlers or such routes), header_config.py (tool `header-config`: a security header the repo config never names, a lead to confirm with dynamic_probe.py; SKIPPED without a supported web app; a package.json, .conf file or directory it could not read gives not-checked rows instead) and attempt_limit_map.py (tool `attempt-limit`, rule `missing-attempt-limit`: a password, one-time-code or reset-code check with no attempt-limit evidence in its file or package, a lead to confirm with dynamic_probe.py --rate-endpoint; SKIPPED without a credential check or sign-in route) and cost_limit_map.py (tool `cost-limit`, rules `missing-cost-limit` and `unbounded-body`: an LLM or paid-API proxy, email or SMS send, upload, search, export or client-sized-page handler with no rate or quota limit evidence in its file or package, or a handler that reads the whole request body, or a body-parser limit of 10 MB or more, with no byte cap; a lead to confirm with dynamic_probe.py --rate-endpoint; SKIPPED without an HTTP handler) and csrf_cookie_map.py (tool `csrf-cookie`, rules `missing-csrf-protection` and `missing-cookie-flags`: a cookie-session state-changing handler with no anti-forgery token, Origin check or CSRF layer, or a session cookie set without Secure, HttpOnly or SameSite; a lead to confirm by reading the handler; SKIPPED without an HTTP handler or cookie) and ownership_sibling_check.py (tool `ownership`, rule `ownership-sibling`: a handler that loads a record by a client-sent id where a sibling handler of the same file checks ownership, a lead to confirm by reading the handler; a file it could not read is a not-checked row) and route_auth_map.py --privileged (tool `privileged-route`, rule `privileged-route`: an admin or role-changing route guarded by authentication alone, with no role or permission check; a lead to confirm by reading the handler). gitleaks runs once over the working tree, then (tool `gitleaks-history`) over the last REVIEW_HISTORY_MAX commits of HEAD (default 1000; 0 = skip, listed as "history not scanned"), so a secret removed from the tree but still in history is reported. gitleaks drops
# fingerprints listed in the repo's .gitleaksignore (as of BASE, HEAD under --full); history reads .gitleaks.toml as of BASE. Airtable object IDs (rec/app/tbl/fld/viw + 14 alnum) are allowlisted for airtable-api-key on gitleaks >= 8.25.1.
# gitleaks generic-api-key hits tagged likely-fixture collapse to one summary row when a group has >3: per top fixture dir (tagged likely-fixture) for hits under a fixture dir, else per file (rule `generic-api-key-summary`, first hit as line) for any other file; bandit B101 (assert) and ruff F821 (undefined name) hits collapse per file the same way when a file has >3 (rules `B101-summary`, `F821-summary`; the F821 message names the undefined names); a semgrep `github-actions-mutable-action-tag` row is dropped when zizmor flagged the same file:line as `unpinned-uses` (one defect, two tools); every other rule, and name-only matches, stay rows; REVIEW_FIXTURE_ROWS=all lists every hit.
# `--history` also runs gitleaks over BASE..HEAD (`--full-history`: the whole history). node_modules, vendor, build
# dirs and .claude/worktrees are never scanned; each heavy scanner takes the heavy lease only when it runs (waits
# REVIEW_LEASE_WAIT s, default 120) and releases it afterwards. If the lease is still full after the wait the scanners
# run degraded without the lease (`nice -n 19` when nice works, plus `--jobs 1` for semgrep and `--parallel 1` for trivy,
# dropped on a crash and retried once) and the summary labels them "(degraded: lease full, ...)"; REVIEW_LEASE_FULL=skip restores the old skip.
# A summary "N findings; N files excluded; analyzers ran: ...; skipped (not installed): ..." goes to stderr (N counts every row but the not-checked ones, which are surface nobody covered, not findings; lead rows such as `unchanged-sibling-call` and `header-not-found` count in N too; a "K not-checked row(s)" line follows when there are any), then "NOT RUN: <tool> (<why>), ..." (or "none"); a tool
# that timed out, crashed or (REVIEW_LEASE_FULL=skip) lost the lease is listed there (once, with a not-checked row on stdout) and never under "ran", so it cannot read as zero findings; a tool that is merely not installed stays under "skipped (not installed)". `--tests` also runs the command
# declared in env REVIEW_TEST_CMD (opt-in; it executes project code). Never installs anything. A missing tool
# or a timeout prints "review_checks: not run: <tool> (<why>)" on stderr and is not a failure. A semgrep scan that emitted findings but
# reported errors prints "review_checks: partial: semgrep ran ..." instead (never "not run"), whatever the error level (a warn-level parse error still makes the scan partial). That line ends with the error counts (N errors on M of S scanned files, by type and level) and each errored file is a not-checked row (path, line 0; 20 per 200-file chunk at most, then one row with the path `.` for the rest, naming the first path left out so two chunks never share a row; an error with no path is counted, not rowed). A semgrep chunk with errors and zero results is "partial" when every error names a path and some scanned file raised no error, and "not run" when every scanned file errored or any error has no path (the unread files are then unknown, so the chunk counts as not scanned and no row names a file). A hub tool that reports a file outside its scanned list is "not run" (paths do not line up), never a clean. tsc also resolves the repo-local node_modules/.bin/tsc (cwd or git toplevel only), run only when REVIEW_TEST_CMD is set.
# Offline caches that scripts/provision_tools.sh --print warms once, outside the sandbox, are used when present: the osv-scanner offline DB
# (unless REVIEW_OSV_DB_DIR or REVIEW_OSV=1 choose a mode), the trivy DB (trivy always runs offline) and a local semgrep p/default snapshot.
# A closing "ran X / wired Y scanners" stderr line names the scanners that had work this run, those that did not run, those that ran with a partial
# scope (trivy secret-only, semgrep with errors or bundled-only) and which a provision fixes (a missing tool, a cold cache, semgrep bundled-only); wired also counts shellcheck, ruff/pyflakes and (with --history) gitleaks-history,
# which provision_tools.sh cannot install, so they can be "not run" but never "fixable". The same summary is recorded best-effort in
# <git-common-dir>/review-checks-last.json for perun_doctor.py.
# guarddog (optional, offline, never installs or fetches): the npm packages a changed package-lock.json newly adds (against the merge-base lock; a bump counts) that are already
# installed under node_modules at the locked version get `guarddog npm scan` (hasInstallScript packages first; cap 25 and REVIEW_GUARDDOG_BUDGET seconds in all, default 300; threat-* rules only,
# each lead tagged [heuristic]; every package left unscanned is named in a not-checked row). A newly added lock entry with hasInstallScript is a lead of its own; see references/tool-hub.md.
# All temp files live in one private mktemp -d dir per run, removed on exit.
# Each tool run is timeboxed (default 60s); a semgrep chunk whose p/default pack hangs spends a second timebox on the bundled-rules rerun. Exit 0 even with findings; 2 on usage/unresolvable base.
set -euo pipefail
# pipx and `uv tool` install into ~/.local/bin, which a sandboxed shell's PATH may lack: append it so provisioned scanners are found (DCR_USER_BIN overrides; empty disables)
lb=${DCR_USER_BIN-${HOME:-/nonexistent}/.local/bin}
case ":$PATH:" in *":$lb:"*) ;; *) [ -z "$lb" ] || [ ! -d "$lb" ] || PATH=$PATH:$lb ;; esac

repo=. base=origin/main tests=0 hist=0 hyg=0 tmo=60 ran="" nr="" failed="" missing="" gap="" dg="" w1="" nice19=0 lease=ok leased=0 full=0 wr=0 hmax= cov="" wired="" wiredx=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base=${2:?--base needs a ref}; case "$base" in -*) echo "review_checks: --base must not start with '-'" >&2; exit 2 ;; esac; shift 2 ;;
    --timeout) tmo=${2:?--timeout needs seconds}; shift 2 ;;
    --tests) tests=1; shift ;;
    --repo) repo=${2:?--repo needs a dir}; [ -d "$repo" ] || { echo "review_checks: --repo: not a directory: $repo" >&2; exit 2; }; shift 2 ;; # replaces `cd DIR && review_checks.sh` (bash guards block chains)
    --history) hist=1; shift ;;
    --hygiene) hyg=1; shift ;;
    --full) wr=1 full=1 hmax=${REVIEW_HISTORY_MAX:-1000}; shift ;;
    --full-history) hist=1 full=1; shift ;;
    *) echo "usage: review_checks.sh [--repo DIR] [--base REF] [--tests] [--history] [--full] [--hygiene] [--timeout SECS]" >&2; exit 2 ;;
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
[ -z "$files" ] || wired+=" gitleaks trufflehog semgrep trivy" # scanners with work this run (any changed file); osv-scanner and the hub add theirs below
# wiredx: scanners that count toward "wired" but that provision_tools.sh cannot install, so they are never "fixable": shellcheck, ruff/pyflakes, gitleaks-history
# --full also scans the last REVIEW_HISTORY_MAX (default 1000) commits of HEAD; 0 = off, said in the NOT RUN list. --history and --full-history keep their ranges.
[ "$hist" = 0 ] || hmax=
case $hmax in *[!0-9]*) hmax=1000 ;; esac
if [ -n "$hmax" ]; then
  if [ "$hmax" -eq 0 ] 2>/dev/null; then echo "review_checks: history not scanned (REVIEW_HISTORY_MAX=0)" >&2; nr+="${nr:+, }gitleaks-history (history not scanned: REVIEW_HISTORY_MAX=0)"; else hist=1; fi
fi
[ "$hist" = 0 ] || wiredx+=" gitleaks-history"

# Existing changed files matching extended regex $1, one per line.
changed() { { printf '%s\n' "$files" | grep -E "$1" || true; } | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done; true; }
# A skip also lands in the JSON as a not-checked row (hub: under $hubtool; else under the tool) so `[]` never hides a tool that did not run.
# Unless merely not installed (that has its own list) it joins the failed set (subtracted from "ran" at print, so a later good file cannot
# re-list it) and the deduped "NOT RUN" list.
# ponytail: per-file tools (shellcheck) leave "ran" when any one file fails, the safe direction.
skip() {
  [ -z "${skq:-}" ] || { skq=$2; return 0; } # quiet probe (trufflehog's file-by-file retry): keep the reason for the caller, report nothing yet
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
    case "$1" in semgrep) miss "$1" "install: pipx install semgrep" ;; guarddog) miss "$1" "install: pipx install guarddog" ;; tsc) miss "$1" "install: npm install -g typescript" ;; *) miss "$1" "install: brew install $1" ;; esac
    return 1; }
  case "$1" in gitleaks|trufflehog|osv-scanner|semgrep|trivy) lease_take || { skip "$1" "heavy lease full"; return 1; } ;; esac
}
# add TOOL FILE LINE RULE MSG -> one TSV row.
add() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" >>"$raw"; }
# run_one TOOL CMD... : sets rc; returns 1 on timeout, with a not-run line unless it is semgrep with the p/default pack in its config (sgreg=1: the caller reruns with the bundled rules and reports that).
run_one() {
  local tool=$1 nz=(); shift; rc=0
  # lease full: heavy scanners run at lowest priority and are named in the summary (never take the lease while degraded)
  if [ "$lease" = degraded ]; then case $tool in gitleaks*|trufflehog|osv-scanner|semgrep|trivy|grype|checkov|gosec) [ "$nice19" != 1 ] || nz=(nice -n 19); case " $dg " in *" $tool "*) ;; *) dg+=" $tool" ;; esac ;; esac; fi
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
  jsx=()
  while IFS= read -r f; do
    run_one node-check node --check "./$f" || continue
    if [ "$rc" != 0 ]; then
      # JSX or markup in a .js file: node cannot parse it, so it is unchecked here, not a SyntaxError
      if grep -q "Unexpected token '<'" "$out" && grep -qE '</|/>' "$f"; then jsx+=("$f")
      else add node-check "$f" "$(sed -nE 's/^.*:([0-9]+)$/\1/p' "$out" | head -n1)" SyntaxError "$(grep -m1 'Error' "$out" || head -n1 "$out")"; fi
    fi
  done <<<"$js_files"
  if [ "${#jsx[@]}" -gt 0 ]; then
    first=$(printf '%s, ' "${jsx[@]:0:3}"); first=${first%, }
    add node-check "${jsx[0]}" 1 not-checked "${#jsx[@]} .js files hold JSX or markup that node --check cannot parse (first 3: $first); a JSX-aware linter or the project build judges them"
  fi
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

# Hygiene tier: low-value rows (trivy LOW, hadolint info/style, checkov ids in HYG below) leave the findings unless --hygiene; sjson counts them in $td/hyg.
export REVIEW_HYGIENE_SHOW=$hyg HYG_COUNT="$td/hyg"
# Scanner JSON (file $2, may have log lines before the JSON, which starts a line) of kind $1 -> TSV: file, line, rule, message.
# Fails closed: missing, empty or malformed JSON exits non-zero instead of reading as "no findings".
sjson() {
  python3 - "$1" "$2" <<'PY'
import collections, hashlib, json, os, pathlib, re, sys
kind = sys.argv[1]
show_hyg = os.environ.get("REVIEW_HYGIENE_SHOW") == "1"
HYG = {"CKV_DOCKER_2", "CKV_AWS_23", "CKV_AWS_126", "CKV_AWS_135", "KSV-0125", "KSV0125", "KSV125", "AVD-KSV-0125"}  # checkov has no severity in this output: HEALTHCHECK, SG description, detailed monitoring, EBS optimized; trivy KSV-0125 (trusted registries) means nothing until a registry list is configured
hidden = 0
def keyline(path, start, end, words, skip=(), yaml=False):
    """Line of the first word (a key or value the scanner named) near a flagged span, else start. Scanners anchor on the container or resource start, not the offending key.
    YAML: search the enclosing --- document (span start onward, then the doc head); HCL and Dockerfile: only the span. Unreadable file or no hit: start."""
    try: ls = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError: return start
    if not start or start > len(ls): return start
    lo, hi = start - 1, max(end or start, start)
    if yaml:
        sep = lambda i: ls[i].startswith("---")
        a = next((i + 1 for i in range(lo, -1, -1) if sep(i)), 0)
        z = next((i for i in range(lo + 1, len(ls)) if sep(i)), len(ls))
        order = list(range(lo, z)) + list(range(a, lo))
    else: order = list(range(lo, min(hi, len(ls))))
    for w in words:
        if w in skip or not w: continue
        r = re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])")
        for i in order:
            if r.search(ls[i]): return i + 1
    return start
def nf(f):  # scanners echo the path they were given ("./.github/..."); rows must carry the changed-file form
    return os.path.normpath(f) if f else f
cl = lambda s: "".join(c if c.isprintable() else "?" for c in str(s)) or "?"  # a package or file can be named with a \r: it would split the row and the closing summary drops it, so control characters become "?", never vanish
t = open(sys.argv[2], encoding="utf-8", errors="replace").read()
# The JSON starts a line. A log line before it can hold a bracket of its own (zizmor logs each audited path: x/[]/action.yml, and "[]" would read as no findings).
m = re.search(r"^[\[{]", t, re.M)
if not m:
    sys.exit("sjson: no JSON in scanner output")
d = json.JSONDecoder().raw_decode(t[m.start():])[0]
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
elif kind == "trufflehog":  # SARIF: runs[].results[]; a clean scan still prints the document with "results": []
    if not isinstance(d, dict) or not isinstance(d.get("runs"), list) or not d["runs"] or not all(isinstance(x, dict) and isinstance(x.get("results"), list) for x in d["runs"]):
        sys.exit("sjson: trufflehog output has no SARIF runs[].results list")
elif kind == "guarddog":  # results: rule -> hits; errors: rule -> why it did not run (its key stays in results, empty). A rule error costs that rule only: the other hits stay and a not-checked row names it
    if not isinstance(d, dict) or not isinstance(d.get("results"), dict) or not isinstance(d.get("errors") or {}, dict) or not any(str(r).startswith("threat-") for r in (*d["results"], *(d.get("errors") or {}))):
        sys.exit("sjson: guarddog output has no results object or no threat-* rule")
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
        lo = lambda x: not show_hyg and str(x.get("Severity")).upper() == "LOW"
        hidden += sum(map(lo, (r.get("Vulnerabilities") or []) + (r.get("Misconfigurations") or [])))
        rows += [(r["Target"], 0, v.get("VulnerabilityID"), f"{v.get('PkgName')}@{v.get('InstalledVersion')}: {v.get('Title', '')}") for v in r.get("Vulnerabilities") or [] if not lo(v)]
        for m in r.get("Misconfigurations") or []:
            if lo(m): continue
            if not show_hyg and (m.get("ID") in HYG or m.get("AVDID") in HYG): hidden += 1; continue
            cm = m.get("CauseMetadata") or {}
            msg = m.get("Message") or ""
            # names after a capitalised kind ("Container 'app' of Deployment 'web'") and the resource itself are not the offending key; the last dotted segment of the rest is
            skip = set(re.findall(r"[A-Z]\w* '([^']+)'", msg)) | set(re.split(r"[/\s]+", cm.get("Resource") or ""))
            words = [t.split(".")[-1] for t in re.findall(r"'([^']+)'", msg)]
            rows.append((r["Target"], keyline(r["Target"], cm.get("StartLine", 0), cm.get("EndLine", 0), words, skip, r["Target"].lower().endswith((".yaml", ".yml"))), m.get("ID"), m.get("Title", "")))
elif kind == "audit":
    # "-" placeholders: the caller's `read` collapses empty leading TSV fields; it supplies the lockfile path itself
    rows += [("-", 0, k, f"{v.get('severity')}: {v.get('name', k)}") for k, v in (d.get("vulnerabilities") or {}).items()]
    rows += [("-", 0, a.get("github_advisory_id") or k, f"{a.get('severity')}: {a.get('module_name')}: {a.get('title', '')}") for k, a in (d.get("advisories") or {}).items()]
    rows += [("-", 0, v.get("id"), f"{p.get('name')}@{p.get('version')}") for p in d.get("dependencies") or [] for v in p.get("vulns") or []]
elif kind == "zizmor":  # row is 0-based in json-v1; fixes and snippets are never read
    for x in d:
        ls = x.get("locations") or [{}]  # the Primary location is the offending line; ls[0] can be a Related span (the enclosing job, a line above)
        l = next((c for c in ls if (c.get("symbolic") or {}).get("kind") == "Primary"), ls[0])
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
            if not show_hyg and c.get("check_id") in HYG: hidden += 1; continue
            fr = (c.get("file_line_range") or [0, 0]) + [0]
            ek = [([s for s in re.split(r"[./]", re.sub(r"\[\d+\]", "", str(k))) if s] or [""])[-1] for k in (c.get("check_result") or {}).get("evaluated_keys") or []]  # last non-index segment; checkov writes "access_logs/[0]/enabled"
            rows.append(("-", keyline(c.get("file_abs_path") or "", fr[0], fr[1], ek), c.get("check_id"), c.get("check_name", "")))
elif kind == "hadolint":
    hl = lambda r: not show_hyg and r.get("level") in ("info", "style")
    hidden += sum(map(hl, d))
    rows = [(r.get("file"), r.get("line", 0), r.get("code"), r.get("message", "")) for r in d if not hl(r)]
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
elif kind == "trufflehog":  # only ruleId (the detector), uri and startLine are read; the message is ours. A result with no location raises: unparseable, never dropped
    for run in d["runs"]:
        for r in run["results"]:
            p = r["locations"][0]["physicalLocation"]
            f, n = nf(p["artifactLocation"]["uri"]), p.get("region", {}).get("startLine", 0)
            if f.endswith(".gz"):  # X.gz beside X with the same bytes: scanned there. Any read or decode error keeps the row
                try:
                    import gzip
                    if os.path.exists(f[:-3]) and gzip.decompress(open(f, "rb").read()) == open(f[:-3], "rb").read(): continue
                except Exception: pass
            if re.search(r"(^|/)\.?(sprockets-)?manifest-[0-9a-f]{16,}\.json$", f): continue  # digest manifest: hex asset digests, not credentials
            # blob noise, dropped only in notebook/css-family blob types: trufflehog decodes base64, so a long base64 line in yaml/env/json/source/map can be a real encoded secret and is kept. A line number below 1 keeps its row (it would read the last line). .ipynb: a blob only as an output mime key at line start ("image/<type>":) or a data:<mime>;base64, URI, so a code-cell base64 or hex literal is kept. Other blob types: >=200 unbroken base64 chars, a wrapped base64 chunk, or >2000 chars. An unreadable line keeps its row
            if n >= 1 and f.endswith((".ipynb", ".css", ".scss", ".less", ".nb")):
                try:
                    ln = open(f, errors="replace").read().split("\n")[n - 1]
                    if f.endswith(".ipynb"): blob = re.match(r'\s*"image/[\w.+-]+"\s*:', ln) or re.search(r"data:[\w.+-]+/[\w.+-]+;base64,", ln)
                    else: blob = re.fullmatch(r"[A-Za-z0-9+/]{60,}={0,2}", re.sub(r"\\n|[\s\"',]", "", ln)) or re.search(r"[A-Za-z0-9+/=_-]{200}", ln) or len(ln) > 2000
                    if blob: continue
                except (OSError, IndexError): pass
            rows.append((f, n, r["ruleId"], "secret detected (unverified: offline scan, --no-verification)"))
elif kind == "guarddog":  # threat-* rules only (capability-* fire on benign code); one row per rule from its first hit, relative to the package dir; code and match are source snippets and are never read
    for r, h in d["results"].items():
        if r.startswith("threat-") and h:
            f, _, l = str(h[0].get("location", "")).rpartition(":")
            rows.append((cl(f or "."), int(l) if l.isdigit() else 0, cl(r), f"{len(h)} hit(s): {cl(h[0].get('message', ''))[:200]} [heuristic]"))
    for r, e in sorted((d.get("errors") or {}).items()):
        rows.append((".", 0, "not-checked", f"rule {cl(r)} did not run ({cl(e)[:120]}); its hits were not checked"))
else:
    for r in d["results"]:
        for p in r.get("packages") or []:
            pk = p.get("package") or {}
            rows += [(r["source"]["path"], 0, v.get("id"), f"{pk.get('name')}@{pk.get('version')}: {v.get('summary', '')}")
                     for v in p.get("vulnerabilities") or []]
err = kind in ("semgrep", "guarddog") and d.get("errors")
rc = 3 if err else 0  # 3 = the scan was partial (rows may be empty); 4 = errors on every scanned file and no findings. Decided on the findings alone: the not-checked rows below are added after
if err and not rows:  # errors and no findings: partial when some scanned file raised no error, else exit 4 (nothing usable was scanned)
    bad = {e.get("path") if isinstance(e, dict) else None for e in err}
    rc = 3 if None not in bad and len(set((d.get("paths") or {}).get("scanned") or [])) > len(bad) else 4
if kind == "semgrep" and not rows and (d.get("paths") or {}).get("scanned") == []: rc = 5  # semgrep scanned none of the files (all filtered or excluded): not a clean pass
if kind == "semgrep" and rc == 3:  # name what semgrep could not fully read, at any level (a warn-level parse error is never downgraded to clean): counts by type and level on stderr, one not-checked row per errored path
    by, files = collections.Counter(), {}  # "<type> (<level>)" -> errors; path -> its distinct "<type>, <level>" pairs. An error with no path is counted, not rowed
    for e in err if isinstance(err, list) else [err]:
        e = e if isinstance(e, dict) else {}
        ty = e.get("type"); ty = ty[0] if isinstance(ty, list) and ty else ty  # a PartialParsing error is ["PartialParsing", [locations]]
        ty, lv = (str(x) if x else "unknown" for x in (ty, e.get("level")))
        by[f"{ty} ({lv})"] += 1
        if isinstance(e.get("path"), str) and e["path"]: files.setdefault(e["path"], {})[f"{ty}, {lv}"] = 1
    # ponytail: 20 named files per chunk (the stderr counts stay exact), then one row for the rest; raise the cap if a reviewer needs every path
    gp = sorted(files)
    rows += [(cl(p), 0, "not-checked", f"semgrep could not fully read this file ({'; '.join(files[p])}); rules may have missed part of it") for p in gp[:20]]
    if len(gp) > 20:  # path ".": an empty leading field would collapse in the caller's TSV read. The first unlisted path keeps each chunk's row unique (chunks hold disjoint files), else the closing dedup of identical not-checked rows would merge two chunks with equal counts into one
        rows.append((".", 0, "not-checked", f"semgrep could not fully read {len(gp) - 20} more file(s) ({len(gp)} with errors in this chunk; the first 20 in path order are listed, the rest start at {cl(gp[20])}); rules may have missed part of them"))
    sc = d.get("paths"); sc = sc.get("scanned") if isinstance(sc, dict) else None
    sc = {str(x) for x in sc} if isinstance(sc, list) else set()
    print(f"review_checks: partial: semgrep ran but reported errors (coverage incomplete; findings above are real) ({sum(by.values())} error(s) on {len(sc & set(gp))} of {len(sc)} scanned file(s): "
          + ", ".join(f"{k} x{n}" for k, n in sorted(by.items(), key=lambda kn: (-kn[1], kn[0]))) + ("; see not-checked rows)" if gp else ")"), file=sys.stderr)
if hidden: open(os.environ["HYG_COUNT"], "a").write(f"{hidden}\n")
for row in rows:
    print("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in row))
sys.exit(rc)
PY
}

# The allowlist template's skip paths as one ERE, set only while the repo has no .gitleaks.toml of its own (gitleaks then uses the template); trufflehog applies the same list below.
tplre=; tplwhat="under .history/, fixtures/, testdata/, generated registry JSON or lockfiles"
[ -f .gitleaks.toml ] || tplre=$(sed -n "s/^  '''\(.*\)''',\$/\1/p" "$here/../templates/gitleaks.toml" 2>/dev/null | paste -sd'|' - || true)
if have gitleaks; then
  # Airtable object IDs (17 chars) match airtable-api-key's shape; one global [[allowlists]] block drops them, added to every gitleaks config below. Needs gitleaks >= 8.25.1 (8.25.0 had the global table broken): older builds get no block.
  glal=; gv=$(gitleaks version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)
  # A repo config without useDefault has no airtable-api-key rule, and targetRules naming a missing rule fails the whole load: no block then.
  if [ "$(printf '%s\n8.25.1\n' "$gv" | sort -V | head -1)" = 8.25.1 ] && { [ ! -f .gitleaks.toml ] || grep -qE '^[[:space:]]*useDefault[[:space:]]*=[[:space:]]*true' .gitleaks.toml; }; then glal=$td/airtable.toml; cat >"$glal" <<'EOT'
[[allowlists]]
description = "Airtable object IDs (rec/app/tbl/fld/viw + 14 alnum): not API keys"
targetRules = ["airtable-api-key"]
regexes = ['''^(?:rec|app|tbl|fld|viw)[A-Za-z0-9]{14}$''']
EOT
  fi
  # Content-hash allowlist (templates/gitleaks.toml): trusted only as of BASE, so a change cannot approve its own secret.
  # A missing file or unresolvable base means an empty list; an entry the change adds or edits is itself a finding.
  export GL_ALLOW=$gla; git show "$ref:.gitleaks-allow" >"$gla" 2>/dev/null || : >"$gla"
  if [ -f .gitleaks-allow ] && ! cmp -s .gitleaks-allow "$gla"; then add gitleaks .gitleaks-allow 0 allowlist-changed "allowlist differs from $ref; the change's entries are NOT applied, review them"; fi
  # .gitleaksignore (fingerprints) is likewise read as of BASE (HEAD under --full), never from the working tree.
  export GL_IGNORE=$gli; git show "$ref:.gitleaksignore" >"$gli" 2>/dev/null || : >"$gli"
  glcfg=(); [ -f .gitleaks.toml ] || glcfg=(--config "$here/../templates/gitleaks.toml") # no repo config: use the allowlist template
  if [ -n "$tplre" ]; then # say what the template hides, so a skipped file is never silent
    skipped=$(printf '%s\n' "$files" | grep -cE "$tplre" || true)
    [ "${skipped:-0}" -eq 0 ] || echo "review_checks: gitleaks template skipped $skipped changed file(s) $tplwhat" >&2
  fi
  if [ "$wr" = 1 ]; then # one batched scan of the working tree; only tracked, non-vendored files are reported
    : >"$rep"; glw=$td/glw # extend the config; skip vendored trees at scan time
    vk='[allowlist]'; [ -z "$glal" ] || vk='[[allowlists]]' # the global table cannot sit beside the deprecated [allowlist]
    printf '[extend]\npath = "%s"\n%s\npaths = [\x27\x27\x27(^|/)(node_modules|vendor|\\.claude/worktrees)/\x27\x27\x27]\n' "${glcfg[1]:-$PWD/.gitleaks.toml}" "$vk" >"$glw"
    [ -z "$glal" ] || cat "$glal" >>"$glw"
    if run_one gitleaks gitleaks detect --config "$glw" --gitleaks-ignore-path "$gli" --no-git --no-banner --exit-code 0 -f json -r "$rep" -s . && scan_ok gitleaks; then
      [ -s "$rep" ] || echo '[]' >"$rep"
      if sjson gitleaks "$rep" >"$tsv"; then
        while IFS=$'\t' read -r f l r m; do f=${f#./}; grep -qxF -- "$f" "$td/files" && add gitleaks "$f" "$l" "$r" "$m"; done <"$tsv"
      else skip gitleaks "unparseable report; secrets were not scanned"; fi
    fi
  else
    pcfg=(); if [ -n "$glal" ]; then pcfg=(--config "$td/glc.toml"); { if [ -n "${glcfg[1]:-}" ]; then printf '[extend]\npath = "%s"\n' "${glcfg[1]}"; else printf '[extend]\nuseDefault = true\n'; fi; cat "$glal"; } >"$td/glc.toml"; else pcfg=(${glcfg[@]+"${glcfg[@]}"}); fi
    while IFS= read -r f; do
      [ -f "$f" ] || continue
      : >"$rep" # a stale report from the previous file must never be read for this one
      run_one gitleaks gitleaks detect ${pcfg[@]+"${pcfg[@]}"} --gitleaks-ignore-path "$gli" --no-git --no-banner --exit-code 0 -f json -r "$rep" -s "./$f" || continue
      scan_ok gitleaks || continue
      [ -s "$rep" ] || echo '[]' >"$rep" # gitleaks may leave an empty report for a clean file
      sjson gitleaks "$rep" >"$tsv" || { skip gitleaks "unparseable report for $f"; continue; }
      while IFS=$'\t' read -r _ l r m; do add gitleaks "$f" "$l" "$r" "$m"; done <"$tsv"
    done <<<"$files"
  fi
  if [ "$hist" = 1 ]; then # history: the commits BASE..HEAD adds, not just the final file state (never BASE...HEAD: that also scans every BASE-only commit when HEAD is behind)
    : >"$rep"; hb=$td/hist-base.toml; git show "$ref:.gitleaks.toml" >"$hb" 2>/dev/null || hb= # read as of BASE like .gitleaksignore, so a change cannot allowlist its own commits
    if [ -n "$hb" ]; then printf '[extend]\npath = "%s"\n' "$hb" >"$td/hist.toml"; else printf '[extend]\nuseDefault = true\n' >"$td/hist.toml"; fi
    if [ -n "$glal" ] && { [ -z "$hb" ] || grep -qE '^[[:space:]]*useDefault[[:space:]]*=[[:space:]]*true' "$hb"; }; then cat "$glal" >>"$td/hist.toml"; fi
    hc=(--config "$td/hist.toml")
    lo=(--log-opts "$base..HEAD"); [ "$full" = 0 ] || lo=(); [ -z "$hmax" ] || lo=(--log-opts "--max-count=$hmax") # default: only the commits since BASE (default origin/main, never a possibly stale local main)
    if run_one gitleaks-history gitleaks detect ${hc[@]+"${hc[@]}"} --no-banner --exit-code 0 -f json -r "$rep" ${lo[@]+"${lo[@]}"} -s . && scan_ok gitleaks-history; then
      [ -s "$rep" ] || echo '[]' >"$rep"
      if sjson gitleaks "$rep" >"$tsv"; then while IFS=$'\t' read -r f l r m; do [[ $f =~ $XRE ]] || add gitleaks-history "$f" "$l" "$r" "$m"; done <"$tsv"
      else skip gitleaks-history "unparseable report"; fi
    fi
  fi
elif [ -n "$files" ]; then add gitleaks "" 0 not-checked "not installed or heavy lease full; secrets were not scanned"; fi

# trufflehog: a second secret detector set, with gitleaks' lease and degraded-nice handling. Offline (--no-verification never calls a provider; --no-update skips the version check). --sarif, never --json or the default
# output: those print the secret (--json as Raw, RawV2, Redacted and SecretParts), while SARIF holds only the detector, path, line and a fingerprint hash, so no value reaches $out, a row or the record. --log-level=-1 keeps stderr (merged into $out) from corrupting the document.
# --fail-on-scan-errors: an unreadable file or path exits 1 (a not-run row), where it would otherwise exit 0 and read as clean. Files are named explicitly, 200 per call like semgrep: the changed files, every tracked file under --full.
# Noise: the gitleaks template's skip paths (tplre, only without a repo .gitleaks.toml) are filtered from the file list here, because trufflehog's own --exclude-paths is ignored for files named on the command line (checked on 3.99.7).
# .gitleaksignore and .gitleaks-allow do not apply to it; its inline `trufflehog:ignore` comment does (tool-hub.md).
# A failed chunk (timeout, crash, or one unreadable file: --fail-on-scan-errors fails the whole call and prints nothing) is retried file by file, so one bad file costs only itself: passing files keep their rows,
# each file that still fails is a not-checked row (partial scope), and when no file passes the tool is "not run" as before: the retry gives up after 3 failures while none has passed. A passing chunk is never retried.
if have trufflehog; then
  tf=() tn=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    if [ -n "$tplre" ] && [[ $f =~ $tplre ]]; then tn=$((tn + 1)); else tf+=("./$f"); fi
  done <<<"$files"
  [ "$tn" -eq 0 ] || echo "review_checks: trufflehog template skipped $tn changed file(s) $tplwhat" >&2
  [ ${#tf[@]} -gt 0 ] || wired=${wired/ trufflehog/} # nothing left to scan: no work, so the closing line never reads it as a scanner that did not run
  # tfscan FILE...: one call; 0 when it ran. A failure reports nothing yet (skip stays quiet via $skq): its reason is left in $tfw for the caller.
  tfscan() {
    skq=1 tfw=
    run_one trufflehog trufflehog --log-level=-1 --no-verification --no-update --sarif --fail-on-scan-errors filesystem "$@" && scan_ok trufflehog && { skq=; return 0; }
    tfw=$skq; skq=; return 1
  }
  # tfrows: the last call's findings ($out) as rows; 1 when its output does not parse
  tfrows() { local f l r m; sjson trufflehog "$out" >"$tsv" && while IFS=$'\t' read -r f l r m; do add trufflehog "$f" "$l" "$r" "$m"; done <"$tsv"; }
  for ((i = 0; i < ${#tf[@]}; i += 200)); do
    tfc=("${tf[@]:i:200}")
    if tfscan "${tfc[@]}"; then tfrows || skip trufflehog "unparseable output; secrets were not scanned"; continue; fi
    [ ${#tfc[@]} -gt 1 ] || { skip trufflehog "$tfw"; continue; } # one file: a retry is the same call
    # ponytail: while no file has passed alone, 3 failed single-file retries end the chunk as not run, so a crashed or hung tool costs 3 extra runs per chunk, not up to 200 timeboxed ones;
    # the price is that 3 or more unreadable files ahead of the first good one also read as not run (loud, never clean). Raise the 3 if that bites.
    tfwhy=$tfw tfgood=0 tfbad=() tfbw=()
    for f in "${tfc[@]}"; do
      if tfscan "$f" && tfrows; then tfgood=1; else tfbad+=("${f#./}"); tfbw+=("${tfw:-unparseable output}"); fi
      [ "$tfgood" = 1 ] || [ ${#tfbad[@]} -lt 3 ] || break
    done
    if [ "$tfgood" = 0 ]; then skip trufflehog "$tfwhy"; continue; fi # no file passes alone: the tool failed, not a file
    for ((j = 0; j < ${#tfbad[@]}; j++)); do add trufflehog "${tfbad[j]}" 0 not-checked "trufflehog failed on this file alone (${tfbw[j]}); it was not scanned for secrets"; done
    [ ${#tfbad[@]} -eq 0 ] || { echo "review_checks: partial: trufflehog could not scan ${#tfbad[@]} of ${#tfc[@]} file(s) of a failed chunk (each is a not-checked row)" >&2; case " $ran " in *" trufflehog(errors) "*) ;; *) ran+=" trufflehog(errors)" ;; esac; }
  done
elif [ -n "$files" ]; then add trufflehog "" 0 not-checked "not installed or heavy lease full; secrets were not scanned"; fi

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
  sg=() sgwas=$ran sgok=0 sgerr=0 sgzero=0 sgj=() sgb=0 sgrx=0 sgbun=(--config "$sgc"); [ "$lease" != degraded ] || { sgj=(--jobs 1); w1+=" semgrep"; }
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
    if [ "$e" = 5 ]; then sgzero=$((sgzero + 1)) # a chunk that scanned 0 files: judged after the loop (NOT CHECKED only when no chunk scanned anything)
    elif [ "$e" = 4 ]; then sgerr=$((sgerr + 1)) # errors on every scanned file and no results: nothing usable from this chunk; judged after the loop
    elif [ "$e" = 0 ] || [ "$e" = 3 ]; then
      sgok=1
      while IFS=$'\t' read -r p l r m; do add semgrep "$p" "$l" "$r" "$m"; done <"$tsv"
      # a "(note)" token in ran is a partial scope: the closing line and the record list it apart from a full run. On exit 3 sjson has already printed the partial line (error counts by type and level) and added the not-checked rows read above
      [ "$e" = 0 ] || case " $ran " in *" semgrep(errors) "*) ;; *) ran+=" semgrep(errors)" ;; esac
    else skip semgrep "unparseable output"; fi
  done
  if [ "$sgzero" -gt 0 ] && [ "$sgok" = 0 ] && [ "$sgerr" = 0 ]; then ran=$sgwas; skip semgrep "NOT CHECKED: semgrep scanned 0 files"; fi
  if [ "$sgerr" -gt 0 ] && [ "$sgok" = 1 ]; then # other chunks scanned fine: partial coverage, not a voided tool
    echo "review_checks: partial: semgrep errored with no findings on $sgerr chunk(s) of up to 200 files (those files were not scanned)" >&2
    add semgrep "" 0 not-checked "semgrep errored on $sgerr chunk(s) of up to 200 files; those files were not scanned"
  elif [ "$sgerr" -gt 0 ]; then ran=$sgwas; skip semgrep "scan errored, no findings"; fi
fi

# World-writable chmod in a Dockerfile RUN (777, a+w, o+w, incl. -R): no installed scanner (hadolint, checkov, trivy) has a rule for it.
while IFS= read -r f; do
  case $f in Dockerfile*|*/Dockerfile*|*.dockerfile) ;; *) continue ;; esac
  [ -f "$f" ] || continue
  while IFS=: read -r l _; do add dockerfile-chmod "$f" "$l" world-writable-chmod "RUN makes files world-writable (chmod 777 / a+w / o+w); grant the service user ownership with chown or a narrower mode instead"; done < <(grep -nE '^[[:space:]]*RUN[[:space:]].*chmod[[:space:]]+(-[A-Za-z-]+[[:space:]]+)*(0?[0-7]?[0-7][0-7][2367]|[ugoa]*[oa][ugoa]*[+=][rxXst]*w)([[:space:]]|$|[;&])' "$f" || true)
done <"$td/files"

# trivy: offline against the cached DB (no download); no DB or any crash reads as not-run, never as clean.
# If the vuln+misconfig scan fails (check bundle unreachable in the sandbox), retry secret-only and say so.
if [ -n "$files" ] && have trivy; then
  # --offline-scan stops the DB fetch, not trivy's telemetry ping (check.trivy.dev): opt out by env var, since an older trivy crashes on an unknown flag
  export TRIVY_DISABLE_TELEMETRY=true
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
  'zizmor;verified;batch;^\.github/(workflows/[^/]+|dependabot)\.ya?ml$|(^|/)action\.ya?ml$;route-only;pipx install zizmor' # also audits Dependabot config and action manifests; actionlint reads workflows only
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
    # GRYPE_CHECK_FOR_APP_UPDATE=false: grype's own-version check calls toolbox-data.anchore.io even with the DB update off (env var, not a flag: an older grype crashes on an unknown flag)
    grype) cmd=(env GRYPE_DB_AUTO_UPDATE=false GRYPE_CHECK_FOR_APP_UPDATE=false grype "sbom:$1" -o json) ;; # SBOM only: dir: scans the whole tree (unverified for lockfiles)
    # CKV_SKIP_PACKAGE_UPDATE_CHECK=true: --skip-download leaves checkov's own-version lookup (pypi.org) on; env var, not a flag, so an older checkov ignores it
    checkov) cmd=(env CKV_SKIP_PACKAGE_UPDATE_CHECK=true checkov -f "$1" -o json --quiet --skip-download --soft-fail) ;;
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

# guarddog: the npm packages a changed package-lock.json newly adds (name@version absent from the merge-base lock, so a version bump counts) that are already installed at the locked version
# (the installed package.json says so: a lock-only bump leaves the old code on disk, and scanning that would read as clean) get an offline YARA scan. It never installs and never runs `verify`;
# guarddog reads a non-directory argument as a registry package NAME and would fetch it, so only existing directories inside the repo are passed. 3.2.0 has no offline flag: its startup refresh of the
# typosquat top-package lists (github.com, hugovk.github.io, packages.ecosyste.ms) is stopped by pointing GUARDDOG_TOP_PACKAGES_CACHE_LOCATION at fresh stub lists, and the --no-sandbox retry (guarddog's
# own kernel sandbox is what otherwise blocks its network) adds a dead proxy. Only threat-* rules become leads (capability-* fire on benign code), and YARA rules are heuristics, so each lead says so.
# The install-hook rules (threat-npm-preinstall-script, threat-process-hooks) match the path */package.json, a nested one: a package's own root package.json, where install hooks live, is never flagged
# by them, so a newly added lock entry with hasInstallScript is a lead of its own (tool package-lock). Unleased: light.
# ponytail: package-lock.json only (no yarn.lock or pnpm-lock.yaml); add a parser when those repos need it.
# gdnew LOCK BASELOCK LEADS: "dir<TAB>name<TAB>version<TAB>flag" per package LOCK has and BASELOCK lacks, flag 1 = its lock entry has hasInstallScript (dir: the first copy inside the repo whose
# package.json version is the locked one, else "-"). LEADS gets finished rows: a package-lock lead per flagged package and a not-checked row per entry that cannot be scanned safely (no version, or control
# characters in its name, version or key). Every field is printable: a \r would split a row and the closing summary drops it silently, so control characters become "?". Non-zero when LOCK has no packages map.
gdnew() {
  python3 -I - "$@" <<'PY'
import json, os, sys
f, bf, lf = sys.argv[1:]
cl = lambda s: "".join(c if c.isprintable() else "?" for c in str(s)) or "?"
def pk(p):  # {lock key: (name, version, hasInstallScript)}; the root "", workspace roots and link entries are repo code, not a download
    d = json.load(open(p, encoding="utf-8"))["packages"]
    return {k: (str(v.get("name") or k.rsplit("node_modules/", 1)[1]), v.get("version"), v.get("hasInstallScript") is True) for k, v in d.items() if "node_modules/" in k and not v.get("link")}
try: old = {(n, v) for n, v, _ in pk(bf).values()}
except Exception: old = set()  # no usable lock at the merge-base: every package is new
new = {}
for k, (n, v, s) in pk(f).items():
    if (n, v) not in old: e = new.setdefault((n, v), [[], False]); e[0].append(k); e[1] = e[1] or s
def has(q, v):  # q holds version v: a lock-only bump leaves the old code installed, and scanning that would read as clean
    try: return json.load(open(os.path.join(q, "package.json"), encoding="utf-8")).get("version") == v
    except (OSError, ValueError, AttributeError): return False
root, d0, rows, leads = os.path.realpath(".") + os.sep, os.path.dirname(f), [], []
for (n, v), (ks, s) in sorted(new.items(), key=lambda kv: not kv[1][1]):  # stable: hasInstallScript packages first, so the cap and the time budget never leave them out
    nm, vs = cl(n), cl(v) if isinstance(v, str) else "?"
    ok = isinstance(v, str) and all(x.isprintable() for x in (n, v, f, *ks))
    if not ok: leads.append(("guarddog", cl(f), 0, "not-checked", f"{nm}@{vs}: the lock entry has no version, or control characters in its name, version or key; not scanned"))
    if s: leads.append(("package-lock", cl(f), 0, "has-install-script", f"{nm}@{vs} is newly added and its lock entry has hasInstallScript: it has a preinstall, install or postinstall script that npm runs on install. guarddog's install-hook rules never read a package's own root package.json, so read that script [heuristic]"))
    # the realpath test keeps a symlink or a .. key from leading a scan outside the repo
    p = next((q for q in (os.path.join(d0, k) for k in ks) if os.path.isdir(q) and (os.path.realpath(q) + os.sep).startswith(root) and has(q, v)), "-") if ok else "-"
    rows.append(f"{p}\t{nm}\t{vs}\t{int(s)}")
if leads: open(lf, "a", encoding="utf-8").write("".join("\t".join(map(str, r)) + "\n" for r in leads))
if rows: print("\n".join(rows))
PY
}
glk=$(changed '(^|/)package-lock\.json$')
if [ -n "$glk" ]; then
  hubtool=guarddog
  if [ "$full" = 1 ]; then skip guarddog "SKIPPED: --full has no base to find newly added packages against"
  else
    gdn=$td/gdnew gdb=$td/gdbase gdl=$td/gdleads; : >"$gdn"; : >"$gdl"
    gmb=$(git merge-base "$ref" HEAD 2>/dev/null || echo "$ref") # the lock as the diff above sees its base: the moved base tip would call the base's own bumps new
    while IFS= read -r f; do
      git show "$gmb:$f" >"$gdb" 2>/dev/null || echo '{}' >"$gdb" # no lock there: every package is new
      gdnew "$f" "$gdb" "$gdl" >>"$gdn" 2>/dev/null || skip guarddog "SKIPPED: $f has no packages map (lockfileVersion 1) or is unparseable"
    done <<<"$glk"
    cat "$gdl" >>"$raw" # the hasInstallScript leads and the named not-checked rows stand with or without guarddog
    gdT=$(grep -c . "$gdn" || true)
    if [ "$gdT" != 0 ] && { wiredx+=" guarddog"; have guarddog; }; then
      gdc=$td/gdcache gdP=0 gdS=0 gdR=0 gdN=0 gdQ=0 gdq= gdsb=() gdpx=() gdt0=$SECONDS gdbud=${REVIEW_GUARDDOG_BUDGET:-300} gdp=http://127.0.0.1:9
      case "$gdbud" in ''|*[!0-9]*) gdbud=300 ;; esac
      mkdir -p "$gdc"
      for gk in npm pypi rubygems go; do printf '{"downloaded_timestamp": %s, "packages": ["example"]}\n' "$(date +%s)" >"$gdc/top_${gk}_packages.json"; done
      gdrun() { run_one guarddog env GUARDDOG_TOP_PACKAGES_CACHE_LOCATION="$gdc" ${gdpx[@]+"${gdpx[@]}"} guarddog "$@" </dev/null; }
      gdscan() { gdrun npm scan ${gdsb[@]+"${gdsb[@]}"} --output-format json "$PWD/$1"; }
      gdok=0 # only a guarddog 3.x scans: the scan JSON was checked on 3.2.0, and any other answer is a named not-checked row, never a clean
      if gdrun --version; then
        if [ "$rc" = 0 ] && grep -qE '(^|[^0-9.])3\.[0-9]+\.[0-9]+' "$out"; then gdok=1
        else skip guarddog "SKIPPED: needs guarddog 3.x (the scan JSON was checked on 3.2.0); --version said: $(head -n1 "$out" | tr -d '[:cntrl:]' | cut -c1-60) (exit $rc)"; fi
      fi
      if [ "$gdok" = 1 ]; then
        while IFS=$'\t' read -r gp gnm gv _; do
          case "$gp" in ''|-) gdN=$((gdN + 1)); continue ;; esac
          gdP=$((gdP + 1))
          if [ "$gdP" -gt 25 ] || [ $((SECONDS - gdt0)) -ge "$gdbud" ]; then gdQ=$((gdQ + 1)); [ "$gdQ" -gt 10 ] || gdq+="${gdq:+, }$gnm@$gv"; continue; fi
          [ -d "$PWD/$gp" ] || { gdN=$((gdN + 1)); continue; } # a non-directory argument is a registry package NAME to guarddog: a fetch
          gdscan "$gp" || continue
          if [ "$rc" != 0 ] && [ "${#gdsb[@]}" = 0 ] && grep -qi 'sandbox initialization failed' "$out"; then # inside another sandbox its own kernel sandbox cannot start
            gdsb=(--no-sandbox) gdpx=(HTTP_PROXY=$gdp HTTPS_PROXY=$gdp ALL_PROXY=$gdp http_proxy=$gdp https_proxy=$gdp all_proxy=$gdp NO_PROXY= no_proxy=) # without it nothing blocks its network: a dead proxy does
            echo "review_checks: guarddog: kernel sandbox unavailable here (nested sandbox); scanning without it, network blocked by a dead proxy" >&2
            gdscan "$gp" || continue
          fi
          scan_ok guarddog || continue
          e=0; sjson guarddog "$out" >"$tsv" || e=$?
          case "$e" in 0) gdS=$((gdS + 1)) ;; 3) gdR=$((gdR + 1)) ;; *) skip guarddog "unparseable output"; continue ;; esac # 3: a rule did not run (its own row says which); the hits of the others stay
          while IFS=$'\t' read -r gf gln grl gmsg; do
            if [ "$grl" = not-checked ]; then add guarddog "$gp" 0 not-checked "$gnm@$gv: $gmsg"; else add guarddog "$gp/$gf" "$gln" "$grl" "$gnm@$gv: $gmsg"; fi
          done <"$tsv"
        done < <(awk -F'\t' '$4 == 1' "$gdn"; awk -F'\t' '$4 != 1' "$gdn") # hasInstallScript packages first, across every lock
        if [ "$gdP" = 0 ]; then skip guarddog "SKIPPED: none of $gdT newly added packages is installed under node_modules at its locked version"
        elif [ "$gdS" = "$gdT" ]; then ran+=" guarddog"
        else
          [ $((gdS + gdR)) = 0 ] || ran+=" guarddog(scanned-$gdS-of-$gdT)"
          gdm="scanned $gdS of $gdT newly added packages in full; $gdN not installed at the locked version or unreadable"
          [ "$gdR" = 0 ] || gdm+="; $gdR scanned with a rule that did not run"
          [ "$gdQ" -le 10 ] || gdq+=" and $((gdQ - 10)) more"
          [ -z "$gdq" ] || gdm+="; over the cap of 25 or the ${gdbud}s time budget, not scanned: $gdq"
          add guarddog "" 0 not-checked "$gdm; a failed or partial scan has its own row"
        fi
      fi
    fi
  fi
  hubtool=
fi

# Optional, --full only: tenant_scope_check.py (Prisma id-only where in server code); SKIPPED when the tree has no *.prisma.
if [ "$full" = 1 ]; then
  if [ -z "$(changed '\.prisma$')" ]; then skip tenant-scope "SKIPPED: no *.prisma"
  elif have python3 && run_one tenant-scope python3 -I "$here/tenant_scope_check.py" "$PWD" && scan_ok tenant-scope; then
    echo "tenant-scope: heuristic; scanned $(sed -nE 's/.*"server_files": ([0-9]+).*/\1/p' "$out" | tail -n1) server files; silence is not proof of tenant isolation" >&2
    while IFS=$'\t' read -r p l r m; do add tenant-scope "$p" "$l" "$r" "$m"; done < <(sed -nE 's/^(.+):([0-9]+): (HIGH|MED): ([^:]+): (.*)$/\1\t\2\t\4\t\5/p' "$out" | awk -F'\t' 'BEGIN{OFS=FS}{gsub(/ /,"-",$3)}1')
  fi
  # route_auth_map.py: HIGH rows (a state-changing handler with no auth evidence) become rows; INFO rows stay in the script's own report. SKIPPED when it finds no handler.
  if have python3 && run_one route-auth python3 -I "$here/route_auth_map.py" "$PWD" && scan_ok route-auth; then
    n=$(sed -nE 's/.*"handlers": ([0-9]+).*/\1/p' "$out" | tail -n1)
    u=$(sed -nE 's/.*"unjudged": ([0-9]+).*/\1/p' "$out" | tail -n1)
    if [ "${n:-0}" = 0 ] && [ "${u:-0}" = 0 ]; then skip route-auth "SKIPPED: no HTTP handlers"
    else
      echo "route-auth: heuristic; scanned $n handlers; silence is not proof of authentication" >&2
      while IFS=$'\t' read -r p l m; do add route-auth "$p" "$l" missing-auth "$m"; done < <(sed -nE 's/^(.+):([0-9]+): HIGH: (.*)$/\1\t\2\t\3/p' "$out")
      while IFS=$'\t' read -r p l m; do add route-auth "$p" "$l" not-checked "$m"; done < <(sed -nE 's/^(.+):([0-9]+): UNJUDGED: (.*)$/\1\t\2\t\3/p' "$out")
    fi
  fi
  # ownership_sibling_check.py: each "path:line: OWNERSHIP: msg" line is a row (rule ownership-sibling); a file it skipped is a not-checked row, never silent.
  if have python3 && run_one ownership python3 -I "$here/ownership_sibling_check.py" "$PWD" && scan_ok ownership; then
    echo "ownership: heuristic; silence is not proof of object-level authorization" >&2
    while IFS=$'\t' read -r p l m; do add ownership "$p" "$l" ownership-sibling "$m"; done < <(sed -nE 's/^(.+):([0-9]+): OWNERSHIP: (.*)$/\1\t\2\t\3/p' "$out")
    while IFS=$'\t' read -r p m; do add ownership "$p" 0 not-checked "not scanned: $m"; done < <(sed -nE 's/^ownership_sibling_check: skipped ([^:]+): (.*)$/\1\t\2/p' "$out")
  fi
  # route_auth_map.py --privileged: each "path:line: PRIV: msg" line (authentication but no role check on a privileged route) is a row (rule privileged-route).
  if have python3 && run_one privileged-route python3 -I "$here/route_auth_map.py" --privileged "$PWD" && scan_ok privileged-route; then
    echo "privileged-route: heuristic; silence is not proof of function-level authorization" >&2
    while IFS=$'\t' read -r p l m; do add privileged-route "$p" "$l" privileged-route "$m"; done < <(sed -nE 's/^(.+):([0-9]+): PRIV: (.*)$/\1\t\2\t\3/p' "$out")
  fi
  # header_config.py: header-not-found and not-checked rows; header-found and header-middleware rows stay in the script's own output. SKIPPED when no supported web app is found.
  if have python3 && run_one header-config python3 -I "$here/header_config.py" "$PWD" && scan_ok header-config; then
    if grep -q 'header-config: no supported web app found' "$out"; then skip header-config "SKIPPED: no supported web app"
    else
      grep -E '^header-config: ' "$out" >&2 || true
      while IFS=$'\t' read -r f l r m; do case "$r" in header-not-found|not-checked) add header-config "$f" "$l" "$r" "$m" ;; esac; done <"$out"
    fi
  fi
  # attempt_limit_map.py: missing-attempt-limit rows (a password, one-time-code or reset-code check with no attempt-limit evidence); attempt-limit-evidence rows stay in the script's own output. SKIPPED when no credential check or sign-in route is found.
  if have python3 && run_one attempt-limit python3 -I "$here/attempt_limit_map.py" "$PWD" && scan_ok attempt-limit; then
    if grep -q 'attempt-limit: no credential check or sign-in route found' "$out"; then skip attempt-limit "SKIPPED: no credential check or sign-in route"
    else
      grep -E '^attempt-limit: ' "$out" >&2 || true
      while IFS=$'\t' read -r f l r m; do case "$r" in missing-attempt-limit) add attempt-limit "$f" "$l" "$r" "$m" ;; esac; done <"$out"
    fi
  fi
  # cost_limit_map.py: missing-cost-limit rows (a costly or unbounded endpoint with no rate or quota limit evidence); cost-limit-evidence rows stay in the script's own output. SKIPPED when no HTTP handler is found.
  if have python3 && run_one cost-limit python3 -I "$here/cost_limit_map.py" "$PWD" && scan_ok cost-limit; then
    if grep -q 'cost-limit: no HTTP handler found' "$out"; then skip cost-limit "SKIPPED: no HTTP handler"
    else
      grep -E '^cost-limit: ' "$out" >&2 || true
      while IFS=$'\t' read -r f l r m; do case "$r" in missing-cost-limit|unbounded-body) add cost-limit "$f" "$l" "$r" "$m" ;; esac; done <"$out"
    fi
  fi
  # csrf_cookie_map.py: missing-csrf-protection rows (a cookie-session POST/PUT/PATCH/DELETE handler with no anti-forgery token, Origin check or CSRF layer) and missing-cookie-flags rows (a session cookie set without Secure, HttpOnly or SameSite). SKIPPED when it finds no handler or cookie.
  if have python3 && run_one csrf-cookie python3 -I "$here/csrf_cookie_map.py" "$PWD" && scan_ok csrf-cookie; then
    if grep -q 'csrf-cookie: no HTTP handler or cookie found' "$out"; then skip csrf-cookie "SKIPPED: no HTTP handler or cookie"
    else
      grep -E '^csrf-cookie: ' "$out" >&2 || true
      while IFS=$'\t' read -r f l r m; do case "$r" in missing-csrf-protection|missing-cookie-flags) add csrf-cookie "$f" "$l" "$r" "$m" ;; esac; done <"$out"
    fi
  fi
  # pii_data_map.py: plaintext-national-id (SSN-shaped literal or national-id key with a quoted digit string), unencrypted-national-id-column (Python model attribute) and raw-pii-to-third-party (raw email or phone sent to an analytics host) rows; values are never printed. SKIPPED when it finds no source file.
  if have python3 && run_one pii-data python3 -I "$here/pii_data_map.py" "$PWD" && scan_ok pii-data; then
    if grep -q 'pii-data: no source file found' "$out"; then skip pii-data "SKIPPED: no source file"
    else
      grep -E '^pii-data: ' "$out" >&2 || true
      while IFS=$'\t' read -r f l r m; do case "$r" in plaintext-national-id|unencrypted-national-id-column|raw-pii-to-third-party) add pii-data "$f" "$l" "$r" "$m" ;; esac; done <"$out"
    fi
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
# unleased: it reads each file's bytes once (capped at 32 MiB). Rows: tool committed-data, rule email-addresses|not-checked (the row with path `.` is the repository total over files below the file threshold); the message has counts or the container format, never a value. No likely-fixture hint or tag (a real address in a fixture is still a leak); only the message leads `likely fixture:`, from the path and the share of placeholder-style or reserved-domain addresses.
pd="$here/committed_personal_data.py"
if [ -n "$cf" ]; then
  if [ ! -f "$pd" ]; then skip committed-data "committed_personal_data.py missing"
  else
    pdok=0; run_one committed-data python3 "$pd" --stdin <<<"$cf" && scan_ok committed-data && pdok=1
    # flushed per row, as above: a timeout still yields the findings made so far
    if [ "$pdok" = 1 ] || [ "$rc" = 124 ] || [ "$rc" = 142 ]; then while IFS=$'\t' read -r f l r m; do add committed-data "$f" "$l" "$r" "$m"; done <"$out"; fi
  fi
fi

# Built-in, no tool to install: dependency currency (dependency_currency.py). Reads each changed manifest, lockfile (direct + transitive), Dockerfile, workflow and runtime pin (vendored dirs are flagged), asks the ecosystem registries for the newest stable release,
# OSV for known vulnerabilities and CISA KEV for exploited ones, and endoflife.date for end-of-life runtimes. Rows: tool dep-currency, rule kev|vulnerable|eol|outdated|drift|unpinned|vendored|not-checked (KEV first); a lookup that fails is a not-checked row (NOT RUN), never "up to date". Needs network; unleased.
dc="$here/dependency_currency.py"
dcf=$(printf '%s\n' "$all" | grep -E '(^|/)(package(-lock)?\.json|npm-shrinkwrap\.json|uv\.lock|setup\.py|\.tool-versions|\.?mise\.toml|\.php-version|vendor/composer/installed\.json|buildSrc/.*\.kt|yarn\.lock|[^/]*(requirements|constraints?)[^/]*\.(txt|in)|(requirements?|reqs?)/[^/]+\.(txt|in)|poetry\.lock|Pipfile(\.lock)?|setup\.cfg|rust-toolchain(\.toml)?|gradle\.properties|gradle-wrapper\.properties|go\.mod|pom\.xml|[^/]*\.gradle(\.kts)?|gradle\.lockfile|lockfile\.json|[^/]*\.versions\.toml|Cargo\.(toml|lock)|composer\.(json|lock)|Dockerfile[^/]*|[^/]*\.Dockerfile|\.nvmrc|\.node-version|\.python-version|runtime\.txt|\.ruby-version|pnpm-lock\.yaml|pyproject\.toml|(docker-)?compose[^/]*\.ya?ml|action\.ya?ml|\.github/(workflows|actions)/.*\.ya?ml|PKG-INFO)$' || true)  # PKG-INFO: a vendored Python package has no package.json-style manifest, only this
dcy=$(printf '%s\n' "$all" | grep -E '\.ya?ml$' | tr '\n' '\0' | xargs -0 grep -lsE -m1 -- '^apiVersion:' || true)  # Kubernetes manifests: container images
[ -n "$dcy" ] && dcf=$(printf '%s\n%s\n' "$dcf" "$dcy" | sed '/^$/d' | sort -u)
if [ -n "$dcf" ]; then
  if [ ! -f "$dc" ]; then skip dep-currency "dependency_currency.py missing"
  else
    dcok=0; run_one dep-currency python3 "$dc" --stdin --budget "$((tmo * 3 / 4))" <<<"$dcf" && scan_ok dep-currency && dcok=1
    if [ "$dcok" = 1 ] || [ "$rc" = 124 ] || [ "$rc" = 142 ]; then while IFS=$'\t' read -r f l r m; do add dep-currency "$f" "$l" "$r" "$m"; done <"$out"; fi
  fi
fi

# Built-in, no tool to install, base mode only: unchanged call sites of a function whose call arguments this diff changed (sibling_sweep.py; read-only git diff and git grep against commits, no checkout).
# Cheap, so unleased. Rows: tool sibling-sweep, rule unchanged-sibling-call|not-checked; leads for the reviewer to open, never findings. The script's one-line stderr summary lands in $out too and is not a row (no tabs).
ss="$here/sibling_sweep.py"
if [ "$full" != 1 ] && [ -n "$files" ]; then
  if [ ! -f "$ss" ]; then skip sibling-sweep "sibling_sweep.py missing"
  else
    if run_one sibling-sweep python3 -I "$ss" --repo . --base "$base" && scan_ok sibling-sweep; then  # rows are written once at the end, so a timeout or crash leaves none
      while IFS=$'\t' read -r f l r m; do [ -z "$m" ] || add sibling-sweep "$f" "$l" "$r" "$m"; done <"$out"  # the stderr summary line has no tabs: not a row
    fi
  fi
fi

if [ "$tests" = 1 ]; then
  if [ -z "${REVIEW_TEST_CMD:-}" ]; then skip tests "REVIEW_TEST_CMD not set"
  elif run_one tests bash -c "$REVIEW_TEST_CMD"; then
    [ "$rc" = 0 ] || add tests "" 0 test-failed "REVIEW_TEST_CMD exited $rc: $(tail -n1 "$out")"
  fi
fi

r=; for t in $ran; do case " $failed " in *" ${t%%(*} "*) ;; *) r+=" $t" ;; esac; done; ran=$r
# "new" flags, diff mode only (a --full or --history row may sit on a line no diff added). Flags are pinned so user git config cannot change the parse:
# --inter-hunk-context=0 and --no-color keep hunk counts and headers exact, the prefixes fix the "+++ b/" name, and -a gives a text file with a NUL byte (invisible-chars rows) hunks instead of "Binary files differ".
# Most rows read the working tree but the diff reads commits (sibling-sweep reads HEAD, so for it null is only cautious), so a row in a file whose working copy differs from HEAD (edited, staged or not, or untracked) is flagged null, not a guessed true/false: $td/dirty is `git status --porcelain -z` (an "XY path" entry per file; --no-renames lists both sides of a rename, -uall every untracked file). --no-optional-locks keeps it a pure read: `git diff HEAD` rewrote .git/index for a file that only changed its mtime even with that flag (git 2.50.1). If a git read here fails, "new" is omitted from every row and stderr says so.
# ponytail: ignored untracked files and assume-unchanged/skip-worktree edits are not listed (add --ignored if a row ever needs the first); a file staged different from HEAD but reverted in the working tree is listed too, where null is only cautious.
ud=; if [ "$wr" = 0 ] && [ "$hist" = 0 ]; then ud=$td/udiff; { git -c core.quotePath=false diff -U0 --inter-hunk-context=0 -M -a --no-color --no-ext-diff --no-textconv --src-prefix=a/ --dst-prefix=b/ "$base"...HEAD >"$ud" && git --no-optional-locks status --porcelain -z --no-renames -uall >"$td/dirty"; } || { ud=; echo 'review_checks: could not list files that differ from HEAD; "new" omitted' >&2; }; fi
REVIEW_STATE="$(git rev-parse --git-common-dir)/review-checks-last.json" HERE="$here" python3 - "$raw" "$ran" "$missing" "$nex" "$dg" "$w1" "$nice19" "$wired" "$gap" "$wiredx" "$ud" "$td/dirty" <<'PY'
import json, os, re, shlex, sys, time
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8", errors="replace")]
rows = [t for i, t in enumerate(rows) if t[3:4] != ["not-checked"] or t not in rows[:i]]  # a tool failing on N files is one not-checked row
# Triage hint, not a verdict (only big generic-api-key groups collapse, below): a secret or hidden-character finding under a sample/fixture/test/mock/docs path is usually dummy data.
FXD = re.compile(r"(^|/)(fixtures?|samples?|examples?|tests?|__tests__|testdata|mocks?|__mocks__|docs?)/", re.I)  # whole directory segment
FXB = re.compile(r"(^|[._-])(fixture|sample|example|mock|test)s?([._-]|$)", re.I)  # file name only, so test-runner/ or sample-service/ stay untagged
def fx(p): return FXD.search(p) or FXB.search(p.rsplit("/", 1)[-1])
def row(t):
    d = {"file": t[1], "line": int(t[2]) if t[2].isdigit() else 0, "rule": t[3], "message": t[4], "text": f"{t[3]}: {t[4]}", "tool": t[0]}
    if t[0] in ("gitleaks", "gitleaks-history", "trufflehog", "invisible-chars") and fx(t[1]):
        d["hint"] = "likely-fixture"; d["text"] += " [likely-fixture]"
    return d
# Low-confidence buckets: generic-api-key (the low-signal rule) hits from gitleaks or gitleaks-history collapse when they are more than 3 in one group:
# under a fixture DIRECTORY per (tool, top fixture dir), tagged likely-fixture; elsewhere per (tool, file), rule generic-api-key-summary, untagged unless the file is name-only fixture-like.
# Every other rule (stripe, github-pat, openai, anthropic, private-key, ...) stays a per-row finding. REVIEW_FIXTURE_ROWS=all (or ALL, 1, true) keeps every row.
# Per-file collapse also covers bandit B101 (assert) and ruff F821 (undefined name, e.g. a harness's injected globals): per (tool, file) when more than 3, rule B101-summary or F821-summary; no fixture-dir bucket for them.
LOW = {"generic-api-key"}
FILE = {("gitleaks", "generic-api-key"), ("gitleaks-history", "generic-api-key"), ("bandit", "B101"), ("ruff", "F821")}
opt = os.environ.get("REVIEW_FIXTURE_ROWS", "").lower() in ("all", "1", "true")
def top(p):
    s = p.split("/")[:-1]; j = next(i for i, x in enumerate(s) if FXD.search(x + "/"))
    while j < len(s) and FXD.search(s[j] + "/"): j += 1
    return "/".join(s[:j]) + "/"
def summ(k, g):
    n = len(g); r = sorted((t[1], row(t)["line"]) for t in g)[:3]
    m = f"{n} generic-api-key hits under {k[1]} tagged likely-fixture (showing 3 of {n}; REVIEW_FIXTURE_ROWS=all for every row): {', '.join(f'{f}:{l}' for f, l in r)}"
    return {"file": k[1], "line": 0, "rule": "likely-fixture-summary", "message": m, "text": f"{k[0]}: {m} [likely-fixture]", "tool": k[0], "hint": "likely-fixture"}
def fsumm(k, g):  # k = (tool, file, "", rule): the rule names the message and the summary row
    n = len(g); L = sorted(row(t)["line"] for t in g); R = k[3]
    m = f"{n} {R} hits in this file (showing 3 of {n}; REVIEW_FIXTURE_ROWS=all for every row): {', '.join(map(str, L[:3]))}"
    if R == "F821":  # distinct backticked names in first-appearance order: first 5, "…" if more
        nm = list(dict.fromkeys(x for t in g for x in re.findall(r"`([^`]+)`", t[4])[:1])); m += f"; names: {', '.join(nm[:5])}{'…' if len(nm) > 5 else ''}"
    d = {"file": k[1], "line": L[0], "rule": f"{R}-summary", "message": m, "text": f"{k[0]}: {m}", "tool": k[0], "_lines": L}  # _lines: every member line, popped before printing
    if k[0] in ("gitleaks", "gitleaks-history") and fx(k[1]): d["hint"] = "likely-fixture"; d["text"] += " [likely-fixture]"
    return d
data = [t for t in rows if len(t) == 5]
# Same defect, two tools: (dup tool, dup rule suffix): (keep tool, keep rule). A dup row goes only when the keep row sits on the same file:line.
SUPERSEDES = {("semgrep", "github-actions-mutable-action-tag"): ("zizmor", "unpinned-uses")}
kept = {(os.path.normpath(t[1]), t[2], t[0], t[3]) for t in data}
data = [t for t in data if not any(t[0] == dt and t[3].endswith(dr) and (os.path.normpath(t[1]), t[2], kt, kr) in kept for (dt, dr), (kt, kr) in SUPERSEDES.items())]
key = lambda t: not opt and t[0] in ("gitleaks", "gitleaks-history") and t[3] in LOW and FXD.search(t[1]) and (t[0], top(t[1]))
fkey = lambda t: not opt and (t[0], t[3]) in FILE and (t[0], t[1], "", t[3])
groups = {}
for t in data:
    if key(t): groups.setdefault(key(t), []).append(t)
    elif fkey(t): groups.setdefault(fkey(t), []).append(t)
out, done = [], set()
for t in data:
    k = key(t) or fkey(t)
    if not k or len(groups[k]) <= 3: out.append(row(t))
    elif k not in done: done.add(k); out.append(summ(k, groups[k]) if key(t) else fsumm(k, groups[k]))
ML = [r.pop("_lines", None) for r in out]  # per-file summary rows: every member line; popped here in every mode so the key never prints
ud = sys.argv[11]  # `git diff -U0` of BASE...HEAD; "" under --full/--history or when a git read above failed (no "new" key)
if ud:
    dirty = {e[3:] for e in open(sys.argv[12], "rb").read().decode("utf-8", "replace").split("\0")}  # "XY path" entries: files with a staged or working-tree change, or untracked
    adds, cur, inh = {}, None, False  # adds: file -> [(first line, count)] of added lines; cur: the file whose hunks are being read; inh: past its first hunk header, where a "+++ " line is content
    for l in open(ud, encoding="utf-8", errors="replace"):
        if l.startswith("diff --git "): cur, inh = None, False
        elif l.startswith("@@ "):
            inh = True; m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", l)
            if cur and m: adds[cur].append((int(m[1]), 1 if m[2] is None else int(m[2])))  # "+N" is one line, "+N,0" none
        elif not inh and l.startswith("+++ b/"): cur = l[6:].rstrip("\n").split("\t")[0]; adds[cur] = []  # git adds a tab after a name with a space; a quoted name or /dev/null leaves cur unset
    for r, ml in zip(out, ML):  # a row in a dirty file is null (unknown); else file-level rows (line 0, no file) are never new; a per-file summary is new when any member line is added; every path is read relative to the repo root, as the tools print it ("./x", absolute)
        f = os.path.relpath(r["file"]) if r["file"] not in ("", "-") else None
        hit = [r["line"]] if ml is None else ml
        r["new"] = None if f in dirty else any(l > 0 and f is not None and a <= l < a + c for l in hit for a, c in adds.get(f, ()))
        if ml is not None and f is not None and f not in dirty:  # added member lines past the 3 shown are named, so the summary says why it is new
            ext = [l for l in ml[3:] if l > 0 and any(a <= l < a + c for a, c in adds.get(f, ()))]
            if ext:
                old = r["message"]; r["message"] += f"; added: {', '.join(map(str, ext))}"; r["text"] = r["text"].replace(old, r["message"], 1)
print(json.dumps(out, indent=1))
n = len(out); nc = sum(r["rule"] == "not-checked" for r in out)  # not-checked rows are unchecked surface, so they are counted apart from findings
dg, w1 = sys.argv[5].split(), sys.argv[6].split()  # lease full: "1 worker" only for tools whose single-worker flag ran; "nice 19" only when nice worked
def lab(t):
    b = t.split("(")[0]
    return t + (f" (degraded: lease full{', nice 19' if sys.argv[7] == '1' else ''}{', 1 worker' if b in w1 else ''})" if b in dg else "")
print(f"review_checks: {n - nc} findings; {sys.argv[4]} files excluded; analyzers ran: {', '.join(lab(t) for t in sys.argv[2].split()) or 'none'}; skipped (not installed): {', '.join(sys.argv[3].split()) or 'none'}", file=sys.stderr)
if nc: print(f"review_checks: {nc} not-checked row(s) (surface a tool did not cover, not findings)", file=sys.stderr)
if ud:
    k = sum(r["new"] is None for r in out)
    print(f"review_checks: {sum(r['new'] is True for r in out)} of {n} rows are on lines this diff adds" + (f", {k} unknown (file differs from HEAD)" if k else ""), file=sys.stderr)
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
[ ! -s "$td/hyg" ] || echo "review_checks: hygiene: $(awk '{n+=$1} END{print n}' "$td/hyg") rows hidden (--hygiene shows them)" >&2
[ -z "$gap" ] || echo "review_checks: missing tools: $gap" >&2
