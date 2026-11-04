#!/usr/bin/env python3
"""dependency_currency.py [--root DIR] [--stdin] [--json] [--budget SECS] [--today YYYY-MM-DD] — how far behind is every dependency, and is it vulnerable.

WHY THIS EXISTS
---------------
A vulnerability scanner answers "is this version known-bad"; it does not answer "how stale is the tree" or "what should I move to". This
check reads every manifest and lockfile it is given (direct and transitive), looks up the newest stable release in the ecosystem's own
registry, asks OSV whether the locked version is vulnerable, and marks CISA KEV-listed CVEs. One row per finding, KEV first.

SCOPE (stdlib only; network through urllib)
-------------------------------------------
npm   package-lock.json (v1-v3), yarn.lock (v1, berry), pnpm-lock.yaml; drift for package.json -> registry.npmjs.org
pip   requirements*/constraints*.txt and requirements/ dirs (== pins; -r/-c includes followed), poetry.lock, Pipfile.lock; drift for *.in, pyproject.toml (incl. extras), setup.cfg, Pipfile -> pypi.org
go    go.mod (require, incl. // indirect; replace honoured)                                    -> proxy.golang.org
maven pom.xml (literal or <properties> versions, parent)                                       -> repo1.maven.org
gradle build.gradle[.kts] string notation, gradle.lockfile, libs.versions.toml                 -> repo1.maven.org
cargo Cargo.lock (registry crates), drift for Cargo.toml                                       -> crates.io
composer composer.lock, drift for composer.json                                                -> repo.packagist.org
Dockerfile, docker-compose and Kubernetes manifest images (any official image with an endoflife.date product of its name), rust-toolchain and .nvmrc/.node-version/.python-version/.ruby-version/go.mod `go` runtimes, plus framework EOL for locked
django, react, next, vue, @angular/core, laravel/framework, symfony and spring-boot (starter-parent)             -> endoflife.date
GitHub Actions `uses:` pins                                                                    -> api.github.com
Vendored directories (vendor, third_party, node_modules, bower_components, Pods) are flagged, not parsed.
Vulnerabilities: api.osv.dev (querybatch + vuln aliases); KEV: cisa.gov known_exploited_vulnerabilities.json.

"LATEST" RULE (fixed per ecosystem)
-----------------------------------
Stable releases only: no pre-release, yanked (PyPI, crates.io) or deprecated (npm) version. npm latest is dist-tags.latest; a Maven
version keeps its -jre/-android flavor; a pre-release below its own stable release counts as behind. Go major-version module paths (`.../v2`)
are separate modules: latest is looked up under the module's own path, never across majors. Runtimes follow the LTS channel for Node and
Java (the newest cycle whose LTS date has passed); other products use their newest cycle. The upgrade target is always a version read
from the registry listing, so it resolves; image targets are checked against Docker Hub.

NEVER "UP TO DATE" BY DEFAULT
-----------------------------
A registry, OSV or KEV lookup that fails (network, 5xx, bad JSON) yields a `not-checked` row (NOT RUN), never a clean row. A host that
fails three connections in a row is skipped for the rest of the run (its rows say so). Work past --budget seconds is not-checked too.

OUTPUT
------
Default: TSV `file<TAB>line<TAB>rule<TAB>message`, only non-current rows, KEV first. Rule: kev, vulnerable, eol, outdated, drift,
unpinned, vendored or not-checked. The message carries name, current, latest, behind, vulnerable ids and the upgrade target.
`--json` prints every row (also current ones) with those fields. Exit 0 always; the caller reads the rows.

KNOWN CEILINGS
--------------
Requirements with ranges are not locked pins and are only checked as drift against a lock in the same directory. Maven versions managed by a parent or BOM that
the pom does not spell out, and floating Gradle versions, give a not-checked or unpinned row. Calls past --budget, response bodies and repo files over 5 MB
and names with `..` or control characters fail closed as not-checked rows. crates.io is called at most once per second.
"""
import argparse, concurrent.futures as cf, configparser, datetime, http.client, json, os, re, socket, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024  # response and file read cap; over it fails closed
HOST_CAP = {"pypi.org": 32 * 1024 * 1024}  # PyPI JSON for big projects (sqlalchemy) passes 5 MB; still capped
DEADLINE = None  # epoch seconds past which Net.get refuses (set by run from --budget)
STUCK = False  # set by run() when lookups were still in flight at the budget; main() then exits with os._exit after flushing
TRIES, BACKOFF = 3, 1.0  # attempts per request and the first backoff in seconds (doubles)
RATE = {"crates.io": 1.0}  # minimum seconds between requests per host
UA = {"User-Agent": "dependency-currency/1 (deep-code-review)"}
OSV_ECO = {"npm": "npm", "pip": "PyPI", "go": "Go", "maven": "Maven", "gradle": "Maven", "cargo": "crates.io", "composer": "Packagist"}
VENDORED = re.compile(r"(^|/)(vendor|third_party|node_modules|bower_components|Pods)/")
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# Docker image / framework package -> endoflife.date product.
IMAGES = {"node": "nodejs", "python": "python", "golang": "go", "ruby": "ruby", "php": "php", "nginx": "nginx", "postgres": "postgresql",
          "redis": "redis", "mysql": "mysql", "alpine": "alpine", "ubuntu": "ubuntu", "debian": "debian", "eclipse-temurin": "eclipse-temurin",
          "openjdk": "eclipse-temurin", "amazoncorretto": "eclipse-temurin", "mongo": "mongodb", "mariadb": "mariadb", "rabbitmq": "rabbitmq",
          "elasticsearch": "elasticsearch", "httpd": "apache-http-server", "tomcat": "tomcat", "traefik": "traefik", "wordpress": "wordpress",
          "rust": "rust", "haproxy": "haproxy", "influxdb": "influxdb", "memcached": "memcached"}
# Symfony components below are released in lockstep with the framework (same version cycle); polyfills, contracts, flex and bundles with their own numbering are left out.
FRAMEWORKS = {("pip", "django"): "django", ("npm", "react"): "react", ("npm", "next"): "nextjs", ("npm", "vue"): "vue",
              ("npm", "@angular/core"): "angular", ("composer", "laravel/framework"): "laravel", ("composer", "symfony/symfony"): "symfony",
              ("composer", "symfony/framework-bundle"): "symfony", ("composer", "symfony/http-kernel"): "symfony",
              ("composer", "symfony/http-foundation"): "symfony", ("composer", "symfony/console"): "symfony", ("composer", "symfony/routing"): "symfony",
              ("composer", "symfony/dependency-injection"): "symfony", ("composer", "symfony/event-dispatcher"): "symfony",
              ("composer", "symfony/config"): "symfony", ("composer", "symfony/security-core"): "symfony", ("composer", "symfony/security-http"): "symfony",
              ("composer", "symfony/security-bundle"): "symfony", ("composer", "symfony/validator"): "symfony", ("composer", "symfony/form"): "symfony",
              ("composer", "symfony/twig-bundle"): "symfony", ("composer", "symfony/string"): "symfony", ("composer", "symfony/yaml"): "symfony",
              ("composer", "symfony/finder"): "symfony", ("composer", "symfony/process"): "symfony", ("composer", "symfony/messenger"): "symfony",
              ("composer", "symfony/mailer"): "symfony", ("composer", "symfony/serializer"): "symfony", ("composer", "symfony/cache"): "symfony",
              # Spring Boot arrives as a parent, BOM import, starter jar, Gradle plugin jar or Gradle plugin marker artifact
              ("maven", "org.springframework.boot:spring-boot"): "spring-boot",
              ("gradle", "org.springframework.boot:spring-boot"): "spring-boot",
              ("maven", "org.springframework.boot:spring-boot-starter-parent"): "spring-boot",
              ("gradle", "org.springframework.boot:spring-boot-starter-parent"): "spring-boot",
              ("maven", "org.springframework.boot:spring-boot-dependencies"): "spring-boot",
              ("gradle", "org.springframework.boot:spring-boot-dependencies"): "spring-boot",
              ("maven", "org.springframework.boot:spring-boot-gradle-plugin"): "spring-boot",
              ("gradle", "org.springframework.boot:spring-boot-gradle-plugin"): "spring-boot",
              ("maven", "org.springframework.boot:org.springframework.boot.gradle.plugin"): "spring-boot",
              ("gradle", "org.springframework.boot:org.springframework.boot.gradle.plugin"): "spring-boot",
              # Spring Framework modules share one version cycle; Data, Security and Cloud have their own numbering and are not listed
              ("maven", "org.springframework:spring-core"): "spring-framework", ("maven", "org.springframework:spring-context"): "spring-framework",
              ("maven", "org.springframework:spring-beans"): "spring-framework", ("maven", "org.springframework:spring-web"): "spring-framework",
              ("maven", "org.springframework:spring-webmvc"): "spring-framework", ("maven", "org.springframework:spring-webflux"): "spring-framework",
              ("maven", "org.springframework:spring-aop"): "spring-framework", ("maven", "org.springframework:spring-jdbc"): "spring-framework",
              ("maven", "org.springframework:spring-tx"): "spring-framework", ("maven", "org.springframework:spring-orm"): "spring-framework",
              ("maven", "org.springframework:spring-expression"): "spring-framework", ("maven", "org.springframework:spring-test"): "spring-framework",
              ("gradle", "org.springframework:spring-core"): "spring-framework", ("gradle", "org.springframework:spring-context"): "spring-framework",
              ("gradle", "org.springframework:spring-beans"): "spring-framework", ("gradle", "org.springframework:spring-web"): "spring-framework",
              ("gradle", "org.springframework:spring-webmvc"): "spring-framework", ("gradle", "org.springframework:spring-webflux"): "spring-framework",
              ("gradle", "org.springframework:spring-aop"): "spring-framework", ("gradle", "org.springframework:spring-jdbc"): "spring-framework",
              ("gradle", "org.springframework:spring-tx"): "spring-framework", ("gradle", "org.springframework:spring-orm"): "spring-framework",
              ("gradle", "org.springframework:spring-expression"): "spring-framework", ("gradle", "org.springframework:spring-test"): "spring-framework",
              ("maven", "io.dropwizard:dropwizard-core"): "dropwizard", ("gradle", "io.dropwizard:dropwizard-core"): "dropwizard",
              ("maven", "io.dropwizard:dropwizard-bom"): "dropwizard", ("gradle", "io.dropwizard:dropwizard-bom"): "dropwizard"}
RT_TOOLS = {"nodejs": "nodejs", "node": "nodejs", "python": "python", "ruby": "ruby", "golang": "go", "go": "go", "rust": "rust", "php": "php", "elixir": "elixir", "erlang": "erlang"}


class NotFound(Exception):
    """A registry answered 404: the thing does not exist (distinct from unreachable)."""


class Net:
    """Cached, thread-safe HTTP with a per-host circuit breaker; replaceable in tests via `fetch`."""

    def __init__(self):
        """Create empty cache, failure counters and lock."""
        self.cache, self.fails, self.nxt, self.lock = {}, {}, {}, threading.Lock()

    def get(self, url, data=None, headers=None):
        """Return response text for url (POST when data is bytes); raise NotFound on 404, OSError/ValueError otherwise."""
        key = (url, data)
        with self.lock:
            if key in self.cache:
                hit = self.cache[key]
                if isinstance(hit, Exception):
                    raise hit
                return hit
        host = urllib.parse.urlsplit(url).netloc
        if self.fails.get(host, 0) >= 3:
            raise OSError(f"{host} unreachable (circuit open after 3 failed connections)")
        h = dict(UA, **(headers or {}))
        if data is not None:
            h["Content-Type"] = "application/json"
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") if host == "api.github.com" else None
        for attempt in range(TRIES):  # transient failures (truncated body, reset, 429, 5xx) are retried with backoff, honouring RATE and the deadline
            wait = BACKOFF * 2 ** (attempt - 1) if attempt else 0
            with self.lock:
                now = time.time()
                if host in RATE:
                    start = max(now + wait, self.nxt.get(host, 0))
                    self.nxt[host], wait = start + RATE[host], start - now
            if DEADLINE is not None and time.time() + wait > DEADLINE:
                raise OSError("time budget exhausted before this lookup")
            if wait > 0:
                time.sleep(wait)
            transient = conn = False
            try:
                req = urllib.request.Request(url, data=data, headers=h)
                if tok:
                    req.add_unredirected_header("Authorization", "Bearer " + tok)  # never copied to a redirect target, never logged
                with urllib.request.urlopen(req, timeout=15) as r:
                    cap = HOST_CAP.get(host, MAX_BYTES)
                    raw = r.read(cap + 1)
                if len(raw) > cap:
                    raise ValueError(f"{url}: response over {cap >> 20} MB")
                res = raw.decode("utf-8", "replace")
                if url.endswith("maven-metadata.xml") and "</metadata>" not in res:  # silently truncated body would yield a partial version list
                    raise http.client.IncompleteRead(raw)
                self.fails[host] = 0
            except ValueError as e:
                res = OSError(str(e))
            except urllib.error.HTTPError as e:
                self.fails[host] = 0
                res = NotFound(url) if e.code == 404 else OSError(f"{url}: HTTP {e.code}")
                transient = e.code == 429 or e.code >= 500
            except http.client.HTTPException as e:  # not an OSError: IncompleteRead, BadStatusLine, ...
                res, transient, conn = OSError(f"{host}: {type(e).__name__}: {e}"), True, True
            except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
                res, transient, conn = OSError(f"{host}: {getattr(e, 'reason', e)}"), True, True
            if transient and attempt < TRIES - 1:
                continue
            if conn:
                self.fails[host] = self.fails.get(host, 0) + 1  # one strike per lookup, not per attempt
            break
        with self.lock:
            self.cache[key] = res
        if isinstance(res, Exception):
            raise res
        return res

    def json(self, url, data=None, headers=None):
        """Return the parsed JSON body of url; a body that does not decode is refetched up to TRIES times, then ValueError."""
        for i in range(TRIES):  # a body cut short without a transport error fails to decode: transient, refetch
            try:
                return json.loads(self.get(url, data, headers))
            except ValueError:
                delay = BACKOFF * 2 ** i
                if i == TRIES - 1 or (DEADLINE is not None and time.time() + delay > DEADLINE):
                    raise
                with self.lock:
                    self.cache.pop((url, data), None)
                time.sleep(delay)


net = Net()


def vkey(v):
    """Numeric components of a version string, build metadata and a leading v dropped: '1.2.3-rc1' -> (1, 2, 3, 1)."""
    return tuple(int(x) for x in re.findall(r"\d+", v.lstrip("v").split("+")[0]))


def is_pre(eco, v):
    """True when v is a pre-release: any '-suffix' for semver registries, qualifier words for PyPI and Maven."""
    v = v.lstrip("v")
    if eco in ("pip", "maven", "gradle"):
        return bool(re.search(r"(?i)(alpha|beta|snapshot|preview|nightly|canary|milestone|dev|[.\-_]?rc\d|[.\-_]cr\d|[.\-_]m\d+$|\d(a|b)\d+$|[.\-_](a|b)\d)", v))
    return "-" in v.split("+")[0] or v.startswith("dev-")


def pk(eco, v):
    """Total-order key: (release numbers without trailing zeros, 1 when final else 0, pre-release numbers); a pre-release sorts below its stable."""
    m = re.match(r"v?(\d+(?:\.\d+)*)(.*)", v.split("+")[0])
    rel = [int(x) for x in m[1].split(".")] if m else []
    while rel and rel[-1] == 0:
        rel.pop()
    return tuple(rel), 0 if is_pre(eco, v) else 1, tuple(int(x) for x in re.findall(r"\d+", m[2] if m else ""))


def qp(name):
    """Return name as a URL path with each `/` segment quoted (safe=''); ValueError on empty, `.`/`..` segments or control characters."""
    if re.search(r"[\x00-\x1f\x7f]", name) or any(x in ("", ".", "..") for x in name.split("/")):
        raise ValueError(f"unsafe name {name!r}")
    return "/".join(urllib.parse.quote(x, safe="") for x in name.split("/"))


def behind(cur, latest):
    """Describe the gap: 'major', 'minor' or 'patch' by the first differing component, or '' when not behind."""
    a, b = vkey(cur), vkey(latest)
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return ("major", "minor", "patch")[min(i, 2)] if y > x else ""
    return "patch" if len(b) > len(a) and any(b[len(a):]) else ""


def sat(spec, ver, cargo=False, composer=False):
    """True when ver satisfies the npm/cargo/composer range spec; a spec it cannot read (git, tag, workspace) counts as satisfied."""
    v = (vkey(ver) + (0, 0, 0))[:3]
    for alt in re.split(r"\s*\|\|?\s*", spec.strip()):
        toks = re.findall(r"(\^|~>?|>=|<=|>|<|=)?\s*v?(\d[\w.*]*|[*xX])", alt.replace(",", " "))
        if not toks or re.search(r"\s-\s|://|^\w+:|^[a-zA-Z]", alt.strip()):
            return True
        ok = True
        for op, t in toks:
            n = [int(p) for p in re.findall(r"\d+", t.split("*")[0].split("x")[0].split(".*")[0])] if t not in "*xX" else []
            wild = "*" in t or "x" in t.lower() or len(n) < 3
            lo = tuple(n + [0, 0, 0])[:3]
            hi = None
            if not n:
                continue
            if op == "^" or (op == "" and cargo and not any(c in t for c in "*x")):
                i = next((k for k, x in enumerate(n) if x), len(n) - 1)
                hi = n[:i] + [n[i] + 1]
            elif op in ("~", "~>"):
                hi = [n[0] + 1] if len(n) < 3 and (composer or len(n) < 2) else [n[0], n[1] + 1]
            elif op in ("", "="):
                if wild:
                    k = len(n) or 1
                    hi = n[:k - 1] + [n[k - 1] + 1]
                else:
                    ok &= v == lo
                    continue
            if hi is not None:
                ok &= lo <= v < tuple(hi + [0, 0, 0])[:3]
            elif op == ">=":
                ok &= v >= lo
            elif op == ">":
                ok &= v > lo
            elif op == "<=":
                ok &= v <= lo
            elif op == "<":
                ok &= v < lo
        if ok:
            return True
    return False


# --- parsers: each returns [(name, version, direct_flag)]; drift parsers return [(name, spec)] -----------------------------------------

def p_npm_lock(txt):
    """Parse package-lock.json (v1 'dependencies' tree or v2/v3 'packages' map) into (name, version) pairs."""
    d, out = json.loads(txt), set()
    for k, e in (d.get("packages") or {}).items():
        if "node_modules/" in k and not e.get("link") and re.match(r"https?://", e.get("resolved", "http://")) and re.match(r"\d", e.get("version", "")):
            out.add((e.get("name") or k.rsplit("node_modules/", 1)[-1], e["version"]))

    def walk(deps):
        """Collect v1 nested dependency entries."""
        for n, e in (deps or {}).items():
            if re.match(r"\d", str(e.get("version", ""))):
                out.add((n, e["version"]))
            walk(e.get("dependencies"))
    walk(d.get("dependencies"))
    return sorted(out)


def p_npm_root(txt):
    """Return {name: version} of the top-level installs of a package-lock.json (v2/v3 `node_modules/<name>`, v1 top `dependencies`)."""
    d = json.loads(txt)
    out = {k[13:]: e["version"] for k, e in (d.get("packages") or {}).items() if k.startswith("node_modules/") and "node_modules/" not in k[13:] and re.match(r"\d", e.get("version", ""))}
    out.update({n: e["version"] for n, e in (d.get("dependencies") or {}).items() if re.match(r"\d", str(e.get("version", "")))})
    return out


def p_yarn_lock(txt):
    """Parse yarn.lock blocks (v1 `version "x"`, berry `version: x`); berry workspace/patch/link entries and __metadata are skipped."""
    out, name = set(), None
    for ln in txt.splitlines():
        if ln and not ln[0].isspace() and ln.endswith(":") and not ln.startswith("#"):
            name = None if ln.startswith("__metadata") or re.search(r"@(?!npm:)[a-z]+:", ln.split(",")[0]) else ln.split(",")[0].strip('":').rsplit("@", 1)[0].strip('"')
        elif name and (m := re.match(r'\s+version:?\s+"?([^"\s]+)"?', ln)):
            out.add((name, m[1]))
            name = None
    return sorted(out)


def p_pnpm_lock(txt):
    """Parse the `packages:` section of pnpm-lock.yaml (v5 `/n/1.0.0`, v6 `/n@1.0.0`, v9 `n@1.0.0`); `snapshots:` repeats it and is ignored."""
    out, on = set(), False
    for ln in txt.splitlines():
        if ln and not ln[0].isspace():
            on = ln.startswith("packages:")
        elif on and (m := re.match(r"  ['\"]?/?((?:@[^/@\s'\"]+/)?[^/@\s'\"]+)[@/](\d+(?:\.\d+)*(?:-[\w.]+)?)", ln)):
            out.add((m[1], m[2]))
    return sorted(out)


def p_pnpm_root(txt):
    """Return {importer dir: {name: version}} of the direct installs in pnpm-lock.yaml: `importers:` entries (v9, workspaces; root is ".") or the top-level
    dependency blocks (v5/v6, root "."). Drift must compare against these: the `packages:` section also lists transitive copies, one of which could
    satisfy a range the direct install does not."""
    out, imp, key, blk, cur = {}, False, ".", False, None
    kinds = ("dependencies", "devDependencies", "optionalDependencies")
    for ln in txt.splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        ind, body = len(ln) - len(ln.lstrip()), ln.strip()
        if ind == 0:
            imp, key, cur = body.startswith("importers:"), ".", None
            blk = not imp and body.rstrip(":") in kinds
            if blk:
                out.setdefault(".", {})
            continue
        if imp and ind == 2:
            key, blk, cur = re.match(r"['\"]?([^'\":]+)", body)[1], False, None  # `.: {}` and quoted keys too
            out.setdefault(key, {})
            continue
        base = 4 if imp else 0
        if imp and ind == 4:
            blk, cur = body.rstrip(":") in kinds, None
            continue
        if not blk:
            continue
        d = out.setdefault(key, {})
        if ind == base + 2 and (m := re.match(r"['\"]?((?:@[^/@\s'\"]+/)?[^@\s'\"]+)['\"]?:\s*(.*)$", body)):
            cur = m[1]
            if (v := re.match(r"\d[\w.\-]*", m[2].strip("'\""))):  # v5 inline `name: 1.2.3`
                d[cur] = v[0].split("_")[0]  # v5 peer suffix `1.2.3_react@18`
        elif ind == base + 4 and cur and (m := re.match(r"version:\s*['\"]?(\d[\w.\-]*)", body)):
            d[cur] = m[1].split("_")[0]
    return out


def p_requirements(txt):
    """Parse `name==version` pins from a requirements file (extras and markers dropped)."""
    return sorted({(m[1].lower().replace("_", "-"), m[2]) for ln in txt.splitlines() if (m := re.match(r"\s*([A-Za-z0-9][\w.\-]*)(?:\[[^\]]*\])?\s*===?\s*([\w.!+\-]+)", ln))})


def p_toml_packages(txt, registry_only=False):
    """Parse `[[package]]` blocks of poetry.lock / Cargo.lock; Cargo keeps only crates.io crates, poetry drops git/path/url/private-index sources."""
    out = set()
    for blk in re.split(r"(?m)^\[\[package\]\]\s*$", txt)[1:]:
        n, v, s = (re.search(rf'(?m)^{k}\s*=\s*"([^"]*)"', blk) for k in ("name", "version", "source"))
        crates = s and re.fullmatch(r"registry\+https://github\.com/rust-lang/crates\.io-index|sparse\+https://index\.crates\.io/?", s[1])
        if n and v and (crates if registry_only else "[package.source]" not in blk):
            out.add((n[1], v[1]))
    return sorted(out)


def p_pipfile_lock(txt):
    """Parse Pipfile.lock 'default' and 'develop' pins."""
    d = json.loads(txt)
    return sorted({(n, e["version"].lstrip("=")) for s in ("default", "develop") for n, e in d.get(s, {}).items() if str(e.get("version", "")).startswith("==")})


def p_go_mod(txt):
    """Parse go.mod: ([(module, version)], [replaced-to-local-path modules]); a module replace swaps in the replacement; `go` is read separately."""
    out, rep, inreq, inrep = set(), [], False, False
    for ln in txt.splitlines():
        s = ln.split("//")[0].strip()
        if re.match(r"(require|replace)\s*\($", s):
            inreq, inrep = s.startswith("require"), s.startswith("replace")
        elif s == ")":
            inreq = inrep = False
        elif (m := re.match(r"(?:replace\s+)?(\S+)(?:\s+(v\d\S*))?\s*=>\s*(\S+)(?:\s+(v\d\S*))?$", s)) and (inrep or s.startswith("replace")):
            rep.append(m.groups())
        elif (m := re.match(r"(?:require\s+)?(\S+)\s+(v\d\S*)$", s)) and (inreq or s.startswith("require")):
            out.add((m[1], m[2]))
    bad = []
    for old, ov, new, nv in rep:
        hit = {x for x in out if x[0] == old and ov in (None, x[1])}
        out -= hit
        if nv and not new.startswith((".", "/")):
            out.add((new, nv))
        elif hit:
            bad.append(old)
    return sorted(out), sorted(bad)


def p_composer_lock(txt):
    """Parse composer.lock packages and packages-dev; dev-branch versions are skipped."""
    d = json.loads(txt)
    return sorted({(p["name"], p["version"].lstrip("v")) for s in ("packages", "packages-dev") for p in d.get(s, []) if re.match(r"v?\d", p.get("version", ""))})


def p_maven_lock(txt):
    """Parse maven-lockfile lockfile.json: every nested dependency (children, recursively) and plugin as (g:a, selected version); excluded entries are skipped; None when the file is not a maven-lockfile."""
    out = set()

    def walk(items):
        """Collect (name, version) from a list of lock entries and their children."""
        for e in items or []:
            v = e.get("selectedVersion") or e.get("version") or ""
            if e.get("groupId") and e.get("artifactId") and re.match(r"\d", v) and e.get("included", True):
                out.add((f"{e['groupId']}:{e['artifactId']}", v))
            walk(e.get("children"))
    try:
        d = json.loads(txt)
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("dependencies"), list):
        return None
    walk(d.get("dependencies"))
    walk(d.get("mavenPlugins"))
    return sorted(out)


def p_pom(txt):
    """Parse pom.xml dependencies and parent; ${property} versions resolve from <properties>; a versionless dependency resolves to this pom's own
    dependencyManagement entry, else is returned in the unresolved names with unresolvable ${property} versions: (pairs, unresolved names)."""
    root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", txt, count=1))
    props = {c.tag: (c.text or "").strip() for c in (root.find("properties") if root.find("properties") is not None else [])}
    pv = (root.findtext("parent/version") or "").strip()
    props.update({"project.version": (root.findtext("version") or pv).strip(), "project.parent.version": pv, "parent.version": pv})
    out, bad, bare = set(), [], []
    for el in list(root.iter("dependency")) + list(root.iter("parent")):
        g, a, v = (el.findtext(k, "").strip() for k in ("groupId", "artifactId", "version"))
        v = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m[1], m[0]), v)
        if g and a and re.match(r"\d", v):
            out.add((f"{g}:{a}", v))
        elif g and a and v:
            bad.append(f"{g}:{a}")
        elif g and a:
            bare.append(f"{g}:{a}")
    bad += [x for x in bare if x not in {n for n, _ in out}]  # versionless and not managed by this pom: parent/BOM unresolved
    return sorted(out), sorted(set(bad))


def p_gradle(txt, name):
    """Parse Gradle files: `g:a:v` strings (build files, lockfile lines `g:a:v=conf`) and version-catalog module/version pairs.
    Returns (pairs, floating names) where floating are dynamic versions such as `1.+`, `+` and `latest.release`."""
    out, dyn = set(), set()
    for m in re.finditer(r"""["']?([\w.\-]+):([\w.\-]+):(\d[\w.\-]*\+?|\+|latest\.\w+)["']?""", txt):
        if m[3].endswith("+") or m[3].startswith("latest."):
            dyn.add(f"{m[1]}:{m[2]}")
        else:
            out.add((f"{m[1]}:{m[2]}", m[3]))
    mk = lambda i: f"{i}:{i}.gradle.plugin"  # plugin marker artifact
    for m in re.finditer(r"""\bid\s*\(?\s*["']([\w.\-]+)["']\s*\)?\s*version\s*\(?\s*["'](\d[^"']*)["']""", txt):
        out.add((mk(m[1]), m[2]))
    if name.endswith(".toml"):
        sec = re.search(r"(?ms)^\[versions\]\s*$(.*?)(?=^\[|\Z)", txt)  # by section, any order
        refs = dict(re.findall(r'(?m)^([\w\-]+)\s*=\s*"([^"]+)"', sec[1])) if sec else {}
        for m in re.finditer(r'\bid\s*=\s*"([\w.\-]+)"\s*,\s*version(?:\.ref)?\s*=\s*"([^"]+)"', txt):
            out.add((mk(m[1]), refs.get(m[2], m[2])))
        for m in re.finditer(r'module\s*=\s*"([^":]+:[^":]+)"\s*,\s*version(?:\.ref)?\s*=\s*"([^"]+)"', txt):
            out.add((m[1], refs.get(m[2], m[2])))
        for m in re.finditer(r'(?:group\s*=\s*"([^"]+)"\s*,\s*name\s*=\s*"([^"]+)"|name\s*=\s*"([^"]+)"\s*,\s*group\s*=\s*"([^"]+)")\s*,\s*version(?:\.ref)?\s*=\s*"([^"]+)"', txt):
            out.add((f"{m[1] or m[4]}:{m[2] or m[3]}", refs.get(m[5], m[5])))  # group/name form
    return sorted(x for x in out if re.match(r"\d", x[1])), sorted(dyn)


def p_json_manifest(txt, keys):
    """Return [(name, spec)] from the named dependency objects of package.json / composer.json."""
    d = json.loads(txt)
    return [(n, s) for k in keys for n, s in (d.get(k) or {}).items() if isinstance(s, str) and not re.match(r"(php|hhvm)$|ext-|lib-", n)]


def p_pip_specs(lines):
    """Return [(name, spec)] from requirements.in-style lines / PEP 508 strings (extras, markers, comments and option lines dropped); unversioned names are skipped."""
    out = []
    for ln in lines:
        if (m := re.match(r"\s*([A-Za-z0-9][\w.\-]*)\s*(?:\[[^\]]*\])?\s*([<>=!~][^;#]*)", ln)):
            out.append((m[1], m[2].strip()))
    return out


def p_pipfile(txt):
    """Return [(name, spec)] from the [packages] and [dev-packages] tables of a Pipfile (`*` means any version and is skipped)."""
    out, sec = [], ""
    for ln in txt.splitlines():
        if (m := re.match(r"\s*\[([^\]]+)\]", ln)):
            sec = m[1]
        elif sec in ("packages", "dev-packages") and (m := re.match(r'\s*([\w.\-]+)\s*=\s*(?:"([^"]+)"|\{[^}]*version\s*=\s*"([^"]+)")', ln)) and (m[2] or m[3]) != "*":
            out.append((m[1], m[2] or m[3]))
    return out


def p_setup_cfg(txt):
    """Return [(name, spec)] from setup.cfg [options] install_requires, setup_requires, tests_require and every [options.extras_require] value."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(txt)
    except configparser.Error:
        return []
    vals = [cp.get("options", k) for k in ("install_requires", "setup_requires", "tests_require") if cp.has_option("options", k)]
    vals += [v for _, v in cp.items("options.extras_require")] if cp.has_section("options.extras_require") else []
    sep = r",\s*(?=[A-Za-z0-9][\w.\-]*\s*(?:\[[^\]]*\])?\s*[<>=!~])"  # `a>=1, b>=2` on one line is two requirements; `>=1,<2` stays one
    return p_pip_specs([x for v in vals for ln in v.splitlines() if not re.match(r"\s*(file|attr)\s*:", ln) for x in re.split(sep, ln)])


def p_pyproject(txt):
    """Return [(name, spec)] from pyproject.toml: [project] dependencies (PEP 621) and [tool.poetry*.dependencies] tables; `python` is skipped."""
    out = []
    if (m := re.search(r"(?ms)^\[project\]\s(?:(?!^\[).)*?^dependencies\s*=\s*\[(.*?)\]", txt)):
        out += p_pip_specs(re.findall(r"[\"']([^\"']+)[\"']", m[1]))
    for sec in (r"project\.optional-dependencies", "dependency-groups"):  # extras and PEP 735 groups: arrays of requirement strings
        if (m := re.search(rf"(?ms)^\[{sec}\]\s*$(.*?)(?=^\[|\Z)", txt)):
            out += p_pip_specs(re.findall(r"[\"']([^\"']+)[\"']", re.sub(r"\{[^}]*\}", "", m[1])))  # {include-group = "x"} pulls in group x, whose own specs are read there
    return out + [x for x in p_cargo_toml(txt, "tool.poetry") if x[0] != "python"]


def p_cargo_toml(txt, only="", ws=None):
    """Return [(crate, spec)] from [dependencies]-style sections (inline or table form) of Cargo.toml; `only` limits to sections containing that text; `ws` ({crate: spec} from the root [workspace.dependencies]) resolves `dep.workspace = true` / `{ workspace = true }`."""
    out, sec = [], ""
    for ln in txt.splitlines():
        if (m := re.match(r"\s*\[([^\]]+)\]", ln)):
            sec = m[1]
            continue
        if only not in sec:
            continue
        if re.search(r"(^|\.)(dev-|build-)?dependencies$", sec):
            if (m := re.match(r"\s*([\w\-]+)(?:\.workspace\s*=\s*true|\s*=\s*\{[^}]*\bworkspace\s*=\s*true)", ln)):
                if ws and m[1] in ws:
                    out.append((m[1], ws[m[1]]))
            elif (m := re.match(r"\s*([\w\-]+)\s*=\s*(?:[\"']([^\"']+)[\"']|\{(?![^}]*\bpackage\s*=)[^}]*version\s*=\s*[\"']([^\"']+)[\"'])", ln)):
                out.append((m[1], m[2] or m[3]))
        elif re.search(r"(^|\.)(dev-|build-)?dependencies\.[\w\-]+$", sec) and (m := re.match(r"\s*version\s*=\s*[\"']([^\"']+)[\"']", ln)):
            out.append((sec.rsplit(".", 1)[1], m[1]))
    return out


def p_uv_lock(txt):
    """Parse uv.lock `[[package]]` blocks: registry packages only (virtual/editable/git/path sources are the project itself or not on the index)."""
    out = set()
    for blk in re.split(r"(?m)^\[\[package\]\]\s*$", txt)[1:]:
        n, v = (re.search(rf'(?m)^{k}\s*=\s*"([^"]*)"', blk) for k in ("name", "version"))
        if n and v and re.search(r"(?m)^source\s*=\s*\{\s*registry\s*=", blk):
            out.add((n[1], v[1]))
    return sorted(out)


def p_composer_installed(txt):
    """Parse vendor/composer/installed.json (v2 {"packages": [...]} or the v1 bare list): the installed (name, version) pairs; dev-branch versions are skipped."""
    d = json.loads(txt)
    return sorted({(p["name"], p["version"].lstrip("v")) for p in (d.get("packages", []) if isinstance(d, dict) else d) if isinstance(p, dict) and p.get("name") and re.match(r"v?\d", str(p.get("version", "")))})


def p_tool_versions(txt, name):
    """Runtime pins from .tool-versions (`tool 1.2.3`) or the [tools] table of mise.toml (`tool = "1.2.3"` / `{ version = "1.2.3" }`): [(endoflife product, version)];
    tools outside RT_TOOLS and non-numeric versions (latest, lts, system, ref:) are skipped."""
    if name == ".tool-versions":
        pairs = [ln.split()[:2] for ln in txt.splitlines() if not ln.lstrip().startswith("#") and len(ln.split()) >= 2]
    else:
        sec = re.search(r"(?ms)^\[tools\]\s*$(.*?)(?=^\[|\Z)", txt)
        pairs = [(m[1], m[2] or m[3]) for m in re.finditer(r'(?m)^\s*"?([\w\-:]+)"?\s*=\s*(?:"([^"]+)"|\{[^}\n]*version\s*=\s*"([^"]+)")', sec[1])] if sec else []
    return [(RT_TOOLS[t.rsplit(":", 1)[-1].lower()], m[1]) for t, v in pairs if t.rsplit(":", 1)[-1].lower() in RT_TOOLS and (m := re.match(r"v?(\d+(?:\.\d+)*)$", v))]


def p_setup_py(txt):
    """Return [(name, spec)] from the string literals of a setup.py install_requires / setup_requires / tests_require list and the lists of an extras_require={...} dict
    (entry_points, package_data, classifiers and every other list are not requirements; a computed list is not read)."""
    blocks = [m[1] for m in re.finditer(r"(?s)(?:install_requires|setup_requires|tests_require)\s*=\s*\[(.*?)\]", txt)] + [m[1] for m in re.finditer(r"(?s)extras_require\s*=\s*\{(.*?)\}", txt)]
    return p_pip_specs([s for b in blocks for s in re.findall(r"[\"']([^\"'\n]+)[\"']", b)])


def p_pom_overrides(txt):
    """Return [(name, literal version, managed version)] for project and profile dependencies that restate a different literal version than this pom's own
    dependencyManagement entry of the same group:artifact:type:classifier (plugin dependencies are not project dependencies)."""
    root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", txt, count=1))
    gav = lambda el: (f"{el.findtext('groupId', '').strip()}:{el.findtext('artifactId', '').strip()}", (el.findtext("type") or "jar").strip(), (el.findtext("classifier") or "").strip(), el.findtext("version", "").strip())
    managed = {x[:3]: x[3] for x in map(gav, root.iterfind("dependencyManagement/dependencies/dependency")) if re.match(r"\d", x[3])}
    return [(x[0], x[3], managed[x[:3]]) for e in list(root.iterfind("dependencies/dependency")) + list(root.iterfind("profiles/profile/dependencies/dependency"))
            for x in [gav(e)] if x[:3] in managed and re.match(r"\d", x[3]) and x[3] != managed[x[:3]]]


def exact(eco, spec):
    """The release a manifest spec pins exactly (npm/composer `1.2.3`, cargo `=1.2.3`, pip `==1.2.3`), else \"\" for any range."""
    m = re.search(r"(?<![=!~<>])==\s*(\d[\w.\-+!]*)(?![\w.*])", spec) if eco == "pip" else re.fullmatch(r"=\s*(\d[\w.+-]*)" if eco == "cargo" else r"=?\s*v?(\d+\.\d+\.\d+(?:[-+][\w.+-]*)?)", spec.strip())
    return m[1] if m else ""


# --- registries: ascending list of STABLE versions (raises on unreachable) --------------------------------------------------------------

def versions(eco, name, cur=""):
    """Return stable versions of name in eco's registry, ascending, honouring yanked/deprecated/pre-release/major-path rules, npm dist-tags.latest
    as the ceiling and, for Maven, cur's -jre/-android flavor. ValueError on an unsafe name."""
    q, path, cap = urllib.parse.quote, qp(name), None
    if eco == "npm":
        d = net.json("https://registry.npmjs.org/" + q(name, safe=""), headers={"Accept": "application/vnd.npm.install-v1+json"})
        vs, cap = [v for v, e in d["versions"].items() if not e.get("deprecated")], (d.get("dist-tags") or {}).get("latest")
    elif eco == "pip":
        d = net.json(f"https://pypi.org/pypi/{path}/json")
        vs = [v for v, fs in d["releases"].items() if fs and not all(f.get("yanked") for f in fs)]
    elif eco == "go":
        esc = "/".join(q(re.sub(r"[A-Z]", lambda m: "!" + m[0].lower(), x), safe="!") for x in name.split("/"))
        vs = [v for v in net.get(f"https://proxy.golang.org/{esc}/@v/list").split() if "+incompatible" not in v]  # the proxy's @latest skips +incompatible tags once a module has a go.mod; ponytail: a pre-modules repo whose only newer major is +incompatible reads as current, query @latest if that matters
    elif eco in ("maven", "gradle"):
        g, a = name.split(":")
        gp = "/".join(qp(x) for x in g.split("."))
        flav = lambda v: (re.search(r"-(?:jre|android)$", v) or [None])[0]
        host = "plugins.gradle.org/m2" if a.endswith(".gradle.plugin") else "repo1.maven.org/maven2"  # Gradle plugin marker artifacts
        vs = [v for v in (e.text or "" for e in ET.fromstring(net.get(f"https://{host}/{gp}/{qp(a)}/maven-metadata.xml")).iter("version")) if flav(v) == flav(cur)]  # <versions> only; never <latest>/<release>
    elif eco == "cargo":
        vs = [e["num"] for e in net.json(f"https://crates.io/api/v1/crates/{path}")["versions"] if not e.get("yanked")]
    elif eco == "composer":
        vs = [e["version"].lstrip("v") for e in net.json(f"https://repo.packagist.org/p2/{path}.json")["packages"][name]]
    else:
        raise ValueError(eco)
    out = {v for v in vs if re.match(r"v?\d", v) and not is_pre(eco, v)}
    if cap:
        out = {v for v in out if pk(eco, v) <= pk(eco, cap)} | {cap}
    return sorted(out, key=lambda v: pk(eco, v))


def ls_remote_latest(repo, err):
    """Highest stable semver tag of github.com/repo via `git ls-remote --tags` (pre-releases and ^{} peels ignored); re-raise err when that fails too."""
    left = None if DEADLINE is None else DEADLINE - time.time()
    if left is not None and left < 2:
        raise err
    try:
        out = subprocess.run(["git", "-c", "credential.helper=", "ls-remote", "--tags", f"https://github.com/{repo}"], capture_output=True, text=True, timeout=min(30, left or 30), cwd=tempfile.gettempdir(),
                             env=dict(os.environ, GIT_TERMINAL_PROMPT="0"), check=False).stdout
    except (OSError, subprocess.SubprocessError):
        raise err from None
    tags = [t for ln in out.splitlines() if (t := ln.partition("refs/tags/")[2]) and re.fullmatch(r"v?\d+(\.\d+)*", t)]
    if not tags:
        raise err
    return max(tags, key=vkey)


FLOAT_TAGS = {}  # repo -> highest tag found behind a floating major release, so many `uses:` lines of one action cost one ls-remote


def gh_latest(repo):
    """Return the latest stable release tag of an owner/repo: releases/latest, else the highest stable tag."""
    repo = qp(repo)
    try:
        try:
            tag = net.json(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"]
            if re.fullmatch(r"v?\d+", tag):  # a floating major alias ("v6") lags point releases such as v6.1.2: take the highest tag instead
                try:
                    tag = FLOAT_TAGS[repo] if repo in FLOAT_TAGS else FLOAT_TAGS.setdefault(repo, ls_remote_latest(repo, OSError()))
                except OSError:
                    pass  # a failed ls-remote is not cached; the alias tag stands
            return tag
        except NotFound:
            t = [e["name"] for e in net.json(f"https://api.github.com/repos/{repo}/tags?per_page=100") if re.match(r"v?\d+(\.\d+)*$", e["name"])]
            if not t:
                raise
            return max(t, key=vkey)
    except OSError as e:
        if not re.search(r"HTTP (403|429)\b", str(e)):
            raise
        return ls_remote_latest(repo, e)  # API quota exhausted (either call): git protocol has none


def cycles(product, today):
    """Fetch endoflife.date cycles for a product; each is a dict with cycle, eol, latest, lts."""
    return net.json(f"https://endoflife.date/api/{product}.json")


def eol_check(product, ver, today):
    """Frameworks (FRAMEWORKS values) take the newest live cycle: their `lts` marks a security-only phase (see lts_row for the LTS channel). Return (cycle, is_eol, eol_date, latest_full, LTS-channel cycle or "") for ver of an endoflife.date product; cycle None when ver matches none."""
    cs = cycles(product, today)

    live = [c for c in cs if c["eol"] is False or (isinstance(c["eol"], str) and c["eol"] > today)]
    lts = [] if product in FRAMEWORKS.values() else [c for c in live if c.get("lts") is True or (isinstance(c.get("lts"), str) and c["lts"] <= today)]
    pick = (lts or live or cs)[0]  # newest live LTS cycle if the product has one, else newest live cycle
    chan = pick["cycle"] if lts else ""  # "" when no live LTS: Docker tag majors stay unrestricted
    lat = pick["latest"]["name"] if isinstance(pick["latest"], dict) else pick["latest"]
    parts = re.findall(r"\d+", ver)
    cur = next((c for n in range(len(parts), 0, -1) for c in cs if c["cycle"] == ".".join(parts[:n])), None)
    if not cur:
        return None, False, "", lat, chan
    e = cur["eol"]
    return cur["cycle"], e is True or (isinstance(e, str) and e <= today), e if isinstance(e, str) else "", lat, chan


# --- row building ------------------------------------------------------------------------------------------------------------------------

def lts_row(r, today):
    """For a framework row that is eol/outdated: a copy aimed at the product's designated LTS cycle (boolean `lts: true`, e.g. Symfony 7.4) when that cycle is live, not
    the newest, and above the current version; else None. "latest" on the main row stays the newest live cycle, so a user on a newer non-LTS cycle is never called current."""
    if r["kind"] != "runtime" or r["name"] not in FRAMEWORKS.values() or r["status"] not in ("eol", "outdated"):
        return None
    try:
        live = [c for c in cycles(r["name"], today) if c["eol"] is False or (isinstance(c["eol"], str) and c["eol"] > today)]
        c = next((c for c in live if c.get("lts") is True), None)
        lat = c and (c["latest"]["name"] if isinstance(c["latest"], dict) else c["latest"])
    except Exception:
        return None
    n = len(vkey(r["current"]))
    if not lat or lat == r["latest"] or not vkey(lat)[:n] > vkey(r["current"]):
        return None
    return dict(r, latest=lat, behind=behind(r["current"], lat), target=lat, note="; ".join(x for x in (r["note"], f"LTS channel (cycle {c['cycle']})") if x))


def row(file, name, kind, status, cur="", latest="", bh="", target="", note="", line=0):
    """Build one finding row dict; vuln/kev are filled later by the OSV pass."""
    return {"file": file, "line": line, "kind": kind, "name": name, "current": cur, "latest": latest, "behind": bh, "vulnerable": None,
            "kev": [], "target": target, "status": status, "note": note}


def dep_row(f, eco, name, cur, today):
    """Compare a locked dependency with its registry's newest stable release; unreachable gives a not-checked row."""
    try:
        vs = versions(eco, name, cur)
    except Exception as e:  # any lookup failure is a not-checked row, never a crash
        return row(f, name, eco, "not-checked", cur, note=f"NOT RUN: registry lookup failed ({type(e).__name__}: {e}); currency unknown")
    if not vs:
        return row(f, name, eco, "not-checked", cur, note="NOT RUN: registry lists no stable release")
    lat = vs[-1]
    newer = [v for v in vs if pk(eco, v) > pk(eco, cur)]
    gap = (behind(cur, lat) or "pre-release") if newer else ""
    pseudo = eco == "go" and re.search(r"-\d{14}-", cur)
    note = "pseudo-version" if pseudo else ""
    return row(f, name, eco, "outdated" if gap else "current", cur, lat.lstrip("v") if eco != "go" else lat, f"{len(newer)} releases, {gap}" if gap else "", lat if gap else "", note)


def hub_latest(image, ver, suffix, major=None):
    """Highest stable tag of library/<image> shaped like ver's tag (same number of components, same suffix), from Docker Hub's tag list (newest pages first,
    at most 4 pages; `next` is followed only on hub.docker.com). Pre-release and variant tags never match the exact shape; `major` restricts candidates to that
    major (the LTS channel). Returns the version part; OSError when Hub is unreachable, ValueError when no tag has the shape."""
    shape = re.compile(r"(\d+(?:\.\d+){%d})%s" % (len(re.findall(r"\d+", ver)) - 1, re.escape(suffix)))
    url, best = f"https://hub.docker.com/v2/repositories/library/{urllib.parse.quote(image, safe='')}/tags?page_size=100" + (f"&name={urllib.parse.quote(suffix, safe='')}" if suffix else ""), []
    for _ in range(4):
        d = net.json(url)
        best += [m[1] for r in d.get("results", []) if (m := shape.fullmatch(r.get("name", ""))) and (major is None or m[1].split(".")[0] == major)]
        if not str(url := d.get("next") or "").startswith("https://hub.docker.com/"):
            break
    if not best:
        raise ValueError(f"no stable {image} tag shaped like {ver}{suffix}")
    return max(best, key=vkey)


def runtime_row(f, product, ver, today, label, line=0, image=None, suffix=""):
    """EOL/currency row for a runtime, base image or framework. For an image, `latest` and the upgrade target come from Docker Hub's tag list (the target
    exists by construction) and the endoflife.date feed (when the image maps to a product) only supplies the end-of-life flag."""
    cyc, eol, edate, lat, latc = None, False, "", "", ""
    if product:
        try:
            cyc, eol, edate, lat, latc = eol_check(product, ver, today)  # latc: the channel cycle `lat` belongs to
        except Exception as e:
            return row(f, label, "runtime", "not-checked", ver, note=f"NOT RUN: endoflife.date lookup failed ({type(e).__name__}: {e})", line=line)
        if cyc is None:
            return row(f, label, "runtime", "not-checked", ver, note=f"NOT RUN: version {ver} matches no {product} release cycle", line=line)
    note = f"cycle {cyc} end-of-life {edate or 'reached'}" if eol else ""
    if image:
        try:
            try:  # the feed's newest (LTS-channel) release, when Docker Hub has that exact tag; else the highest stable tag of this shape
                if not lat or net.json(f"https://hub.docker.com/v2/repositories/library/{urllib.parse.quote(image, safe='')}/tags/{urllib.parse.quote(lat + suffix, safe='')}").get("name") != lat + suffix:
                    raise NotFound(lat)
            except NotFound:
                lat = hub_latest(image, ver, suffix, latc.split(".")[0] or None)
        except (OSError, ValueError, NotFound, AttributeError, TypeError) as e:  # AttributeError/TypeError: a non-dict JSON body
            if not eol:
                return row(f, label, "runtime", "not-checked", ver, note=f"NOT RUN: Docker Hub tag lookup failed ({type(e).__name__}: {e}); currency unknown", line=line)
            lat, note = "", note + " latest unverified (Docker Hub tags unavailable)"
    n = len(vkey(ver))
    gap = behind(ver, lat) if lat and vkey(lat)[:n] > vkey(ver) else ""
    status = "eol" if eol else "outdated" if gap else "current"
    target = ""
    if status != "current" and lat:
        target = f"{image}:{lat}{suffix}" if image else lat
    return row(f, label, "runtime", status, ver, lat, f"{gap}" if gap else "", target, note, line)


def eol_guess(img, ver, today):
    """The image name as an endoflife.date product when that product exists and lists ver's cycle, else None (404 or no such cycle); any other lookup failure raises."""
    try:
        return img if eol_check(img, ver, today)[0] else None
    except NotFound:
        return None


def ref_row(f, ref, i, today, stages=()):
    """Row for one image reference (FROM or compose `image:`): EOL/currency via endoflife.date, 'unpinned' for floating tags, not-checked otherwise."""
    if "$" in ref:
        return row(f, ref, "image", "not-checked", note="NOT RUN: image reference uses a variable that is not resolved here", line=i)
    ref = re.sub(r"^docker\.io/(library/)?", "", ref)
    ref, dig = ref.split("@")[0], "@" in ref
    img, _, tag = ref.partition(":")
    if img not in IMAGES and (re.search(r"[/.:]", img) or not tag or img.lower() in stages or not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", img)):  # not a possible public library/ image
        return row(f, img, "image", "not-checked", tag, note="NOT RUN: no currency source for this image", line=i)
    m = re.match(r"(\d+(?:\.\d+)*)(.*)", tag)
    if not m and dig:
        return row(f, img, "image", "not-checked", tag, note="NOT RUN: pinned by digest only; version unknown", line=i)
    if not m:
        return row(f, img, "image", "unpinned", tag or "latest", note="floating tag, no version to compare; pin a version", line=i)
    try:
        prod = IMAGES.get(img) or eol_guess(img, m[1], today)  # unmapped official image: the endoflife.date product of the same name, when it exists
    except Exception as e:  # a network/5xx failure is not "no EOL source"
        return row(f, img, "image", "not-checked", m[1], note=f"NOT RUN: endoflife.date lookup failed ({type(e).__name__}: {e})", line=i)
    r = runtime_row(f, prod, m[1], today, img, i, image=img, suffix=m[2])
    if not prod:
        r["note"] = "; ".join(x for x in (r["note"], "no end-of-life source; latest looked up on Docker Hub as library/" + img) if x)
    return r


def docker_rows(f, txt, today):
    """Rows for each Dockerfile FROM (ARG defaults substituted; stage references and scratch skipped) and each compose `image:`."""
    out, stages, args = [], set(), {}
    for i, ln in enumerate(txt.splitlines(), 1):
        if (m := re.match(r"\s*ARG\s+(\w+)=(\S+)", ln)):
            args[m[1]] = m[2].strip("\"'")
        if (m := re.match(r"\s*(?:-\s*)?image:\s*[\"']?([^\s\"'#]+)", ln)):
            if "{{" in m[1]:
                continue  # Helm/Go template, not an image reference
            out.append(ref_row(f, m[1], i, today, stages))
        elif (m := re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", ln, re.I)):
            ref, stage = m[1], (m[2] or "").lower()
            skip = ref.lower() in stages or ref == "scratch"
            if stage:
                stages.add(stage)
            if not skip:
                out.append(ref_row(f, re.sub(r"\$\{?(\w+)\}?", lambda a: args.get(a[1], a[0]), ref), i, today, stages))
    return out


def action_rows(f, txt):
    """Rows for each `uses: owner/repo@ref`: branch refs are unpinned, SHA pins need a `# vX` comment, tags compare by release."""
    out = []
    for i, ln in enumerate(txt.splitlines(), 1):
        if (m := re.match(r"\s*-?\s*uses:\s*[\"']?(docker://[^\s\"']+)", ln)):
            out.append(row(f, m[1], "action", "not-checked", note="NOT RUN: docker:// action image is not checked here", line=i))
            continue
        m = re.match(r"\s*-?\s*uses:\s*[\"']?([\w.\-]+/[\w.\-]+)(?:/[^@\s\"']*)?@([^\s\"']+)[\"']?\s*(?:#\s*(\S+))?", ln)
        if not m:
            continue
        repo, ref, cm = m[1], m[2], m[3] or ""
        cur = ref
        if re.fullmatch(r"[0-9a-f]{40}", ref):
            if not re.match(r"v?\d", cm):
                out.append(row(f, repo, "action", "not-checked", ref[:12], note="NOT RUN: SHA pin without a `# vX.Y.Z` comment; version unknown", line=i))
                continue
            cur = cm
        elif not re.match(r"v?\d", ref):
            out.append(row(f, repo, "action", "unpinned", ref, note="branch ref is not a pinned version", line=i))
            continue
        try:
            lat = gh_latest(repo)
        except Exception as e:
            out.append(row(f, repo, "action", "not-checked", cur, note=f"NOT RUN: GitHub lookup failed ({type(e).__name__}: {e})", line=i))
            continue
        n = len(vkey(cur))
        gap = behind(cur, lat) if vkey(lat)[:n] > vkey(cur) else ""
        out.append(row(f, repo, "action", "outdated" if gap else "current", cur, lat, gap, f"{repo}@{lat}" if gap else "", line=i))
    return out


def norm(eco, n):
    """Lock-map key: PEP 503 normalised for pip, unchanged otherwise."""
    return re.sub(r"[-_.]+", "-", n).lower() if eco == "pip" else n


def pep_sat(spec, v):
    """sat() for a PEP 440 specifier set: `~=` becomes a tilde range, `==` an exact/wildcard match and `!=` clauses are ignored."""
    spec = re.sub(r"!=\s*[\w.*]+,?", "", spec.split(";")[0]).replace("~=", "~").replace("==", "=").strip(" ,")
    return sat(spec, v, composer=True) if spec else True


def drift_rows(f, specs, locked, eco, **kw):
    """Rows for manifest specs that no locked version satisfies (or that the lock lacks); locked maps name -> [versions]."""
    out = []
    for n, s in specs:
        vs = locked.get(norm(eco, n))
        if not vs:
            out.append(row(f, n, eco, "drift", "", note=f"manifest requires {s} but the lockfile has no entry; re-lock"))
        elif not any((pep_sat(s, v) if eco == "pip" else sat(s, v, **kw)) for v in vs):
            out.append(row(f, n, eco, "drift", vs[0], note=f"manifest requires {s} but the lockfile pins {', '.join(vs)}; re-lock"))
    return out


# --- file walk ---------------------------------------------------------------------------------------------------------------------------

def read(root, rel):
    """Read a repo file as text, or None when missing or outside root; ValueError when it is over 5 MB (callers turn that into a not-checked row)."""
    if os.path.isabs(rel) or ".." in rel.split("/"):
        return None
    top = os.path.realpath(root)
    if not os.path.realpath(os.path.join(root, rel)).startswith(top + os.sep):
        return None  # a symlink pointing outside the repo
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            txt = fh.read(MAX_BYTES + 1)
    except OSError:
        return None
    if len(txt) > MAX_BYTES:
        raise ValueError("file over 5 MB")
    return txt


VENDOR_CAP = 200  # vendored rows listed before one overflow row
VMANIFEST = re.compile(r"PKG-INFO|package\.json|composer\.json|go\.mod|pom\.xml|Cargo\.toml|pyproject\.toml|setup\.py|.*\.gemspec")


def vendored_rows(root, files):
    """One row per vendored package: the nearest ancestor dir holding a manifest, else the first dir under the vendor dir; named from the manifest."""
    keys = {}
    vf = [f for f in files if VENDORED.search(f)]
    mdirs = {os.path.dirname(f): f for f in vf if VMANIFEST.fullmatch(os.path.basename(f))}
    for f in vf:
        end, d = VENDORED.search(f).end(), os.path.dirname(f)
        while len(d) >= end and d not in mdirs:
            d = os.path.dirname(d)
        if len(d) < end:
            rest = f[end:]
            d = f[:end] + rest.split("/")[0] if "/" in rest else f[:end].rstrip("/")
        keys[d] = mdirs.get(d)
    out = []
    for d, mf in sorted(keys.items())[:VENDOR_CAP]:
        name = os.path.basename(d)
        try:
            txt = read(root, mf) if mf and not (DEADLINE and time.time() > DEADLINE) else None  # reads count against --budget
            if txt and mf.endswith(("package.json", "composer.json")):
                name = json.loads(txt).get("name") or name
            elif txt and mf.endswith("PKG-INFO"):
                name = re.search(r"(?m)^Name:\s*(\S+)", txt)[1]
            elif txt and mf.endswith("go.mod"):
                name = re.search(r"(?m)^module\s+(\S+)", txt)[1]
            elif txt and mf.endswith(("Cargo.toml", "pyproject.toml")):
                name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', txt)[1]
            elif txt and mf.endswith("pom.xml"):
                name = re.search(r"<artifactId>([^<]+)</artifactId>", re.sub(r"(?s)<parent>.*?</parent>", "", txt))[1]
        except Exception:  # RecursionError on hostile JSON included
            name = os.path.basename(d)  # unreadable manifest: keep the dir name
        if not isinstance(name, str) or not name.isprintable() or not name.strip() or len(name) > 200:
            name = os.path.basename(d)
        out.append(row(d, str(name), "vendored", "vendored", note="vendored code is not covered by any lockfile; currency and vulnerabilities not checked, review upstream versions by hand"))
    if len(keys) > VENDOR_CAP:
        out.append(row("", "vendored", "manifest", "not-checked", note=f"NOT RUN: {len(keys) - VENDOR_CAP} more vendored packages not listed (cap {VENDOR_CAP})"))
    return out


PIP_SEED = re.compile(r"(^|/)((requirements|constraints?)[\w.\-]*\.(txt|in)|(requirements?|reqs?)/(?!(?i:readme|licen[sc]e|notice|changelog|authors|contributing)[^/]*$)[^/]+\.(txt|in))$")
REQDIR = re.compile(r"requirements?|reqs?")


def pip_files(root, files):
    """Requirement files: requirements*/constraints*.txt|.in, anything in a requirements/ dir, and every in-repo file they pull in with -r/-c (followed transitively)."""
    fs, out, todo = set(files), set(), [f for f in files if PIP_SEED.search(f)]
    while todo:
        f = todo.pop()
        if f in out:
            continue
        out.add(f)
        try:
            txt = read(root, f) or ""
        except ValueError:
            continue
        todo += [t for m in re.finditer(r"(?m)^\s*(?:--requirement|--constraint|-r|-c)(?:\s*=\s*|\s+|(?=[^\s=\-]))([^\s#]+)", txt)  # -r f, -rf, -r=f, --requirement=f; a trailing `# note` is cut
                 if (t := os.path.normpath(os.path.join(os.path.dirname(f), m[1])).replace("\\", "/")) in fs and read(root, t) is not None]
    return out


def pom_props(txt):
    """The <properties> of a pom.xml as {name: text}."""
    root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", txt, count=1))
    return {c.tag: (c.text or "").strip() for c in (root.find("properties") if root.find("properties") is not None else [])}


def pom_chain(root, f, fset):
    """In-repo ancestor poms of pom f, nearest first, as parsed elements: each child's <parent> must name the pom its relativePath (default ../pom.xml; an empty
    element means 'look in a repository') points at, by artifactId and by groupId when that pom spells one."""
    out = []
    while len(out) < 10:
        try:
            el = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", read(root, f) or "", count=1))
        except ET.ParseError:
            break
        par = el.find("parent")
        if par is None:
            break
        rp = par.find("relativePath")
        rel = (rp.text or "").strip() if rp is not None else "../pom.xml"
        if not rel:
            break
        pf = os.path.normpath(os.path.join(os.path.dirname(f), rel)).replace("\\", "/")
        pf = pf if pf.endswith(".xml") else pf + "/pom.xml"
        if pf not in fset or pf.startswith("../"):
            break
        try:
            pe = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", read(root, pf) or "", count=1))
        except ET.ParseError:
            break
        if pe.findtext("artifactId", "").strip() != par.findtext("artifactId", "").strip() or (pe.findtext("groupId") and pe.findtext("groupId").strip() != par.findtext("groupId", "").strip()):
            break
        out.append(pe)
        f = pf
    return out


def pom_parent_drift(root, f, txt, fset):
    """Drift rows for this pom's own project/dependencies that pin a literal version while an in-repo ancestor's dependencyManagement manages the same coordinate at
    another version, or an ancestor property named after the exact artifactId (`<a>.version`/`<a>-version`) or after an artifactId segment found in the groupId
    (reactor-core in io.projectreactor -> reactor.version) of the same major holds another version. Plugins, profiles and the pom's own dependencyManagement are not touched."""
    chain = pom_chain(root, f, fset)
    if not chain:
        return []
    props, managed = {}, {}
    for pe in chain:
        for c in (pe.find("properties") if pe.find("properties") is not None else []):
            props.setdefault(c.tag, (c.text or "").strip())
    sub = lambda v: re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m[1], m[0]), v)
    for pe in chain:
        for el in pe.findall("dependencyManagement/dependencies/dependency"):
            g, a, v = (el.findtext(k, "").strip() for k in ("groupId", "artifactId", "version"))
            if g and a and re.match(r"\d", sub(v)):
                managed.setdefault(f"{g}:{a}", sub(v))
    out = []
    for el in ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", txt, count=1)).findall("dependencies/dependency"):
        g, a, v = (el.findtext(k, "").strip() for k in ("groupId", "artifactId", "version"))
        if not (g and a and re.match(r"\d", v)):
            continue
        stems = [a] + [x for x in a.split("-") if len(x) >= 3 and x in g]
        pm = managed.get(f"{g}:{a}") or next((props[k] for x in stems for k in (f"{x}.version", f"{x}-version") if re.match(r"\d", props.get(k, "")) and vkey(props[k])[:1] == vkey(v)[:1]), None)
        if pm and pm != v:
            out.append(row(f, f"{g}:{a}", "maven", "drift", pm, note=f"pom pins {v} but a parent pom manages {pm}; drop the override or update the parent"))
    return out


def p_gradle_vars(txt, name):
    """Version variables a Gradle file defines: `ext.v = [k: '1.2']` (v.k), `ext.k = '1.2'`, `def k = '1.2'`, `val k = "1.2"`, `extra["k"] = "1.2"` and gradle.properties lines."""
    if name.endswith(".properties"):
        return dict(re.findall(r"(?m)^([\w.\-]+)\s*[=:]\s*(\d[\w.\-]*)\s*$", txt))
    out = {f"{m[1]}.{k}": v for m in re.finditer(r"(?m)^[ \t]*(?:(?:project\.|rootProject\.)?ext\.)?(\w+)\s*=\s*\[([^\]]*)\]", txt) for k, v in re.findall(r"""(\w+)\s*:\s*["'](\d[\w.\-]*)["']""", m[2])}
    sc = r"""(\w+)\s*=\s*["'](\d[\w.\-]*)["']"""
    out.update(re.findall(r"""(?m)^[ \t]*(?:(?:project\.|rootProject\.)?ext\.|def\s+|val\s+|var\s+)""" + sc, txt))
    for blk in re.findall(r"(?s)\bext\s*\{(.*?)\}", txt):  # bare `k = '1.2'` only inside an ext { } block
        out.update(re.findall(sc, blk))
    out.update(re.findall(r"""extra\[["'](\w+)["']\]\s*=\s*["'](\d[\w.\-]*)["']""", txt))
    return out


def gradle_sub(txt, vs):
    """Replace `${v.k}` / `$k` references in a Gradle build file with the version vs (from p_gradle_vars) defines; unknown references stay."""
    def one(m):
        k = m[1] or m[2]
        return vs.get(k) or vs.get(re.sub(r"^(?:(?:root)?[Pp]roject\.)?(?:ext\.)?", "", k)) or m[0]
    return re.sub(r"\$\{([\w.]+)\}|\$(\w+(?:\.\w+)*)", one, txt)


def ancestors(d):
    """Parent directories of d, nearest first, ending with the repo root \"\"."""
    out = []
    while d:
        d = os.path.dirname(d)
        out.append(d)
    return out


def collect(root, files, today):
    """Walk files: return (deps [(file, eco, name, ver)], other rows already built, drift/vendored rows)."""
    deps, rows = [], []
    lockdir, npmpk = {}, {}  # ponytail: each lock's `packages` map is held in memory for the run; fine below the 5 MB read cap.
    # npmpk: dir -> the `packages` map of a v2/v3 package-lock.json (workspaces resolve through it)
    nvm_float = {"node", "stable", "latest", "system", "lts/*"}

    def add(f, eco, pairs, lock=None, d=None):
        """Record lock pairs for f and remember name -> versions per directory for drift checks (`lock` overrides the pairs, e.g. npm top-level installs)."""
        deps.extend((f, eco, n, v) for n, v in pairs)
        m = lockdir.setdefault((os.path.dirname(f) if d is None else d, eco), {})
        for n, v in (lock.items() if lock else pairs):
            m.setdefault(norm(eco, n), []).append(v)

    def nr(f, name, why):
        """Append a not-checked row for something that cannot be resolved."""
        rows.append(row(f, name, "manifest", "not-checked", note="NOT RUN: " + why))

    rows.extend(vendored_rows(root, files))
    pipf, fset, gv = pip_files(root, files), set(files), {}

    def gsub(f, txt):
        """Gradle build text with its version variables (this dir and ancestors, nearest wins) substituted."""
        d = os.path.dirname(f)
        if d not in gv:
            vs = {}
            for a in reversed([d] + ancestors(d)):
                for g in sorted(files):
                    if os.path.dirname(g) == a and (g.endswith((".gradle", ".gradle.kts")) or os.path.basename(g) == "gradle.properties") and not VENDORED.search(g):
                        vs.update(p_gradle_vars(read(root, g) or "", os.path.basename(g)))
            gv[d] = vs
        return gradle_sub(txt, gv[d])
    for f in sorted(files):
        cinst = f.endswith("vendor/composer/installed.json")  # Composer's install record is the lock when no composer.lock is committed
        if VENDORED.search(f) and not cinst:
            continue
        b = os.path.basename(f)
        try:
            txt = read(root, f)
            if txt is None:
                continue
            if cinst:
                add(f, "composer", p_composer_installed(txt), d=f[:-len("vendor/composer/installed.json")].rstrip("/"))
            elif b in ("package-lock.json", "npm-shrinkwrap.json"):
                add(f, "npm", p_npm_lock(txt), p_npm_root(txt))
                npmpk[os.path.dirname(f)] = json.loads(txt).get("packages") or {}
            elif b == "yarn.lock":
                add(f, "npm", p_yarn_lock(txt))
            elif b == "pnpm-lock.yaml":
                add(f, "npm", p_pnpm_lock(txt))
                for imp, direct in p_pnpm_root(txt).items():  # drift compares each package dir with its own direct installs
                    pdir = os.path.normpath(os.path.join(os.path.dirname(f), imp)).replace("\\", "/")
                    lockdir[("" if pdir == "." else pdir, "npm")] = {n: [v] for n, v in direct.items()}  # even when empty: transitive copies must not stand in
            elif f in pipf and not b.endswith(".in"):
                add(f, "pip", p_requirements(txt))
            elif b == "poetry.lock":
                add(f, "pip", p_toml_packages(txt))
            elif b == "uv.lock":
                add(f, "pip", p_uv_lock(txt))
            elif b == "Pipfile.lock":
                add(f, "pip", p_pipfile_lock(txt))
            elif b == "Cargo.lock":
                add(f, "cargo", p_toml_packages(txt, True))
            elif b == "composer.lock":
                add(f, "composer", p_composer_lock(txt))
            elif b == "go.mod":
                pairs, bad = p_go_mod(txt)
                add(f, "go", pairs)
                for n in bad:
                    nr(f, n, "module is replaced by a local path; the code in use is not the registry version")
                if (g := re.search(r"(?m)^go\s+(\d+(?:\.\d+)*)", txt)):
                    rows.append(("runtime", f, "go", g[1], "go directive", "min"))  # a minimum, not a pin: only EOL counts
                if (g := re.search(r"(?m)^toolchain\s+go(\d+(?:\.\d+)*)", txt)):
                    rows.append(("runtime", f, "go", g[1], "go toolchain"))
            elif b == "lockfile.json" and '"dependencies"' in txt:  # maven-lockfile (chains-project): nested children = transitive deps
                pairs = p_maven_lock(txt)
                if pairs is None:
                    continue  # some other lockfile.json: not ours, skip silently
                deps.extend((f, "maven", n, v) for n, v in pairs)
                for n, v in pairs:
                    lockdir.setdefault((os.path.dirname(f), "mvnlock"), {}).setdefault(n, []).append(v)
            elif b == "pom.xml":
                pairs, bad = p_pom(txt)
                add(f, "maven", pairs)
                if (j := re.search(r"<(?:maven\.compiler\.release|java\.version)>\s*(\d[\d.]*)\s*<", txt)):
                    rows.append(("runtime", f, "eclipse-temurin", re.sub(r"^1\.", "", j[1]), "java"))
                for n in bad:
                    nr(f, n, "version is not a literal or a resolvable property, or is managed by a parent/BOM not resolved here")
            elif b in ("build.gradle", "build.gradle.kts", "gradle.lockfile") or b.endswith(".versions.toml") or (b.endswith(".kt") and re.search(r"(^|/)buildSrc/", f)):
                pairs, dyn = p_gradle(txt if b == "gradle.lockfile" or b.endswith(".toml") else gsub(f, txt), b)
                deps.extend((f, "gradle", n, v) for n, v in pairs)
                if b.endswith((".gradle", ".kts", ".kt")):  # a gradle.properties `<artifact>Version` that disagrees with the pin declared here
                    props = {}
                    for a in reversed([os.path.dirname(f)] + ancestors(os.path.dirname(f))):
                        props.update(p_gradle_vars(read(root, os.path.join(a, "gradle.properties")) or "", "gradle.properties"))
                    pv = {re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)[._-]?version$", "", k).lower()): (k, x) for k, x in props.items() if re.search(r"(?i)version$", k)}
                    for n, v in pairs:
                        art = n.split(":")[1]
                        k, x = next((pv[c] for c in (re.sub(r"[^a-z0-9]", "", art.lower()),) if c in pv), (None, None))
                        if k and not is_pre("gradle", v) and pk("gradle", x) != pk("gradle", v):
                            rows.append(row(f, n, "gradle", "drift", v, note=f"{b} declares {v} but gradle.properties {k}={x}; one of them is stale"))
                if b == "gradle.lockfile":
                    for n, v in pairs:
                        lockdir.setdefault((os.path.dirname(f), "gradlelock"), {}).setdefault(n, []).append(v)
                if (j := re.search(r"(?:JavaLanguageVersion\.of|jvmToolchain)\(\s*(\d+)\s*\)", txt)):
                    rows.append(("runtime", f, "eclipse-temurin", j[1], "java"))
                rows.extend(row(f, n, "gradle", "unpinned", note="dynamic version resolves to whatever is newest at build time; pin a version") for n in dyn)
            elif re.fullmatch(r"Dockerfile[\w.\-]*|[\w.\-]+\.Dockerfile|(docker-)?compose[\w.\-]*\.ya?ml", b):
                rows.extend(docker_rows(f, txt, today))
            elif re.search(r"(^|/)\.github/(workflows|actions)/.*\.ya?ml$", f) or b in ("action.yml", "action.yaml"):
                rows.extend(action_rows(f, txt))
            elif b.endswith((".yaml", ".yml")) and re.search(r"(?m)^apiVersion:", txt) and re.search(r"(?m)^kind:", txt):  # Kubernetes manifest: container images
                rows.extend(docker_rows(f, txt, today))
            elif b in ("rust-toolchain", "rust-toolchain.toml"):
                if (m := re.search(r"""(?m)^\s*(?:channel\s*=\s*["'])?(\d+\.\d+(?:\.\d+)?)\b""", txt)):  # nightly/stable/beta float: no version to compare
                    rows.append(("runtime", f, "rust", m[1], "rust"))
            elif b == "gradle-wrapper.properties":
                if (m := re.search(r"(?m)^distributionUrl=.*/gradle-(\d+(?:\.\d+)*)-(?:bin|all)\.zip", txt)):
                    rows.append(("runtime", f, "gradle", m[1], "gradle"))
            elif b in (".tool-versions", "mise.toml", ".mise.toml"):
                rows.extend(("runtime", f, prod, ver, prod) for prod, ver in p_tool_versions(txt, b))
            elif b in (".nvmrc", ".node-version", ".python-version", ".ruby-version", ".php-version"):
                prod = {".nvmrc": "nodejs", ".node-version": "nodejs", ".python-version": "python", ".ruby-version": "ruby", ".php-version": "php"}[b]
                v = txt.strip().splitlines()[0].strip() if txt.strip() else ""
                if (m := re.search(r"\d+(?:\.\d+)*", v)):
                    rows.append(("runtime", f, prod, m[0], b))
                elif v.lower() in nvm_float:
                    rows.append(row(f, b, "runtime", "unpinned", v, note="floating alias, no version to compare; pin a version"))
                else:
                    nr(f, b, f"runtime pin {v!r} has no version number to compare")
        except Exception as e:
            nr(f, b, f"could not parse ({type(e).__name__}: {e})")
    def piplock(d):
        """Locked pip versions visible from dir d: its own locks plus those in its requirements/ subdirs; None when there are none."""
        ms = [m for (ld, k), m in lockdir.items() if k == "pip" and (ld == d or (os.path.dirname(ld) == d and REQDIR.fullmatch(os.path.basename(ld))))]
        return {n: sum((m.get(n, []) for m in ms), []) for m in ms for n in m} if ms else None
    for f in sorted(files):  # drift needs the lock found above, so it runs second
        b, d = os.path.basename(f), os.path.dirname(f)
        if VENDORED.search(f) or not (b in ("package.json", "composer.json", "Cargo.toml", "pyproject.toml", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod") or b.endswith(".versions.toml") or b in ("setup.cfg", "Pipfile", "setup.py") or (f in pipf and b.endswith(".in"))):
            continue
        try:
            if (txt := read(root, f)) is None:
                continue
            if b == "package.json":
                specs = p_json_manifest(txt, ("dependencies", "devDependencies", "optionalDependencies"))
                lk = lockdir.get((d, "npm"))
                if lk is None:  # a workspace package: nearest ancestor package-lock that lists it in `packages`
                    anc = next((a for a in ancestors(d) if a in npmpk), None)
                    ws = os.path.relpath(d, anc or ".").replace("\\", "/") if d else ""
                    wsg = (npmpk[anc].get("") or {}).get("workspaces") if anc is not None else None
                    wsg = wsg.get("packages") if isinstance(wsg, dict) else wsg  # npm lists workspaces in the root entry, not necessarily one `packages` entry per workspace
                    if anc is not None and (ws in npmpk[anc] or any(re.fullmatch(re.escape(g.removeprefix("./").rstrip("/")).replace(r"\*\*", ".*").replace(r"\*", "[^/]*"), ws) for g in wsg or [] if isinstance(g, str))):
                        pk_ = npmpk[anc]
                        ent = {n: pk_.get(f"{ws}/node_modules/{n}") or pk_.get(f"node_modules/{n}") or {} for n, _ in specs}  # own copy first, then hoisted
                        specs = [(n, sp) for n, sp in specs if not ent[n].get("link")]  # linked sibling workspaces have no version
                        lk = {n: [e["version"]] for n, e in ent.items() if e.get("version")}  # a missing entry becomes a "no entry" drift row
                if lk is not None:
                    rows.extend(drift_rows(f, specs, lk, "npm"))
                elif not any((a, "npm") in lockdir for a in ancestors(d)):  # no lock anywhere above: an exact manifest pin is the installed version
                    deps.extend((f, "npm", n, v) for n, s in specs if (v := exact("npm", s)))
            elif b == "composer.json":
                j = json.loads(txt)
                if (lk := lockdir.get((d, "composer"))) is not None:
                    rows.extend(drift_rows(f, p_json_manifest(txt, ("require", "require-dev")), lk, "composer", composer=True))
                else:
                    deps.extend((f, "composer", n, v) for n, s in p_json_manifest(txt, ("require", "require-dev")) if (v := exact("composer", s)))
                if (pf := ((j.get("config") or {}).get("platform") or {}).get("php")) and (vs := re.findall(r"\d+(?:\.\d+)*", str(pf))):
                    rows.append(("runtime", f, "php", vs[0], "php"))
                elif isinstance(rq := (j.get("require") or {}).get("php"), str):  # lowest LOWER bound only; `<8.1` alone gives no row
                    vs = [m[1] for alt in re.split(r"\|\|?", rq) for m in re.findall(r"(<=?|!=)?\s*v?(\d+(?:\.\d+)*)", alt.replace(",", " ")) if m[0] == ""]
                    if vs:
                        rows.append(("runtime", f, "php", min(vs, key=vkey), "php", "allows"))
            elif b == "pom.xml":
                lk = lockdir.get((d, "mvnlock")) or {}
                rows.extend(row(f, n, "maven", "drift", lk[n][0], note=f"pom pins {v} but lockfile.json has {', '.join(lk[n])}; re-lock") for n, v in p_pom(txt)[0] if n in lk and v not in lk[n])
                rows.extend(row(f, n, "maven", "drift", v, note=f"pom restates {v} but its own dependencyManagement pins {m}; the literal wins, drop one") for n, v, m in p_pom_overrides(txt))
                rows.extend(pom_parent_drift(root, f, txt, fset))
            elif b.startswith("build.gradle") or b.endswith(".versions.toml"):
                cat = b.endswith(".versions.toml")
                pd = os.path.dirname(d) if cat and os.path.basename(d) == "gradle" else d  # catalog lives in <project>/gradle/
                locks = [m for (ld, k), m in lockdir.items() if k == "gradlelock" and (ld == pd or (cat and (not pd or ld.startswith(pd + "/"))))]  # build files: same-dir lock only
                lk = {n: [v for m in locks for v in m.get(n, [])] for m in locks for n in m} if locks else None  # union of lockfiles at or below the project dir
                if lk is not None:  # declared vs locked, both directions
                    for n, v in p_gradle(txt if cat else gsub(f, txt), b)[0]:
                        if n.endswith(".gradle.plugin"):
                            continue
                        if n not in lk:
                            if not cat:  # a catalog lists unused libs and modules without a lock: only below-lock drift counts
                                rows.append(row(f, n, "gradle", "drift", note=f"{b} declares {v} but gradle.lockfile has no entry; re-lock"))
                        elif not (is_pre("gradle", v) or any(pk("gradle", x) == pk("gradle", v) for x in lk[n])):  # exact declared vs locked (2.0 == 2.0.0), either direction; pre-release/SNAPSHOT declarations skipped
                            above = all(pk("gradle", x) > pk("gradle", v) for x in lk[n])
                            rows.append(row(f, n, "gradle", "drift", lk[n][0], note=f"{b} declares {v} but gradle.lockfile pins {', '.join(lk[n])}"
                                            + ("; the lock is above the declaration, which may come from dependency conflict resolution" if above else "; re-lock")))
            elif b == "go.mod":
                gs = read(root, os.path.join(d, "go.sum"))
                have = {(x.split()[0], x.split()[1].removesuffix("/go.mod")) for x in (gs or "").splitlines() if len(x.split()) > 1}  # "mod v h1:" and "mod v/go.mod h1:"
                rows.extend(row(f, n, "go", "drift", v, note=f"go.mod requires {v} but go.sum has no entry for it; run go mod tidy") for n, v in p_go_mod(txt)[0] if gs is not None and (n, v) not in have)
                vm = dict(re.findall(r"(?m)^# (\S+) (v\S+)$", read(root, os.path.join(d, "vendor", "modules.txt")) or ""))  # `# module version` headers of the vendor tree
                rows.extend(row(f, n, "go", "drift", v, note=f"go.mod requires {v} but vendor/modules.txt has {vm[n]}; run go mod vendor") for n, v in p_go_mod(txt)[0] if n in vm and vm[n] != v)
            elif b == "Cargo.toml":
                ad = d if (d, "cargo") in lockdir else next((a for a in ancestors(d) if (a, "cargo") in lockdir), None)  # a workspace member uses the nearest ancestor lock
                art = (read(root, os.path.join(ad, "Cargo.toml")) or "") if ad is not None and ad != d else txt
                rel = os.path.relpath(d or ".", ad or ".").replace("\\", "/")
                if ad is not None and ad != d and (not re.search(r"^\s*\[workspace\]", art, re.M) or re.search(r"exclude\s*=\s*\[[^\]]*[\"']%s/?[\"']" % re.escape(rel), art)):
                    ad = None  # not a workspace root, or the member is excluded from it
                if ad is not None:
                    rt = art
                    ws = dict(p_cargo_toml(rt or "", "workspace.dependencies"))
                    rows.extend(drift_rows(f, p_cargo_toml(txt, ws=ws), lockdir[(ad, "cargo")], "cargo", cargo=True))
                else:  # no Cargo.lock: `=x.y.z` pins (workspace.dependencies, member and [target.*] tables) are the versions in use
                    deps.extend((f, "cargo", n, v) for n, s in p_cargo_toml(txt) if (v := exact("cargo", s)))
                wr = next((t for a in ancestors(d) if "[workspace.dependencies]" in (t := read(root, os.path.join(a, "Cargo.toml")) or "")), "")
                wsx = {n: exact("cargo", s) for n, s in p_cargo_toml(wr, "workspace.dependencies")}
                rows.extend(row(f, n, "cargo", "drift", v, note=f"{f} pins {v} but [workspace.dependencies] pins {wsx[n]}; align them") for n, s in p_cargo_toml(txt) if (v := exact("cargo", s)) and wsx.get(n) and wsx[n] != v)
            elif b in ("pyproject.toml", "setup.cfg", "Pipfile", "setup.py") or b.endswith(".in"):
                specs = {"pyproject.toml": p_pyproject, "setup.cfg": p_setup_cfg, "Pipfile": p_pipfile, "setup.py": p_setup_py}.get(b, lambda t: p_pip_specs(t.splitlines()))(txt)
                if (lk := piplock(d)) is not None:
                    rows.extend(drift_rows(f, specs, lk, "pip"))
                else:  # no lock beside it: `==` pins are the versions in use
                    deps.extend((f, "pip", n, v) for n, s in specs if (v := exact("pip", s)))
        except Exception as e:
            nr(f, b, f"could not parse ({type(e).__name__}: {e})")
    gd = {}  # one module declared at different versions in two files of the same Gradle project (build file vs version catalog, ...)
    for f, eco, n, v in deps:
        b, d = os.path.basename(f), os.path.dirname(f)
        if eco == "gradle" and b != "gradle.lockfile" and not is_pre("gradle", v):
            gd.setdefault((os.path.dirname(d) if b.endswith(".versions.toml") and os.path.basename(d) == "gradle" else d, n), set()).add((v, f))
    for (_, n), m in sorted(gd.items()):
        per = {}
        for v, f in m:
            per.setdefault(f, set()).add(pk("gradle", v))
        if len(per) > 1 and all(len(s) == 1 for s in per.values()) and len(set().union(*per.values())) > 1:  # a file that itself declares two versions (two catalog aliases) is ambiguous: skip
            s = sorted(m, key=lambda x: pk("gradle", x[0]))
            (v, f), (v2, f2) = s[0], s[-1]  # lowest vs highest: different versions, so different files
            rows.append(row(f, n, "gradle", "drift", v, note=f"{f} declares {v} but {f2} declares {v2}; one of them is stale"))
    return deps, rows


def osv_pass(rows):
    """Fill vulnerable (list of ids, or None + NOT RUN note) and kev (CVE ids) for dependency rows; KEV list fetched once."""
    todo = [r for r in rows if r["kind"] in OSV_ECO and r["status"] in ("outdated", "current") and r["current"]]
    if not todo:
        return
    keys = sorted({(r["kind"], r["name"], r["current"]) for r in todo})
    res, err = {}, "short response"
    try:
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            body = json.dumps({"queries": [{"package": {"name": n, "ecosystem": OSV_ECO[e]}, "version": v.lstrip("v") if e == "go" else v} for e, n, v in chunk]}).encode()
            for k, r in zip(chunk, net.json("https://api.osv.dev/v1/querybatch", body)["results"]):
                res[k] = [x["id"] for x in r.get("vulns", [])]
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    for r in todo:
        if (r["kind"], r["name"], r["current"]) not in res:
            r["note"] = (r["note"] + "; " if r["note"] else "") + f"NOT RUN: OSV lookup failed ({err}); vulnerability status unknown"
            r["osv_failed"] = True
    ids = sorted({i for v in res.values() for i in v})
    kev, alias, bad = set(), {}, set()
    if ids:
        try:
            kev = {e["cveID"] for e in net.json(KEV_URL)["vulnerabilities"]}
        except Exception as e:
            for r in todo:
                r["note"] = (r["note"] + "; " if r["note"] else "") + f"NOT RUN: KEV lookup failed ({type(e).__name__}: {e}); KEV ordering unavailable"
            ids = []

        def aliases(i):
            """Return [i] + the OSV aliases of i; an id that cannot be resolved lands in `bad`."""
            if i.startswith("CVE-"):
                return [i]
            try:
                return [i] + (net.json("https://api.osv.dev/v1/vulns/" + urllib.parse.quote(i)).get("aliases") or [])
            except Exception:
                bad.add(i)
                return [i]
        with cf.ThreadPoolExecutor(8) as ex:
            alias = dict(zip(ids, ex.map(aliases, ids)))
    for r in todo:
        k = (r["kind"], r["name"], r["current"])
        if k in res:
            r["vulnerable"] = res[k]
            r["kev"] = sorted({c for i in res[k] for c in alias.get(i, [i]) if c in kev})
            if bad & set(res[k]):
                r["note"] = (r["note"] + "; " if r["note"] else "") + "NOT RUN: alias lookup failed for " + ",".join(sorted(bad & set(res[k]))) + "; KEV status unknown"


RANK = {"kev": 0, "vulnerable": 1, "eol": 2, "outdated": 3, "drift": 4, "unpinned": 5, "vendored": 6, "not-checked": 7, "current": 9}


def rule_of(r):
    """Return the output rule for a row: kev and vulnerable override the status."""
    if r.get("osv_failed") and r["status"] == "current":
        return "not-checked"  # OSV never answered: not provably clean
    return "kev" if r["kev"] else "vulnerable" if r["vulnerable"] else r["status"]


def message(r):
    """Compose the human message carrying name, current, latest, behind, vulnerable ids and upgrade target."""
    p = [f"{r['kind']} {r['name']}"]
    if r["current"] or r["latest"]:
        p.append(f"current {r['current'] or '-'}, latest {r['latest'] or '-'}")
    if r["behind"]:
        p.append(f"behind: {r['behind']}")
    if r["vulnerable"]:
        p.append("vulnerable: " + ",".join(r["vulnerable"][:8]) + (f" (+{len(r['vulnerable']) - 8} more)" if len(r["vulnerable"]) > 8 else ""))
    if r["kev"]:
        p.append("CISA KEV: " + ",".join(r["kev"]))
    if r["target"]:
        p.append(f"upgrade to {r['target']}")
    if r["note"]:
        p.append(r["note"])
    return "; ".join(p).replace("\t", " ").replace("\n", " ")


def run(root, files, today, budget=45.0):
    """Collect, look up and return the sorted row dicts (every row, current ones included)."""
    global DEADLINE
    t0 = time.time()
    DEADLINE = t0 + budget
    deps, rows = collect(root, files, today)
    rt = [r for r in rows if isinstance(r, tuple)]
    rows = [r for r in rows if isinstance(r, dict)]
    for f, eco, n, v in deps:  # framework EOL from locked versions
        p = FRAMEWORKS.get((eco, n))
        if p:
            rt.append(("runtime", f, p, v, p))  # label = the framework product, not the dependency coordinate
    seen, jobs = set(), []
    for _, f, prod, ver, label, *kind in rt:
        if (f, prod, ver, label) not in seen:
            seen.add((f, prod, ver, label))
            jobs.append((f, prod, ver, label, kind))
    uniq = sorted({(eco, n, v) for _, eco, n, v in deps})
    ex = cf.ThreadPoolExecutor(8)
    rfut = {ex.submit(runtime_row, f, prod, ver, today, label): (f, prod, ver, label, kind) for f, prod, ver, label, kind in jobs}
    dfut = {ex.submit(dep_row, "", k[0], k[1], k[2], today): k for k in uniq}
    cf.wait(list(rfut) + list(dfut), timeout=max(0.0, t0 + budget - time.time()))  # hard budget: stuck lookups become not-checked rows
    global STUCK
    STUCK = any(not x.done() for x in list(rfut) + list(dfut))
    ex.shutdown(wait=False, cancel_futures=True)
    exhausted = "NOT RUN: time budget exhausted before this lookup"

    def fin(x, mk):
        """Result of a finished future, else mk(note): cancelled or unfinished lookups are budget-exhausted, a raised one names its exception."""
        if x.cancelled() or not x.done():
            return mk(exhausted)
        return mk(f"NOT RUN: lookup failed ({x.exception()!r})") if x.exception() else x.result()
    for x, (f, prod, ver, label, kind) in rfut.items():
        r = fin(x, lambda note: row(f, label, "runtime", "not-checked", ver, note=note))
        if kind == ["allows"] and r["status"] == "eol":
            r["note"] = f"composer require.php allows EOL {prod} {ver}; " + r["note"]
        if kind == ["min"] and r["status"] == "outdated":
            r.update(status="current", behind="", target="")
        rows.append(r)
        if (x := lts_row(r, today)):
            rows.append(x)
    res = {k: fin(x, lambda note: row("", k[1], k[0], "not-checked", k[2], note=note)) for x, k in dfut.items()}
    for f, eco, n, v in deps:
        r = dict(res[(eco, n, v)])
        r["file"] = f
        rows.append(r)
    osv_pass(rows)
    if not STUCK:  # stuck workers keep their retries bounded by the deadline
        DEADLINE = None
    uniq_rows = {json.dumps(r, sort_keys=True): r for r in rows}.values()  # identical rows (same file, name, status, note) collapse
    return sorted(uniq_rows, key=lambda r: (RANK[rule_of(r)], r["file"], r["name"]))


def main(argv=None):
    """CLI entry: print TSV rows (non-current) or JSON (all rows); exit 0."""
    ap = argparse.ArgumentParser(description="dependency currency detector")
    ap.add_argument("--root", default=".")
    ap.add_argument("--stdin", action="store_true", help="newline-separated paths relative to --root (default: git ls-files)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    files = [x for x in sys.stdin.read().split("\n") if x] if a.stdin else subprocess.run(
        ["git", "-C", a.root, "ls-files", "-z"], capture_output=True, text=True, check=False).stdout.split("\0")
    rows = run(a.root, [x for x in files if x], a.today, a.budget)
    if a.json:
        print(json.dumps([dict(r, rule=rule_of(r)) for r in rows], indent=1))
    else:
        for r in rows:
            if rule_of(r) != "current":
                print(f"{r['file']}\t{r['line']}\t{rule_of(r)}\t{message(r)}")
    if STUCK:  # worker threads blocked in sockets would hold the interpreter open past the budget
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
