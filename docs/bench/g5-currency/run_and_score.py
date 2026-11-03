#!/usr/bin/env python3
"""G5 scored run: detector vs truth/*.json + a fresh registry snapshot (PREREGISTERED.md, gate G5). Stdlib only.

Usage:
  run_and_score.py SNAPSHOT.json DETECTOR_REPO [--out DIR]   the ONE scored run (refuses an existing --out)
  run_and_score.py ... --set DIR                              use DIR/{fixtures,truth,drift.json} instead of this dir (set #2)
  run_and_score.py --self-test                               synthetic rows, no network, no detector

Per fixture: copy to a temp git repo, run `review_checks.sh --full` (default budget = the scored, default surface)
and `dependency_currency.py --json` (script-only, informational), save raw output beside score.json.

Rules (default surface):
  * effective latest = snapshot latest; truth row is outdated when current != latest, else a decoy.
  * outdated row = hit only if a dep-currency row has the same alias-normalised name, rule in kev|vulnerable|eol|outdated,
    and latest == snapshot latest. Aliases come from the detector SOURCE (IMAGES, FRAMEWORKS, runtime-file labels).
  * a decoy with an outdated|drift|eol row is a false flag; not-checked / NOT RUN / no row is a miss.
  * eol true needs an eol row; vendored needs a vendored row; expected drift rows are DRIFT below (build.py "# drift").
  * every hit's upgrade target must resolve (registry: in snapshot.versions; runtime/action: matches snapshot latest).
  * KEV-first: OSV + CISA KEV queried independently; "not exercised" when no truth row is KEV-listed or lookup fails.
Ceilings: name-only matching (names are unique per fixture, checked); go/maven OSV queries use the same name forms as truth.
"""
import ast, datetime, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, urllib.request
from http.client import IncompleteRead

HERE = os.path.dirname(os.path.abspath(__file__))
SET = HERE  # --set DIR swaps this; scripts and default results dir stay under HERE
RC = ".claude/skills/deep-code-review/scripts/review_checks.sh"
DC = ".claude/skills/deep-code-review/scripts/dependency_currency.py"
# from build.py "# drift" comments: fixture -> names that must produce a drift row
DRIFT = {"npm": ["lodash"], "pip": ["flask"], "go": ["golang.org/x/net"], "maven": ["org.apache.commons:commons-lang3"],
         "gradle": ["com.fasterxml.jackson.core:jackson-databind"], "cargo": ["tokio"], "composer": ["guzzlehttp/guzzle"],
         "monorepo": ["express"]}
RUNTIME_LABELS = {".nvmrc": "nodejs", ".node-version": "nodejs", ".python-version": "python", ".ruby-version": "ruby",
                  "go directive": "go"}  # asserted present in detector source by aliases()
KIND = {"docker": "runtime", "eol": "runtime", "actions": "action"}
OSV_ECO = {"npm": "npm", "pip": "PyPI", "go": "Go", "maven": "Maven", "gradle": "Maven", "cargo": "crates.io", "composer": "Packagist"}
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
HIT_RULES = {"kev", "vulnerable", "eol", "outdated"}


def nv(x):
    """Version string without a leading v."""
    return str(x or "").strip().lstrip("vV")


def aliases(detector):
    """Label -> product map built only from detector source: IMAGES, FRAMEWORKS values, runtime-file labels."""
    src = open(os.path.join(detector, DC)).read()
    lit = {}
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("IMAGES", "FRAMEWORKS"):
            lit[n.targets[0].id] = ast.literal_eval(n.value)
    for lab in RUNTIME_LABELS:
        assert '"%s"' % lab in src, "runtime label not in detector source: " + lab
    m = dict(lit["IMAGES"])
    m.update({name: prod for (_, name), prod in lit["FRAMEWORKS"].items()})
    m.update(RUNTIME_LABELS)
    return m


def canon(kind, name, al):
    """Alias-normalised name: runtime labels -> endoflife product; pip PEP 503."""
    if kind == "runtime":
        return al.get(name, name)
    return re.sub(r"[-_.]+", "-", name).lower() if kind == "pip" else name


def parse_default(r):
    """review_checks row -> normalised dict (message: 'kind name; current X, latest Y; ...; upgrade to T; ...')."""
    seg = r["message"].split("; ")
    kind, _, name = seg[0].partition(" ")
    m = re.search(r"current ([^\s,;]*), latest ([^\s,;]*)", r["message"])
    t = re.search(r"upgrade to ([^;]+)", r["message"])
    cl = lambda s: "" if s in (None, "-") else s
    return {"rule": r["rule"], "kind": kind, "name": name, "current": cl(m[1]) if m else "", "latest": cl(m[2]) if m else "",
            "target": t[1].strip() if t else "", "file": r["file"], "message": r["message"]}


def parse_script(r):
    """dependency_currency --json row -> normalised dict."""
    return {"rule": r["rule"], "kind": r["kind"], "name": r["name"], "current": r["current"], "latest": r["latest"],
            "target": r["target"], "file": r["file"], "message": r.get("note", "")}


def eff_status(r):
    """Row's real status behind a kev/vulnerable override: outdated when its own current != latest."""
    if r["rule"] in ("kev", "vulnerable"):
        return "outdated" if r["current"] and r["latest"] and nv(r["current"]) != nv(r["latest"]) else "current"
    return r["rule"]


def target_ok(t, kind, name, snap_latest, versions):
    """Does an upgrade target resolve? registry: listed by snapshot.versions; runtime/action: matches snapshot latest."""
    if not t or "unverified" in t:
        return False
    if kind in OSV_ECO:
        return nv(t) in {nv(v) for v in versions(kind, name)}
    tag = nv(t.split("@")[-1].split(":")[-1])
    m = re.match(r"\d+(\.\d+)*", tag)
    return bool(m) and nv(snap_latest).startswith(m[0])


def score(fx, truth, snap, rows, al, versions, drift):
    """Criteria for one fixture -> dict name -> list of failure strings (empty = pass)."""
    out = {"outdated_hits": [], "decoys_clean": [], "eol_rows": [], "vendored_rows": [], "drift_rows": [], "targets_resolve": []}
    by = {}
    for r in rows:
        by.setdefault((r["kind"], canon(r["kind"], r["name"], al)), []).append(r)
    for t in truth:
        eco = t["ecosystem"]
        kind = KIND.get(eco, eco)
        nm = canon(kind, t.get("eol_product") or t["name"], al)
        s = snap["%s:%s" % (eco, t["name"])]
        sl, rs = s["latest"], by.get((kind, nm), [])
        if t.get("vendored"):
            top = t["file"]
            if not any(r["rule"] == "vendored" and top.startswith(r["file"] + "/") for r in rows):
                out["vendored_rows"].append(t["name"])
            continue
        if nv(t["current"]) == nv(sl):  # decoy
            bad = [r["rule"] for r in rs if eff_status(r) in ("outdated", "drift", "eol")]
            if bad:
                out["decoys_clean"].append("%s (%s)" % (t["name"], ",".join(bad)))
            continue
        hit = [r for r in rs if r["rule"] in HIT_RULES and nv(r["latest"]) == nv(sl)]
        if not hit:
            why = "NOT RUN" if any(r["rule"] == "not-checked" for r in rs) else "no row" if not rs else "wrong rule/latest"
            out["outdated_hits"].append("%s (%s)" % (t["name"], why))
            continue
        if not any(versions is not None and target_ok(r["target"], kind, t["name"], sl, versions) for r in hit):
            out["targets_resolve"].append(t["name"])
        if s.get("eol", t.get("eol")) and not any(r["rule"] == "eol" for r in hit):
            out["eol_rows"].append(t["name"])
    for n in drift:
        if not any(r["rule"] == "drift" for k, v in by.items() if k[1] == canon(k[0], n, al) for r in v):
            out["drift_rows"].append(n)
    return out


def http(url, data=None):
    """GET/POST JSON."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "g5-score/1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def kev_ids():
    """CISA KEV cveID set; retries 3x on a truncated body (IncompleteRead) or network error (OSError), then re-raises."""
    for i in range(3):
        try:
            return {v["cveID"] for v in http(KEV_URL)["vulnerabilities"]}
        except (IncompleteRead, OSError):
            if i == 2:
                raise


def kev_expected(truths):
    """Independent OSV + CISA KEV: set of (fixture, name) whose truth current version has a KEV-listed CVE. None on lookup failure."""
    try:
        kev = kev_ids()
        exp = set()
        for fx, rows in truths.items():
            reg = [t for t in rows if t["ecosystem"] in OSV_ECO and not t.get("vendored")]
            for i in range(0, len(reg), 100):
                chunk = reg[i:i + 100]
                qs = [{"package": {"name": t["name"], "ecosystem": OSV_ECO[t["ecosystem"]]}, "version": nv(t["current"]) if t["ecosystem"] == "go" else t["current"]} for t in chunk]
                res = http("https://api.osv.dev/v1/querybatch", json.dumps({"queries": qs}).encode())["results"]
                for t, x in zip(chunk, res):
                    for v in x.get("vulns", []):
                        d = http("https://api.osv.dev/v1/vulns/" + v["id"])
                        if kev & ({d["id"]} | set(d.get("aliases", []))):
                            exp.add((fx, t["name"]))
        return exp
    except Exception as e:  # noqa: BLE001 - any failure means not exercised
        print("KEV lookup failed:", type(e).__name__, e, file=sys.stderr)
        return None


def kev_first(exp_fx, rows, al):
    """Failures: expected KEV rows without a kev rule, or a kev row after a non-kev row (rows in detector output order)."""
    bad = [n for n in exp_fx if not any(r["rule"] == "kev" and canon(r["kind"], r["name"], al) == canon(r["kind"], n, al) for r in rows)]
    seen_other = False
    for r in rows:
        if r["rule"] != "kev":
            seen_other = True
        elif seen_other:
            bad.append("order: " + r["name"])
    return bad


def sh(cmd, cwd, env=None):
    """Run a command, return (stdout, stderr)."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, timeout=900)
    return p.stdout, p.stderr


def run(snapfile, detector, out):
    """The scored run."""
    os.makedirs(out)  # refuses to overwrite an earlier run
    snap = json.load(open(snapfile))
    al = aliases(detector)
    sv = importlib.util.spec_from_file_location("snapshot", os.path.join(HERE, "snapshot.py"))
    S = importlib.util.module_from_spec(sv)
    sv.loader.exec_module(S)
    truths = {os.path.basename(f)[:-5]: json.load(open(os.path.join(SET, "truth", f))) for f in sorted(os.listdir(os.path.join(SET, "truth")))}
    age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.strptime(snap["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)).total_seconds() / 3600
    crit = {"snapshot_fresh_24h": [] if age <= 24 else ["snapshot is %.1fh old" % age]}
    drift_map = json.load(open(os.path.join(SET, "drift.json"))) if SET != HERE else DRIFT
    exp = kev_expected(truths)
    res = {"default": {}, "script-only": {}}
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    kevfail = []
    for fx, truth in truths.items():
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "r")
            shutil.copytree(os.path.join(SET, "fixtures", fx), repo)
            for c in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "fixture"]):
                sh(c, repo, env)
            o1, e1 = sh(["bash", os.path.join(detector, RC), "--repo", repo, "--full"], repo)
            o2, e2 = sh(["python3", os.path.join(detector, DC), "--root", repo, "--json"], repo)
        for tag, o, e in (("default", o1, e1), ("scriptonly", o2, e2)):
            open(os.path.join(out, "%s.%s.json" % (fx, tag)), "w").write(o)
            open(os.path.join(out, "%s.%s.stderr" % (fx, tag)), "w").write(e)
        try:
            rd = [parse_default(r) for r in json.loads(o1) if r.get("tool") == "dep-currency"]
        except ValueError:
            rd = []
        try:
            rs = [parse_script(r) for r in json.loads(o2)]
        except ValueError:
            rs = []
        for lab, rows in (("default", rd), ("script-only", rs)):
            res[lab][fx] = score(fx, truth, snap["fixtures"][fx], rows, al, S.versions, drift_map.get(fx, []))
        if exp:
            kevfail += ["%s:%s" % (fx, b) for b in kev_first([n for f, n in exp if f == fx], rd, al)]
    for c in res["default"][next(iter(truths))]:
        crit[c] = ["%s: %s" % (fx, x) for fx, d in res["default"].items() for x in d[c]]
    crit["kev_first"] = None if exp is None or not exp else kevfail
    return report(crit, res, exp, out)


def report(crit, res, exp, out=None):
    """Print PASS/FAIL per criterion + overall; write score.json when out is given. Returns overall bool."""
    ok = True
    for c, f in crit.items():
        if c == "kev_first" and f is None:
            print("kev_first: not exercised" + (" (lookup failed)" if exp is None else " (no truth row KEV-listed)"))
            continue
        ok &= not f
        print("%s: %s%s" % (c, "PASS" if not f else "FAIL", "" if not f else "  " + "; ".join(f)))
    so = {c: sum(len(d[c]) for d in res["script-only"].values()) for c in next(iter(res["script-only"].values()), {})}
    print("script-only (informational, not gating) failures per criterion:", so)
    print("OVERALL:", "PASS" if ok else "FAIL")
    if out:
        json.dump({"criteria": crit, "overall": ok, "default": res["default"], "script_only": res["script-only"],
                   "kev_expected": None if exp is None else sorted(map(list, exp))}, open(os.path.join(out, "score.json"), "w"), indent=1)
    return ok


def self_test():
    """Synthetic rows: hit, miss, decoy flag, vulnerable override, alias, eol, vendored, drift, target, kev order."""
    al = {"node": "nodejs", ".nvmrc": "nodejs", "org.x:spring-boot-starter-parent": "spring-boot"}
    snap = {"npm:a": {"latest": "2.0.0"}, "npm:b": {"latest": "1.0.0"}, "npm:c": {"latest": "3.0.0"}, "pip:Foo_Bar": {"latest": "2"},
            "eol:nodejs": {"latest": "26.1.0", "eol": True}, "docker:node": {"latest": "26.1.0", "eol": True},
            "npm:ms": {"latest": "2"}, "maven:org.x:y": {"latest": "5"}}
    T = lambda eco, n, cur, **k: dict({"name": n, "ecosystem": eco, "current": cur, "eol": None, "vendored": False, "file": "f"}, **k)
    truth = [T("npm", "a", "1.0.0"), T("npm", "b", "1.0.0"), T("npm", "c", "2.0.0"), T("pip", "Foo_Bar", "1"),
             T("eol", "nodejs", "20.1.0", eol_product="nodejs", eol=True), T("npm", "ms", "1", vendored=True, file="third_party/ms/package.json")]
    R = lambda rule, kind, name, cur, lat, tgt="", file="f": {"rule": rule, "kind": kind, "name": name, "current": cur, "latest": lat, "target": tgt, "file": file, "message": ""}
    V = lambda k, n: ["1.0.0", "2.0.0"]
    rows = [R("vulnerable", "npm", "a", "1.0.0", "2.0.0", "2.0.0"),          # hit via vulnerable override
            R("vulnerable", "npm", "b", "1.0.0", "1.0.0"),                   # decoy, vulnerable only: not a flag
            R("outdated", "npm", "c", "2.0.0", "3.0.0", "3.0.0"),            # c is outdated row on decoy-less miss? c truth outdated; target 3.0.0 unresolvable
            R("outdated", "pip", "foo-bar", "1", "2", "9"),                   # alias hit, bad target
            R("eol", "runtime", ".nvmrc", "20.1.0", "26.1.0", "26.1.0"),     # eol alias hit
            R("vendored", "vendored", "third_party", "", "", "", "third_party")]
    r = score("x", truth, snap, rows, al, V, ["a"])
    assert r["outdated_hits"] == [] and r["decoys_clean"] == [] and r["eol_rows"] == [] and r["vendored_rows"] == [], r
    assert r["targets_resolve"] == ["c", "Foo_Bar"], r
    assert r["drift_rows"] == ["a"], r
    r = score("x", truth, snap, [R("not-checked", "npm", "a", "1.0.0", ""), R("outdated", "npm", "b", "1.0.0", "1.0.0")], al, V, [])
    assert "a (NOT RUN)" in r["outdated_hits"] and "c (no row)" in r["outdated_hits"] and r["decoys_clean"] == ["b (outdated)"], r
    assert r["vendored_rows"] == ["ms"] and len(r["eol_rows"]) == 0 and "nodejs (no row)" in r["outdated_hits"], r
    p = parse_default({"rule": "outdated", "file": "p", "message": "npm a; current 1.0.0, latest 2.0.0; behind: major; upgrade to 2.0.0"})
    assert (p["kind"], p["name"], p["latest"], p["target"]) == ("npm", "a", "2.0.0", "2.0.0"), p
    assert parse_default({"rule": "r", "file": "p", "message": "runtime go directive; current 1.2, latest -; x"})["name"] == "go directive"
    assert kev_first(["a"], [R("kev", "npm", "a", "1", "2"), R("outdated", "npm", "b", "1", "2")], al) == []
    assert kev_first(["a"], [R("outdated", "npm", "b", "1", "2"), R("kev", "npm", "a", "1", "2")], al) == ["order: a"]
    assert target_ok("node:26.1.0-alpine", "runtime", "node", "26.1.0", None) and not target_ok("x (unverified)", "runtime", "n", "1", None)
    print("self-test OK")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--set" in a:
        i = a.index("--set")
        SET = os.path.abspath(a[i + 1])
        del a[i:i + 2]
    if a == ["--self-test"]:
        self_test()
    elif len(a) in (2, 4) and (len(a) == 2 or a[2] == "--out"):
        o = a[3] if len(a) == 4 else os.path.join(HERE, "results-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        sys.exit(0 if run(a[0], a[1], o) else 1)
    else:
        sys.exit(__doc__)
