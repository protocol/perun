#!/usr/bin/env python3
"""invisible_chars.py hardening: locale files keep only bidi overrides, flag emoji tags are skipped, early-NUL files report only under a
text extension, UTF-16 decodes without NUL rows, fixture paths are no longer dropped (review_checks tags them), ESC in snapshots and logs
is skipped, 2 MB read cap, 200-row cap, per-row flush, newline-only path split, file-name scan; audit_skills: known binary
extension is `unscanned` unconditionally and fixtures are scanned. Hermetic: temp dirs only; special characters are built with chr()
so this file stays plain ASCII."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "deep-code-review" / "scripts"
sys.path.insert(0, str(SCRIPT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
import audit_skills  # noqa: E402
import invisible_chars as ic  # noqa: E402

NUL, ESC, BEL, RLO, LRO, RLM, LRE, ZWSP = chr(0), chr(27), chr(7), chr(0x202E), chr(0x202D), chr(0x200F), chr(0x202A), chr(0x200B)
FLAG = chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + chr(0xE007F)  # England


def rules(rel, text):
    return [r[1] for r in ic.scan_file(rel, text.encode("utf-8"))]


def cli(paths, cwd, timeout=60):
    return subprocess.run([sys.executable, str(SCRIPT / "invisible_chars.py")], cwd=cwd, input=paths, capture_output=True, text=True, timeout=timeout).stdout.split("\n")[:-1]


class Locale(unittest.TestCase):
    def test_locale_files_report_only_bidi_overrides_and_isolates(self):
        noise = "msgstr \"a" + RLM + ZWSP + LRE + "b\"\n"
        for rel in ("a.po", "x.ARB", "b.xlf", "b.xliff", "app.properties", "Localizable.strings", "src/locales/en.json", "app/i18n/en.yml", "l10n/en.txt"):
            self.assertEqual(rules(rel, noise), [], rel)
        for ch in (RLO, LRO, chr(0x2066), chr(0x2069)):
            self.assertEqual(rules("a.po", "x" + ch + "y"), ["hidden-unicode"], hex(ord(ch)))
        self.assertEqual(rules("src/app.js", noise), ["hidden-unicode"] * 3)  # same bytes outside a locale file are reported

    def test_locale_files_still_report_control_characters(self):
        self.assertEqual(rules("a.po", "x" + BEL), ["control-char"])

    def test_flag_emoji_tag_sequence_is_clean_but_loose_tags_are_not(self):
        self.assertEqual(rules("README.md", "England " + FLAG + " ok\n"), [])
        rows = ic.scan_file("a.md", ("x" + FLAG + chr(0xE0067) + "\n").encode())
        self.assertEqual(rows, [(1, "hidden-unicode", "hidden character U+E0067 at col 9")])  # a tag after the flag is not part of it
        self.assertEqual(rules("a.md", chr(0xE0067) + "abc"), ["hidden-unicode"])
        self.assertEqual(rules("a.md", chr(0x1F3F4) + chr(0xE0067) + "x"), ["hidden-unicode"])  # no cancel tag: not a flag sequence

    def test_audit_skills_skips_flag_emoji_too(self):
        self.assertEqual([r for r in audit_skills.scan_line(1, "flag " + FLAG) if r[2] == "hidden-unicode"], [])
        self.assertEqual([r[2] for r in audit_skills.scan_line(1, "x" + chr(0xE0067))], ["hidden-unicode"])


class Binary(unittest.TestCase):
    def test_early_nul_reports_only_under_a_text_extension(self):
        body = ("ab" + NUL + "cd" + NUL).encode()
        self.assertEqual(len(ic.scan_file("a.rs", body)), 1)
        self.assertEqual(ic.scan_file("blob.dat", body), [])
        self.assertEqual(ic.scan_file("Localizable.strings", b"bplist00" + body), [])  # a binary plist, not text
        self.assertEqual(ic.scan_file("a.golden", body), [])  # goldens are often binary
        self.assertEqual(ic.scan_file("noext", body), [])
        self.assertEqual(ic.scan_file("a.png", body), [])

    def test_utf16_with_bom_is_decoded_without_nul_rows(self):
        for enc in ("utf-16", "utf-16-be"):
            raw = (("" if enc == "utf-16" else chr(0xFEFF)) + "key = value" + ESC + "\n" + "more text here\n").encode(enc)  # "utf-16" writes its own BOM
            self.assertEqual(ic.scan_file("a.ini", raw), [(1, "control-char", "control character U+001B at col 12")], enc)
        self.assertEqual(ic.scan_file("a.ini", ("clean text\n" * 4).encode("utf-16")), [])

    def test_utf16_without_bom_sniffs_nuls_on_alternate_bytes(self):
        for enc in ("utf-16-le", "utf-16-be"):
            self.assertEqual(ic.scan_file("a.txt", ("hello world\n" * 5).encode(enc)), [], enc)
            raw = ("name = x" + RLO + "y\n" + "hello world\n").encode(enc)
            self.assertEqual([r[1] for r in ic.scan_file("a.txt", raw)], ["hidden-unicode"], enc)

    def test_random_nuls_are_not_mistaken_for_utf16(self):
        self.assertEqual(len(ic.scan_file("a.py", b"print(1)\n" * 50 + NUL.encode() + b"x")), 1)


class FixtureAndEsc(unittest.TestCase):
    def test_fixture_like_paths_are_scanned_not_dropped(self):
        for rel in ("tests/fixtures/a.txt", "testdata/b.py", "my-fixtures-lib/c.py", "unfixtured.py"):
            self.assertEqual(rules(rel, "x" + BEL), ["control-char"], rel)

    def test_esc_alone_is_skipped_in_snapshots_and_logs_but_other_controls_are_not(self):
        for rel in ("a.snap", "a.golden", "a.ANSI", "run.log", "src/__snapshots__/a.txt", "__snapshots__/b.js"):
            self.assertEqual(rules(rel, "\x1b[31mred" + ESC + "\n"), [], rel)
            self.assertEqual(rules(rel, "x" + BEL), ["control-char"], rel)
        for rel in ("a.py", "snapshots/a.txt", "a.logger", "x__snapshots__/a.txt"):
            self.assertEqual(rules(rel, "x" + ESC), ["control-char"], rel)

    def test_audit_skills_has_no_path_skip_and_known_binary_ext_is_unscanned(self):
        with tempfile.TemporaryDirectory() as td:
            for rel, body in {"fixtures/a.txt": ESC, "logo.png": "plain text " + ESC, "big.PDF": "x" * 1_500_000}.items():
                p = Path(td) / rel
                p.parent.mkdir(exist_ok=True)
                p.write_text(body)
            got = sorted((f["file"], f["rule"], f["message"]) for f in audit_skills.scan(td)[0])
        self.assertEqual([g[:2] for g in got], [("big.PDF", "unscanned"), ("fixtures/a.txt", "control-char"), ("logo.png", "unscanned")])
        self.assertIn("known binary extension", got[0][2])


class Limits(unittest.TestCase):
    def test_char_hits_counts_the_rest_up_to_a_cap(self):
        rows = ic.char_hits(ESC * 50000, ic.CTRL, "control character")
        self.assertEqual((len(rows), rows[-1][1]), (21, "10000+ more control characters not listed"))

    def test_file_over_2mb_is_read_in_part_with_a_hint_row(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "big.txt").write_bytes(b"a" * ic.MAX_READ + ("\n" + ESC).encode())  # the ESC lies past the cap
            Path(td, "ok.txt").write_bytes(b"a" * ic.MAX_READ)  # exactly at the cap: fully read
            out = cli("big.txt\nok.txt\n", td)
        self.assertEqual(out, ["big.txt\t0\tnot-checked\tpartially scanned: file over 2 MB, only the first 2 MB were read"])

    def test_row_cap_prints_200_then_one_summary_row_and_stops(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(30):
                Path(td, "f%02d.txt" % i).write_bytes((ESC + "\n").encode() * 10)
            out = cli("".join("f%02d.txt\n" % i for i in range(30)), td)
        self.assertEqual(len(out), 201)
        self.assertEqual(out[-1], "f20.txt\t0\tnot-checked\toutput capped at 200 rows; later findings and files were not scanned")

    def test_exactly_200_rows_have_no_summary_row(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.txt").write_bytes((ESC + "\n").encode() * 20)
            for i in range(9):
                Path(td, "b%d.txt" % i).write_bytes((ESC + "\n").encode() * 20)
            out = cli("a.txt\n" + "".join("b%d.txt\n" % i for i in range(9)), td)
        self.assertEqual(len(out), 200)

    def test_rows_are_flushed_per_file_so_a_hang_keeps_earlier_findings(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.txt").write_bytes(ESC.encode())
            os.mkfifo(os.path.join(td, "stuck"))  # open() for reading blocks until a writer appears
            with self.assertRaises(subprocess.TimeoutExpired) as cm:
                subprocess.run([sys.executable, str(SCRIPT / "invisible_chars.py")], cwd=td, input="a.txt\nstuck\n", capture_output=True, text=True, timeout=3)
        out = cm.exception.stdout
        self.assertEqual((out.decode() if isinstance(out, bytes) else out), "a.txt\t1\tcontrol-char\tcontrol character U+001B at col 1\n")


class Names(unittest.TestCase):
    def test_paths_split_on_newline_only_and_hidden_file_names_are_reported_at_line_0(self):
        ls = chr(0x2028)
        with tempfile.TemporaryDirectory() as td:
            names = ["a" + ls + "b.txt", "evil" + RLO + "txt.py", "clean.py"]
            for n in names:
                Path(td, n).write_bytes(b"x = 1\n" if n != names[0] else ESC.encode())
            out = cli("\n".join(names) + "\n", td)
        self.assertEqual(out, ["a" + ls + "b.txt\t1\tcontrol-char\tcontrol character U+001B at col 1",
                               "evil" + RLO + "txt.py\t0\thidden-unicode\thidden character in file name U+202E at col 5"])


if __name__ == "__main__":
    unittest.main()
