#!/usr/bin/env python3
"""Regression tests for the TSV collapse of outdated transitive npm rows: more than 3 outdated rows from one npm lockfile whose names no sibling
package.json declares directly print as one outdated row (smallest line, first 3 names, major-behind count); direct rows, 3 or fewer, lockfiles
without a readable package.json (or a yarn.lock beside a "workspaces" package.json), vulnerable rows and --json (every row) stay unchanged. Offline: dep_row and osv_pass are stubbed."""
import contextlib, importlib.util, io, json, os, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

MINOR, MAJOR = "2 releases, minor", "3 releases, major"


def npm_lock(names):
    """A package-lock v3 text listing node_modules/<name> at 1.0.0 for every name."""
    pk = {"": {}}
    pk.update({f"node_modules/{n}": {"version": "1.0.0"} for n in names})
    return json.dumps({"lockfileVersion": 3, "packages": pk})


def make_root(files):
    """Temp repo with files (path -> text); returns its path."""
    d = tempfile.mkdtemp()
    for f, t in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, f)) or d, exist_ok=True)
        with open(os.path.join(d, f), "w") as fh:
            fh.write(t)
    return d


def stub_dep_row(plan):
    """Replacement for dc.dep_row: name -> (behind, line) from plan, always outdated to 2.0.0."""
    def fake(f, eco, name, cur, today):
        bh, line = plan[name]
        return dc.row("", name, eco, "outdated", cur, "2.0.0", bh, "2.0.0", line=line)
    return fake


def stub_osv(vulnerable):
    """Replacement for dc.osv_pass: marks the names in vulnerable as vulnerable, leaves the rest clean."""
    def fake(rows):
        for r in rows:
            if r["name"] in vulnerable:
                r["vulnerable"] = ["GHSA-fictional-0001"]
    return fake


def run_main(root, files, plan, extra=(), vulnerable=()):
    """Run dc.main over the given files with stubs; return stdout lines (or the parsed JSON when --json)."""
    out = io.StringIO()
    with mock.patch.object(dc, "dep_row", stub_dep_row(plan)), mock.patch.object(dc, "osv_pass", stub_osv(set(vulnerable))), \
            mock.patch("sys.stdin", io.StringIO("\n".join(files) + "\n")), contextlib.redirect_stdout(out):
        dc.main(["--root", root, "--stdin", "--today", "2026-11-08", *extra])
    text = out.getvalue()
    return json.loads(text) if "--json" in extra else [ln for ln in text.splitlines() if ln]


class TransitiveCollapse(unittest.TestCase):
    def setUp(self):
        self.plan = {}

    def project(self, direct, transitive, pkg=True):
        """Write package.json (direct deps, when pkg) and a lock listing direct + transitive names; plans each name outdated, lines count up."""
        names = list(direct) + list(transitive)
        for i, n in enumerate(names):
            self.plan[n] = (MAJOR if i % 2 else MINOR, 20 + i)
        files = {"package-lock.json": npm_lock(names)}
        if pkg:
            files["package.json"] = json.dumps({"dependencies": {n: "^1.0.0" for n in direct}})
        return make_root(files)

    def test_more_than_three_transitive_collapse_to_one_row(self):
        root = self.project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"])
        lines = run_main(root, ["package-lock.json"], self.plan)
        self.assertEqual(len(lines), 2, lines)
        f, line, rule, msg = next(ln for ln in lines if "transitive" in ln).split("\t")
        self.assertEqual((f, rule), ("package-lock.json", "outdated"))
        self.assertEqual(line, "21")  # smallest transitive line (direct-a took line 20)
        self.assertEqual(msg, "5 transitive npm packages outdated in this lockfile (3 a major behind; first 3: pkg-01, pkg-02, pkg-03; "
                              "--json lists every one): upgrade the direct dependencies that pull them in")

    def test_direct_row_stays_separate(self):
        root = self.project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04"])
        lines = run_main(root, ["package-lock.json"], self.plan)
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any(ln.split("\t")[3].startswith("npm direct-a") for ln in lines), lines)
        self.assertTrue(any("4 transitive npm packages" in ln for ln in lines), lines)

    def test_three_or_fewer_transitive_stay_unchanged(self):
        root = self.project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03"])
        lines = run_main(root, ["package-lock.json"], self.plan)
        self.assertEqual(len(lines), 4, lines)
        self.assertTrue(all("transitive npm packages" not in ln for ln in lines), lines)

    def test_no_package_json_no_collapse(self):
        root = self.project([], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"], pkg=False)
        lines = run_main(root, ["package-lock.json"], self.plan)
        self.assertEqual(len(lines), 5, lines)
        self.assertTrue(all("transitive npm packages" not in ln for ln in lines), lines)

    def test_vulnerable_row_never_collapsed(self):
        root = self.project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"])
        lines = run_main(root, ["package-lock.json"], self.plan, vulnerable=("pkg-02",))
        self.assertEqual(len(lines), 3, lines)  # direct-a row, pkg-02 vulnerable row, 4 transitive collapsed
        vuln = [ln for ln in lines if ln.split("\t")[2] == "vulnerable"]
        self.assertEqual(len(vuln), 1, lines)
        self.assertIn("pkg-02", vuln[0])
        self.assertIn("4 transitive npm packages", "\n".join(lines))

    def test_json_keeps_every_row(self):
        names = ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"]
        root = self.project(["direct-a"], names)
        rows = run_main(root, ["package-lock.json"], self.plan, extra=("--json",))
        listed = sorted(r["name"] for r in rows if r["status"] == "outdated" and r["name"] in names)
        self.assertEqual(listed, names)
        self.assertTrue(all(r["rule"] == "outdated" for r in rows if r["name"] in names))

    def yarn_project(self, direct, transitive, pj_text):
        """Write a yarn.lock listing direct + transitive names and the given package.json text; plans each name outdated."""
        names = list(direct) + list(transitive)
        for i, n in enumerate(names):
            self.plan[n] = (MINOR, 20 + i)
        lock = "".join(f'{n}@^1.0.0:\n  version "1.0.0"\n\n' for n in names)
        return make_root({"yarn.lock": lock, "package.json": pj_text})

    def test_yarn_lock_sibling_package_json_collapses(self):
        root = self.yarn_project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"],
                                 json.dumps({"dependencies": {"direct-a": "^1.0.0"}}))
        lines = run_main(root, ["yarn.lock"], self.plan)
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any(ln.split("\t")[3].startswith("npm direct-a") for ln in lines), lines)
        self.assertTrue(any(ln.startswith("yarn.lock\t21\toutdated\t5 transitive npm packages") for ln in lines), lines)

    def test_yarn_workspaces_never_collapse(self):
        root = self.yarn_project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"],
                                 json.dumps({"workspaces": ["packages/*"], "dependencies": {"direct-a": "^1.0.0"}}))
        lines = run_main(root, ["yarn.lock"], self.plan)
        self.assertEqual(len(lines), 6, lines)  # 1 direct + 5 transitive rows, nothing folded
        self.assertTrue(all("transitive npm packages" not in ln for ln in lines), lines)

    def test_transitive_name_with_tab_is_one_four_field_line(self):
        root = self.project(["direct-a"], ["pkg\t01", "pkg-02", "pkg-03", "pkg-04"])
        lines = run_main(root, ["package-lock.json"], self.plan)
        collapsed = [ln for ln in lines if "transitive" in ln]
        self.assertEqual(len(collapsed), 1, lines)
        self.assertEqual(len(collapsed[0].split("\t")), 4, collapsed)
        self.assertIn("first 3: pkg 01, pkg-02, pkg-03", collapsed[0])

    def test_malformed_package_json_with_yarn_lock_no_collapse(self):
        root = self.yarn_project(["direct-a"], ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"], "{not json")
        lines = run_main(root, ["yarn.lock"], self.plan)
        self.assertTrue(all("transitive npm packages" not in ln for ln in lines), lines)
        self.assertEqual(sum("outdated" in ln.split("\t")[2] for ln in lines), 6, lines)


if __name__ == "__main__":
    res = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TransitiveCollapse))
    print(f"Tests: {res.testsRun - len(res.failures) - len(res.errors)}/{res.testsRun}")
    raise SystemExit(not res.wasSuccessful())
