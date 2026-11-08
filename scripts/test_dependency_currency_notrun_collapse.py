#!/usr/bin/env python3
"""Regression tests for the TSV collapse of not-checked rows: more than 3 not-checked rows sharing (file, ecosystem, note) print as one
row (rule not-checked, smallest line, first 3 names); 3 or fewer, other notes, other files and other rules print unchanged; --json keeps
every row. Offline: dep_row and osv_pass are stubbed, so no registry or OSV call is made."""
import contextlib, importlib.util, io, json, os, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

BLOCKED = "NOT RUN: registry unreachable (circuit open)"
OTHER = "NOT RUN: registry lookup failed (fictional)"


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
    """Replacement for dc.dep_row: name -> (note, line) from plan, always not-checked."""
    def fake(f, eco, name, cur, today):
        note, line = plan[name]
        return dc.row("", name, eco, "not-checked", cur, note=note, line=line)
    return fake


def run_main(root, names_by_file, plan, extra=()):
    """Run dc.main over the given files with stubs; return stdout lines (or the parsed JSON when --json)."""
    stdin = "\n".join(names_by_file) + "\n"
    out = io.StringIO()
    with mock.patch.object(dc, "dep_row", stub_dep_row(plan)), mock.patch.object(dc, "osv_pass", lambda rows: None), \
            mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
        dc.main(["--root", root, "--stdin", "--today", "2026-11-08", *extra])
    text = out.getvalue()
    return json.loads(text) if "--json" in extra else [ln for ln in text.splitlines() if ln]


class Collapse(unittest.TestCase):
    def setUp(self):
        self.plan = {}

    def lock(self, rel, names, note, first_line=11):
        """Write a lock at rel holding names, planning each as not-checked with note; lines count up from first_line."""
        for i, n in enumerate(names):
            self.plan[n] = (note, first_line + i)
        return rel, npm_lock(names)

    def root(self, *locks):
        return make_root({rel: txt for rel, txt in locks})

    def test_more_than_three_collapse_to_one_row(self):
        rel, txt = self.lock("package-lock.json", ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"], BLOCKED)
        lines = run_main(self.root((rel, txt)), [rel], self.plan)
        self.assertEqual(len(lines), 1, lines)
        f, line, rule, msg = lines[0].split("\t")
        self.assertEqual((f, line, rule), ("package-lock.json", "11", "not-checked"))
        self.assertEqual(msg, "5 npm packages not checked in this file (first 3: pkg-01, pkg-02, pkg-03; --json lists every one): " + BLOCKED)

    def test_collapsed_row_uses_smallest_line(self):
        rel, txt = self.lock("package-lock.json", ["pkg-01", "pkg-02", "pkg-03", "pkg-04"], BLOCKED, first_line=40)
        self.plan["pkg-03"] = (BLOCKED, 7)  # smallest line is not the first name
        lines = run_main(self.root((rel, txt)), [rel], self.plan)
        self.assertEqual(lines[0].split("\t")[1], "7")

    def test_exactly_three_stay_unchanged(self):
        rel, txt = self.lock("package-lock.json", ["pkg-01", "pkg-02", "pkg-03"], BLOCKED)
        lines = run_main(self.root((rel, txt)), [rel], self.plan)
        self.assertEqual(len(lines), 3)
        self.assertEqual([ln.split("\t")[1] for ln in lines], ["11", "12", "13"])
        self.assertTrue(all("packages not checked" not in ln for ln in lines))

    def test_different_note_in_same_file_stays(self):
        rel, txt = self.lock("package-lock.json", ["pkg-01", "pkg-02", "pkg-03", "pkg-04"], BLOCKED)
        self.plan["odd-01"] = (OTHER, 50)
        txt = npm_lock(["pkg-01", "pkg-02", "pkg-03", "pkg-04", "odd-01"])
        lines = run_main(self.root((rel, txt)), [rel], self.plan)
        self.assertEqual(len(lines), 2, lines)  # sorted by name: odd-01 first, then the collapsed pkg group
        self.assertEqual(sum("4 npm packages not checked" in ln for ln in lines), 1, lines)
        self.assertEqual(sum("npm odd-01" in ln and OTHER in ln for ln in lines), 1, lines)

    def test_different_file_stays(self):
        a = self.lock("a/package-lock.json", ["pkg-01", "pkg-02"], BLOCKED)
        b = self.lock("b/package-lock.json", ["pkg-03", "pkg-04"], BLOCKED)
        lines = run_main(self.root(a, b), ["a/package-lock.json", "b/package-lock.json"], self.plan)
        self.assertEqual(len(lines), 4, lines)  # 2 + 2 across two files: no group over 3 in either file
        self.assertTrue(all("packages not checked" not in ln for ln in lines))

    def test_json_keeps_every_row(self):
        names = ["pkg-01", "pkg-02", "pkg-03", "pkg-04", "pkg-05"]
        rel, txt = self.lock("package-lock.json", names, BLOCKED)
        rows = run_main(self.root((rel, txt)), [rel], self.plan, extra=("--json",))
        listed = sorted(r["name"] for r in rows if r["status"] == "not-checked")
        self.assertEqual(listed, names)
        self.assertTrue(all(r["rule"] == "not-checked" for r in rows if r["status"] == "not-checked"))
        self.assertTrue(all(r["note"] == BLOCKED for r in rows if r["name"] in names))


if __name__ == "__main__":
    unittest.main()
