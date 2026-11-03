#!/usr/bin/env python3
"""Regression tests for dependency_currency.py root causes found by the set-6 scored run: npm-shrinkwrap.json and uv.lock read as locks, exact manifest
pins read when no lock exists (Cargo workspace/member/target tables, composer.json with vendor/composer/installed.json, Gradle buildSrc constants and
gradle.properties, setup.py), runtime pins in .tool-versions / mise.toml / .php-version, Spring Framework EOL from spring-core, go vendor/modules.txt drift
and a Maven literal that restates a managed version. Offline (collect() makes no network call)."""
import importlib.util, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def collect(files):
    """Write files (path -> text) to a temp repo and return dc.collect's (deps, rows)."""
    with tempfile.TemporaryDirectory() as d:
        for f, t in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
            with open(os.path.join(d, f), "w") as fh:
                fh.write(t)
        return dc.collect(d, sorted(files), "2026-11-03")


def pairs(deps):
    """(eco, name, version) triples of the collected dependencies."""
    return sorted({(e, n, v) for _, e, n, v in deps})


def drifts(rows):
    """Names of the drift rows."""
    return sorted(r["name"] for r in rows if isinstance(r, dict) and r["status"] == "drift")


def runtimes(rows):
    """(product, version) of the runtime tuples."""
    return sorted((r[2], r[3]) for r in rows if isinstance(r, tuple))


class Locks(unittest.TestCase):
    def test_npm_shrinkwrap_is_a_lock(self):
        """npm-shrinkwrap.json (v1 tree) is parsed like package-lock.json: its versions are rows and a stale range drifts."""
        deps, rows = collect({"package.json": '{"dependencies": {"fict-a": "^2.0.0"}}',
                              "npm-shrinkwrap.json": '{"lockfileVersion": 1, "dependencies": {"fict-a": {"version": "1.4.0"}}}'})
        self.assertEqual(pairs(deps), [("npm", "fict-a", "1.4.0")])
        self.assertEqual(drifts(rows), ["fict-a"])

    def test_uv_lock_is_a_lock(self):
        """uv.lock registry packages are locked versions (drift vs pyproject); the virtual project entry is not a dependency."""
        lock = ('version = 1\n[[package]]\nname = "fict-b"\nversion = "0.13.0"\nsource = { registry = "https://pypi.org/simple" }\n'
                '[[package]]\nname = "my-app"\nversion = "0.1.0"\nsource = { virtual = "." }\n')
        deps, rows = collect({"pyproject.toml": '[project]\nname = "my-app"\ndependencies = ["fict-b>=0.14.0"]\n', "uv.lock": lock})
        self.assertEqual(pairs(deps), [("pip", "fict-b", "0.13.0")])
        self.assertEqual(drifts(rows), ["fict-b"])

    def test_composer_installed_json_is_a_lock(self):
        """vendor/composer/installed.json (v2 and v1 shapes) stands in for a missing composer.lock; manifest ranges are checked against it."""
        man = '{"require": {"fict/c": "^1.7.4"}}'
        for inst in ('{"packages": [{"name": "fict/c", "version": "1.7.3"}]}', '[{"name": "fict/c", "version": "v1.7.3"}]'):
            deps, rows = collect({"composer.json": man, "vendor/composer/installed.json": inst})
            self.assertEqual(pairs(deps), [("composer", "fict/c", "1.7.3")])
            self.assertEqual(drifts(rows), ["fict/c"])


class ExactPinsWithoutLock(unittest.TestCase):
    def test_cargo_workspace_member_and_target_pins(self):
        """With no Cargo.lock, `=x.y.z` pins in [workspace.dependencies], a member crate and [target.*.dependencies] are read; a range is not;
        a member pin that differs from the workspace pin is drift."""
        deps, rows = collect({
            "Cargo.toml": '[workspace]\nmembers = ["m"]\n[workspace.dependencies]\nfict-a = "=1.0.1"\nfict-b = "=2.0.0"\nfict-r = "1.2"\n',
            "m/Cargo.toml": '[package]\nname = "m"\n[dependencies]\nfict-a = { workspace = true }\nfict-b = "=2.1.0"\n[target.\'cfg(unix)\'.dependencies]\nfict-t = "=0.3.0"\n'})
        self.assertEqual(pairs(deps), [("cargo", "fict-a", "1.0.1"), ("cargo", "fict-b", "2.0.0"), ("cargo", "fict-b", "2.1.0"), ("cargo", "fict-t", "0.3.0")])
        self.assertEqual(drifts(rows), ["fict-b"])

    def test_composer_exact_pins(self):
        """composer.json with no lock: `1.2.3` / `v1.2.3` are pins, `^1.2.3` is not; php and ext-* are never packages."""
        deps, _ = collect({"composer.json": '{"require": {"php": "8.1.0", "fict/a": "1.2.3", "fict/b": "^1.0.0", "fict/c": "v2.0.1"}}'})
        self.assertEqual(pairs(deps), [("composer", "fict/a", "1.2.3"), ("composer", "fict/c", "2.0.1")])

    def test_gradle_buildsrc_constants_and_properties(self):
        """buildSrc/**/*.kt `g:a:v` constants are dependencies; a gradle.properties `<artifact>Version` that differs is drift, one that matches is not."""
        deps, rows = collect({
            "buildSrc/src/main/kotlin/Deps.kt": 'object Deps {\n const val a = "org.fict:fict-core:1.0.0"\n const val b = "org.fict:other:2.0.0"\n}\n',
            "gradle.properties": "fictCoreVersion=1.1.0\notherVersion=2.0.0\n"})
        self.assertEqual(pairs(deps), [("gradle", "org.fict:fict-core", "1.0.0"), ("gradle", "org.fict:other", "2.0.0")])
        self.assertEqual(drifts(rows), ["org.fict:fict-core"])

    def test_setup_py_install_requires(self):
        """setup.py install_requires `==` pins are read when no pip lock sits beside it; ranges are not pins."""
        deps, _ = collect({"svc/setup.py": 'setup(\n install_requires=[\n  "fict-a==1.3.8",\n  "fict-b>=2.0",\n ],\n extras_require={"dev": ["fict-c==0.1.0"]},\n)\n'})
        self.assertEqual(pairs(deps), [("pip", "fict-a", "1.3.8"), ("pip", "fict-c", "0.1.0")])

    def test_lock_present_means_manifest_pins_are_not_duplicated(self):
        """A lock beside the manifest owns the versions: the exact pin in the manifest adds no dependency of its own."""
        deps, _ = collect({"package.json": '{"dependencies": {"fict-a": "1.0.0"}}',
                           "package-lock.json": '{"lockfileVersion": 1, "dependencies": {"fict-a": {"version": "1.0.0"}}}'})
        self.assertEqual([f for f, *_ in deps], ["package-lock.json"])


class Runtimes(unittest.TestCase):
    def test_tool_versions_mise_and_php_version(self):
        """.tool-versions, the [tools] table of mise.toml and .php-version give runtime pins; floating aliases and unknown tools give none."""
        _, rows = collect({".tool-versions": "nodejs 16.20.2\nrust 1.70.0 1.69.0\nterraform 1.5.0\n# python 3.8.0\n", "mise.toml": '[tools]\nruby = "3.0.6"\npython = { version = "3.9.1" }\nnode = "lts"\n[env]\nX = "1.2.3"\n',
                           ".php-version": "7.4.33\n"})
        self.assertEqual(runtimes(rows), [("nodejs", "16.20.2"), ("php", "7.4.33"), ("python", "3.9.1"), ("ruby", "3.0.6"), ("rust", "1.70.0")])

    def test_spring_core_maps_to_spring_framework_eol(self):
        """spring-core (and siblings) in maven/gradle feed the spring-framework end-of-life check; Spring Boot keeps its own product."""
        self.assertEqual(dc.FRAMEWORKS[("maven", "org.springframework:spring-core")], "spring-framework")
        self.assertEqual(dc.FRAMEWORKS[("gradle", "org.springframework:spring-webmvc")], "spring-framework")
        self.assertEqual(dc.FRAMEWORKS[("maven", "org.springframework.boot:spring-boot")], "spring-boot")


class DriftWithoutLock(unittest.TestCase):
    def test_go_vendor_modules_txt(self):
        """vendor/modules.txt that records another version than go.mod is drift (go build -mod=vendor rejects it); matching entries are quiet."""
        _, rows = collect({"go.mod": "module example.com/x\ngo 1.21\nrequire example.com/a v1.0.0\nrequire example.com/b v2.0.0\n",
                           "vendor/modules.txt": "# example.com/a v1.0.1\n## explicit\nexample.com/a\n# example.com/b v2.0.0\n## explicit\nexample.com/b\n"})
        self.assertEqual(drifts(rows), ["example.com/a"])

    def test_maven_literal_restating_managed_version(self):
        """A <dependency> literal version that differs from the same pom's dependencyManagement entry is drift; an equal one is not."""
        dep = lambda a, v: f"<dependency><groupId>g</groupId><artifactId>{a}</artifactId><version>{v}</version></dependency>"
        pom = ("<project><dependencyManagement><dependencies>" + dep("a", "2.0") + dep("b", "1.0") + "</dependencies></dependencyManagement><dependencies>"
               + dep("a", "1.0") + dep("b", "1.0") + "</dependencies></project>")
        _, rows = collect({"pom.xml": pom})
        self.assertEqual(drifts(rows), ["g:a"])


class Negatives(unittest.TestCase):
    def test_setup_py_ignores_non_requirement_lists(self):
        """entry_points, package_data and classifiers lists are not requirements; only install_requires and extras_require lists are."""
        deps, _ = collect({"setup.py": "setup(install_requires=['req==1.0'], entry_points={'console_scripts': ['a==1.0']}, package_data={'p': ['x==2']}, extras_require={'d': ['ex==3.0']})\n"})
        self.assertEqual(pairs(deps), [("pip", "ex", "3.0"), ("pip", "req", "1.0")])

    def test_setup_cfg_and_pipfile_lockless_pins(self):
        """setup.cfg and Pipfile `==` pins are dependencies when no pip lock sits beside them."""
        deps, _ = collect({"a/setup.cfg": "[options]\ninstall_requires =\n    fict-a==1.0\n", "b/Pipfile": '[packages]\nfict-b = "==2.0"\n'})
        self.assertEqual(pairs(deps), [("pip", "fict-a", "1.0"), ("pip", "fict-b", "2.0")])

    def test_gradle_property_matches_artifact_only(self):
        """A property named for the group's last segment (coreVersion) does not drift an unrelated artifact of that group."""
        _, rows = collect({"buildSrc/src/main/kotlin/D.kt": 'const val a = "com.acme.core:foo-lib:1.0.0"\n', "gradle.properties": "coreVersion=9.9.9\n"})
        self.assertEqual(drifts(rows), [])

    def test_cargo_renamed_dependency_and_single_quotes(self):
        """A member dep renamed with package = \"x\" is not compared with the workspace key; single-quoted TOML strings parse."""
        deps, rows = collect({"Cargo.toml": "[workspace]\nmembers = ['m']\n[workspace.dependencies]\nfict-a = '=1.0.0'\n",
                              "m/Cargo.toml": "[dependencies]\nfict-a = { package = 'other', version = '=2.0.0' }\n"})
        self.assertEqual(pairs(deps), [("cargo", "fict-a", "1.0.0")])
        self.assertEqual(drifts(rows), [])

    def test_composer_installed_bad_entry_and_pom_plugin_deps(self):
        """One nameless installed.json entry does not discard the rest; plugin dependencies and a different classifier are not overrides."""
        deps, _ = collect({"composer.json": "{}", "vendor/composer/installed.json": '{"packages": [{"version": "1.0"}, {"name": "fict/c", "version": "1.0.0"}]}'})
        self.assertEqual(pairs(deps), [("composer", "fict/c", "1.0.0")])
        d = lambda v, extra="": f"<dependency><groupId>g</groupId><artifactId>a</artifactId>{extra}<version>{v}</version></dependency>"
        pom = ("<project><dependencyManagement><dependencies>" + d("2.0") + "</dependencies></dependencyManagement><dependencies>" + d("1.0", "<classifier>tests</classifier>")
               + "</dependencies><build><plugins><plugin><dependencies>" + d("1.0") + "</dependencies></plugin></plugins></build></project>")
        self.assertEqual(drifts(collect({"pom.xml": pom})[1]), [])


if __name__ == "__main__":
    unittest.main()
