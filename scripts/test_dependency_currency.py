#!/usr/bin/env python3
"""Tests for dependency_currency.py: fictional fixtures for npm, pip, go, maven, gradle, cargo, composer, a Dockerfile/Actions
monorepo and a vendored dir, with every HTTP call mocked (no network). Covers the per-ecosystem "latest" rule, decoys at latest,
drift, EOL, KEV-first ordering, upgrade-target resolution and the NOT RUN row when a registry is unreachable."""
import contextlib, importlib.util, io, json, os, sys, tempfile, time, unittest, urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
TODAY = "2026-11-03"
J = json.dumps


def node_cycles():
    """endoflife.date cycles for the fictional node product: 25 is not LTS, 24 and 22 are, 18 is EOL."""
    return J([{"cycle": "25", "eol": "2026-06-01", "latest": "25.1.0", "lts": False}, {"cycle": "24", "eol": "2028-04-30", "latest": "24.2.1", "lts": "2025-10-28"},
              {"cycle": "22", "eol": "2027-04-30", "latest": "22.9.0", "lts": "2024-10-29"}, {"cycle": "18", "eol": "2025-04-30", "latest": "18.20.8", "lts": "2022-10-25"}])


def routes():
    """Map URL substring -> response text for the mocked registries."""
    npmv = lambda *vs, **dep: J({"versions": {v: ({"deprecated": "x"} if v in dep else {}) for v in vs}})
    return {
        "registry.npmjs.org/fict-npm": npmv("1.0.0", "2.0.0", "3.0.0-beta.1", "9.9.9", **{"9.9.9": 1}),
        "registry.npmjs.org/fict-dep": npmv("2.0.0"),
        "pypi.org/pypi/fict-py/json": J({"releases": {"1.0": [{}], "1.4": [{}], "2.0": [{"yanked": True}], "2.0rc1": [{}]}}),
        "pypi.org/pypi/fict-pydecoy/json": J({"releases": {"3.1": [{}]}}),
        "proxy.golang.org/example.com/fictmod/v2/@v/list": "v2.0.0\nv2.1.0\nv2.2.0\nv2.3.0-rc1\n",
        "proxy.golang.org/example.com/fictdecoy/@v/list": "v1.5.0\n",
        "proxy.golang.org/example.com/fictmod/v2/@latest": J({"Version": "v2.2.0"}),
        "proxy.golang.org/example.com/fictdecoy/@latest": J({"Version": "v1.5.0"}),
        "maven2/org/fict/lib/maven-metadata.xml": "<metadata><versions><version>1.0.0</version><version>1.2.0</version><version>1.3.0-SNAPSHOT</version></versions></metadata>",
        "maven2/org/fict/glib/maven-metadata.xml": "<metadata><versions><version>4.0.0</version><version>4.1.0</version></versions></metadata>",
        "crates.io/api/v1/crates/fict-crate": J({"versions": [{"num": "0.3.0", "yanked": False}, {"num": "0.4.0", "yanked": False}, {"num": "0.5.0", "yanked": True}]}),
        "repo.packagist.org/p2/fict/pkg.json": J({"packages": {"fict/pkg": [{"version": "v2.1.0"}, {"version": "v2.0.0"}, {"version": "dev-main"}]}}),
        "endoflife.date/api/nodejs.json": node_cycles(),
        "endoflife.date/api/python.json": J([{"cycle": "3.14", "eol": "2030-10-31", "latest": "3.14.0", "lts": False}, {"cycle": "3.12", "eol": "2028-10-31", "latest": "3.12.7", "lts": False}]),
        "hub.docker.com/v2/repositories/library/node/tags": J({"results": [{"name": "24-alpine"}, {"name": "22-alpine"}, {"name": "25-rc-alpine"}]}),
        "hub.docker.com/v2/repositories/library/python/tags": J({"results": [{"name": "3.14-slim"}, {"name": "3.13-slim"}]}),
        "api.github.com/repos/acme/fict-action/releases/latest": J({"tag_name": "v4.2.0"}),
        "api.github.com/repos/acme/fict-pinned/releases/latest": J({"tag_name": "v1.0.0"}),
        "api.osv.dev/v1/vulns/GHSA-fict-0001": J({"aliases": ["CVE-2099-0001"]}),
        "cisa.gov": J({"vulnerabilities": [{"cveID": "CVE-2099-0001"}]}),
    }


def fake(table, osv=None, down=()):
    """Return a Net.get replacement serving `table`; hosts containing a `down` substring raise OSError; osv answers querybatch."""
    def get(url, data=None, headers=None):
        """Mocked HTTP GET/POST."""
        if any(d in url for d in down):
            raise OSError("unreachable (mock)")
        if url.endswith("/v1/querybatch"):
            qs = json.loads(data)["queries"]
            return J({"results": [{"vulns": [{"id": i} for i in (osv or {}).get(q["package"]["name"], [])]} for q in qs]})
        for k, v in table.items():
            if k in url:
                return v
        raise dc.NotFound(url)
    return get


FILES = {
    "web/package-lock.json": J({"lockfileVersion": 3, "packages": {"": {}, "node_modules/fict-npm": {"version": "1.0.0", "resolved": "https://r/x.tgz"},
                                "node_modules/a/node_modules/fict-dep": {"version": "2.0.0", "resolved": "https://r/y.tgz"}}}),
    "web/package.json": J({"dependencies": {"fict-npm": "^2.0.0", "fict-dep": "^2.0.0"}}),
    "py/requirements.txt": "fict-py==1.0\nfict-pydecoy==3.1  # decoy\n",
    "go/go.mod": "module example.com/app\n\ngo 1.22\n\nrequire (\n\texample.com/fictmod/v2 v2.1.0\n\texample.com/fictdecoy v1.5.0 // indirect\n)\n",
    "mvn/pom.xml": '<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><fv>1.0.0</fv></properties><dependencies>'
                   '<dependency><groupId>org.fict</groupId><artifactId>lib</artifactId><version>${fv}</version></dependency></dependencies></project>',
    "gr/gradle.lockfile": "org.fict:glib:4.1.0=runtimeClasspath\n",
    "rs/Cargo.lock": '[[package]]\nname = "app"\nversion = "0.1.0"\n\n[[package]]\nname = "fict-crate"\nversion = "0.3.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n',
    "rs/Cargo.toml": '[dependencies]\nfict-crate = "0.4"\n',
    "php/composer.lock": J({"packages": [{"name": "fict/pkg", "version": "v2.0.0"}], "packages-dev": []}),
    "ops/Dockerfile": "FROM node:18-alpine AS build\nFROM build AS again\nFROM python:3.14-slim\nFROM scratch\nFROM node:latest\n",
    ".github/workflows/ci.yml": "steps:\n  - uses: acme/fict-action@v3\n  - uses: acme/fict-pinned@v1.0.0\n  - uses: acme/fict-main@main\n  - uses: acme/x@0123456789abcdef0123456789abcdef01234567\n",
    "vendor/lib/a.js": "x",
}


class T(unittest.TestCase):
    """Currency detector behaviour against mocked registries."""

    def run_dc(self, table=None, osv=None, down=(), files=None):
        """Write FILES to a temp repo, run the detector with a mocked network, return {(file, name): row}."""
        files = files or FILES
        with tempfile.TemporaryDirectory() as d:
            for f, c in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
                with open(os.path.join(d, f), "w") as fh:
                    fh.write(c)
            dc.net = dc.Net()
            dc.net.get = fake(table or routes(), osv, down)
            rows = dc.run(d, sorted(files), TODAY)
        self.rows = rows
        return {(r["file"], r["name"]): r for r in rows}

    def test_every_ecosystem(self):
        """Outdated rows carry current, latest, behind and a registry-resolved target; decoys at latest produce no finding."""
        r = self.run_dc()
        a = r[("web/package-lock.json", "fict-npm")]
        self.assertEqual((a["status"], a["latest"], a["target"]), ("outdated", "2.0.0", "2.0.0"))  # deprecated 9.9.9 and beta skipped
        self.assertEqual(r[("web/package-lock.json", "fict-dep")]["status"], "current")  # transitive decoy
        self.assertEqual(r[("py/requirements.txt", "fict-py")]["latest"], "1.4")  # yanked 2.0 and rc skipped
        self.assertEqual(r[("py/requirements.txt", "fict-pydecoy")]["status"], "current")
        self.assertEqual(r[("go/go.mod", "example.com/fictmod/v2")]["latest"], "v2.2.0")
        self.assertEqual(r[("go/go.mod", "example.com/fictdecoy")]["status"], "current")
        self.assertEqual(r[("mvn/pom.xml", "org.fict:lib")]["latest"], "1.2.0")  # SNAPSHOT skipped, property resolved
        self.assertEqual(r[("gr/gradle.lockfile", "org.fict:glib")]["status"], "current")
        self.assertEqual(r[("rs/Cargo.lock", "fict-crate")]["latest"], "0.4.0")  # yanked 0.5.0 skipped
        self.assertEqual(r[("php/composer.lock", "fict/pkg")]["latest"], "2.1.0")  # dev-main skipped

    def test_drift_runtime_actions_vendored(self):
        """Manifest-vs-lock drift, EOL image with verified target, floating tag, action pins and the vendored flag."""
        r = self.run_dc()
        self.assertEqual(r[("web/package.json", "fict-npm")]["status"], "drift")
        self.assertEqual(r[("rs/Cargo.toml", "fict-crate")]["status"], "drift")
        img = [x for x in self.rows if x["file"] == "ops/Dockerfile"]
        self.assertEqual(len(img), 3)  # stage reference and scratch skipped
        n18 = next(x for x in img if x["current"] == "18")
        self.assertEqual((n18["status"], n18["target"]), ("eol", "node:24-alpine"))  # latest comes from Hub tags, shaped like the current tag; the feed only sets eol
        self.assertTrue(any(x["status"] == "unpinned" for x in img))
        self.assertTrue(any(x["name"] == "python" and x["status"] == "current" for x in img))
        act = {x["name"]: x for x in self.rows if x["kind"] == "action"}
        self.assertEqual((act["acme/fict-action"]["status"], act["acme/fict-action"]["target"]), ("outdated", "acme/fict-action@v4.2.0"))
        self.assertEqual(act["acme/fict-pinned"]["status"], "current")
        self.assertEqual(act["acme/fict-main"]["status"], "unpinned")
        self.assertEqual(act["acme/x"]["status"], "not-checked")
        self.assertTrue(any(x["kind"] == "vendored" for x in self.rows))
        self.assertTrue(any(x["name"] == "go directive" for x in self.rows))

    def test_kev_first(self):
        """A KEV-listed vulnerable row sorts before an ordinary vulnerable row, which sorts before outdated ones."""
        r = self.run_dc(osv={"fict-npm": ["GHSA-fict-0001"], "fict-py": ["GHSA-fict-0002"]})
        self.assertEqual(r[("web/package-lock.json", "fict-npm")]["kev"], ["CVE-2099-0001"])
        rules = [dc.rule_of(x) for x in self.rows]
        self.assertEqual(rules[:2], ["kev", "vulnerable"])
        self.assertLess(rules.index("vulnerable"), rules.index("outdated"))

    def test_unreachable_is_not_run(self):
        """Unreachable registry, OSV or endoflife.date gives not-checked rows, never current."""
        r = self.run_dc(down=("registry.npmjs.org", "pypi.org", "endoflife.date"))
        for k in (("web/package-lock.json", "fict-npm"), ("web/package-lock.json", "fict-dep"), ("py/requirements.txt", "fict-pydecoy")):
            self.assertEqual(r[k]["status"], "not-checked")
            self.assertIn("NOT RUN", r[k]["note"])
        self.assertTrue(all(x["status"] == "not-checked" for x in self.rows if x["file"] == "ops/Dockerfile" and x["kind"] == "runtime"))
        r = self.run_dc(down=("api.osv.dev",))
        self.assertIn("NOT RUN: OSV", r[("web/package-lock.json", "fict-npm")]["note"])
        self.assertIsNone(r[("web/package-lock.json", "fict-npm")]["vulnerable"])

    def test_semver_ranges(self):
        """Range checker: caret, tilde, cargo bare, composer tilde, wildcard, or, unreadable specs."""
        s = dc.sat
        self.assertTrue(s("^1.2.3", "1.9.0") and not s("^1.2.3", "2.0.0") and not s("^0.2.1", "0.3.0"))
        self.assertTrue(s("~1.2.3", "1.2.9") and not s("~1.2.3", "1.3.0"))
        self.assertTrue(s("1.2", "1.9.0", cargo=True) and not s("1.2", "2.0.0", cargo=True))
        self.assertTrue(s("~1.2", "1.9.0", composer=True) and not s("~1.2", "2.0.0", composer=True))
        self.assertTrue(s("^1 || ^3", "3.1.0") and s("latest", "9.0.0") and s("git+https://x/y", "1.0.0"))

    def test_behind_and_pre(self):
        """behind() names the first differing level; is_pre() flags qualifiers per ecosystem."""
        self.assertEqual((dc.behind("1.0.0", "2.0.0"), dc.behind("1.0.0", "1.2.0"), dc.behind("1.0.0", "1.0.3"), dc.behind("2.0.0", "1.0.0")), ("major", "minor", "patch", ""))
        self.assertTrue(dc.is_pre("npm", "1.0.0-beta.1") and dc.is_pre("pip", "2.0rc1") and dc.is_pre("maven", "1.0-SNAPSHOT") and not dc.is_pre("maven", "1.0.Final"))


def lock(**pk):
    """A package-lock.json v3 text with the given name=version root entries."""
    return J({"lockfileVersion": 3, "packages": {"": {}, **{f"node_modules/{n}": {"version": v, "resolved": "https://r/x.tgz"} for n, v in pk.items()}}})


def with_routes(**extra):
    """routes() plus extra URL-substring -> text entries (keys given as k__j are not needed; pass via dict)."""
    t = routes()
    t.update(extra)
    return t


class Fix(unittest.TestCase):
    """Review fixes: OSV-down current rows, parsers, pre-release/flavor rules, untrusted names, size caps, budget and rate limit."""
    run_dc = T.run_dc

    def row(self, r, f, name):
        """The row for (file, name) or fail."""
        self.assertIn((f, name), r, sorted(r))
        return r[(f, name)]

    def test_osv_down_current_row_main(self):
        """A current dependency with OSV unreachable is a not-checked row in rule_of and in main()'s TSV, never silent."""
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "package-lock.json"), "w") as fh:
                fh.write(lock(**{"fict-dep": "2.0.0"}))
            dc.net = dc.Net()
            dc.net.get = fake(routes(), None, ("api.osv.dev",))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO("package-lock.json\n")):
                dc.main(["--root", d, "--stdin", "--today", TODAY])
            rows = dc.run(d, ["package-lock.json"], TODAY)
        self.assertEqual(dc.rule_of(rows[0]), "not-checked")
        self.assertRegex(out.getvalue(), r"package-lock\.json\t0\tnot-checked\t.*OSV")

    def test_osv_short_response_not_current(self):
        """An OSV answer with fewer results than queries leaves the row not-checked."""
        dc.net = dc.Net()
        get = fake(routes())
        dc.net.get = lambda url, data=None, headers=None: J({"results": []}) if url.endswith("querybatch") else get(url, data, headers)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "package-lock.json"), "w") as fh:
                fh.write(lock(**{"fict-dep": "2.0.0"}))
            rows = dc.run(d, ["package-lock.json"], TODAY)
        self.assertEqual(dc.rule_of(rows[0]), "not-checked")

    def test_lock_parsers(self):
        """yarn berry, workspace keys, pnpm (v5/v6/v9), poetry git/path and cargo non-crates sources."""
        berry = '__metadata:\n  version: 6\n\n"fict-a@npm:^1.0.0, fict-a@npm:^1.1.0":\n  version: 1.2.3\n\n"root@workspace:.":\n  version: 0.0.0-use.local\n'
        self.assertEqual(dc.p_yarn_lock(berry), [("fict-a", "1.2.3")])
        ws = J({"packages": {"": {}, "packages/ws": {"version": "1.0.0"}, "node_modules/ws": {"resolved": "file:../ws", "link": True},
                             "node_modules/fict-a": {"version": "1.0.0", "resolved": "https://r/a.tgz"}}})
        self.assertEqual(dc.p_npm_lock(ws), [("fict-a", "1.0.0")])
        pn = ("lockfileVersion: '9.0'\npackages:\n  fict-a@1.2.3:\n    resolution: {}\n  '@fict/b@2.0.0-rc.1':\n    x: 1\n  /fict-c@3.1.0(react@18.0.0):\n    x: 1\n"
              "  /@fict/d/4.0.0_react@18.0.0:\n    x: 1\nsnapshots:\n  fict-z@9.9.9:\n    x: 1\n")
        self.assertEqual(dc.p_pnpm_lock(pn), [("@fict/b", "2.0.0-rc.1"), ("@fict/d", "4.0.0"), ("fict-a", "1.2.3"), ("fict-c", "3.1.0")])
        poetry = '[[package]]\nname = "ok"\nversion = "1.0"\n\n[[package]]\nname = "gitpkg"\nversion = "2.0"\n\n[package.source]\ntype = "git"\nurl = "https://x/y"\n'
        self.assertEqual(dc.p_toml_packages(poetry), [("ok", "1.0")])
        cargo = ('[[package]]\nname = "a"\nversion = "1.0.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n[[package]]\nname = "b"\nversion = "1.0.0"\n'
                 'source = "registry+https://private.example.com/index"\n\n[[package]]\nname = "c"\nversion = "1.0.0"\nsource = "sparse+https://index.crates.io/"\n')
        self.assertEqual(dc.p_toml_packages(cargo, True), [("a", "1.0.0"), ("c", "1.0.0")])

    def test_npm_drift_uses_root_entry(self):
        """Drift compares package.json with node_modules/<name>, not the highest nested copy."""
        lk = J({"packages": {"": {}, "node_modules/fict-a": {"version": "1.0.0", "resolved": "https://r/a"}, "node_modules/x/node_modules/fict-a": {"version": "2.0.0", "resolved": "https://r/b"}}})
        r = self.run_dc(files={"w/package-lock.json": lk, "w/package.json": J({"dependencies": {"fict-a": "^1.0.0"}})})
        self.assertNotIn(("w/package.json", "fict-a"), r)

    def test_python_drift(self):
        """requirements.in vs requirements.txt and pyproject (poetry and PEP 621) vs poetry.lock drift."""
        r = self.run_dc(files={"p/requirements.in": "fict-py>=2\nfict-pydecoy~=3.0\n", "p/requirements.txt": "fict-py==1.0\nfict-pydecoy==3.1\n",
                               "q/pyproject.toml": '[project]\nname = "x"\ndependencies = ["fict-py>=2"]\n\n[tool.poetry.dependencies]\npython = "^3.11"\nfict-pydecoy = "^3.0"\n',
                               "q/poetry.lock": '[[package]]\nname = "fict-py"\nversion = "1.0"\n\n[[package]]\nname = "fict-pydecoy"\nversion = "3.1"\n'})
        self.assertEqual(self.row(r, "p/requirements.in", "fict-py")["status"], "drift")
        self.assertNotIn(("p/requirements.in", "fict-pydecoy"), r)
        self.assertEqual(self.row(r, "q/pyproject.toml", "fict-py")["status"], "drift")
        self.assertNotIn(("q/pyproject.toml", "fict-pydecoy"), r)
        self.assertNotIn(("q/pyproject.toml", "python"), r)

    def test_go_replace(self):
        """A local replace is a not-checked row; a module replace swaps in the replacement module and version."""
        gm = "module example.com/app\n\nrequire (\n\texample.com/fictmod/v2 v2.1.0\n\texample.com/other v1.0.0\n)\n\nreplace example.com/fictmod/v2 => ../local\nreplace example.com/other v1.0.0 => example.com/fictdecoy v1.5.0\n"
        r = self.run_dc(files={"go/go.mod": gm})
        a = self.row(r, "go/go.mod", "example.com/fictmod/v2")
        self.assertEqual(a["status"], "not-checked")
        self.assertIn("replace", a["note"])
        self.assertEqual(self.row(r, "go/go.mod", "example.com/fictdecoy")["status"], "current")
        self.assertNotIn(("go/go.mod", "example.com/other"), r)

    def test_maven_managed_and_spring(self):
        """Versionless deps resolve from dependencyManagement or give a not-checked row; starter-parent drives spring-boot EOL."""
        pom = ('<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.2.0</version></parent>'
               '<dependencyManagement><dependencies><dependency><groupId>org.fict</groupId><artifactId>lib</artifactId><version>1.0.0</version></dependency></dependencies></dependencyManagement>'
               '<dependencies><dependency><groupId>org.fict</groupId><artifactId>lib</artifactId></dependency>'
               '<dependency><groupId>org.fict</groupId><artifactId>glib</artifactId></dependency></dependencies></project>')
        t = with_routes(**{"endoflife.date/api/spring-boot.json": J([{"cycle": "3.5", "eol": "2032-01-01", "latest": "3.5.0", "lts": False}, {"cycle": "3.2", "eol": "2024-11-23", "latest": "3.2.12", "lts": False}])})
        r = self.run_dc(table=t, files={"m/pom.xml": pom})
        self.assertEqual(len([x for x in self.rows if x["name"] == "org.fict:lib"]), 1)
        self.assertEqual(self.row(r, "m/pom.xml", "org.fict:glib")["status"], "not-checked")
        sb = [x for x in self.rows if x["kind"] == "runtime" and x["status"] == "eol"]
        self.assertEqual(len(sb), 1)

    def test_floating_refs_give_rows(self):
        """.nvmrc aliases, Dockerfile ARG tags, quoted uses:, compose images and Gradle dynamic versions are rows, never silent."""
        files = {".nvmrc": "lts/*\n", "sub/.python-version": "mystery\n", "ops/Dockerfile": "ARG V=18\nFROM node:${V}-alpine\nFROM node:$UNKNOWN\n",
                 ".github/workflows/q.yml": "steps:\n  - uses: \"acme/fict-action@v3\"\n  - uses: 'acme/fict-pinned@v1.0.0'\n  - uses: docker://alpine:3\n",
                 "docker-compose.yml": "services:\n  a:\n    image: node:18-alpine\n  b:\n    image: \"ghcr.io/x/y:1\"\n", "g/build.gradle": "implementation 'org.fict:glib:4.+'\n"}
        r = self.run_dc(files=files)
        self.assertEqual(self.row(r, ".nvmrc", ".nvmrc")["status"], "unpinned")
        self.assertEqual(self.row(r, "sub/.python-version", ".python-version")["status"], "not-checked")
        dk = [x for x in self.rows if x["file"] == "ops/Dockerfile"]
        self.assertEqual(sorted(x["status"] for x in dk), ["eol", "not-checked"])
        act = {x["name"]: x["status"] for x in self.rows if x["kind"] == "action"}
        self.assertEqual((act["acme/fict-action"], act["acme/fict-pinned"]), ("outdated", "current"))
        self.assertEqual(act["docker://alpine:3"], "not-checked")
        cp = {x["name"]: x["status"] for x in self.rows if x["file"] == "docker-compose.yml"}
        self.assertEqual(cp, {"node": "eol", "ghcr.io/x/y": "not-checked"})
        self.assertEqual(self.row(r, "g/build.gradle", "org.fict:glib")["status"], "unpinned")

    def test_prerelease_flavor_and_dist_tag(self):
        """A pre-release below its own stable is behind; npm latest is dist-tags.latest; Maven keeps -jre/-android."""
        t = with_routes(**{"registry.npmjs.org/fict-pre": J({"versions": {"2.0.0-rc.1": {}, "2.0.0": {}}}),
                           "registry.npmjs.org/fict-tag": J({"dist-tags": {"latest": "1.5.0"}, "versions": {"1.0.0": {}, "1.5.0": {}, "2.0.0": {}}}),
                           "maven2/org/fict/guava/maven-metadata.xml": "<metadata><versions><version>1.0-jre</version><version>1.1-jre</version><version>2.0-android</version></versions></metadata>"})
        r = self.run_dc(table=t, files={"w/package-lock.json": lock(**{"fict-pre": "2.0.0-rc.1", "fict-tag": "1.0.0"}), "g/gradle.lockfile": "org.fict:guava:1.0-jre=runtimeClasspath\n"})
        a = self.row(r, "w/package-lock.json", "fict-pre")
        self.assertEqual((a["status"], a["latest"]), ("outdated", "2.0.0"))
        self.assertEqual(self.row(r, "w/package-lock.json", "fict-tag")["latest"], "1.5.0")
        self.assertEqual(self.row(r, "g/gradle.lockfile", "org.fict:guava")["latest"], "1.1-jre")

    def test_untrusted_names(self):
        """Names are quoted per segment with safe='', `..` and control characters are refused."""
        urls = []
        dc.net = dc.Net()
        dc.net.get = lambda url, data=None, headers=None: urls.append(url) or J({"packages": {"fict/pkg?x": []}})
        dc.versions("composer", "fict/pkg?x")
        self.assertIn("fict/pkg%3Fx", urls[0])
        for eco, n in (("pip", "../x"), ("npm", "a/../b"), ("composer", "a/../b"), ("cargo", "a\nb"), ("maven", "..:x"), ("go", "example.com/../x")):
            with self.assertRaises(ValueError):
                dc.versions(eco, n)
        self.assertEqual(len(urls), 1)

    def test_size_caps_fail_closed(self):
        """A response or a repo file over 5 MB is an error / not-checked row, not a silent pass."""
        big = 5 * 1024 * 1024 + 1

        class R:
            """Fake urlopen response."""
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return b"x" * (big if n < 0 else min(n, big))
        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: R()):
            with self.assertRaises(OSError):
                dc.Net().get("https://example.com/big")
        r = self.run_dc(files={"requirements.txt": "x" * big})
        self.assertEqual(self.row(r, "requirements.txt", "requirements.txt")["status"], "not-checked")

    def test_composer_exclusion(self):
        """php, hhvm, ext-* and lib-* are platform entries; php-http/client is a real package."""
        c = J({"require": {"php": ">=8", "hhvm": "*", "ext-json": "*", "lib-curl": "*", "php-http/client": "^1.0"}})
        self.assertEqual(dc.p_json_manifest(c, ("require",)), [("php-http/client", "^1.0")])

    def test_budget_and_crates_rate(self):
        """Real Net.get refuses calls past the deadline and spaces crates.io calls at least 1 s apart."""
        n = dc.Net()
        dc.DEADLINE = time.time() - 1
        try:
            with self.assertRaises(OSError):
                n.get("https://api.osv.dev/v1/querybatch", b"{}")
        finally:
            dc.DEADLINE = None
        sleeps = []

        class R:
            """Fake urlopen response."""
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return b"{}"
        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: R()), mock.patch.object(dc.time, "sleep", sleeps.append):
            n = dc.Net()
            n.get("https://crates.io/api/v1/crates/a")
            n.get("https://crates.io/api/v1/crates/b")
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 0.9)


if __name__ == "__main__":
    unittest.main()
