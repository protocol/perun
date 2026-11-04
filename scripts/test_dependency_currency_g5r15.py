#!/usr/bin/env python3
"""Regression tests for dependency_currency.py / review_checks.sh root causes found by the set-7 scored run: Go +incompatible tags stay out of latest, a floating
major release tag hiding point releases, framework EOL for Dropwizard, the Gradle wrapper as a runtime pin, Gradle build-file vs version-catalog drift, and
vendored dirs that hold no recognised manifest. Fictional names; every HTTP call mocked."""
import importlib.util, os, re, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def collect(files):
    """Write files (path -> text) to a temp repo and return dc.collect's (deps, rows)."""
    with tempfile.TemporaryDirectory() as d:
        for f, t in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, f)) or d, exist_ok=True)
            with open(os.path.join(d, f), "w") as fh:
                fh.write(t)
        return dc.collect(d, sorted(files), "2026-11-04")


class G5R15(unittest.TestCase):
    def test_go_incompatible_tag_is_not_latest(self):
        """A +incompatible tag is not the module's latest: the Go proxy's @latest skips it once the module has a go.mod (go-sqlite3: v1.14.x, not v2.0.3+incompatible)."""
        old = dc.net.get
        dc.net.get = lambda url, data=None, headers=None: "v1.0.0\nv1.0.9\nv3.1.0+incompatible\n"
        try:
            self.assertEqual(dc.versions("go", "example.com/fict/mod")[-1], "v1.0.9")
        finally:
            dc.net.get = old

    def test_floating_major_release_tag_does_not_hide_point_releases(self):
        """releases/latest tagged `v6` while v6.1.2 exists: the highest tag wins, so v6.1.0 is behind it."""
        old_net, old_ls = dc.net.json, dc.ls_remote_latest
        dc.net.json = lambda url, headers=None: {"tag_name": "v6"}
        calls = []
        dc.ls_remote_latest = lambda repo, err: calls.append(repo) or "v6.1.2"
        try:
            self.assertEqual([dc.gh_latest("fict/act") for _ in range(3)], ["v6.1.2"] * 3)
        finally:
            dc.net.json, dc.ls_remote_latest = old_net, old_ls
        self.assertEqual(calls, ["fict/act"])  # one ls-remote per repo, however many `uses:` lines name it

    def test_dropwizard_core_is_a_framework(self):
        """io.dropwizard:dropwizard-core feeds the endoflife.date `dropwizard` product, in Maven and Gradle."""
        self.assertEqual({dc.FRAMEWORKS[(e, "io.dropwizard:dropwizard-core")] for e in ("maven", "gradle")}, {"dropwizard"})

    def test_gradle_wrapper_is_a_runtime_pin(self):
        """gradle-wrapper.properties distributionUrl yields a `gradle` runtime tuple (bin and all distributions)."""
        for kind in ("bin", "all"):
            _, rows = collect({"gradle/wrapper/gradle-wrapper.properties": f"distributionUrl=https\\://services.example.com/distributions/gradle-7.4.1-{kind}.zip\n"})
            self.assertEqual([r[2:4] for r in rows if isinstance(r, tuple)], [("gradle", "7.4.1")])

    def test_gradle_build_file_vs_catalog_drift(self):
        """The same module at two versions in build.gradle and gradle/libs.versions.toml (no lockfile) is a drift row; equal versions are not."""
        files = {"build.gradle": 'dependencies { implementation "org.fict:lib:1.0.1" }\n',
                 "gradle/libs.versions.toml": '[versions]\nlib = "1.0.3"\n[libraries]\nlib = { module = "org.fict:lib", version.ref = "lib" }\n'}
        _, rows = collect(files)
        self.assertEqual([r["name"] for r in rows if isinstance(r, dict) and r["status"] == "drift"], ["org.fict:lib"])
        files["build.gradle"] = files["build.gradle"].replace("1.0.1", "1.0.3")
        _, rows = collect(files)
        self.assertEqual([r for r in rows if isinstance(r, dict) and r["status"] == "drift"], [])
        files["gradle/libs.versions.toml"] = '[libraries]\nlib = "org.fict:lib:1.0.3"\nlib-old = "org.fict:lib:1.0.1"\n'  # two aliases in one file: ambiguous, no row
        _, rows = collect(files)
        self.assertEqual([r for r in rows if isinstance(r, dict) and r["status"] == "drift"], [])

    def test_vendored_dir_without_manifest_gets_a_row(self):
        """A vendored dir holding only PKG-INFO and sources is one vendored row named from PKG-INFO's Name; review_checks.sh now hands PKG-INFO over."""
        rows = dc.vendored_rows(os.path.join(HERE, "nonexistent"), ["vendor/fictpkg/fictpkg.py"])
        self.assertEqual([(r["file"], r["status"]) for r in rows], [("vendor/fictpkg", "vendored")])
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "vendor/x"))
            with open(os.path.join(d, "vendor/x/PKG-INFO"), "w") as fh:
                fh.write("Metadata-Version: 2.1\nName: fictpkg\nVersion: 1.0.5\n")
            self.assertEqual([r["name"] for r in dc.vendored_rows(d, ["vendor/x/PKG-INFO", "vendor/x/m.py"])], ["fictpkg"])
        with open(os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/review_checks.sh")) as fh:
            sh = fh.read()
        rx = re.search(r"dcf=\$\(printf '%s\\n' \"\$all\" \| grep -E '(.*)' \|\| true\)", sh)[1]
        for f in ("vendor/fictpkg/PKG-INFO", "gradle/wrapper/gradle-wrapper.properties"):
            self.assertTrue(re.search(rx.replace("[^/]*", "[^/]*"), f), f)
        self.assertFalse(re.search(rx, "vendor/fictpkg/fictpkg.py"))


if __name__ == "__main__":
    unittest.main()
