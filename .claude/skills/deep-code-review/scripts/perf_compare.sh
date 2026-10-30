#!/usr/bin/env bash
# perf_compare.sh [--runs N] [--base REF] [--json FILE] -- CMD...: hyperfine A/B of CMD in a detached worktree of BASE vs the current tree; one verdict line.
# Invoke with bash. Rules, caveats and how to read the verdict: references/tool-hub.md (single source).
# Exit: 0 verdict printed, 1 hyperfine missing or the run failed, 2 refused/usage.
set -u
usage="usage: perf_compare.sh [--runs N] [--base REF] [--json FILE] -- CMD..."
refuse() { echo "REFUSED: $*" >&2; exit 2; }
runs=10; base=""; json=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) echo "$usage"; exit 0 ;;
    --runs) [ -n "${2:-}" ] || refuse "--runs needs a number"; runs="$2"; shift 2 ;;
    --base) [ -n "${2:-}" ] || refuse "--base needs a git ref"; base="$2"; shift 2 ;;
    --json) [ -n "${2:-}" ] || refuse "--json needs a file path"; json="$2"; shift 2 ;;
    --) shift; break ;;
    *) refuse "$usage" ;;
  esac
done
[ $# -ge 1 ] || refuse "$usage"
[[ "$runs" =~ ^[1-9][0-9]{0,3}$ ]] && [ "$runs" -ge 2 ] || refuse "--runs must be a whole number from 2 to 9999, got '$runs'"
git rev-parse --git-dir >/dev/null 2>&1 || refuse "not inside a git work tree"
if [ -z "$base" ]; then
  base="$(git merge-base HEAD origin/main 2>/dev/null)" || refuse "no origin/main to take a base from; pass --base REF"
fi
case "$base" in -*) refuse "--base must be a git ref, not an option" ;; esac
sha="$(git rev-parse --verify --quiet "$base^{commit}")" || refuse "--base '$base' is not a commit"
command -v hyperfine >/dev/null 2>&1 || { echo "NOT CHECKED: hyperfine (install: brew install hyperfine)" >&2; exit 1; }

prefix="$(git rev-parse --show-prefix)"
[ -n "$json" ] || json="$(cd "$(git rev-parse --git-common-dir)" && pwd)/perf-compare-last.json"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/perfcmp.XXXXXX")" || exit 1
trap 'git worktree remove --force "$tmp/base" >/dev/null 2>&1; rm -rf "$tmp"' EXIT
trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
# Hooks off for the temporary checkout: a post-checkout hook must not run in it.
git -c core.hooksPath=/dev/null worktree add --quiet --detach "$tmp/base" "$sha" || { echo "perf_compare: could not check out $sha" >&2; exit 1; }
[ -d "$tmp/base/$prefix" ] || { echo "perf_compare: ${prefix:-.} does not exist at $sha" >&2; exit 1; }

# POSIX single quotes (each ' becomes '"'"'): printf %q writes $'..' for control characters, which dash reads as a literal $.
q() { local s="$1" sq="'" sub="'\"'\"'"; printf "'%s'" "${s//$sq/$sub}"; }
# One word after -- is a shell string; several words are quoted for sh so each stays one argument.
if [ $# -eq 1 ]; then cmd="$1"; else cmd=""; for a in "$@"; do cmd="$cmd$(q "$a") "; done; fi
# base runs first, then current, one warm-up each; the current tree is the working tree, uncommitted changes included.
if ! hyperfine --style none --shell=default --warmup 1 --runs "$runs" --export-json "$tmp/hf.json" \
     -n base "cd $(q "$tmp/base/$prefix") && $cmd" -n current "cd $(q "$PWD") && $cmd" >"$tmp/hf.log" 2>&1; then
  tail -n 5 "$tmp/hf.log" >&2
  echo "perf_compare: hyperfine failed; CMD must exit 0 in both trees" >&2; exit 1
fi

python3 -I - "$tmp/hf.json" "$json" <<'PY'
import json, shutil, sys
src, dst = sys.argv[1:3]
def fail(m): sys.exit("perf_compare: " + m)
try:
    d = json.load(open(src))
    s = {r["name"]: r["summary"]["time_wall_clock"] for r in d["results"]}
    b, c = s["base"], s["current"]
    if d["schema_version"] != 2 or b["unit"] != "second" or c["unit"] != "second":
        fail("unsupported hyperfine export (needs schema_version 2 in seconds: hyperfine 2.x)")
    mb, sb, nb = float(b["mean"]), float(b["stddev"]), int(b["count"])
    mc, sc, nc = float(c["mean"]), float(c["stddev"]), int(c["count"])
except (OSError, ValueError, KeyError, TypeError):
    fail("unreadable hyperfine export")
if not mb > 0: fail("base mean is not positive")
# Ranges are mean +- sd and overlap when the means differ by at most sd + sd. That is conservative about run-to-run spread only:
# base runs fully before current, so drift between the two blocks (load, thermal, cache) is outside the sd and can read as slower or faster.
v = "within noise (ranges overlap)" if abs(mc - mb) <= sb + sc else ("slower" if mc > mb else "faster") + " (ranges do not overlap)"
try: shutil.copyfile(src, dst)
except OSError as e: fail("cannot write %s: %s" % (dst, e.strerror))
print("perf_compare: base %.2f ms (sd %.2f, n=%d) | current %.2f ms (sd %.2f, n=%d) | ratio %.2fx | %s | json=%s"
      % (mb * 1e3, sb * 1e3, nb, mc * 1e3, sc * 1e3, nc, mc / mb, v, dst))
PY
