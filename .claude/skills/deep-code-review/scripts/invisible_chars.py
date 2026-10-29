#!/usr/bin/env python3
"""invisible_chars.py - flag NUL, control and hidden characters in text files.

Input: paths on stdin, one per line (newline-split only), relative to the cwd.

Prints one TSV row per finding on stdout, flushed per row: `file<TAB>line<TAB>rule<TAB>message`, with rule `control-char`
(NUL and other C0 controls except tab, LF, CR, FF), `hidden-unicode` (bidi overrides, zero-width, tag and variation-selector
characters; ZWJ/ZWNJ/VS16 only beside ASCII so emoji and Persian text stay clean; tag characters inside a flag emoji
sequence are part of the glyph and skipped; a file NAME is scanned too, at line 0) or `not-checked` (surface this scan did not
cover), and a message carrying the codepoint and 1-based column. At most 20 findings per rule and file then one count row, and
at most 200 rows in all, then one `not-checked` row and the scan stops. Only the first 2 MB of a file is read; a larger file adds a
`partially scanned` row. Path-based leniency (callers that want none, like audit_skills.py, use control_findings and
HIDDEN directly): locale files (.po .arb .xlf .xliff .properties .strings, or under locales/ i18n/ l10n/) report only bidi
overrides and isolates, not RLM/LRM/embeds/ZWSP; ESC alone is not reported in .snap, .golden, .ansi, .log or __snapshots__/.
Fixture and test paths are not dropped here; review_checks.sh tags their rows `[likely-fixture]` (its FXD/FXB patterns).
Binary files: a known binary extension is skipped; a NUL in the first 8 KB makes git show a file as binary, so a file with a
known text/source extension still reports its first control character and any other early-NUL file is skipped silently. UTF-16
(a BOM, or NULs on alternate bytes) is decoded and scanned, never reported as NULs. Symlinks and unreadable files are skipped.
Read-only; stdlib only. Also imported by scripts/audit_skills.py, so the rules live in one place.
"""
import os
import re
import sys
from itertools import islice

HIDDEN = re.compile(  # bidi, zero-width, soft hyphen, tag and variation-selector smuggling; ZWJ/ZWNJ/VS16 only beside ASCII (emoji, Persian ok)
    r"[\u061c\u180e\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\U000e0000-\U000e007f\U000e0100-\U000e01ef]|"
    r"(?<!^)\ufeff|(?<=[\x00-\x7f])(?:[\u200c\u200d\ufe00-\ufe0e]|\ufe0f(?!\u20e3))|[\u200c\u200d](?=[\x00-\x7f])")
CTRL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f]")  # C0 controls but tab, LF, CR, FF: invisible in editors; one NUL makes git show the file as binary and hide its diff
BINARY_EXT = frozenset(".png .jpg .jpeg .gif .ico .webp .bmp .tif .tiff .pdf .zip .gz .tgz .bz2 .xz .zst .7z .rar .jar .war .class .so .dylib .dll .exe .o .a .lib "
                       ".bin .wasm .woff .woff2 .ttf .otf .eot .mp3 .mp4 .mov .avi .webm .ogg .wav .flac .pyc .pyo .pyd .sqlite .sqlite3 .db .pkl .pickle .npy .npz .parquet".split())
CTRL_NOESC = re.compile(r"[\x00-\x08\x0b\x0e-\x1a\x1c-\x1f]")  # CTRL minus ESC (U+001B): terminal colour codes in snapshots and logs
OVERRIDE = re.compile("[\u202d\u202e\u2066-\u2069]")  # bidi overrides and isolates: the ones that reorder what a reviewer reads, the only hidden rows kept in locale files
FLAG = re.compile("\U0001f3f4[\U000e0020-\U000e007e]+\U000e007f")  # flag emoji (England, Scotland, Wales): black flag + tag letters + cancel tag
NULB = re.compile(b"\0")
TEXT_EXT = frozenset((".py .pyi .js .jsx .mjs .cjs .ts .tsx .vue .svelte .json .jsonc .yml .yaml .toml .ini .cfg .conf .env .md .mdx .rst .txt .csv .tsv .xml .svg .html .htm "
                      ".css .scss .sass .less .sh .bash .zsh .fish .ps1 .bat .cmd .rb .php .pl .lua .go .rs .java .kt .kts .scala .swift .c .h .cc .cpp .hpp .cs .dart .ex .exs "
                      ".erl .hs .clj .sql .graphql .gql .proto .tf .hcl .gradle .tex .po .arb .xlf .xliff .properties .snap .ansi .log").split())  # no .strings (binary plists) or .golden (binary goldens)
LOCALE_EXT = frozenset(".po .arb .xlf .xliff .properties .strings".split())
LOCALE_DIR = re.compile(r"(^|/)(locales?|i18n|l10n)/", re.I)
ESC_EXT = frozenset(".snap .golden .ansi .log".split())
MAX_CTRL = 20  # per rule and file; the rest is counted in one summary row, never dropped silently
MORE_CAP = 10000  # counting the rest stops here ("10000+ more")
MAX_READ = 2 << 20  # bytes read per file; the rest is reported as not scanned
MAX_ROWS = 200  # per run


def char_hits(text, rx, what):
    """[(line, message)]: the first MAX_CTRL matches of `rx` in `text` as `<what> U+XXXX at col N` (1-based; CRLF and CR count as one
    line break, so numbers match editors), then one `N more <what>s not listed` row (N counted up to MORE_CAP). Pure; no I/O."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    it = rx.finditer(text)  # lazy: a file of millions of matches never becomes a list
    rows = [(text.count("\n", 0, m.start()) + 1, "%s U+%04X at col %d" % (what, ord(m.group()), m.start() - text.rfind("\n", 0, m.start()))) for m in islice(it, MAX_CTRL)]
    rest = sum(1 for _ in islice(it, MORE_CAP))
    if rest:
        rows.append((rows[-1][0], "%d%s more %ss not listed" % (rest, "+" * (rest == MORE_CAP), what)))
    return rows


def unflag(text):
    """`text` with each flag emoji sequence masked by black flags of the same length, so HIDDEN skips its tag characters and columns hold. Pure."""
    return FLAG.sub(lambda m: "\U0001f3f4" * len(m.group()), text)


def hidden_hits(text, rx=HIDDEN):
    """char_hits for hidden characters outside flag emoji sequences. Pure; no I/O."""
    return char_hits(unflag(text), rx, "hidden character")


def decode(raw):
    """(text, binary) for one file's bytes. UTF-16 (a BOM, or NULs on alternate bytes only) decodes and is not binary. Otherwise utf-8
    (replace) and binary is git's own test, a NUL in the first 8 KB. Pure; no I/O."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") and raw[:4] != b"\xff\xfe\0\0":  # FF FE 00 00 is a UTF-32 BOM
        return raw.decode("utf-16", "replace"), False
    s = raw[:8192]
    even, odd = s[0::2].count(0), s[1::2].count(0)
    if even + odd >= 4 and (even + odd) * 4 >= len(s) and min(even, odd) * 10 <= even + odd:  # 4+ NULs, a quarter of the bytes, nearly all on one parity
        return raw.decode("utf-16-le" if odd > even else "utf-16-be", "replace"), False
    return raw.decode("utf-8", "replace"), bool(NULB.search(raw, 0, 8192))


def control_findings(rel, text, binary, rx=CTRL):
    """[(line, message)]: NUL/C0 control-character findings for one decoded file (see `decode`). A binary file lists only its first control
    character, and only under a known text/source extension; any other early-NUL file is skipped silently. No path leniency here.
    Pure; no I/O."""
    if binary and os.path.splitext(rel)[1].lower() not in TEXT_EXT:
        return []
    rows = char_hits(text, rx, "control character")
    return rows[:1] if binary else rows


def scan_file(rel, raw):
    """[(line, rule, message)] for one file's bytes: control-char rows, plus hidden-unicode rows unless the file is binary, with the path
    leniency in the module docstring (locale files, ESC in snapshots and logs). A known binary extension gives nothing. Pure; no I/O."""
    ext = os.path.splitext(rel)[1].lower()
    if ext in BINARY_EXT:
        return []
    text, binary = decode(raw)
    esc_ok = ext in ESC_EXT or "/__snapshots__/" in "/" + rel
    out = [(n, "control-char", m) for n, m in control_findings(rel, text, binary, CTRL_NOESC if esc_ok else CTRL)]
    if not binary:
        locale = ext in LOCALE_EXT or LOCALE_DIR.search(rel)
        out += [(n, "hidden-unicode", m) for n, m in hidden_hits(text, OVERRIDE if locale else HIDDEN)]
    return out


def main():
    """Read newline-separated paths from stdin, print TSV findings to stdout (flushed per row). Return 0 (findings are leads, not a failure). Read-only."""
    sent = 0
    for rel in sys.stdin.read().split("\n"):  # not splitlines(): it also splits on U+2028, U+0085, \x1c-\x1e, which a file name may hold
        if not rel:
            continue
        rows = [(0, "hidden-unicode", m.replace("hidden character", "hidden character in file name")) for _, m in hidden_hits(rel)[:1]]
        if not os.path.islink(rel):
            try:
                with open(rel, "rb") as fh:
                    raw = fh.read(MAX_READ + 1)
            except OSError:
                raw = b""
            if len(raw) > MAX_READ:
                raw = raw[:MAX_READ]
                rows.append((0, "not-checked", "partially scanned: file over %d MB, only the first %d MB were read" % (MAX_READ >> 20, MAX_READ >> 20)))
            rows += scan_file(rel, raw)
        for n, rule, msg in rows:
            if sent == MAX_ROWS:
                print("%s\t0\tnot-checked\toutput capped at %d rows; later findings and files were not scanned" % (rel, MAX_ROWS), flush=True)
                return 0
            print("%s\t%d\t%s\t%s" % (rel, n, rule, msg), flush=True)
            sent += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
