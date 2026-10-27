#!/usr/bin/env bash
# review_checks.sh [--base REF] [--tests] [--history] [--timeout SECS] — run local, read-only analyzers over the files
# changed since REF (default origin/main, compared as REF...HEAD) and print findings as a JSON array on
# stdout: [{"file","line","rule","message","text","tool"}]. `text` ("rule: message") is the key
# scripts/score_review.py matches on. Findings are LEADS: verify each against the code before reporting.
#
# Tools (linters, gitleaks, osv-scanner, semgrep, trivy): see references/method-situational.md. Each runs only when
# installed and only on matching changed files. Secrets are redacted and never printed; osv-scanner needs env
# REVIEW_OSV=1 (network); semgrep uses repo rules, else the bundled taint rules plus p/default (never `--config auto`); trivy is offline.
# Tool hub: zizmor, bandit, gosec, grype, checkov, hadolint (snyk-agent-scan is unverified, skipped) run from one registry
# (`hub=`); a matching changed file with the tool missing prints "NOT CHECKED: <tool> (install: <hint>)" on stderr, never a silent clean.
# `--history` also runs gitleaks over BASE..HEAD (`--full-history`: the whole history). node_modules, vendor, build
# dirs and .claude/worktrees are never scanned; each heavy scanner takes the heavy lease only when it runs (waits
# REVIEW_LEASE_WAIT s, default 120, else skipped) and releases it afterwards.
# A summary "N findings; N files excluded; analyzers ran: ...; skipped (not installed): ..." goes to stderr. `--tests` also runs the command
# declared in env REVIEW_TEST_CMD (opt-in; it executes project code). Never installs anything. A missing tool
# or a timeout prints "review_checks: not run: <tool> (<why>)" on stderr and is not a failure.
# Each tool is timeboxed (default 60s). Exit 0 even with findings; 2 on usage/unresolvable base.
set -euo pipefail

base=origin/main tests=0 hist=0 tmo=60 ran="" missing="" lease=ok leased=0 full=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base=${2:?--base needs a ref}; case "$base" in -*) echo "review_checks: --base must not start with '-'" >&2; exit 2 ;; esac; shift 2 ;;
    --timeout) tmo=${2:?--timeout needs seconds}; shift 2 ;;
    --tests) tests=1; shift ;;
    --history) hist=1; shift ;;
    --full-history) hist=1 full=1; shift ;;
    *) echo "usage: review_checks.sh [--base REF] [--tests] [--history] [--timeout SECS]" >&2; exit 2 ;;
  esac
done
case "$tmo" in ''|*[!0-9]*) echo "review_checks: --timeout must be an integer" >&2; exit 2 ;; esac
git rev-parse --verify -q "$base^{commit}" >/dev/null || { echo "review_checks: unresolvable base '$base'" >&2; exit 2; }
here=$(cd "$(dirname "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)"

raw=$(mktemp "${TMPDIR:-/tmp}/review-raw.XXXXXX") out=$(mktemp "${TMPDIR:-/tmp}/review-out.XXXXXX") tsv=$(mktemp "${TMPDIR:-/tmp}/review-tsv.XXXXXX")
sgh=$(mktemp -d "${TMPDIR:-/tmp}/review-sg.XXXXXX") # semgrep HOME: the macOS agent sandbox denies writes to ~/.semgrep
rep=$(mktemp "${TMPDIR:-/tmp}/review-gl.XXXXXX") gla=$(mktemp "${TMPDIR:-/tmp}/review-gla.XXXXXX") # mktemp files are mode 600
trap 'rm -rf "$raw" "$out" "$tsv" "$sgh" "$rep" "$gla"' EXIT INT TERM HUP
# Vendored, build and worktree dirs are never scanned (a changed file under them is dropped here, for every tool).
XRE='(^|/)(node_modules|\.claude/worktrees|vendor|dist|build|\.git|\.venv|venv|target|__pycache__)/'
all=$(git diff --name-only --diff-filter=ACMR "$base"...HEAD)
files=$(printf '%s\n' "$all" | grep -Ev "$XRE" || true)
nex=$(( $(printf '%s\n' "$all" | grep -c .) - $(printf '%s\n' "$files" | grep -c .) ))
rc=0

# Existing changed files matching extended regex $1, one per line.
changed() { { printf '%s\n' "$files" | grep -E "$1" || true; } | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done; true; }
# Inside the tool hub ($hubtool set) a skip also lands in the JSON as a not-checked row, so `[]` never hides a tool that did not run.
skip() { echo "review_checks: not run: $1 ($2)" >&2; [ -z "${hubtool:-}" ] || add "$hubtool" "" 0 not-checked "$2"; }
# Run "$@" under a timebox; stdout+stderr -> $out. perl alarm when no timeout(1) (stock macOS).
tbox() {
  if command -v timeout >/dev/null; then timeout "$tmo" "$@" >"$out" 2>&1
  elif command -v gtimeout >/dev/null; then gtimeout "$tmo" "$@" >"$out" 2>&1
  else perl -e 'alarm shift; exec @ARGV' "$tmo" "$@" >"$out" 2>&1; fi
}
# have TOOL: 0 when installed, else prints the not-run line.
# Heavy scanners take the machine-wide heavy lease (held by this shell) lazily, only once installed and about to run, so
# concurrent sessions queue instead of piling on; lease_drop frees it after the last one. Waits REVIEW_LEASE_WAIT s
# (default 120) then reports the scanner as skipped. Fail open: no perun_policy.py (review-only install) or an
# unexpected exit from it (reported once) means no gate.
pp="$(dirname "$0")/../../agentic-delivery/scripts/perun_policy.py"
lease_take() {
  [ "$leased" = 1 ] && return 0
  [ "$lease" = ok ] || return 1
  [ -f "$pp" ] && command -v python3 >/dev/null || return 0
  local w=${REVIEW_LEASE_WAIT:-120} r
  while :; do
    r=0; python3 "$pp" heavy-acquire >/dev/null 2>&1 || r=$?
    case "$r" in
      0) leased=1; return 0 ;;
      1) if [ "$w" -le 0 ]; then lease=full; return 1; fi; sleep 5; w=$((w - 5)) ;;
      *) skip lease "policy rc=$r"; lease=none; return 0 ;;
    esac
  done
}
lease_drop() { [ "$leased" = 1 ] && { python3 "$pp" heavy-release >/dev/null 2>&1 || true; leased=0; }; true; }
have() {
  command -v "$1" >/dev/null || { skip "$1" "not installed"; missing+=" $1"; return 1; }
  case "$1" in gitleaks|osv-scanner|semgrep|trivy) lease_take || { skip "$1" "heavy lease full"; return 1; } ;; esac
}
# add TOOL FILE LINE RULE MSG -> one TSV row.
add() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" >>"$raw"; }
# run_one TOOL CMD... : sets rc; returns 1 (with a not-run line) on timeout.
run_one() {
  local tool=$1; shift; rc=0
  [ -n "${hubtool:-}" ] || case " $ran " in *" $tool "*) ;; *) ran+=" $tool" ;; esac # hub tools count as ran only after a good parse
  tbox "$@" || rc=$?
  case "$rc" in 124|142) skip "$tool" "timeout ${tmo}s"; return 1 ;; esac
  return 0
}
# scan_ok TOOL [OKRC...]: false (with a not-run line) when the last run_one exit code is not 0 or an OKRC (findings), i.e. a crash.
scan_ok() { local t=$1 c; shift; for c in 0 "$@"; do [ "$rc" = "$c" ] && return 0; done; skip "$t" "exit $rc"; return 1; }
# Findings parsed from $out by a sed script (TSV columns) land via `add`.
sh_files=$(changed '\.(sh|bash)$')
if [ -n "$sh_files" ]; then
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

if [ -n "$(changed '\.(ts|tsx)$')" ] && [ -f tsconfig.json ] && have tsc; then
  if run_one tsc tsc --noEmit -p tsconfig.json && scan_ok tsc 1 2; then
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
import hashlib, json, os, re, sys
kind = sys.argv[1]
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
elif kind in ("zizmor", "hadolint"):
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
    kept = [r for r in d if not allowed(r)]
    if len(kept) < len(d):
        print(f"review_checks: .gitleaks-allow suppressed {len(d) - len(kept)} finding(s)", file=sys.stderr)
    rows = [(r.get("File"), r.get("StartLine"), r.get("RuleID"), r.get("Description") or "secret detected") for r in kept]
elif kind.startswith("trivy"):
    for r in d.get("Results") or []:  # Secrets only in the secret-only fallback, and never the Match (it would leak the value)
        if kind == "trivy-secret": rows += [(r["Target"], s.get("StartLine", 0), s.get("RuleID"), s.get("Title", "secret detected")) for s in r.get("Secrets") or []]
        rows += [(r["Target"], 0, v.get("VulnerabilityID"), f"{v.get('PkgName')}@{v.get('InstalledVersion')}: {v.get('Title', '')}") for v in r.get("Vulnerabilities") or []]
        rows += [(r["Target"], (m.get("CauseMetadata") or {}).get("StartLine", 0), m.get("ID"), m.get("Title", "")) for m in r.get("Misconfigurations") or []]
elif kind == "zizmor":  # row is 0-based in json-v1; fixes and snippets are never read
    for x in d:
        l = ((x.get("locations") or [{}])[0])
        f = (((l.get("symbolic") or {}).get("key") or {}).get("Local") or {}).get("verbatim_path")
        r = (((l.get("concrete") or {}).get("location") or {}).get("start_point") or {}).get("row", -1)
        rows.append((f, r + 1, x.get("ident"), x.get("desc", "")))
elif kind == "bandit":  # issue_text (B105 embeds the secret) and code are never read
    rows = [(os.path.relpath(r["filename"]), r.get("line_number", 0), r.get("test_id"), "potential issue (see the bandit docs for this test id)") for r in d["results"]]
elif kind == "gosec":
    for r in d["Issues"] or []:
        ln = str(r.get("line", "0")).split("-")[0]
        rows.append((os.path.relpath(r["file"]), int(ln) if ln.isdigit() else 0, r.get("rule_id"), r.get("details", "")))
elif kind == "grype":  # file comes from the caller (it scanned one target)
    for m in d["matches"]:
        v, a = m.get("vulnerability") or {}, m.get("artifact") or {}
        rows.append(("", 0, v.get("id"), f"{a.get('name')}@{a.get('version')}: {(v.get('description') or '')[:200]}"))
elif kind == "checkov":  # code_block is never read
    for x in ds:
        for c in x["results"].get("failed_checks") or []:
            rows.append(("", (c.get("file_line_range") or [0])[0], c.get("check_id"), c.get("check_name", "")))
elif kind == "hadolint":
    rows = [(r.get("file"), r.get("line", 0), r.get("code"), r.get("message", "")) for r in d]
elif kind == "semgrep":
    rows = [(r["path"], r["start"]["line"], r.get("check_id"), (r.get("extra") or {}).get("message", "")) for r in d["results"]]
else:
    for r in d["results"]:
        for p in r.get("packages") or []:
            pk = p.get("package") or {}
            rows += [(r["source"]["path"], 0, v.get("id"), f"{pk.get('name')}@{pk.get('version')}: {v.get('summary', '')}")
                     for v in p.get("vulnerabilities") or []]
for row in rows:
    print("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in row))
sys.exit(3 if kind == "semgrep" and d.get("errors") else 0)  # 3 = rows printed, but the scan was partial
PY
}

if have gitleaks; then
  # Content-hash allowlist (templates/gitleaks.toml): trusted only as of BASE, so a change cannot approve its own secret.
  # A missing file or unresolvable base means an empty list; an entry the change adds or edits is itself a finding.
  export GL_ALLOW=$gla; git show "$base:.gitleaks-allow" >"$gla" 2>/dev/null || : >"$gla"
  if [ -f .gitleaks-allow ] && ! cmp -s .gitleaks-allow "$gla"; then add gitleaks .gitleaks-allow 0 allowlist-changed "allowlist differs from $base; the change's entries are NOT applied, review them"; fi
  glcfg=(); [ -f .gitleaks.toml ] || glcfg=(--config "$here/../templates/gitleaks.toml") # no repo config: use the allowlist template
  if [ ${#glcfg[@]} -gt 0 ]; then # say what the template hides, so a skipped file is never silent
    skipped=$(printf '%s\n' "$files" | grep -cE "$(sed -n "s/^  '''\(.*\)''',\$/\1/p" "$here/../templates/gitleaks.toml" | paste -sd'|' -)" || true)
    [ "${skipped:-0}" -eq 0 ] || echo "review_checks: gitleaks template skipped $skipped changed file(s) under .history/, fixtures/, testdata/ or generated registry JSON" >&2
  fi
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    : >"$rep" # a stale report from the previous file must never be read for this one
    run_one gitleaks gitleaks detect ${glcfg[@]+"${glcfg[@]}"} --no-git --no-banner --exit-code 0 -f json -r "$rep" -s "./$f" || continue
    scan_ok gitleaks || continue
    [ -s "$rep" ] || echo '[]' >"$rep" # gitleaks may leave an empty report for a clean file
    sjson gitleaks "$rep" >"$tsv" || { skip gitleaks "unparseable report for $f"; continue; }
    while IFS=$'\t' read -r _ l r m; do add gitleaks "$f" "$l" "$r" "$m"; done <"$tsv"
  done <<<"$files"
  if [ "$hist" = 1 ]; then # history: the commits in BASE...HEAD (the file list's range), not just the final file state
    : >"$rep"
    lo=(--log-opts "$base...HEAD"); [ "$full" = 0 ] || lo=() # default: only the commits since BASE
    if run_one gitleaks-history gitleaks detect --no-banner --exit-code 0 -f json -r "$rep" ${lo[@]+"${lo[@]}"} -s . && scan_ok gitleaks-history; then
      [ -s "$rep" ] || echo '[]' >"$rep"
      if sjson gitleaks "$rep" >"$tsv"; then while IFS=$'\t' read -r f l r m; do [[ $f =~ $XRE ]] || add gitleaks-history "$f" "$l" "$r" "$m"; done <"$tsv"
      else skip gitleaks-history "unparseable report"; fi
    fi
  fi
fi

lock_files=$(changed '(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|Cargo\.lock|poetry\.lock|requirements[^/]*\.txt|composer\.lock)$')
if [ -z "$lock_files" ]; then :
elif [ "${REVIEW_OSV:-}" != 1 ]; then skip osv-scanner "REVIEW_OSV not set; osv-scanner queries the OSV API"
elif have osv-scanner; then
  while IFS= read -r f; do
    run_one osv-scanner osv-scanner --format json -L "./$f" || continue
    scan_ok osv-scanner 1 || continue # exit 1 = vulnerabilities found
    sjson osv "$out" >"$tsv" || { skip osv-scanner "unparseable output for $f"; continue; }
    while IFS=$'\t' read -r _ l r m; do add osv-scanner "$f" "$l" "$r" "$m"; done <"$tsv"
  done <<<"$lock_files"
fi

sgc=${REVIEW_SEMGREP_CONFIG:-}
[ -n "$sgc" ] || for c in .semgrep.yml .semgrep; do [ -e "$c" ] && { sgc=$c; break; }; done
sgcfg=(--config "$sgc")
if [ -z "$sgc" ]; then # no repo rules: bundled taint rules, plus the p/default registry pack unless REVIEW_SEMGREP_REGISTRY=0 (never --config auto)
  sgc=$here/../templates/semgrep-taint; sgcfg=(--config "$sgc")
  [ "${REVIEW_SEMGREP_REGISTRY:-1}" = 0 ] || sgcfg+=(--config p/default)
fi
if [ ! -e "$sgc" ]; then
  if [ -z "${REVIEW_SEMGREP_CONFIG:-}" ] && [ "$sgc" = "$here/../templates/semgrep-taint" ]; then skip semgrep "bundled rules missing at $sgc (reinstall the skill)"
  else skip semgrep "REVIEW_SEMGREP_CONFIG must be an existing local path"; fi
elif have semgrep; then
  sg=()
  while IFS= read -r f; do [ -f "$f" ] && sg+=("$f"); done <<<"$files"
  # One call per 200 files: typically a single run, but bounded argv and a timeout that is not shared by everything.
  for ((i = 0; i < ${#sg[@]}; i += 200)); do
    run_one semgrep env HOME="$sgh" SEMGREP_USER_HOME="$sgh" semgrep "${sgcfg[@]}" --json --quiet --metrics=off --disable-version-check -- "${sg[@]:i:200}" || continue
    if [ "$rc" != 0 ] && [ ${#sgcfg[@]} -gt 2 ]; then # registry pack unreachable (offline): rerun with the bundled rules alone
      run_one semgrep env HOME="$sgh" SEMGREP_USER_HOME="$sgh" semgrep --config "$sgc" --json --quiet --metrics=off --disable-version-check -- "${sg[@]:i:200}" || continue
    fi
    scan_ok semgrep || continue
    e=0; sjson semgrep "$out" >"$tsv" || e=$?
    if [ "$e" = 0 ] || [ "$e" = 3 ]; then
      while IFS=$'\t' read -r p l r m; do add semgrep "$p" "$l" "$r" "$m"; done <"$tsv"
      [ "$e" = 0 ] || skip semgrep "partial scan: semgrep reported errors"
    else skip semgrep "unparseable output"; fi
  done
fi

# trivy: offline against the cached DB (no download); no DB or any crash reads as not-run, never as clean.
# If the vuln+misconfig scan fails (check bundle unreachable in the sandbox), retry secret-only and say so.
if [ -n "$files" ] && have trivy; then
  tv=(trivy fs --quiet --format json --skip-version-check --skip-db-update --offline-scan --skip-dirs node_modules,.claude/worktrees,vendor,dist,build,.git,.venv,venv,target)
  tk=trivy
  if run_one trivy "${tv[@]}" --scanners vuln,misconfig . && { [ "$rc" = 0 ] || {
    if grep -Eqi 'dial |no such host|connection (refused|reset)|unreachable|x509|TLS|failed to download|download.*(bundle|check)|(bundle|check).*download' "$out"; then
      echo "review_checks: trivy: secret-only (misconfig bundle unreachable)" >&2; tk=trivy-secret; ran+=" trivy(secret-only)"
      run_one trivy "${tv[@]}" --skip-check-update --scanners secret .
    fi; }; } && scan_ok trivy; then
    if sjson "$tk" "$out" >"$tsv"; then
      while IFS=$'\t' read -r f l r m; do printf '%s\n' "$files" | grep -qxF -- "$f" && add trivy "$f" "$l" "$r" "$m"; done <"$tsv"
    else skip trivy "unparseable output"; fi
  fi
fi

# Tool hub registry: name;flags status;mode;match (ERE on changed files);license class;install hint. One row per routed tool.
# Flags were checked against each tool's official docs (verified) or not (unverified: skipped by default). License class:
# route-only = never bundled, only run when the user installed it (licenses unchecked, so nothing is bundle-ok yet).
hub=(
  'zizmor;verified;batch;^\.github/workflows/[^/]+\.ya?ml$;route-only;pipx install zizmor'
  'bandit;verified;batch;\.py$;route-only;pipx install bandit'
  'gosec;verified;batch;\.go$;route-only;go install github.com/securego/gosec/v2/cmd/gosec@latest'
  'grype;verified;each;(^|/)[^/]*(sbom|bom)[^/]*\.json$;route-only;brew install grype'
  'checkov;verified;each;(^|/)(Dockerfile[^/]*|[^/]+\.tf|docker-compose[^/]*\.ya?ml)$;route-only;pipx install checkov'
  'hadolint;verified;each;(^|/)(Dockerfile[^/]*|[^/]+\.dockerfile)$;route-only;brew install hadolint'
  'snyk-agent-scan;unverified;each;(^|/)(\.mcp\.json|mcp[^/]*\.json|SKILL\.md)$;route-only;uvx snyk-agent-scan'
)
# hubcmd TOOL TARGET...: sets cmd (argv), okrc (extra non-crash exit codes) and jf (file the JSON lands in).
hubcmd() {
  local t=$1; shift; jf=$out okrc=""
  case $t in
    zizmor) cmd=(zizmor --format=json --offline "$@"); okrc="11 12 13 14" ;; # 11-14 = findings (docs.zizmor.sh/usage)
    bandit) cmd=(bandit -q -f json --exit-zero "$@") ;;
    gosec) jf=$rep; : >"$rep"; cmd=(env GOPROXY=off gosec -fmt=json -no-fail -out "$rep" ./...) ;;
    grype) cmd=(env GRYPE_DB_AUTO_UPDATE=false grype "sbom:$1" -o json) ;; # SBOM only: dir: scans the whole tree (unverified for lockfiles)
    checkov) cmd=(checkov -f "$1" -o json --quiet --skip-download --soft-fail) ;;
    hadolint) cmd=(hadolint -f json --no-fail "$1") ;;
  esac
}
while IFS=';' read -r hn hs hm hre _ hh; do
  hf=$(changed "$hre"); [ -n "$hf" ] || continue
  nc() { echo "NOT CHECKED: $hn ($1)" >&2; add "$hn" "" 0 not-checked "$1"; }
  if [ "$hs" != verified ]; then nc "$hs flags: skipped by default"; continue; fi
  command -v "$hn" >/dev/null || { nc "install: $hh"; missing+=" $hn"; continue; }
  hubtool=$hn
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
        while IFS=$'\t' read -r p l r m; do printf '%s\n' "$hf" | grep -qxF -- "$p" && add "$hn" "$p" "$l" "$r" "$m"; done <"$tsv"
      else while IFS=$'\t' read -r _ l r m; do add "$hn" "$f" "$l" "$r" "$m"; done <"$tsv"; fi
    else skip "$hn" "unparseable output"; fi
    [ "$hm" != batch ] || break
  done <<<"$([ "$hm" = batch ] && echo x || printf '%s\n' "$hf")"
done < <(printf '%s\n' "${hub[@]}")
hubtool=

lease_drop

if [ "$tests" = 1 ]; then
  if [ -z "${REVIEW_TEST_CMD:-}" ]; then skip tests "REVIEW_TEST_CMD not set"
  elif run_one tests bash -c "$REVIEW_TEST_CMD"; then
    [ "$rc" = 0 ] || add tests "" 0 test-failed "REVIEW_TEST_CMD exited $rc: $(tail -n1 "$out")"
  fi
fi

python3 - "$raw" "$ran" "$missing" "$nex" <<'PY'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8", errors="replace")]
print(json.dumps([{"file": t[1], "line": int(t[2]) if t[2].isdigit() else 0, "rule": t[3], "message": t[4],
                   "text": f"{t[3]}: {t[4]}", "tool": t[0]} for t in rows if len(t) == 5], indent=1))
n = sum(len(t) == 5 for t in rows)
print(f"review_checks: {n} findings; {sys.argv[4]} files excluded; analyzers ran: {', '.join(sys.argv[2].split()) or 'none'}; skipped (not installed): {', '.join(sys.argv[3].split()) or 'none'}", file=sys.stderr)
PY
