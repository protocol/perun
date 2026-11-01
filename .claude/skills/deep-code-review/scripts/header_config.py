#!/usr/bin/env python3
"""header_config.py DIR -- heuristic lead-finder for security response headers that a web app's repo config never names. Report-only, stdlib only.

Usage: python3 -I header_config.py DIR

A web app is found when DIR holds a package.json that depends on next, express, fastify, koa, hono, @nestjs/core, nuxt, @sveltejs/kit or astro,
any vercel.json, netlify.toml or _headers file, or a .conf file with `server {` or `add_header`. With none of these the script prints no rows and
"header-config: no supported web app found" on stderr, unless a package.json, a .conf file or a directory could not be read: the unread input may be the
web app, so it prints those not-checked rows and "header-config: web app detection incomplete; N path(s) not read" (N = those rows) instead.
Otherwise it looks, case-insensitively, for content-security-policy, x-content-type-options, referrer-policy, x-frame-options and strict-transport-security
in JS/TS files (a quoted name in code, comments ignored), vercel.json, netlify.toml, _headers and nginx .conf files. In JS/TS a quoted name that is only
read or removed does not count: the first argument of .get(, .has(, .delete(, .getHeader(, .hasHeader( or .removeHeader(, or a subscript key such as
headers["x-frame-options"] with no assignment after it. Other mentions still count: an object key, .set(, .append(, setHeader(, a one- or two-argument
header() call, a comparison, a list of two or more names.
Not read: symlinks; node_modules, .git, dist, build, .next, coverage, vendor, .venv, __pycache__, out, venv, .vercel, .netlify, .nuxt, .output, .svelte-kit,
.turbo and .cache directories; a subdirectory with its own .git entry (a nested checkout, worktree or submodule: scan it on its own); directories named
test, tests, __tests__, e2e, spec, specs, fixture, fixtures, doc, docs, example, examples or __mocks__ (judged on the path below DIR, so a checkout under a
parent named tests is still scanned); files named *.test.*, *.spec.* or *.min.*.

Rows: TSV on stdout, `file<TAB>line<TAB>rule<TAB>message`, paths relative to DIR with `/`, sorted by file, line, rule, message.
- header-found: one per (file, header) at its first line; the header is named there, its value and use are not checked.
- header-middleware: a JS/TS import or require of helmet, @fastify/helmet or koa-helmet (not inside a string or comment, not `import type`); its options are
  not checked, and an unused or dead import still counts. While one is present no header-not-found row is printed, because what a library sets by default
  is not encoded here.
- header-not-found: file `.`, line 0, one per header no file names: content-security-policy, x-content-type-options, referrer-policy and
  x-frame-options (not when a file naming content-security-policy also has frame-ancestors anywhere in it). Never for strict-transport-security. A lead, not a
  finding: a host, CDN or proxy may set the header, so confirm with dynamic_probe.py on a running instance.
- not-checked: a candidate file over 1 MB (1,000,000 bytes) is not read, a file cannot be read, or a directory cannot be listed (file `.` for DIR itself).
stderr: one summary line, "header-config: web app found; N not found in repo config; silence is not proof headers are served", the detection-incomplete line
or the no-web-app line.
Exit 0; 2 with "usage: header_config.py DIR" on stderr for no argument, extra arguments or a DIR that is not a directory. Reads files only; writes nothing.

ponytail: per-repository scope (one configured app in a monorepo hides another); other header plugins, computed header names and out-of-repo layers are
not seen; values are not checked; a comparison or a list of names still counts as naming a header, while a one-name list such as ["x-frame-options"]
reads as a subscript; an unused or dead helmet import still hides every lead; frame-ancestors anywhere in a file that names content-security-policy hides
the x-frame-options lead (file-level, not per string); nested checkouts and submodules are not read; Python frameworks are not covered; plain node:http
servers without a listed framework are not detected; Apache .htaccess, nginx more_set_headers and other proxy configs are not read; `mask` does not parse
regex literals. Upgrade to a config parser per host if precision matters more.
"""
import json, os, re, stat, sys

sys.dont_write_bytecode = True  # `python3 -I` drops this dir from sys.path: add it for the sibling imports and leave no __pycache__ behind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dynamic_probe import SECURITY_HEADERS  # noqa: E402
from tenant_scope_check import SKIP_DIR, lineno, mask  # noqa: E402

TRACKED = SECURITY_HEADERS + ("x-frame-options", "strict-transport-security")
PRUNE = SKIP_DIR | {"out", "venv", ".vercel", ".netlify", ".nuxt", ".output", ".svelte-kit", ".turbo", ".cache"} | {  # directory names skipped below DIR (never DIR itself or its parents)
    "test", "tests", "__tests__", "e2e", "spec", "specs", "fixture", "fixtures", "doc", "docs", "example", "examples", "__mocks__"}
SKIP_FILE = (".test.", ".spec.", ".min.")
JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")  # next.config.* is covered by these
CONFIG_FILES = ("vercel.json", "netlify.toml", "_headers")  # their presence alone makes a web app
WEB_DEPS = {"next", "express", "fastify", "koa", "hono", "@nestjs/core", "nuxt", "@sveltejs/kit", "astro"}  # ponytail: fixed list, add a name when a framework is missed
MAX_BYTES = 1_000_000  # ponytail: a candidate over this is reported, not read; raise it if a real config needs more
NOT_FOUND = "%s not found in repo config (hosting, CDN or proxy layers may set it; confirm with dynamic_probe.py on a running instance)"

SP = r"[^\S\n]"  # whitespace that is not a newline: keeps the per-line rules on their line
NAME = r"(?P<h>%s)" % "|".join(re.escape(n) for n in TRACKED)
QUOTED = re.compile(r"""["'`]%s["'`]""" % NAME, re.I)  # the closing quote is required: Content-Security-Policy-Report-Only is another header
TOML = re.compile(r"""(^|[{,])\s*["']?%s["']?\s*=""" % NAME, re.I | re.M)  # a [headers.values] key or an inline-table key
LINES = re.compile(r"^%s*%s%s*:" % (SP, NAME, SP), re.I | re.M)  # a _headers line
NGINX = re.compile(r"""^%s*add_header%s+["']?%s["']?%s""" % (SP, SP, NAME, SP), re.I | re.M)
MIDDLEWARE = re.compile(r"""(?:require\(\s*|from\s+|import\s+|import\(\s*)["'](?P<h>helmet|@fastify/helmet|koa-helmet)["']""", re.I)
TYPE_IMPORT = re.compile(r"\bimport\s+type\b[\w\s{},*$]*?(?=\bfrom\b)")  # ends where the `from` of an `import type` statement starts: a type-only import is erased at build time
READ_CALL = re.compile(r"\.\s*(?:get|has|delete|getHeader|hasHeader|removeHeader)\s*\(\s*\Z")  # tried on the 40 characters before a quoted name
SUBSCRIPT = re.compile(r"\[\s*\Z")  # same window
SUBSCRIPT_END = re.compile(r"\s*\](?!\s*[-+*/%&|^?]*=(?![=>]))")  # `]` with no assignment after it: ==, ===, != and !== are comparisons
COMMENT = re.compile(r"^[ \t]*#.*", re.M)
WEB_CONF = re.compile(r"server\s*\{|add_header")


def first_lines(rx, text, skip=None):
    """{lowercase name: first line} for the `h` group of every match of rx in text, leaving out a match for which skip(text, match) is true."""
    out = {}
    for m in rx.finditer(text):
        h = m.group("h").lower()
        if h not in out and not (skip and skip(text, m)):
            out[h] = lineno(text, m.start("h"))
    return out


def is_read(text, m):
    """True when the quoted name at match m is only read or removed, which does not show the header is set: the first argument of a read call, or a subscript key with no assignment after it."""
    k = m.start()
    return bool(READ_CALL.search(text, max(0, k - 40), k) or (SUBSCRIPT.search(text, max(0, k - 40), k) and SUBSCRIPT_END.match(text, m.end())))


def helmet_imports(raw, text):
    """{helmet package: first line} for the imports in text that are code. text is raw masked with strings kept; in the twin with string contents blanked
    (same offsets) a keyword inside a string is a blank, and an `import type` statement leaves nothing at run time."""
    code = mask(raw, keep=False)
    typed = {m.end() for m in TYPE_IMPORT.finditer(code)}
    return first_lines(MIDDLEWARE, text, lambda t, m: code[m.start()] != t[m.start()] or m.start() in typed)


def is_web(name, text):
    """True when a package.json depends on a listed framework or a .conf file has `server {` or `add_header`."""
    if name == "package.json":
        try:
            pkg = json.loads(text)
        except (ValueError, RecursionError):
            return False
        return isinstance(pkg, dict) and any(isinstance(pkg.get(k), dict) and WEB_DEPS & set(pkg[k]) for k in ("dependencies", "devDependencies"))
    return name.endswith(".conf") and bool(WEB_CONF.search(text))


def scan(name, text):
    """(first line per tracked header, first line per helmet package, frame-ancestors beside a content-security-policy) for one candidate file."""
    mw, skip = {}, None
    if name.endswith(JS_EXT):
        low = text.lower()
        if not any(k in low for k in TRACKED + ("helmet", "frame-ancestors")):
            return {}, mw, False  # mask is a slow pure-Python loop and a file without these substrings cannot match
        raw, text = text, mask(text, keep=True)  # ponytail: mask does not parse regex literals, so a quote inside one can blank or keep the wrong text
        rx, skip = QUOTED, is_read
        if "helmet" in low:
            mw = helmet_imports(raw, text)
    else:
        if name == "netlify.toml":
            text = COMMENT.sub("", text)  # blank full-line comments, keep the line count
        rx = {"vercel.json": QUOTED, "netlify.toml": TOML, "_headers": LINES}.get(name, NGINX)
    hits = first_lines(rx, text, skip)
    fa = "content-security-policy" in hits and any("frame-ancestors" in ln.lower() and not ln.lstrip().startswith("#") for ln in text.split("\n"))
    return hits, mw, fa


def relpath(p, root):
    """p below root with `/`; a control character or an undecodable byte becomes `?` so a name cannot break the TSV row or the print."""
    return re.sub(r"[\x00-\x1f\x7f\ud800-\udfff]", "?", os.path.relpath(p, root).replace(os.sep, "/"))


def main(argv):
    """Scan argv[0], print the rows and the stderr summary; return 0, or 2 on a usage error."""
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        print("usage: header_config.py DIR", file=sys.stderr)
        return 2
    root, web, framed, middleware, seen, rows, blind = argv[0], False, False, False, set(), [], []

    def unread(rel, why, detects):
        """Add a not-checked row; detects marks an input that could have made DIR a web app (a package.json, a .conf file, a directory)."""
        rows.append((rel, 0, "not-checked", why))
        if detects:
            blind.append(rows[-1])

    for dp, dn, fn in os.walk(root, onerror=lambda e: unread(relpath(e.filename, root), "directory not listable", True)):
        dn[:] = [d for d in dn if d not in PRUNE and not os.path.lexists(os.path.join(dp, d, ".git"))]  # a subdirectory with a .git entry is another checkout: scan it on its own
        for f in fn:
            if not (f.endswith(JS_EXT + (".conf",)) or f == "package.json" or f in CONFIG_FILES) or any(s in f for s in SKIP_FILE):
                continue
            p, why = os.path.join(dp, f), None
            try:
                st = os.lstat(p)
                if not stat.S_ISREG(st.st_mode):
                    continue  # a symlink, pipe or socket
                web = web or f in CONFIG_FILES
                if st.st_size > MAX_BYTES:
                    why = "file over 1 MB not read"
                else:
                    with open(p, encoding="utf-8-sig", errors="replace") as fh:
                        text = fh.read()
            except OSError:
                why = "file not readable"
            if why:
                unread(relpath(p, root), why, f == "package.json" or f.endswith(".conf"))
                continue
            web = web or is_web(f, text)
            hits, mw, fa = scan(f, text)
            seen.update(hits)
            framed, middleware = framed or fa, middleware or bool(mw)
            rel = relpath(p, root)
            rows += [(rel, n, "header-found", "%s named here; value and use not checked" % h) for h, n in hits.items()]
            rows += [(rel, n, "header-middleware", "%s header middleware present; options not checked" % h) for h, n in mw.items()]
    if web:
        want = () if middleware else SECURITY_HEADERS + (() if framed else ("x-frame-options",))
        missing = [h for h in want if h not in seen]
        rows += [(".", 0, "header-not-found", NOT_FOUND % h) for h in missing]
        note = "web app found; %d not found in repo config; silence is not proof headers are served" % len(missing)
    elif blind:
        rows, note = blind, "web app detection incomplete; %d path(s) not read" % len(blind)
    else:
        rows, note = [], "no supported web app found"
    for r in sorted(rows):
        print("%s\t%d\t%s\t%s" % r)
    print("header-config: " + note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
