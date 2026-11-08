#!/usr/bin/env python3
"""Tests: committed_personal_data.py prints one not-checked row for a compressed or columnar container kind that more than 3 files share (under the first path in sorted order, naming the first 3), keeps one row per file for a kind of 3 or fewer, never groups partial-scan rows, sanitises tabs in the named paths, and leaves the email-addresses rows and the repository total unchanged. Every file is built in a temporary repository; the addresses are example.com fixtures and the file names are invented."""
import gzip
import unittest

from test_committed_personal_data import addrs, csv, scan

GZ_DATA = gzip.compress(b"no addresses here")
PDF_DATA = b"%PDF-1.4\n% no addresses here\n"
ZIP_DATA = b"PK\x03\x04" + b"\0" * 26
CONTAINER = "compressed/columnar container (%s): addresses inside its pages may not be seen, so this is not a clean result%s"
COLLAPSED = "%d %s containers not scanned (first 3: %s): addresses inside their pages may not be seen, so this is not a clean result"


def rows(out):
    """{path: (rule, message)} of the TSV rows on stdout."""
    return {p: (rule, m) for p, _, rule, m in (line.split("\t") for line in out.splitlines())}


class Collapse(unittest.TestCase):
    def test_more_than_three_collapse_to_one_row_under_the_first_sorted_path(self):
        files = {"dumps/c.gz": GZ_DATA, "dumps/a.gz": GZ_DATA, "dumps/e.gz": GZ_DATA, "dumps/b.gz": GZ_DATA, "dumps/d.gz": GZ_DATA}
        rc, out, err = scan(files, raw=True)
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out, "dumps/a.gz\t0\tnot-checked\t%s\n" % (
            COLLAPSED % (5, "gzip", "dumps/a.gz, dumps/b.gz, dumps/c.gz")))
        self.assertEqual(scan(files, "--strict")[0], 0)  # not-checked rows alone are no finding, collapsed or not

    def test_exactly_three_keep_one_row_per_file(self):
        files = {"dumps/c.gz": GZ_DATA, "dumps/a.gz": GZ_DATA, "dumps/b.gz": GZ_DATA}
        rc, out, _ = scan(files, raw=True)
        self.assertEqual((rc, out), (0, "".join("%s\t0\tnot-checked\t%s\n" % (p, CONTAINER % ("gzip", "")) for p in ("dumps/a.gz", "dumps/b.gz", "dumps/c.gz"))))

    def test_mixed_kinds_group_separately(self):
        files = {"dumps/%s.gz" % n: GZ_DATA for n in "abcd"}
        files.update({"docs/p%d.pdf" % i: PDF_DATA for i in range(1, 5)})
        files.update({"z1.zip": ZIP_DATA, "z2.zip": ZIP_DATA})
        got = rows(scan(files, raw=True)[1])
        self.assertEqual(got, {
            "dumps/a.gz": ("not-checked", COLLAPSED % (4, "gzip", "dumps/a.gz, dumps/b.gz, dumps/c.gz")),
            "docs/p1.pdf": ("not-checked", COLLAPSED % (4, "pdf", "docs/p1.pdf, docs/p2.pdf, docs/p3.pdf")),
            "z1.zip": ("not-checked", CONTAINER % ("zip", "")),
            "z2.zip": ("not-checked", CONTAINER % ("zip", "")),
        })

    def test_address_findings_and_their_counts_are_unaffected(self):
        files = {"people.csv": csv(addrs(12)), **{"dumps/%s.gz" % n: GZ_DATA for n in "abcd"}}
        got = rows(scan(files, "--include-reserved", raw=True)[1])
        self.assertEqual(set(got), {"people.csv", "dumps/a.gz"})
        rule, message = got["people.csv"]
        self.assertEqual(rule, "email-addresses")
        self.assertTrue(message.startswith("12 distinct email addresses (threshold 10); of 12 counting reserved names, "), message)
        self.assertEqual(got["dumps/a.gz"], ("not-checked", COLLAPSED % (4, "gzip", "dumps/a.gz, dumps/b.gz, dumps/c.gz")))

    def test_partial_scan_rows_are_never_grouped(self):
        files = {"dumps/%s.gz" % n: gzip.compress(bytes(range(256)) * 2) for n in "abcd"}
        rc, out, _ = scan(files, "--max-bytes", "100", raw=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "".join("dumps/%s.gz\t0\tnot-checked\t%s\n" % (n, CONTAINER % ("gzip", "; only the first 100 bytes were read")) for n in "abcd"))

    def test_tab_in_a_named_path_cannot_split_the_collapsed_row(self):
        files = {"a\tb.gz": GZ_DATA, "c.gz": GZ_DATA, "d.gz": GZ_DATA, "e.gz": GZ_DATA}
        rc, out, _ = scan(files, raw=True)
        self.assertEqual(out, "a b.gz\t0\tnot-checked\t%s\n" % (COLLAPSED % (4, "gzip", "a b.gz, c.gz, d.gz")))


if __name__ == "__main__":
    unittest.main()
