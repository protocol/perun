#!/usr/bin/env bash
# review_checks.sh [--base REF] [--tests] [--timeout SECS] — run local, read-only analyzers over the files
# changed since REF (default origin/main, compared as REF...HEAD) and print findings as a JSON array on
# stdout: [{"file","line","rule","message","text","tool"}]. `text` ("rule: message") is the key
# scripts/score_review.py matches on. Findings are LEADS: verify each against the code before reporting.
#
# Tools, each run only when installed and only on matching changed files: shellcheck + bash -n (*.sh/*.bash),
# python -m py_compile + ruff/pyflakes (*.py), node --check (*.js/*.mjs/*.cjs), tsc --noEmit (*.ts/*.tsx and a
# root tsconfig.json), go vet (*.go and a root go.mod), jq empty (*.json). Optional security scanners:
# gitleaks (changed files only; the secret value is redacted and never printed), osv-scanner (only when a
# changed file is a lockfile and env REVIEW_OSV=1, since it queries the OSV API), semgrep (only with a local rules path in env REVIEW_SEMGREP_CONFIG; never
# `--config auto`, which phones home). `--tests` also runs the command
# declared in env REVIEW_TEST_CMD (opt-in; it executes project code). Never installs anything. A missing tool
# or a timeout prints "review_checks: not run: <tool> (<why>)" on stderr and is not a failure.
# Each tool is timeboxed (default 60s). Exit 0 even with findings; 2 on usage/unresolvable base.
set -euo pipefail

base=origin/main tests=0 tmo=60
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base=${2:?--base needs a ref}; shift 2 ;;
    --timeout) tmo=${2:?--timeout needs seconds}; shift 2 ;;
    --tests) tests=1; shift ;;
    *) echo "usage: review_checks.sh [--base REF] [--tests] [--timeout SECS]" >&2; exit 2 ;;
  esac
done
case "$tmo" in ''|*[!0-9]*) echo "review_checks: --timeout must be an integer" >&2; exit 2 ;; esac
git rev-parse --verify -q "$base^{commit}" >/dev/null || { echo "review_checks: unresolvable base '$base'" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"

raw=$(mktemp "${TMPDIR:-/tmp}/review-raw.XXXXXX") out=$(mktemp "${TMPDIR:-/tmp}/review-out.XXXXXX")
trap 'rm -f "$raw" "$out"' EXIT
files=$(git diff --name-only --diff-filter=ACMR "$base"...HEAD)
rc=0

# Existing changed files matching extended regex $1, one per line.
changed() { { printf '%s\n' "$files" | grep -E "$1" || true; } | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done; true; }
skip() { echo "review_checks: not run: $1 ($2)" >&2; }
# Run "$@" under a timebox; stdout+stderr -> $out. perl alarm when no timeout(1) (stock macOS).
tbox() {
  if command -v timeout >/dev/null; then timeout "$tmo" "$@" >"$out" 2>&1
  elif command -v gtimeout >/dev/null; then gtimeout "$tmo" "$@" >"$out" 2>&1
  else perl -e 'alarm shift; exec @ARGV' "$tmo" "$@" >"$out" 2>&1; fi
}
# have TOOL: 0 when installed, else prints the not-run line.
have() { command -v "$1" >/dev/null || { skip "$1" "not installed"; return 1; }; }
# add TOOL FILE LINE RULE MSG -> one TSV row.
add() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" >>"$raw"; }
# run_one TOOL CMD... : sets rc; returns 1 (with a not-run line) on timeout.
run_one() {
  local tool=$1; shift; rc=0
  tbox "$@" || rc=$?
  case "$rc" in 124|142) skip "$tool" "timeout ${tmo}s"; return 1 ;; esac
  return 0
}
# Findings parsed from $out by a sed script (TSV columns) land via `add`.
sh_files=$(changed '\.(sh|bash)$')
if [ -n "$sh_files" ]; then
  if have shellcheck; then
    while IFS= read -r f; do
      run_one shellcheck shellcheck -f gcc "$f" || continue
      sed -nE 's/^.*:([0-9]+):[0-9]+: [a-z]+: (.*) \[(SC[0-9]+)\]$/\1\t\3\t\2/p' "$out" |
        while IFS=$'\t' read -r l r m; do add shellcheck "$f" "$l" "$r" "$m"; done
    done <<<"$sh_files"
  fi
  while IFS= read -r f; do
    run_one bash-n bash -n "$f" || continue
    [ "$rc" = 0 ] || add bash-n "$f" "$(sed -nE 's/.*line ([0-9]+):.*/\1/p' "$out" | head -n1)" syntax "$(head -n1 "$out")"
  done <<<"$sh_files"
fi

py_files=$(changed '\.py$')
if [ -n "$py_files" ]; then
  if have python3; then
    while IFS= read -r f; do
      run_one py_compile python3 -c 'import sys;compile(open(sys.argv[1],"rb").read(),sys.argv[1],"exec")' "$f" || continue
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
      run_one "$ln" "${lint[@]}" "$f" || continue
      sed -nE 's/^.*:([0-9]+):[0-9]+:? ([A-Z]+[0-9]+ )?(.*)$/\1\t\2\t\3/p' "$out" |
        while IFS=$'\t' read -r l r m; do add "$ln" "$f" "$l" "${r% }" "$m"; done
    done <<<"$py_files"
  fi
fi

js_files=$(changed '\.(js|mjs|cjs)$')
if [ -n "$js_files" ] && have node; then
  while IFS= read -r f; do
    run_one node-check node --check "$f" || continue
    [ "$rc" = 0 ] || add node-check "$f" "$(sed -nE 's/^.*:([0-9]+)$/\1/p' "$out" | head -n1)" SyntaxError "$(grep -m1 'Error' "$out" || head -n1 "$out")"
  done <<<"$js_files"
fi

if [ -n "$(changed '\.(ts|tsx)$')" ] && [ -f tsconfig.json ] && have tsc; then
  if run_one tsc tsc --noEmit -p tsconfig.json; then
    sed -nE 's/^(.*)\(([0-9]+),[0-9]+\): error (TS[0-9]+): (.*)$/\1\t\2\t\3\t\4/p' "$out" |
      while IFS=$'\t' read -r f l r m; do add tsc "$f" "$l" "$r" "$m"; done
  fi
fi

if [ -n "$(changed '\.go$')" ] && [ -f go.mod ] && have go; then
  if run_one go-vet go vet ./...; then
    sed -nE 's/^([^#[:space:]][^:]*\.go):([0-9]+):[0-9]+: (.*)$/\1\t\2\t\3/p' "$out" |
      while IFS=$'\t' read -r f l m; do add go-vet "$f" "$l" vet "$m"; done
  fi
fi

json_files=$(changed '\.json$')
if [ -n "$json_files" ] && have jq; then
  while IFS= read -r f; do
    run_one jq jq empty "$f" || continue
    [ "$rc" = 0 ] || add jq "$f" "$(sed -nE 's/.*line ([0-9]+).*/\1/p' "$out" | head -n1)" invalid-json "$(head -n1 "$out")"
  done <<<"$json_files"
fi

# Scanner JSON (file $2, may have log noise before the JSON) of kind $1 -> TSV: file, line, rule, message.
sjson() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null || true
import json, sys
kind = sys.argv[1]
t = open(sys.argv[2], encoding="utf-8", errors="replace").read()
i = min([x for x in (t.find("{"), t.find("[")) if x >= 0], default=-1)
d = json.JSONDecoder().raw_decode(t[i:])[0] if i >= 0 else []
rows = []
if kind == "gitleaks":  # Secret/Match fields are deliberately never read
    rows = [(r.get("File"), r.get("StartLine"), r.get("RuleID"), r.get("Description") or "secret detected") for r in d]
elif kind == "semgrep":
    rows = [(r["path"], r["start"]["line"], r.get("check_id"), (r.get("extra") or {}).get("message", "")) for r in d.get("results") or []]
else:
    for r in d.get("results") or []:
        for p in r.get("packages") or []:
            pk = p.get("package") or {}
            rows += [(r["source"]["path"], 0, v.get("id"), f"{pk.get('name')}@{pk.get('version')}: {v.get('summary', '')}")
                     for v in p.get("vulnerabilities") or []]
for row in rows:
    print("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in row))
PY
}

if have gitleaks; then
  rep=$(mktemp "${TMPDIR:-/tmp}/review-gl.XXXXXX"); trap 'rm -f "$raw" "$out" "$rep"' EXIT
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    run_one gitleaks gitleaks detect --no-git --no-banner --redact --exit-code 0 -f json -r "$rep" -s "$f" || continue
    sjson gitleaks "$rep" | while IFS=$'\t' read -r _ l r m; do add gitleaks "$f" "$l" "$r" "$m"; done
    : >"$rep"
  done <<<"$files"
fi

lock_files=$(changed '(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|Cargo\.lock|poetry\.lock|requirements[^/]*\.txt|composer\.lock)$')
if [ -z "$lock_files" ]; then :
elif [ "${REVIEW_OSV:-}" != 1 ]; then skip osv-scanner "REVIEW_OSV not set; osv-scanner queries the OSV API"
elif have osv-scanner; then
  while IFS= read -r f; do
    run_one osv-scanner osv-scanner --format json -L "$f" || continue
    sjson osv "$out" | while IFS=$'\t' read -r _ l r m; do add osv-scanner "$f" "$l" "$r" "$m"; done
  done <<<"$lock_files"
fi

if [ -z "${REVIEW_SEMGREP_CONFIG:-}" ]; then skip semgrep "REVIEW_SEMGREP_CONFIG not set; --config auto is never used"
elif [ ! -e "$REVIEW_SEMGREP_CONFIG" ]; then skip semgrep "REVIEW_SEMGREP_CONFIG must be an existing local path"
elif have semgrep; then
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    run_one semgrep semgrep --config "$REVIEW_SEMGREP_CONFIG" --json --quiet --metrics=off --disable-version-check "$f" || continue
    sjson semgrep "$out" | while IFS=$'\t' read -r _ l r m; do add semgrep "$f" "$l" "$r" "$m"; done
  done <<<"$files"
fi

if [ "$tests" = 1 ]; then
  if [ -z "${REVIEW_TEST_CMD:-}" ]; then skip tests "REVIEW_TEST_CMD not set"
  elif run_one tests bash -c "$REVIEW_TEST_CMD"; then
    [ "$rc" = 0 ] || add tests "" 0 test-failed "REVIEW_TEST_CMD exited $rc: $(tail -n1 "$out")"
  fi
fi

python3 - "$raw" <<'PY'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8", errors="replace")]
print(json.dumps([{"file": t[1], "line": int(t[2]) if t[2].isdigit() else 0, "rule": t[3], "message": t[4],
                   "text": f"{t[3]}: {t[4]}", "tool": t[0]} for t in rows if len(t) == 5], indent=1))
PY
