"""header_config.py (static security-header lead-finder): rows for every evidence source over fictional fixtures, web-app detection, ignored
paths, size and encoding limits, the usage and exit-code contract, and the review_checks.sh --full wiring. Fixtures are fictional (acme,
example.com); one new file per feature, nothing appended to a shared spec."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # the in-process imports below must not leave a __pycache__ in the skill's scripts dir

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
SCRIPT = SK / "header_config.py"
RC = SK / "review_checks.sh"
sys.path.insert(0, str(SK))  # the in-process runs (mocked failures) and the mask check import the scripts directly
import dynamic_probe  # noqa: E402
import header_config  # noqa: E402
from tenant_scope_check import mask  # noqa: E402

CSP, XCTO, RP, XFO, HSTS = ("content-security-policy", "x-content-type-options", "referrer-policy", "x-frame-options", "strict-transport-security")
FOUND = "%s named here; value and use not checked"
MIDDLEWARE = "%s header middleware present; options not checked"
NOT_FOUND = "%s not found in repo config (hosting, CDN or proxy layers may set it; confirm with dynamic_probe.py on a running instance)"
SUMMARY = "header-config: web app found; %d not found in repo config; silence is not proof headers are served\n"
NO_WEB = "header-config: no supported web app found\n"
USAGE = "usage: header_config.py DIR\n"
WEB = {"package.json": '{"dependencies": {"express": "^4.0.0"}}\n'}  # one listed framework dependency makes a web app
BARE = [(".", 0, "header-not-found", NOT_FOUND % h) for h in (CSP, RP, XCTO, XFO)]  # a web app that names nothing, in output order
LISTED = ("next", "express", "fastify", "koa", "hono", "@nestjs/core", "nuxt", "@sveltejs/kit", "astro")

# One fixture per evidence source: the (file, header) pairs it must give, and nothing else.
SOURCES = {
    "next.config headers()": ({"next.config.js": '''module.exports = { async headers() { return [{ source: "/(.*)", headers: [{ key: "Content-Security-Policy", value: "default-src 'self'" }] }]; } };\n'''}, {("next.config.js", CSP)}),
    "setHeader with single quotes": ({"server.js": "res.setHeader('X-Content-Type-Options', 'nosniff');\n"}, {("server.js", XCTO)}),
    "template literal name": ({"src/app.ts": "res.set(`Referrer-Policy`, 'no-referrer');\n"}, {("src/app.ts", RP)}),
    "writeHead object": ({"srv.mjs": 'res.writeHead(200, { "Content-Type": "text/html", "X-Frame-Options": "DENY" });\n'}, {("srv.mjs", XFO)}),
    "array of name/value tuples": ({"lib/headers.cjs": 'const hdrs = [["Strict-Transport-Security", "max-age=31536000"], ["Referrer-Policy", "no-referrer"]];\n'},
                                   {("lib/headers.cjs", HSTS), ("lib/headers.cjs", RP)}),
    "name in upper case": ({"web/mw.tsx": 'headers.set("X-FRAME-OPTIONS", "DENY");\n'}, {("web/mw.tsx", XFO)}),
    "vercel.json": ({"vercel.json": '{"headers": [{"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"}, {"key": "Referrer-Policy", "value": "no-referrer"}]}]}\n'},
                    {("vercel.json", XCTO), ("vercel.json", RP)}),
    "netlify.toml table": ({"netlify.toml": '[[headers]]\n  for = "/*"\n  [headers.values]\n    X-Frame-Options = "DENY"\n'}, {("netlify.toml", XFO)}),
    "netlify.toml inline table": ({"netlify.toml": '[[headers]]\n  for = "/*"\n  values = { Referrer-Policy = "no-referrer", "X-Content-Type-Options" = "nosniff" }\n'},
                                  {("netlify.toml", RP), ("netlify.toml", XCTO)}),
    "_headers file": ({"public/_headers": "/*\n  Content-Security-Policy: default-src 'self'\n  x-frame-options: DENY\n"}, {("public/_headers", CSP), ("public/_headers", XFO)}),
    "nginx add_header": ({"deploy/nginx.conf": 'server {\n  add_header X-Frame-Options "DENY" always;\n  add_header "Referrer-Policy" no-referrer;\n}\n'},
                         {("deploy/nginx.conf", XFO), ("deploy/nginx.conf", RP)}),
}

SERVER = "\n".join([
    '/* notes',  # 1
    '   "X-Frame-Options" is not set here */',  # 2
    '// "Referrer-Policy"',  # 3
    'const app = require("express")();',  # 4
    'app.use((req, res, next) => {',  # 5
    '  res.setHeader("X-Content-Type-Options", "nosniff");',  # 6
    '  res.setHeader("x-content-type-options", "nosniff");',  # 7
    '  next();',  # 8
    '});',  # 9
    '', '',  # 10, 11
    'app.use((req, res) => res.set("Strict-Transport-Security", "max-age=1"));',  # 12
    ''])
GOLD = {**WEB, "server.js": SERVER, "public/_headers": "# acme edge headers\n/*\n  Content-Security-Policy: default-src 'self'; frame-ancestors 'none'\n"}
GOLD_ROWS = [
    (".", 0, "header-not-found", NOT_FOUND % RP),  # x-frame-options is covered by the frame-ancestors in the CSP file
    ("public/_headers", 3, "header-found", FOUND % CSP),
    ("server.js", 6, "header-found", FOUND % XCTO),  # named again on line 7: one row, at the first line
    ("server.js", 12, "header-found", FOUND % HSTS),  # line 12 sorts after line 6 as a number, not as text
]

MIDDLEWARES = {
    'const helmet = require("helmet");': "helmet",
    "import helmet from 'helmet';": "helmet",
    'import { helmet } from "helmet";': "helmet",
    'const helmet = await import("helmet");': "helmet",
    "const helmet = require('koa-helmet');": "koa-helmet",
    'import helmet from "@fastify/helmet";': "@fastify/helmet",
}
NOT_MIDDLEWARE = (
    '// const helmet = require("helmet");',
    '/* import helmet from "helmet"; */',
    'const name = "helmet";',
    'const h = require("not-helmet");',
    'const h = require("helmet-csp");',
    'const hint = "import helmet from \'helmet\'";',  # the whole import is text inside a string
    "const hint = 'const helmet = require(\"helmet\")';",
    "const hint = `import helmet from 'helmet'`;",
    'import type { HelmetOptions } from "helmet";',  # a type-only import is erased at build time
    "import type helmet from 'helmet';",
    'import type * as H from "helmet";',
    'import type {\n  HelmetOptions,\n} from "helmet";',
)

# Reads and removals do not show that a header is set: each source alone leaves every header not found.
READS = {
    ".get": 'const v = res.headers.get("Content-Security-Policy");\n',
    ".has": 'if (headers.has("X-Frame-Options")) warn();\n',
    ".delete": 'headers.delete("Referrer-Policy");\n',
    "getHeader": 'const v = res.getHeader("X-Content-Type-Options");\n',
    "hasHeader": "if (res.hasHeader('X-Frame-Options')) warn();\n",
    "removeHeader": "res.removeHeader(`Content-Security-Policy`);\n",
    "multi-line .get": 'const v = headers.get(\n  "Content-Security-Policy"\n);\n',
    "spaces around the name": 'const v = headers.get( "Referrer-Policy" );\n',
    "optional chain": 'const v = ctx?.headers?.get("Referrer-Policy");\n',
    "subscript read": 'const v = res.headers["x-frame-options"];\n',
    "subscript with spaces": 'const v = res.headers[ "x-frame-options" ];\n',
    "subscript compared with ===": 'if (h["x-content-type-options"] === "nosniff") ok();\n',
    "subscript compared with ==": 'if (h["x-content-type-options"] == "nosniff") ok();\n',
    "subscript compared with !==": 'if (h["x-content-type-options"] !== "nosniff") bad();\n',
    "subscript compared with !=": 'if (h["x-content-type-options"] != "nosniff") bad();\n',
    "subscript removed": 'delete headers["x-frame-options"];\n',
    "one-name list (ponytail limit: reads as a subscript)": 'const required = ["x-frame-options"];\n',
}
# Other mentions still count, at their line: source -> the headers it gives header-found rows for.
SETS = {
    "subscript assignment": ('headers["x-frame-options"] = "DENY";\n', (XFO,)),
    "subscript assignment without spaces": ('headers["x-frame-options"]="DENY";\n', (XFO,)),
    "subscript ??=": ('headers["referrer-policy"] ??= "no-referrer";\n', (RP,)),
    ".set": ('headers.set("Referrer-Policy", "no-referrer");\n', (RP,)),
    ".append": ('headers.append("X-Content-Type-Options", "nosniff");\n', (XCTO,)),
    "setHeader": ('res.setHeader("X-Frame-Options", "DENY");\n', (XFO,)),
    "two-argument header()": ('res.header("Content-Security-Policy", "default-src \'self\'");\n', (CSP,)),
    "one-argument header()": ('const v = res.header("Content-Security-Policy");\n', (CSP,)),
    "comparison": ('if (name === "x-frame-options") skip();\n', (XFO,)),
    "list of names": ('const required = ["content-security-policy", "referrer-policy"];\n', (CSP, RP)),
    "name as the second argument of .get": ('const v = cache.get(key, "Referrer-Policy");\n', (RP,)),
    "object key": ('res.writeHead(200, { "X-Content-Type-Options": "nosniff" });\n', (XCTO,)),
}

# Ignored below DIR: build or vendor output and test or documentation trees.
IGNORED_DIRS = ("node_modules", ".git", "dist", "build", ".next", "vendor", ".venv", "__pycache__", "coverage", "out", "venv", ".vercel", ".netlify",
                ".nuxt", ".output", ".svelte-kit", ".turbo", ".cache", "test", "tests", "__tests__", "e2e", "spec", "specs", "fixture", "fixtures", "doc", "docs", "example", "examples", "__mocks__")
IGNORED_FILES = ("src/app.test.js", "src/app.spec.ts", "public/app.min.js", "src/tests/deep/a.js")
EVIDENCE = 'import helmet from "helmet";\nres.set({ "Content-Security-Policy": "x", "X-Content-Type-Options": "x", "Referrer-Policy": "x", "X-Frame-Options": "x" });\n'

FRAME = {  # files -> the headers still not found (in output order)
    "JS: frame-ancestors in the CSP file": ({"app.js": '''res.setHeader("Content-Security-Policy", "frame-ancestors 'none'");\n'''}, (RP, XCTO)),
    "JS: frame-ancestors only in another file": ({"a.js": '''res.setHeader("Content-Security-Policy", "default-src 'self'");\n''', "b.js": '''const policy = "frame-ancestors 'self'";\n'''}, (RP, XCTO, XFO)),
    "JS: frame-ancestors in a second CSP file": ({"a.js": '''res.setHeader("Content-Security-Policy", "default-src 'self'");\n''', "b.js": '''res.setHeader("Content-Security-Policy", "frame-ancestors 'none'");\n'''}, (RP, XCTO)),
    "JS: frame-ancestors only in a comment": ({"a.js": '''// frame-ancestors 'none'\nres.setHeader("Content-Security-Policy", "default-src 'self'");\n'''}, (RP, XCTO, XFO)),
    "_headers: frame-ancestors on a # line": ({"_headers": "# frame-ancestors 'none'\n/*\n  Content-Security-Policy: default-src 'self'\n"}, (RP, XCTO, XFO)),
    "_headers: frame-ancestors on the CSP line": ({"_headers": "/*\n  Content-Security-Policy: frame-ancestors 'none'\n"}, (RP, XCTO)),
    "vercel.json": ({"vercel.json": '''{"headers": [{"source": "/(.*)", "headers": [{"key": "Content-Security-Policy", "value": "frame-ancestors 'none'"}]}]}\n'''}, (RP, XCTO)),
    "netlify.toml": ({"netlify.toml": '[[headers]]\n  for = "/*"\n  [headers.values]\n    Content-Security-Policy = "frame-ancestors \'none\'"\n'}, (RP, XCTO)),
    "nginx": ({"nginx.conf": '''server {\n  add_header Content-Security-Policy "frame-ancestors 'none'" always;\n}\n'''}, (RP, XCTO)),
    "x-frame-options named, no frame-ancestors": ({"a.js": '''res.setHeader("Content-Security-Policy", "default-src 'self'");\nres.setHeader("X-Frame-Options", "DENY");\n'''}, (RP, XCTO)),
    "Report-Only is not a CSP, so its frame-ancestors does not count": ({"_headers": "/*\n  Content-Security-Policy-Report-Only: frame-ancestors 'none'\n"}, (CSP, RP, XCTO, XFO)),
    "URL before frame-ancestors in one string": ({"app.js": '''res.setHeader("Content-Security-Policy", "default-src 'self' https://cdn.example.com; frame-ancestors 'none'");\n'''}, (RP, XCTO)),
    "URL before frame-ancestors in a template literal": ({"app.ts": '''const csp = `default-src 'self' https://cdn.example.com; frame-ancestors 'none'`;\nres.set(`Content-Security-Policy`, csp);\n'''}, (RP, XCTO)),
}

DETECT = [("%s in dependencies" % d, {"package.json": json.dumps({"dependencies": {d: "1"}})}, True) for d in LISTED] + [
    ("framework in devDependencies", {"package.json": json.dumps({"devDependencies": {"astro": "1"}})}, True),
    ("package.json in a subdirectory", {"apps/web/package.json": json.dumps({"dependencies": {"next": "1"}})}, True),
    ("package.json with a BOM", {"package.json": b"\xef\xbb\xbf" + json.dumps({"dependencies": {"express": "1"}}).encode()}, True),
    ("valid devDependencies beside a list for dependencies", {"package.json": json.dumps({"dependencies": ["express"], "devDependencies": {"koa": "1"}})}, True),
    ("vercel.json alone", {"vercel.json": "{}"}, True),
    ("netlify.toml alone", {"netlify.toml": ""}, True),
    ("_headers alone", {"_headers": ""}, True),
    ("conf with a server block", {"nginx.conf": "server {\n  listen 80;\n}\n"}, True),
    ("conf with server{ and no space", {"a.conf": "server{}\n"}, True),
    ("conf with add_header only", {"snippet.conf": "add_header X-Acme 1;\n"}, True),
    ("unlisted frameworks", {"package.json": json.dumps({"dependencies": {"react": "1", "commander": "1"}})}, False),
    ("dependencies is a list", {"package.json": json.dumps({"dependencies": ["express"]})}, False),
    ("dependencies is a string", {"package.json": json.dumps({"dependencies": "express"})}, False),
    ("dependencies is null", {"package.json": json.dumps({"dependencies": None})}, False),
    ("package.json is a list", {"package.json": '["express"]'}, False),
    ("package.json is a string", {"package.json": '"express"'}, False),
    ("invalid package.json", {"package.json": '{"dependencies": {"express": '}, False),
    ("conf without server or add_header", {"app.conf": "[core]\nname = acme\n"}, False),
    ("server block in a non-conf file", {"nginx.txt": "server {\n}\n"}, False),
    ("python framework", {"requirements.txt": "flask\n", "app.py": "from flask import Flask\n"}, False),
    ("plain node:http server", {"package.json": "{}", "server.js": 'require("http").createServer((q, s) => { s.setHeader("Content-Security-Policy", "x"); s.end(); });\n'}, False),
    ("command-line tool naming a header", {"package.json": json.dumps({"dependencies": {"commander": "1"}}), "bin/cli.js": 'console.log("Content-Security-Policy");\n'}, False),
    ("static html with no config", {"index.html": '''<meta http-equiv="Content-Security-Policy" content="default-src 'self'">\n''', "site.css": "a{}\n"}, False),
]


def write(root, files):
    """Write {relative path: str or bytes} under root, creating directories."""
    for rel, data in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def run(*argv):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, argv)], capture_output=True, encoding="utf-8", errors="replace")


def deny(real, target):
    """Wrap an open- or scandir-like callable: PermissionError for the one `target` path, the real call for every other path."""
    def wrapper(path, *a, **k):
        if path == target:
            raise PermissionError(13, "Permission denied", path)
        return real(path, *a, **k)
    return wrapper


def parse(stdout):
    """TSV rows [(file, line, rule, message)] of the script's stdout."""
    rows = []
    for line in stdout.splitlines():
        f = line.split("\t")
        assert len(f) == 4, line
        rows.append((f[0], int(f[1]), f[2], f[3]))
    return rows


def pairs(rows, rule):
    """{(file, first word of the message)} for the rows of one rule: the header, or the package for a middleware row."""
    return {(r[0], r[3].split()[0]) for r in rows if r[2] == rule}


class HeaderConfig(unittest.TestCase):
    def scan(self, files, under=None, prep=None):
        """Write files into a fresh directory, run the script on it, return (rows, stderr).
        `under` puts the directory below a parent of that name; `prep(dir)` runs before the scan."""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t, under, "app") if under else Path(t)
            write(d, files)
            if prep:
                prep(d)
            r = run(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        return parse(r.stdout), r.stderr

    def call(self, files, denied_file=None, denied_dir=None):
        """Run header_config.main in this process on a fresh fixture, with open or os.scandir raising PermissionError for one path (a mock, so it also
        fails for root). denied_* is a path below the fixture, "." for the fixture itself. Return (exit code, rows, stderr)."""
        with tempfile.TemporaryDirectory() as t:
            write(t, files)
            at = lambda rel: None if rel is None else (t if rel == "." else os.path.join(t, rel))  # noqa: E731
            out, err = io.StringIO(), io.StringIO()
            with mock.patch("builtins.open", deny(open, at(denied_file))), mock.patch("os.scandir", deny(os.scandir, at(denied_dir))), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = header_config.main([t])
        return rc, parse(out.getvalue()), err.getvalue()

    def missing(self, files):
        return [r[3].split()[0] for r in self.scan(files)[0] if r[2] == "header-not-found"]

    def test_golden_rows(self):
        rows, err = self.scan(GOLD)
        self.assertEqual(rows, GOLD_ROWS)
        self.assertEqual(err, SUMMARY % 1)

    def test_every_evidence_source(self):
        for name, (files, want) in SOURCES.items():
            with self.subTest(name):
                rows, _ = self.scan({**WEB, **files})
                self.assertEqual(pairs(rows, "header-found"), want)
                self.assertEqual(pairs(rows, "header-middleware"), set())

    def test_exact_not_found_message(self):
        rows, err = self.scan(WEB)
        self.assertEqual(rows, BARE)
        self.assertEqual(rows[0][3], "content-security-policy not found in repo config (hosting, CDN or proxy layers may set it; confirm with dynamic_probe.py on a running instance)")
        self.assertEqual(err, SUMMARY % 4)

    def test_middleware_forms_and_no_not_found_rows(self):
        for src, pkg in MIDDLEWARES.items():
            with self.subTest(src):
                rows, err = self.scan({**WEB, "app.js": src + "\n"})
                self.assertEqual(rows, [("app.js", 1, "header-middleware", MIDDLEWARE % pkg)])
                self.assertEqual(err, SUMMARY % 0)

    def test_middleware_beside_a_found_header(self):
        rows, _ = self.scan({**WEB, "app.js": 'import helmet from "helmet";\nres.setHeader("X-Frame-Options", "DENY");\n'})
        self.assertEqual(rows, [("app.js", 1, "header-middleware", MIDDLEWARE % "helmet"), ("app.js", 2, "header-found", FOUND % XFO)])

    def test_text_that_is_not_a_middleware_import(self):
        for src in NOT_MIDDLEWARE:
            with self.subTest(src):
                self.assertEqual(self.scan({**WEB, "app.js": src + "\n"})[0], BARE)

    def test_js_comments_do_not_count(self):
        src = '// res.setHeader("Content-Security-Policy", "x");\n/* res.setHeader("X-Frame-Options", "DENY");\n   res.setHeader("Referrer-Policy", "no-referrer"); */\n// import helmet from "helmet";\n'
        self.assertEqual(self.scan({**WEB, "app.js": src})[0], BARE)

    def test_commented_lines_in_config_files_do_not_count(self):
        files = {
            "netlify.toml": '# X-Frame-Options = "DENY"\n#   values = { Referrer-Policy = "no-referrer" }\n[headers.values]\n  X-Content-Type-Options = "nosniff" # kept\n',
            "public/_headers": "# X-Frame-Options: DENY\n  # Referrer-Policy: no-referrer\n/*\n  Content-Security-Policy: default-src 'self'\n",
            "nginx.conf": 'server {\n  # add_header X-Frame-Options DENY;\n    #add_header Referrer-Policy no-referrer;\n  add_header Strict-Transport-Security "max-age=1" always;\n}\n',
        }
        rows, _ = self.scan(files)
        self.assertEqual(pairs(rows, "header-found"), {("netlify.toml", XCTO), ("public/_headers", CSP), ("nginx.conf", HSTS)})

    def test_report_only_headers_are_not_counted(self):
        files = {
            **WEB,
            "app.js": 'res.setHeader("Content-Security-Policy-Report-Only", "x");\n',
            "vercel.json": '{"headers": [{"key": "Content-Security-Policy-Report-Only", "value": "x"}]}\n',
            "netlify.toml": 'Content-Security-Policy-Report-Only = "x"\n',
            "_headers": "/*\n  Content-Security-Policy-Report-Only: x\n",
            "nginx.conf": 'server {\n  add_header Content-Security-Policy-Report-Only "x";\n}\n',
        }
        self.assertEqual(self.scan(files)[0], BARE)

    def test_frame_ancestors_and_x_frame_options(self):
        for name, (files, want) in FRAME.items():
            with self.subTest(name):
                self.assertEqual(self.missing({**WEB, **files}), list(want))

    def test_hsts_is_never_not_found(self):
        self.assertNotIn(HSTS, self.missing(WEB))
        rows, _ = self.scan({**WEB, "app.js": 'res.setHeader("Strict-Transport-Security", "max-age=1");\n'})
        self.assertEqual(pairs(rows, "header-found"), {("app.js", HSTS)})
        self.assertEqual([r[3].split()[0] for r in rows if r[2] == "header-not-found"], [CSP, RP, XCTO, XFO])

    def test_ignored_paths_give_no_evidence(self):
        files = {"%s/a.js" % d: EVIDENCE for d in IGNORED_DIRS}
        files.update({f: EVIDENCE for f in IGNORED_FILES})
        files.update({"docs/_headers": "X-Frame-Options: DENY\n", "examples/vercel.json": '{"key": "Referrer-Policy"}\n', "tests/nginx.conf": "server {\n  add_header X-Frame-Options DENY;\n}\n",
                      "spec/netlify.toml": 'X-Frame-Options = "DENY"\n'})
        self.assertEqual(self.scan({**WEB, **files})[0], BARE)

    def test_ignored_paths_do_not_make_a_web_app(self):
        files = {"examples/app/package.json": WEB["package.json"], "docs/vercel.json": "{}", "tests/netlify.toml": "", "spec/_headers": "", "fixtures/site.conf": "server {}\n",
                 "src/app.test.js": EVIDENCE, "node_modules/express/package.json": WEB["package.json"]}
        self.assertEqual(self.scan(files), ([], NO_WEB))

    def test_near_miss_names_are_scanned(self):
        files = {**WEB, "src/testing/a.js": 'x("X-Frame-Options")\n', "src/app.minimal.js": 'x("Referrer-Policy")\n', "src/latest/b.js": 'x("X-Content-Type-Options")\n',
                 "src/docs-site/c.js": 'x("Content-Security-Policy")\n'}
        rows, _ = self.scan(files)
        self.assertEqual(pairs(rows, "header-found"), {("src/testing/a.js", XFO), ("src/app.minimal.js", RP), ("src/latest/b.js", XCTO), ("src/docs-site/c.js", CSP)})

    def test_web_app_detection(self):
        for name, files, web in DETECT:
            with self.subTest(name):
                rows, err = self.scan(files)
                if web:
                    self.assertTrue(err.startswith("header-config: web app found;"), err)
                else:
                    self.assertEqual((rows, err), ([], NO_WEB))

    def test_config_file_is_a_web_app_even_when_unread(self):
        rows, _ = self.scan({"vercel.json": b'{"a": "' + b"x" * 1_000_001 + b'"}'})
        self.assertEqual(rows, BARE + [("vercel.json", 0, "not-checked", "file over 1 MB not read")])

    def test_file_over_1_mb_is_reported_not_read(self):
        head = b'res.setHeader("Referrer-Policy", "x");\n'
        rows, err = self.scan({**WEB, "src/big.js": head + b"a" * (1_000_001 - len(head))})
        self.assertEqual(rows, BARE + [("src/big.js", 0, "not-checked", "file over 1 MB not read")])
        self.assertEqual(err, SUMMARY % 4)

    def test_file_of_exactly_1_mb_is_read(self):
        head = b"X-Frame-Options: DENY\n"
        rows, _ = self.scan({**WEB, "public/_headers": head + b"#" * (1_000_000 - len(head))})
        self.assertEqual(pairs(rows, "header-found"), {("public/_headers", XFO)})
        self.assertEqual([r for r in rows if r[2] == "not-checked"], [])

    def test_unreadable_file_is_reported_without_a_root_dependency(self):
        rc, rows, err = self.call({**WEB, "src/locked.js": 'x("Referrer-Policy")\n', "src/ok.js": 'x("X-Frame-Options")\n'}, denied_file="src/locked.js")
        self.assertEqual(rc, 0)
        self.assertEqual(rows, BARE[:3] + [("src/locked.js", 0, "not-checked", "file not readable"), ("src/ok.js", 1, "header-found", FOUND % XFO)])
        self.assertEqual(err, SUMMARY % 3)  # only the denied path failed: the rest of the tree was still read

    def test_unlistable_directory_is_reported(self):
        files = {**WEB, "src/private/_headers": "X-Frame-Options: DENY\n", "src/ok.js": 'x("Referrer-Policy")\n'}
        rc, rows, err = self.call(files, denied_dir="src/private")
        self.assertEqual(rc, 0)
        self.assertEqual(rows, [r for r in BARE if r[3].split()[0] != RP] + [("src/ok.js", 1, "header-found", FOUND % RP), ("src/private", 0, "not-checked", "directory not listable")])
        self.assertEqual(err, SUMMARY % 3)

    def test_unread_detection_input_is_not_reported_as_no_web_app(self):
        big = b"x" * 1_000_001
        unreadable, over = "file not readable", "file over 1 MB not read"
        cases = {  # name: (files, denied file, denied dir, the not-checked rows that must be printed)
            "package.json over 1 MB": ({"package.json": b'{"a": "' + big + b'"}'}, None, None, [("package.json", over)]),
            "package.json not readable": ({"package.json": WEB["package.json"]}, "package.json", None, [("package.json", unreadable)]),
            "package.json below DIR not readable": ({"apps/web/package.json": WEB["package.json"]}, "apps/web/package.json", None, [("apps/web/package.json", unreadable)]),
            ".conf over 1 MB": ({"deploy/nginx.conf": b"#" * 1_000_001}, None, None, [("deploy/nginx.conf", over)]),
            ".conf not readable": ({"deploy/nginx.conf": "server {}\n"}, "deploy/nginx.conf", None, [("deploy/nginx.conf", unreadable)]),
            "directory not listable": ({"src/private/package.json": WEB["package.json"]}, None, "src/private", [("src/private", "directory not listable")]),
            "DIR itself not listable": ({}, None, ".", [(".", "directory not listable")]),
            "two paths": ({"package.json": "{}", "src/private/x.js": "x"}, "package.json", "src/private", [("package.json", unreadable), ("src/private", "directory not listable")]),
            "detection input beside an unrelated unread file": ({"package.json": b'{"a": "' + big + b'"}', "src/big.js": big}, None, None, [("package.json", over)]),
        }
        for name, (files, denied_file, denied_dir, want) in cases.items():
            with self.subTest(name):
                rc, rows, err = self.call(files, denied_file, denied_dir)
                self.assertEqual((rc, rows), (0, [(f, 0, "not-checked", why) for f, why in want]))
                self.assertEqual(err, "header-config: web app detection incomplete; %d path(s) not read\n" % len(want))

    def test_unread_input_that_cannot_make_a_web_app_keeps_the_no_web_summary(self):
        big = b"x" * 1_000_001
        for name, files, denied in (("JS file over 1 MB", {"src/big.js": big}, None), ("JS file not readable", {"src/a.js": "x"}, "src/a.js"),
                                    ("vendor-style file not readable", {"app.test.js": "x", "README.md": "x"}, "app.test.js")):
            with self.subTest(name):
                self.assertEqual(self.call(files, denied)[1:], ([], NO_WEB))

    def test_unread_config_file_or_directory_beside_a_web_app(self):
        rc, rows, err = self.call({"vercel.json": "{}"}, denied_file="vercel.json")
        self.assertEqual((rc, rows, err), (0, BARE + [("vercel.json", 0, "not-checked", "file not readable")], SUMMARY % 4))

    def test_deeply_nested_package_json_is_no_crash_and_no_web_app(self):
        for src in ("[" * 100000 + "]" * 100000, '{"a":' * 100000 + "1" + "}" * 100000):
            self.assertEqual(self.scan({"package.json": src}), ([], NO_WEB))

    def test_json_recursion_error_is_not_a_crash_on_any_interpreter(self):
        """Newer interpreters parse 100000 nested arrays, so force the RecursionError an older one raises."""
        with mock.patch.object(header_config.json, "loads", side_effect=RecursionError):
            self.assertEqual(self.call({"package.json": "{}"}), (0, [], NO_WEB))

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "root reads any file")
    def test_unreadable_file_is_reported(self):
        rows, _ = self.scan({**WEB, "src/locked.js": 'x("Referrer-Policy")\n'}, prep=lambda d: os.chmod(d / "src/locked.js", 0))
        self.assertEqual(rows, BARE + [("src/locked.js", 0, "not-checked", "file not readable")])

    def test_nested_checkouts_are_not_scanned(self):
        helmet = 'import helmet from "helmet";\nres.setHeader("X-Frame-Options", "DENY");\n'
        for name, files in {
            "worktree (.git file)": {"wt/.git": "gitdir: ../.git/worktrees/wt\n", "wt/app.js": helmet},
            "clone or submodule (.git directory)": {"libs/sub/.git/HEAD": "ref: refs/heads/main\n", "libs/sub/app.js": helmet},
            "worktree below .claude": {".claude/worktrees/feat/.git": "gitdir: x\n", ".claude/worktrees/feat/src/app.js": helmet},
        }.items():
            with self.subTest(name):
                self.assertEqual(self.scan({**WEB, **files})[0], BARE)
        nested_app = {"wt/.git": "gitdir: x\n", "wt/package.json": WEB["package.json"], "wt/vercel.json": "{}", "wt/nginx.conf": "server {}\n"}
        self.assertEqual(self.scan(nested_app), ([], NO_WEB))  # the nested checkout is not a web app of this one

    def test_dir_that_holds_a_git_entry_is_still_scanned(self):
        for make in (lambda d: (d / ".git").mkdir(), lambda d: (d / ".git").write_text("gitdir: x\n", encoding="utf-8")):
            self.assertEqual(self.scan(GOLD, prep=make)[0], GOLD_ROWS)

    def test_middleware_text_in_a_string_does_not_hide_the_leads(self):
        src = 'const hint = "import helmet from \'helmet\'";\nres.setHeader("Content-Security-Policy", "default-src \'self\'");\n'
        rows, err = self.scan({**WEB, "app.js": src})
        self.assertEqual(rows, [r for r in BARE if r[3].split()[0] != CSP] + [("app.js", 2, "header-found", FOUND % CSP)])
        self.assertEqual(err, SUMMARY % 3)

    def test_a_real_import_is_found_at_its_own_line_beside_text_and_type_imports(self):
        for name, src in {
            "after a string": 'const hint = "import helmet from \'helmet\'";\nimport helmet from "helmet";\n',
            "after an import type of another package": 'import type { Request } from "express";\nconst helmet = require("helmet");\n',
            "export from after an import type": 'import type { Request } from "express";\nexport { default } from "helmet";\n',
            "after an import type of helmet": 'import type { A } from "helmet";\nimport helmet from "helmet";\n',
        }.items():
            with self.subTest(name):
                self.assertEqual(self.scan({**WEB, "app.js": src})[0], [("app.js", 2, "header-middleware", MIDDLEWARE % "helmet")])

    def test_both_masks_keep_every_offset(self):
        s = 'import x from "y"; // it\'s "c"\n/* "block"\n   c */ const a = `t ${1} \\` end`; const b = \'it\\\'s\';\n'
        self.assertEqual(len(mask(s, keep=True)), len(s))
        self.assertEqual(len(mask(s, keep=False)), len(s))
        self.assertEqual([i for i, c in enumerate(mask(s, keep=False)) if c == "\n"], [i for i, c in enumerate(s) if c == "\n"])

    def test_reads_and_removals_are_not_evidence_that_a_header_is_set(self):
        for name, src in READS.items():
            with self.subTest(name):
                self.assertEqual(self.scan({**WEB, "app.js": src})[0], BARE)

    def test_other_mentions_still_count_at_their_line(self):
        for name, (src, headers) in SETS.items():
            with self.subTest(name):
                rows, _ = self.scan({**WEB, "app.js": src})
                self.assertEqual(sorted((r[1], r[3]) for r in rows if r[2] == "header-found"), sorted((1, FOUND % h) for h in headers))

    def test_a_read_before_a_set_gives_the_sets_line(self):
        for name, src, line, header in (
                ("get, compare, then set", 'const v = headers.get("X-Frame-Options");\nif (headers["x-frame-options"] === "SAMEORIGIN") warn();\nheaders.set("X-Frame-Options", "DENY");\n', 3, XFO),
                ("getHeader, removeHeader, then a subscript assignment", 'const v = res.getHeader("Referrer-Policy");\nres.removeHeader("Referrer-Policy");\nres.headers["referrer-policy"] = "no-referrer";\n', 3, RP),
                ("read and set on one line", 'headers.get("X-Content-Type-Options") || headers.set("X-Content-Type-Options", "nosniff");\n', 1, XCTO)):
            with self.subTest(name):
                rows, _ = self.scan({**WEB, "app.js": src})
                self.assertEqual([r for r in rows if r[2] == "header-found"], [("app.js", line, "header-found", FOUND % header)])
                self.assertNotIn(NOT_FOUND % header, [r[3] for r in rows])

    def test_a_csp_read_does_not_hide_the_x_frame_options_lead(self):
        src = 'const v = res.headers.get("Content-Security-Policy");\nconst embed = "frame-ancestors *";\n'
        self.assertEqual(self.missing({**WEB, "app.js": src}), [CSP, RP, XCTO, XFO])

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as out:
            write(out, {"h.js": 'x("X-Frame-Options")\n', "sub/g.js": 'x("Referrer-Policy")\n', "package.json": WEB["package.json"]})

            def link(d):
                os.symlink(Path(out) / "h.js", d / "link.js")
                os.symlink(Path(out) / "sub", d / "linkdir")

            self.assertEqual(self.scan(WEB, prep=link)[0], BARE)
            self.assertEqual(self.scan({"index.html": "x"}, prep=lambda d: os.symlink(Path(out) / "package.json", d / "package.json")), ([], NO_WEB))

    def test_bad_bytes_do_not_drop_a_file(self):
        files = {**WEB, "a.js": b'const s = "\xff\xfe";\nres.setHeader("X-Frame-Options", "DENY"); // caf\xe9\n', "_headers": b"/*\n  Referrer-Policy: \xff\n"}
        self.assertEqual(pairs(self.scan(files)[0], "header-found"), {("a.js", XFO), ("_headers", RP)})

    def test_bom_in_a_headers_file(self):
        rows, _ = self.scan({"_headers": b"\xef\xbb\xbfX-Frame-Options: DENY\n"})
        self.assertEqual(pairs(rows, "header-found"), {("_headers", XFO)})
        self.assertEqual([r[1] for r in rows if r[2] == "header-found"], [1])

    def test_control_character_in_a_path_cannot_break_the_row(self):
        rows, _ = self.scan({**WEB, "we\tird.js": 'x("X-Frame-Options")\n'})
        self.assertEqual(pairs(rows, "header-found"), {("we?ird.js", XFO)})

    def test_no_rows_without_a_web_app(self):
        for files in ({"package.json": json.dumps({"dependencies": {"commander": "1"}}), "bin/cli.js": 'console.log("Content-Security-Policy");\n'},
                      {"index.html": "<p>hello</p>\n"}):
            self.assertEqual(self.scan(files), ([], NO_WEB))

    def test_dir_below_a_parent_named_test_or_fixtures_is_still_scanned(self):
        want = self.scan(GOLD)
        self.assertEqual(want[0], GOLD_ROWS)
        for parent in ("test", "fixtures", "docs", "node_modules"):
            with self.subTest(parent):
                self.assertEqual(self.scan(GOLD, under=parent), want)

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "a_file"
            f.write_text("x", encoding="utf-8")
            for argv in ([], [t, t], ["--bogus", t], [Path(t) / "missing"], [f]):
                with self.subTest(argv=argv):
                    r = run(*argv)
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", USAGE))

    def test_repeat_run_and_another_location_give_identical_output(self):
        first = self.scan(GOLD)
        self.assertEqual(self.scan(GOLD), first)
        self.assertEqual(self.scan(GOLD, under="elsewhere"), first)

    def test_one_header_list(self):
        self.assertIs(header_config.SECURITY_HEADERS, dynamic_probe.SECURITY_HEADERS)
        self.assertEqual(dynamic_probe.SECURITY_HEADERS, (CSP, XCTO, RP))

    def test_writes_nothing_beside_the_script_or_in_the_target(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as d:
            for n in ("header_config.py", "dynamic_probe.py", "tenant_scope_check.py"):
                shutil.copy(SK / n, t)
            write(d, GOLD)
            before = sorted(str(p.relative_to(d)) for p in Path(d).rglob("*"))
            r = subprocess.run([sys.executable, "-I", str(Path(t) / "header_config.py"), d], capture_output=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, run(d).stdout)
            self.assertEqual(sorted(os.listdir(t)), ["dynamic_probe.py", "header_config.py", "tenant_scope_check.py"])
            self.assertEqual(sorted(str(p.relative_to(d)) for p in Path(d).rglob("*")), before)

    def test_review_checks_full_wiring(self):
        env = dict(os.environ, PATH="/usr/bin:/bin", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, files):
                g = Path(t) / name
                write(g, files)
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            web = {**WEB, "server.js": 'res.setHeader("X-Content-Type-Options", "nosniff");\n', "src/big.js": b"a" * 1_000_001}
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("web", web))], capture_output=True, text=True, env=env)
            rows = [x for x in json.loads(r.stdout) if x["tool"] == "header-config"]
            want = {(".", 0, "header-not-found", NOT_FOUND % h) for h in (CSP, RP, XFO)} | {("src/big.js", 0, "not-checked", "file over 1 MB not read")}
            self.assertEqual({(x["file"], x["line"], x["rule"], x["message"]) for x in rows}, want)  # the found row for x-content-type-options stays out
            self.assertEqual(len(rows), len(want))
            self.assertIn(SUMMARY % 3, r.stderr)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("plain", {"a.ts": "export const a = 1;\n"}))], capture_output=True, text=True, env=env)
            self.assertIn("header-config (SKIPPED: no supported web app)", r.stderr)
            self.assertEqual([(x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "header-config"], [("not-checked", "SKIPPED: no supported web app")])
            blind = repo("blind", {"package.json": b'{"a": "' + b"x" * 1_000_001 + b'"}'})  # the only web-app signal is unread: not-checked, never SKIPPED
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(blind)], capture_output=True, text=True, env=env)
            self.assertIn("header-config: web app detection incomplete; 1 path(s) not read", r.stderr)
            self.assertNotIn("header-config (SKIPPED", r.stderr)
            self.assertEqual([(x["file"], x["line"], x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "header-config"],
                             [("package.json", 0, "not-checked", "file over 1 MB not read")])


if __name__ == "__main__":
    unittest.main()
