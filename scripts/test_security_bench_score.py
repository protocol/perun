#!/usr/bin/env python3
"""Tests for scripts/security_bench_score.py and its seeded fixtures. Offline."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import security_bench_score as s  # noqa: E402

FIX = HERE / "eval-fixtures/security-seeded"
KEYS = json.loads((FIX / "keys.json").read_text())
VULN = {i: k for i, k in KEYS.items() if k["cwe"]}
FIRST, K1 = next(iter(VULN.items()))


def find(k, **kw):
    return {**{"file": k["file"], "line": k["line"], "cwe": k["cwe"]}, **kw}


def arm(root, name, per_diff):
    d = Path(root) / name
    d.mkdir()
    for i in KEYS:
        (d / f"{i}.json").write_text(json.dumps(per_diff.get(i, [])))
    return d


def added_lines(diff_id):
    lines = (FIX / "diffs" / f"{diff_id}.diff").read_text().split("\n")
    start = next(n for n, l in enumerate(lines) if l.startswith("@@"))
    return [l[1:] for l in lines[start + 1:] if l.startswith("+")]


class Fixtures(unittest.TestCase):
    def test_shape(self):
        self.assertEqual((len(VULN), len(KEYS) - len(VULN)), (12, 4))
        self.assertEqual(len({k["cwe"] for k in VULN.values()}), 12)
        self.assertEqual({p.stem for p in (FIX / "diffs").glob("*.diff")}, set(KEYS))

    def test_key_line_holds_its_marker_and_data_is_fictional(self):
        for i, k in VULN.items():
            self.assertIn(k["marker"], added_lines(i)[k["line"] - 1], i)
        txt = "".join(p.read_text() for p in (FIX / "diffs").glob("*.diff"))
        self.assertFalse(re.search(r"AKIA[0-9A-Z]{16}|gh[pousr]_\w{36,}|sk_(live|test)_|@(?!example\.com)\w+\.(com|org)\b", txt))

    def test_decoy_argv_ends_options(self):
        self.assertIn('"--", path', (FIX / "diffs/15-decoy-fixed-argv.diff").read_text())


class Normalize(unittest.TestCase):
    def test_cwe_forms(self):
        for x in ("CWE-89", "cwe-89", " CWE-89", "89", 89):
            self.assertEqual(s.cwe_id(x), 89)
        self.assertIsNone(s.cwe_id(True))
        self.assertIsNone(s.cwe_id("none"))

    def test_paths(self):
        for a in ("./app/x.py", "a/app/x.py", "b/app/x.py", "/repo/work/app/x.py", "app/x.py"):
            self.assertTrue(s.same_file(a, "app/x.py"), a)
        self.assertFalse(s.same_file("app/y.py", "app/x.py"))
        self.assertFalse(s.same_file("notapp/x.py", "app/x.py"))


class Score(unittest.TestCase):
    def scored(self, per_diff, **kw):
        with tempfile.TemporaryDirectory() as t:
            return s.score(KEYS, s.load(arm(t, "a", per_diff), KEYS), **kw)

    def test_perfect_noisy_and_empty(self):
        perfect = {i: [find(k, line=k["line"] + 1)] for i, k in VULN.items()}
        noisy = dict(perfect)
        noisy["13-decoy-sqli-param"] = [{"file": "app/orders_safe.py", "line": 3, "cwe": "CWE-89"}]
        p, n, e = self.scored(perfect), self.scored(noisy), self.scored({})
        self.assertEqual((p["precision"], p["recall"], p["decoy_fp"]), (1.0, 1.0, "0/4"))
        self.assertEqual((n["recall"], n["decoy_fp"]), (1.0, "1/4"))
        self.assertAlmostEqual(n["precision"], 12 / 13)
        self.assertEqual((e["precision"], e["recall"]), (None, 0.0))

    def test_tol_boundary(self):
        self.assertEqual(self.scored({FIRST: [find(K1, line=K1["line"] + 1)]})["true_positives"], 1)
        self.assertEqual(self.scored({FIRST: [find(K1, line=K1["line"] + 2)]})["true_positives"], 0)
        self.assertEqual(self.scored({FIRST: [find(K1, line=K1["line"] + 2)]}, tol=2)["true_positives"], 1)

    def test_wrong_file_and_wrong_cwe(self):
        self.assertEqual(self.scored({FIRST: [find(K1, file="app/other.py")]})["true_positives"], 0)
        self.assertEqual(self.scored({FIRST: [find(K1, cwe="CWE-1")]})["true_positives"], 0)

    def test_normalization_and_equiv(self):
        self.assertEqual(self.scored({FIRST: [find(K1, file="b/./" + K1["file"], cwe=89)]})["true_positives"], 1)
        i, k = "10-idor", KEYS["10-idor"]
        self.assertEqual(self.scored({i: [find(k, cwe="CWE-284")]})["true_positives"], 1)
        self.assertEqual(self.scored({FIRST: [find(K1, cwe="CWE-284")]})["true_positives"], 0)

    def test_missing_cwe_scored_on_file_line(self):
        r = self.scored({FIRST: [{"file": K1["file"], "line": K1["line"]}]})
        self.assertEqual((r["true_positives"], r["cwe_missing"]), (1, 1))
        self.assertNotIn("cwe_missing", self.scored({}))

    def test_duplicates_collapse(self):
        r = self.scored({FIRST: [find(K1), find(K1, line=K1["line"] + 1), find(K1, cwe="89")]})
        self.assertEqual((r["true_positives"], r["findings"], r["dup_findings"], r["precision"]), (1, 1, 2, 1.0))
        far = self.scored({FIRST: [find(K1), find(K1, line=K1["line"] + 9)]})
        self.assertEqual((far["findings"], far["precision"]), (2, 0.5))

    def test_decoy_fp_alongside_tp(self):
        r = self.scored({FIRST: [find(K1)], "14-decoy-escaped-html": [{"file": "app/greet_safe.py", "line": 6, "cwe": 79}]})
        self.assertEqual((r["true_positives"], r["decoy_fp"], r["precision"]), (1, "1/4", 0.5))


class FailClosed(unittest.TestCase):
    def code(self, argv):
        with self.assertRaises(SystemExit) as c:
            s.main(argv)
        return c.exception.code

    def test_arms(self):
        with tempfile.TemporaryDirectory() as t:
            ok = arm(t, "ok", {})
            self.assertEqual(self.code([f"ok={ok}", f"gone={Path(t) / 'nope'}"]), 2)
            self.assertEqual(self.code([f"ok={ok}", f"ok={ok}"]), 2)
            self.assertEqual(self.code(["nodir"]), 2)
            self.assertEqual(self.code([f"ok={ok}", "--tol", "-1"]), 2)

    def test_malformed_findings(self):
        bad = ['{"not": "a list"}', "not json{", '[{"file": "a.py", "line": true}]', '[{"file": "a.py"}]',
               '[{"file": "a.py", "line": 3, "cwe": [1]}]']
        with tempfile.TemporaryDirectory() as t:
            ok = arm(t, "ok", {})
            (ok / "01-sqli.json").unlink()
            self.assertEqual(self.code([f"ok={ok}"]), 2)
            for b in bad:
                (ok / "01-sqli.json").write_text(b)
                self.assertEqual(self.code([f"ok={ok}"]), 2, b)

    def test_invalid_keys(self):
        cases = ["{}", "[]", '{"x": {"cwe": null}}', '{"x": {"file": "a", "line": 1}}',
                 '{"x": {"cwe": "CWE-89", "file": "a", "line": true}}', '{"x": {"cwe": "oops", "file": "a", "line": 1}}',
                 '{"x": {"cwe": "CWE-89", "file": "a", "line": 1, "equiv": ["zzz"]}}', "not json"]
        with tempfile.TemporaryDirectory() as t:
            for n, c in enumerate(cases):
                kp = Path(t) / f"k{n}.json"
                kp.write_text(c)
                self.assertEqual(self.code(["a=" + t, "--keys", str(kp)]), 2, c)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as t:
            p = subprocess.run([sys.executable, str(HERE / "security_bench_score.py"), f"a={arm(t, 'a', {})}"],
                               capture_output=True, text=True)
            q = subprocess.run([sys.executable, str(HERE / "security_bench_score.py"), f"a={Path(t) / 'x'}"],
                               capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["a"]["recall"], 0.0)
        self.assertEqual(q.returncode, 2)


if __name__ == "__main__":
    unittest.main()
