#!/usr/bin/env python3
"""Regression tests for the set-8 currency misses: Heroku runtime.txt, Gradle Kotlin plugin pins, Maven artifact-property drift. Fictional names; offline."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_dependency_currency_g5r15 import collect, dc

POM = """<project><properties><fict.version>1.0.0</fict.version></properties><dependencies>
<dependency><groupId>com.example</groupId><artifactId>fict</artifactId><version>%s</version></dependency></dependencies></project>"""


def runtimes(files):
    return [(r[1], r[4], r[3]) for r in collect(files)[1] if isinstance(r, tuple) and r[0] == "runtime"]


class G5R16(unittest.TestCase):
    def test_runtime_txt(self):
        self.assertEqual(runtimes({"runtime.txt": "python-3.10.12\n"}), [("runtime.txt", "python", "3.10.12")])

    def test_kotlin_plugin(self):
        for t in ('plugins { kotlin("jvm") version "1.9.22" }', 'plugins { id("org.jetbrains.kotlin.jvm") version "1.9.22" }',
                  "plugins { id 'org.jetbrains.kotlin.jvm' version '1.9.22' }"):
            self.assertIn(("build.gradle.kts", "kotlin", "1.9.22"), runtimes({"build.gradle.kts": t}), t)

    def test_pom_property_drift(self):
        drift = lambda v: [r for r in collect({"pom.xml": POM % v})[1] if r["status"] == "drift"]
        self.assertEqual([r["current"] for r in drift("0.9.0")], ["0.9.0"])
        self.assertEqual(drift("1.0.0"), [])
        self.assertEqual(drift("${fict.version}"), [])


class G5R16Review(unittest.TestCase):
    def _drift(self, pom):
        return [r for r in collect({"pom.xml": pom})[1] if r["status"] == "drift"]

    def test_trailing_zero_is_equal(self):
        self.assertEqual(self._drift(POM % "1.0"), [])

    def test_shared_referenced_property_skipped(self):
        pom = POM.replace("</dependencies>", "<dependency><groupId>com.example</groupId><artifactId>other</artifactId><version>${fict.version}</version></dependency></dependencies>")
        self.assertEqual(self._drift(pom % "0.9.0"), [])

    def test_plugin_dependency_skipped(self):
        pom = '<project><properties><fict.version>1.0.0</fict.version></properties><build><plugins><plugin><artifactId>p</artifactId><dependencies><dependency><groupId>com.example</groupId><artifactId>fict</artifactId><version>0.9.0</version></dependency></dependencies></plugin></plugins></build></project>'
        self.assertEqual(self._drift(pom), [])

    def test_profile_managed_dependency_drifts(self):
        pom = '<project><properties><fict.version>1.0.0</fict.version></properties><profiles><profile><dependencyManagement><dependencies><dependency><groupId>com.example</groupId><artifactId>fict</artifactId><version>0.9.0</version></dependency></dependencies></dependencyManagement></profile></profiles></project>'
        self.assertEqual([r["current"] for r in self._drift(pom)], ["0.9.0"])

    def test_runtime_txt_non_python_or_empty(self):
        for body in ("node-18.0.0\n", "", "python-\n"):
            self.assertEqual(runtimes({"runtime.txt": body}), [], body)

    def test_npm_prerelease_latest_not_target(self):
        old = dc.net.get, dc.net.json
        dc.net.json = lambda url, headers=None: {"dist-tags": {"latest": "3.0.0-rc.1"}, "versions": {"1.0.0": {}, "2.0.0": {}, "3.0.0-rc.1": {}}}
        try:
            self.assertEqual(dc.versions("npm", "fict-pkg")[-1], "2.0.0")
        finally:
            dc.net.get, dc.net.json = old


if __name__ == "__main__":
    unittest.main()
