#!/usr/bin/env python3
"""Tests: committed_personal_data.py ends each flagged file's message with fixture signals, counts only (how many of the file's addresses have a placeholder-style local part, how many are on a reserved domain, out of how many addresses, reserved names counted), and starts the message with `likely fixture:` only when the path is a test, spec, fixture or mock path AND at least half of the addresses are placeholder-style or on a reserved domain. The label is a hint: no row is dropped, the threshold and the exit code are unchanged, the repository-total and not-checked rows carry neither signals nor label, and no address, domain or local part is printed. Every address is a made-up .zz name or an example.com name, and the real-looking local parts are obviously invented."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_committed_personal_data import CPD, ROW, csv, parquet_like, scan  # noqa: E402

spec = importlib.util.spec_from_file_location("committed_personal_data", CPD)
cpd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpd)

LABEL = "likely fixture: "
STEMS = (b"user", b"john", b"jane.doe", b"test_user", b"foo.bar", b"alice", b"demo")  # placeholder-style once the digits are dropped
FIRST = (b"zorblax", b"quimby", b"frobnitz", b"wibblet", b"glorpin", b"snarfle", b"thrumble", b"yonderk", b"vexilla", b"plonkus", b"drizzler", b"blimpo")
LAST = (b"fizzwick", b"snodgrass", b"bumbershoot", b"wigglesworth", b"tumblewick", b"crumplehorn")


def fake(n, domain="acme.zz", start=0):
    """n distinct placeholder-style addresses (bytes); `start` keeps two calls apart."""
    return [b"%s%d@%s" % (STEMS[i % len(STEMS)], i, domain.encode()) for i in range(start, start + n)]


def real(n, domain="acme.zz", start=0):
    """n distinct real-looking addresses (bytes) built from obviously invented names."""
    return [b"%s.%s%d@%s" % (FIRST[i % len(FIRST)], LAST[i % len(LAST)], i, domain.encode()) for i in range(start, start + n)]


def msg(n, pool, ph, rv, label=False, thr=10):
    """The message of a flagged-file row: `n` distinct addresses, `ph` placeholder-style and `rv` reserved-domain ones out of `pool`."""
    return "%s%d distinct email addresses (threshold %d); of %d counting reserved names, %d with placeholder-style local parts, %d on reserved domains" % (
        LABEL if label else "", n, thr, pool, ph, rv)


def rows(out):
    """{path: (rule, message)} of the TSV rows on stdout."""
    return {p: (rule, m) for p, _, rule, m in (line.split("\t") for line in out.splitlines())}


class Label(unittest.TestCase):
    def test_test_path_of_placeholder_addresses_is_labelled(self):
        rc, out, err = scan({"tests/people.csv": csv(fake(12))}, raw=True)
        self.assertEqual((rc, out, err), (0, "tests/people.csv" + ROW + msg(12, 12, 12, 0, True) + "\n", ""))

    def test_test_path_of_reserved_domains_is_labelled_and_a_default_scan_drops_the_file(self):
        files = {"spec/people.csv": csv(real(12, "example.com"))}  # real-looking local parts, but every address is on a reserved domain
        self.assertEqual(scan(files, "--include-reserved", raw=True)[1], "spec/people.csv" + ROW + msg(12, 12, 0, 12, True) + "\n")
        self.assertEqual(scan(files, raw=True), (0, "", ""))  # reserved names are not counted by default: no row, label or not

    def test_signals_do_not_change_with_include_reserved(self):
        mixed = {"tests/mixed.csv": csv(real(12) + real(30, "example.com", 50))}  # 12 counted, 30 reserved names the default count leaves out
        self.assertEqual(scan(mixed, raw=True)[1], "tests/mixed.csv" + ROW + msg(12, 42, 0, 30, True) + "\n")
        self.assertEqual(scan(mixed, "--include-reserved", raw=True)[1], "tests/mixed.csv" + ROW + msg(42, 42, 0, 30, True) + "\n")

    def test_test_path_of_real_looking_addresses_is_not_labelled(self):
        files = {"tests/real.csv": csv(real(12)),  # 0 of 12
                 "tests/few.csv": csv(real(10, start=20) + fake(2, start=40)),  # 2 of 12
                 "tests/under.csv": csv(fake(5, start=60) + real(7, start=70)),  # 5 of 12: just under half
                 "tests/half.csv": csv(fake(6, start=80) + real(6, start=90))}  # 6 of 12: at least half
        self.assertEqual(rows(scan(files, raw=True)[1]), {
            "tests/real.csv": ("email-addresses", msg(12, 12, 0, 0)),
            "tests/few.csv": ("email-addresses", msg(12, 12, 2, 0)),
            "tests/under.csv": ("email-addresses", msg(12, 12, 5, 0)),
            "tests/half.csv": ("email-addresses", msg(12, 12, 6, 0, True))})

    def test_a_non_test_path_is_never_labelled(self):
        paths = ("data/people.csv", "people.csv", "src/contest.csv", "latest.csv", "test-runner/people.csv", "docs/people.csv",
                 "examples/people.csv", "samples/people.csv")  # every file is all placeholder-style
        out = scan({p: csv(fake(12)) for p in paths}, raw=True)[1]
        self.assertEqual(rows(out), {p: ("email-addresses", msg(12, 12, 12, 0)) for p in paths})
        out = scan({"data/people.csv": csv(real(12, "example.com"))}, "--include-reserved", raw=True)[1]  # all on reserved domains, still no label
        self.assertEqual(rows(out), {"data/people.csv": ("email-addresses", msg(12, 12, 0, 12))})

    def test_each_test_path_form_is_labelled(self):
        paths = ("tests/a.csv", "test/a.csv", "src/test/resources/a.csv", "__tests__/a.csv", "__mocks__/a.csv", "spec/a.csv", "specs/a.csv",
                 "fixtures/a.csv", "__fixtures__/a.csv", "mocks/a.csv", "testdata/a.csv", "test_data/a.csv", "test-data/a.csv",
                 "people.test.csv", "test_people.csv", "people_spec.csv", "mock-people.csv", "people.fixture.csv", "people.mocks.csv")
        got = rows(scan({p: csv(fake(12)) for p in paths}, raw=True)[1])
        self.assertEqual(sorted(got), sorted(paths))
        self.assertEqual([p for p, (_, m) in got.items() if not m.startswith(LABEL)], [])

    def test_fixture_path_table(self):
        for p in ("tests/a.csv", "src/test/resources/a.csv", "__tests__/a.csv", "Tests/People.CSV", "a/FIXTURES/b.csv", "people.test.ts", "test_people.py",
                  "people_test", "user_spec.rb", "mock-users.json", "test.csv", "a/b/testdata/c.json"):
            self.assertTrue(cpd.fixture_path(p), p)
        for p in ("data/people.csv", "src/contest.csv", "latest.csv", "test-runner/a.csv", "mytests/a.csv", "tests_old/a.csv", "docs/a.csv",
                  "examples/a.csv", "samples/a.csv", "attest/a.csv", "protest_list.csv", "inspect.csv", "specification.md", "greatest-hits.csv"):
            self.assertFalse(cpd.fixture_path(p), p)

    def test_fixture_signals_counts_each_address_once(self):
        pool = {b"user1@example.com", b"john.doe@acme.zz", b"zorblax.fizzwick@acme.zz", b"1234@acme.zz", b"info@acme.zz", b"john.smith@acme.zz", b"x@host.test"}
        self.assertEqual(cpd.fixture_signals(pool), (2, 2, 3))  # placeholder-style: user1, john.doe; reserved: user1, x; either: user1, john.doe, x
        self.assertEqual(cpd.fixture_signals(set()), (0, 0, 0))

    def test_placeholder_style_local_parts(self):
        yes = [b"user", b"user12", b"john", b"jane.doe", b"test_user", b"foo+bar", b"Test.User", b"johndoe", b"testuser99", b"demo-1", b"fake.email",
               b"first.last", b"sample", b"alice.bob"]
        no = [b"john.smith", b"info", b"admin", b"1234", b"maria.zorblax", b"tester2x", b"usera", b"jsmith", b"zorblax"]
        words = csv([x + b"@acme.zz" for x in yes + no])
        self.assertEqual(scan({"tests/words.csv": words}, "--threshold", "1", raw=True)[1], "tests/words.csv" + ROW + msg(23, 23, len(yes), 0, True, 1) + "\n")


class HintOnly(unittest.TestCase):
    FILES = {"tests/ten.csv": csv(fake(10)),  # at the threshold: flagged and labelled
             "tests/nine.csv": csv(fake(9, start=100)),  # one below: no row, label or not
             "tests/small.parquet": parquet_like(fake(9, start=300)),  # a container under the threshold: its not-checked row stays as it was
             "tests/real.csv": csv(real(12)),
             "data/people.csv": csv(fake(12, start=200))}

    def test_no_row_dropped_and_no_threshold_changed(self):
        got = rows(scan(self.FILES, raw=True)[1])
        self.assertEqual(sorted(got), ["data/people.csv", "tests/real.csv", "tests/small.parquet", "tests/ten.csv"])  # nine.csv: 9 < 10 still gives no row
        self.assertEqual(got["tests/ten.csv"], ("email-addresses", msg(10, 10, 10, 0, True)))
        self.assertEqual(got["tests/real.csv"], ("email-addresses", msg(12, 12, 0, 0)))
        self.assertEqual(got["data/people.csv"], ("email-addresses", msg(12, 12, 12, 0)))
        rule, m = got["tests/small.parquet"]
        self.assertEqual(rule, "not-checked")
        self.assertTrue(m.startswith("compressed/columnar container (parquet)"), m)
        self.assertNotIn("placeholder", m)
        self.assertNotIn(LABEL, m)

    def test_a_labelled_row_is_still_a_strict_finding(self):
        self.assertEqual(scan({"tests/people.csv": csv(fake(12))}, "--strict")[0], 1)
        self.assertEqual(scan({"tests/people.csv": csv(fake(12))})[0], 0)
        self.assertEqual(scan({"tests/people.csv": csv(fake(9))}, "--strict")[0], 0)

    def test_the_repository_total_row_has_no_signals_and_no_label(self):
        spread = {"tests/s%d.csv" % i: csv(fake(9, start=1000 + 9 * i)) for i in range(6)}  # 54 distinct, no file reaches 10
        got = rows(scan(spread, raw=True)[1])
        self.assertEqual(list(got), ["."])
        rule, m = got["."]
        self.assertEqual(rule, "email-addresses")
        self.assertTrue(m.startswith("54 distinct email addresses across 6 file(s) that each stay below the file threshold 10 "), m)
        self.assertNotIn("placeholder", m)
        self.assertNotIn(LABEL, m)

    def test_only_counts_are_printed(self):
        files = {**self.FILES, "tests/mixed.csv": csv(real(12, start=500) + real(30, "example.com", 600))}
        out = scan(files, "--include-reserved", raw=True)[1]
        self.assertIn(LABEL, out)
        for _, _, _, m in (line.split("\t") for line in out.splitlines()):
            for leak in ("@", "acme", "zz", "example", "zorblax", "fizzwick", "Jane", "user", "john"):
                self.assertNotIn(leak, m)


if __name__ == "__main__":
    unittest.main()
