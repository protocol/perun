#!/usr/bin/env bash
# supply_chain_check.sh [--online] [--fail-on critical|high|moderate|low] [--scorecard owner/repo] [--allow-skip] [DIR]
# Supply-chain gate that reuses OSS tools; each runs only if installed, else it is reported SKIPPED. zizmor/actionlint print "n/a" (never SKIPPED/INCOMPLETE) when DIR has no .github/workflows/*.y*ml.
#   osv-scanner  lockfile advisories. Opt-in: needs --online (or SUPPLY_CHAIN_ONLINE=1) because it queries
#                api.osv.dev. Prints counts by severity + fixed versions; fails on >= --fail-on (default high).
#   zizmor, actionlint  static checks on DIR/.github/workflows (local, no network).
#   scorecard    OpenSSF Scorecard, informational scores, no threshold. --scorecard owner/repo scores a PUBLIC repo remotely
#                (queries GitHub). Without it, a git DIR is scanned offline from an export of HEAD (tracked files only, so an
#                untracked node_modules never scores) with the checks that work offline; Vulnerabilities (a false 10 while
#                api.osv.dev is unreachable) and Fuzzing (errors) never run there. That is a partial view, not comparable with
#                a public Scorecard score: SAST sees workflow files only, and export-ignore paths are not scored. A subdirectory
#                DIR scores the whole repo root (the ok line says so). A non-git DIR, or a partial clone missing objects (lazy
#                fetch stays off, so this never touches the network), is SKIPPED.
# Severity bands: advisory database_specific.severity, else the CVSS score OSV reports (>=9 critical, >=7 high,
# >=4 moderate, else low). An advisory with neither (e.g. a CVSS vector string) is "unknown" and counts as at or
# above ANY threshold (fail closed).
# osv-scanner CLI crash (rc>1) retries via the OSV API with curl and prints "osv: api-fallback"; python3+curl needed.
# Exit: 0 every check ran clean; 1 finding at/above threshold or a tool failed; 2 usage;
#       3 INCOMPLETE: a check was skipped (tool or python3 missing, osv not requested, scorecard with no exportable git HEAD), nothing failed.
#       Reach: an npm osv row no source file imports prints "(reach: dev-only|transitive)"; only dev-only skips the gate
#       unless SUPPLY_CHAIN_STRICT=1 (transitive may be reached via a direct dependency); unknown reach is gated.
#       --allow-skip turns a skip-only run into exit 0. A finding (1) wins over INCOMPLETE (3). Needs python3 for osv.
set -u
online=${SUPPLY_CHAIN_ONLINE:-0}; fail_on=high; sc_repo=; allow_skip=0; skipped=
need() { [ "$1" -ge 2 ] || { echo "$2 needs a value" >&2; exit 2; }; }
while [ $# -gt 0 ]; do
  case $1 in
    --online) online=1 ;;
    --allow-skip) allow_skip=1 ;;
    --fail-on) need $# --fail-on; fail_on=$2; shift ;;
    --scorecard) need $# --scorecard; sc_repo=$2; shift ;;
    -*) echo "usage: $0 [--online] [--fail-on critical|high|moderate|low] [--scorecard owner/repo] [--allow-skip] [DIR]" >&2; exit 2 ;;
    *) dir=$1 ;;
  esac
  shift
done
case $fail_on in critical|high|moderate|low) ;; *) echo "bad --fail-on: $fail_on" >&2; exit 2 ;; esac
[[ -z $sc_repo || $sc_repo =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "bad --scorecard (want owner/repo): $sc_repo" >&2; exit 2; }
dir=${dir:-.}; rc=0
have() { command -v "$1" >/dev/null 2>&1; }
skip() { echo "SKIPPED $1: $2"; skipped="$skipped $1"; }

# --- osv-scanner ---
# Fallback: npm package-lock.json and pinned requirements*.txt only; other lockfiles print "partial coverage" and fail unless --allow-skip.
# Prints osv-scanner-shaped JSON; any API or curl error exits 1 so the caller keeps the CLI failure.
osv_api='import json, os, re, subprocess, sys
def api(url, body=None):
    c = ["curl", "-fsS", "--max-time", "60", url] + (["-H", "Content-Type: application/json", "-d", json.dumps(body)] if body else [])
    return json.loads(subprocess.run(c, capture_output=True, text=True, check=True).stdout)
pk = set()
cand = []
for d, ds, fs in os.walk(sys.argv[1]):
    ds[:] = [x for x in ds if x not in (".git", "node_modules", ".venv", "venv", "vendor")]
    cand += [os.path.join(d, f) for f in fs if f == "package-lock.json" or re.fullmatch(r"requirements.*\.txt", f)]
# like osv-scanner -r: skip gitignored copies (stale build/worktree locks), else old versions flag a patched repo.
# One git call; any git failure (missing, not a repo, rc 128) means nothing is treated as ignored.
ign = set()
try:
    g = subprocess.run(["git", "-C", sys.argv[1], "check-ignore", "--stdin", "-z"], input="\0".join(cand), capture_output=True, text=True)
    if g.returncode in (0, 1): ign = set(g.stdout.split("\0"))
except OSError: pass
for p in cand:
    f = os.path.basename(p)
    if p in ign: print("skipped gitignored: " + p, file=sys.stderr); continue
    if f == "package-lock.json":
        for k, v in (json.load(open(p)).get("packages") or {}).items():
            if "node_modules/" in k and v.get("version"): pk.add(("npm", k.rsplit("node_modules/", 1)[1], v["version"]))
    else:
        for l in open(p):
            m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;#]+)", l)
            if m: pk.add(("PyPI", m[1], m[2]))
pk = sorted(pk)
if not pk: sys.exit("osv api fallback: no npm/pip lockfile packages found")
res = []
for i in range(0, len(pk), 1000):
    q = [{"package": {"ecosystem": e, "name": n}, "version": v} for e, n, v in pk[i:i + 1000]]
    r = api("https://api.osv.dev/v1/querybatch", {"queries": q})["results"]
    assert len(r) == len(q), "osv api fallback: result count mismatch"
    res += r
vs = {}
pkgs = []
for (e, n, v), r in zip(pk, res):
    ids = [x["id"] for x in r.get("vulns") or []]
    for x in ids: vs.setdefault(x, None)
    pkgs.append({"package": {"name": n, "version": v, "ecosystem": e}, "groups": [], "vulnerabilities": ids})
for x in vs: vs[x] = api("https://api.osv.dev/v1/vulns/" + x)
for p in pkgs: p["vulnerabilities"] = [vs[x] for x in p["vulnerabilities"]]
print(json.dumps({"results": [{"packages": pkgs}]}))
'
if [ "$online" != 1 ]; then
  skip osv-scanner "opt-in; it queries api.osv.dev (pass --online or SUPPLY_CHAIN_ONLINE=1)"
elif ! have osv-scanner; then skip osv-scanner "not installed"
elif ! have python3; then skip osv-scanner "python3 needed to summarise"
else
  # REVIEW_OSV_DB_DIR: pre-seeded DB, offline run. Missing DB keeps the CLI failure (never clean) and prints the warm command.
  osvx=(); [ -z "${REVIEW_OSV_DB_DIR:-}" ] || { export OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$REVIEW_OSV_DB_DIR; osvx=(--offline-vulnerabilities)
    [ -n "$(find "$REVIEW_OSV_DB_DIR" -type f -name '*.zip' 2>/dev/null | head -n1)" ] || osv_empty=1; }
  if [ "${osv_empty:-}" = 1 ]; then out=; osv_rc=0
  else out=$(osv-scanner ${osvx[@]+"${osvx[@]}"} --format json -r "$dir" 2>/dev/null); osv_rc=$?; fi
  # CLI crash (e.g. Go TLS x509 OSStatus -26276 in the macOS sandbox): POST the lockfile packages to the OSV API via curl.
  if [ "$osv_rc" -gt 1 ] && [ -z "${REVIEW_OSV_DB_DIR:-}" ] && have curl && fb=$(python3 -I -c "$osv_api" "$dir"); then
    out=$fb; osv_rc=0; echo "osv: api-fallback (osv-scanner CLI failed)"
    # Lockfiles the fallback cannot read: say so and never report a clean pass.
    unread=$(find "$dir" \( -name .git -o -name node_modules -o -name .venv -o -name venv -o -name vendor \) -prune -o -type f \
      \( -name go.mod -o -name go.sum -o -name Cargo.lock -o -name yarn.lock -o -name pnpm-lock.yaml -o -name poetry.lock -o -name Gemfile.lock -o -name composer.lock \) -print | tr '\n' ' ')
    if [ -n "$unread" ]; then echo "partial coverage: ${unread% } not checked"; [ "$allow_skip" = 1 ] || rc=1; fi
  fi
  # osv exit 128 (no package sources) is unconfirmed against osv docs here, so it stays a FAIL.
  if [ "${osv_empty:-}" = 1 ]; then
    echo "FAIL osv-scanner: NOT CHECKED, no pre-seeded DB; warm it once: OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$REVIEW_OSV_DB_DIR osv-scanner --offline-vulnerabilities --download-offline-databases ."; rc=1
  elif [ "$osv_rc" -gt 1 ]; then echo "FAIL osv-scanner: exit $osv_rc"; rc=1
  else
    printf '%s' "$out" | python3 -I -c '
import json, os, re, sys
order = ["low", "moderate", "high", "critical"]
# Reach tag per row: imported (npm name in a JS/TS import, require or dynamic import outside node_modules/.git, and outside
# a root-level .venv/venv/vendor), dev-only (npm "dev": true on every occurrence, or an osv dev/build/test group), else
# transitive (it may be reached through a direct dependency, so it still gates). Every row not imported prints "(reach: <tag>)";
# only dev-only skips the --fail-on gate, unless SUPPLY_CHAIN_STRICT=1. Unknown (unreadable file, lockfile without a "packages"
# map, non-npm ecosystem, no ecosystem field) is imported = gated. PyPI dist names differ from module names, so PyPI is
# downgraded only by a dev group. ponytail: regex scan misses computed require(x) and config-string use; symlinks not followed.
devs, prods, imp, scan_ok = set(), set(), set(), True
JS = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["\x27\x60]([^"\x27\x60]+)["\x27\x60]""")
for d, ds, fs in os.walk(sys.argv[2], onerror=lambda e: globals().update(scan_ok=False)):
    ds[:] = [x for x in ds if x not in (".git", "node_modules") and not (d == sys.argv[2] and x in (".venv", "venv", "vendor"))]
    for f in fs:
        if f.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro", ".mdx")):
            try: txt = open(os.path.join(d, f), errors="replace").read()
            except OSError: scan_ok = False; continue
            for m in JS.findall(txt):
                if m[0] not in ".#/" and ":" not in m: imp.add("/".join(m.split("/")[:2 if m[0] == "@" else 1]))
    if "package-lock.json" in fs:
        try:
            for k, v in json.load(open(os.path.join(d, "package-lock.json")))["packages"].items():  # v1 has no "packages": fail closed
                if "node_modules/" in k: (devs if v.get("dev") else prods).add(k.rsplit("node_modules/", 1)[1] + "@" + str(v.get("version")))
        except (OSError, ValueError, AttributeError, KeyError): scan_ok = False
def devonly(p):
    k = p["package"]["name"] + "@" + str(p["package"]["version"])
    if p["package"].get("ecosystem") == "npm" and (k in devs or k in prods): return k not in prods  # the lock is authoritative: dev only if every occurrence is dev
    return bool({str(g).lower() for g in p.get("dependency_groups") or []} & {"dev", "build", "test"})
def reach(p):
    n, e = p["package"]["name"], p["package"].get("ecosystem")
    if not scan_ok or (n in imp and e == "npm"): return "imported"
    return "dev-only" if devonly(p) else "transitive" if e == "npm" else "imported"
def sev(v, g):
    s = str((v.get("database_specific") or {}).get("severity", "")).lower()
    if s == "medium": s = "moderate"
    if s in order: return s
    try: n = float(g)
    except (TypeError, ValueError): return "unknown"
    return "critical" if n >= 9 else "high" if n >= 7 else "moderate" if n >= 4 else "low"
def fixed(v):
    return sorted({e["fixed"] for a in v.get("affected", []) for r in a.get("ranges", []) for e in r.get("events", []) if "fixed" in e})
try: data = json.load(sys.stdin)
except ValueError: print("FAIL osv-scanner: unparseable output"); sys.exit(1)
strict = os.environ.get("SUPPLY_CHAIN_STRICT") == "1"
counts, gate, rows, down = {}, {}, [], 0
for res in data.get("results") or []:
    for p in res.get("packages") or []:
        maxg = {i: g.get("max_severity") for g in p.get("groups") or [] for i in g.get("ids", [])}
        for v in p.get("vulnerabilities") or []:
            s, r = sev(v, maxg.get(v.get("id"))), reach(p)
            counts[s] = counts.get(s, 0) + 1
            if r != "dev-only" or strict: gate[s] = gate.get(s, 0) + 1
            else: down += 1
            rows.append((s, p["package"]["name"], p["package"]["version"], v.get("id"), (",".join(fixed(v)) or "none") + ("" if r == "imported" else " (reach: %s)" % r)))
print("osv-scanner: " + (", ".join("%s=%d" % (s, counts[s]) for s in reversed(order + ["unknown"]) if s in counts) or "no advisories"))
for s, n, ver, i, f in sorted(rows, key=lambda r: -order.index(r[0]) if r[0] in order else 1):
    print("  %-8s %s@%s %s fixed in: %s" % (s, n, ver, i, f))
if down: print("  %d dev-only: excluded from the --fail-on gate (SUPPLY_CHAIN_STRICT=1 gates them)" % down)
t = order.index(sys.argv[1])
sys.exit(1 if any(s == "unknown" or order.index(s) >= t for s in gate) else 0)
' "$fail_on" "$dir" || rc=1
  fi
fi

# --- CI hardening ---
wf="$dir/.github/workflows"
for t in zizmor actionlint; do
  if [ -z "$(find "$wf" -maxdepth 1 -name '*.y*ml' 2>/dev/null | head -n1)" ]; then echo "n/a $t: no workflow files, not applicable"
  elif ! have $t; then skip $t "not installed"
  elif [ $t = zizmor ] && ! zizmor "$wf"; then echo "FAIL zizmor"; rc=1
  elif [ $t = actionlint ] && ! (cd "$dir" && find .github/workflows -maxdepth 1 -name '*.y*ml' -exec actionlint {} +); then echo "FAIL actionlint"; rc=1
  else echo "ok $t"; fi
done

# --- OpenSSF Scorecard ---
# Local mode scans the repo root's HEAD export, like the remote mode scores the whole repo whatever DIR is.
# ponytail: git archive honors export-ignore, so such paths are not scored; use git checkout-index --prefix if that bites.
# GIT_NO_LAZY_FETCH=1 stops a partial clone fetching missing blobs (network); a git that ignores it may still do so.
sc_local() {
  local top sub=
  top=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null) || { skip scorecard "DIR is not a git repo (or git is missing); pass --scorecard owner/repo (public repos; queries GitHub)"; return; }
  [ -n "$(git -C "$dir" rev-parse --show-prefix)" ] && sub=", DIR is a subdirectory so the whole repo is scored"
  sc_ex=$(mktemp -d "${TMPDIR:-/tmp}/supply-chain-sc.XXXXXX") || { skip scorecard "mktemp failed"; return; }
  trap 'rm -rf "$sc_ex"' EXIT # also on SIGTERM/SIGHUP/SIGINT: the export is a full copy of the tracked files
  if ! (set -o pipefail; GIT_NO_LAZY_FETCH=1 git -C "$top" archive HEAD | tar -x -C "$sc_ex"); then skip scorecard "git archive HEAD failed (no commits, or objects missing in a partial clone: lazy fetch is off to stay offline)"
  elif scorecard --local="$sc_ex" --show-details \
    --checks=Binary-Artifacts,Dangerous-Workflow,Dependency-Update-Tool,License,Packaging,Pinned-Dependencies,SAST,Security-Policy,Token-Permissions
  then echo "ok scorecard (local export of HEAD in $top$sub; partial view, not comparable with a public Scorecard score; no pass/fail threshold)"
  else echo "FAIL scorecard"; rc=1; fi
}
if ! have scorecard; then skip scorecard "not installed"
elif [ -z "$sc_repo" ]; then sc_local
elif scorecard --repo="github.com/$sc_repo"; then echo "ok scorecard (review scores above; no pass/fail threshold)"
else echo "FAIL scorecard"; rc=1; fi
if [ "$rc" = 0 ] && [ -n "$skipped" ] && [ "$allow_skip" != 1 ]; then
  echo "INCOMPLETE: skipped$skipped (pass --allow-skip to accept)"; exit 3
fi
exit $rc
