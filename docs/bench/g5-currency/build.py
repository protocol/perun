#!/usr/bin/env python3
"""Generate the 8 G5 fixture repos + truth/*.json from the SPEC below, using snapshot.py for registry data.
Truth row = {name, ecosystem, current, latest, behind, decoy, eol} plus direct, file, drift (manifest
constraint the lock violates, else null), vendored, eol_product. Decoys are pinned at the registry latest at build time. Hashes in go.sum / composer.lock are
deterministic placeholders (fixtures are static data, not buildable projects)."""
import base64, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot as S

ROOT = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(ROOT, "fixtures")
ROWS = {}  # fixture -> truth rows

def w(path, text):
    p = os.path.join(FX, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)

def ph(s):
    return base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()

def row(fx, eco, name, pin, direct, file, declared=None, eol_product=None, vendored=False, **extra):
    """pin 'L' = latest (decoy). Registry ecosystems verify the pin exists."""
    r = {"name": name, "ecosystem": eco}
    if eco in ("npm", "pip", "go", "maven", "gradle", "cargo", "composer"):
        vs = S.versions(eco, name)
        lat = vs[-1]
        cur = lat if pin == "L" else pin
        assert cur in vs, (eco, name, cur)
    else:
        if eol_product:
            r["eol_product"] = eol_product
        if eco == "docker":
            r["eol_product"] = eol_product
        lat = S.latest({**r, "name": name})
        cur = lat if pin == "L" else pin
    r.update(current=cur, latest=lat, behind=S.behind(cur, lat), decoy=cur == lat,
             eol=S.eol_of(eol_product, cur) if eol_product else None,
             direct=direct, file=file, drift=declared, vendored=vendored, **extra)
    ROWS.setdefault(fx, []).append(r)
    return cur

def v(x):  # strip leading v
    return x.lstrip("v")

# ---------------- npm lock writer (also used by monorepo web) ----------------
def npm_files(base, name, deps, trans, declared, engines=None):
    """deps/trans: lists of (pkg, locked version). declared: pkg -> manifest range."""
    pj = {"name": name, "version": "1.0.0", "private": True,
          "dependencies": {p: declared.get(p, "^" + v_) for p, v_ in deps}}
    if engines:
        pj["engines"] = {"node": engines}
    w(base + "package.json", json.dumps(pj, indent=2) + "\n")
    pk = {"": {"name": name, "version": "1.0.0", "dependencies": pj["dependencies"]}}
    for p, v_ in deps + trans:
        pk["node_modules/" + p] = {"version": v_, "resolved": "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (p, p, v_)}
    w(base + "package-lock.json", json.dumps({"name": name, "version": "1.0.0", "lockfileVersion": 3,
                                              "requires": True, "packages": pk}, indent=2) + "\n")

def go_files(base, mod, gover, direct, indirect, locked=None):
    locked = locked or {}
    out = "module %s\n\ngo %s\n\nrequire (\n" % (mod, gover)
    out += "".join("\t%s %s\n" % (n, c) for n, c in direct)
    out += ")\n\nrequire (\n" + "".join("\t%s %s // indirect\n" % (n, c) for n, c in indirect) + ")\n"
    w(base + "go.mod", out)
    s = ""
    for n, c in direct + indirect:
        c = locked.get(n, c)
        s += "%s %s h1:%s\n%s %s/go.mod h1:%s\n" % (n, c, ph(n + c), n, c, ph(n + c + "mod"))
    w(base + "go.sum", s)

# ---------------- 1 npm ----------------
def npm():
    f = "npm"
    deps = [("express", row(f, "npm", "express", "4.18.2", True, "package-lock.json", "^4.18.2")),
            ("lodash", row(f, "npm", "lodash", "4.17.20", True, "package-lock.json", "^4.17.21")),  # drift: lock < manifest range
            ("uuid", row(f, "npm", "uuid", "L", True, "package-lock.json")),
            ("dayjs", row(f, "npm", "dayjs", "L", True, "package-lock.json")),
            ("nanoid", row(f, "npm", "nanoid", "L", True, "package-lock.json"))]
    trans = [("qs", row(f, "npm", "qs", "6.11.0", False, "package-lock.json")),
             ("minimist", row(f, "npm", "minimist", "1.2.5", False, "package-lock.json")),
             ("ms", row(f, "npm", "ms", "2.0.0", False, "package-lock.json"))]
    row(f, "eol", "nodejs", "20.11.0", True, ".nvmrc", eol_product="nodejs")
    npm_files("npm/", "acme-orders-web", deps, trans, {"lodash": "^4.17.21"}, engines=">=20")
    w("npm/.nvmrc", "20.11.0\n")

# ---------------- 2 pip ----------------
def pip():
    f = "pip"
    rs = [("flask", row(f, "pip", "flask", "3.0.0", True, "requirements.txt", ">=3.0.3")),  # drift
          ("requests", row(f, "pip", "requests", "2.31.0", True, "requirements.txt")),
          ("pyyaml", row(f, "pip", "pyyaml", "5.4.1", True, "requirements.txt")),
          ("jinja2", row(f, "pip", "jinja2", "3.1.2", False, "requirements.txt")),
          ("urllib3", row(f, "pip", "urllib3", "1.26.18", False, "requirements.txt")),
          ("certifi", row(f, "pip", "certifi", "L", False, "requirements.txt")),
          ("idna", row(f, "pip", "idna", "L", False, "requirements.txt")),
          ("click", row(f, "pip", "click", "L", False, "requirements.txt"))]
    row(f, "eol", "python", "3.9.18", True, ".python-version", eol_product="python")
    w("pip/requirements.in", "flask>=3.0.3\nrequests>=2.31\npyyaml==5.4.1\n")
    w("pip/requirements.txt", "# compiled by pip-compile\n" + "".join(
        "%s==%s\n    # via %s\n" % (n, c, "-r requirements.in" if n in ("flask", "requests", "pyyaml") else "flask, requests")
        for n, c in rs))
    w("pip/.python-version", "3.9.18\n")

# ---------------- 3 go ----------------
def go():
    f = "go"
    d = [(n, row(f, "go", n, p, True, "go.mod")) for n, p in [
        ("github.com/gin-gonic/gin", "v1.9.1"), ("github.com/spf13/cobra", "v1.8.0"),
        ("github.com/stretchr/testify", "v1.8.4"),
        ("github.com/go-chi/chi/v5", "v5.0.10"),  # major-version path = separate module
        ("github.com/google/uuid", "L"), ("github.com/rs/zerolog", "L")]]
    i = [("golang.org/x/text", row(f, "go", "golang.org/x/text", "v0.14.0", False, "go.mod")),
         ("golang.org/x/net", row(f, "go", "golang.org/x/net", "v0.21.0", False, "go.mod", "go.sum has only v0.17.0")),  # drift
         ("golang.org/x/sys", row(f, "go", "golang.org/x/sys", "L", False, "go.mod"))]
    row(f, "eol", "go", "1.22.0", True, "go.mod", eol_product="go")
    go_files("go/", "example.com/acme/gateway", "1.22.0", d, i, {"golang.org/x/net": "v0.17.0"})

# ---------------- 4 maven / 5 gradle ----------------
def maven():
    f = "maven"
    ga = lambda n: n.split(":")
    d = [(n, row(f, "maven", n, p, True, "lockfile.json", dec)) for n, p, dec in [
        ("org.apache.commons:commons-lang3", "3.12.0", "3.14.0"),  # drift: pom 3.14.0, lock 3.12.0
        ("com.fasterxml.jackson.core:jackson-databind", "2.15.0", None),
        ("org.apache.commons:commons-text", "1.10.0", None),
        ("org.slf4j:slf4j-api", "L", None)]]
    t = [(n, row(f, "maven", n, p, False, "lockfile.json")) for n, p in [
        ("commons-io:commons-io", "2.11.0"), ("org.yaml:snakeyaml", "1.33"),
        ("commons-codec:commons-codec", "L"), ("org.apache.commons:commons-collections4", "L")]]
    boot = row(f, "eol", "spring-boot", "3.3.2", True, "pom.xml", eol_product="spring-boot")
    decl = {"org.apache.commons:commons-lang3": "3.14.0"}
    dep = "".join("    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></dependency>\n"
                  % (*ga(n), decl.get(n, c)) for n, c in d)
    w("maven/pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n'
      '  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>%s</version></parent>\n'
      '  <groupId>example.com.acme</groupId><artifactId>billing-svc</artifactId><version>1.0.0</version>\n'
      '  <dependencies>\n%s  </dependencies>\n</project>\n' % (boot, dep))
    w("maven/lockfile.json", json.dumps({"lockFileVersion": 1, "groupId": "example.com.acme", "artifactId": "billing-svc",
        "dependencies": [dict(zip(("groupId", "artifactId"), ga(n)), version=c, scope="compile") for n, c in d + t]}, indent=2) + "\n")

def gradle():
    f = "gradle"
    d = [(n, row(f, "gradle", n, p, True, "gradle.lockfile", dec)) for n, p, dec in [
        ("org.yaml:snakeyaml", "2.0", None), ("commons-io:commons-io", "2.11.0", None),
        ("com.fasterxml.jackson.core:jackson-databind", "2.13.0", "2.15.0"),  # drift
        ("org.slf4j:slf4j-api", "L", None), ("junit:junit", "L", None)]]
    t = [(n, row(f, "gradle", n, p, False, "gradle.lockfile")) for n, p in [
        ("org.apache.commons:commons-text", "1.9"), ("org.apache.commons:commons-lang3", "3.12.0"),
        ("commons-codec:commons-codec", "L")]]
    boot = row(f, "eol", "spring-boot", "3.4.1", True, "build.gradle", eol_product="spring-boot")
    decl = {"com.fasterxml.jackson.core:jackson-databind": "2.15.0"}
    w("gradle/build.gradle", "plugins {\n    id 'java'\n    id 'org.springframework.boot' version '%s'\n}\n\ndependencies {\n%s}\n" % (
        boot, "".join("    implementation '%s:%s'\n" % (n, decl.get(n, c)) for n, c in d)))
    w("gradle/gradle.lockfile", "# This is a Gradle generated file for dependency locking.\n" + "".join(
        "%s:%s=compileClasspath,runtimeClasspath\n" % (n, c) for n, c in sorted(d + t)) + "empty=\n")

# ---------------- 6 cargo ----------------
def cargo():
    f = "cargo"
    d = [(n, row(f, "cargo", n, p, True, "Cargo.lock", dec)) for n, p, dec in [
        ("serde", "1.0.150", None), ("tokio", "1.28.0", "1.40"),  # drift: lock 1.28.0 < ^1.40
        ("rand", "0.8.5", None), ("regex", "1.8.0", None),
        ("log", "L", None), ("anyhow", "L", None)]]
    t = [(n, row(f, "cargo", n, p, False, "Cargo.lock")) for n, p in [
        ("memchr", "2.5.0"), ("itoa", "L"), ("bytes", "L")]]
    decl = {"tokio": "1.40", "serde": "1.0", "rand": "0.8", "regex": "1.8", "log": "0.4", "anyhow": "1"}
    w("cargo/Cargo.toml", '[package]\nname = "acme-telemetry"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n' +
      "".join('%s = "%s"\n' % (n, decl[n]) for n, _ in d))
    w("cargo/Cargo.lock", "# This file is automatically @generated by Cargo.\nversion = 3\n\n" +
      '[[package]]\nname = "acme-telemetry"\nversion = "0.1.0"\ndependencies = [\n%s]\n\n' % "".join(' "%s",\n' % n for n, _ in d) +
      "\n".join('[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n' % (n, c) for n, c in d + t))

# ---------------- 7 composer ----------------
def composer():
    f = "composer"
    d = [(n, row(f, "composer", n, p, True, "composer.lock", dec)) for n, p, dec in [
        ("monolog/monolog", "3.3.1", None), ("symfony/yaml", "v6.3.0", None),
        ("guzzlehttp/guzzle", "7.5.0", "^7.8"),  # drift: lock 7.5.0 < ^7.8
        ("nesbot/carbon", "L", None), ("ramsey/uuid", "L", None), ("vlucas/phpdotenv", "L", None)]]
    t = [(n, row(f, "composer", n, p, False, "composer.lock")) for n, p in [
        ("psr/log", "3.0.0"), ("symfony/polyfill-mbstring", "v1.28.0")]]
    php = row(f, "eol", "php", "8.1.27", True, "composer.json", eol_product="php")
    decl = {"guzzlehttp/guzzle": "^7.8"}
    req = {n: decl.get(n, "^" + v(c)) for n, c in d}
    req["php"] = "^8.1"
    w("composer/composer.json", json.dumps({"name": "acme/shop", "require": req, "config": {"platform": {"php": php}}}, indent=4) + "\n")
    w("composer/composer.lock", json.dumps({"_readme": ["This file locks the dependencies of the project"],
        "content-hash": hashlib.md5(b"acme-shop").hexdigest(),
        "packages": [{"name": n, "version": c, "type": "library"} for n, c in sorted(d + t)],
        "platform": {"php": "^8.1"}, "plugin-api-version": "2.6.0"}, indent=4) + "\n")

# ---------------- 8 Dockerfile + Actions monorepo ----------------
def mono():
    f = "monorepo"
    exp = row(f, "npm", "express", "4.18.2", True, "services/web/package-lock.json", "^4.19.0")  # drift
    bp = row(f, "npm", "body-parser", "1.20.1", False, "services/web/package-lock.json")
    dj = row(f, "npm", "dayjs", "L", True, "services/web/package-lock.json")
    npm_files("monorepo/services/web/", "acme-web", [("express", exp), ("dayjs", dj)], [("body-parser", bp)], {"express": "^4.19.0"})
    gin = row(f, "go", "github.com/gin-gonic/gin", "v1.9.1", True, "services/worker/go.mod")
    uu = row(f, "go", "github.com/google/uuid", "L", True, "services/worker/go.mod")
    tx = row(f, "go", "golang.org/x/text", "v0.14.0", False, "services/worker/go.mod")
    go_files("monorepo/services/worker/", "example.com/acme/worker", "1.27.0",
             [("github.com/gin-gonic/gin", gin), ("github.com/google/uuid", uu)], [("golang.org/x/text", tx)])
    nd = row(f, "docker", "node", "18.20.4", True, "services/web/Dockerfile", eol_product="nodejs")
    ng = row(f, "docker", "nginx", "1.25.5", True, "services/web/Dockerfile", eol_product="nginx")
    gl = row(f, "docker", "golang", "L", True, "services/worker/Dockerfile", eol_product="go")
    al = row(f, "docker", "alpine", "L", True, "services/worker/Dockerfile", eol_product="alpine")
    w("monorepo/services/web/Dockerfile", "FROM node:%s AS build\nWORKDIR /app\nCOPY . .\nRUN npm ci\n\nFROM nginx:%s\nCOPY --from=build /app /usr/share/nginx/html\n" % (nd, ng))
    w("monorepo/services/worker/Dockerfile", "FROM golang:%s AS build\nWORKDIR /src\nCOPY . .\nRUN go build -o /worker .\n\nFROM alpine:%s\nCOPY --from=build /worker /worker\nCMD [\"/worker\"]\n" % (gl, al))
    # actions: tags must exist as releases
    pins = [("actions/checkout", "3.6.0"), ("actions/cache", "3.3.2"), ("actions/setup-node", "3.9.1"),
            ("actions/setup-go", "L"), ("actions/download-artifact", "L")]
    cur = {}
    for n, p in pins:
        if p != "L":
            rel = [r["tag_name"] for r in S.gj("https://api.github.com/repos/%s/releases?per_page=100" % n)]
            for pg in (2, 3):
                if "v" + p not in rel:
                    rel += [r["tag_name"] for r in S.gj("https://api.github.com/repos/%s/releases?per_page=100&page=%d" % (n, pg))]
            assert "v" + p in rel, (n, p)
        cur[n] = row(f, "actions", n, p, True, ".github/workflows/ci.yml")
    w("monorepo/.github/workflows/ci.yml", "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n" +
      "".join("      - uses: %s@v%s\n" % (n, c) for n, c in cur.items()) + "      - run: npm ci && go test ./...\n")
    # vendored copy (no marker file; flagged by path + header)
    vm = row(f, "npm", "ms", "2.0.0", False, "third_party/ms/package.json", vendored=True)
    w("monorepo/third_party/ms/package.json", json.dumps({"name": "ms", "version": vm, "main": "./index.js"}, indent=2) + "\n")
    w("monorepo/third_party/ms/index.js", "/**\n * Helpers. (copied from upstream ms@%s)\n */\nvar s = 1000;\nmodule.exports = function (val) { return Number(val) * s; };\n" % vm)

for fn in (npm, pip, go, maven, gradle, cargo, composer, mono):
    fn()
os.makedirs(os.path.join(ROOT, "truth"), exist_ok=True)
for fx, rs in ROWS.items():
    json.dump(rs, open(os.path.join(ROOT, "truth", fx + ".json"), "w"), indent=1)
    print(fx, "rows", len(rs), "outdated", sum(not r["decoy"] for r in rs), "decoy", sum(r["decoy"] for r in rs))
