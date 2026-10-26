#!/usr/bin/env bash
# supply_chain_check.sh [--online] [--fail-on critical|high|moderate|low] [--scorecard owner/repo] [--allow-skip] [DIR]
# Supply-chain gate that reuses OSS tools; each runs only if installed, else it is reported SKIPPED.
#   osv-scanner  lockfile advisories. Opt-in: needs --online (or SUPPLY_CHAIN_ONLINE=1) because it queries
#                api.osv.dev. Prints counts by severity + fixed versions; fails on >= --fail-on (default high).
#   zizmor, actionlint  static checks on DIR/.github/workflows (local, no network).
#   scorecard    OpenSSF Scorecard for a PUBLIC repo; only with --scorecard owner/repo (queries GitHub).
# Severity bands: advisory database_specific.severity, else the CVSS score OSV reports (>=9 critical, >=7 high,
# >=4 moderate, else low). An advisory with neither (e.g. a CVSS vector string) is "unknown" and counts as at or
# above ANY threshold (fail closed).
# osv-scanner CLI crash (rc>1) retries via the OSV API with curl and prints "osv: api-fallback"; python3+curl needed.
# Exit: 0 every check ran clean; 1 finding at/above threshold or a tool failed; 2 usage;
#       3 INCOMPLETE: a check was skipped (tool or python3 missing, osv/scorecard not requested), nothing failed.
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
for d, ds, fs in os.walk(sys.argv[1]):
    ds[:] = [x for x in ds if x not in (".git", "node_modules", ".venv", "venv", "vendor")]
    for f in fs:
        p = os.path.join(d, f)
        if f == "package-lock.json":
            for k, v in (json.load(open(p)).get("packages") or {}).items():
                if "node_modules/" in k and v.get("version"): pk.add(("npm", k.rsplit("node_modules/", 1)[1], v["version"]))
        elif re.fullmatch(r"requirements.*\.txt", f):
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
    pkgs.append({"package": {"name": n, "version": v}, "groups": [], "vulnerabilities": ids})
for x in vs: vs[x] = api("https://api.osv.dev/v1/vulns/" + x)
for p in pkgs: p["vulnerabilities"] = [vs[x] for x in p["vulnerabilities"]]
print(json.dumps({"results": [{"packages": pkgs}]}))
'
if [ "$online" != 1 ]; then
  skip osv-scanner "opt-in; it queries api.osv.dev (pass --online or SUPPLY_CHAIN_ONLINE=1)"
elif ! have osv-scanner; then skip osv-scanner "not installed"
elif ! have python3; then skip osv-scanner "python3 needed to summarise"
else
  out=$(osv-scanner --format json -r "$dir" 2>/dev/null); osv_rc=$?
  # CLI crash (e.g. Go TLS x509 OSStatus -26276 in the macOS sandbox): POST the lockfile packages to the OSV API via curl.
  if [ "$osv_rc" -gt 1 ] && have curl && fb=$(python3 -I -c "$osv_api" "$dir"); then
    out=$fb; osv_rc=0; echo "osv: api-fallback (osv-scanner CLI failed)"
    # Lockfiles the fallback cannot read: say so and never report a clean pass.
    unread=$(find "$dir" \( -name .git -o -name node_modules -o -name .venv -o -name venv -o -name vendor \) -prune -o -type f \
      \( -name go.mod -o -name go.sum -o -name Cargo.lock -o -name yarn.lock -o -name pnpm-lock.yaml -o -name poetry.lock -o -name Gemfile.lock -o -name composer.lock \) -print | tr '\n' ' ')
    if [ -n "$unread" ]; then echo "partial coverage: ${unread% } not checked"; [ "$allow_skip" = 1 ] || rc=1; fi
  fi
  # osv exit 128 (no package sources) is unconfirmed against osv docs here, so it stays a FAIL.
  if [ "$osv_rc" -gt 1 ]; then echo "FAIL osv-scanner: exit $osv_rc"; rc=1
  else
    printf '%s' "$out" | python3 -I -c '
import json, sys
order = ["low", "moderate", "high", "critical"]
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
counts, rows = {}, []
for res in data.get("results") or []:
    for p in res.get("packages") or []:
        maxg = {i: g.get("max_severity") for g in p.get("groups") or [] for i in g.get("ids", [])}
        for v in p.get("vulnerabilities") or []:
            s = sev(v, maxg.get(v.get("id")))
            counts[s] = counts.get(s, 0) + 1
            rows.append((s, p["package"]["name"], p["package"]["version"], v.get("id"), ",".join(fixed(v)) or "none"))
print("osv-scanner: " + (", ".join("%s=%d" % (s, counts[s]) for s in reversed(order + ["unknown"]) if s in counts) or "no advisories"))
for s, n, ver, i, f in sorted(rows, key=lambda r: -order.index(r[0]) if r[0] in order else 1):
    print("  %-8s %s@%s %s fixed in: %s" % (s, n, ver, i, f))
t = order.index(sys.argv[1])
sys.exit(1 if any(s == "unknown" or order.index(s) >= t for s in counts) else 0)
' "$fail_on" || rc=1
  fi
fi

# --- CI hardening ---
wf="$dir/.github/workflows"
for t in zizmor actionlint; do
  if [ ! -d "$wf" ]; then skip $t "no .github/workflows"
  elif ! have $t; then skip $t "not installed"
  elif [ $t = zizmor ] && ! zizmor "$wf"; then echo "FAIL zizmor"; rc=1
  elif [ $t = actionlint ] && ! (cd "$dir" && actionlint); then echo "FAIL actionlint"; rc=1
  else echo "ok $t"; fi
done

# --- OpenSSF Scorecard (public repos) ---
if [ -z "$sc_repo" ]; then skip scorecard "pass --scorecard owner/repo (public repos; queries GitHub)"
elif ! have scorecard; then skip scorecard "not installed"
elif scorecard --repo="github.com/$sc_repo"; then echo "ok scorecard (review scores above; no pass/fail threshold)"
else echo "FAIL scorecard"; rc=1; fi
if [ "$rc" = 0 ] && [ -n "$skipped" ] && [ "$allow_skip" != 1 ]; then
  echo "INCOMPLETE: skipped$skipped (pass --allow-skip to accept)"; exit 3
fi
exit $rc
