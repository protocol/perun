#!/usr/bin/env python3
"""Generate G5 set #3: 8 fixture repos + truth/*.json + drift.json under this directory.

Same truth schema and "latest" rule as set #2 (see ../snapshot.py); fresh packages not used in set #1 or #2. New shapes:
pnpm lockfile v9 single package, pip-compile requirements, go.mod only, maven properties, gradle catalog with bundles +
groovy DSL, cargo single crate, composer without dev block, npm workspaces (package-lock v3) with a vendored copy.
Numeric pre-release trap: npm `yaml` (latest stable 2.x, newer 3.0.0-N pre-releases exist; N numeric).
Decoys are pinned at the registry latest at build time. Hashes are deterministic placeholders.
Needs network. Run: python3 set3/build.py
"""
import base64, hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import snapshot as S

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


# 1 npm: pnpm lockfile v9, numeric pre-release trap (yaml), node EOL, mysql container
def npm():
    f = "npm"; ip = "pnpm-lock.yaml"
    d = [("yaml", row(f, "npm", "yaml", "2.3.4", True, ip, "^2.8.0")), ("zod", row(f, "npm", "zod", "3.22.4", True, ip)),
         ("pino", row(f, "npm", "pino", "8.19.0", True, ip)), ("cors", row(f, "npm", "cors", "L", True, ip))]
    t = [("sonic-boom", row(f, "npm", "sonic-boom", "3.8.0", False, ip)), ("thread-stream", row(f, "npm", "thread-stream", "2.4.1", False, ip)),
         ("safe-stable-stringify", row(f, "npm", "safe-stable-stringify", "L", False, ip))]
    decl = {"yaml": "^2.8.0"}
    w("npm/package.json", json.dumps({"name": "quill-gateway", "version": "1.4.0", "private": True, "packageManager": "pnpm@9.1.0",
        "dependencies": {n: decl.get(n, "^" + v) for n, v in d}}, indent=2) + "\n")
    w("npm/pnpm-lock.yaml", "lockfileVersion: '9.0'\n\nimporters:\n\n  .:\n    dependencies:\n" + "".join(
        "      %s:\n        specifier: %s\n        version: %s\n" % (n, decl.get(n, "^" + v), v) for n, v in d) +
        "\npackages:\n\n" + "".join("  %s@%s:\n    resolution: {integrity: sha512-%s}\n\n" % (n, v, ph(n + v)) for n, v in d + t) +
        "snapshots:\n\n" + "".join("  %s@%s: {}\n\n" % x for x in d + t))
    w("npm/.nvmrc", "18.19.1\n")
    row(f, "eol", "nodejs", "18.19.1", True, ".nvmrc", eol_product="nodejs")
    my = row(f, "docker", "mysql", "8.0.36", True, "Dockerfile", eol_product="mysql")
    w("npm/Dockerfile", "FROM mysql:%s\nCOPY schema.sql /docker-entrypoint-initdb.d/\n" % my)
    workflow(f, "ci.yml", [("actions/checkout", "3.6.0"), ("pnpm/action-setup", "L")], "pnpm test")

# 2 pip: pip-compile requirements.in/.txt with "# via", EOL python, ruby-free; mongo container
def pip():
    f = "pip"
    d = [("fastapi", row(f, "pip", "fastapi", "0.100.0", True, "requirements.txt")),
         ("sqlalchemy", row(f, "pip", "sqlalchemy", "1.4.49", True, "requirements.txt", ">=2.0")),
         ("gunicorn", row(f, "pip", "gunicorn", "21.2.0", True, "requirements.txt")),
         ("rich", row(f, "pip", "rich", "L", True, "requirements.txt"))]
    t = [("starlette", "fastapi", row(f, "pip", "starlette", "0.27.0", False, "requirements.txt")),
         ("pygments", "rich", row(f, "pip", "pygments", "2.15.1", False, "requirements.txt")),
         ("markdown-it-py", "rich", row(f, "pip", "markdown-it-py", "L", False, "requirements.txt"))]
    w("pip/requirements.in", "fastapi\nsqlalchemy>=2.0\ngunicorn\nrich\n")
    w("pip/requirements.txt", "#\n# This file is autogenerated by pip-compile with Python 3.9\n#\n" + "".join(
        "%s==%s\n    # via -r requirements.in\n" % (n, v) for n, v in d) + "".join(
        "%s==%s\n    # via %s\n" % (n, v, via) for n, via, v in t))
    w("pip/.python-version", "3.9.18\n")
    row(f, "eol", "python", "3.9.18", True, ".python-version", eol_product="python")
    mg = row(f, "docker", "mongo", "5.0.24", True, "docker/Dockerfile", eol_product="mongodb")
    w("pip/docker/Dockerfile", "FROM mongo:%s\nCOPY mongod.conf /etc/mongod.conf\n" % mg)

# 3 go: gorilla/mux service, go.mod with indirect block, EOL go + golang image, actions
def go():
    f = "go"
    dr = [("github.com/gorilla/mux", row(f, "go", "github.com/gorilla/mux", "v1.8.0", True, "go.mod")),
          ("github.com/urfave/cli/v2", row(f, "go", "github.com/urfave/cli/v2", "v2.25.7", True, "go.mod")),
          ("github.com/spf13/viper", row(f, "go", "github.com/spf13/viper", "v1.16.0", True, "go.mod", "go.sum has only v1.15.0")),
          ("github.com/sirupsen/logrus", row(f, "go", "github.com/sirupsen/logrus", "L", True, "go.mod"))]
    ind = [("go.uber.org/multierr", row(f, "go", "go.uber.org/multierr", "v1.10.0", False, "go.mod")),
           ("golang.org/x/oauth2", row(f, "go", "golang.org/x/oauth2", "v0.11.0", False, "go.mod")),
           ("github.com/fsnotify/fsnotify", row(f, "go", "github.com/fsnotify/fsnotify", "L", False, "go.mod"))]
    row(f, "eol", "go", "1.21", True, "go.mod", eol_product="go")
    w("go/go.mod", "module example.com/reefline/gatewayd\n\ngo 1.21\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in dr) + ")\n\nrequire (\n" +
      "".join("\t%s %s // indirect\n" % x for x in ind) + ")\n")
    w("go/go.sum", "".join("%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, "v1.15.0" if n.endswith("viper") else c, ph(n + c), n, "v1.15.0" if n.endswith("viper") else c, ph(n + c + "m")) for n, c in dr + ind))
    gl = row(f, "docker", "golang", "1.21.0", True, "Dockerfile", eol_product="go")
    w("go/Dockerfile", "FROM golang:%s\nWORKDIR /src\nCOPY . .\nRUN go build -o /gatewayd .\nENTRYPOINT [\"/gatewayd\"]\n" % gl)
    workflow(f, "build.yml", [("actions/checkout", "3.5.3"), ("actions/setup-go", "4.0.1"), ("golangci/golangci-lint-action", "L")], "go test ./...")

# 4 maven: properties + dependencyManagement transitive pins, EOL spring-boot parent
def maven():
    f = "maven"
    boot = row(f, "eol", "spring-boot", "3.1.5", True, "pom.xml", eol_product="spring-boot")
    d = [("org.apache.commons:commons-math3", row(f, "maven", "org.apache.commons:commons-math3", "3.5", True, "pom.xml")),
         ("com.zaxxer:HikariCP", row(f, "maven", "com.zaxxer:HikariCP", "5.0.1", True, "pom.xml")),
         ("org.mockito:mockito-core", row(f, "maven", "org.mockito:mockito-core", "4.11.0", True, "pom.xml")),
         ("ch.qos.logback:logback-classic", row(f, "maven", "ch.qos.logback:logback-classic", "L", True, "pom.xml"))]
    m = [("org.codehaus.plexus:plexus-utils", row(f, "maven", "org.codehaus.plexus:plexus-utils", "3.4.2", False, "pom.xml")),
         ("org.apache.commons:commons-pool2", row(f, "maven", "org.apache.commons:commons-pool2", "2.11.1", False, "pom.xml")),
         ("org.reactivestreams:reactive-streams", row(f, "maven", "org.reactivestreams:reactive-streams", "L", False, "pom.xml"))]
    dep = lambda n, v: "    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></dependency>\n" % (*n.split(":"), v)
    props = "".join("    <lib.%s.version>%s</lib.%s.version>\n" % (n.split(":")[1], v, n.split(":")[1]) for n, v in d)
    w("maven/pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n'
      '  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>%s</version></parent>\n'
      '  <groupId>example.com.reefline</groupId><artifactId>settlement-api</artifactId><version>1.0.0</version>\n'
      '  <properties>\n%s  </properties>\n  <dependencyManagement>\n    <dependencies>\n%s    </dependencies>\n  </dependencyManagement>\n  <dependencies>\n%s  </dependencies>\n</project>\n'
      % (boot, props, "".join(dep(n, v) for n, v in m),
         "".join("    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>${lib.%s.version}</version></dependency>\n" % (*n.split(":"), n.split(":")[1]) for n, v in d)))

# 5 gradle: version catalog with bundles + groovy DSL + lockfile
def gradle():
    f = "gradle"
    d = [("micrometer", "io.micrometer:micrometer-core", "1.10.5", True), ("moshi", "com.squareup.moshi:moshi", "1.14.0", True),
         ("csv", "org.apache.commons:commons-csv", "1.9.0", True), ("serialization", "org.jetbrains.kotlinx:kotlinx-serialization-json", "L", True)]
    t = [("org.reactivestreams:reactive-streams", "1.0.3"), ("org.hdrhistogram:HdrHistogram", "2.1.12"), ("io.micrometer:micrometer-commons", "1.10.5")]
    cur = {}
    for a, n, p, dr in d:
        cur[n] = row(f, "gradle", n, p, dr, "gradle.lockfile", "1.12.0" if a == "moshi" else None)
    for n, p in t:
        cur[n] = row(f, "gradle", n, p, False, "gradle.lockfile")
    w("gradle/gradle/libs.versions.toml", "[versions]\n" + "".join('%s = "%s"\n' % (a, "1.12.0" if a == "moshi" else cur[n]) for a, n, p, dr in d) +
      "\n[libraries]\n" + "".join('%s = { group = "%s", name = "%s", version.ref = "%s" }\n' % (a, *n.split(":"), a) for a, n, p, dr in d) +
      '\n[bundles]\nio = ["moshi", "csv", "serialization"]\n')
    w("gradle/build.gradle", "plugins {\n    id 'java-library'\n}\n\ndependencies {\n    implementation libs.micrometer\n    implementation libs.bundles.io\n}\n")
    w("gradle/gradle.lockfile", "# This is a Gradle generated file for dependency locking.\n" + "".join(
        "%s:%s=compileClasspath,runtimeClasspath\n" % kv for kv in sorted(cur.items())) + "empty=\n")
    workflow(f, "gradle.yml", [("actions/checkout", "3.5.0"), ("gradle/gradle-build-action", "L")], "./gradlew build")

# 6 cargo: single crate, drift on tracing, rust-toolchain via docker
def cargo():
    f = "cargo"
    d = [("tracing", row(f, "cargo", "tracing", "0.1.37", True, "Cargo.lock", "0.1.40")), ("rayon", row(f, "cargo", "rayon", "1.7.0", True, "Cargo.lock")),
         ("indexmap", row(f, "cargo", "indexmap", "1.9.3", True, "Cargo.lock")), ("itertools", row(f, "cargo", "itertools", "L", True, "Cargo.lock"))]
    t = [("once_cell", row(f, "cargo", "once_cell", "1.18.0", False, "Cargo.lock")), ("crossbeam-utils", row(f, "cargo", "crossbeam-utils", "0.8.16", False, "Cargo.lock")),
         ("hashbrown", row(f, "cargo", "hashbrown", "0.12.3", False, "Cargo.lock")), ("autocfg", row(f, "cargo", "autocfg", "L", False, "Cargo.lock"))]
    decl = {"tracing": "0.1.40"}
    w("cargo/Cargo.toml", '[package]\nname = "shoal-indexer"\nversion = "0.5.0"\nedition = "2021"\n\n[dependencies]\n' +
      "".join('%s = "%s"\n' % (n, decl.get(n, v)) for n, v in d))
    w("cargo/Cargo.lock", "# This file is automatically @generated by Cargo.\nversion = 3\n\n" +
      '[[package]]\nname = "shoal-indexer"\nversion = "0.5.0"\ndependencies = [\n' + "".join(' "%s",\n' % n for n, _ in d) + "]\n\n" + "".join(
          '[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n' % x for x in d + t))
    workflow(f, "rust.yml", [("actions/checkout", "3.6.0"), ("Swatinem/rust-cache", "L")], "cargo test")

# 7 composer: packages only (no dev), transitive rows, php docker
def composer():
    f = "composer"
    d = [("league/csv", row(f, "composer", "league/csv", "9.8.0", True, "composer.lock")),
         ("doctrine/dbal", row(f, "composer", "doctrine/dbal", "3.6.0", True, "composer.lock", "^4.0")),
         ("symfony/finder", row(f, "composer", "symfony/finder", "v5.4.0", True, "composer.lock")),
         ("ramsey/collection", row(f, "composer", "ramsey/collection", "L", True, "composer.lock"))]
    t = [("doctrine/deprecations", row(f, "composer", "doctrine/deprecations", "v1.0.0", False, "composer.lock")),
         ("psr/container", row(f, "composer", "psr/container", "1.1.1", False, "composer.lock")),
         ("psr/cache", row(f, "composer", "psr/cache", "L", False, "composer.lock"))]
    php = row(f, "eol", "php", "8.1.27", True, "composer.json", eol_product="php")
    pd = row(f, "docker", "php", "8.1.27", True, "Dockerfile", eol_product="php")
    w("composer/Dockerfile", "FROM php:%s-cli\nCOPY --from=composer:2 /usr/bin/composer /usr/bin/composer\n" % pd)
    decl = {"doctrine/dbal": "^4.0"}
    req = {"php": ">=8.1"}
    req.update({n: decl.get(n, "^" + v.lstrip("v")) for n, v in d})
    w("composer/composer.json", json.dumps({"name": "reefline/ledger-export", "require": req}, indent=4) + "\n")
    pk = lambda xs: [{"name": n, "version": v, "type": "library"} for n, v in xs]
    w("composer/composer.lock", json.dumps({"_readme": ["This file locks the dependencies of the project"], "content-hash": hashlib.md5(b"reefline").hexdigest(),
        "packages": pk(d + t), "packages-dev": [], "platform": {"php": req["php"]}}, indent=4) + "\n")

# 8 monorepo: npm workspaces (package-lock v3) + python service + vendored copy + actions + containers
def mono():
    f = "monorepo"; ip = "package-lock.json"
    d = [("react", row(f, "npm", "react", "17.0.2", True, ip)), ("fastify", row(f, "npm", "fastify", "4.24.0", True, ip, "^4.26.0")),
         ("prettier", row(f, "npm", "prettier", "L", True, ip))]
    t = [("scheduler", row(f, "npm", "scheduler", "0.20.2", False, ip)), ("loose-envify", row(f, "npm", "loose-envify", "L", False, ip))]
    decl = {"fastify": "^4.26.0"}
    w("monorepo/package.json", json.dumps({"name": "reefline-mono", "private": True, "workspaces": ["packages/*"]}, indent=2) + "\n")
    w("monorepo/packages/app/package.json", json.dumps({"name": "@reefline/app", "version": "0.1.0", "dependencies": {n: decl.get(n, "^" + v) for n, v in d}}, indent=2) + "\n")
    pk = {"": {"name": "reefline-mono", "workspaces": ["packages/*"]}, "packages/app": {"name": "@reefline/app", "version": "0.1.0",
          "dependencies": {n: decl.get(n, "^" + v) for n, v in d}}}
    for n, v in d + t:
        pk["node_modules/" + n] = {"version": v, "resolved": "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (n, n, v), "integrity": "sha512-" + ph(n + v)}
    w("monorepo/package-lock.json", json.dumps({"name": "reefline-mono", "lockfileVersion": 3, "requires": True, "packages": pk}, indent=2) + "\n")
    py = [("pyjwt", row(f, "pip", "pyjwt", "2.7.0", True, "services/auth/requirements.txt")), ("pytz", row(f, "pip", "pytz", "2023.3", True, "services/auth/requirements.txt")),
          ("attrs", row(f, "pip", "attrs", "L", False, "services/auth/requirements.txt"))]
    w("monorepo/services/auth/requirements.txt", "".join("%s==%s\n" % x for x in py))
    nd = row(f, "docker", "node", "18.19.1", True, "packages/app/Dockerfile", eol_product="nodejs")
    ng = row(f, "docker", "nginx", "1.24.0", True, "packages/app/Dockerfile", eol_product="nginx")
    w("monorepo/packages/app/Dockerfile", "FROM node:%s AS build\nWORKDIR /app\nCOPY . .\nRUN npm ci && npm run build\n\nFROM nginx:%s\nCOPY --from=build /app/dist /usr/share/nginx/html\n" % (nd, ng))
    workflow(f, "ci.yml", [("actions/checkout", "3.6.0"), ("actions/setup-node", "3.8.1"), ("actions/setup-python", "4.7.0"), ("docker/setup-buildx-action", "L")], "npm test --workspaces")
    vv = row(f, "npm", "is-odd", "2.0.0", False, "third_party/is-odd/package.json", vendored=True)
    w("monorepo/third_party/is-odd/package.json", json.dumps({"name": "is-odd", "version": vv, "main": "index.js"}, indent=2) + "\n")
    w("monorepo/third_party/is-odd/index.js", "/**\n * Vendored copy of upstream is-odd@%s (MIT), do not edit.\n */\nmodule.exports = n => Math.abs(n) %% 2 === 1;\n" % vv)

if __name__ == "__main__":
    for fn in (npm, pip, go, maven, gradle, cargo, composer, mono):
        fn()
    os.makedirs(os.path.join(HERE, "truth"), exist_ok=True)
    for fx, rs in ROWS.items():
        json.dump(rs, open(os.path.join(HERE, "truth", fx + ".json"), "w"), indent=1)
        print(fx, "rows", len(rs), "outdated", sum(not r["decoy"] for r in rs), "decoy", sum(r["decoy"] for r in rs))
    json.dump(DRIFT, open(os.path.join(HERE, "drift.json"), "w"), indent=1)
