#!/usr/bin/env python3
"""Registry snapshot for G5 ground truth. Independent of any detector code.

Usage:
  snapshot.py [--set DIR]     re-fetch latest for every row in truth/*.json -> snapshot-<UTC date>.json
  snapshot.py versions ECO NAME   print stable non-yanked versions (probe helper)

"latest" rule (PREREGISTERED G5): stable only (no pre-release, yanked, deprecated);
runtimes: newest cycle that is LTS (when the product has LTS) and not EOL, else newest cycle;
Go major-version module paths are separate modules (the proxy list is per path).
Pre-release: npm/cargo/composer treat any "-" suffix as pre-release (numeric "5.0.0-2" included).
Ceiling: version ordering is numeric-tuple only (no semver prerelease tie-breaks); retracted Go
versions are not filtered.
"""
import datetime, glob, json, os, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SET = HERE  # --set DIR: read DIR/truth, write DIR/snapshot-<date>.json
PRE = re.compile(r"(?i)(alpha|beta|rc|dev|snapshot|preview|nightly|canary|\bnext\b|[.-]m\d+$|[.-]?(a|b)\d+$|-pre)")

def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": "g5-currency-snapshot/1", "Accept": accept})
    for i in range(3):  # transient truncation seen on crates.io
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode()
        except Exception:
            if i == 2:
                raise

def gj(url):
    return json.loads(get(url))

def key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0].lstrip("vV")))

def stable(vs, eco=None):
    """npm/cargo/composer: any '-' suffix is a pre-release (covers numeric "5.0.0-2"); others use PRE only."""
    dash = eco in ("npm", "cargo", "composer")
    return sorted((v for v in vs if not PRE.search(v) and not (dash and "-" in v)), key=key)

def versions(eco, name):
    """All stable, non-yanked, non-deprecated versions, ascending."""
    if eco == "npm":
        d = json.loads(get("https://registry.npmjs.org/" + name, "application/vnd.npm.install-v1+json"))
        return stable((v for v, m in d["versions"].items() if not m.get("deprecated")), eco)
    if eco == "pip":
        d = gj("https://pypi.org/pypi/%s/json" % name)
        return stable(v for v, fs in d["releases"].items() if fs and not all(f.get("yanked") for f in fs))
    if eco == "go":
        esc = re.sub(r"[A-Z]", lambda m: "!" + m.group().lower(), name)
        return stable(get("https://proxy.golang.org/%s/@v/list" % esc).split())
    if eco in ("maven", "gradle"):
        g, a = name.split(":")
        x = ET.fromstring(get("https://repo1.maven.org/maven2/%s/%s/maven-metadata.xml" % (g.replace(".", "/"), a)))
        return stable(v.text for v in x.iter("version"))
    if eco == "cargo":
        d = gj("https://crates.io/api/v1/crates/%s/versions" % name)
        return stable((v["num"] for v in d["versions"] if not v["yanked"]), eco)
    if eco == "composer":
        d = gj("https://repo.packagist.org/p2/%s.json" % name)["packages"][name]
        return stable((v["version"] for v in d if not v.get("abandoned") and "dev" not in v["version"]), eco)
    raise ValueError(eco)

def eol_cycles(product):
    return gj("https://endoflife.date/api/%s.json" % product)

def eol_latest(product):
    """Newest non-EOL LTS cycle if the product has LTS, else newest cycle (rows are newest-first)."""
    cs = eol_cycles(product)
    live = [c for c in cs if c["eol"] is False or str(c["eol"]) > datetime.date.today().isoformat()]
    today = datetime.date.today().isoformat()
    lts = [c for c in live if c.get("lts") is True or (c.get("lts") and str(c["lts"]) <= today)]
    return (lts or live or cs)[0]

def eol_of(product, current):
    """True if the cycle containing `current` (longest cycle-prefix match) is past its EOL date."""
    best = None
    for c in eol_cycles(product):
        cy = str(c["cycle"])
        if (current == cy or current.startswith(cy + ".")) and (best is None or len(cy) > len(str(best["cycle"]))):
            best = c
    e = best["eol"]
    return e is True or (isinstance(e, str) and e <= datetime.date.today().isoformat())

def latest(row):
    eco, name = row["ecosystem"], row["name"]
    if eco == "eol":
        c = eol_latest(name)
        return c["latest"]
    if eco == "docker":  # base image tag; latest from endoflife.date, tag existence checked on Docker Hub
        v = eol_latest(row["eol_product"])["latest"]
        t = gj("https://hub.docker.com/v2/repositories/library/%s/tags/%s" % (name, v))
        assert t.get("name") == v, "hub tag missing"
        return v
    if eco == "actions":
        return gj("https://api.github.com/repos/%s/releases/latest" % name)["tag_name"].lstrip("v")
    return versions(eco, name)[-1]

def behind(cur, lat):
    a, b = key(cur), key(lat)
    n = max(len(a), len(b), 3)
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    for i, k in enumerate(("major", "minor", "patch")):
        if a[i] != b[i]:
            return k
    return "none"

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    out = {"fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "fixtures": {}, "changed_vs_truth": []}
    for f in sorted(glob.glob(os.path.join(SET, "truth", "*.json"))):
        fx = os.path.basename(f)[:-5]
        rows = json.load(open(f))
        out["fixtures"][fx] = {}
        for r in rows:
            l = latest(r)
            e = {"latest": l, "behind": behind(r["current"], l)}
            if r.get("eol_product"):
                e["eol"] = eol_of(r["eol_product"], r["current"])
            out["fixtures"][fx]["%s:%s" % (r["ecosystem"], r["name"])] = e
            if l != r["latest"]:
                out["changed_vs_truth"].append([fx, r["name"], r["latest"], l])
    p = os.path.join(SET, "snapshot-%s.json" % now.strftime("%Y-%m-%d"))
    json.dump(out, open(p, "w"), indent=1)
    print(p, len(out["changed_vs_truth"]), "changed")

if __name__ == "__main__":
    if sys.argv[1:2] == ["--set"]:
        SET = os.path.abspath(sys.argv[2])
        del sys.argv[1:3]
    if len(sys.argv) == 4 and sys.argv[1] == "versions":
        print(versions(sys.argv[2], sys.argv[3]))
    else:
        main()
