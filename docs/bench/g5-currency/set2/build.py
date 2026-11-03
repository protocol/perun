#!/usr/bin/env python3
"""Generate G5 set #2: 8 fixture repos + truth/*.json + drift.json under this directory.

Same truth schema and "latest" rule as set #1 (see ../build.py and ../snapshot.py); different fictional apps, mostly
different packages, different manifest shapes (yarn, poetry, pnpm workspace, version catalog, cargo workspace, pom
properties). Decoys are pinned at the registry latest at build time. Hashes are deterministic placeholders.
Needs network. Run: python3 set2/build.py
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

# 1 npm: yarn v1 lockfile, redis container, .node-version
def npm():
    f = "npm"
    d = [("axios", row(f, "npm", "axios", "0.27.2", True, "yarn.lock")),
         ("moment", row(f, "npm", "moment", "2.29.1", True, "yarn.lock", "^2.30.0")),
         ("commander", row(f, "npm", "commander", "9.4.1", True, "yarn.lock")),
         ("picocolors", row(f, "npm", "picocolors", "L", True, "yarn.lock"))]
    t = [("follow-redirects", row(f, "npm", "follow-redirects", "1.15.2", False, "yarn.lock")),
         ("form-data", row(f, "npm", "form-data", "4.0.0", False, "yarn.lock")),
         ("proxy-from-env", row(f, "npm", "proxy-from-env", "L", False, "yarn.lock"))]
    decl = {"moment": "^2.30.0"}
    w("npm/package.json", json.dumps({"name": "nimbus-portal", "version": "2.3.0", "private": True,
        "dependencies": {n: decl.get(n, "^" + v) for n, v in d}, "engines": {"node": ">=16"}}, indent=2) + "\n")
    w("npm/yarn.lock", "# yarn lockfile v1\n\n\n" + "".join(
        '%s@%s:\n  version "%s"\n  resolved "https://registry.yarnpkg.com/%s/-/%s-%s.tgz"\n\n' % (
            n, "^" + decl.get(n, v).lstrip("^"), v, n, n, v) for n, v in d + t))
    w("npm/.node-version", "16.20.2\n")
    row(f, "eol", "nodejs", "16.20.2", True, ".node-version", eol_product="nodejs")
    rd = row(f, "docker", "redis", "6.2.14", True, "Dockerfile", eol_product="redis")
    w("npm/Dockerfile", "FROM redis:%s\nCOPY redis.conf /usr/local/etc/redis/redis.conf\n" % rd)

# 2 pip: poetry (pyproject + poetry.lock), postgres container
def pip():
    f = "pip"
    d = [("django", row(f, "pip", "django", "4.2.7", True, "poetry.lock", "^5.0")),
         ("celery", row(f, "pip", "celery", "5.2.7", True, "poetry.lock")),
         ("httpx", row(f, "pip", "httpx", "0.24.1", True, "poetry.lock")),
         ("pydantic", row(f, "pip", "pydantic", "L", True, "poetry.lock"))]
    t = [("sqlparse", row(f, "pip", "sqlparse", "0.4.3", False, "poetry.lock")),
         ("kombu", row(f, "pip", "kombu", "5.2.4", False, "poetry.lock")),
         ("anyio", row(f, "pip", "anyio", "3.6.2", False, "poetry.lock")),
         ("annotated-types", row(f, "pip", "annotated-types", "L", False, "poetry.lock"))]
    decl = {"django": "^5.0"}
    w("pip/pyproject.toml", '[tool.poetry]\nname = "harbor-ledger"\nversion = "0.9.0"\ndescription = "Example ledger service"\n\n'
      '[tool.poetry.dependencies]\npython = "^3.8"\n' + "".join(
          '%s = "%s"\n' % (n, decl.get(n, "^" + v)) for n, v in d) + '\n[build-system]\nrequires = ["poetry-core"]\nbuild-backend = "poetry.core.masonry.api"\n')
    w("pip/poetry.lock", "# This file is automatically @generated by Poetry.\n\n" + "".join(
        '[[package]]\nname = "%s"\nversion = "%s"\ndescription = ""\noptional = false\npython-versions = ">=3.8"\n\n' % (n, v) for n, v in d + t) +
      '[metadata]\nlock-version = "2.0"\npython-versions = "^3.8"\ncontent-hash = "%s"\n' % hashlib.sha256(b"harbor").hexdigest())
    w("pip/.python-version", "3.8.18\n")
    row(f, "eol", "python", "3.8.18", True, ".python-version", eol_product="python")
    pg = row(f, "docker", "postgres", "13.14", True, "docker/db.Dockerfile", eol_product="postgresql")
    w("pip/docker/db.Dockerfile", "FROM postgres:%s\nCOPY init.sql /docker-entrypoint-initdb.d/\n" % pg)

# 3 go: echo service, replace directive, actions, containers
def go():
    f = "go"
    dr = [("github.com/labstack/echo/v4", row(f, "go", "github.com/labstack/echo/v4", "v4.9.0", True, "go.mod")),
          ("github.com/jackc/pgx/v5", row(f, "go", "github.com/jackc/pgx/v5", "v5.3.1", True, "go.mod")),
          ("github.com/redis/go-redis/v9", row(f, "go", "github.com/redis/go-redis/v9", "v9.0.5", True, "go.mod")),
          ("github.com/golang-jwt/jwt/v4", row(f, "go", "github.com/golang-jwt/jwt/v4", "v4.4.0", True, "go.mod")),
          ("github.com/prometheus/client_golang", row(f, "go", "github.com/prometheus/client_golang", "L", True, "go.mod")),
          ("go.uber.org/zap", row(f, "go", "go.uber.org/zap", "L", True, "go.mod"))]
    ind = [("golang.org/x/crypto", row(f, "go", "golang.org/x/crypto", "v0.14.0", False, "go.mod", "go.sum has only v0.12.0")),
           ("golang.org/x/text", row(f, "go", "golang.org/x/text", "v0.9.0", False, "go.mod")),
           ("golang.org/x/sync", row(f, "go", "golang.org/x/sync", "L", False, "go.mod"))]
    row(f, "eol", "go", "1.20", True, "go.mod", eol_product="go")
    out = "module example.com/tidepool/ledgerd\n\ngo 1.20\n\nrequire (\n" + "".join("\t%s %s\n" % x for x in dr) + ")\n\nrequire (\n" + \
          "".join("\t%s %s // indirect\n" % x for x in ind) + ")\n\nreplace example.com/tidepool/shared => ../shared\n"
    w("go/go.mod", out)
    w("go/go.sum", "".join("%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, "v0.12.0" if n.endswith("x/crypto") else c, ph(n + c), n, "v0.12.0" if n.endswith("x/crypto") else c, ph(n + c + "m")) for n, c in dr + ind))
    gl = row(f, "docker", "golang", "1.20.14", True, "build/Dockerfile", eol_product="go")
    al = row(f, "docker", "alpine", "3.17.9", True, "build/Dockerfile", eol_product="alpine")
    w("go/build/Dockerfile", "FROM golang:%s AS b\nWORKDIR /src\nCOPY . .\nRUN go build -o /ledgerd ./cmd/ledgerd\n\nFROM alpine:%s\nCOPY --from=b /ledgerd /ledgerd\nENTRYPOINT [\"/ledgerd\"]\n" % (gl, al))
    workflow(f, "test.yml", [("actions/checkout", "4.1.0"), ("actions/setup-go", "4.1.0"), ("docker/build-push-action", "L")], "go test ./...")

# 4 maven: pom with <properties> and dependencyManagement pins (transitive), no lockfile
def maven():
    f = "maven"
    boot = row(f, "eol", "spring-boot", "2.7.18", True, "pom.xml", eol_product="spring-boot")
    d = [("org.apache.logging.log4j:log4j-core", row(f, "maven", "org.apache.logging.log4j:log4j-core", "2.17.0", True, "pom.xml")),
         ("org.apache.httpcomponents.client5:httpclient5", row(f, "maven", "org.apache.httpcomponents.client5:httpclient5", "5.2.1", True, "pom.xml")),
         ("com.squareup.okhttp3:okhttp", row(f, "maven", "com.squareup.okhttp3:okhttp", "4.9.3", True, "pom.xml")),
         ("org.jsoup:jsoup", row(f, "maven", "org.jsoup:jsoup", "L", True, "pom.xml"))]
    m = [("commons-beanutils:commons-beanutils", row(f, "maven", "commons-beanutils:commons-beanutils", "1.9.4", False, "pom.xml")),
         ("org.apache.commons:commons-collections4", row(f, "maven", "org.apache.commons:commons-collections4", "4.4", False, "pom.xml")),
         ("commons-codec:commons-codec", row(f, "maven", "commons-codec:commons-codec", "L", False, "pom.xml"))]
    dep = lambda n, v: "    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></dependency>\n" % (*n.split(":"), v)
    props = "".join("    <v%d>%s</v%d>\n" % (i, v, i) for i, (n, v) in enumerate(d))
    w("maven/pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n'
      '  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>%s</version></parent>\n'
      '  <groupId>example.com.tidepool</groupId><artifactId>reporting-batch</artifactId><version>3.1.0</version>\n'
      '  <properties>\n%s  </properties>\n  <dependencyManagement>\n    <dependencies>\n%s    </dependencies>\n  </dependencyManagement>\n  <dependencies>\n%s  </dependencies>\n</project>\n'
      % (boot, props, "".join(dep(n, v) for n, v in m),
         "".join("    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>${v%d}</version></dependency>\n" % (*n.split(":"), i) for i, (n, v) in enumerate(d))))

# 5 gradle: version catalog (libs.versions.toml) + kts + lockfile
def gradle():
    f = "gradle"
    d = [("retrofit", "com.squareup.retrofit2:retrofit", "2.9.0", True), ("gson", "com.google.code.gson:gson", "2.8.9", True),
         ("coroutines", "org.jetbrains.kotlinx:kotlinx-coroutines-core", "1.6.4", True), ("annotations", "org.jetbrains:annotations", "L", True)]
    t = [("com.squareup.okio:okio", "3.2.0"), ("io.netty:netty-codec-http", "4.1.94.Final"), ("org.apache.commons:commons-compress", "1.21")]
    cur = {}
    for a, n, p, dr in d:
        cur[n] = row(f, "gradle", n, p, dr, "gradle.lockfile", "2.10.1" if a == "gson" else None)
    for n, p in t:
        cur[n] = row(f, "gradle", n, p, False, "gradle.lockfile")
    w("gradle/gradle/libs.versions.toml", "[versions]\n" + "".join('%s = "%s"\n' % (a, "2.10.1" if a == "gson" else cur[n]) for a, n, p, dr in d) +
      "\n[libraries]\n" + "".join('%s = { module = "%s", version.ref = "%s" }\n' % (a, n, a) for a, n, p, dr in d))
    w("gradle/build.gradle.kts", 'plugins {\n    kotlin("jvm") version "1.8.10"\n}\n\ndependencies {\n' + "".join("    implementation(libs.%s)\n" % a for a, *_ in d) + "}\n")
    w("gradle/gradle.lockfile", "# This is a Gradle generated file for dependency locking.\n" + "".join(
        "%s:%s=compileClasspath,runtimeClasspath\n" % kv for kv in sorted(cur.items())) + "empty=\n")

# 6 cargo: workspace with two members, workspace.dependencies, drift on reqwest
def cargo():
    f = "cargo"
    d = [("axum", row(f, "cargo", "axum", "0.6.20", True, "Cargo.lock")), ("clap", row(f, "cargo", "clap", "4.1.0", True, "Cargo.lock")),
         ("reqwest", row(f, "cargo", "reqwest", "0.11.18", True, "Cargo.lock", "0.12")), ("chrono", row(f, "cargo", "chrono", "L", True, "Cargo.lock")),
         ("thiserror", row(f, "cargo", "thiserror", "L", True, "Cargo.lock"))]
    t = [("hyper", row(f, "cargo", "hyper", "0.14.27", False, "Cargo.lock")), ("openssl", row(f, "cargo", "openssl", "0.10.55", False, "Cargo.lock")),
         ("bytes", row(f, "cargo", "bytes", "1.4.0", False, "Cargo.lock")), ("base64", row(f, "cargo", "base64", "0.21.0", False, "Cargo.lock"))]
    decl = {"reqwest": "0.12"}
    w("cargo/Cargo.toml", '[workspace]\nmembers = ["crates/api", "crates/core"]\nresolver = "2"\n\n[workspace.dependencies]\n' +
      "".join('%s = "%s"\n' % (n, decl.get(n, v)) for n, v in d))
    for c, names in (("api", ["axum", "clap", "reqwest"]), ("core", ["chrono", "thiserror"])):
        w("cargo/crates/%s/Cargo.toml" % c, '[package]\nname = "kelp-%s"\nversion = "0.2.0"\nedition = "2021"\n\n[dependencies]\n' % c + "".join("%s = { workspace = true }\n" % n for n in names))
    w("cargo/Cargo.lock", "# This file is automatically @generated by Cargo.\nversion = 3\n\n" +
      '[[package]]\nname = "kelp-api"\nversion = "0.2.0"\ndependencies = [\n "axum",\n "clap",\n "reqwest",\n "kelp-core",\n]\n\n'
      '[[package]]\nname = "kelp-core"\nversion = "0.2.0"\ndependencies = [\n "chrono",\n "thiserror",\n]\n\n' + "".join(
          '[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n' % x for x in d + t))
    workflow(f, "rust.yml", [("actions/checkout", "3.5.0"), ("actions/cache", "L")], "cargo test --workspace")

# 7 composer: packages + packages-dev, php constraint
def composer():
    f = "composer"
    d = [("monolog/monolog", row(f, "composer", "monolog/monolog", "2.8.0", True, "composer.lock")),
         ("symfony/console", row(f, "composer", "symfony/console", "v5.4.0", True, "composer.lock")),
         ("twig/twig", row(f, "composer", "twig/twig", "v3.4.0", True, "composer.lock", "^3.14")),
         ("league/flysystem", row(f, "composer", "league/flysystem", "2.5.0", True, "composer.lock")),
         ("ramsey/uuid", row(f, "composer", "ramsey/uuid", "L", True, "composer.lock"))]
    t = [("psr/log", row(f, "composer", "psr/log", "1.1.4", False, "composer.lock")),
         ("symfony/deprecation-contracts", row(f, "composer", "symfony/deprecation-contracts", "v2.5.1", False, "composer.lock")),
         ("symfony/polyfill-mbstring", row(f, "composer", "symfony/polyfill-mbstring", "L", False, "composer.lock"))]
    dev = [("phpunit/phpunit", row(f, "composer", "phpunit/phpunit", "9.5.0", True, "composer.lock"))]
    php = row(f, "eol", "php", "8.0.30", True, "composer.json", eol_product="php")
    decl = {"twig/twig": "^3.14"}
    req = {"php": ">=" + ".".join(php.split(".")[:2])}
    req.update({n: decl.get(n, "^" + v) for n, v in d})
    w("composer/composer.json", json.dumps({"name": "tidepool/storefront", "require": req, "require-dev": {"phpunit/phpunit": "^9.5"}}, indent=4) + "\n")
    pk = lambda xs: [{"name": n, "version": v, "type": "library"} for n, v in xs]
    w("composer/composer.lock", json.dumps({"_readme": ["This file locks the dependencies of the project"], "content-hash": hashlib.md5(b"tidepool").hexdigest(),
        "packages": pk(d + t), "packages-dev": pk(dev), "platform": {"php": req["php"]}}, indent=4) + "\n")

# 8 monorepo: pnpm workspace + python service + vendored copy + actions + containers
def mono():
    f = "monorepo"
    ip = "pnpm-lock.yaml"
    d = [("vite", row(f, "npm", "vite", "4.3.9", True, ip)), ("vue-router", row(f, "npm", "vue-router", "4.1.6", True, ip, "^4.4.0")),
         ("pinia", row(f, "npm", "pinia", "L", True, ip))]
    t = [("rollup", row(f, "npm", "rollup", "3.20.0", False, ip)), ("esbuild", row(f, "npm", "esbuild", "0.17.19", False, ip))]
    decl = {"vue-router": "^4.4.0"}
    w("monorepo/pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n  - 'packages/*'\n")
    w("monorepo/apps/dashboard/package.json", json.dumps({"name": "@tidepool/dashboard", "private": True, "dependencies": {n: decl.get(n, "^" + v) for n, v in d}}, indent=2) + "\n")
    w("monorepo/pnpm-lock.yaml", "lockfileVersion: '9.0'\n\nimporters:\n  apps/dashboard:\n    dependencies:\n" + "".join(
        "      %s:\n        specifier: %s\n        version: %s\n" % (n, decl.get(n, "^" + v), v) for n, v in d) +
        "\npackages:\n" + "".join("  %s@%s:\n    resolution: {integrity: sha512-%s}\n" % (n, v, ph(n + v)) for n, v in d + t) +
        "\nsnapshots:\n" + "".join("  %s@%s: {}\n" % x for x in d + t))
    py = [("pandas", row(f, "pip", "pandas", "1.5.3", True, "services/ingest/requirements.txt")),
          ("python-dateutil", row(f, "pip", "python-dateutil", "2.8.2", False, "services/ingest/requirements.txt")),
          ("tzdata", row(f, "pip", "tzdata", "L", False, "services/ingest/requirements.txt"))]
    w("monorepo/services/ingest/requirements.txt", "".join("%s==%s\n" % x for x in py))
    pyv = row(f, "docker", "python", "3.10.13", True, "services/ingest/Dockerfile", eol_product="python")
    w("monorepo/services/ingest/Dockerfile", "FROM python:%s\nWORKDIR /srv\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\n" % pyv)
    nd = row(f, "docker", "node", "20.11.1", True, "apps/dashboard/Dockerfile", eol_product="nodejs")
    ng = row(f, "docker", "nginx", "L", True, "apps/dashboard/Dockerfile", eol_product="nginx")
    w("monorepo/apps/dashboard/Dockerfile", "FROM node:%s AS build\nWORKDIR /app\nCOPY . .\nRUN corepack enable && pnpm install --frozen-lockfile && pnpm build\n\nFROM nginx:%s\nCOPY --from=build /app/dist /usr/share/nginx/html\n" % (nd, ng))
    workflow(f, "ci.yml", [("actions/checkout", "4.1.0"), ("actions/setup-node", "4.0.0"), ("pnpm/action-setup", "3.0.0"),
                                              ("actions/upload-artifact", "4.3.0"), ("docker/build-push-action", "L")], "pnpm -r test")
    vv = row(f, "npm", "escape-string-regexp", "4.0.0", False, "vendor/escape-string-regexp/package.json", vendored=True)
    w("monorepo/vendor/escape-string-regexp/package.json", json.dumps({"name": "escape-string-regexp", "version": vv, "main": "index.js"}, indent=2) + "\n")
    w("monorepo/vendor/escape-string-regexp/index.js", "/**\n * Vendored copy of upstream escape-string-regexp@%s (MIT), do not edit.\n */\nmodule.exports = s => s.replace(/[|\\\\{}()[\\]^$+*?.]/g, '\\\\$&').replace(/-/g, '\\\\x2d');\n" % vv)

if __name__ == "__main__":
    for fn in (npm, pip, go, maven, gradle, cargo, composer, mono):
        fn()
    os.makedirs(os.path.join(HERE, "truth"), exist_ok=True)
    for fx, rs in ROWS.items():
        json.dump(rs, open(os.path.join(HERE, "truth", fx + ".json"), "w"), indent=1)
        print(fx, "rows", len(rs), "outdated", sum(not r["decoy"] for r in rs), "decoy", sum(r["decoy"] for r in rs))
    json.dump(DRIFT, open(os.path.join(HERE, "drift.json"), "w"), indent=1)
