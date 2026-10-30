#!/usr/bin/env python3
"""Tests: committed_personal_data.py counts distinct non-reserved email addresses per tracked file (CSV and binary-ish alike), reports path and count only and never an address, drops reserved, noreply, git@ and asset-scale names unless --include-reserved, honors the threshold edge, --strict, --stdin and the size cap, reports the repository total of addresses spread thin over files that each stay below the threshold, gives a file in a recognised compressed or columnar format under the threshold a not-checked row (never a silent pass; parquet, Arrow and ORC need their footer, a zlib header must decode), and fails closed outside a repository or on a bad flag value (no traceback). Every address is a fictional example.com/example.org name or a made-up .zz domain."""
import bz2
import gzip
import importlib.util
import lzma
import os
import random
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
import zlib
from pathlib import Path

CPD = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/committed_personal_data.py"
ROW = "\t0\temail-addresses\t"


def addrs(n, domain="example.com", start=1):
    """n distinct fictional addresses, bytes."""
    return [b"fixture-user-%04d@%s" % (i, domain.encode()) for i in range(start, start + n)]


def csv(a):
    return b"id,name,email\n" + b"".join(b"%d,Jane Smith,%s\n" % (i, x) for i, x in enumerate(a))


def parquet_like(a):
    """Magic, 4-byte little-endian length prefix per value (PLAIN byte arrays), NUL padding, magic."""
    return b"PAR1" + b"".join(len(x).to_bytes(4, "little") + x for x in a) + b"\0" * 64 + b"PAR1"


def arrow_like(a):
    """String values glued back to back after an offsets buffer, as Arrow lays them out."""
    off = [0]
    for x in a:
        off.append(off[-1] + len(x))
    return b"ARROW1\0\0" + b"".join(o.to_bytes(4, "little") for o in off) + b"".join(a) + b"\0" * 8 + b"ARROW1"


def scan(files, *args, stdin=None, links=None, git=True):
    """Build a throwaway repo from {path: bytes}, run the script on it, return (exit code, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        for rel, data in files.items():
            Path(d, rel).write_bytes(data)
        for name, target in (links or {}).items():
            os.symlink(target, Path(d, name))
        env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(d).parent)}
        if git:
            subprocess.run(["git", "-C", d, "init", "-q"], check=True, env=env)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True, env=env)
        r = subprocess.run([sys.executable, str(CPD), *args, d], input=stdin, capture_output=True, text=True, env=env, timeout=60)
        return r.returncode, r.stdout, r.stderr


class Fixtures(unittest.TestCase):
    FILES = {"export.csv": csv(addrs(12)), "data.parquet": parquet_like(addrs(12, "example.org"))}

    def test_csv_and_binary_flagged_with_include_reserved(self):
        rc, out, err = scan(self.FILES, "--include-reserved")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(sorted(out.splitlines()), [
            "data.parquet" + ROW + "12 distinct email addresses (threshold 10)",
            "export.csv" + ROW + "12 distinct email addresses (threshold 10)"])

    def test_arrow_like_glued_values_flagged(self):
        rc, out, _ = scan({"data.arrow": arrow_like(addrs(12, "acme.zz"))})
        self.assertEqual((rc, out), (0, "data.arrow" + ROW + "12 distinct email addresses (threshold 10)\n"))

    def test_same_fixtures_clean_without_include_reserved(self):
        rc, out, err = scan(self.FILES)  # no email-addresses row; the parquet-like file starts with PAR1, so it is a not-checked row instead
        self.assertEqual((rc, err, out.count("\n")), (0, "", 1))
        self.assertTrue(out.startswith("data.parquet\t0\tnot-checked\tcompressed/columnar container (parquet)"), out)

    def test_no_address_or_domain_in_output(self):
        files = {**self.FILES, "people.csv": csv(addrs(12, "acme.zz"))}
        for args in ((), ("--include-reserved",), ("--include-reserved", "--strict")):
            rc, out, err = scan(files, *args)
            self.assertIn(rc, (0, 1))
            self.assertIn("people.csv" + ROW, out)  # findings were printed ...
            for leak in ("@", "fixture-user", "example", "acme", "Jane"):
                self.assertNotIn(leak, out + err)  # ... and none carries a value

    def test_threshold_edge(self):
        nine, ten = addrs(9), addrs(10)
        noisy = csv(nine + [x.upper() for x in nine] + nine)  # repeats and case variants count once
        files = {"nine.csv": noisy, "ten.csv": csv(ten)}
        self.assertEqual(scan(files, "--include-reserved")[1], "ten.csv" + ROW + "10 distinct email addresses (threshold 10)\n")
        self.assertEqual(scan(files, "--include-reserved", "--threshold", "9")[1].splitlines(), [
            "nine.csv" + ROW + "9 distinct email addresses (threshold 9)", "ten.csv" + ROW + "10 distinct email addresses (threshold 9)"])
        self.assertEqual(scan(files, "--include-reserved", "--threshold", "11")[1], "")

    def test_default_counts_unreserved_domains_and_drops_reserved(self):
        mixed = csv(addrs(6, "acme.zz") + addrs(6, "example.com", 7))
        self.assertEqual(scan({"m.csv": mixed})[1], "")
        self.assertEqual(scan({"m.csv": mixed}, "--include-reserved")[1], "m.csv" + ROW + "12 distinct email addresses (threshold 10)\n")
        more = csv(addrs(10, "acme.zz") + addrs(6, "example.com", 11))
        self.assertEqual(scan({"m.csv": more})[1], "m.csv" + ROW + "10 distinct email addresses (threshold 10)\n")

    def test_reserved_and_noreply_forms_dropped_lookalikes_counted(self):
        dropped = [b"a1@example.com", b"a2@example.net", b"a3@example.org", b"a4@mail.example.com", b"a5@host.test",
                   b"a6@host.example", b"a7@host.invalid", b"a8@host.localhost", b"noreply@acme.zz", b"no-reply@acme.zz",
                   b"donotreply@acme.zz", b"do-not-reply@acme.zz", b"a9@users.noreply.acme.zz", b"my.noreply@acme.zz"]
        counted = [b"b1@example.com.zz", b"b2@pre.zztest", b"b3@host.zzexample", b"noreplyfan@acme.zz"]  # a reserved name only as part of another label
        files = {"dropped.txt": b"\n".join(dropped), "counted.txt": b"\n".join(counted)}
        self.assertEqual(scan(files, "--threshold", "1")[1], "counted.txt" + ROW + "4 distinct email addresses (threshold 1)\n")
        self.assertEqual(scan(files, "--threshold", "1", "--include-reserved")[1].splitlines(), [
            "counted.txt" + ROW + "4 distinct email addresses (threshold 1)",
            "dropped.txt" + ROW + "14 distinct email addresses (threshold 1)"])

    def test_asset_scale_names_are_not_addresses(self):
        exts = (b"png", b"jpg", b"jpeg", b"gif", b"webp", b"svg", b"pdf", b"avif", b"ico", b"bmp", b"tif", b"tiff", b"heic", b"heif", b"apng")
        scales = (b"2x", b"3x", b"1.5x", b"2x-dark", b"3x-dark-hc")  # what an iOS Contents.json, an Android res dir or a web manifest lists
        assets = b"\n".join(b"icon-%02d@%s.%s" % (i, scales[i % 5], ext) for i, ext in enumerate(exts))
        self.assertEqual(scan({"Contents.json": assets})[1], "")
        self.assertEqual(scan({"Contents.json": assets}, "--include-reserved")[1], "Contents.json" + ROW + "15 distinct email addresses (threshold 10)\n")
        near = b"\n".join(b"n%02d@2x.zz" % i for i in range(12))  # a digits-x first label is dropped only before an image extension
        self.assertEqual(scan({"near.txt": near})[1], "near.txt" + ROW + "12 distinct email addresses (threshold 10)\n")
        other = b"\n".join(b"n%d@%s" % (i, t) for i, t in enumerate((b"2x-dark.zz", b"2x.png.zz", b"x2.png", b"2x.pngx", b"1.5.png")))
        self.assertEqual(scan({"other.txt": other}, "--threshold", "1")[1], "other.txt" + ROW + "5 distinct email addresses (threshold 1)\n")

    def test_git_ssh_account_is_not_an_address(self):
        remotes = b"\n".join(b"git@host%02d.zz:org/repo.git\nssh://git@host%02d.zz/org/repo" % (i, i + 6) for i in range(6))  # 12 hosts
        self.assertEqual(scan({"deps.txt": remotes})[1], "")
        self.assertEqual(scan({"deps.txt": remotes}, "--include-reserved")[1], "deps.txt" + ROW + "12 distinct email addresses (threshold 10)\n")
        people = b"\n".join(user + b"@acme.zz" for user in (b"mygit", b"x.git", b"git2", b"git-bot", b"git+x"))  # git only inside a longer local part; built, so this file stays under the threshold itself
        self.assertEqual(scan({"people.txt": people}, "--threshold", "1")[1], "people.txt" + ROW + "5 distinct email addresses (threshold 1)\n")

    def test_strict_exit_codes(self):
        flagged, clean = {"a.csv": csv(addrs(12))}, {"a.csv": csv(addrs(2))}
        self.assertEqual(scan(flagged, "--include-reserved")[0], 0)
        self.assertEqual(scan(flagged, "--include-reserved", "--strict")[0], 1)
        self.assertEqual(scan(clean, "--include-reserved", "--strict")[0], 0)

    def test_size_cap_flags_partial_and_never_reads_as_clean(self):
        pad = b"." * 2000
        hit = scan({"a.csv": csv(addrs(12)) + pad}, "--include-reserved", "--max-bytes", "1000")[1]
        self.assertEqual(hit, "a.csv" + ROW + "12 distinct email addresses (threshold 10); only the first 1000 bytes were read\n")
        late = scan({"b.csv": csv(addrs(2)) + pad + csv(addrs(12, start=50))}, "--include-reserved", "--max-bytes", "1000")[1]
        self.assertEqual(late, "b.csv\t0\tnot-checked\tpartially scanned: file over 1000 bytes, only the first 1000 were read\n")
        self.assertEqual(scan({"c.csv": b"." * 1000}, "--max-bytes", "1000")[1], "")  # exactly the cap: fully scanned
        self.assertIn("not-checked", scan({"c.csv": b"." * 1001}, "--max-bytes", "1000")[1])

    def test_count_cap_marks_plus(self):
        out = scan({"big.csv": csv(addrs(100_000))}, "--include-reserved")[1]
        self.assertEqual(out, "big.csv" + ROW + "100000+ distinct email addresses (threshold 10)\n")

    def test_stdin_limits_files_and_symlinks_are_skipped(self):
        files = {"a.csv": csv(addrs(12)), "b.csv": csv(addrs(12))}
        rows = scan(files, "--include-reserved", links={"c.csv": "a.csv"})[1].splitlines()
        self.assertEqual([r.split("\t")[0] for r in sorted(rows)], ["a.csv", "b.csv"])
        self.assertEqual(scan(files, "--include-reserved", "--stdin", stdin="a.csv\ngone.csv\n\n")[1].splitlines(), [
            "a.csv" + ROW + "12 distinct email addresses (threshold 10)"])

    def test_hostile_file_name_cannot_split_the_row(self):
        out = scan({"a\tb.csv": csv(addrs(12))}, "--include-reserved")[1]
        self.assertEqual(out, "a b.csv" + ROW + "12 distinct email addresses (threshold 10)\n")

    @unittest.skipIf(os.geteuid() == 0, "root can read mode 000 files")
    def test_unreadable_file_is_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "locked.csv").write_bytes(csv(addrs(12)))
            subprocess.run(["git", "-C", d, "init", "-q"], check=True)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            os.chmod(Path(d, "locked.csv"), 0)  # after the add: git cannot index an unreadable file
            r = subprocess.run([sys.executable, str(CPD), d], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, "locked.csv\t0\tnot-checked\tunreadable: Permission denied\n"))

    def test_non_utf8_file_names_do_not_crash_the_scan(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(CPD), "--stdin", d], input=b"caf\xe9.csv\n", capture_output=True)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))  # a path that is not there is skipped, not a decode error
            try:
                Path(os.fsdecode(os.fsencode(d) + b"/caf\xe9.csv")).write_bytes(csv(addrs(12)))
            except OSError:
                self.skipTest("this file system refuses non-UTF-8 file names")  # macOS; Linux runs the rest
            subprocess.run(["git", "-C", d, "init", "-q"], check=True)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            r = subprocess.run([sys.executable, str(CPD), "--include-reserved", d], capture_output=True)
        self.assertEqual((r.returncode, r.stdout), (0, b"caf\xe9.csv" + ROW.encode() + b"12 distinct email addresses (threshold 10)\n"))

    def test_fails_closed_outside_a_repository_and_on_bad_usage(self):
        rc, out, err = scan({"a.csv": csv(addrs(12))}, git=False)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("git ls-files failed", err)
        for bad in (["--threshold", "0"], ["--threshold", "100001"], ["--max-bytes", "0"], ["--threshold", "x"],
                    ["--repo-threshold", "0"], ["--repo-threshold", "100001"], ["--repo-threshold", "x"],
                    ["--max-bytes", "1073741825"], ["--max-bytes", "99999999999999999999"]):  # a huge size was a traceback with exit 1
            rc, _, err = scan({"a.csv": b""}, *bad)
            self.assertEqual(rc, 2, bad)
            self.assertIn("usage: committed_personal_data.py", err)
            self.assertNotIn("Traceback", err)
        for edge in ("1", "100000"):  # both ends of the --repo-threshold range are accepted
            self.assertEqual(scan({"a.csv": b""}, "--repo-threshold", edge), (0, "", ""))


class RepositoryTotal(unittest.TestCase):
    @staticmethod
    def spread(files, per, start=1):
        """`files` files of `per` distinct acme.zz addresses each, none reaching the file threshold."""
        return {"f%02d.txt" % i: csv(addrs(per, "acme.zz", start + i * per)) for i in range(files)}

    @staticmethod
    def total(n, files, limit=50):
        return ".%s%d distinct email addresses across %d file(s) that each stay below the file threshold 10 (repository threshold %d; --threshold 1 lists the files)\n" % (ROW, n, files, limit)

    def test_addresses_spread_thin_reach_a_repository_total(self):
        self.assertEqual(scan(self.spread(20, 3)), (0, self.total(60, 20), ""))  # 60 distinct, 3 per file: no file is flagged

    def test_total_edge_repeats_and_flagged_files(self):
        files = self.spread(25, 2)  # 50 distinct
        self.assertEqual(scan(files)[1], self.total(50, 25))
        self.assertEqual(scan(files, "--repo-threshold", "51")[1], "")
        same = {"f%02d.txt" % i: csv(addrs(3, "acme.zz")) for i in range(30)}  # the same 3 addresses in 30 files count once
        self.assertEqual(scan(same, "--repo-threshold", "4")[1], "")
        self.assertEqual(scan(same, "--repo-threshold", "3")[1], self.total(3, 30, 3))
        flagged = "big.csv" + ROW + "12 distinct email addresses (threshold 10)"
        big = {**self.spread(20, 2), "big.csv": csv(addrs(12, "acme.zz", 5000))}  # 40 spread + one flagged file, whose 12 are left out of the total
        self.assertEqual(scan(big)[1], flagged + "\n")
        self.assertEqual(scan(big, "--repo-threshold", "40")[1].splitlines(), [flagged, self.total(40, 20, 40).rstrip("\n")])

    def test_total_is_a_strict_finding_and_follows_include_reserved_and_stdin(self):
        files = self.spread(20, 3)
        self.assertEqual([scan(files)[0], scan(files, "--strict")[0], scan(self.spread(10, 3), "--strict")[0]], [0, 1, 0])  # 60, then 30 < 50
        self.assertEqual(scan({"d.bin": b"PK\x03\x04" + b"\0" * 16}, "--strict")[0], 0)  # a not-checked row alone is no finding
        reserved = {"f%02d.txt" % i: csv(addrs(3, "example.com", 1 + 3 * i)) for i in range(20)}
        self.assertEqual(scan(reserved), (0, "", ""))
        self.assertEqual(scan(reserved, "--include-reserved")[1], self.total(60, 20))
        self.assertEqual(scan(files, "--stdin", stdin="\n".join(list(files)[:10]))[1], "")  # only the listed files are counted: 30 < 50


class Containers(unittest.TestCase):
    # (kind, bytes at the start, bytes at the end): parquet, Arrow and ORC repeat their magic at the end, the others are told by the start alone
    FORMATS = (
        ("parquet", b"PAR1", b"PAR1"), ("parquet", b"PARE", b"PARE"), ("arrow", b"ARROW1\0\0", b"ARROW1"), ("orc", b"ORC", b"ORC\x1b"),
        ("zip", b"PK\x03\x04", b""), ("gzip", b"\x1f\x8b\x08\x00", b""), ("zstd", b"\x28\xb5\x2f\xfd", b""), ("xz", b"\xfd7zXZ\x00", b""),
        ("7z", b"7z\xbc\xaf\x27\x1c", b""), ("lz4", b"\x04\x22\x4d\x18", b""), ("bzip2", b"BZh91AY&SY", b""), ("avro", b"Obj\x01", b""),
        ("pdf", b"%PDF-1.7\n", b""), ("zlib", b"\x78\x9c\x03\x00\x00\x00\x00\x01", b""),  # an empty zlib stream: header, final empty block, adler32
    )

    @staticmethod
    def blob(start, end, n):
        return start + b"\0" * 8 + b"\n".join(addrs(n, "acme.zz")) + b"\0" * 8 + end

    def test_container_under_the_threshold_is_not_checked_never_silent(self):
        for kind, start, end in self.FORMATS:  # 9 addresses < 10: such a file used to pass silently
            rc, out, err = scan({"data.bin": self.blob(start, end, 9)})
            self.assertEqual((rc, err, out.count("\n")), (0, "", 1), (kind, start))
            path, line, rule, msg = out.rstrip("\n").split("\t")
            self.assertEqual((path, line, rule), ("data.bin", "0", "not-checked"), (kind, start))
            self.assertIn("compressed/columnar container (%s)" % kind, msg)
            for leak in ("@", "fixture-user", "acme"):
                self.assertNotIn(leak, out)

    def test_container_at_or_over_the_threshold_is_flagged_once(self):
        for kind, start, end in self.FORMATS:
            out = scan({"data.bin": self.blob(start, end, 12)})[1]
            self.assertEqual(out, "data.bin" + ROW + "12 distinct email addresses (threshold 10)\n", kind)

    def test_magic_counts_only_at_the_start_of_the_file(self):
        files = {"late.bin": b"x" + self.blob(b"PAR1", b"PAR1", 9), "plain.csv": csv(addrs(9, "acme.zz"))}
        self.assertEqual(scan(files), (0, "", ""))

    def test_a_magic_without_its_footer_is_not_a_container(self):
        tail = b"\n".join(addrs(3, "acme.zz")) + b"\n"
        names = {"a.txt": b"PAR1 is a name\n", "b.txt": b"PARE is a name\n", "c.txt": b"ARROW1 is a name\n", "d.txt": b"ORC Holdings is a name\n"}
        self.assertEqual(scan({k: v + tail for k, v in names.items()}), (0, "", ""))
        self.assertEqual(scan({"cut.parquet": b"PAR1" + b"\0" * 8 + tail}), (0, "", ""))  # a truncated file has no footer either

    def test_start_and_end_magics_must_not_overlap(self):
        self.assertEqual(scan({"a.parquet": b"PAR1", "b.orc": b"ORC\n", "c.arrow": b"ARROW1"}), (0, "", ""))  # one magic read as both ends
        out = scan({"a.parquet": b"PAR1PAR1", "b.orc": b"ORCORC\n", "c.arrow": b"ARROW1ARROW1"})[1]  # the shortest files that hold both
        self.assertEqual([r.split("\t")[0] for r in out.splitlines()], ["a.parquet", "b.orc", "c.arrow"], out)

    def test_the_footer_is_read_from_the_end_of_a_file_over_the_cap(self):
        out = scan({"d.parquet": self.blob(b"PAR1", b"PAR1", 9)}, "--max-bytes", "100")[1]
        self.assertTrue(out.startswith("d.parquet\t0\tnot-checked\tcompressed/columnar container (parquet)"), out)
        self.assertTrue(out.endswith("; only the first 100 bytes were read\n"), out)
        out = scan({"d.parquet": self.blob(b"PAR1", b"PAR1", 9)}, "--max-bytes", "5")[1]  # a cap shorter than both magics still sees parquet
        self.assertTrue(out.startswith("d.parquet\t0\tnot-checked\tcompressed/columnar container (parquet)"), out)

    def test_real_compressed_exports_are_never_silent(self):
        data = csv(addrs(3000, "acme.zz"))
        pdf = b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + zlib.compress(data) + b"\nendstream\nendobj\n%%EOF\n"
        for kind, blob in (("gzip", gzip.compress(data, mtime=0)), ("bzip2", bz2.compress(data)), ("xz", lzma.compress(data)),
                           ("zlib", zlib.compress(data)), ("zlib", zlib.compress(b"hi")), ("pdf", pdf)):
            rc, out, err = scan({"export.bin": blob})
            self.assertEqual((rc, err), (0, ""), kind)
            self.assertTrue(out.startswith("export.bin\t0\tnot-checked\tcompressed/columnar container (%s)" % kind), (kind, out))
            self.assertEqual(out.count("\n"), 1, kind)
            self.assertNotIn("@", out)

    def test_zlib_header_lookalikes_are_not_zlib(self):
        files = {"tok.txt": b"807", "math.txt": b"x^2 + y^2 = 1\n" * 40, "pair.txt": b"x\x9c is not deflate data, only a header-shaped pair of bytes\n"}
        self.assertEqual(scan(files), (0, "", ""))  # each opens with a pair that passes the 2-byte header check (x^, 80, x + 0x9c)


class Noise(unittest.TestCase):
    def test_random_bytes_stay_under_the_default_threshold(self):
        files = {"r%d.bin" % s: random.Random(s).randbytes(8 << 20) for s in range(3)}
        self.assertEqual(scan(files), (0, "", ""))

    def test_long_runs_scan_in_linear_time(self):
        rc, out, _ = scan({"run.txt": b"a" * (8 << 20), "ats.txt": (b"a" * 100 + b"@a.bc ") * 100_000})
        self.assertEqual((rc, out), (0, ""))


    def test_dotted_run_after_an_at_sign_uses_bounded_memory(self):
        spec = importlib.util.spec_from_file_location("committed_personal_data", CPD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        buf = b"x@" + b"a." * (1 << 20)  # an unbounded domain match grew the regex stack to ~140 MB here
        tracemalloc.start()
        try:
            self.assertEqual(mod.addresses(buf, True), set())
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 16 << 20)


if __name__ == "__main__":
    unittest.main()
