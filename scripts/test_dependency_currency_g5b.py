#!/usr/bin/env python3
"""Regression tests for dependency_currency.py root causes found by the set-5 scored run: requirement files in any directory and their -r/-c includes,
setup.cfg/pyproject-extras/Pipfile drift, rust-toolchain pins, a root Cargo.toml, Symfony components, unmapped image EOL, Kubernetes images,
npm workspaces absent from the lock's `packages`, Maven parent overrides and Gradle ext/property versions. Offline (every lookup mocked)."""
import importlib.util, os, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
TODAY = "2026-11-03"


def collect(files):
    """Write files (path -> text) to a temp repo and return dc.collect's (deps, rows)."""
    with tempfile.TemporaryDirectory() as d:
        for f, t in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
            with open(os.path.join(d, f), "w") as fh:
                fh.write(t)
        return dc.collect(d, sorted(files), TODAY)


def drifts(rows):
    """Names of the drift rows."""
    return sorted(r["name"] for r in rows if isinstance(r, dict) and r["status"] == "drift")


class Pip(unittest.TestCase):
    def test_requirements_dir_and_includes(self):
        """Pins in requirements/*.txt (any file name), constraints*.txt and files pulled in by -r/-c from any requirement file are read."""
        deps, _ = collect({"requirements/base.txt": "fict-a==1.0\n", "requirements/dev.txt": "-r base.txt\nfict-b==2.0\n", "constraints.txt": "fict-c==3.0\n",
                           "requirements.txt": "-r deploy/prod.pins\n", "deploy/prod.pins": "fict-d==4.0\n", "notes/other.txt": "fict-e==5.0\n"})
        self.assertEqual(sorted(n for _, _, n, _ in deps), ["fict-a", "fict-b", "fict-c", "fict-d"])

    def test_readme_in_requirements_dir_and_include_forms(self):
        """requirements/README.txt is not a requirement file; -rfile, -r=file, --requirement=file and trailing # comments resolve; a symlink out of the repo is refused."""
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as d:
            open(os.path.join(out, "secret.txt"), "w").write("fict-out==1.0\n")
            os.makedirs(os.path.join(d, "requirements"))
            for f, t in {"requirements/README.txt": "fict-readme==1.0\n", "requirements/a.txt": "fict-a==1\n", "requirements/b.txt": "fict-b==1\n", "requirements/c.txt": "fict-c==1\n",
                         "requirements.txt": "-rrequirements/a.txt # note\n-r=requirements/b.txt\n--requirement=requirements/c.txt\n-r link.txt\n"}.items():
                open(os.path.join(d, f), "w").write(t)
            os.symlink(os.path.join(out, "secret.txt"), os.path.join(d, "link.txt"))
            names = sorted(n for _, _, n, _ in dc.collect(d, sorted(["requirements.txt", "link.txt", "requirements/README.txt", "requirements/a.txt", "requirements/b.txt", "requirements/c.txt"]), TODAY)[0])
        self.assertEqual(names, ["fict-a", "fict-b", "fict-c"])

    def test_setup_cfg_junk_and_include_group(self):
        """setup.cfg file:/attr: values are skipped and a comma list on one line splits per requirement; a PEP 735 include-group is not a package."""
        self.assertEqual(dc.p_setup_cfg("[options]\ninstall_requires =\n    file: requirements.txt\n    fict-a>=1, fict-b>=2,<3\n    fict-c>=1,<2\n"),
                         [("fict-a", ">=1"), ("fict-b", ">=2,<3"), ("fict-c", ">=1,<2")])
        self.assertEqual(dc.p_pyproject('[dependency-groups]\ndev = ["fict-a>=1", {include-group = "fict-b>=9"}]\n'), [("fict-a", ">=1")])

    def test_setup_cfg_pyproject_extras_pipfile_drift(self):
        """Specs in setup.cfg (install_requires and extras), pyproject extras / dependency groups and a Pipfile drift against locks in the dir or its requirements/ dir."""
        _, rows = collect({"requirements/dev.txt": "fict-a==0.8\nfict-b==0.8\nfict-c==0.8\n",
                           "setup.cfg": "[options]\ninstall_requires =\n    fict-a>=0.9\n    fict-z\n[options.extras_require]\nx =\n    fict-b>=0.9\n",
                           "pyproject.toml": '[project.optional-dependencies]\ndev = ["fict-c>=0.9"]\n',
                           "svc/Pipfile": '[packages]\nfict-p = ">=3.0"\nfict-q = "*"\n', "svc/Pipfile.lock": '{"default": {"fict-p": {"version": "==2.1"}, "fict-q": {"version": "==1.0"}}}'})
        self.assertEqual(drifts(rows), ["fict-a", "fict-b", "fict-c", "fict-p"])


class Misc(unittest.TestCase):
    def test_root_cargo_toml_drift(self):
        """A Cargo.toml at the repo root pairs with the Cargo.lock beside it (no relpath crash)."""
        _, rows = collect({"Cargo.toml": '[dependencies]\nfict-serde = "2.0"\n', "Cargo.lock": '[[package]]\nname = "fict-serde"\nversion = "1.0.1"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n'})
        self.assertEqual(drifts(rows), ["fict-serde"])
        self.assertFalse([r for r in rows if isinstance(r, dict) and r["status"] == "not-checked"], rows)

    def test_rust_toolchain(self):
        """Bare rust-toolchain and rust-toolchain.toml pins give a rust runtime row; floating channels give none."""
        for f, t, want in (("rust-toolchain", "1.68.0\n", ["1.68.0"]), ("rust-toolchain.toml", '[toolchain]\nchannel = "1.70"\n', ["1.70"]),
                           ("rust-toolchain", "stable\n", []), ("rust-toolchain.toml", '[toolchain]\nchannel = "nightly-2023-05-01"\n', [])):
            _, rows = collect({f: t})
            self.assertEqual([r[3] for r in rows if isinstance(r, tuple) and r[2] == "rust"], want, (f, t))

    def test_framework_latest_is_newest_live_and_lts_is_a_channel_row(self):
        """latest stays the newest live cycle (a user on a newer non-LTS cycle is not called current); a boolean LTS cycle above an old user is an extra LTS-channel row; a dated lts is ignored."""
        cs = [{"cycle": "8.1", "eol": "2027-01-31", "latest": "8.1.10", "lts": False}, {"cycle": "8.0", "eol": "2027-01-01", "latest": "8.0.16", "lts": False},
              {"cycle": "7.4", "eol": "2029-11-30", "latest": "7.4.22", "lts": True}, {"cycle": "6.3", "eol": "2024-01-31", "latest": "6.3.12", "lts": False}]
        with mock.patch.object(dc, "cycles", lambda p, t: cs):
            self.assertEqual(dc.eol_check("symfony", "6.3.1", TODAY)[3], "8.1.10")
            r = dc.runtime_row("composer.lock", "symfony", "8.0.2", TODAY, "symfony")  # newer than the LTS, behind the newest: flagged, no LTS row
            self.assertEqual((r["status"], r["latest"], dc.lts_row(r, TODAY)), ("outdated", "8.1.10", None))
            self.assertEqual(dc.runtime_row("composer.lock", "symfony", "8.1.10", TODAY, "symfony")["status"], "current")
            old = dc.runtime_row("composer.lock", "symfony", "6.3.1", TODAY, "symfony")
            x = dc.lts_row(old, TODAY)
            self.assertEqual((old["status"], old["latest"], x["status"], x["latest"], x["target"]), ("eol", "8.1.10", "eol", "7.4.22", "7.4.22"))
        dated = [{"cycle": "20", "eol": "2030-01-01", "latest": "20.3", "lts": False}, {"cycle": "19", "eol": "2029-01-01", "latest": "19.9", "lts": "2025-01-01"}]
        with mock.patch.object(dc, "cycles", lambda p, t: dated):
            r = dc.runtime_row("package.json", "angular", "19.1.0", TODAY, "angular")
            self.assertEqual((r["latest"], dc.lts_row(r, TODAY)), ("20.3", None))

    def test_symfony_components_are_framework(self):
        """Locked symfony components map to the symfony EOL product; polyfills and contracts (own numbering) do not."""
        self.assertEqual(dc.FRAMEWORKS[("composer", "symfony/http-foundation")], "symfony")
        self.assertNotIn(("composer", "symfony/polyfill-mbstring"), dc.FRAMEWORKS)
        self.assertNotIn(("composer", "symfony/service-contracts"), dc.FRAMEWORKS)

    def test_unmapped_image_eol_and_k8s(self):
        """An official image outside IMAGES uses the endoflife.date product of the same name; a Kubernetes manifest's `- image:` is read; 404 keeps Hub-only behaviour."""
        cs = [{"cycle": "3.11", "eol": "2025-01-01", "latest": "3.11.19", "lts": False}, {"cycle": "5.0", "eol": False, "latest": "5.0.4", "lts": False}]
        with mock.patch.object(dc, "cycles", lambda p, t: cs), mock.patch.object(dc.net, "json", side_effect=OSError("offline")):
            r = dc.docker_rows("k8s/db.yaml", "kind: StatefulSet\nspec:\n  containers:\n    - image: cassandra:3.11.19\n    - image: \"{{ .Values.img }}\"\n", TODAY)
        self.assertEqual([(x["name"], x["status"]) for x in r], [("cassandra", "eol")])
        with mock.patch.object(dc, "cycles", side_effect=dc.NotFound("x")), mock.patch.object(dc.net, "json", side_effect=OSError("offline")):
            self.assertEqual(dc.ref_row("f", "fictdb:1.2", 1, TODAY)["status"], "not-checked")
        with mock.patch.object(dc, "cycles", side_effect=OSError("HTTP 503")), mock.patch.object(dc.net, "json", side_effect=OSError("offline")):
            r = dc.ref_row("f", "fictdb:1.2", 1, TODAY)
            self.assertTrue(r["status"] == "not-checked" and "endoflife.date lookup failed" in r["note"], r)
        seen = []
        with mock.patch.object(dc, "docker_rows", lambda f, t, today: seen.append(f) or []):
            collect({"deploy/app.yaml": "apiVersion: v1\nkind: Pod\n", "deploy/vals.yaml": "image: x:1\n"})
        self.assertEqual(seen, ["deploy/app.yaml"])

    def test_npm_workspace_without_lock_entry(self):
        """A workspace matched by the root `workspaces` globs drifts against the root lock even when `packages` has no entry for it."""
        lock = '{"lockfileVersion": 3, "packages": {"": {"workspaces": ["./apps/*"]}, "node_modules/fict-jwt": {"version": "8.5.1"}}}'
        _, rows = collect({"package.json": '{"workspaces": ["./apps/*"]}', "package-lock.json": lock, "apps/api/package.json": '{"dependencies": {"fict-jwt": "^9.0.0"}}',
                           "other/package.json": '{"dependencies": {"fict-jwt": "^9.0.0"}}'})
        self.assertEqual([r["file"] for r in rows if isinstance(r, dict) and r["status"] == "drift"], ["apps/api/package.json"])

    def test_maven_parent_override_drift(self):
        """A literal child version that differs from the parent's dependencyManagement, or from a same-major `<artifact prefix>.version` property, is drift; equal or unrelated is not."""
        parent = ('<project><groupId>g</groupId><artifactId>p</artifactId><version>1</version><properties><fict.version>3.6.0</fict.version><other.version>9.0</other.version></properties>'
                  '<dependencyManagement><dependencies><dependency><groupId>g</groupId><artifactId>managed</artifactId><version>2.0</version></dependency></dependencies></dependencyManagement></project>')
        parent = parent.replace("<project>", "<project><modelVersion>4.0.0</modelVersion>")
        dep = lambda a, v, g="g": f"<dependency><groupId>{g}</groupId><artifactId>{a}</artifactId><version>{v}</version></dependency>"
        par = "<parent><groupId>g</groupId><artifactId>p</artifactId><version>1</version>%s</parent>"
        child = lambda rp="", extra="": ("<project>" + par % rp + "<dependencies>" + dep("managed", "1.0") + dep("fict-core", "3.5.11", "io.fict") + dep("fict-same", "3.6.0", "io.fict")
                                         + dep("other-lib", "1.0") + dep("lone", "1.0") + dep("fict-x", "3.5.11", "org.else") + "</dependencies>" + extra + "</project>")
        _, rows = collect({"pom.xml": parent, "core/pom.xml": child()})
        self.assertEqual(drifts(rows), ["g:managed", "io.fict:fict-core"])  # fict-x: 'fict' is not in its groupId -> no property guess
        extra = ("<dependencyManagement><dependencies>" + dep("managed2", "9.0") + "</dependencies></dependencyManagement><build><plugins><plugin><dependencies>" + dep("managed", "0.1")
                 + "</dependencies></plugin></plugins></build><profiles><profile><dependencies>" + dep("managed", "0.2") + "</dependencies></profile></profiles>")
        _, rows = collect({"pom.xml": parent, "core/pom.xml": child("", extra).replace(dep("managed", "1.0"), "")})
        self.assertEqual(drifts(rows), ["io.fict:fict-core"])  # own dependencyManagement, plugin and profile deps are not compared
        for rp, files in (("<relativePath/>", {}), ("<relativePath>../nope/pom.xml</relativePath>", {})):
            _, rows = collect({"pom.xml": parent, "core/pom.xml": child(rp)})
            self.assertEqual(drifts(rows), [], rp)
        _, rows = collect({"pom.xml": parent.replace("<artifactId>p</artifactId>", "<artifactId>q</artifactId>"), "core/pom.xml": child()})
        self.assertEqual(drifts(rows), [], "parent coordinates differ")

    def test_gradle_interpolated_versions_drift(self):
        """`${v.k}`, `$kVersion` and gradle.properties versions resolve, so a declaration is compared with gradle.lockfile."""
        files = {"dependencies.gradle": "ext.v = [\n    fict: '3.0.0',\n    same: '1.0.0'\n]\next.kVersion = '2.0.0'\n", "gradle.properties": "pVersion=5.0.0\n",
                 "app/build.gradle": 'dependencies {\n  implementation "g:fict:${v.fict}"\n  implementation "g:same:${v.same}"\n  implementation "g:k:$kVersion"\n  implementation "g:pp:${pVersion}"\n}\n',
                 "app/gradle.lockfile": "g:fict:2.1.0=compileClasspath\ng:same:1.0.0=compileClasspath\ng:k:1.0.0=compileClasspath\ng:pp:4.0.0=compileClasspath\n"}
        _, rows = collect(files)
        self.assertEqual(drifts(rows), ["g:fict", "g:k", "g:pp"])
        self.assertEqual(dc.p_gradle_vars("version = '1.2.3'\nrootProject.name = '9'\next { kk = '2.0' }\n", "build.gradle"), {"kk": "2.0"})


class Filter(unittest.TestCase):
    def test_review_checks_passes_every_manifest_the_script_reads(self):
        """review_checks.sh hands dependency_currency.py a file list; it must include requirement dirs, constraints, setup.cfg, Pipfile, rust-toolchain and Gradle ext/property files."""
        import re
        src = open(os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/review_checks.sh")).read()
        pat = re.search(r"^dcf=\$\(.*?grep -E '([^']+)'", src, re.M)[1]
        for f in ("requirements/base.txt", "pip/reqs/dev.in", "constraints.txt", "setup.cfg", "svc/Pipfile", "rust-toolchain", "rust-toolchain.toml", "gradle/dependencies.gradle", "gradle.properties", "Cargo.toml"):
            self.assertTrue(re.search(pat, f), f)
        self.assertFalse(re.search(pat, "docs/notes.txt"))


if __name__ == "__main__":
    unittest.main()
