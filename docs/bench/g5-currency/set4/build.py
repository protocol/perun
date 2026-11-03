#!/usr/bin/env python3
"""Generate G5 set #4: 8 fixture repos + truth/*.json + drift.json under this directory.

Same truth schema and "latest" rule as sets #2/#3 (see ../snapshot.py); every package, action and runtime name is new
versus sets #1-#3 except language runtimes (python, go, php) which are unavoidable. New shapes: yarn.lock v1, poetry.lock,
go.mod + docker-compose image, maven with a KEV/OSV-flagged pin, gradle Kotlin DSL + catalog + lockfile, cargo workspace
(two members, one lock), composer with a require-dev block, pnpm workspace (v9 lock, importers per package) + vendored copy.
New generic traps: (1) "fake latest" comments in manifests/Dockerfiles that advertise an unreleased newer version (not in
truth; a detector must take latest from the registry, not the file); (2) two-segment composer versions (psr/http-message
1.1 vs 2.0) and a four-segment latest (arrow-core 2.3.0.1).
KEV/OSV row: maven org.apache.struts:struts2-core pinned 2.3.31 carries a "vuln" object (OSV ids from api.osv.dev, KEV CVEs
from the CISA catalog), fetched at build time; snapshot.py ignores it.
Decoys are pinned at the registry latest at build time. Hashes are deterministic placeholders.
Needs network. GitHub API answers are cached under $TMPDIR/g5s4gh so reruns stay inside the 60/hr unauthenticated limit.
Run: python3 set4/build.py
"""
import base64, hashlib, json, os, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import snapshot as S

_get = S.get
def _cached(url, accept="application/json"):
    if "api.github.com" not in url:
        return _get(url, accept)
    d = os.path.join(os.environ.get("TMPDIR", "/tmp"), "g5s4gh"); os.makedirs(d, exist_ok=True)
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
    """Attach OSV ids (api.osv.dev) and KEV CVEs (CISA catalog) for a pinned version; asserts each CVE is in the KEV feed."""
    q = json.dumps({"package": {"name": name, "ecosystem": ecosystem}, "version": version}).encode()
    osv = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.osv.dev/v1/query", q, {"Content-Type": "application/json"}), timeout=30).read())
    ids = sorted(v["id"] for v in osv.get("vulns", []))
    kev = {v["cveID"] for v in json.loads(_get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"))["vulnerabilities"]}
    assert ids and all(c in kev for c in cves), (ids, cves)
    [r for r in ROWS[fx] if r["name"] == name][0]["vuln"] = {"osv": ids, "kev": sorted(cves)}

# 1 npm: yarn.lock v1, drift on dotenv, angular EOL, httpd container, fake-latest trap in Dockerfile
def npm():
    f = "npm"; ip = "yarn.lock"
    d = [("@angular/core", row(f, "npm", "@angular/core", "15.2.0", True, ip)), ("chalk", row(f, "npm", "chalk", "4.1.2", True, ip)),
         ("dotenv", row(f, "npm", "dotenv", "16.0.3", True, ip, "^16.4.0")), ("helmet", row(f, "npm", "helmet", "6.2.0", True, ip)),
         ("escape-html", row(f, "npm", "escape-html", "L", True, ip))]
    t = [("ansi-styles", row(f, "npm", "ansi-styles", "4.3.0", False, ip)), ("supports-color", row(f, "npm", "supports-color", "7.2.0", False, ip)),
         ("has-flag", row(f, "npm", "has-flag", "L", False, ip))]
    decl = {"dotenv": "^16.4.0"}
    rng = lambda n, v: decl.get(n, v if n == "@angular/core" else "^" + v)
    w("npm/package.json", json.dumps({"name": "tidepool-portal", "version": "2.1.0", "private": True,
        "dependencies": {n: rng(n, v) for n, v in d}}, indent=2) + "\n")
    w("npm/yarn.lock", "# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.\n# yarn lockfile v1\n\n\n" + "".join(
        '%s@%s:\n  version "%s"\n  resolved "https://registry.yarnpkg.com/%s/-/%s-%s.tgz#%s"\n  integrity sha512-%s\n\n' % (
            ('"%s"' % n if n.startswith("@") else n), rng(n, v) if (n, v) in d else "^" + v, v, n, n.split("/")[-1], v,
            hashlib.sha1((n + v).encode()).hexdigest(), ph(n + v)) for n, v in d + t))
    row(f, "eol", "angular", "15.2.0", True, "package.json", eol_product="angular")
    hd = row(f, "docker", "httpd", "2.4.57", True, "Dockerfile", eol_product="apache-http-server")
    w("npm/Dockerfile", "# TODO: move to httpd:9.9.9 once it is released\nFROM httpd:%s\nCOPY dist/ /usr/local/apache2/htdocs/\n" % hd)
    workflow(f, "triage.yml", [("actions/stale", "8.0.0"), ("actions/labeler", "L")], "yarn test")

# 2 pip: poetry.lock + pyproject, drift on orjson, EOL python, memcached container, fake-latest comment
def pip():
    f = "pip"
    d = [("tenacity", row(f, "pip", "tenacity", "8.2.2", True, "poetry.lock")), ("orjson", row(f, "pip", "orjson", "3.9.0", True, "poetry.lock", ">=3.10")),
         ("uvicorn", row(f, "pip", "uvicorn", "0.22.0", True, "poetry.lock")), ("colorama", row(f, "pip", "colorama", "L", True, "poetry.lock"))]
    t = [("h11", row(f, "pip", "h11", "0.14.0", False, "poetry.lock")), ("sniffio", row(f, "pip", "sniffio", "L", False, "poetry.lock"))]
    decl = {"orjson": ">=3.10"}
    w("pip/pyproject.toml", '[tool.poetry]\nname = "tidepool-worker"\nversion = "0.3.0"\n\n[tool.poetry.dependencies]\npython = "^3.8"\n' +
      "".join('%s = "%s"\n' % (n, decl.get(n, "^" + v)) for n, v in d) + "# next: tenacity 99.0 is planned, not released\n")
    w("pip/poetry.lock", "".join('[[package]]\nname = "%s"\nversion = "%s"\ndescription = ""\noptional = false\npython-versions = ">=3.8"\n\n' % x for x in d + t) +
      '[metadata]\nlock-version = "2.0"\npython-versions = "^3.8"\ncontent-hash = "%s"\n' % hashlib.sha256(b"tidepool").hexdigest())
    w("pip/.python-version", "3.8.18\n")
    row(f, "eol", "python", "3.8.18", True, ".python-version", eol_product="python")
    mc = row(f, "docker", "memcached", "1.6.17", True, "docker/Dockerfile", eol_product="memcached")
    w("pip/docker/Dockerfile", "FROM memcached:%s\nCMD [\"memcached\", \"-m\", \"64\"]\n" % mc)
    workflow(f, "release.yml", [("softprops/action-gh-release", "0.1.15")], "poetry build")

# 3 go: fiber service, go.mod + indirect block, EOL go, haproxy image in compose, drift via go.sum
def go():
    f = "go"
    dr = [("github.com/gofiber/fiber/v2", row(f, "go", "github.com/gofiber/fiber/v2", "v2.40.0", True, "go.mod")),
          ("github.com/hashicorp/go-retryablehttp", row(f, "go", "github.com/hashicorp/go-retryablehttp", "v0.7.1", True, "go.mod", "go.sum has only v0.7.0")),
          ("github.com/go-playground/validator/v10", row(f, "go", "github.com/go-playground/validator/v10", "v10.14.0", True, "go.mod")),
          ("github.com/google/go-cmp", row(f, "go", "github.com/google/go-cmp", "L", True, "go.mod"))]
    ind = [("github.com/valyala/fasthttp", row(f, "go", "github.com/valyala/fasthttp", "v1.47.0", False, "go.mod")),
           ("github.com/pelletier/go-toml/v2", row(f, "go", "github.com/pelletier/go-toml/v2", "v2.0.8", False, "go.mod")),
           ("github.com/klauspost/compress", row(f, "go", "github.com/klauspost/compress", "L", False, "go.mod"))]
    row(f, "eol", "go", "1.20", True, "go.mod", eol_product="go")
    w("go/go.mod", "module example.com/tidepool/edged\n\ngo 1.20\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in dr) + ")\n\nrequire (\n" +
      "".join("\t%s %s // indirect\n" % x for x in ind) + ")\n")
    w("go/go.sum", "".join("%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, "v0.7.0" if n.endswith("retryablehttp") else c, ph(n + c), n, "v0.7.0" if n.endswith("retryablehttp") else c, ph(n + c + "m")) for n, c in dr + ind))
    hp = row(f, "docker", "haproxy", "2.8.3", True, "docker-compose.yml", eol_product="haproxy")
    w("go/docker-compose.yml", "services:\n  lb:\n    image: haproxy:%s\n    ports:\n      - \"8080:8080\"\n" % hp)
    workflow(f, "image.yml", [("docker/login-action", "2.2.0")], "go test ./...")

# 4 maven: properties, KEV/OSV pin (struts2-core 2.3.31), EOL tomcat, tomcat image
def maven():
    f = "maven"
    tc = row(f, "eol", "tomcat", "9.0.80", True, "pom.xml", eol_product="tomcat")
    d = [("org.apache.struts:struts2-core", row(f, "maven", "org.apache.struts:struts2-core", "2.3.31", True, "pom.xml")),
         ("org.apache.poi:poi", row(f, "maven", "org.apache.poi:poi", "4.1.2", True, "pom.xml")),
         ("org.hibernate.validator:hibernate-validator", row(f, "maven", "org.hibernate.validator:hibernate-validator", "6.2.5.Final", True, "pom.xml")),
         ("org.ehcache:ehcache", row(f, "maven", "org.ehcache:ehcache", "L", True, "pom.xml"))]
    vuln(f, "Maven", "org.apache.struts:struts2-core", "2.3.31", ["CVE-2017-5638"])
    m = [("org.apache.xmlbeans:xmlbeans", row(f, "maven", "org.apache.xmlbeans:xmlbeans", "3.1.0", False, "pom.xml")),
         ("org.glassfish:jakarta.el", row(f, "maven", "org.glassfish:jakarta.el", "L", False, "pom.xml"))]
    dep = lambda n, v: "    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></dependency>\n" % (*n.split(":"), v)
    w("maven/pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n'
      '  <groupId>example.com.tidepool</groupId><artifactId>reports-web</artifactId><version>3.2.0</version><packaging>war</packaging>\n'
      '  <properties>\n    <tomcat.version>%s</tomcat.version>\n%s  </properties>\n  <dependencyManagement>\n    <dependencies>\n%s    </dependencies>\n  </dependencyManagement>\n  <dependencies>\n%s  </dependencies>\n</project>\n'
      % (tc, "".join("    <lib.%s.version>%s</lib.%s.version>\n" % (n.split(":")[1], v, n.split(":")[1]) for n, v in d),
         "".join(dep(n, v) for n, v in m),
         "".join("    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>${lib.%s.version}</version></dependency>\n" % (*n.split(":"), n.split(":")[1]) for n, v in d)))
    td = row(f, "docker", "tomcat", "9.0.80", True, "Dockerfile", eol_product="tomcat")
    w("maven/Dockerfile", "FROM tomcat:%s\nCOPY target/reports-web.war /usr/local/tomcat/webapps/ROOT.war\n" % td)
    workflow(f, "maven.yml", [("actions/setup-java", "3.12.0")], "mvn -B verify")

# 5 gradle: Kotlin DSL + catalog + lockfile + gradle.properties drift
def gradle():
    f = "gradle"
    d = [("ktor", "io.ktor:ktor-server-core", "2.3.2", True), ("exposed", "org.jetbrains.exposed:exposed-core", "0.41.1", True),
         ("clikt", "com.github.ajalt.clikt:clikt", "3.5.2", True), ("arrow", "io.arrow-kt:arrow-core", "1.2.0", True),
         ("logging", "io.github.oshai:kotlin-logging", "L", True)]
    t = [("org.jetbrains.kotlin:kotlin-stdlib", "1.8.22"), ("io.ktor:ktor-utils", "2.3.2")]
    cur = {}
    for a, n, p, dr in d:
        cur[n] = row(f, "gradle", n, p, dr, "gradle.lockfile", "4.0.0" if a == "clikt" else None)
    for n, p in t:
        cur[n] = row(f, "gradle", n, p, False, "gradle.lockfile")
    w("gradle/gradle/libs.versions.toml", "[versions]\n" + "".join('%s = "%s"\n' % (a, "4.0.0" if a == "clikt" else cur[n]) for a, n, p, dr in d) +
      "\n[libraries]\n" + "".join('%s = { module = "%s", version.ref = "%s" }\n' % (a, n, a) for a, n, p, dr in d))
    w("gradle/build.gradle.kts", 'plugins {\n    kotlin("jvm") version "1.8.22"\n}\n\ndependencies {\n' + "".join(
        "    implementation(libs.%s)\n" % a for a, n, p, dr in d) + "    // upgrade plan: ktor 9.0.0 (unreleased)\n}\n")
    w("gradle/gradle.lockfile", "# This is a Gradle generated file for dependency locking.\n" + "".join(
        "%s:%s=compileClasspath,runtimeClasspath\n" % kv for kv in sorted(cur.items())) + "empty=\n")
    workflow(f, "gradle.yml", [("docker/metadata-action", "4.6.0")], "./gradlew build")

# 6 cargo: workspace (2 members, one lock), drift on smallvec, rust toolchain EOL + image
def cargo():
    f = "cargo"
    d = [("bitflags", row(f, "cargo", "bitflags", "1.3.2", True, "Cargo.lock")), ("tempfile", row(f, "cargo", "tempfile", "3.6.0", True, "Cargo.lock")),
         ("smallvec", row(f, "cargo", "smallvec", "1.10.0", True, "Cargo.lock", "1.13.0")), ("scopeguard", row(f, "cargo", "scopeguard", "L", True, "Cargo.lock"))]
    t = [("lock_api", row(f, "cargo", "lock_api", "0.4.10", False, "Cargo.lock")), ("parking_lot", row(f, "cargo", "parking_lot", "0.12.1", False, "Cargo.lock")),
         ("cfg-if", row(f, "cargo", "cfg-if", "L", False, "Cargo.lock"))]
    decl = {"smallvec": "1.13.0"}
    w("cargo/Cargo.toml", '[workspace]\nmembers = ["crates/core", "crates/cli"]\nresolver = "2"\n')
    w("cargo/crates/core/Cargo.toml", '[package]\nname = "tern-core"\nversion = "0.2.0"\nedition = "2021"\n\n[dependencies]\n' +
      "".join('%s = "%s"\n' % (n, decl.get(n, v)) for n, v in d[:3]))
    w("cargo/crates/cli/Cargo.toml", '[package]\nname = "tern-cli"\nversion = "0.2.0"\nedition = "2021"\n\n[dependencies]\ntern-core = { path = "../core" }\n%s = "%s"\n# bump scopeguard to 9.9.9 after release\n' % (d[3][0], d[3][1]))
    w("cargo/Cargo.lock", "# This file is automatically @generated by Cargo.\nversion = 3\n\n" +
      '[[package]]\nname = "tern-cli"\nversion = "0.2.0"\ndependencies = [\n "tern-core",\n "scopeguard",\n]\n\n'
      '[[package]]\nname = "tern-core"\nversion = "0.2.0"\ndependencies = [\n' + "".join(' "%s",\n' % n for n, _ in d[:3]) + "]\n\n" + "".join(
          '[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n' % x for x in d + t))
    rt = row(f, "eol", "rust", "1.70.0", True, "rust-toolchain.toml", eol_product="rust")
    w("cargo/rust-toolchain.toml", '[toolchain]\nchannel = "%s"\n' % rt)
    rd = row(f, "docker", "rust", "1.70.0", True, "Dockerfile", eol_product="rust")
    w("cargo/Dockerfile", "FROM rust:%s\nWORKDIR /src\nCOPY . .\nRUN cargo build --release\n" % rd)
    workflow(f, "pages.yml", [("peaceiris/actions-gh-pages", "3.9.3")], "cargo doc")

# 7 composer: require + require-dev, 2-segment versions, drift on commonmark, mariadb image
def composer():
    f = "composer"
    d = [("laminas/laminas-diactoros", row(f, "composer", "laminas/laminas-diactoros", "2.25.2", True, "composer.lock")),
         ("league/commonmark", row(f, "composer", "league/commonmark", "2.4.0", True, "composer.lock", "^2.5")),
         ("psr/http-message", row(f, "composer", "psr/http-message", "1.1", True, "composer.lock")),
         ("psr/clock", row(f, "composer", "psr/clock", "L", True, "composer.lock"))]
    dev = [("symfony/process", row(f, "composer", "symfony/process", "v5.4.0", True, "composer.lock"))]
    t = [("brick/math", row(f, "composer", "brick/math", "0.11.0", False, "composer.lock")), ("league/config", row(f, "composer", "league/config", "L", False, "composer.lock"))]
    php = row(f, "eol", "php", "8.0.30", True, "composer.json", eol_product="php")
    md = row(f, "docker", "mariadb", "10.6.16", True, "Dockerfile", eol_product="mariadb")
    w("composer/Dockerfile", "FROM mariadb:%s\nCOPY init.sql /docker-entrypoint-initdb.d/\n" % md)
    decl = {"league/commonmark": "^2.5"}
    c = lambda n, v: decl.get(n, "^" + v.lstrip("v"))
    w("composer/composer.json", json.dumps({"name": "tidepool/docs-site", "require": {"php": ">=8.0", **{n: c(n, v) for n, v in d}},
        "require-dev": {n: c(n, v) for n, v in dev}}, indent=4) + "\n")
    pk = lambda xs: [{"name": n, "version": v, "type": "library"} for n, v in xs]
    w("composer/composer.lock", json.dumps({"_readme": ["This file locks the dependencies of the project"], "content-hash": hashlib.md5(b"tidepool").hexdigest(),
        "packages": pk(d + t), "packages-dev": pk(dev), "platform": {"php": ">=8.0"}}, indent=4) + "\n")
    workflow(f, "qemu.yml", [("docker/setup-qemu-action", "2.2.0")], "composer test")

# 8 monorepo: pnpm workspace (v9 lock, 2 importers) + python service + vendored copy + actions + containers + ruby EOL
def mono():
    f = "monorepo"; ip = "pnpm-lock.yaml"
    d = [("date-fns", row(f, "npm", "date-fns", "2.30.0", True, ip)), ("zustand", row(f, "npm", "zustand", "4.3.8", True, ip, "^4.5.0")),
         ("rxjs", row(f, "npm", "rxjs", "7.8.1", True, ip)), ("ee-first", row(f, "npm", "ee-first", "L", True, ip))]
    decl = {"zustand": "^4.5.0"}
    sp = lambda n, v: decl.get(n, "^" + v)
    w("monorepo/package.json", json.dumps({"name": "tidepool-mono", "private": True, "packageManager": "pnpm@9.1.0"}, indent=2) + "\n")
    w("monorepo/pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    for pkg, grp in (("web", d[:2]), ("sync", d[2:])):
        w("monorepo/packages/%s/package.json" % pkg, json.dumps({"name": "@tidepool/" + pkg, "version": "0.1.0", "dependencies": {n: sp(n, v) for n, v in grp}}, indent=2) + "\n")
    imp = "".join("  packages/%s:\n    dependencies:\n%s" % (pkg, "".join("      %s:\n        specifier: %s\n        version: %s\n" % (n, sp(n, v), v) for n, v in grp))
                  for pkg, grp in (("web", d[:2]), ("sync", d[2:])))
    w("monorepo/pnpm-lock.yaml", "lockfileVersion: '9.0'\n\nimporters:\n\n" + imp + "\npackages:\n\n" + "".join(
        "  %s@%s:\n    resolution: {integrity: sha512-%s}\n\n" % (n, v, ph(n + v)) for n, v in d) + "snapshots:\n\n" + "".join("  %s@%s: {}\n\n" % x for x in d))
    py = [("tqdm", row(f, "pip", "tqdm", "4.65.0", True, "services/ingest/requirements.txt")), ("markupsafe", row(f, "pip", "markupsafe", "2.1.3", True, "services/ingest/requirements.txt")),
          ("six", row(f, "pip", "six", "L", False, "services/ingest/requirements.txt"))]
    w("monorepo/services/ingest/requirements.txt", "".join("%s==%s\n" % x for x in py))
    rb = row(f, "eol", "ruby", "3.1.4", True, "tools/.ruby-version", eol_product="ruby")
    w("monorepo/tools/.ruby-version", rb + "\n")
    rq = row(f, "docker", "rabbitmq", "3.12.0", True, "docker/Dockerfile", eol_product="rabbitmq")
    w("monorepo/docker/Dockerfile", "FROM rabbitmq:%s\nRUN rabbitmq-plugins enable --offline rabbitmq_management\n" % rq)
    workflow(f, "ci.yml", [("actions/github-script", "6.4.1"), ("codecov/codecov-action", "L")], "pnpm -r test")
    vv = row(f, "npm", "array-flatten", "1.1.1", False, "third_party/array-flatten/package.json", vendored=True)
    w("monorepo/third_party/array-flatten/package.json", json.dumps({"name": "array-flatten", "version": vv, "main": "index.js"}, indent=2) + "\n")
    w("monorepo/third_party/array-flatten/index.js", "/**\n * Vendored copy of upstream array-flatten@%s (MIT), do not edit.\n */\nmodule.exports = a => a.flat(Infinity);\n" % vv)

if __name__ == "__main__":
    for fn in (npm, pip, go, maven, gradle, cargo, composer, mono):
        fn()
    os.makedirs(os.path.join(HERE, "truth"), exist_ok=True)
    for fx, rs in ROWS.items():
        json.dump(rs, open(os.path.join(HERE, "truth", fx + ".json"), "w"), indent=1)
        print(fx, "rows", len(rs), "outdated", sum(not r["decoy"] for r in rs), "decoy", sum(r["decoy"] for r in rs))
    json.dump(DRIFT, open(os.path.join(HERE, "drift.json"), "w"), indent=1)
