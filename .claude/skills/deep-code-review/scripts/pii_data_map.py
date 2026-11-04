#!/usr/bin/env python3
"""pii_data_map.py DIR -- heuristic lead-finder for personal data kept or sent in the clear (CWE-312/359/200). Report-only, stdlib only.

Usage: python3 -I pii_data_map.py DIR

Read this when you review a codebase that handles people's data: a national id committed as a literal, a national-id column with no encryption, or a raw email or phone sent to an analytics
host leaks to everyone with repo, database or vendor access. A row is a lead, never a finding, and SILENCE IS NOT PROOF: encryption, hashing or a vault may sit in a layer this scan cannot see.
Rows never hold a value. Rows are `file<TAB>line<TAB>rule<TAB>message`; stderr gets one summary line. Test paths are not scanned (route_auth_map.TEST). Source: JS/TS/Python, Go, Java, Kotlin.
- `plaintext-national-id`: a quoted SSN-shaped literal (ddd-dd-dddd) or a national-id-named key (ssn, national_id, social security, tax id, pesel) assigned a quoted digit string, in source code.
  An all-same-digit or sequential 123456789 placeholder is skipped. One row per run of consecutive lines.
- `unencrypted-national-id-column`: a Python model attribute named like a national id and set to an empty value or a Django/SQLAlchemy field, with no encrypt, hash, vault, tokenize or mask in its statement (a multi-line Column(...) included).
- `raw-pii-to-third-party`: a line (the whole statement: its open brackets up to 6 lines above and 4 below; a variable it uses and that one of the 3 lines above assigns from an email or phone counts too) that names an analytics, tracking or telemetry host (not localhost) and passes an email or phone with no hash, digest, redact or mask.
  Opaque refs (`vault://`, `cus_` ids) and hashed payloads do not match.

ponytail: code_of cuts at a `#` or `//` inside a string literal too (a URL keeps its `//`, a `#` in a string hides the rest of its line); statement text only, and its look-behind stops at a block-opening line (`) {`, `=> {`, a keyword line ending `{` or `:`, any line ending `:`), so a payload assigned inside a callback above is not tied to a call below it and a dict key alone on a line ending `:` ends the look-behind early. Also uncovered: a call whose own opening line ends in a function literal (`track(() => {`) loses its look-behind; the keyword alternative of the block opener cuts at data lines such as `{ for: {`, name-based; a column declared in another style (Prisma, SQL, JPA, GORM) or a payload built far from the call reads as clean. Upgrade to per-framework parsing if recall matters more.
"""
import os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stat  # noqa: E402
from attempt_limit_map import PRUNE, shown, walk  # noqa: E402
from header_config import MAX_BYTES  # noqa: E402
from route_auth_map import NOTSRC, TEST, read  # noqa: E402

L, R = r"(?:(?<![a-z])|(?=[A-Z]))", r"(?![a-z])"  # case-sensitive word edges: user_ssn, userEmail and userSSN match, myemail and emailed do not
ID = L + r"(?i:ssn|national_?id|nat_?id|social_?security(?:_?number)?|tax_?id|pesel)" + R
SSN = re.compile(r"""["'`]\s*(\d{3})-(\d{2})-(\d{4})\s*["'`]""")
KEYED = re.compile(r"""%s["'`]?\s*[:=]\s*["'`](\d[\d -]{6,})["'`]""" % ID)
COLUMN = re.compile(r"""^\s+%s\s*(?::\s*[\w.\[\]]+\s*)?=\s*(?:["']{2}|None\b|(?:models\.|db\.)?(?:\w*Field|Column|String)\()""" % ID)
SAFE = re.compile(r"encrypt|crypt|hash|vault|tokeni[sz]e|mask|redact|digest|hmac|sha\d|\bsha\w*\(|md5", re.I)
URL = re.compile(r"""https?://([\w.-]+)""")
TRACK = re.compile(r"analytics|tracking|tracker|telemetry|mixpanel|amplitude|hotjar|posthog|segment\.|pixel", re.I)
RAW = re.compile(L + r"(?i:email|phone)" + R)
ASSIGN = re.compile(r"^\s*(?:(?:const|let|var|val|final)\s+)?([A-Za-z_]\w*)\s*(?:,\s*\w+\s*)?(?::=|=)")


def placeholder(d):
    d = re.sub(r"\D", "", d)
    return len(set(d)) == 1 or d == "123456789"


def code_of(ln):
    """ln without a whole-line or trailing # or // comment."""
    return "" if re.match(r"\s*(?:#|//)", ln) else re.split(r"\s(?:#|//)", ln)[0]


OPENER = re.compile(r"(?:\)|=>)\s*\{\s*$|\b(?:if|for|while|else|try|catch|finally|switch|with|function|class|def)\b.*[{:]\s*$|:\s*$")


def statement(code, i):
    """Text of the statement that holds code[i]: from the line where its open brackets began (at most 6 lines up) to where they close (at most 4 lines down)."""
    depth = lambda t: sum(t.count(c) for c in "({[") - sum(t.count(c) for c in ")}]")
    up = lambda t: sum(t.count(c) for c in "([") - sum(t.count(c) for c in ")]")  # a block header's `{` does not count
    a, d = i, 0
    for k in range(i - 1, max(i - 7, -1), -1):  # the farthest line within 6 above where a parenthesis is still open is the call's opening line
        if OPENER.search(code[k]): break  # an enclosing block (callback, if, def) is not part of the statement
        d += up(code[k])
        if d > 0: a = k
    b, d = i, sum(depth(code[k]) for k in range(a, i + 1))
    while d > 0 and b + 1 < len(code) and b - i < 4:
        b += 1
        d += depth(code[b])
    return " ".join(code[a:b + 1])


def payload_above(code, i, stmt):
    """Lines among the 3 above code[i] that assign a variable the statement uses, when they name an email or phone."""
    out = []
    for k in range(max(i - 3, 0), i):
        m = ASSIGN.match(code[k])
        if m and RAW.search(code[k]) and re.search(r"\b%s\b" % re.escape(m.group(1)), stmt): out.append(code[k])
    return " ".join(out)


def sources(root):
    """Scanned paths: walk() (JS/TS/Python) plus Go, Java and Kotlin, regular files under MAX_BYTES, test paths left out."""
    files = walk(root)[0]
    # PRUNE minus `example`: com.example is a usual Java package, not sample code
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in PRUNE - {"example"}]
        for f in fn:
            r = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            try: st = os.lstat(os.path.join(dp, f))
            except OSError: continue
            if f.endswith((".go", ".java", ".kt")) and stat.S_ISREG(st.st_mode) and st.st_size <= MAX_BYTES and not NOTSRC.search(r): files.append(r)
    return files


def analyze(root):
    """(rows [(shown path, line, rule, message)], number of files scanned)."""
    rows, files = [], sources(root)
    for rel in files:
        t = read(root, rel)
        if t is None: continue
        code, py, last = [code_of(x) for x in t.split("\n")], rel.endswith(".py"), -9
        for i, ln in enumerate(code):
            k = KEYED.search(ln)
            if any(not placeholder("".join(m.groups())) for m in SSN.finditer(ln)) or (k and not placeholder(k.group(1))):
                if i - last > 1:
                    rows.append((shown(root, rel), i + 1, "plaintext-national-id", "committed literal holds a national id in plaintext (value not shown)"))
                last = i
            elif py and COLUMN.match(ln) and not SAFE.search(statement(code, i)):
                rows.append((shown(root, rel), i + 1, "unencrypted-national-id-column", "national-id attribute is a plain column with no encryption or hash"))
            elif any(TRACK.search(h) and not h.startswith(("localhost", "127.")) for h in URL.findall(ln)):
                c = statement(code, i)
                if not RAW.search(c): c += " " + payload_above(code, i, c)
                if RAW.search(c) and not SAFE.search(c):
                    rows.append((shown(root, rel), i + 1, "raw-pii-to-third-party", "raw email or phone is sent to a third-party analytics host (value not shown)"))
    return rows, len(files)


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: pii_data_map.py DIR", file=sys.stderr)
        return 2
    rows, n = analyze(argv[1])
    for r in rows: print("%s\t%d\t%s\t%s" % r)
    print("pii-data: %d files, %d leads; silence is not proof that personal data is protected" % (n, len(rows)) if n else "pii-data: no source file found", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
