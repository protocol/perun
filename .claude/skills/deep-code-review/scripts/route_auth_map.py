#!/usr/bin/env python3
"""route_auth_map.py [--paths] DIR -- heuristic lead-finder for HTTP handlers with no authentication evidence (CWE-306/862). Report-only, stdlib only.

Read this when you review an API surface for missing authentication or run the anonymous GET sweep in security-appsec.md: a handler that
mutates state and never touches an identity check is reachable by anyone, and generic linters do not see it. Run
`python3 -I route_auth_map.py DIR` (add `--paths` to list the GET and ANY routes, one per line). A row is a lead to verify, and SILENCE IS NOT PROOF
OF AUTHENTICATION: the scan only sees the call shapes listed below.

1. Inventory every handler: Next.js app/**/route.(ts|tsx|js|jsx|mjs) exported GET/POST/PUT/PATCH/DELETE (function, const, destructured or re-exported),
   pages/api/** (methods read from `req.method` checks, else ANY), "use server" exported async functions (METHOD ACTION), Express/Router/Hono/
   Fastify `<receiver>.get|post|put|patch|delete|all("/path", ...)`, FastAPI `@x.get(...)` and Flask `@x.route(..., methods=[...])` decorators.
2. One row per handler: `path:line: SEV: METHOD route auth=<evidence>`. Evidence, first hit wins: a call, decorator or `Depends(...)` naming an
   identity check (IDENTITY below: getServerSession, auth(), currentUser, requireAuth*, verify*, login_required...; a Depends/Security argument
   with user, auth, token, current, bearer, jwt, api_key, verify or login in it) or `req.user`/`current_user.`/`g.user` in the handler, in a
   same-file function it names, or at module level (a `.use(<auth>)` or Fastify addHook on the same receiver BEFORE the route counts, with its
   path prefix); else `token` (a header read in the handler and a comparison with a secret/token/api-key/password word on one line); else `middleware` (a Next
   middleware.ts/proxy.ts of the same app that names an identity check, or can answer 401/403 under any name (`status: 401`, `.status(403)`,
   `new Response("Unauthorized"`), and whose matcher covers the route, less any route a quoted `/path` in that file names as an allow-list entry
   (a trailing `(.*)`, `/*` or `/:name*` is dropped first; a path in the condition of an `if` that refuses is a scope check, not an entry)); else `none`.
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
paths, `.all("/x/*", guard)` as a gate (it reads as an ANY route), TS generics on a route call. A decorator above the route decorator
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
import json, os, re, sys

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
REFUSE = re.compile(r"""\bstatus[:(]\s*40[13]|Response\(\s*["'](?:Unauthorized|Forbidden)""")  # a middleware that can answer 401/403 gates what its matcher covers, whatever its check is called
END = re.compile(r"^\S", re.M)  # a JS span ends at the next line that starts at column 0 (its closing brace or the next declaration)
JSFN = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)|^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\b|function\b|\()", re.M)
PYFN = re.compile(r"^(?:@[^\n]*\n)*(?:async[ \t]+)?def[ \t]+(\w+)", re.M)  # decorators above a def belong to it, not to the module
PYSTR = re.compile(r'#[^\n]*|("""|\'\'\')(?:\\.|(?!\1).)*?\1|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
LIT = re.compile(r"""(["'`])(/[^"'`$]*)\1""")
GLOB = re.compile(r"(?:\(\.\*\)|/\*|/:\w+\*)$")  # the wildcard that ends a glob-style path literal: `/sign-in(.*)`, `/x/*`, `/x/:path*`
JOIN = re.compile(r"(?:[?:]|&&|\|\|)\s*|(?<!\s)\s+(?=[.?:]|&&|\|\|)")  # whitespace a statement runs over: after `? : && ||`, before `. ? : && ||`
HOOK = re.compile(r"""(["'])(?:onRequest|preHandler|preValidation|preParsing)\1""")
RCV = re.compile(r"\b(\w+)\s*(?::[^=\n]+)?=\s*(?:await\s+)?(?:new\s+)?(?:express|Router|Hono|Fastify|fastify|Elysia)\b")
PYDEC = re.compile(r"^([ \t]*)@\w+\.(%s|route)\(" % H, re.M)
PYDEF = re.compile(r"\bdef\s+\w+\s*\(")
JSPRE = re.compile(r"\.(?:%s|all)\(|use server" % H)


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


def refusing_ifs(m, mk):
    """(open, close) indexes of the parentheses of each `if (...)` in masked text m whose body can answer 401/403 (REFUSE in strings-kept mk).
    The body is the braced block (nested statements count, an `else` branch does not) or the one statement, which ends at the first `;` or line break outside brackets
    that does not carry it on (the next line starts with `.`, `?`, `:`, `&&` or `||`, or this one ends in `?`, `:`, `&&` or `||`: a ternary, logical or chained call)."""
    out = []
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
        if REFUSE.search(mk[s:e + 1]): out.append((a, b))
    return out


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
    lits = {GLOB.sub("", g[2]).rstrip("/") for g in LIT.finditer(mk) if not any(a < g.start() < b for a, b in sc)}
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


def call_hs(m, mk, hs, uses, gone):
    """Express/Router/Hono/Fastify `<receiver>.get|post|...(path, ...)` routes and positional `.use(...)` / `.addHook(...)` auth."""
    rcv = RECEIVERS | set(RCV.findall(m))
    for t in re.finditer(r"\b(\w+)\.(use|addHook|%s|all)\(" % H, m):
        r, k = t.group(1), t.group(2)
        op = t.end() - 1
        cl = close_of(m, op) if r in rcv else -1
        ps = parts(m[op + 1:cl], mk[op + 1:cl]) if cl > 0 else None
        if not ps: continue
        p0 = ps[0][1].strip()
        lit = LIT.fullmatch(p0)
        if k in ("use", "addHook"):
            gone.append((t.start(), cl + 1))
            if k == "addHook" and not HOOK.fullmatch(p0): continue
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
        e = re.compile(r"\n[ \t]{0,%d}(?=\S)" % len(t.group(1))).search(m, sc)
        end = e.start() if e else len(m)
        gone.append((t.start(), end))
        hs.append((t.start(), "|".join(meths), pyroute(pm.group(2)), [(t.start(), dm.start()), (dm.end() - 1, end)], None, None, None))


def analyze(rel, raw, mws):
    """[(path, line, METHOD, route, auth)] for one file."""
    py = rel.endswith(".py")
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
        lab = pre or use or next((g[0] for g in got if g[0]), None) or ("token" if any(g[1] for g in got) else None) or mw or "none"
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
    mws, rows, seen = {}, [], 0
    for rel in files:
        raw = read(root, rel) if MWF.fullmatch(os.path.basename(rel)) else None
        if raw is not None: mws[os.path.dirname(rel)] = mw_pats(mask(raw), mask(raw, True))
    for rel in files:
        raw = read(root, rel)
        if raw is None or not (NAPP.match(rel) or NAPI.match(rel) or (PYDEC if rel.endswith(".py") else JSPRE).search(raw)): continue
        seen += 1
        rows += analyze(rel, raw, mws)
    return sorted(rows), seen


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
