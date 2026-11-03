#!/usr/bin/env python3
"""Generate G5 set #5: 8 fixture repos + truth/*.json + drift.json under this directory.

Same truth schema and "latest" rule as sets #2-#4 (see ../snapshot.py). Every registry package, action and image name is new
versus sets #1-#4 (language runtimes python, go, php, rust, nodejs are unavoidable). Layouts: npm workspaces + package-lock v3
(apps/*, libs/*), pip requirements/ split + constraints.txt + setup.cfg, go.work with two modules, maven multi-module (parent
dependencyManagement + child override), gradle Groovy DSL + ext versions + per-module lockfile, cargo single crate with target
tables + vendored crate + bare rust-toolchain file, composer root + nested module manifest/lock, polyglot monorepo (npm lock v2,
Pipfile.lock, go module, vendored npm copy, compose image). Traps: "fake latest" comments (not in truth).
KEV row: maven org.springframework:spring-beans pinned 5.3.17 carries a "vuln" object (OSV ids from api.osv.dev, KEV CVE from
the CISA catalog), fetched at build time; snapshot.py ignores it.
Decoys are pinned at the registry latest at build time. Hashes are deterministic placeholders.
Needs network. GitHub API answers are cached under $TMPDIR/g5s5gh so reruns stay inside the 60/hr unauthenticated limit.
Run: python3 set5/build.py
"""
import base64, hashlib, http.client, json, os, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import snapshot as S

_get = S.get
def _cached(url, accept="application/json"):
    if "api.github.com" not in url:
        return _get(url, accept)
    d = os.path.join(os.environ.get("TMPDIR", "/tmp"), "g5s5gh"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, hashlib.md5(url.encode()).hexdigest())
    if not os.path.exists(p):
        r = _get(url, accept)
        open(p, "w").write(r)
    return open(p).read()
S.get = _cached

ROWS, DRIFT = {}, {}

def w(path, text):
    p = os.path.join(HERE, "fixtures", path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)

def ph(s):
    return base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()

def row(fx, eco, name, pin, direct, file, declared=None, eol_product=None, vendored=False):
    """pin 'L' = latest (decoy). Registry ecosystems verify the pin exists; actions verify the tag."""
    r = {"name": name, "ecosystem": eco}
    if eco in ("npm", "pip", "go", "maven", "gradle", "cargo", "composer"):
        vs = S.versions(eco, name)
        lat = vs[-1]
        cur = lat if pin == "L" else pin
        assert cur in vs, (eco, name, cur)
    else:
        if eol_product:
            r["eol_product"] = eol_product
        lat = S.latest(r)
        cur = lat if pin == "L" else pin
        if eco == "docker" and cur != lat:
            t = S.gj("https://hub.docker.com/v2/repositories/library/%s/tags/%s" % (name, cur))
            assert t.get("name") == cur, ("hub tag", name, cur)
        if eco == "actions" and cur != lat:
            S.get("https://api.github.com/repos/%s/git/ref/tags/v%s" % (name, cur))
    r.update(current=cur, latest=lat, behind=S.behind(cur, lat), decoy=cur == lat,
             eol=S.eol_of(eol_product, cur) if eol_product else None,
             direct=direct, file=file, drift=declared, vendored=vendored)
    if declared and not vendored:
        DRIFT.setdefault(fx, []).append(name)
    ROWS.setdefault(fx, []).append(r)
    return cur

def workflow(fx, name, pins, run):
    path = ".github/workflows/" + name
    cur = [(n, row(fx, "actions", n, p, True, path)) for n, p in pins]
    w(fx + "/" + path, "name: ci\non:\n  pull_request:\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n" +
      "".join("      - uses: %s@v%s\n" % (n, c) for n, c in cur) + "      - run: %s\n" % run)



def vuln(fx, ecosystem, name, version, cves):
    """Attach OSV ids (api.osv.dev) and KEV CVEs (CISA catalog) for a pinned version; asserts each CVE is in the KEV feed.
    Both endpoints truncate bodies (IncompleteRead) now and then, so the whole lookup retries up to 6 times."""
    for i in range(6):
        try:
            q = json.dumps({"package": {"name": name, "ecosystem": ecosystem}, "version": version}).encode()
            osv = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.osv.dev/v1/query", q, {"Content-Type": "application/json"}), timeout=30).read())
            kev = {v["cveID"] for v in json.loads(_get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"))["vulnerabilities"]}
            break
        except OSError:
            if i == 5:
                raise
        except http.client.IncompleteRead:
            if i == 5:
                raise
    ids = sorted(v["id"] for v in osv.get("vulns", []))
    assert ids and all(c in kev for c in cves), (ids, cves)
    [r for r in ROWS[fx] if r["name"] == name][0]["vuln"] = {"osv": ids, "kev": sorted(cves)}

def jd(o):
    return json.dumps(o, indent=2) + "\n"

# 1 npm: npm workspaces (apps/*, libs/*), package-lock v3, drift on jsonwebtoken + bcryptjs, node EOL, cassandra in compose
def npm():
    f = "npm"; ip = "package-lock.json"
    web = [("preact", row(f, "npm", "preact", "10.19.3", True, ip)), ("luxon", row(f, "npm", "luxon", "3.4.4", True, ip)), ("mitt", row(f, "npm", "mitt", "L", True, ip))]
    api = [("ws", row(f, "npm", "ws", "8.14.2", True, ip)), ("jsonwebtoken", row(f, "npm", "jsonwebtoken", "8.5.1", True, ip, "^9.0.0")),
           ("bcryptjs", row(f, "npm", "bcryptjs", "2.4.3", True, ip, "^3.0.0")), ("yargs", row(f, "npm", "yargs", "17.7.2", True, ip))]
    lib = [("semver", row(f, "npm", "semver", "7.5.4", True, ip))]
    ind = [("fast-glob", row(f, "npm", "fast-glob", "3.3.1", False, ip)), ("nanostores", row(f, "npm", "nanostores", "L", False, ip))]
    decl = {"jsonwebtoken": "^9.0.0", "bcryptjs": "^3.0.0"}
    rng = lambda n, v: decl.get(n, "^" + v)
    w("npm/package.json", jd({"name": "harbor-suite", "private": True, "workspaces": ["apps/*", "libs/*"]}))
    for p, grp in (("apps/web", web), ("apps/api", api), ("libs/util", lib)):
        w("npm/%s/package.json" % p, jd({"name": "@harbor/" + p.split("/")[1], "version": "1.0.0", "dependencies": {n: rng(n, v) for n, v in grp}}))
    pk = {"": {"name": "harbor-suite", "workspaces": ["apps/*", "libs/*"]}}
    for n, v in web + api + lib + ind:
        pk["node_modules/" + n] = {"version": v, "resolved": "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (n, n, v), "integrity": "sha512-" + ph(n + v)}
    w("npm/package-lock.json", jd({"name": "harbor-suite", "lockfileVersion": 3, "requires": True, "packages": pk}))
    w("npm/.node-version", row(f, "eol", "nodejs", "18.19.1", True, ".node-version", eol_product="nodejs") and "18.19.1\n")
    cs = row(f, "docker", "cassandra", "3.11.19", True, "infra/docker-compose.yml", eol_product="cassandra")
    w("npm/infra/docker-compose.yml", "# note: cassandra:99.0 is on the roadmap, not released\nservices:\n  store:\n    image: cassandra:%s\n    ports:\n      - \"9042:9042\"\n" % cs)
    workflow(f, "pages.yml", [("actions/configure-pages", "3.0.6"), ("actions/deploy-pages", "L")], "npm test --workspaces")

# 2 pip: requirements/ split (-r include), constraints.txt for transitives, setup.cfg drift on tabulate, EOL python image
def pip():
    f = "pip"; bp = "requirements/base.txt"
    base = [("structlog", row(f, "pip", "structlog", "23.1.0", True, bp)), ("jsonschema", row(f, "pip", "jsonschema", "4.17.3", True, bp)),
            ("arrow", row(f, "pip", "arrow", "1.2.3", True, bp)), ("cachetools", row(f, "pip", "cachetools", "5.3.1", True, bp)),
            ("msgpack", row(f, "pip", "msgpack", "L", True, bp)), ("pillow", row(f, "pip", "pillow", "9.5.0", True, bp))]
    dev = [("tabulate", row(f, "pip", "tabulate", "0.8.10", True, "requirements/dev.txt", ">=0.9.0")),
           ("pendulum", row(f, "pip", "pendulum", "2.1.2", True, "requirements/dev.txt"))]
    ind = [("typing-extensions", row(f, "pip", "typing-extensions", "L", False, "constraints.txt"))]
    w("pip/requirements/base.txt", "".join("%s==%s\n" % x for x in base) + "# structlog 99.0 pending release\n")
    w("pip/requirements/dev.txt", "-r base.txt\n" + "".join("%s==%s\n" % x for x in dev))
    w("pip/constraints.txt", "".join("%s==%s\n" % x for x in ind))
    w("pip/setup.cfg", "[metadata]\nname = harbor-batch\nversion = 0.4.0\n\n[options]\npackages = find:\ninstall_requires =\n    structlog\n    jsonschema\n    tabulate>=0.9.0\n")
    py = row(f, "docker", "python", "3.9.18", True, "Dockerfile", eol_product="python")
    w("pip/Dockerfile", "FROM python:%s\nWORKDIR /app\nCOPY requirements/ requirements/\nRUN pip install -r requirements/base.txt -c constraints.txt\n" % py)
    workflow(f, "publish.yml", [("pypa/gh-action-pypi-publish", "1.8.10")], "python -m build")

# 3 go: go.work with two modules, drift via go.sum, EOL go, traefik image
def go():
    f = "go"; a, b = "svc/api/go.mod", "svc/worker/go.mod"
    ra = [("github.com/tidwall/gjson", row(f, "go", "github.com/tidwall/gjson", "v1.14.4", True, a)), ("github.com/samber/lo", row(f, "go", "github.com/samber/lo", "L", True, a)),
          ("github.com/hashicorp/go-multierror", row(f, "go", "github.com/hashicorp/go-multierror", "v1.1.0", True, a))]
    rb = [("github.com/BurntSushi/toml", row(f, "go", "github.com/BurntSushi/toml", "v1.3.2", True, b, "go.sum has only v1.3.1")),
          ("github.com/oklog/ulid/v2", row(f, "go", "github.com/oklog/ulid/v2", "v2.0.2", True, b)), ("golang.org/x/time", row(f, "go", "golang.org/x/time", "L", True, b))]
    ri = [("github.com/gofrs/flock", row(f, "go", "github.com/gofrs/flock", "v0.8.1", False, b))]
    row(f, "eol", "go", "1.20", True, "go.work", eol_product="go")
    w("go/go.work", "go 1.20\n\nuse (\n\t./svc/api\n\t./svc/worker\n)\n")
    w("go/" + a, "module example.com/harbor/api\n\ngo 1.20\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in ra) + ")\n")
    w("go/" + b, "module example.com/harbor/worker\n\ngo 1.20\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in rb) + "\t%s %s // indirect\n)\n" % ri[0])
    w("go/svc/worker/go.sum", "".join("%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, "v1.3.1" if n.endswith("toml") else c, ph(n + c), n, "v1.3.1" if n.endswith("toml") else c, ph(n + c + "m")) for n, c in rb + ri))
    w("go/svc/api/go.sum", "".join("%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, c, ph(n + c), n, c, ph(n + c + "m")) for n, c in ra))
    tf = row(f, "docker", "traefik", "3.1.7", True, "deploy/docker-compose.yml", eol_product="traefik")
    w("go/deploy/docker-compose.yml", "services:\n  edge:\n    image: traefik:%s\n    command: --providers.docker\n" % tf)
    workflow(f, "release.yml", [("goreleaser/goreleaser-action", "4.6.0")], "go test ./...")

# 4 maven: multi-module (parent dependencyManagement, child override = drift on reactor-core), KEV/OSV pin spring-beans 5.3.17, couchdb image
def maven():
    f = "maven"
    core = [("com.github.ben-manes.caffeine:caffeine", row(f, "maven", "com.github.ben-manes.caffeine:caffeine", "2.9.3", True, "core/pom.xml")),
            ("org.bouncycastle:bcprov-jdk18on", row(f, "maven", "org.bouncycastle:bcprov-jdk18on", "1.72", True, "core/pom.xml")),
            ("org.apache.commons:commons-configuration2", row(f, "maven", "org.apache.commons:commons-configuration2", "L", True, "core/pom.xml")),
            ("io.projectreactor:reactor-core", row(f, "maven", "io.projectreactor:reactor-core", "3.5.11", True, "core/pom.xml", "3.6.0"))]
    web = [("org.springframework:spring-beans", row(f, "maven", "org.springframework:spring-beans", "5.3.17", True, "web/pom.xml")),
           ("org.postgresql:postgresql", row(f, "maven", "org.postgresql:postgresql", "42.5.1", True, "web/pom.xml")),
           ("org.flywaydb:flyway-core", row(f, "maven", "org.flywaydb:flyway-core", "9.22.3", True, "web/pom.xml")),
           ("com.h2database:h2", row(f, "maven", "com.h2database:h2", "2.1.214", True, "web/pom.xml"))]
    vuln(f, "Maven", "org.springframework:spring-beans", "5.3.17", ["CVE-2022-22965"])
    dep = lambda n, v: "    <dependency><groupId>%s</groupId><artifactId>%s</artifactId>%s</dependency>\n" % (*n.split(":"), "<version>%s</version>" % v if v else "")
    pom = lambda mod, deps: ('<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n  <parent><groupId>example.com.harbor</groupId>'
        '<artifactId>harbor-parent</artifactId><version>5.0.0</version></parent>\n  <artifactId>harbor-%s</artifactId>\n  <dependencies>\n%s  </dependencies>\n</project>\n' % (mod, deps))
    # parent manages every version via properties; the core module overrides reactor-core with a literal (the drift)
    w("maven/pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n  <groupId>example.com.harbor</groupId><artifactId>harbor-parent</artifactId>'
      '<version>5.0.0</version><packaging>pom</packaging>\n  <modules><module>core</module><module>web</module></modules>\n  <properties>\n    <reactor.version>3.6.0</reactor.version>\n'
      + "".join("    <%s.version>%s</%s.version>\n" % (n.split(":")[1], v, n.split(":")[1]) for n, v in core[:3] + web) + '  </properties>\n  <dependencyManagement>\n    <dependencies>\n'
      + "".join("    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>${%s.version}</version></dependency>\n" % (*n.split(":"), n.split(":")[1]) for n, v in core[:3] + web)
      + '    </dependencies>\n  </dependencyManagement>\n</project>\n')
    w("maven/core/pom.xml", pom("core", "".join(dep(n, None) for n, v in core[:3]) + dep(*core[3])))
    w("maven/web/pom.xml", pom("web", "".join(dep(n, None) for n, v in web)))
    cd = row(f, "docker", "couchdb", "3.3.3", True, "docker-compose.yml", eol_product="couchdb")
    w("maven/docker-compose.yml", "services:\n  docs:\n    image: couchdb:%s\n    environment:\n      COUCHDB_USER: admin\n" % cd)
    workflow(f, "build.yml", [("stCarolas/setup-maven", "4.5")], "mvn -B verify")

# 5 gradle: Groovy DSL, ext versions in dependencies.gradle, two modules, per-module lockfile, drift on mordant
def gradle():
    f = "gradle"; lk = "app/gradle.lockfile"
    d = [("koin", "io.insert-koin:koin-core", "3.4.3", True), ("mockk", "io.mockk:mockk", "1.13.5", True), ("mordant", "com.github.ajalt.mordant:mordant", "2.1.0", True),
         ("junit", "org.junit.jupiter:junit-jupiter-api", "5.9.3", True), ("mapstruct", "org.mapstruct:mapstruct", "1.5.5.Final", True),
         ("sqlite", "org.xerial:sqlite-jdbc", "3.42.0.0", True), ("wire", "com.squareup.wire:wire-runtime", "L", True), ("kotest", "io.kotest:kotest-assertions-core", "L", False)]
    cur = {n: row(f, "gradle", n, p, dr, lk, "3.0.0" if a == "mordant" else None) for a, n, p, dr in d}
    w("gradle/settings.gradle", "rootProject.name = 'harbor-tools'\ninclude ':app', ':lib'\n")
    w("gradle/dependencies.gradle", "ext.v = [\n" + ",\n".join("    %s: '%s'" % (a, "3.0.0" if a == "mordant" else cur[n]) for a, n, p, dr in d) + "\n]\n")
    w("gradle/build.gradle", "apply from: 'dependencies.gradle'\n// upgrade plan: koin 99.0 (unreleased)\nsubprojects {\n    repositories { mavenCentral() }\n}\n")
    gs = lambda xs: "".join("    implementation \"%s:${v.%s}\"\n" % (n, a) for a, n, p, dr in xs)
    w("gradle/app/build.gradle", "plugins { id 'java' }\n\ndependencies {\n" + gs(d[:4]) + "}\n")
    w("gradle/lib/build.gradle", "plugins { id 'java-library' }\n\ndependencies {\n" + gs(d[4:7]) + "}\n")
    w("gradle/" + lk, "# This is a Gradle generated file for dependency locking.\n" + "".join("%s:%s=compileClasspath,runtimeClasspath\n" % kv for kv in sorted(cur.items())) + "empty=\n")
    workflow(f, "wrapper.yml", [("gradle/wrapper-validation-action", "1.1.0")], "./gradlew build")

# 6 cargo: single crate, [target] + [dev-dependencies] tables, vendored crate, bare rust-toolchain file, drift on semver
def cargo():
    f = "cargo"
    d = [("ryu", row(f, "cargo", "ryu", "1.0.13", True, "Cargo.lock")), ("humantime", row(f, "cargo", "humantime", "2.1.0", True, "Cargo.lock")),
         ("fastrand", row(f, "cargo", "fastrand", "1.9.0", True, "Cargo.lock")), ("bytemuck", row(f, "cargo", "bytemuck", "1.13.1", True, "Cargo.lock")),
         ("semver", row(f, "cargo", "semver", "1.0.17", True, "Cargo.lock", "1.0.20")), ("dashmap", row(f, "cargo", "dashmap", "5.4.0", True, "Cargo.lock"))]
    dv = [("either", row(f, "cargo", "either", "L", True, "Cargo.lock"))]
    t = [("ahash", row(f, "cargo", "ahash", "L", False, "Cargo.lock"))]
    decl = {"semver": "1.0.20"}
    w("cargo/Cargo.toml", '[package]\nname = "reef-agent"\nversion = "0.9.0"\nedition = "2021"\n\n[dependencies]\n' + "".join('%s = "%s"\n' % (n, decl.get(n, v)) for n, v in d[:5]) +
      '\n[target.\'cfg(unix)\'.dependencies]\ndashmap = "%s"\n\n[dev-dependencies]\neither = "%s"\n# next: ryu 9.9 after release\n' % (d[5][1], dv[0][1]))
    w("cargo/Cargo.lock", "# This file is automatically @generated by Cargo.\nversion = 3\n\n" + '[[package]]\nname = "reef-agent"\nversion = "0.9.0"\n\n' + "".join(
        '[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n' % x for x in d + dv + t).rstrip("\n") + "\n")
    sv = row(f, "cargo", "strsim", "0.10.0", False, "vendor/strsim/Cargo.toml", vendored=True)
    w("cargo/vendor/strsim/Cargo.toml", '[package]\nname = "strsim"\nversion = "%s"\nedition = "2015"\nlicense = "MIT"\n' % sv)
    w("cargo/vendor/strsim/src/lib.rs", "//! Vendored copy of upstream strsim %s (MIT), do not edit.\npub fn hamming(a: &str, b: &str) -> usize { a.chars().zip(b.chars()).filter(|(x, y)| x != y).count() }\n" % sv)
    rt = row(f, "eol", "rust", "1.68.0", True, "rust-toolchain", eol_product="rust")
    w("cargo/rust-toolchain", rt + "\n")
    workflow(f, "audit.yml", [("EmbarkStudios/cargo-deny-action", "1.5.0"), ("taiki-e/install-action", "L")], "cargo deny check")

# 7 composer: root + nested modules/billing manifest/lock, PHP and Symfony EOL, php image
def composer():
    f = "composer"
    ro = [("guzzlehttp/psr7", row(f, "composer", "guzzlehttp/psr7", "2.5.0", True, "composer.lock")), ("symfony/http-foundation", row(f, "composer", "symfony/http-foundation", "v6.3.1", True, "composer.lock")),
          ("nikic/fast-route", row(f, "composer", "nikic/fast-route", "L", True, "composer.lock"))]
    bi = [("egulias/email-validator", row(f, "composer", "egulias/email-validator", "3.2.6", True, "modules/billing/composer.lock")),
          ("league/mime-type-detection", row(f, "composer", "league/mime-type-detection", "L", True, "modules/billing/composer.lock")),
          ("phpoption/phpoption", row(f, "composer", "phpoption/phpoption", "1.9.1", True, "modules/billing/composer.lock", "^1.10")),
          ("symfony/string", row(f, "composer", "symfony/string", "v6.3.0", True, "modules/billing/composer.lock"))]
    dev = [("fakerphp/faker", row(f, "composer", "fakerphp/faker", "v1.21.0", True, "modules/billing/composer.lock"))]
    php = row(f, "eol", "php", "8.0.30", True, "composer.json", eol_product="php")
    row(f, "eol", "symfony", "6.3.1", True, "composer.json", eol_product="symfony")
    pd = row(f, "docker", "php", "8.0.30", True, "Dockerfile", eol_product="php")
    w("composer/Dockerfile", "FROM php:%s\nCOPY . /var/www/html\n" % pd)
    decl = {"phpoption/phpoption": "^1.10"}
    c = lambda n, v: decl.get(n, "^" + v.lstrip("v"))
    pk = lambda xs: [{"name": n, "version": v, "type": "library"} for n, v in xs]
    lock = lambda p, d, dv: w(p, jd({"_readme": ["This file locks the dependencies of the project"], "content-hash": hashlib.md5(p.encode()).hexdigest(), "packages": pk(d), "packages-dev": pk(dv), "platform": {"php": ">=8.0"}}))
    w("composer/composer.json", jd({"name": "harbor/shop", "require": {"php": ">=8.0", **{n: c(n, v) for n, v in ro}}}))
    lock("composer/composer.lock", ro, [])
    w("composer/modules/billing/composer.json", jd({"name": "harbor/billing", "require": {n: c(n, v) for n, v in bi}, "require-dev": {n: c(n, v) for n, v in dev}}))
    lock("composer/modules/billing/composer.lock", bi, dev)
    workflow(f, "php.yml", [("webfactory/ssh-agent", "0.8.0")], "composer test")

# 8 monorepo: npm lock v2 app + Pipfile.lock service + go gateway + vendored npm copy + wordpress image
def mono():
    f = "monorepo"; ip = "apps/dashboard/package-lock.json"
    n_ = [("lit", row(f, "npm", "lit", "2.7.6", True, ip)), ("dompurify", row(f, "npm", "dompurify", "3.0.5", True, ip)), ("immer", row(f, "npm", "immer", "10.0.2", True, ip)),
          ("clsx", row(f, "npm", "clsx", "L", True, ip))]
    w("monorepo/apps/dashboard/package.json", jd({"name": "ledger-dashboard", "version": "0.2.0", "dependencies": {n: "^" + v for n, v in n_}}))
    pk = {"": {"name": "ledger-dashboard", "version": "0.2.0"}}
    pk.update({"node_modules/" + n: {"version": v, "integrity": "sha512-" + ph(n + v)} for n, v in n_})
    w("monorepo/" + ip, jd({"name": "ledger-dashboard", "lockfileVersion": 2, "requires": True, "packages": pk,
        "dependencies": {n: {"version": v} for n, v in n_}}))
    pp = "services/etl/Pipfile.lock"
    p_ = [("sortedcontainers", row(f, "pip", "sortedcontainers", "2.3.0", True, pp)), ("more-itertools", row(f, "pip", "more-itertools", "10.1.0", True, pp)),
          ("toolz", row(f, "pip", "toolz", "0.12.0", True, pp)), ("pendulum", row(f, "pip", "pendulum", "2.1.2", True, pp, ">=3.0"))]
    w("monorepo/services/etl/Pipfile", '[[source]]\nurl = "https://pypi.org/simple"\nname = "pypi"\n\n[packages]\n' + "".join('%s = "%s"\n' % (n, ">=3.0" if n == "pendulum" else "*") for n, v in p_))
    w("monorepo/" + pp, jd({"_meta": {"sources": [{"name": "pypi", "url": "https://pypi.org/simple"}]}, "default": {n: {"version": "==" + v, "hashes": ["sha256:" + hashlib.sha256((n + v).encode()).hexdigest()]} for n, v in p_}, "develop": {}}))
    g = "services/gateway/go.mod"
    g_ = [("github.com/rs/cors", row(f, "go", "github.com/rs/cors", "v1.9.0", True, g)), ("github.com/mitchellh/mapstructure", row(f, "go", "github.com/mitchellh/mapstructure", "L", True, g))]
    gi = [("github.com/andybalholm/brotli", row(f, "go", "github.com/andybalholm/brotli", "v1.0.5", False, g))]
    w("monorepo/" + g, "module example.com/ledger/gateway\n\ngo 1.21\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in g_) + "\t%s %s // indirect\n)\n" % gi[0])
    wp = row(f, "docker", "wordpress", "6.3.1", True, "docker-compose.yml", eol_product="wordpress")
    w("monorepo/docker-compose.yml", "services:\n  site:\n    image: wordpress:%s\n    ports:\n      - \"8000:80\"\n" % wp)
    workflow(f, "paths.yml", [("dorny/paths-filter", "2.11.1"), ("peter-evans/create-pull-request", "L")], "make test")
    vv = row(f, "npm", "yocto-queue", "1.0.0", False, "third_party/yocto-queue/package.json", vendored=True)
    w("monorepo/third_party/yocto-queue/package.json", jd({"name": "yocto-queue", "version": vv, "main": "index.js"}))
    w("monorepo/third_party/yocto-queue/index.js", "/**\n * Vendored copy of upstream yocto-queue@%s (MIT), do not edit.\n */\nmodule.exports = class Queue { constructor() { this.items = []; } enqueue(v) { this.items.push(v); } };\n" % vv)

if __name__ == "__main__":
    for fn in (npm, pip, go, maven, gradle, cargo, composer, mono):
        fn()
    os.makedirs(os.path.join(HERE, "truth"), exist_ok=True)
    for fx, rs in ROWS.items():
        json.dump(rs, open(os.path.join(HERE, "truth", fx + ".json"), "w"), indent=1)
        print(fx, "rows", len(rs), "outdated", sum(not r["decoy"] for r in rs), "decoy", sum(r["decoy"] for r in rs))
    json.dump(DRIFT, open(os.path.join(HERE, "drift.json"), "w"), indent=1)
