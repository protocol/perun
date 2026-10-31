#!/usr/bin/env python3
"""route_auth_map.py [--paths] DIR -- heuristic lead-finder for HTTP handlers with no authentication evidence (CWE-306/862). Report-only, stdlib only.

Read this when you review an API surface for missing authentication or run the anonymous GET sweep in security-appsec.md: a handler that
mutates state and never touches an identity check is reachable by anyone, and generic linters do not see it. Run
`python3 -I route_auth_map.py DIR` (add `--paths` to list the GET and ANY routes, one per line). A row is a lead to verify, and SILENCE IS NOT PROOF
OF AUTHENTICATION: the scan only sees the call shapes listed below.

1. Inventory every handler: Next.js app/**/route.(ts|tsx|js|jsx|mjs) exported GET/POST/PUT/PATCH/DELETE (function, const, destructured or re-exported),
   pages/api/** (methods read from `req.method` checks, else ANY), "use server" exported async functions (METHOD ACTION), Express/Router/Hono/
   Fastify `<receiver>.get|post|put|patch|delete|all("/path", ...)` (TS type arguments allowed: `app.post<{ Body: Widget }>("/path", h)`), FastAPI `@x.get(...)` and Flask `@x.route(..., methods=[...])` decorators.
2. One row per handler: `path:line: SEV: METHOD route auth=<evidence>`. Evidence, first hit wins: a call, decorator or `Depends(...)` naming an
   identity check (IDENTITY below: getServerSession, auth(), currentUser, requireAuth*, verify*, login_required...; a Depends/Security argument
   with user, auth, token, current, bearer, jwt, api_key, verify or login in it) or `req.user`/`current_user.`/`g.user` in the handler, in a
   same-file function it names, or at module level (a `.use(<auth>)` or Fastify addHook on the same receiver BEFORE the route counts, with its
   path prefix); else `token` (a header read in the handler and a comparison with a secret/token/api-key/password word on one line); else `middleware` (a Next
   middleware.ts/proxy.ts of the same app that names an identity check, or can answer 401/403 under any name (`status: 401`, `.status(403)`,
   `.code(401)`, `statusCode = 403`, `.unauthorized(`, `.forbidden(`, `new Response("Unauthorized"`), and whose matcher covers the route, less any route a quoted `/path` in that file names as an allow-list entry
   (a trailing `(.*)`, `/*` or `/:name*` is dropped first; a path in the condition of an `if` that refuses is a scope check, not an entry)); else `root-hook` (a Fastify `x.addHook("onRequest"|"preHandler"|"preValidation"|"preParsing", fn)` on a receiver bound
   to a `Fastify(...)` call, at any depth (a factory function included), whose `fn` can refuse as above or names an identity check, inline or in a same-file function or const it names.
   It covers what the hook file wires onto that receiver AFTER the hook, in source order and within the block that holds the hook (a plugin function or an `if` does not leak): the routes of a scanned file that it passes to `x.register(plugin, opts)` by a relative import (or an inline
   `require`/`import`), or that it calls as `fn(x, ...)` with x as the first argument and `fn` imported from that file, and the non-GET routes declared on x in its own file. What the hook covers is read
   from the `if` statements of its text up to and including its first refusal: a negated path test with a bare return (`if (!req.url.startsWith("/api/")) return;`) is a scope, so only routes under it
   are covered; a positive path test with a bare return (`=== "/api/ping"`, or `PUBLIC_PATHS.includes(url)` over a same-file declaration of the paths) is an allow-list entry (also after the refusal),
   so a route it names keeps its own evidence (`===` and `==` name that path only, `startsWith` and any other test such as `includes` every route whose path starts with it, `/api/pingpong` too, as JS
   does); a path in the condition of a refusing `if` is a scope (`startsWith` scopes the routes under it by path segment, `===` and any other test only that path), and a `!` before it covers nothing. A quoted path anywhere else (a role table the hook reads, a path
   test in a refusing `if` after the first refusal) says nothing, and a route-registration literal never counts. A bare return before the first refusal under a condition that is no path test and no
   identity check (`if (req.headers["x-preview"]) return;`) is a bypass: the hook covers nothing. The `prefix` option of the register call is put before the route when such a path is judged); else `none`.
3. SEV: HIGH when auth is none and the handler mutates (any method but GET; ANY and ACTION count as mutating), else INFO.

Known limits (NOT covered, so silence proves nothing): auth applied at a mount in another file (`app.use("/api", authedRouter)`) reads none;
a middleware's path rules are read only as quoted `/path` literals: any such literal in the file (an allow-list array or Set, a Clerk-style `createRouteMatcher([...])`
list, or any other path rule narrower than the matcher) takes that route and what is under it out of the middleware's coverage, except a prefix of a matcher entry (the matcher's
own paths, `startsWith("/api")` under `/api/:path*`) and a literal in the condition of an `if` whose braced block or one statement can refuse (a scope
check, nested refusals included: `if (p.startsWith("/api/")) { return <401> }`; a braceless body runs over a line break when the next line starts with `.`, `?`, `:`,
`&&` or `||` or this one ends in `?`, `:`, `&&` or `||`); a trailing `(.*)`, `/*` or `/:name*` is dropped from a literal (`"/sign-in(.*)"` takes `/sign-in` and what is
under it out; a wildcard inside a path, `/a/*/b`, is not read) and only a route that starts with the literal is taken out, so `includes("/hook")` or `endsWith("/hook")`
leaves `/api/hook` reading `middleware` (it is open); conditions are not evaluated and a literal held in a collection or variable is not followed
to its uses, so `if (!p.startsWith("/open")) return <401>` reads `/open` as gated (it is open) and `if (!p.startsWith("/api")) return next()` reads `/api` as
open (it is gated) unless a matcher entry starts with it, as does a scope check that is no `if` with a refusing body (a ternary `p.startsWith("/api/") ? <401> : next()`,
an `&&` chain, a `switch` `case`, a body that only redirects to a login page); a regex, computed or imported allow-list is not read, so a route it lets through, or one
covered by a 401/403 that checks no identity (CSRF, geo, rate limit), still reads `middleware`, while a gate that only redirects to a login page under
custom names reads none; an identity check that calls no listed name (`ctx.state.session`) is missed; evidence one function away is followed
only one level through same-file functions (from a route's own arguments, not from `.use(guard)`), and a name in IDENTITY covers by name alone;
Flask `before_request` and FastAPI `@app.middleware` guards are not followed (those routes read none); server actions are not matched against
middleware; the shown route has no mount prefix; ANY has no method check, so a read-only
pages/api handler can be over-flagged; not handled: Django urls, NestJS decorators, `.route(path).get()` chains, calls chained on a call result
(`new Elysia().get(...)`) or split from their receiver by whitespace, `fastify.route({...})`, `app.on(...)`, a call with a spread argument
(`app.post("/x", ...guards, h)`), inline "use server", wrapped action consts (`export const a = wrap(async ...)`), template or computed route
paths, `.all("/x/*", guard)` as a gate (it reads as an ANY route). A type-argument list is read only when its angle brackets balance within 2000 characters with no `;`, `&&` or `||` outside
brackets and a `(` follows, so a list that breaks that reads as no route. A `root-hook` row is only as good as the text scan: conditions are not evaluated (a method
test, a regex or computed path test, a scope held in a variable, an `endsWith`, `includes` or `slice(0, n) ===` test read as a prefix test when it exempts and as the path itself when it scopes, a per-route opt-out inside the hook, or a bypass OR-ed with a path test still reads `root-hook`,
and a path rule that is no `if` condition (a ternary, an `&&` chain, a `switch` `case`) is not read at all, so a route it exempts reads `root-hook`), a `!` before a scope path in a refusing
`if`, or before a path test that is OR-ed or AND-ed with anything else, makes the hook cover nothing (which side is open is unknown), a bare return after the first refusal is not checked as a
bypass, the hook must come before the `register` call, the direct call or the route in source order and in a block that holds it (an awaited register has already loaded its routes; a route above the
hook in its own file is never credited, nor is a GET of its own file; a hook in a plugin function or an `if` reaches nothing after that block, and code formatted at column 0 widens the block), every wiring site seen of a routes file must be covered (every call of an imported name counts as one, and direct calls are read only in
files that contain `.register` or `addHook`; a namespace member call `ns.fn(app)` or a call with type arguments is not seen), a `prefix` that is not a plain string literal leaves a hook with a
scope or allow-list path covering nothing, handlers are followed through same-file declarations only (an imported guard is not read), allow-list paths
are matched as text, and a bare IDENTITY name or a 401/403 alone makes a hook count. A hook on a receiver not bound to `Fastify(...)` (a plugin parameter, a factory result,
`await Fastify()`) stays file-local (the `.use`/addHook rule above), and receivers are matched by name per file. Any other way of registering routes (a path alias,
autoload, `.route`, a plugin that registers another, `import type`, `export default function`, a typed CJS binding) is not seen, so those routes read none. A decorator above the route decorator
(Flask/FastAPI register the undecorated function) is ignored, so `@login_required` placed there reads none. A JS handler ends at the next line
that starts at column 0 and a Python one at the next line indented no deeper than its decorator, so minified one-line files blur spans.
Public-by-design routes (login, webhooks, health, NextAuth `[...nextauth]`) read none, or `middleware` when a gate lets them through by a rule that is not a literal path:
after reviewing one, put a `route-auth-ok` comment on its line or the line above and the row reads `auth=public`. Edit IDENTITY and RECEIVERS for house guards.

Output: one row per handler sorted by path then line, one JSON summary line (handlers, files, high, findings = the HIGH rows) and a stderr line
`heuristic; scanned N files with M handlers; ...`. `--paths` prints the unique GET and ANY routes (dynamic segments as `:name`) and no JSON.
Exit 0 always on a readable DIR (report-only: never fails a build on its own), 2 on usage error. Reads files only; writes nothing.
ponytail: text scan on the tenant_scope_check.py masker, not an AST -- regex literals with quotes can desync it. Upgrade to a parser if
precision matters more.
"""
import json, os, posixpath, re, sys

sys.dont_write_bytecode = True  # `python3 -I` drops this dir from sys.path: add it for the sibling import and leave no __pycache__ behind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tenant_scope_check import SKIP_DIR, close_of, lineno, mask, parts  # noqa: E402

IDENTITY = (  # configurable: a call, decorator or (in `.use`/route middleware) bare name like these counts as an identity check
    "getServerSession", "getSession", "getToken", "getAuth", "auth", "currentUser", "getUser", "getCurrentUser",
    r"require(?:Auth|User|Session|Login|Admin)\w*", "withAuth", r"auth(?:Middleware|Guard)", r"authenticate\w*", r"authorize\w*",
    "isAuthenticated", "isLoggedIn", r"ensure(?:Auth|LoggedIn)\w*", "protect", "validateRequest", r"verify\w*", "constructEvent",
    "jwt", "expressjwt", "checkJwt", "bearerAuth", "basicAuth", "clerkMiddleware",
    "login_required", "jwt_required", "token_required", "auth_required", "requires_auth", "permission_required", r"get_current_\w+")
RECEIVERS = {"app", "router", "server", "fastify"}  # `<name>.get("/x", ...)` is a route even without a framework constructor in the file
EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")
MARK = "route-auth-ok"
VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")
V = "|".join(VERBS)
H = V.lower()  # route method names as written in code: app.get, @app.post
ID = "|".join(IDENTITY)
CALL = re.compile(r"(?<![\w$])(%s)\(" % ID)
DECO = re.compile(r"@(?:\w+\.)*(%s)\b(?!\.(?:%s|route)\()" % (ID, H))  # not a route decorator on a blueprint named auth
DEP = re.compile(r"(?:Depends|Security)\(\s*[\w.]*(?:user|auth|token|current|bearer|jwt|api_?key|verify|login)\w*", re.I)
USE = re.compile(r"(?<![\w$])(%s)\b(?!:)" % ID)  # a bare name; `auth: false` (an object key) is not evidence
REQ = re.compile(r"\b((?:req|request)\.(?:user|auth)|current_user(?=\.)|g\.user)\b")  # `current_user.` only: an import of the name is not a check
CMP = re.compile(r"[!=]=|timingSafeEqual|compare_digest")
SEC = re.compile(r"secret|token|api.?key|password", re.I)
HDR = re.compile(r"header|authorization", re.I)
TEST = re.compile(r"\.(?:test|spec)\.|(?:^|/)(?:__tests__|tests?|e2e)/|(?:^|/)(?:test_[^/]*|[^/]*_test|conftest)\.py")
NAPP = re.compile(r"(?:(.*)/)?app/(?:(.*)/)?route\.(?:[tj]sx?|mjs)$")
NAPI = re.compile(r"(?:(.*)/)?pages/(api/.+)\.(?:[tj]sx?|mjs)$")
MWF = re.compile(r"(?:middleware|proxy)\.[jt]s")
REFUSE = re.compile(r"""\bstatus[:(]\s*40[13]|Response\(\s*["'](?:Unauthorized|Forbidden)|\.code\(\s*40[13]|\bstatusCode\s*=\s*40[13]|\.(?:unauthorized|forbidden)\(""")  # a middleware or hook that can answer 401/403 gates what it covers, whatever its check is called
GATE = re.compile(REFUSE.pattern + "|" + CALL.pattern)  # text that can refuse a request or calls an identity check
END = re.compile(r"^\S", re.M)  # a JS span ends at the next line that starts at column 0 (its closing brace or the next declaration)
JSFN = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)|^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\b|function\b|\()", re.M)
PYFN = re.compile(r"^(?:@[^\n]*\n)*(?:async[ \t]+)?def[ \t]+(\w+)", re.M)  # decorators above a def belong to it, not to the module
PYSTR = re.compile(r'#[^\n]*|("""|\'\'\')(?:\\.|(?!\1).)*?\1|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
LIT = re.compile(r"""(["'`])(/[^"'`$]*)\1""")
GLOB = re.compile(r"(?:\(\.\*\)|/\*|/:\w+\*)$")  # the wildcard that ends a glob-style path literal: `/sign-in(.*)`, `/x/*`, `/x/:path*`
JOIN = re.compile(r"(?:[?:]|&&|\|\|)\s*|(?<!\s)\s+(?=[.?:]|&&|\|\|)")  # whitespace a statement runs over: after `? : && ||`, before `. ? : && ||`
HOOK = re.compile(r"""(["'])(?:onRequest|preHandler|preValidation|preParsing)\1""")
BARE = re.compile(r"\breturn\s*(?:;|\}|$)|\b(?:done|next)\(\s*\)", re.M)  # a statement that lets the request through unanswered: `return;`, `return }`, `return` ending a line, `done()`
RCV =re.compile(r"\b(\w+)\s*(?::[^=\n]+)?=\s*(?:await\s+)?(?:new\s+)?(?:express|Router|Hono|Fastify|fastify|Elysia)\b")
PYDEC = re.compile(r"^([ \t]*)@\w+\.(%s|route)\(" % H, re.M)
PYDEF = re.compile(r"\bdef\s+\w+\s*\(")
JSPRE = re.compile(r"\.(?:%s|all)[(<]|use server" % H)
OPEN = re.compile(r"\s*\(")
FRCV = re.compile(r"""\b(\w+)\s*(?::[^=\n]+)?=\s*(?:[Ff]astify|require\(\s*["']fastify["']\s*\))\s*\(""")  # a receiver bound to a Fastify instance
DECL = re.compile(r"^([ \t]*)(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+([\w$]+)", re.M)
IMP = (re.compile(r"""\bimport\s+([^"']*?)\s*from\s*(["'])(\.[^"'\n]*)\2"""),  # import a, { b as c } from "./x"
       re.compile(r"""\b(?:const|let|var)\s+([^=]*?)=\s*(?:await\s+)?(?:require|import)\(\s*(["'])(\.[^"'\n]*)\2"""))  # const { a } = require("./x")
INL = re.compile(r"""\b(?:require|import)\(\s*["'](\.[^"'\n]*)["']""")  # register(require("./x"))
ARG1 = re.compile(r"\s*([\w$]+)\s*[,)]")  # the first argument of a call, when it is a bare name


def pymask(s, keep=False):
    """mask() for Python: `#` comments blanked, string contents (triple quotes included) blanked unless keep; quotes and newlines kept."""
    def sp(t): return re.sub(r"[^\n]", " ", t)
    def f(x):
        t = x.group(0)
        if t[0] == "#": return sp(t)
        if keep: return t
        return t[0] + sp(t[1:-1]) + t[-1]
    return PYSTR.sub(f, s)


def blank(t, spans):
    """t with every (a, b) span replaced by spaces (newlines kept)."""
    o = list(t)
    for a, b in spans: o[a:b] = [c if c == "\n" else " " for c in t[a:b]]
    return "".join(o)


def ident(t, bare=False):
    """Label of the earliest identity evidence in masked text t (bare names count too when bare), else None."""
    hits = []
    for rx in (CALL, DECO, DEP, REQ) + ((USE,) if bare else ()):
        x = rx.search(t)
        if x: hits.append((x.start(), re.sub(r"\s+", "", x.group(0)) + ")" if rx is DEP else x.group(1)))
    return min(hits)[1] if hits else None


def tok(k):
    """True when strings-kept text k compares a header against a secret-looking word on one line (a shared-secret check)."""
    return bool(HDR.search(k)) and any(CMP.search(l) and SEC.search(l) for l in k.splitlines())


def seg(s):
    x = re.fullmatch(r"\[\[?\.\.\.(\w+)\]?\]", s)  # [...x] and [[...x]]
    if x: return ":%s*" % x.group(1)
    x = re.fullmatch(r"\[(\w+)\]", s)
    return ":" + x.group(1) if x else s


def nroute(path):
    """Next file path (below app/ or pages/) to a route: route groups (x) dropped, [id] -> :id, [...x] -> :x*."""
    return "/" + "/".join(seg(s) for s in path.split("/") if not re.fullmatch(r"\(.*\)", s))


def pyroute(p):
    p = re.sub(r"<(?:[\w.]+:)?(\w+)>", r":\1", re.sub(r"\{(\w+)(?::[^}]*)?\}", r":\1", p))
    return p if p.startswith("/") else "/" + p


def methods(k):
    """GET/POST/PUT/PATCH/DELETE a pages/api file tests for (`req.method ===`, `case "X":`), in canonical order."""
    rx = r"""\bmethod\s*[!=]==?\s*"(%s)"|"(%s)"\s*[!=]==?\s*\w+\.method|\bcase\s+"(%s)"\s*:""" % (V, V, V)
    found = {g for t in re.findall(rx, k.replace("'", '"')) for g in t}
    return [v for v in VERBS if v in found]


def items(s):
    """[(local, exported)] of an `export { a as B, C }` or destructuring name list (a trailing comma gives an empty pair)."""
    return [(p[0], p[-1]) for p in (re.split(r"\s*(?::|\bas\b)\s*", x.strip()) for x in s.split(","))]


def nextdecl(m, i):
    x = END.search(m, i + 1)
    return x.start() if x else len(m)


def outdent(m, i, n):
    """Index of the line break before the first non-blank line after i that is indented no deeper than n columns, else len(m)."""
    e = re.compile(r"\n[ \t]{0,%d}(?=\S)" % n).search(m, i)
    return e.start() if e else len(m)


def block_end(m, i):
    """Index of the line break that ends the block holding position i: before the first later line indented less than i's own line (len(m) when that line is at column 0)."""
    n = len(re.match(r"[ \t]*", m[m.rfind("\n", 0, i) + 1:])[0])
    return outdent(m, i, n - 1) if n else len(m)


def defs(m, py):
    """{name: (start, end)} of column-0 function definitions: start just after the name (Python: at its decorators), end at the next column-0 declaration or statement."""
    out = {}
    for t in (PYFN if py else JSFN).finditer(m):
        e = re.compile(r"\n(?=\S)").search(m, t.end()) if py else END.search(m, t.end())
        out[next(g for g in t.groups() if g)] = (t.start() if py else t.end(), e.start() if e else len(m))
    return out


def p2re(p):
    """Next matcher path (path-to-regexp subset) to a regex source; (?: groups survive the :name rewrite."""
    p = re.sub(r"/:\w+\*", "(?:/.*)?", p)
    p = re.sub(r"/:\w+\+", "/.+", p)
    p = re.sub(r"/:\w+\?", "(?:/[^/]+)?", p)
    return re.sub(r"(?<!\?):\w+", "[^/]+", p)


def ifs(m):
    """(open, close, start, end) of each `if (...)` in masked text m: the indexes of the condition's parentheses and of the first and last character of its body.
    The body is the braced block (nested statements count, an `else` branch does not) or the one statement, which ends at the first `;` or line break outside brackets
    that does not carry it on (the next line starts with `.`, `?`, `:`, `&&` or `||`, or this one ends in `?`, `:`, `&&` or `||`: a ternary, logical or chained call)."""
    j = JOIN.sub(lambda x: x[0].replace("\n", " "), m)  # same length as m, with those line breaks read as spaces
    for t in re.finditer(r"\bif\s*\(", m):
        a = t.end() - 1
        b = close_of(m, a)
        if b < 0: continue
        s = b + 1
        while m[s:s + 1].isspace(): s += 1
        e, d = s, 0
        if m[s:s + 1] == "{": e = close_of(m, s)
        else:
            for e in range(s, len(m)):
                d += (j[e] in "([{") - (j[e] in ")]}")
                if d < 1 and j[e] in ";\n": break
        yield a, b, s, e


def refusing_ifs(m, mk):
    """(open, close) indexes of the parentheses of each `if (...)` in masked text m whose body (see ifs) can answer 401/403 (REFUSE in strings-kept mk)."""
    return [(a, b) for a, b, s, e in ifs(m) if REFUSE.search(mk[s:e + 1])]


def litpath(g):
    """The path a quoted /path match g (LIT) names as an allow-list entry: a trailing `(.*)`, `/*` or `/:name*` and trailing slashes dropped."""
    return GLOB.sub("", g[2]).rstrip("/")


def lit(mk, g):
    """(path, op) of the quoted /path match g (LIT) in strings-kept text mk: the path as litpath reads it, and how the text tests it. op is "=" when the literal is compared with
    `==` or `===` on either side against a plain identifier or member chain (`req.url`, `req.routeOptions.url`), "^" when it is the argument of `startsWith(`, else "?" (`includes`,
    a collection, a regex, `!==`, or `==`/`===` against a call or an index: `slice(0, n)`, `path.dirname(x)`, `split("?")[0]` can test a prefix or a derived value, and "?" only
    moves a route toward flagged). gated() reads the op by role: a test that exempts or scopes a route by its raw string reads differently from one that scopes it by path segment."""
    pre, post = mk[max(0, g.start() - 40):g.start()], mk[g.end():g.end() + 40]
    return litpath(g), "=" if re.search(r"[\w$]\s*={2,3}\s*$", pre) or re.match(r"\s*={2,3}(?!=)\s*[\w$.]+(?=\s*[^\s\w$.?(\[])", post) else "^" if re.search(r"startsWith\(\s*$", pre) else "?"


def mw_pats(m, mk):
    """Matcher regexes of a Next middleware that names an identity check or can answer 401/403 (catch-all without a matcher, [] when it has none we can read), else [].
    Every quoted /path in the file counts as a public allow-list entry: that route and what is under it stay uncovered (a trailing `(.*)`, `/*` or `/:name*` is dropped
    first, so a glob list such as `createRouteMatcher(["/sign-in(.*)"])` works). Not an exemption: "/", a literal that is a prefix of
    a matcher entry (the matcher's own paths), and a literal in the condition of an `if` whose body can refuse (a scope check such as `if (p.startsWith("/api/")) return 401`)."""
    if not (ident(m, True) or "next-auth/middleware" in mk or REFUSE.search(mk)): return []
    x = re.search(r"\bmatcher\s*:\s*", m)
    i = x.end() if x else len(m)
    c = m[i:i + 1]
    j = close_of(m, i) if c == "[" else m.find(c, i + 1) if c in ("'", '"', "`") else -1
    ms = [p.replace("\\\\", "\\") for p in re.findall(r"""['"`](/[^'"`]*)['"`]""", mk[i:j + 1])]
    sc = refusing_ifs(m, mk)
    lits = {litpath(g) for g in LIT.finditer(mk) if not any(a < g.start() < b for a, b in sc)}
    opn = "".join("(?!%s(?:/|$))" % re.escape(q) for q in lits if q and not any(p.startswith(q) for p in ms))
    if not x: return [re.compile(opn + ".*")]
    pats = []
    for p in ms:
        try: pats.append(re.compile(opn + p2re(p)))
        except re.error: pass
    return pats


def next_hs(m, route, mwb, hs, gone, fn):
    """Next app/**/route.* exports: `function GET`, `const GET =`, `const { GET, POST } =`, `export { h as GET }`."""
    for t in re.finditer(r"^export\s+(?:async\s+)?function\s+(%s)\b|^export\s+(?:const|let|var)\s+(%s)\b" % (V, V), m, re.M):
        gone.append((t.end(), nextdecl(m, t.start())))
        hs.append((t.start(), t.group(1) or t.group(2), route, [gone[-1]], None, None, mwb))
    for t in re.finditer(r"^export\s+(?:const|let|var)\s*\{([^}]*)\}\s*=", m, re.M):
        gone.append((t.end(), nextdecl(m, t.start())))
        hs.extend((t.start(), ex, route, [gone[-1]], None, None, mwb) for _, ex in items(t.group(1)) if ex in VERBS)
    for t in re.finditer(r"^export\s*\{([^}]*)\}", m, re.M):
        hs.extend((t.start(), ex, route, [fn[lo]] if lo in fn else [], None, None, mwb) for lo, ex in items(t.group(1)) if ex in VERBS)


def opener(m, i):
    """Index of the `(` that opens the call arguments at m[i], past a TS type-argument list `<...>` when m[i] is `<`; -1 when it is no call (`x.get < y && f(z)`).
    The angles must balance within 2000 characters, no `;`, `&&`, `||` or closing bracket may stand outside brackets before they do, and `(` must follow."""
    if m[i:i + 1] == "(": return i
    o = a = 0
    for k in range(i, min(len(m), i + 2000)):
        c = m[k]
        if c in "([{": o += 1
        elif c in ")]}":
            o -= 1
            if o < 0: return -1
        elif o == 0:
            if c == "<": a += 1
            elif c == ">" and m[k - 1] != "=":  # `=>` is an arrow type, not a closing angle
                a -= 1
                if a == 0:
                    x = OPEN.match(m, k + 1)
                    return x.end() - 1 if x else -1
            elif c == ";" or m[k:k + 2] in ("&&", "||"): return -1
    return -1


def callargs(m, mk, names, rcv=None):
    """(match, open, close, parts) of each `<receiver>.<name>(...)` or `.<name><T>(...)` call (name: regex alternatives) in masked text m, on a receiver in rcv when given;
    a call with a spread argument or unbalanced brackets is skipped."""
    for t in re.finditer(r"\b(\w+)\.(%s)(?=[(<])" % names, m):
        if rcv is not None and t.group(1) not in rcv: continue
        op = opener(m, t.end())
        cl = close_of(m, op) if op > 0 else -1
        ps = parts(m[op + 1:cl], mk[op + 1:cl]) if cl > 0 else None
        if ps: yield t, op, cl, ps


def call_hs(m, mk, hs, uses, gone):
    """Express/Router/Hono/Fastify `<receiver>.get|post|...(path, ...)` routes, TS type arguments allowed, and positional `.use(...)` / `.addHook(...)` auth."""
    rcv, frcv = RECEIVERS | set(RCV.findall(m)), set(FRCV.findall(mk))
    for t, op, cl, ps in callargs(m, mk, "use|addHook|%s|all" % H, rcv):
        r, k = t.group(1), t.group(2)
        p0 = ps[0][1].strip()
        lit = LIT.fullmatch(p0)
        if k in ("use", "addHook"):
            gone.append((t.start(), cl + 1))
            if k == "addHook" and not HOOK.fullmatch(p0): continue
            if k == "addHook" and r in frcv and len(ps) > 1 and not re.fullmatch(r"[\w$.]+", ps[1][0].strip()): continue  # an inline handler on a Fastify() receiver is judged by wiring(), not by name
            lab = ident(",".join(a[0] for a in ps), True)
            if lab: uses.append((r, t.start(), lit.group(2).rstrip("*/") if lit else "", lab))
        elif lit and len(ps) > 1:
            gone.append((op, cl + 1))
            hs.append((t.start(), "ANY" if k == "all" else k.upper(), lit.group(2), [(op + 2 + len(ps[0][0]), cl)],
                       ident(",".join(a[0] for a in ps[:-1]), True), r, None))


def py_hs(m, mk, hs, gone):
    """FastAPI `@x.get("/p")` and Flask `@x.route("/p", methods=[...])` decorators; the span is the route decorator, the ones below it, the signature and the body.
    Decorators ABOVE the route decorator are not evidence for it: the framework registers the undecorated function."""
    for t in PYDEC.finditer(m):
        op = t.end() - 1
        cl = close_of(m, op)
        ps = parts(m[op + 1:cl], mk[op + 1:cl]) if cl > 0 else None
        pm = ps and re.fullmatch(r"""(["'])(/[^"']*|)\1""", ps[0][1].strip())
        dm = PYDEF.search(m, cl) if pm else None
        sc = close_of(m, dm.end() - 1) if dm else -1
        if sc < 0: continue
        km = re.search(r"\bmethods\s*=\s*[\[(]([^\])]*)", mk[op + 1:cl])
        if t.group(2) != "route": meths = [t.group(2).upper()]
        elif km: meths = [v for v in VERBS if re.search(r"""['"]%s['"]""" % v, km.group(1), re.I)]
        else: meths = ["GET"]
        if not meths: continue
        end = outdent(m, sc, len(t.group(1)))
        gone.append((t.start(), end))
        hs.append((t.start(), "|".join(meths), pyroute(pm.group(2)), [(t.start(), dm.start()), (dm.end() - 1, end)], None, None, None))


def mount(ps):
    """Path prefix a `x.register(plugin, opts)` call (ps: its parts) mounts the plugin under: the literal `prefix` of an inline options object, "" when there is none to read
    (no options, or an object with neither `prefix` nor a spread), None when it is unknown (an options variable, a spread, a prefix that is not a string literal)."""
    o = ps[1][1].strip() if len(ps) > 1 else "{}"
    if o[:1] != "{" or "..." in o: return None
    if not re.search(r"\bprefix\b", o): return ""
    g = re.search(r"\bprefix\s*:\s*" + LIT.pattern + r"\s*[,}]", o)
    return g[2].rstrip("/") if g else None


def resolve(rel, spec, known):
    """The file in known (rel's scanned files) that the relative import `spec` written in `rel` names: as written, with a source extension or as a directory index; a `.js` spec finds its `.ts` source. None when absent."""
    b = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
    for c in (b, re.sub(r"\.jsx?$", "", b)):
        for s in ("",) + EXT + tuple("/index" + e for e in EXT):
            if c + s in known: return c + s


def decls(m):
    """{name: (start, end)} of function and const/let/var declarations at any indent: start just after the name, end at the next line indented no deeper than the declaration.
    ponytail: one entry per name (the last wins), so the same name in two scopes collides; upgrade to scoped lookup if that matters."""
    return {t.group(2): (t.end(), outdent(m, t.end(), len(t.group(1)))) for t in DECL.finditer(m)}


def reach(m, dc, a, b):
    """[(start, end)] spans of m[a:b] and, transitively, of the same-file declarations (dc) whose names appear in it."""
    sp, seen = [(a, b)], set()
    for x, y in sp:  # grows as it goes
        for w in re.findall(r"[\w$]+", m[x:y]):
            if w in dc and w not in seen: seen.add(w); sp.append(dc[w])
    return sp


def hook(m, mk, dc, a, b):
    """([scope groups], [exempt paths]) of a Fastify hook handler at m[a:b] that can answer 401/403 or names an identity check, else None; each path is a lit() pair, and a route
    is covered when every group scopes it and no exempt path lets it through (see gated). The handler's text is the span plus, transitively, the same-file declarations (dc) it
    names. Only the `if` statements up to and including the first refusal (the first REFUSE match of each span) say what the hook covers; a quoted /path anywhere else (a role
    table the hook reads, a path test after the refusal) says nothing. A trailing `(.*)`, `/*` or `/:name*` is dropped from a path.
    - A path in the condition of an `if` whose body refuses or calls an identity check is a scope (one group for all of them); a `!` before it makes the test ambiguous: None.
    - A path test whose body is a bare return (BARE), the path written in the condition or in a same-file declaration the condition names: negated (`!`) it is a scope (a group per
      `if`), else an allow-list entry, also after the first refusal; a negated one that is OR-ed or AND-ed with anything else is ambiguous: None.
    - A bare return before the first refusal under a condition that is no path test and no identity check (an IDENTITY call, or a comparison with a secret/token/api-key/password
      word) is a bypass: None.
    ponytail: conditions are not evaluated (a bypass OR-ed with a path test reads as the path test; `includes`, `endsWith`, a regex test and `==`/`===` against a call or an index
    (`slice(0, n)`, `path.dirname(x)`, `split("?")[0]`) read as a prefix test when they exempt and as the path itself when they scope), a trailing slash on a `startsWith` literal is dropped, so it exempts a longer name too, a
    bare return after the first refusal is not checked as a bypass, `return reply...` and `return true` are not bare, and a bare return in a same-file helper the hook names voids
    it too (a noisy HIGH, never a quiet one)."""
    sp = reach(m, dc, a, b)
    if not (REFUSE.search("\n".join(mk[x:y] for x, y in sp)) or CALL.search("\n".join(m[x:y] for x, y in sp))
            or (re.fullmatch(r"[\w$.]+", m[a:b].strip()) and USE.search(m[a:b]))): return None
    cut = {}  # span -> index of its first refusal
    for x, y in sp:
        r = REFUSE.search(mk, x, y)
        cut[x, y] = r.start() if r else y
    groups, scope, free = [], set(), set()
    for o, c, s, e in ifs(m):
        span = next((p for p in sp if p[0] <= o < p[1]), None)
        if span is None: continue
        before = o < cut[span]
        if GATE.search(mk[s:e + 1]):
            if not before: continue
            for g in LIT.finditer(mk, o, c):
                if "!" in m[o:g.start()]: return None
                scope.add(lit(mk, g))
        elif BARE.search(m[s:e + 1]):
            lits = {lit(mk, g) for x, y in reach(m, dc, o, c + 1) for g in LIT.finditer(mk, x, y)}
            if lits and "!" not in m[o:c]: free |= lits
            elif not before: continue
            elif lits and re.search(r"&&|\|\|", m[o:c]): return None
            elif lits: groups.append(sorted(lits))
            elif not (CALL.search(m[o:c]) or CMP.search(mk[o:c]) and SEC.search(mk[o:c])): return None
    return ([sorted(scope)] if scope else []) + groups, sorted(free)


def wiring(rel, raw, known):
    """(hooks, sites) of the file rel. hooks: {receiver: [(position, end of its block, hook())]} for each `x.addHook("onRequest"|...)` that hook() accepts, x being bound to a `Fastify(...)` call, at any depth.
    sites: [(file, (mount, hooks))], one for each place rel wires the routes of a scanned file onto an instance: `x.register(plugin, opts)` whose plugin is a relative import, or an inline
    require/import, of that file (mount is mount(opts)), and a call `fn(x, ...)` of a name imported from it outside any register call (mount ""). hooks are those on x placed before the
    call or register in a block that holds it (block_end); a direct call whose first argument is not a bare name has none.
    ponytail: direct calls are read only in files that contain `.register` or `addHook` (the masker is slow), so a second call site elsewhere is missed; a namespace member call
    (`ns.fn(app)`) or a call with type arguments is not seen; every call of an imported name is a site, so a helper called from a hook or a factory called elsewhere leaves its file uncovered."""
    m, mk = mask(raw), mask(raw, True)
    imp, dc, hooks, sites = {}, decls(m), {}, []
    for rx in IMP:
        for t in rx.finditer(mk):
            imp.update((b, resolve(rel, t[3], known)) for _, b in items(re.sub(r"[{}]", "", t[1])))
    for t, op, cl, ps in callargs(m, mk, "addHook", set(FRCV.findall(mk))):
        if len(ps) < 2 or not HOOK.fullmatch(ps[0][1].strip()): continue
        a = op + 2 + len(ps[0][0])  # the handler argument
        h = hook(m, mk, dc, a, a + len(ps[1][0]))
        if h: hooks.setdefault(t[1], []).append((t.start(), block_end(m, t.start()), h))
    regs = list(callargs(m, mk, "register"))
    for t, op, cl, ps in regs:
        fs = {resolve(rel, s, known) for s in INL.findall(ps[0][1])} | {imp.get(w) for w in re.findall(r"[\w$]+", ps[0][0])}
        site = (mount(ps), [h for p, q, h in hooks.get(t[1], []) if p < t.start() < q])
        sites += [(f, site) for f in fs]  # an unresolved name gives None: no file is called that
    names = [re.escape(w) for w, f in imp.items() if f]
    for t in (re.finditer(r"(?<![\w$.])(%s)\(" % "|".join(names), m) if names else ()):
        if any(op < t.start() < cl for _, op, cl, _ in regs): continue  # inside a register call: the register site covers it
        x = ARG1.match(m, t.end())
        sites.append((imp[t[1]], ("", [h for p, q, h in hooks.get(x and x[1], []) if p < t.start() < q])))
    return hooks, sites


def gated(sites, route):
    """True when at every site (mount, hooks) of the file a refusing root hook covers `route`. A hook with no path literal covers it whatever the mount; one with scope
    groups covers only the routes every group scopes, less the routes an exempt path lets through, judged on mount + route (an unknown mount covers nothing). A path is read by
    its op (lit), as the JS test runs: a scope is the path itself for `==`, `===` and any other test, and the routes under it by path segment for `startsWith`; an exemption is
    the path itself for `==` and `===` against a plain name, and every route whose raw path starts with it (`/x/healthz` under `/x/health`) for `startsWith` and any other test, the root `/` alone
    for any but `startsWith`. No sites: False."""
    def cover(p, t): q, op = t; return p == q or op == "^" and bool(q) and p.startswith(q + "/")
    def exempt(p, t): q, op = t; return p == q or op != "=" and (op == "^" or bool(q)) and p.startswith(q)
    def ok(pre, sc, ex):
        if not (sc or ex): return True
        if pre is None: return False
        p = (pre + route).rstrip("/")
        return all(any(cover(p, q) for q in g) for g in sc) and not any(exempt(p, q) for q in ex)
    return bool(sites) and all(any(ok(pre, *h) for h in hs) for pre, hs in sites)


def analyze(rel, raw, mws, sites=None, hooks=None):
    """[(path, line, METHOD, route, auth)] for one file; sites: the wiring() sites that wire the file, for the root-hook evidence; hooks: the wiring() hooks of the file itself.
    A non-GET route is also covered by the hook of its own receiver declared before it in a block that holds the route (a route above the hook keeps its own evidence, and a GET reads INFO either way).
    ponytail: source order stands in for Fastify registration order, so a route added before the hook is never credited (conservative); block nesting stands in for encapsulation, so a hook
    in a plugin function or an `if` never reaches a route after the block, and a column-0 one-liner widens the block to the end of the file."""
    hooks, py = hooks or {}, rel.endswith(".py")
    mk_ = pymask if py else mask
    m, mk, rl = mk_(raw), mk_(raw, True), raw.splitlines()
    fn = defs(m, py)
    hs, uses, gone = [], [], []  # handlers (pos, METHOD, route, spans, pre-label, receiver, middleware base); `.use` auth; spans hidden from module-level text
    if py: py_hs(m, mk, hs, gone)
    else:
        n, p = NAPP.match(rel), NAPI.match(rel)
        if n: next_hs(m, nroute(n.group(2) or ""), n.group(1) or "", hs, gone, fn)
        elif p:
            segs = p.group(2).split("/")
            d = re.search(r"^(?:export\s+default|module\.exports)", m, re.M)
            hs.append((d.start() if d else 0, "|".join(methods(mk)) or "ANY", nroute("/".join(segs[:-1] if segs[-1] == "index" else segs)), [(0, len(m))], None, None, p.group(1) or ""))
        if re.match(r"\s*(['\"])use server\1", mk):
            for t in re.finditer(r"^export\s+async\s+function\s+(\w+)|^export\s+const\s+(\w+)\s*=\s*async\b", m, re.M):
                gone.append((t.end(), nextdecl(m, t.start())))
                hs.append((t.start(), "ACTION", t.group(1) or t.group(2), [gone[-1]], None, None, None))
        call_hs(m, mk, hs, uses, gone)
    hide = gone + list(fn.values())
    mod = ident(blank(m, hide))  # module level: what is outside every handler, function definition and `.use` call; scanned once, per handler it would make a file with many routes quadratic
    out = []
    for pos, meth, route, spans, pre, rcv, mwb in hs:
        ln = lineno(m, pos)
        own = "\n".join(m[a:b] for a, b in spans)
        got = [(ident(m[a:b]), tok(mk[a:b])) for a, b in spans + [fn[w] for w in sorted(set(re.findall(r"[\w$]+", own))) if w in fn]] + [(mod, False)]
        use = next((u[3] for u in uses if u[0] == rcv and u[1] < pos and (route == u[2] or route.startswith(u[2] + "/"))), None)
        pats = mws.get(mwb) if mwb is not None else None
        mw = "middleware" if pats and any(x.fullmatch(route) for x in pats) else None
        mine = [h for p, q, h in hooks.get(rcv, ()) if p < pos < q]  # hooks on this route's receiver declared before it, in a block that holds it
        lab = pre or use or next((g[0] for g in got if g[0]), None) or ("token" if any(g[1] for g in got) else None) or mw or ("root-hook" if gated(sites, route) or meth != "GET" and gated([("", mine)], route) else None) or "none"
        if any(MARK in l for l in rl[max(0, ln - 2):ln]): lab = "public"
        out.append((rel, ln, meth, route, lab))
    return out


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8-sig", errors="replace") as f: return f.read()
    except OSError: return None


def scan(root):
    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIR)
        for f in sorted(fn):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            if f.endswith(EXT) and not TEST.search(rel): files.append(rel)
    known = set(files)
    mws, rows, todo, cov, own = {}, [], [], {}, {}  # todo: files with handlers; cov: file -> wiring() sites that wire it; own: file -> its own wiring() hooks
    for rel in files:
        raw = read(root, rel) if MWF.fullmatch(os.path.basename(rel)) else None
        if raw is not None: mws[os.path.dirname(rel)] = mw_pats(mask(raw), mask(raw, True))
    for rel in files:
        raw = read(root, rel)
        if raw is None: continue
        if ".register" in raw or "addHook" in raw:
            own[rel], sites = wiring(rel, raw, known)
            for f, site in sites: cov.setdefault(f, []).append(site)
        if NAPP.match(rel) or NAPI.match(rel) or (PYDEC if rel.endswith(".py") else JSPRE).search(raw): todo.append((rel, raw))
    for rel, raw in todo: rows += analyze(rel, raw, mws, cov.get(rel), own.get(rel))
    return sorted(rows), len(todo)


def main(argv):
    a = [x for x in argv[1:] if x != "--paths"]
    if len(a) != 1 or not os.path.isdir(a[0]):
        print("usage: route_auth_map.py [--paths] DIR", file=sys.stderr); return 2
    rows, files = scan(a[0])
    print("heuristic; scanned %d files with %d handlers; silence is not proof of authentication" % (files, len(rows)), file=sys.stderr)
    if "--paths" in argv[1:]:
        for r in sorted({r[3] for r in rows if {"GET", "ANY"} & set(r[2].split("|"))}): print(r)
        return 0
    out = [(r, "HIGH" if r[4] == "none" and any(x != "GET" for x in r[2].split("|")) else "INFO") for r in rows]
    for r, s in out: print("%s:%d: %s: %s %s auth=%s" % (r[0], r[1], s, r[2], r[3], r[4]))
    hi = [(r, s) for r, s in out if s == "HIGH"]
    print(json.dumps({"tool": "route_auth_map", "handlers": len(rows), "files": files, "high": len(hi),
                      "findings": [{"file": r[0], "line": r[1], "severity": s, "message": "%s %s auth=%s" % r[2:]} for r, s in hi]}))
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
