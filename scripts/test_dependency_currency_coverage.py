#!/usr/bin/env python3
"""Coverage tests for dependency_currency.py: lookup crashes (http.client.IncompleteRead), Maven lockfile.json, Gradle plugins and drift,
Go go.sum drift, runtime EOL rows from composer/Maven/Gradle, and per-package vendored rows. Fictional fixtures, every HTTP call mocked."""
import time, ast, contextlib, http.client, io, json, os, re, sys, tempfile, unittest, urllib.error, urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_dependency_currency as base

dc, J = base.dc, json.dumps


def table(**extra):
    """Base mocked registries plus php, Java and Gradle plugin-portal routes, plus `extra`."""
    t = dict(base.routes())
    t.update({
        "endoflife.date/api/php.json": J([{"cycle": "8.4", "eol": "2028-12-31", "latest": "8.4.1", "lts": False}, {"cycle": "8.0", "eol": "2023-11-26", "latest": "8.0.30", "lts": False},
                                          {"cycle": "7.4", "eol": "2022-11-28", "latest": "7.4.33", "lts": False}]),
        "endoflife.date/api/eclipse-temurin.json": J([{"cycle": "25", "eol": "2031-09-30", "latest": "25.0.1", "lts": "2025-09-16"}, {"cycle": "17", "eol": "2029-10-31", "latest": "17.0.9", "lts": "2021-09-14"},
                                                      {"cycle": "8", "eol": "2022-03-31", "latest": "8.0.400", "lts": "2014-03-18"}]),
        "plugins.gradle.org/m2/org/fict/plug/org.fict.plug.gradle.plugin/maven-metadata.xml": "<metadata><versions><version>1.0.0</version><version>1.1.0</version></versions></metadata>",
        "plugins.gradle.org/m2/org/fict/tp/org.fict.tp.gradle.plugin/maven-metadata.xml": "<metadata><versions><version>2.0.0</version></versions></metadata>",
    })
    t.update(extra)
    return t


class Resp:
    """Fake urlopen response."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return b"{}"


class Cov(unittest.TestCase):
    """Each test is one item of the detector coverage fix."""
    run_dc = base.T.run_dc

    def statuses(self, f=None, kind=None):
        """(name, status) pairs of the last run's rows, optionally filtered by file and kind."""
        return {(r["name"], r["status"]) for r in self.rows if (f is None or r["file"] == f) and (kind is None or r["kind"] == kind)}

    def test_incomplete_read_retried_then_oserror(self):
        """IncompleteRead is not an OSError: Net.get retries once, then raises OSError (never leaks HTTPException)."""
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise http.client.IncompleteRead(b"x")
        with mock.patch.object(urllib.request, "urlopen", boom), mock.patch.object(dc, "BACKOFF", 0):
            with self.assertRaises(OSError):
                dc.Net().get("https://example.com/a")
        self.assertEqual(len(calls), 3)
        seq = [http.client.IncompleteRead(b"x"), Resp()]

        def flaky(*a, **k):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with mock.patch.object(urllib.request, "urlopen", flaky), mock.patch.object(dc, "BACKOFF", 0):
            self.assertEqual(dc.Net().get("https://example.com/b"), "{}")

    def test_lookup_exception_never_exits_nonzero(self):
        """Any exception from one lookup becomes a not-checked row naming it; main() still exits 0 and keeps the other rows."""
        ok = base.fake(base.routes())

        def get(url, data=None, headers=None):
            if "fict-npm" in url:
                raise http.client.IncompleteRead(b"x")
            if "fict-py" in url:
                raise RuntimeError("weird")
            return ok(url, data, headers)
        with tempfile.TemporaryDirectory() as d:
            for n, c in (("package-lock.json", base.lock(**{"fict-npm": "1.0.0", "fict-dep": "2.0.0"})), ("requirements.txt", "fict-py==1.0\n")):
                with open(os.path.join(d, n), "w") as fh:
                    fh.write(c)
            dc.net = dc.Net()
            dc.net.get = get
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO("package-lock.json\nrequirements.txt\n")):
                self.assertEqual(dc.main(["--root", d, "--stdin", "--today", base.TODAY]), 0)
        self.assertRegex(out.getvalue(), r"not-checked\t.*fict-npm.*IncompleteRead")
        self.assertRegex(out.getvalue(), r"not-checked\t.*fict-py.*RuntimeError")

    def test_maven_lockfile_transitive_and_drift(self):
        """lockfile.json children are checked for currency; a pom version that differs from the lock is drift."""
        pom = '<project><dependencies><dependency><groupId>org.fict</groupId><artifactId>lib</artifactId><version>1.0.0</version></dependency></dependencies></project>'
        lock = J({"groupId": "org.fict", "artifactId": "app", "dependencies": [{"groupId": "org.fict", "artifactId": "lib", "version": "1.2.0", "children": [
            {"groupId": "org.fict", "artifactId": "glib", "version": "4.0.0", "children": []}]}]})
        self.run_dc(table=table(), files={"m/pom.xml": pom, "m/lockfile.json": lock})
        self.assertIn(("org.fict:glib", "outdated"), self.statuses("m/lockfile.json"))
        self.assertIn(("org.fict:lib", "drift"), self.statuses("m/pom.xml"))

    def test_gradle_plugins_and_drift(self):
        """plugins{} and versions.toml [plugins] resolve through marker artifacts; build.gradle vs gradle.lockfile drift; no duplicate rows."""
        bg = "plugins {\n  id 'org.fict.plug' version '1.0.0'\n}\ndependencies {\n  implementation 'org.fict:lib:1.0.0'\n  testImplementation 'org.fict:lib:1.0.0'\n}\n"
        toml = '[versions]\nplug = "2.0.0"\n[plugins]\nfp = { id = "org.fict.tp", version.ref = "plug" }\n'
        self.run_dc(table=table(), files={"g/build.gradle": bg, "g/gradle.lockfile": "org.fict:lib:0.9.0=runtimeClasspath\n", "g/libs.versions.toml": toml})
        self.assertIn(("org.fict.plug:org.fict.plug.gradle.plugin", "outdated"), self.statuses("g/build.gradle"))
        self.assertIn(("org.fict.tp:org.fict.tp.gradle.plugin", "current"), self.statuses("g/libs.versions.toml"))
        self.assertIn(("org.fict:lib", "drift"), self.statuses("g/build.gradle"))
        keys = [(r["file"], r["kind"], r["name"], r["current"], r["status"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_go_sum_drift(self):
        """A go.mod require whose version is not in go.sum is drift; a matching go.sum line is clean."""
        gm = "module example.com/app\n\nrequire example.com/fictmod/v2 v2.1.0\n"
        self.run_dc(table=table(), files={"a/go.mod": gm, "a/go.sum": "example.com/fictmod/v2 v2.0.0 h1:abc=\n", "b/go.mod": gm, "b/go.sum": "example.com/fictmod/v2 v2.1.0 h1:abc=\nexample.com/fictmod/v2 v2.1.0/go.mod h1:def=\n"})
        self.assertIn(("example.com/fictmod/v2", "drift"), self.statuses("a/go.mod"))
        self.assertNotIn("drift", {s for _, s in self.statuses("b/go.mod")})

    def test_runtime_eol_composer_and_java(self):
        """composer platform.php beats require.php; Maven release/java.version and Gradle toolchain give Java EOL rows."""
        files = {"p1/composer.json": J({"require": {"php": ">=7.4"}, "config": {"platform": {"php": "8.0.2"}}}),
                 "p2/composer.json": J({"require": {"php": "^7.4 || ^8.0"}}),
                 "j1/pom.xml": "<project><properties><maven.compiler.release>17</maven.compiler.release></properties></project>",
                 "j2/pom.xml": "<project><properties><java.version>1.8</java.version></properties></project>",
                 "j3/build.gradle": "java {\n  toolchain { languageVersion = JavaLanguageVersion.of(8) }\n}\n"}
        self.run_dc(table=table(), files=files)
        rt = {r["file"]: r for r in self.rows if r["kind"] == "runtime"}
        self.assertEqual((rt["p1/composer.json"]["current"], rt["p1/composer.json"]["status"]), ("8.0.2", "eol"))
        self.assertEqual((rt["p2/composer.json"]["current"], rt["p2/composer.json"]["status"]), ("7.4", "eol"))
        self.assertEqual(rt["j1/pom.xml"]["status"], "outdated")
        self.assertEqual(rt["j1/pom.xml"]["current"], "17")
        self.assertEqual((rt["j2/pom.xml"]["current"], rt["j2/pom.xml"]["status"]), ("8", "eol"))
        self.assertEqual((rt["j3/build.gradle"]["current"], rt["j3/build.gradle"]["status"]), ("8", "eol"))

    def test_vendored_one_row_per_package(self):
        """Each vendored package dir gets its own row, named from its manifest (else its dir name)."""
        files = {"vendor/acme-a/package.json": J({"name": "fict-a"}), "vendor/acme-a/index.js": "x", "vendor/b/composer.json": J({"name": "fict/b"}),
                 "vendor/b/src/x.php": "x", "vendor/plain/f.js": "x", "vendor/plain/g.js": "x"}
        self.run_dc(table=table(), files=files)
        v = {r["file"]: r["name"] for r in self.rows if r["kind"] == "vendored"}
        self.assertEqual(v, {"vendor/acme-a": "fict-a", "vendor/b": "fict/b", "vendor/plain": "plain"})

    def test_review_fold(self):
        """Review fixes: hostile vendored JSON, go.sum /go.mod lines, gradle lock direction, composer bounds, vendored cap and names, retry budget, toml order."""
        # 1 + 6: deep JSON and control-char names fall back to the dir name; no crash
        files = {"vendor/deep/package.json": "[" * 100000, "vendor/ctl/package.json": J({"name": "bad\x1b[31mname"}), "vendor/ok/package.json": J({"name": "fict-ok"})}
        self.run_dc(table=table(), files=files)
        self.assertEqual({r["file"]: r["name"] for r in self.rows if r["kind"] == "vendored"}, {"vendor/deep": "deep", "vendor/ctl": "ctl", "vendor/ok": "fict-ok"})
        # 2: go.sum with only the /go.mod line is not drift
        gm = "module example.com/app\n\nrequire example.com/fictmod/v2 v2.1.0\n"
        self.run_dc(table=table(), files={"go.mod": gm, "go.sum": "example.com/fictmod/v2 v2.1.0/go.mod h1:def=\n"})
        self.assertNotIn("drift", {r["status"] for r in self.rows})
        # 3: any exact declared-vs-locked mismatch is drift, lock above declared says conflict resolution; declared but absent from the lock is drift
        bg = "dependencies {\n  implementation 'org.fict:lib:1.0.0'\n  implementation 'org.fict:glib:4.0.0'\n}\n"
        self.run_dc(table=table(), files={"build.gradle": bg, "gradle.lockfile": "org.fict:lib:1.2.0=x\n"})
        self.assertEqual({r["name"] for r in self.rows if r["status"] == "drift"}, {"org.fict:glib", "org.fict:lib"})
        self.assertIn("conflict resolution", next(r["note"] for r in self.rows if r["name"] == "org.fict:lib" and r["status"] == "drift"))
        # 4: upper bounds ignored, lowest lower bound wins, note says allows
        self.run_dc(table=table(), files={"a/composer.json": J({"require": {"php": "<8.1"}}), "b/composer.json": J({"require": {"php": ">=7.4 <8.4"}})})
        rt = {r["file"]: r for r in self.rows if r["kind"] == "runtime"}
        self.assertNotIn("a/composer.json", rt)
        self.assertEqual(rt["b/composer.json"]["current"], "7.4")
        self.assertIn("allows EOL php 7.4", rt["b/composer.json"]["note"])
        # 5: cap + overflow row
        self.run_dc(table=table(), files={f"vendor/p{i:03d}/a.js": "x" for i in range(dc.VENDOR_CAP + 5)})
        self.assertEqual(len([r for r in self.rows if r["kind"] == "vendored"]), dc.VENDOR_CAP)
        self.assertEqual(len([r for r in self.rows if r["status"] == "not-checked" and "5 more vendored" in r["note"]]), 1)
        # 8: [versions] after [plugins]
        toml = '[plugins]\nfp = { id = "org.fict.tp", version.ref = "plug" }\n[versions]\nplug = "2.0.0"\n'
        self.run_dc(table=table(), files={"libs.versions.toml": toml})
        self.assertIn(("org.fict.tp:org.fict.tp.gradle.plugin", "current"), self.statuses())

    def test_retry_rechecks_deadline_and_rate(self):
        """The second attempt re-runs the DEADLINE check and the per-host rate wait."""
        sleeps, n = [], dc.Net()

        def boom(*a, **k):
            dc.DEADLINE = 1.0  # budget gone after attempt 1
            raise http.client.IncompleteRead(b"x")
        try:
            with mock.patch.object(urllib.request, "urlopen", boom):
                with self.assertRaisesRegex(OSError, "time budget"):
                    n.get("https://example.com/a")
        finally:
            dc.DEADLINE = None
        calls = []

        def boom2(*a, **k):
            calls.append(1)
            raise http.client.IncompleteRead(b"x")
        with mock.patch.object(urllib.request, "urlopen", boom2), mock.patch.object(dc.time, "sleep", sleeps.append), mock.patch.object(dc, "BACKOFF", 0):
            with self.assertRaises(OSError):
                dc.Net().get("https://crates.io/api/v1/crates/z")
        self.assertEqual((len(calls), len(sleeps)), (3, 2))  # rate wait redone before attempts 2 and 3
        self.assertTrue(all(x > 0.9 for x in sleeps), sleeps)

    def test_dcf_regex_matches_every_parsed_filename(self):
        """review_checks.sh's dcf manifest regex (read from the script) matches every filename the detector parses, lockfile.json included."""
        src = open(os.path.join(base.HERE, "..", ".claude/skills/deep-code-review/scripts/review_checks.sh")).read()
        rx = re.compile(re.search(r"^dcf=.*?grep -E '([^']+)'", src, re.M)[1])
        names = ["package-lock.json", "package.json", "yarn.lock", "pnpm-lock.yaml", "requirements.txt", "requirements-dev.in", "poetry.lock", "Pipfile.lock", "pyproject.toml",
                 "Cargo.lock", "Cargo.toml", "composer.lock", "composer.json", "go.mod", "pom.xml", "lockfile.json", "build.gradle", "build.gradle.kts", "gradle.lockfile",
                 "libs.versions.toml", "Dockerfile", "app.Dockerfile", "docker-compose.yml", "action.yml", ".nvmrc", ".node-version", ".python-version", ".ruby-version",
                 ".github/workflows/ci.yml"]
        self.assertEqual([n for n in names if not rx.search("sub/dir/" + n)], [])

    def test_framework_eol_via_gradle_plugin_and_bom(self):
        """spring-boot EOL comes from a Gradle plugin id, a versions.toml plugin and a Maven BOM import."""
        t = table(**{"endoflife.date/api/spring-boot.json": J([{"cycle": "3.5", "eol": "2032-01-01", "latest": "3.5.0", "lts": False}, {"cycle": "3.2", "eol": "2024-11-23", "latest": "3.2.12", "lts": False}]),
                     "plugins.gradle.org/m2/org/springframework/boot/org.springframework.boot.gradle.plugin/maven-metadata.xml": "<metadata><versions><version>3.2.0</version><version>3.5.0</version></versions></metadata>",
                     "maven2/org/springframework/boot/spring-boot-dependencies/maven-metadata.xml": "<metadata><versions><version>3.2.0</version></versions></metadata>"})
        bom = '<project><dependencyManagement><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-dependencies</artifactId><version>3.2.0</version><type>pom</type><scope>import</scope></dependency></dependencies></dependencyManagement></project>'
        for f, c in (("g/build.gradle", "plugins {\n id 'org.springframework.boot' version '3.2.0'\n}\n"),
                     ("g/libs.versions.toml", '[versions]\nsb = "3.2.0"\n[plugins]\nsb = { id = "org.springframework.boot", version.ref = "sb" }\n'), ("m/pom.xml", bom)):
            self.run_dc(table=t, files={f: c})
            self.assertEqual([(r["name"], r["status"]) for r in self.rows if r["kind"] == "runtime" and r["file"] == f], [("spring-boot", "eol")], f)
        for k in ("org.springframework.boot:org.springframework.boot.gradle.plugin", "org.springframework.boot:spring-boot-dependencies"):
            self.assertEqual(dc.FRAMEWORKS[("gradle", k)], "spring-boot")

    def test_metadata_latest_is_deterministic(self):
        """Latest is the highest stable <versions> entry: <latest>/<release> are ignored and a truncated metadata body is retried, never used."""
        full = "<metadata><latest>9.9.9</latest><release>9.9.9</release><versions><version>1.0.0</version><version>1.2.0</version><version>1.3.0-SNAPSHOT</version></versions></metadata>"
        dc.net = dc.Net()
        dc.net.get = lambda *a, **k: full
        self.assertEqual(dc.versions("maven", "org.fict:lib"), ["1.0.0", "1.2.0"])
        bodies = ["<metadata><versions><version>1.0.0</version>", full]

        class R(Resp):
            def read(self, n=-1): return bodies.pop(0).encode()
        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: R()), mock.patch.object(dc, "BACKOFF", 0):
            self.assertEqual(dc.Net().get("https://repo1.maven.org/maven2/org/fict/lib/maven-metadata.xml"), full)
        bodies[:] = ["<metadata><versions><version>1.0.0</version>"] * 3
        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: R()), mock.patch.object(dc, "BACKOFF", 0):
            with self.assertRaises(OSError):
                dc.Net().get("https://repo1.maven.org/maven2/org/fict/other/maven-metadata.xml")

    def test_go_directive_is_a_minimum(self):
        """`go X` gives a row only when its cycle is EOL; `toolchain goX` is a pin and can be outdated."""
        cyc = lambda e: J([{"cycle": "1.25", "eol": "2027-08-01", "latest": "1.25.3", "lts": False}, {"cycle": "1.22", "eol": e, "latest": "1.22.9", "lts": False}])
        gm = "module example.com/app\n\ngo 1.22\n\ntoolchain go1.22.3\n"
        self.run_dc(table=table(**{"endoflife.date/api/go.json": cyc("2025-02-01")}), files={"go.mod": gm})
        st = {r["name"]: r["status"] for r in self.rows if r["kind"] == "runtime"}
        self.assertEqual(st, {"go directive": "eol", "go toolchain": "eol"})
        self.run_dc(table=table(**{"endoflife.date/api/go.json": cyc("2099-01-01")}), files={"go.mod": gm})
        st = {r["name"]: r["status"] for r in self.rows if r["kind"] == "runtime"}
        self.assertEqual(st, {"go directive": "current", "go toolchain": "outdated"})

    def test_transient_statuses_retried_with_backoff(self):
        """429 and 5xx are retried with doubling backoff; 3 failures give one OSError and one circuit strike, not an open circuit; 404 is not retried."""
        def err(code):
            return urllib.error.HTTPError("https://example.com/x", code, "x", {}, None)
        seq, sleeps = [err(503), err(429), Resp()], []

        def go(*a, **k):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        n = dc.Net()
        with mock.patch.object(urllib.request, "urlopen", go), mock.patch.object(dc.time, "sleep", sleeps.append):
            self.assertEqual(n.get("https://example.com/x"), "{}")
        self.assertEqual(sleeps, [1.0, 2.0])
        calls = []

        def down(*a, **k):
            calls.append(1)
            raise urllib.error.URLError("reset")
        with mock.patch.object(urllib.request, "urlopen", down), mock.patch.object(dc, "BACKOFF", 0):
            for u in ("a", "b"):
                with self.assertRaises(OSError):
                    n.get("https://example.org/" + u)
        self.assertEqual(len(calls), 6)  # circuit still closed after 2 lookups
        calls.clear()

        def nf(*a, **k):
            calls.append(1)
            raise err(404)
        with mock.patch.object(urllib.request, "urlopen", nf):
            with self.assertRaises(dc.NotFound):
                dc.Net().get("https://example.com/nf")
        self.assertEqual(len(calls), 1)

    def test_json_decode_error_retried(self):
        """A truncated JSON body (no transport error) is refetched; three bad bodies raise ValueError."""
        bodies = ['{"a": "unterm', '{"a": "unterm', '{"a": 1}']

        class R(Resp):
            def read(self, n=-1): return bodies.pop(0).encode()
        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: R()), mock.patch.object(dc, "BACKOFF", 0):
            self.assertEqual(dc.Net().json("https://crates.io/api/v1/crates/x"), {"a": 1})
            bodies[:] = ['{"a": "unterm'] * 3
            with self.assertRaises(ValueError):
                dc.Net().json("https://example.com/j")
        self.assertEqual(bodies, [])

    def test_github_token_and_ls_remote_fallback(self):
        """GH_TOKEN is sent to api.github.com only; a 403/429 falls back to git ls-remote: highest stable tag, no pre-releases or peels."""
        seen = []

        def spy(req, timeout=0):
            seen.append(dict(req.header_items()))
            return Resp()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "tok-123", "GITHUB_TOKEN": ""}), mock.patch.object(urllib.request, "urlopen", spy):
            dc.Net().get("https://api.github.com/repos/acme/x/releases/latest")
            dc.Net().get("https://example.com/y")
        self.assertEqual(seen[0].get("Authorization"), "Bearer tok-123")
        self.assertNotIn("Authorization", seen[1])
        ls = "\n".join(f"{'a' * 40}\trefs/tags/{t}" for t in ("v4", "v4.2.0", "v4.2.0^{}", "v5.0.0-rc1", "v4.10.1", "notes"))
        for code in (403, 429):
            dc.net = dc.Net()
            dc.net.get = mock.Mock(side_effect=OSError(f"https://api.github.com/x: HTTP {code}"))
            with mock.patch.object(dc.subprocess, "run", return_value=mock.Mock(stdout=ls)) as run:
                self.assertEqual(dc.gh_latest("acme/fict-action"), "v4.10.1")
            self.assertEqual(run.call_args[0][0], ["git", "-c", "credential.helper=", "ls-remote", "--tags", "https://github.com/acme/fict-action"])
        with mock.patch.object(dc.subprocess, "run", return_value=mock.Mock(stdout="")):
            with self.assertRaises(OSError):
                dc.gh_latest("acme/fict-action")
        dc.net.get = mock.Mock(side_effect=OSError("https://api.github.com/x: HTTP 500"))
        with mock.patch.object(dc.subprocess, "run") as run:
            with self.assertRaises(OSError):
                dc.gh_latest("acme/fict-action")
        run.assert_not_called()

    def test_tables_are_pure_literals(self):
        """FRAMEWORKS and IMAGES stay ast.literal_eval-able (consumers read them from the source without importing it)."""
        with open(os.path.join(base.HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py")) as fh:
            tree = ast.parse(fh.read())
        for name in ("FRAMEWORKS", "IMAGES"):
            val = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name)
            self.assertEqual(ast.literal_eval(val), getattr(dc, name))

    def test_review_round6(self):
        """Token not copied on redirect; tags-API 403 falls back to ls-remote in a neutral cwd without credential helpers; foreign lockfile.json skipped."""
        import email.message, tempfile
        with mock.patch.dict(os.environ, {"GH_TOKEN": "tok-123"}):
            req = urllib.request.Request("https://api.github.com/x")
            req.add_unredirected_header("Authorization", "Bearer tok-123")
            new = urllib.request.HTTPRedirectHandler().redirect_request(req, None, 302, "Found", email.message.Message(), "https://objects.example.com/y")
            self.assertNotIn("Authorization", dict(new.header_items()))
            seen = []
            with mock.patch.object(urllib.request, "urlopen", lambda r, timeout=0: seen.append(r) or Resp()):
                dc.Net().get("https://api.github.com/repos/acme/x/releases/latest")
            self.assertEqual(seen[0].unredirected_hdrs.get("Authorization"), "Bearer tok-123")
            self.assertNotIn("Authorization", seen[0].headers)
        dc.net = dc.Net()
        dc.net.get = lambda url, *a, **k: (_ for _ in ()).throw(dc.NotFound(url) if "releases/latest" in url else OSError(f"{url}: HTTP 403"))
        ls = f"{'a' * 40}\trefs/tags/v1.2.0\n"
        with mock.patch.object(dc.subprocess, "run", return_value=mock.Mock(stdout=ls)) as run:
            self.assertEqual(dc.gh_latest("acme/fict-action"), "v1.2.0")
        self.assertEqual(run.call_args[0][0][:3], ["git", "-c", "credential.helper="])
        self.assertEqual(run.call_args[1]["cwd"], tempfile.gettempdir())
        for body in ('{"dependencies": {"a": "1"}}', "not json", "[1]"):
            self.run_dc(table=table(), files={"x/lockfile.json": body})
            self.assertEqual([r for r in self.rows if r["file"] == "x/lockfile.json"], [], body)

    def test_hard_budget_returns_rows_and_not_checked(self):
        """A stuck Net with --budget 1 returns within ~2s: finished rows kept, one not-checked row per pending lookup, STUCK set so main() os._exit()s."""
        import threading
        gate, ok = threading.Event(), base.fake(base.routes())

        def slow(url, data=None, headers=None):
            if "fict-npm" in url:
                gate.wait(30)
            return ok(url, data, headers)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "package-lock.json"), "w") as fh:
                fh.write(base.lock(**{"fict-npm": "1.0.0", "fict-dep": "2.0.0"}))
            dc.net = dc.Net()
            dc.net.get = slow
            t0 = time.time()
            try:
                rows = dc.run(d, ["package-lock.json"], base.TODAY, budget=1)
            finally:
                gate.set()
                dc.DEADLINE = None  # a stuck run keeps its deadline on purpose
        self.assertLess(time.time() - t0, 4)
        st = {r["name"]: r for r in rows}
        self.assertEqual(st["fict-npm"]["status"], "not-checked")
        self.assertIn("time budget exhausted", st["fict-npm"]["note"])
        self.assertEqual(st["fict-dep"]["status"], "current")
        self.assertTrue(dc.STUCK)

    def test_main_budget_exits_fast_with_rows(self):
        """main() with a tiny budget over many deps (queued lookups get cancelled) prints not-checked rows and returns/exits 0 quickly."""
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "package-lock.json"), "w") as fh:
                fh.write(base.lock(**{f"fict-n{i}": "1.0.0" for i in range(300)}))
            dc.net = dc.Net()
            dc.net.get = lambda *a, **k: time.sleep(0.2) or (_ for _ in ()).throw(dc.NotFound("x"))
            out, t0 = io.StringIO(), time.time()
            with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO("package-lock.json\n")), mock.patch.object(dc.os, "_exit", side_effect=SystemExit(0)):
                try:
                    self.assertEqual(dc.main(["--root", d, "--stdin", "--budget", "0.5", "--today", base.TODAY]), 0)
                except SystemExit as e:
                    self.assertEqual(e.code, 0)
        dc.DEADLINE = None
        self.assertLess(time.time() - t0, 3)
        self.assertGreaterEqual(out.getvalue().count("time budget exhausted"), 100)

    def test_catalog_and_pnpm_drift(self):
        """versions.toml version.ref feeds gradle drift; pnpm drift uses the direct installs (v9 importers, v6 top-level, v5 inline), not transitive copies."""
        toml = '[versions]\nlib = "2.10.1"\n[libraries]\nl = { module = "org.fict:lib", version.ref = "lib" }\n'
        self.run_dc(table=table(), files={"libs.versions.toml": toml, "gradle.lockfile": "org.fict:lib:1.2.0=x\n"})
        self.assertIn(("org.fict:lib", "drift"), self.statuses("libs.versions.toml"))
        pj = J({"dependencies": {"fict-npm": "^4.4.0"}})
        v9 = ("lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies:\n      fict-npm:\n        specifier: ^4.4.0\n        version: 4.1.6(x@1.0.0)\n"
              "packages:\n  fict-npm@4.1.6:\n    resolution: {}\n  other@1.0.0:\n    resolution: {}\n  fict-npm@4.9.0:\n    resolution: {}\n")
        v6 = "lockfileVersion: '6.0'\ndependencies:\n  fict-npm:\n    specifier: ^4.4.0\n    version: 4.1.6\npackages:\n  /fict-npm@4.1.6:\n    x: 1\n  /fict-npm@4.9.0:\n    x: 1\n"
        v5 = "lockfileVersion: 5.4\nspecifiers:\n  fict-npm: ^4.4.0\ndependencies:\n  fict-npm: 4.1.6\npackages:\n  /fict-npm/4.1.6:\n    x: 1\n  /fict-npm/4.9.0:\n    x: 1\n"
        for lk in (v9, v6, v5):
            self.run_dc(table=table(), files={"package.json": pj, "pnpm-lock.yaml": lk})
            self.assertIn(("fict-npm", "drift"), self.statuses("package.json"), lk[:20])

    def test_catalog_standard_layout_drift(self):
        """gradle/libs.versions.toml drifts against gradle.lockfile at the project root and in module dirs (union)."""
        toml = '[versions]\nlib = "2.10.1"\nglib = "4.0.0"\n[libraries]\nl = { module = "org.fict:lib", version.ref = "lib" }\ng = { module = "org.fict:glib", version.ref = "glib" }\n'
        self.run_dc(table=table(), files={"p/gradle/libs.versions.toml": toml, "p/gradle.lockfile": "org.fict:lib:2.8.9=x\n", "p/app/gradle.lockfile": "org.fict:glib:4.1.0=x\n"})
        self.assertEqual({n for n, s in self.statuses("p/gradle/libs.versions.toml") if s == "drift"}, {"org.fict:lib", "org.fict:glib"})  # glib: lock above declared, both directions drift
        self.run_dc(table=table(), files={"gradle/libs.versions.toml": toml, "gradle.lockfile": "org.fict:lib:2.8.9=x\n"})
        self.assertIn(("org.fict:lib", "drift"), self.statuses("gradle/libs.versions.toml"))

    def test_pnpm_workspace_importer_drift(self):
        """A workspace pnpm-lock at the repo root drifts against apps/web/package.json using that importer's direct installs."""
        lk = ("lockfileVersion: '9.0'\nimporters:\n  apps/web:\n    dependencies:\n      fict-npm:\n        specifier: ^4.4.0\n        version: 4.1.6\n"
              "  apps/other:\n    dependencies:\n      fict-npm:\n        specifier: ^4.1.0\n        version: 4.9.0\n"
              "packages:\n  fict-npm@4.1.6:\n    x: 1\n  fict-npm@4.9.0:\n    x: 1\n")
        self.run_dc(table=table(), files={"pnpm-lock.yaml": lk, "apps/web/package.json": J({"dependencies": {"fict-npm": "^4.4.0"}}),
                                          "apps/other/package.json": J({"dependencies": {"fict-npm": "^4.1.0"}})})
        self.assertIn(("fict-npm", "drift"), self.statuses("apps/web/package.json"))
        self.assertNotIn("drift", {s for _, s in self.statuses("apps/other/package.json")})

    def test_round9_gradle_scope_and_pnpm_importer(self):
        """Root build.gradle uses its same-dir lock only; catalogs emit no 'no entry' rows; empty importers and v5 peer suffixes do not leak transitive versions."""
        bg = "dependencies {\n  implementation 'org.fict:lib:1.0.0'\n}\n"
        self.run_dc(table=table(), files={"build.gradle": bg, "app/gradle.lockfile": "org.fict:glib:4.1.0=x\n"})
        self.assertEqual([r for r in self.rows if r["status"] == "drift"], [])  # module lock must not make root 'missing'
        toml = '[versions]\nlib = "1.0.0"\n[libraries]\nl = { module = "org.fict:lib", version.ref = "lib" }\n'
        self.run_dc(table=table(), files={"gradle/libs.versions.toml": toml, "gradle.lockfile": "org.fict:glib:4.1.0=x\n"})
        self.assertEqual([r for r in self.rows if r["status"] == "drift"], [])
        lk = ("lockfileVersion: '9.0'\nimporters:\n  .: {}\n  apps/web:\n    dependencies:\n      fict-npm:\n        specifier: ^4.4.0\n        version: 4.9.0\n"
              "packages:\n  fict-npm@4.9.0:\n    x: 1\n")
        self.run_dc(table=table(), files={"pnpm-lock.yaml": lk, "package.json": J({"dependencies": {"fict-npm": "^4.4.0"}})})
        self.assertIn(("fict-npm", "drift"), self.statuses("package.json"))  # root importer is empty: transitive 4.9.0 must not stand in
        self.assertEqual(dc.p_pnpm_root("dependencies:\n  fict-npm: 4.1.6_react@18.0.0\n")["."], {"fict-npm": "4.1.6"})


    def test_round10_cap_images_gradle_workspaces(self):
        """Per-host cap lets PyPI exceed 5 MB (still capped); image latest comes from Hub tags, mongo maps, unmapped library images use Hub; gradle drift both ways; npm workspaces pair with the ancestor lock."""
        class Big(Resp):
            def __init__(self, n): self.n = n
            def read(self, n=-1): return b"x" * min(self.n, n)
        for url, size, ok in (("https://pypi.org/pypi/x/json", 6 << 20, True), ("https://pypi.org/pypi/x/json", 33 << 20, False), ("https://example.com/x", 6 << 20, False)):
            with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: Big(size)), mock.patch.object(dc, "BACKOFF", 0):
                if ok:
                    self.assertEqual(len(dc.Net().get(url)), size)
                else:
                    with self.assertRaises(OSError):
                        dc.Net().get(url)
        hub = lambda *names: J({"results": [{"name": n} for n in names]})
        t = table(**{"endoflife.date/api/mysql.json": J([{"cycle": "26.10", "eol": "2030-01-01", "latest": "26.10.0"}, {"cycle": "9.7", "eol": "2030-01-01", "latest": "9.7.4", "lts": True}]),
                     "endoflife.date/api/mongodb.json": J([{"cycle": "7.0", "eol": "2030-01-01", "latest": "7.0.1"}]),
                     "library/mysql/tags/9.7.4": J({"name": "9.7.4"}), "library/mysql/tags": hub("26.10.0", "9.7.4"), "library/mongo/tags": hub("8.0.1", "8.0", "7.0.1"), "library/busybox/tags": hub("1.37.0", "1.36.1", "1.37.0-uclibc")})
        df = "FROM mysql:9.7.1\nFROM mongo:7.0.1\nFROM busybox:1.36.1\n"
        r = self.run_dc(table=t, files={"Dockerfile": df})
        self.assertEqual((r[("Dockerfile", "mysql")]["latest"], r[("Dockerfile", "mysql")]["status"]), ("9.7.4", "outdated"))  # not the feed's 26.10.0
        self.assertEqual((r[("Dockerfile", "mongo")]["latest"], r[("Dockerfile", "mongo")]["status"]), ("8.0.1", "outdated"))
        b = r[("Dockerfile", "busybox")]
        self.assertEqual((b["latest"], b["target"]), ("1.37.0", "busybox:1.37.0"))  # no EOL product: Hub tags only
        toml = '[versions]\nm = "1.12.0"\n[libraries]\nm = { group = "org.fict", name = "lib", version.ref = "m" }\n'
        self.assertEqual(dc.p_gradle(toml, "libs.versions.toml")[0], [("org.fict:lib", "1.12.0")])  # group/name catalog form
        # gradle: lock above or below declared is drift
        bg = "dependencies {\n  implementation 'org.fict:lib:1.2.0'\n  implementation 'org.fict:glib:4.0.0'\n}\n"
        self.run_dc(table=table(), files={"build.gradle": bg, "gradle.lockfile": "org.fict:lib:1.0.0=x\norg.fict:glib:4.1.0=x\n"})
        d = {r["name"]: r["note"] for r in self.rows if r["status"] == "drift"}
        self.assertEqual(set(d), {"org.fict:lib", "org.fict:glib"})
        self.assertIn("conflict resolution", d["org.fict:glib"])
        self.assertNotIn("conflict resolution", d["org.fict:lib"])
        # npm workspace: own node_modules copy wins, hoisted copy otherwise, linked siblings skipped
        lock = J({"lockfileVersion": 3, "packages": {"": {"workspaces": ["apps/*"]}, "apps/web": {}, "apps/cli": {}, "node_modules/fict-npm": {"version": "4.9.0"},
                                                      "apps/web/node_modules/fict-npm": {"version": "1.0.0"}, "node_modules/fict-dep": {"version": "2.0.0"}, "node_modules/web-sibling": {"resolved": "apps/x", "link": True}}})
        pj = lambda **d: J({"dependencies": d})
        files = {"package-lock.json": lock, "package.json": J({"workspaces": ["apps/*"]}), "apps/web/package.json": pj(**{"fict-npm": "^4.4.0", "web-sibling": "*"}),
                 "apps/cli/package.json": pj(**{"fict-npm": "^4.4.0", "fict-dep": "^1.0.0"}), "other/package.json": pj(**{"fict-npm": "^4.4.0"})}
        self.run_dc(table=table(), files=files)
        self.assertEqual({(f, n) for f in files for n, s in self.statuses(f) if s == "drift"}, {("apps/web/package.json", "fict-npm"), ("apps/cli/package.json", "fict-dep")})

    def test_round11_review_fold(self):
        """Gradle 2.0==2.0.0 and pre-release declarations, npm workspace missing entry, Hub next host, stage aliases, LTS-aware fallback, bad JSON, exact-tag route, Hub down, pagination."""
        bg = "dependencies {\n  implementation 'org.fict:lib:2.0'\n  implementation 'org.fict:glib:4.0.0-SNAPSHOT'\n  implementation 'org.fict:hlib:5.0.0-rc1'\n}\n"
        self.run_dc(table=table(), files={"build.gradle": bg, "gradle.lockfile": "org.fict:lib:2.0.0=x\norg.fict:glib:4.1.0=x\norg.fict:hlib:5.0.0=x\n"})
        self.assertEqual([r for r in self.rows if r["status"] == "drift"], [])
        lock = J({"lockfileVersion": 3, "packages": {"": {}, "apps/web": {}}})
        files = {"package-lock.json": lock, "apps/web/package.json": J({"dependencies": {"fict-npm": "^1.0.0"}})}
        self.run_dc(table=table(), files=files)
        self.assertIn("no entry", next(r["note"] for r in self.rows if r["status"] == "drift"))
        hub = lambda *names, nxt=None: J({"results": [{"name": n} for n in names], "next": nxt})
        eol = {"endoflife.date/api/mongodb.json": J([{"cycle": "7.0", "eol": "2030-01-01", "latest": "7.0.1"}])}
        # next off hub.docker.com is not followed; bad JSON body is NOT RUN, not a crash
        seen = []
        t = table(**{"library/busybox/tags": hub("1.36.1", nxt="https://evil.example.com/p2")})
        g = base.fake(t)
        dc.net = dc.Net(); dc.net.get = lambda u, *a, **k: (seen.append(u), g(u, *a, **k))[1]
        self.assertEqual(dc.hub_latest("busybox", "1.36.1", ""), "1.36.1")
        self.assertFalse(any("evil.example.com" in u for u in seen))
        r = self.run_dc(table=table(**{"library/busybox/tags": "[1]"}), files={"Dockerfile": "FROM busybox:1.36.1\n"})
        self.assertEqual(r[("Dockerfile", "busybox")]["status"], "not-checked")
        # pagination: best tag on page 2; stage alias with a tag and non-library names make no Hub call
        p2 = "https://hub.docker.com/v2/repositories/library/busybox/tags?page=2"
        r = self.run_dc(table=table(**{"library/busybox/tags?page=2": hub("1.40.0"), "library/busybox/tags": hub("1.36.1", nxt=p2)}), files={"Dockerfile": "FROM busybox:1.36.1\n"})
        b = r[("Dockerfile", "busybox")]
        self.assertEqual(b["latest"], "1.40.0")
        self.assertIn("Docker Hub", b["note"])
        r = self.run_dc(table=table(), files={"Dockerfile": "FROM busybox:1.36.1 AS build\nFROM build:2.0\nFROM My_Img:1.0\n"})
        self.assertEqual(sum("no currency source" in x["note"] for x in self.rows), 2)
        # LTS-aware fallback: node:25 must not beat 24; exact feed tag absent so the Hub list decides
        r = self.run_dc(files={"Dockerfile": "FROM node:18-alpine\n"}, table=table(**{"library/node/tags/24.2.1-alpine": "{}", "library/node/tags": hub("25-alpine", "24-alpine", "22-alpine")}))
        self.assertEqual(r[("Dockerfile", "node")]["target"], "node:24-alpine")
        # exact-tag path: the feed's release is used when Hub has it (precise route key)
        r = self.run_dc(table=table(**eol, **{"library/mongo/tags/7.0.1": J({"name": "7.0.1"}), "library/mongo/tags": hub("8.0.1")}), files={"Dockerfile": "FROM mongo:7.0.0\n"})
        self.assertEqual(r[("Dockerfile", "mongo")]["latest"], "7.0.1")
        # Hub unreachable: an eol image keeps its eol row with latest unverified, a live one is NOT RUN
        old = {"endoflife.date/api/mongodb.json": J([{"cycle": "7.0", "eol": "2020-01-01", "latest": "7.0.1"}])}
        r = self.run_dc(table=table(**old), down=("hub.docker.com",), files={"Dockerfile": "FROM mongo:7.0.0\nFROM busybox:1.36.1\n"})
        self.assertEqual(r[("Dockerfile", "busybox")]["status"], "not-checked")
        self.assertEqual(r[("Dockerfile", "mongo")]["status"], "eol")
        self.assertIn("latest unverified", r[("Dockerfile", "mongo")]["note"])
        r = self.run_dc(table=table(**eol), down=("hub.docker.com",), files={"Dockerfile": "FROM mongo:7.0.0\n"})
        self.assertEqual(r[("Dockerfile", "mongo")]["status"], "not-checked")


if __name__ == "__main__":
    unittest.main()
