#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.parser-code-engine and perun.js.express4-async-throw (js.yml), and for the
Express 4 gate review_checks.sh applies to the second rule's rows.

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` comment marks the NEXT line as a required finding, an
`// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too (so must a
copy of each fixture under a test path). PARSER_HELD_OUT uses a library (yaml-front-matter) that none of the other parser fixtures
use. All names and values are fictional. RULES=<dir> checks another copy of the rules. The live check needs semgrep and prints
SKIP without it; the gate check stubs semgrep and runs review_checks.sh on a throwaway repo; the offline checks always run.
Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, ".claude", "skills", "deep-code-review")
RULES = os.environ.get("RULES") or os.path.join(SK, "templates", "semgrep-taint")
PARSER, EXPRESS4 = "perun.js.parser-code-engine", "perun.js.express4-async-throw"
IDS = (PARSER, EXPRESS4)

PARSER_LIB = r'''import matter from "gray-matter";
import fs from "node:fs";
import path from "node:path";

export function parseNote(text: string) {
  // ruleid: perun.js.parser-code-engine
  return matter(text).data;
}
export function parseExcerpt(text: string) {
  // ruleid: perun.js.parser-code-engine
  return matter(text, { excerpt: true });
}
export function parseNoteSafely(text: string) {
  const deny = () => { throw new Error("script front matter is not accepted"); };
  // ok: perun.js.parser-code-engine
  return matter(text, { engines: { js: deny, javascript: deny } }).data;
}
export function parseNoteJsOff(text: string) {
  const deny = () => { throw new Error("script front matter is not accepted"); };
  // ok: perun.js.parser-code-engine
  return matter(text, { engines: { javascript: deny } }).data;
}
export function parseNoteToml(text: string, parseToml: (s: string) => object) {
  // gray-matter merges options.engines over its defaults, so the javascript engine is still there.
  // ruleid: perun.js.parser-code-engine
  return matter(text, { engines: { toml: parseToml } }).data;
}
export function readPost(slug: string) {
  const raw = fs.readFileSync(path.join("content", `${slug}.md`), "utf8");
  // ok: perun.js.parser-code-engine
  return matter(raw);
}
export function readUploaded(file: { path: string }) {
  const raw = fs.readFileSync(file.path, "utf8");
  // ruleid: perun.js.parser-code-engine
  return matter(raw);
}
// ok: perun.js.parser-code-engine
export const banner = matter("---\ntitle: Acme notes\n---\n");
'''

PARSER_SERVER = r'''const express = require("express");
const matter = require("gray-matter");
const yaml = require("js-yaml");
const fm = require("front-matter");
const app = express();
app.use(express.text());

app.post("/notes/preview", (req, res) => {
  // ruleid: perun.js.parser-code-engine
  const { data } = matter(req.body);
  res.json(data);
});
app.post("/config/import", (req, res) => {
  // ruleid: perun.js.parser-code-engine
  const cfg = yaml.safeLoad(req.body, { schema: yaml.DEFAULT_FULL_SCHEMA });
  // ok: perun.js.parser-code-engine
  const plain = yaml.safeLoad(req.body, { schema: yaml.FAILSAFE_SCHEMA });
  // perun.js.deserialize-untrusted owns yaml.load, so this rule stays silent on it (checked below).
  // ok: perun.js.parser-code-engine
  const full = yaml.load(req.body, { schema: yaml.DEFAULT_FULL_SCHEMA });
  res.json({ cfg, plain, full });
});
app.post("/pages/import", (req, res) => {
  // ruleid: perun.js.parser-code-engine
  const page = fm(req.body, { allowUnsafe: true });
  // ok: perun.js.parser-code-engine
  const safe = fm(req.body);
  res.json({ page, safe });
});
'''

# Held out: a Next route handler parsing an uploaded file with yaml-front-matter, a library no other fixture here uses.
PARSER_HELD_OUT = r'''import yamlFront from "yaml-front-matter";

export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get("page") as File;
  const body = await file.text();
  // ruleid: perun.js.parser-code-engine
  const page = yamlFront.loadFront(body);
  // ok: perun.js.parser-code-engine
  const safe = yamlFront.safeLoadFront(body);
  return Response.json({ title: page.title, safe: safe.title });
}
'''

EXPRESS_APP = r'''const express = require("express");
const asyncHandler = require("express-async-handler");
const router = express.Router();

function readSessionId(req) {
  const pair = (req.headers.cookie || "").split("; ").find((p) => p.startsWith("acme_sid="));
  // ruleid: perun.js.express4-async-throw
  return pair ? decodeURIComponent(pair.slice(9)) : null;
}
function readLocale(req) {
  try {
    // ok: perun.js.express4-async-throw
    return decodeURIComponent(req.headers["x-locale"] || "en");
  } catch {
    return "en";
  }
}
function readTheme(req) {
  // ok: perun.js.express4-async-throw
  return JSON.parse(req.cookies.theme || "{}");
}
async function currentAccount(req) {
  const sid = readSessionId(req);
  return sid ? sessions.get(sid) : null;
}
async function currentLocale(req) {
  return readLocale(req);
}
async function themeFor(req) {
  try {
    return readTheme(req);
  } catch (e) {
    return {};
  }
}
const withTenant = async (req, res, next) => {
  // ruleid: perun.js.express4-async-throw
  req.tenant = decodeURIComponent(req.params.tenant);
  next();
};
router.get("/reports", async (req, res) => {
  // ruleid: perun.js.express4-async-throw
  const filter = JSON.parse(req.query.filter || "{}");
  res.json(await reports.find(filter));
});
router.post("/hooks", async function (req, res) {
  // ruleid: perun.js.express4-async-throw
  const target = new URL(req.body.callback);
  res.json({ host: target.host });
});
router.get("/search", async (req, res) => {
  try {
    // ok: perun.js.express4-async-throw
    const q = JSON.parse(req.query.q);
    res.json(await search(q));
  } catch (e) {
    res.status(400).json({ error: "bad query" });
  }
});
router.get("/sync", (req, res) => {
  // ok: perun.js.express4-async-throw
  res.json(JSON.parse(req.query.v || "{}"));
});
router.get("/wrapped", asyncHandler(async (req, res) => {
  // ok: perun.js.express4-async-throw
  const u = new URL(req.query.u);
  res.json({ host: u.host });
}));
router.get("/cached", async (req, res) => {
  // ok: perun.js.express4-async-throw
  const row = JSON.parse(await cache.get("acme:summary"));
  res.json(row);
});
module.exports = { router, withTenant, currentAccount, currentLocale, themeFor };
'''

EXPRESS_TS = r'''import type { Request, Response } from "express";

export async function loadPrefs(req: Request) {
  // ruleid: perun.js.express4-async-throw
  return JSON.parse(req.cookies.prefs ?? "{}");
}
export const profile = async (req: Request, res: Response) => {
  // ruleid: perun.js.express4-async-throw
  const back = new URL(req.get("referer") ?? "");
  res.json({ back: back.pathname, prefs: await loadPrefs(req) });
};
'''

# The helper is declared after the async middleware that calls it; a sync-only file and a Koa handler stay clean.
EXPRESS_ORDER = r'''export async function requireClaims(req, res, next) {
  req.claims = claimsFrom(req);
  next();
}
function claimsFrom(req) {
  const raw = (req.headers.authorization || "").replace(/^Bearer /, "");
  // ruleid: perun.js.express4-async-throw
  return JSON.parse(Buffer.from(raw.split(".")[1] || "", "base64url").toString());
}
function pageFrom(req) {
  // ok: perun.js.express4-async-throw
  return JSON.parse(req.query.page || "1");
}
function list(req, res) {
  res.json({ page: pageFrom(req) });
}
'''

# Regression: hop 2 once ran metavariable-pattern on every statement near a helper, and semgrep 1.183.0 failed the whole file
# ("Invalid_argument: String.sub / Bytes.sub") on a TypeScript `(x as T).y = ...` statement. Helpers on both sides of the
# handlers, a call from a route callback and from an assigned arrow, and a helper only ever called inside try.
EXPRESS_CAST = r'''import type { Request, Response } from "express";
import { Router } from "express";
export const router = Router();
const out = document.getElementById("acme-out")!;

export function paint(q: string) {
  out.innerText = decodeURIComponent(q);
  (out as HTMLInputElement).value = `acme ${q}`;
}
function readFilter(req: Request) {
  // ruleid: perun.js.express4-async-throw
  return JSON.parse(String(req.query.filter ?? "{}"));
}
function readSort(req: Request) {
  // ok: perun.js.express4-async-throw
  return JSON.parse(String(req.query.sort ?? "[]"));
}
router.get("/items", async (req: Request, res: Response) => {
  (res as Response).json({ filter: readFilter(req), label: `acme ${req.path}` });
});
export const exportItems = async (req: Request, res: Response) => {
  res.json({ next: readCursor(req) });
};
router.get("/sorted", async (req: Request, res: Response) => {
  try {
    res.json(readSort(req));
  } catch (e) {
    res.status(400).end();
  }
});
function readCursor(req: Request) {
  // ruleid: perun.js.express4-async-throw
  return decodeURIComponent(String(req.query.cursor ?? ""));
}
'''

# Next.js route handlers (app router GET/POST exports) run inside Next, which turns a throw into a 500: clean. Pages API routes
# are skipped by path (see SKIPPED).
NEXT_ROUTE = r'''function readTag(request: Request) {
  // ok: perun.js.express4-async-throw
  return decodeURIComponent(request.headers.get("x-acme-tag") ?? "");
}
export async function GET(request: Request) {
  // ok: perun.js.express4-async-throw
  const u = new URL(request.url);
  return Response.json({ q: u.searchParams.get("q"), tag: readTag(request) });
}
export const POST = async (request: Request) => {
  // ok: perun.js.express4-async-throw
  const back = new URL(request.headers.get("referer") ?? "");
  return Response.json({ back: back.pathname });
};
'''

KOA = r'''const Router = require("@koa/router");
const router = new Router();
router.get("/k", async (ctx) => {
  // ok: perun.js.express4-async-throw
  ctx.body = JSON.parse(ctx.query.v);
});
'''

FILES = {"lib/notes.ts": PARSER_LIB, "server/notes.js": PARSER_SERVER, "app/api/import/route.ts": PARSER_HELD_OUT,
         "server/app.js": EXPRESS_APP, "server/member.ts": EXPRESS_TS, "server/order.mjs": EXPRESS_ORDER, "server/koa.js": KOA,
         "server/cast.ts": EXPRESS_CAST, "app/api/acme/route.ts": NEXT_ROUTE}
# Test, fixture and mock paths are excluded from both rules, scripts and *.config.* from the parser rule, Next pages API routes
# (pages/api) from the Express rule: nothing here may be reported.
SKIPPED = {"tests/notes.test.ts": PARSER_LIB, "__mocks__/notes.js": PARSER_SERVER, "scripts/import-pages.ts": PARSER_HELD_OUT,
           "site.config.ts": PARSER_LIB, "tests/app.test.js": EXPRESS_APP, "server/member.spec.ts": EXPRESS_TS,
           "pages/api/acme.js": EXPRESS_APP, "src/pages/api/member.ts": EXPRESS_TS}
ANN = re.compile(r"^\s*//\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= set(IDS), out
    return out


# Offline: at least 3 findings and 3 near misses per rule, and the held-out library fixture has both kinds.
for rid in IDS:
    for kind in ("ruleid", "ok"):
        n = sum(1 for body in FILES.values() for _, r in annotated(body, kind) if r == rid)
        assert n >= 3, (rid, kind, n)
assert annotated(PARSER_HELD_OUT, "ruleid") and annotated(PARSER_HELD_OUT, "ok")
assert "yaml-front-matter" not in PARSER_LIB + PARSER_SERVER, "the held-out library is used only by the held-out fixture"

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)) or d, exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES, *SKIPPED],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got, other = set(), set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.<lang>.<name> tail
    for x in r["results"]:
        rid = "perun." + x["check_id"].rsplit("perun.", 1)[-1]
        (got if rid in IDS else other).add((x["path"], x["start"]["line"], rid))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    ln = PARSER_SERVER.split("\n").index("  const full = yaml.load(req.body, { schema: yaml.DEFAULT_FULL_SCHEMA });") + 1
    assert ("server/notes.js", ln, "perun.js.deserialize-untrusted") in other, "the yaml.load the parser rule leaves alone is still reported"
elif os.environ.get("REQUIRE_SEMGREP") == "1":
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not on PATH")
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the gate and offline checks below do")

# Gate: review_checks.sh keeps an express4-async-throw row only under a package.json that pins express 4 without
# express-async-errors, express-promise-router or @awaitjs/express (nearest manifest naming express wins). A stub semgrep returns one row per case; the manifests sit in the
# base commit, so no dependency check reads them. The parser rule's rows are never filtered.
CASES = {"e4": {"dependencies": {"express": "^4.19.2"}}, "e4dev": {"devDependencies": {"express": "~4.18.0"}},
         "e4alias": {"dependencies": {"express": "npm:express@4.21.0"}}, "e5": {"dependencies": {"express": "^5.1.0"}},
         "e14": {"dependencies": {"express": "14.0.0"}}, "latest": {"dependencies": {"express": "latest"}},
         "e4wrap": {"dependencies": {"express": "4.21.0", "express-async-errors": "^3.1.1"}},
         "e4promise": {"dependencies": {"express": "^4.21.0", "express-promise-router": "^4.1.1"}},
         "e4await": {"dependencies": {"express": "4.21.0"}, "devDependencies": {"@awaitjs/express": "^0.9.0"}}, "none": {"dependencies": {"koa": "^2.15.0"}},
         "mono/packages/api": {"name": "acme-api"}, "mono": {"dependencies": {"express": "4.17.3"}}, "bad": "{not json"}
KEEP = {"e4", "e4dev", "e4alias", "mono", "mono/packages/api"}
with tempfile.TemporaryDirectory() as t:
    repo, sb = os.path.join(t, "repo"), os.path.join(t, "bin")
    os.makedirs(sb)
    res = []
    for c, j in CASES.items():
        os.makedirs(os.path.join(repo, c, "src"), exist_ok=True)
        open(os.path.join(repo, c, "package.json"), "w").write(j if isinstance(j, str) else json.dumps(j))
        res.append({"check_id": EXPRESS4, "path": f"{c}/src/app.js", "start": {"line": 1}, "extra": {"message": f"crash {c}", "severity": "WARNING"}})
    res.append({"check_id": PARSER, "path": "e5/src/app.js", "start": {"line": 1}, "extra": {"message": "engine", "severity": "ERROR"}})
    open(os.path.join(sb, "semgrep"), "w").write("#!/bin/sh\ncat <<'J'\n" + json.dumps({"results": res, "errors": []}) + "\nJ\n")
    os.chmod(os.path.join(sb, "semgrep"), 0o755)
    g = lambda *a: subprocess.run(["git", "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *a], cwd=repo, check=True, capture_output=True)
    g("init", "-q", "."); g("add", "."); g("commit", "-q", "-m", "base"); g("branch", "base")
    for c in CASES:
        open(os.path.join(repo, c, "src", "app.js"), "w").write("module.exports = {};\n")
    g("add", "."); g("commit", "-q", "-m", "app")
    heavy = os.path.join(t, "notadir")
    open(heavy, "w").close()
    env = dict(os.environ, PATH=sb + os.pathsep + os.environ["PATH"], HOME=t, PERUN_HEAVY_DIR=heavy, REVIEW_SEMGREP_REGISTRY="0")
    for k in ("REVIEW_OSV", "REVIEW_OSV_DB_DIR"):
        env.pop(k, None)
    p = subprocess.run(["bash", os.path.join(SK, "scripts", "review_checks.sh"), "--base", "base"], cwd=repo, env=env, capture_output=True, text=True)
    out = json.loads(p.stdout)
    seen = {}  # rows of one rule fold into the first file plus an "also: a, b" hint
    for row in out:
        if row.get("rule") in IDS:
            for f in [row["file"]] + [x for x in (row.get("hint") or "").removeprefix("also: ").split(", ") if x]:
                seen.setdefault(row["rule"], set()).add(f)
    assert seen.get(EXPRESS4) == {f"{c}/src/app.js" for c in KEEP}, (sorted(seen.get(EXPRESS4, ())), p.stderr[-800:])
    # The gate itself on an absolute path spelled through a symlink to the repo (macOS /tmp is /private/tmp): still Express 4.
    src = open(os.path.join(SK, "scripts", "review_checks.sh")).read()
    ns = {"os": os, "json": json, "re": re}
    exec("\n".join(l[4:] for l in re.search(r"\n(    def ex4\(f\):\n(?:        .*\n)+)", src).group(1).split("\n")), ns)
    os.symlink(repo, os.path.join(t, "link"))
    here = os.getcwd()
    os.chdir(os.path.join(t, "link"))
    try:
        assert ns["ex4"](os.path.join(t, "link", "e4", "src", "app.js")) and not ns["ex4"](os.path.join(t, "link", "e5", "src", "app.js"))
    finally:
        os.chdir(here)
    assert seen.get(PARSER) == {"e5/src/app.js"}, seen

# Offline: ids, severities, CWE metadata, the test-path exclusions shared with the other bundled rules, and the regexes that
# carry the precision (semgrep anchors metavariable-regex at the start, as re.match does).
JS = open(os.path.join(RULES, "js.yml")).read()
block = lambda rid: JS.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
excl = lambda b: json.loads((re.search(r"paths:\n\s+exclude: (\[.*\])", b) or [0, "[]"])[1])
base = excl(block("perun.js.hardcoded-credential-compare"))
pb, eb = block(PARSER), block(EXPRESS4)
for rid, b, sev, cwe in ((PARSER, pb, "ERROR", "CWE-94"), (EXPRESS4, eb, "WARNING", "CWE-248")):
    assert JS.count(f"- id: {rid}\n") == 1 and f"  severity: {sev}\n" in b and f'"{cwe}: ' in b, rid
    assert base and set(base) <= set(excl(b)), f"{rid} skips the shared test paths"
assert set(excl(pb)) - set(base) == {"scripts", "*.config.*"} and set(excl(eb)) - set(base) == {"pages/api"}
rx = lambda b, mv: re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", b)
(fsa,) = rx(pb, "A")
assert all(re.match(fsa, s) for s in ('path.join("content", slug)', "file", "postsDir + name")), fsa
assert not any(re.match(fsa, s) for s in ("file.path", "upload.filepath", "req.files.page.tempFilePath")), fsa
assert pb.count('"gray-matter"') == 3 and pb.count("pattern-not: '$M($S, {...,") == 2, "gray-matter binding forms and the engines/parsers override"
(ld,) = rx(pb, "LOAD")
(sch,) = rx(pb, "SCH")
assert all(re.match(ld, s) for s in ("load", "loadAll", "safeLoad", "safeLoadAll")) and not any(re.match(ld, s) for s in ("loadFront", "dump", "loader")), ld
assert all(re.match(sch, s) for s in ("yaml.DEFAULT_FULL_SCHEMA", "FULL_SCHEMA", "jsTypes")) and not any(re.match(sch, s) for s in ("yaml.FAILSAFE_SCHEMA", "CORE_SCHEMA", "DEFAULT_SCHEMA")), sch
fns = rx(eb, "FN")
assert len(fns) == 2 and len(set(fns)) == 1, "one async-function regex, shared by the call-argument and assignment forms"
assert all(re.match(fns[0], s) for s in ("async (req, res) => {}", "async function (req, res) {}", "async function h(request) {}", "async req => 1", "async (_req, res) => {}"))
assert not any(re.match(fns[0], s) for s in ("(req, res) => {}", "asyncHandler(async (req, res) => {})", "async (ctx) => {}", "function (req) {}")), fns
(meth,) = rx(eb, "METH")
assert all(re.match(meth, s) for s in ("get", "post", "use", "all", "del")) and not any(re.match(meth, s) for s in ("send", "json", "getx", "listen")), meth
# Hop 2 matches the calling handler with sequence patterns only: metavariable-pattern there made semgrep fail whole TypeScript files.
assert "metavariable-pattern" not in eb and eb.count("pattern-not-inside: try { ... } catch") == 2 and eb.count("try { ... <... $H(...) ...>; ... } catch ($E)") == 3, "hop 1 skips a sink in try, hop 2 a call in try"
(nv,) = {m for m in rx(eb, "G")}
assert all(re.match(nv, s) for s in ("withTenant", "module.exports.list", "GETS", "get")) and not any(re.match(nv, s) for s in ("GET", "POST", "DELETE", "OPTIONS")), nv
assert eb.count("*not_next_verb") == 1 and eb.count("*express_meth") == 1 and eb.count("*req_name") == 1, "hop 2 reuses hop 1's name filters"
RC = open(os.path.join(SK, "scripts", "review_checks.sh")).read()
assert f'x[2] != "{EXPRESS4}" or ex4(x[0])' in RC, "review_checks.sh gates the rule on Express 4"
print("ok")
