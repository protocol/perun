#!/usr/bin/env python3
"""committed_personal_data.py [--threshold N] [--repo-threshold N] [--include-reserved] [--strict] [--stdin] [--max-bytes N] [ROOT] — count distinct email addresses per tracked file and report the path and the count, never an address.

WHY THIS EXISTS
---------------
gitleaks, trufflehog and semgrep look for secrets. A committed export of real people's data (an arrow, parquet or csv report holding
hundreds of customer addresses) holds no secret, so every one of them passes it clean. This check counts instead of matching rules:
for each tracked file it counts the distinct email-shaped strings whose domain is not a reserved example or test name, and reports a
file whose count reaches a threshold. It is a lead, not a verdict: open the file locally and decide whether the people published the
data on purpose.

WHAT COUNTS
-----------
Files: every path of `git -C ROOT ls-files -z` (default ROOT is `.`), or with `--stdin` the newline-separated paths on stdin, relative
to ROOT (review_checks.sh passes the files it scans). Symlinks, directories (submodules) and paths missing on disk (a sparse
checkout) are skipped.

Bytes: up to `--max-bytes` (default 32 MiB, at most 1 GiB) of each file is read raw, with no decoding, so a text export and the plain
string bytes of a binary one (sqlite, pickles) are scanned the same way. A larger file is scanned over its first `--max-bytes` only: its
row says so when it is flagged, and when it is not it gets a `not-checked` row, so it never reads as a clean file. A file in a
recognised compressed or columnar format (see KNOWN CEILINGS) that stays under the threshold gets a `not-checked` row too.

Vendored paths: this script scans every path it is given and skips none. review_checks.sh drops vendored, build and worktree
directories (node_modules, vendor, dist, build, third_party, Pods, bower_components and so on) and *.min.js before it calls the script,
so run on its own it also reads those.

Address: ASCII `local@domain`; the local part is up to 64 characters of letters, digits and `._%+-`, the domain is up to 256 bytes of
dot-joined labels ending in a 2-24 letter label. Distinct means case-insensitive. Counting stops at 100000 distinct addresses per file.

Dropped unless `--include-reserved`: the reserved example and test names (example.com, example.net and example.org with their
subdomains, and the .test, .example, .invalid and .localhost top-level names), noreply forms (the word `noreply` or `donotreply`,
also written `no-reply`, `no_reply`, `do.not.reply` and so on, as a whole word of the local part or of a domain label, such as
users.noreply.github.com), the ssh account `git@` of git hosts (`git@github.com:org/repo.git`, `ssh://git@host/org/repo`: a local part of
exactly `git`) and image asset-scale names (`icon@2x.png`, `icon@1.5x.png`, `icon@2x-dark.png`: `@`, digits with an optional decimal
part, `x`, an optional `-word`, then one of png, jpg, jpeg, gif, webp, avif, svg, pdf, ico, bmp, tif, tiff, heic, heif or apng).
`--include-reserved` counts them too, so tests can plant fictional example.com fixtures.

Threshold (default 10, `--threshold N`): a file is reported at or above N distinct addresses. Prose and manifests (README, SECURITY,
CODEOWNERS, package.json) seldom name ten different mailboxes, and a data export names dozens to thousands. Random or compressed
bytes are no noise at that level: about 0.05 email-shaped strings per MB were measured (the unit tests scan 24 MiB of random bytes). A
contributor list (AUTHORS, MAINTAINERS, .mailmap) reaches 10 by design and is reported as a lead too; whether those people agreed to
publish is the reviewer's call.

Repository total (default 50, `--repo-threshold N`): addresses spread thin, one or two in each of dozens of per-person or per-record
files, never reach the file threshold. So the distinct addresses of all the files that stay below it are also counted together, and the
total is reported when it reaches N. A file already reported is left out, so no address is counted twice, and an address that appears in
many files counts once. 50 is five times the file threshold: a leak of per-record files runs to hundreds of addresses (the audit behind
this check found about 850), while a small repository seldom scatters 50 different mailboxes through its docs and headers. A large one
may, and then gets one lead row. `--threshold 1` lists the files behind the total.

OUTPUT
------
One TSV row per file on stdout, flushed per row: `path<TAB>0<TAB>rule<TAB>message`, the row shape invisible_chars.py prints, so
review_checks.sh adds each as a finding. Rule `email-addresses` carries the count ("12 distinct email addresses (threshold 10)"), and
once for the repository total under the path `.` ("69 distinct email addresses across 75 file(s) ..."); rule `not-checked` is surface
this scan did not cover (an unreadable file, one over the size cap, or a compressed/columnar container). Never an address, a domain or
a line of a file: only the path and the count (or the container format). Silent when there is nothing to report. Read-only; stdlib only.

EXIT CODES (fail closed)
------------------------
  0  advisory: finished, whatever it found (with `--strict`, nothing was flagged).
  1  `--strict` and at least one file, or the repository total, was flagged (`not-checked` rows alone do not count).
  2  bad usage, or `git ls-files` failed (not a repository): never a silent pass.

KNOWN CEILINGS
--------------
Addresses inside compressed streams are not reliably seen, and a parquet or Arrow file also stores its values in pages and buffers, so a
neighbouring value's tail can stick to an address (a reserved domain may then read as a real one, and a repeated value may count more
than once): a low count proves nothing about such a file. A file in one of the formats below that stays under the threshold therefore
gets a `not-checked` row (the format, never a value) instead of passing silently; one at or above the threshold is reported as usual,
as a lower bound. The formats are recognised from their magic bytes (CONTAINERS in this file), and only these are:
  parquet  `PAR1` at the start and the end, or `PARE` at both (encrypted footer)    arrow  `ARROW1` at the start and the end (IPC file)
  orc      `ORC` at the start and before the last byte (ORC 0.11 files lack the end magic and pass as plain bytes)
  zip      `PK\\x03\\x04` (also docx, xlsx, pptx, jar, epub)    gzip  `\\x1f\\x8b`    zstd  `\\x28\\xb5\\x2f\\xfd`    xz  `\\xfd7zXZ\\x00`
  7z       `7z\\xbc\\xaf\\x27\\x1c`    lz4 frame  `\\x04\\x22\\x4d\\x18`    bzip2  `BZh`, a digit 1-9, `1AY&SY`    avro  `Obj\\x01`    pdf  `%PDF-`
  zlib     a valid RFC 1950 header followed by data that decodes (a bare zlib stream)
A magic without its footer (a text file that opens with "PAR1" or "ORC") is not a parquet or ORC file and gets no row. Every other
compressed or columnar format (brotli, snappy, rar, an Arrow IPC stream, raw deflate, a file whose magic was cut off) is read as plain
bytes and can pass clean. UTF-16 text, non-ASCII addresses and obfuscated forms (`[at]`, `%40`, `\\u0040`) are not seen. Names are not
detected.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zlib

THRESHOLD = 10  # distinct addresses at or above which a file is reported
REPO_THRESHOLD = 50  # distinct addresses, over the files below THRESHOLD, at or above which the repository total is reported
MAX_READ = 32 << 20  # bytes read per file; the rest is reported as not scanned
MAX_READ_CAP = 1 << 30  # --max-bytes ceiling: read(n) sizes its buffer up front, so a huge n is a traceback (exit 1, which --strict reads as a finding)
MAX_COUNT = 100_000  # distinct addresses counted per file; the scan of that file stops there (bounds memory)
# (start, end, kind) byte regexes: a file that opens with `start` and ends with `end` holds compressed or columnar pages, where an address is
# not reliably seen, so it must not pass silently. Parquet (PAR1, or PARE with an encrypted footer) and Arrow repeat their magic as the
# footer, and an ORC postscript ends with "ORC" and one length byte: requiring that, and that the two magics do not overlap, keeps a text
# file that merely opens with "PAR1" or "ORC", or is only "PAR1", out.
CONTAINERS = (
    (rb"PAR1", rb"PAR1", "parquet"), (rb"PARE", rb"PARE", "parquet"), (rb"ARROW1", rb"ARROW1", "arrow"), (rb"ORC", rb"ORC.", "orc"),
    (rb"PK\x03\x04", b"", "zip"), (rb"\x1f\x8b", b"", "gzip"), (rb"\x28\xb5\x2f\xfd", b"", "zstd"), (rb"\xfd7zXZ\x00", b"", "xz"),
    (rb"7z\xbc\xaf\x27\x1c", b"", "7z"), (rb"\x04\x22\x4d\x18", b"", "lz4"), (rb"BZh[1-9]1AY&SY", b"", "bzip2"),
    (rb"Obj\x01", b"", "avro"), (rb"%PDF-", b"", "pdf"),
)

# The scan starts at each '@': the domain is matched within 256 bytes after it and the local part is read leftwards from the 64 bytes before
# it. One regex over the whole buffer would retry every start inside a long alphanumeric run (base64, hex, minified code), which is
# quadratic, and an unbounded domain match on `@a.a.a.` repeated for megabytes grows the regex stack to gigabytes.
DOMAIN = re.compile(rb"(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}")
LOCAL = re.compile(rb"[A-Za-z0-9._%+-]+")  # matched on the (reversed) 64 bytes before the '@'
# Run on one lower-cased address: example.com/net/org (and subdomains), the .test/.example/.invalid/.localhost names, noreply forms,
# image asset-scale names (icon@2x.png is a file name, not a mailbox) and the ssh account of git hosts (git@github.com:org/repo.git).
RESERVED = re.compile(
    rb"@(?:[a-z0-9-]+\.)*example\.(?:com|net|org)\Z"
    rb"|\.(?:test|example|invalid|localhost)\Z"
    rb"|(?<![a-z0-9])(?:no[-_.]?reply|do[-_.]?not[-_.]?reply)(?![a-z0-9])"
    rb"|@[0-9]+(?:\.[0-9]+)?x(?:-[a-z0-9]+)*\.(?:png|jpe?g|gif|webp|avif|svg|pdf|ico|bmp|tiff?|heic|heif|apng)\Z"
    rb"|\Agit@"
)


def addresses(buf: bytes, include_reserved: bool = False) -> set[bytes]:
    """The distinct lower-cased email-shaped strings in `buf` (at most MAX_COUNT: the scan stops there).

    Reserved example/test/localhost, noreply, `git@` and asset-scale (`icon@2x.png`) names are left out unless `include_reserved`.
    Edge cases: an empty buffer gives an empty set; a '@' with no letters, digits or `._%+-` before it, or with no dotted domain after
    it, is not an address; case variants of one address count once. Pure; no I/O.
    """
    found: set[bytes] = set()
    i = buf.find(b"@")
    while i != -1:
        dom = DOMAIN.match(buf, i + 1, i + 257)
        loc = LOCAL.match(buf[max(0, i - 64):i][::-1]) if dom else None
        if loc:
            addr = (loc.group()[::-1] + b"@" + dom.group()).lower()
            if include_reserved or not RESERVED.search(addr):
                found.add(addr)
                if len(found) >= MAX_COUNT:
                    break
        i = buf.find(b"@", i + 1)
    return found


def zlib_stream(head: bytes) -> bool:
    """True when `head` opens a zlib stream (RFC 1950): a deflate header whose check bits add up, and data that decodes.

    One text file in 31 that opens with a fitting pair of characters (`8` then `0`) passes the 2-byte header check by chance, so the
    first block must also decode: it must end inside `head` or run for 64 bytes without an error. Truncated input is fine; a stream
    that needs a preset dictionary is not recognised. Pure; the decoder reads at most 4 KiB and returns at most 4 KiB.
    """
    if len(head) < 2 or head[0] & 0x8F != 8 or (head[0] << 8 | head[1]) % 31:
        return False
    d = zlib.decompressobj()
    try:
        d.decompress(head[:4096], 4096)
    except zlib.error:
        return False
    return d.eof or len(head) >= 64


def container(buf: bytes, tail: bytes, size: int) -> str | None:
    """The compressed or columnar format a file is in, or None: `buf` is its first bytes, `tail` its last 8, `size` its length in bytes.

    Edge cases: an empty file, a magic without its footer (a text file that opens with "PAR1") and a file too short to hold both magics
    (a bare "PAR1" is one magic read as both ends) are None. `size` is the real length, not len(buf), which a small --max-bytes cuts. Pure; no I/O.
    """
    for start, end, kind in CONTAINERS:
        head, foot = re.match(start, buf), re.search(end + rb"\Z", tail, re.S)
        if head and foot and head.end() + foot.end() - foot.start() <= size:
            return kind
    return "zlib" if zlib_stream(buf[:4096]) else None


def tracked(root: str) -> list[str]:
    """The paths of `git -C root ls-files -z`. Exits 2 with git's own message when it fails (not a repository): never a silent clean."""
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
    if r.returncode:
        print("committed_personal_data: git ls-files failed in %s: %s" % (root, r.stderr.decode("utf-8", "replace").strip()), file=sys.stderr)
        sys.exit(2)
    return [os.fsdecode(p) for p in r.stdout.split(b"\0") if p]


def row(rel: str, rule: str, msg: str) -> None:
    """Print one TSV finding row, flushed. Tab and newline in the path become spaces so a hostile file name cannot split the row."""
    print("%s\t0\t%s\t%s" % (rel.replace("\t", " ").replace("\n", " "), rule, msg), flush=True)


def main(argv: list[str] | None = None) -> int:
    """Print one TSV row per flagged or unchecked file (see the module docstring); return the exit code. Read-only."""
    ap = argparse.ArgumentParser(prog="committed_personal_data.py", description="Count distinct email addresses per tracked file; never print one.")
    ap.add_argument("root", nargs="?", default=".", help="repository root (default .)")
    ap.add_argument("--threshold", type=int, default=THRESHOLD, help="report a file at or above this many distinct addresses (default %d)" % THRESHOLD)
    ap.add_argument("--repo-threshold", type=int, default=REPO_THRESHOLD, help="report the repository total at or above this many distinct addresses over the files below --threshold (default %d)" % REPO_THRESHOLD)
    ap.add_argument("--include-reserved", action="store_true", help="also count the reserved example/test names, noreply forms, git@ and asset-scale names (for fictional fixtures)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a file or the repository total is flagged (default: always exit 0)")
    ap.add_argument("--stdin", action="store_true", help="scan the newline-separated paths on stdin instead of every tracked file")
    ap.add_argument("--max-bytes", type=int, default=MAX_READ, help="bytes read per file (default %d, at most %d)" % (MAX_READ, MAX_READ_CAP))
    a = ap.parse_args(argv)
    if not 1 <= a.threshold <= MAX_COUNT:
        ap.error("--threshold must be between 1 and %d" % MAX_COUNT)
    if not 1 <= a.repo_threshold <= MAX_COUNT:
        ap.error("--repo-threshold must be between 1 and %d" % MAX_COUNT)
    if not 1 <= a.max_bytes <= MAX_READ_CAP:
        ap.error("--max-bytes must be between 1 and %d" % MAX_READ_CAP)
    for stream in (sys.stdin, sys.stdout):  # a non-UTF-8 file name must not crash the scan: that would hide every file
        stream.reconfigure(errors="surrogateescape")
    paths = [p for p in sys.stdin.read().split("\n") if p] if a.stdin else tracked(a.root)
    flagged = holders = 0
    spread: set[bytes] = set()  # the distinct addresses of the files that stay under --threshold, for the repository total
    for rel in paths:
        p = os.path.join(a.root, rel)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as fh:
                buf = fh.read(a.max_bytes + 1)
                size = os.fstat(fh.fileno()).st_size
                fh.seek(max(0, size - 8))
                tail = fh.read(8)  # the footer of a parquet, Arrow or ORC file; past `buf` when the file is over the cap
        except OSError as e:
            row(rel, "not-checked", "unreadable: %s" % e.strerror)
            continue
        big = len(buf) > a.max_bytes
        found = addresses(buf[:a.max_bytes], a.include_reserved)
        n = len(found)
        partial = "; only the first %d bytes were read" % a.max_bytes if big else ""
        kind = container(buf, tail, size)
        if n >= a.threshold:
            flagged += 1
            row(rel, "email-addresses", "%d%s distinct email addresses (threshold %d)%s" % (n, "+" * (n >= MAX_COUNT), a.threshold, partial))
            continue
        holders += bool(found)
        if len(spread) < MAX_COUNT:  # bounds memory: the total stops growing there
            spread |= found
        if kind:
            row(rel, "not-checked", "compressed/columnar container (%s): addresses inside its pages may not be seen, so this is not a clean result%s" % (kind, partial))
        elif big:
            row(rel, "not-checked", "partially scanned: file over %d bytes, only the first %d were read" % (a.max_bytes, a.max_bytes))
    if len(spread) >= a.repo_threshold:
        flagged += 1
        row(".", "email-addresses", "%d%s distinct email addresses across %d file(s) that each stay below the file threshold %d (repository threshold %d; --threshold 1 lists the files)" % (
            len(spread), "+" * (len(spread) >= MAX_COUNT), holders, a.threshold, a.repo_threshold))
    return 1 if a.strict and flagged else 0


if __name__ == "__main__":
    sys.exit(main())
