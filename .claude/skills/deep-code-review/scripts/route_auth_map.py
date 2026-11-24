#!/usr/bin/env python3
"""route_auth_map.py [--paths | --all] DIR -- heuristic lead-finder for HTTP handlers with no authentication evidence (CWE-306/862). Report-only, stdlib only.

Read this when you review an API surface for missing authentication or run the anonymous GET sweep in security-appsec.md: a handler that
mutates state and never touches an identity check is reachable by anyone, and generic linters do not see it. Run
`python3 -I route_auth_map.py DIR` (add `--privileged` to list privileged routes guarded by authentication alone, with no role, permission or admin check in the handler: admin path segments, role or permission changes, PUT/PATCH/DELETE on `/users/:id` and kin; the same run prints `OWN:` rows, authenticated NestJS writes by client-sent id or of a client-sent owner id whose member and called service method never compare the requester to the owner, and `OWN-CHECKED:` rows naming the check read where they do, see ownership(), and a `NOT-CHECKED:` row per file whose route-like decorator gave no route (the handlers under such decorators were not judged; other routes in the file were), then `MASS:` / `MASS-CHECKED:` rows (client body reaches an ORM write with a privileged field and no strip or pick, CWE-915), `IDMIX:` rows (access check on the path id, write `where` on a body id) and `CHILD:` rows (child row parent key from the body, no tie to the path parent), see authz_leads(); add `--paths` to list the GET and ANY routes, one per line, or `--all` to list every route and method as `METHOD /path file:line`). A row is a lead to verify, and SILENCE IS NOT PROOF
OF AUTHENTICATION: the scan only sees the call shapes listed below.

1. Inventory every handler: Next.js app/**/route.(ts|tsx|js|jsx|mjs) exported GET/POST/PUT/PATCH/DELETE (function, const, destructured or re-exported),
   pages/api/** (methods read from `req.method` checks, else ANY), "use server" exported async functions (METHOD ACTION), Express/Router/Hono/
   Fastify `<receiver>.get|post|put|patch|delete|all("/path", ...)` (TS type arguments allowed: `app.post<{ Body: Widget }>("/path", h)`), raw node:http / fetch-handler dispatch (a file that calls `createServer(`,
   `Deno.serve(`, `Bun.serve(` or defines `fetch(request) {`: one handler per `if (pathname === "/x" && req.method === "POST")` branch or `switch (pathname) { case "/x": ... }` case, either operand order,
   `url.pathname`, a `pathname` variable or `req.url`, a path literal or a same-file `const X = "/x"`; the method comes from the condition, the block or an enclosing `if`, and a branch with no method test, a branch in a class that is not `export default class` (a Durable Object), a `startsWith` or regex dispatch and an imported path constant are not seen; identity evidence before the dispatch in the enclosing function counts, an earlier branch's block does not), FastAPI `@x.get(...)` and Flask `@x.route(..., methods=[...])` decorators, NestJS `@Controller('prefix' | { path })` classes with `@Get|Post|Put|Patch|Delete|All|Head|Options('path' | ['a', 'b'])` members (`@UseGuards(X)` on the member or class is the evidence, a Throttler or RateLimit guard is not, `@Public()`-style decorators read `public`, `none` otherwise; a repo that wires a non-rate-limit `APP_GUARD` or `useGlobalGuards(` reads `global guard, unverified` for the unguarded ones; a constant path reads `{?}`); in those classes a ts-rest member (`@Api(server.route.x)`, `@TsRest(contract.x)`, `@TsRestHandler(c.x)`) is one row with the same guard evidence, METHOD and path read from the scanned contract (`name = x.router({ x: { method: 'PUT', path: '/v1/a/:id' } })`, a `${...}` reading `{?}`), else route `contract:x` (method `ANY` unless the entry names one; never guessed). A coverage line counts the files with a `@Get(`-style or ts-rest decorator this scan emitted no row for.
   `--paths` and `--all` also inventory (no auth evidence is judged for these; default mode prints one UNJUDGED line per file with state-changing Go, Spring, PHP or Django routes) Go (`HandleFunc|Handle("[METHOD ]/p")` incl. Go 1.22 patterns, chi/gin/echo `x.Get|GET|Any("/p")`, `x.Handle|Method|Add("GET", "/p")`,
   gorilla `.Methods(...)`, with `Group`/`PathPrefix` variables and chi `Route("/a", func...)` prefixes), Spring (`@Get|Post|Put|Patch|DeleteMapping`, `@RequestMapping` with `method=`, array paths, the class-level `@RequestMapping` prefix)
   Django urlconfs (`path|re_path|url`, method ANY, `include("pkg.urls")` prefixes resolved to a scanned file) and PHP (Symfony `#[Route(path, methods: [...])]` attributes and `@Route` annotations, with the class-level
   `#[Route]` prefix; Laravel `Route::get|post|put|patch|delete|any('/p', ...)`, no `prefix()`/`group()` nesting). Not seen there: DRF routers, `add_url_rule`, `include(module)`, Kotlin DSL, a prefix held in a variable.
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
3. SEV: HIGH when auth is none (or presence-check with no Authorization/Bearer credential forwarded in the handler) and the handler mutates (any method but GET; ANY and ACTION count as mutating), else INFO. A handler with no other evidence that reads the caller's cookie/header and forwards it as Authorization/Bearer reads `auth=forwarded` (INFO); a Bearer built from a server secret stays `none`.

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
pages/api handler can be over-flagged; not handled: Django urls,`.route(path).get()` chains, calls chained on a call result
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
after reviewing one, put a `route-auth-ok` comment on its line or the line above and the row reads `auth=public`. Edit IDENTITY and RECEIVERS for house guards; a handler that itself answers 401 (`status: 401`, `.status(401)`, `sendStatus(401)`, `abort(401)`, `HTTPException(status_code=401)`) reads auth=presence-check (a presence gate, not verification).

Output: one row per handler sorted by path then line, one JSON summary line (handlers, files, high, findings = the HIGH rows) and a stderr line
`heuristic; scanned N files with M handlers; ...`. `--paths` prints the unique GET and ANY routes (dynamic segments as `:name`) and no JSON; `--all` prints one `METHOD /path file:line` line per route and method and no JSON (the two flags exclude each other).
Exit 0 always on a readable DIR (report-only: never fails a build on its own), 2 on usage error. Reads files only; writes nothing.
ponytail: text scan on the tenant_scope_check.py masker, not an AST -- regex literals with quotes can desync it. Upgrade to a parser if
precision matters more.
"""
import json, os, posixpath, re, sys

sys.dont_write_bytecode = True  # `python3 -I` drops this dir from sys.path: add it for the sibling import and leave no __pycache__ behind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tenant_scope_check import SKIP_DIR, close_of, lineno, mask, parts  # noqa: E402

IDENTITY = (  # configurable (require* takes Auth, User, Session, Member, Account...): a call, decorator or (in `.use`/route middleware) bare name like these counts as an identity check
    "getServerSession", "getSession", "getToken", "getAuth", "auth", "currentUser", "getUser", "getCurrentUser",
    r"require(?:Auth|User|Session|Login|Admin|Member|Account|Viewer|Principal)\w*", "withAuth", r"auth(?:Middleware|Guard)", r"authenticate\w*", r"authorize\w*",
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
REQ = re.compile(r"\b((?:req|request)\.(?:user|auth|member(?!\s*=(?!=)))|current_user(?=\.)|g\.user)\b")  # `current_user.` only: an import of the name is not a check
CMP = re.compile(r"[!=]=|timingSafeEqual|compare_digest")
SEC = re.compile(r"secret|token|api.?key|password", re.I)
HDR = re.compile(r"header|authorization", re.I)
TEST = re.compile(r"\.(?:test|spec)\.|(?:^|/)(?:__tests__|tests?|e2e)/|(?:^|/)(?:test_[^/]*|[^/]*_test|conftest)\.py")
NAPP = re.compile(r"(?:(.*)/)?app/(?:(.*)/)?route\.(?:[tj]sx?|mjs)$")
NAPI = re.compile(r"(?:(.*)/)?pages/(api/.+)\.(?:[tj]sx?|mjs)$")
MWF = re.compile(r"(?:middleware|proxy)\.[jt]s")
REFUSE = re.compile(r"""\bstatus[:(]\s*40[13]|Response\(\s*["'](?:Unauthorized|Forbidden)|\.code\(\s*40[13]|\bstatusCode\s*=\s*40[13]|\.(?:unauthorized|forbidden)\(""")  # a middleware or hook that can answer 401/403 gates what it covers, whatever its check is called
FWD = re.compile(r"""(?:^|[{,])\s*["']?authorization["']?\s*:|Bearer\s*\$\{|Bearer\s*["'`]\s*\+|(?<!res)(?<!response)\.set\(\s*["']authorization""", re.I | re.M)  # a credential forwarded in an outbound call: the upstream verifies it (object-key position only, so a string "authorization: none" is no forward; res.set is a response header)
READ = re.compile(r"""(?:\(await\s+)?(?:cookies|headers)\(\)\)?\s*\.get\([^()]*\)|\bcookieStore\.get\([^()]*\)|\bget(?:Header|Cookie)\([^()]*\)|\breq(?:uest)?\.(?:headers|cookies)(?:\.get\([^()]*\)|\.\w+|\[[^\]]*\])?""")  # the forms of reading the caller's own cookie/header; a trailing ?.value is allowed by pure()
SECRET = re.compile(r"process\.env|import\.meta\.env|Deno\.env|\benv\.|\bconfig\.|\bsettings\.|\bget(?:Env|Secret)\(")  # extra guard on top of the allowlist in pure()
def vexpr(t, i, nl=True):
    """The expression that starts at t[i]: up to the first , ; or closer at bracket depth 0 (a newline also ends it when nl is false and the next line does not continue it). Strings and balanced template literals are skipped whole."""
    d, q, pend, j = 0, None, [], i
    while j < len(t):
        c = t[j]
        if q:
            if c == "\\": j += 1
            elif q == "`" and t[j:j + 2] == "${": pend.append(d); d += 1; q = None; j += 1
            elif c == q: q = None
        elif c in "'\"`": q = c
        elif c in "([{": d += 1
        elif c in "}])":
            if d == 0: return t[i:j]
            d -= 1
            if pend and pend[-1] == d: pend.pop(); q = "`"
        elif d == 0 and c in ",;": return t[i:j]
        elif d == 0 and c == "\n" and not nl and not re.match(r"\s*[?|&+.:*/<>=-]", t[j + 1:]): return t[i:j]
        j += 1
    return t[i:]
def forwarded(t, action=False):
    """True when every credential forwarded as Authorization/Bearer (or fed to a *header* helper as token/auth) is provably the caller's own. Each full value expression must hold nothing but caller reads (cookies().get, headers().get, req.headers, getHeader/getCookie; ?., .value, a `?? ''` literal), string literals and allowed variables, with at least one read. An allowed variable is a parameter of a server action's own signature or one whose every assignment is itself such an expression; any other identifier, call, ternary or operator rejects it, so a server secret, a helper parameter or a mixed value stays HIGH."""
    sig = action and re.match(r"[^(){}]*\(([^()]*)\)", t)  # only a server action's arguments are caller-supplied; a route handler's are the request
    nm = lambda v: r"(?<![\w$.])" + re.escape(v) + r"(?![\w$])"
    seen = set()
    def fed(v):
        if v in seen: return False
        seen.add(v)
        inits = [vexpr(t, m.end(), False) for m in re.finditer(nm(v) + r"\s*[-+*/%|&?]{0,2}=(?![=>])", t)]
        r = all(pure(x) for x in inits) and (bool(inits) or bool(sig and re.search(nm(v), sig.group(1))))
        seen.discard(v)
        return r
    def pure(e):
        if SECRET.search(e): return False
        e = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", "¤", e)
        e = READ.sub("§", e)
        e = re.sub(r"(?<![\w$.])Bearer(?![\w$])", "", e)
        e = re.sub(r"(?<![\w$.§])(?:[A-Za-z_]|\$(?=\w))[\w$]*", lambda m: "§" if fed(m.group()) else "!", e)
        e = re.sub(r"\??\.value|\?\?|\|\|", "", e)
        return "§" in e and re.fullmatch(r"[\s+`${}§¤]*", e) is not None
    vals = []
    for m in FWD.finditer(t):
        k = m.end() + len((re.match(r"[\"']?\s*,", t[m.end():]) or [""])[0])
        if t[m.start():m.end()].lower().find("bearer") >= 0: k = max(t.rfind(c, 0, m.start()) for c in "'\"`")
        vals.append(vexpr(t, k))
    vals = [pure(x.strip()) for x in vals] + [fed(v) for v in re.findall(r"\b\w*header\w*\(\s*(\w*(?:token|auth|jwt)\w*)\b", t, re.I)]
    return bool(vals) and all(vals)
EARLY401 = re.compile(r"""\bstatus\s*(?::|\()\s*401\b|sendStatus\(\s*401|abort\(\s*401|HTTPException\(\s*status_code\s*=\s*401""")  # a handler that answers 401 itself (a BFF forwarding an Authorization header it checked) has identity evidence
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
PNAME = r"(?<![\w$])(?:[\w$]+\.)*(?:pathname|path|url)\b"  # `pathname`, `path` or `url`, bare or as the last segment (`url.pathname`, `req.url`), as written in raw dispatch
PCMP = re.compile(PNAME + r"""\s*={2,3}\s*(?:(["'`])(?P<a>/[^\s"'`$]*)\1|(?P<b>[\w$]+)(?![\w$.(\[]))|(?:(["'`])(?P<c>/[^\s"'`$]*)\4|(?<![\w$.])(?P<d>[\w$]+))\s*={2,3}\s*""" + PNAME)  # `pathname === "/x"` in either order, or against a same-file `const X = "/x"`
PCONST = re.compile(r"""\bconst[ \t]+([\w$]+)\s*(?::[^=\n]+)?=\s*(["'`])(?P<p>/[^\s"'`$]*)\2""")
PCASE = re.compile(r"""\bcase\s+(["'`])(?P<p>/[^\s"'`$]*)\1\s*:""")
FETCH = r"\bfetch\s*\([^)]*\)\s*(?::[^{;=]*)?\{"  # a `fetch(request, env) {` method or function definition, return type allowed
SRV = re.compile(r"\bcreateServer\s*\(|\bDeno\.serve\(|\bBun\.serve\(|addEventListener\(\s*[\"']fetch|export\s+(?:async\s+)?function\s+fetch\b|^[ \t]+(?:async[ \t]+)?" + FETCH, re.M)  # a file that creates an http server or defines a fetch handler
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


NEST = re.compile(r"@Controller\s*\(")
NESTM = re.compile(r"@(Get|Post|Put|Patch|Delete|All|Head|Options)\s*\(")
NESTG = re.compile(r"@UseGuards\s*\(")
NESTSTR = re.compile(r"""(["'`])([^"'`]*)\1""")
NESTPUB = re.compile(r"@(?:Public|IsPublic|SkipAuth|NoAuth|AllowAnonymous|AllowUnauthenticated)\s*\(")
CLASSKW = re.compile(r"\bclass\b")
NESTGLOBAL = re.compile(r"\bAPP_GUARD\b|\buseGlobalGuards\s*\(")
NESTRATE = re.compile(r"(?![\w$.]*(?:auth|jwt|session|role|permission))[\w$.]*(?:throttl|rate_?limit)", re.I)  # `.match`: a rate-limit guard is no identity check, unless its name also says Auth, Jwt, Session, Role or Permission


DECOCALL = re.compile(r"@[\w$.]+\s*\(")  # a decorator call `@Name(`: nest_hs keeps only these from the text before a class, so an import never reads as a class guard
NESTDECO = re.compile(r"@[\w$.]+\s*(?:<[^()]*)?\s*\(?")  # `@Name`, optionally spaced, with a generic argument (nested `<A<B>>` too: skipped up to the next paren), and its opening paren
TSR = re.compile(r"@(?:Api|TsRest|TsRestHandler)\s*\(\s*([\w$]+(?:\s*\.\s*[\w$]+)*)\s*[,)]")  # a ts-rest member decorator whose argument is a contract route reference; `@TsRest({ jsonQuery })` options are not
TSRSRV = re.compile(r"\b([\w$]+)\s*=\s*(initNestServer|nestControllerContract)\s*\(\s*([\w$]+)\s*\)")  # `const server = initNestServer(contract)`: `server.route.x` names contract.x
TSRDEF = re.compile(r"\b([\w$]+)\s*=\s*[\w$]+\.router\s*\(\s*\{")
TSRC = {}  # ts-rest contract name -> {key: (METHOD or None, path or None)}, None when two definitions share the name; filled by scan()
ROUTEDECO = re.compile(NESTM.pattern + "|" + TSR.pattern)  # for the coverage line: a decorator that should give a row


def fields(m, a, b):
    """{key: (start, end)} of the depth-0 `key: value` pairs in the object body m[a:b] (masked): a value runs to the next depth-0 comma, so a key of a nested object is not the body's own; quoted keys are not read."""
    f, d = [], 0
    if b < a: return {}
    for c in m[a:b]:
        d -= c in ")]}"
        f.append(c if d == 0 else " ")
        d += c in "([{"
    f, out = "".join(f), {}
    for x in re.finditer(r"(?:^|,)\s*([\w$]+)\s*:", f):
        z = f.find(",", x.end())
        out.setdefault(x[1], (a + x.end(), a + (z if z >= 0 else len(f))))
    return out


def tsval(s):
    """The value of a string-literal expression s (strings kept), each `${...}` of a template reading `{?}`; None for anything else (a variable, a concatenation, a call)."""
    s = re.sub(r"\s+as\s+const$", "", s.strip())
    t = NESTSTR.fullmatch(re.sub(r"\$\{[^}]*\}", "{?}", s) if s.startswith("`") else s)
    return t[2] if t else None


def ts_contracts(m, mk):
    """{name: {key: (METHOD or None, path or None)}} of the ts-rest contracts `name = x.router({ key: { method: 'PUT', path: '/a/:id' } }, { pathPrefix: '/v1' })` in masked text m (mk: strings kept).
    Only an entry whose value is an object literal is read, and only its own depth-0 `method:` and `path:` (a `path` field of a body schema is not the route); a path that is no string literal is None,
    a `pathPrefix` that is none reads `{?}`. A nested router (`users: c.router(...)`, a router variable) is not entered, so its routes stay unresolved.
    A name defined twice in m maps to None (unresolved), as scan() does for a name defined in two files."""
    out = {}
    for t in TSRDEF.finditer(m):
        b = t.end() - 1; e = close_of(m, b)
        if e < 0: continue
        q, pfx = re.compile(r"\s*,\s*\{").match(m, e + 1), ""
        px = q and fields(m, q.end(), close_of(m, q.end() - 1)).get("pathPrefix")
        if px: pfx = tsval(mk[px[0]:px[1]]) or "{?}"
        rs = {}
        for k, (s, z) in fields(m, b + 1, e).items():
            s += len(m[s:z]) - len(m[s:z].lstrip())
            if m[s:s + 1] != "{": continue
            f = fields(m, s + 1, close_of(m, s))
            mt, p = ((tsval(mk[slice(*f[n])]) if n in f else None) for n in ("method", "path"))
            rs[k] = (mt.upper() if mt and mt.upper() in VERBS + ("HEAD", "OPTIONS") else None, None if p is None else pfx + p)
        out[t[1]] = None if t[1] in out else rs
    return out


def ts_route(chain, srv):
    """(METHOD, path) a ts-rest decorator argument names: `server.route.x` (server from initNestServer) or `c.x` (nestControllerContract, or the contract itself) looked up in TSRC;
    a name defined twice, a nested key, a whole router or a non-literal path reads route `contract:<key>`, a non-literal method `ANY` (method unknown, so a state change is not ruled out). Never guessed by key alone.
    Limit: the lookup is by contract name, not by import, so a same-named contract from an unscanned package binds by name to the scanned one."""
    ns = re.split(r"\s*\.\s*", chain)
    s = srv.get(ns[0])
    name, keys = (s[1], ns[2:] if s[0] == "initNestServer" and ns[1:2] == ["route"] else ns[1:]) if s else (ns[0], ns[1:])
    mt, p = (TSRC.get(name) or {}).get(keys[0], (None, None)) if len(keys) == 1 else (None, None)
    return mt or "ANY", p if p is not None else "contract:" + ".".join(keys or ns)


def nest_deco_end(m, i, j):
    """End of the run of decorators (`@Name(...)`) that starts at m[i:j] after whitespace: where the member signature begins, so a `@UseGuards(` or `@Public(` inside a body or parameter list is not a member decorator."""
    p = i
    while True:
        while p < j and m[p].isspace(): p += 1
        t = NESTDECO.match(m, p, j)
        if not t: return p
        p = t.end()
        if t[0].endswith("("): p = max(close_of(m, p - 1), p) + 1


def nest_guards(m, i, j):
    """Names of the `@UseGuards(...)` arguments in masked m[i:j] that are not rate-limit guards, in order (`AuthGuard('jwt')` reads AuthGuard; `new X()` reads `new`, X)."""
    out = []
    for t in NESTG.finditer(m, i, j):
        cl = close_of(m, t.end() - 1)
        out += [n for n in re.findall(r"(?<![\w$.])[A-Za-z_$][\w$.]*", m[t.end():cl] if cl > 0 else "") if not NESTRATE.match(n)]
    return out


def nest_guard(m, i, j):
    """Name of the first nest_guards() argument in masked m[i:j], else None."""
    return next(iter(nest_guards(m, i, j)), None)


def app_roots(rel, raw):
    """App-root directories a manifest-ish file marks: its own dir for `package.json`, `nest-cli.json`, `main.ts`, `tsconfig.app.json`; plus each `projects.*.root` of a `nest-cli.json` (monorepo mode)."""
    d, out = os.path.dirname(rel), {os.path.dirname(rel)}
    if os.path.basename(rel) == "nest-cli.json":
        try: ps = json.loads(raw).get("projects") or {}
        except ValueError: ps = {}
        for v in ps.values() if isinstance(ps, dict) else ():
            if isinstance(v, dict) and isinstance(v.get("root"), str): out.add("" if (q := posixpath.normpath(posixpath.join(d, v["root"]))) == "." else q)
    return out


def app_of(rel, mf):
    """The app a file belongs to: its nearest directory above (set mf, from app_roots) marking an app, else "" (the repo root); a global guard reaches only controllers of its own app.
    ponytail: a workspace lib with its own package.json that exports an APP_GUARD module is its own "app", so it does not reach the apps importing it; those routes read auth=none (HIGH), the safe direction. A nested `main.ts` or `tsconfig.app.json` (`src/cli`) is likewise its own app, which a global guard does not reach (safe)."""
    d = os.path.dirname(rel)
    while d and d not in mf: d = os.path.dirname(d)
    if d: return d
    ps = rel.split("/")[:-1]  # no marker below the root: the dir above the deepest `src/` (apps/a/src/x.ts -> apps/a), so sibling apps stay apart
    return "/".join(ps[:len(ps) - ps[::-1].index("src") - 1]) if "src" in ps else ""


def nest_global(m):
    """True when masked text m wires an auth-looking global guard: a class named by `APP_GUARD` (`useClass|useExisting|useValue: X`) or `useGlobalGuards(new X())` that is not a rate-limit guard."""
    names = []
    for t in NESTGLOBAL.finditer(m):
        if t[0] == "APP_GUARD":  # the whole enclosing `{ provide, useClass }` object, whichever order
            a, d = t.start() - 1, 0
            while a >= 0 and (d or m[a] != "{"): d += (m[a] == "}") - (m[a] == "{"); a -= 1
            cl = close_of(m, a) if a >= 0 else -1
            names += re.findall(r"(?:useClass|useExisting|useValue)\s*:\s*(?:new\s+)?([\w$.]+)", m[a:cl] if cl > 0 else "")
        else:
            cl = close_of(m, t.end() - 1)
            names += re.findall(r"(?<![\w$.])[A-Za-z_$][\w$.]*", m[t.end():cl])
    return any(n != "new" and not NESTRATE.match(n) for n in names)


def nest_paths(a):
    """Paths named by the arguments a (strings kept) of a Controller or verb decorator: a string, an array of strings (all of them), or the `path:` key of an options object; empty is [""];
    a part that is no string literal (a constant) reads `{?}`, so the row names an unresolved path, never the prefix alone."""
    a = a.strip()
    if a.startswith("{"):
        x = re.search(r"\bpath\s*:\s*(\[[^\]]*\]|[^,}]*)", a)
        a = x[1].strip() if x else ""
    els = [e.strip() for e in a.strip("[] \n").split(",") if e.strip()]
    return [(NESTSTR.fullmatch(e) or [0, 0, "{?}"])[2] for e in els] or [""]


def nest_hs(m, mk, hs, gone, glob=False):
    """NestJS `@Controller('prefix')` classes: each `@Get|Post|Put|Patch|Delete|All|Head|Options('path')` member is a route `/prefix/path` (an array of paths gives one route each; `{ path }` object form read).
    Evidence: `@UseGuards(X)` on the member or on the class (a decorator above or below `@Controller`, never reaching back past the previous class), a rate-limit guard (Throttler, RateLimit) excluded; else a `@Public()`-style
    decorator reads `public`; else, when the repo wires an auth-looking global guard (`APP_GUARD`, `useGlobalGuards(`), `global guard, unverified`.
    ponytail: guards are matched by presence, never by what the guard class checks; a guard built inline or by a factory reads by its first identifier. `setGlobalPrefix(...)` and URI versioning
    (`enableVersioning`, `version:` in `@Controller`/`@Version`) are not applied: a row's path is the controller prefix plus the member path only.
    A global guard reaches only controllers of its own app (see app_of). A ts-rest member decorator (`@Api|TsRest|TsRestHandler(ref)`) is one row with the same evidence, its METHOD and path from ts_route();
    a `contract:<key>` row is not joined to the controller prefix.
    Returns {route pos: (class decorator text, {member or parameter name: its type name})} for ownership()."""
    prev, srv, ctx = 0, {t[1]: t.groups()[1:] for t in TSRSRV.finditer(m)}, {}
    for t in NEST.finditer(m):
        op = t.end() - 1; cl = close_of(m, op)
        k = CLASSKW.search(m, cl)
        k = k.start() if k else -1
        b = m.find("{", k) if k > 0 else -1
        e = close_of(m, b) if b > 0 else -1
        if e < 0: continue
        pres = nest_paths(mk[op + 1:cl])
        w = max(m.rfind("\n}", 0, t.start()), m.rfind(";", 0, t.start()), prev)
        cg, cp = nest_guard(m, w, k), NESTPUB.search(m, w, k)
        cx = ("\n".join(mk[d.start():close_of(m, d.end() - 1) + 1] for d in DECOCALL.finditer(m, w, k)), dict(reversed(re.findall(r"\b([\w$]+)\s*[?!]?:\s*([\w$]+)", m[b:e]))))  # the first `name: Type` wins: the constructor field, not a later parameter of the same name
        prev = e + 1
        gone.append((t.start(), e + 1))
        i = b + 1
        while i < e:  # one class member per pass: ends at the `}` or `;` that closes it at depth 0
            j, d = i, 0
            while j < e:
                c = m[j]
                d += (c in "([{") - (c in ")]}")
                if d == 0 and c in ";}": break
                j += 1
            dj = nest_deco_end(m, i, j)
            if NESTM.search(m, i, dj) or TSR.search(m, i, dj):  # a route member ends at its body's `}`, not at the one of a return type (`): Promise<{ ok: boolean }> {`)
                p = m.find("(", dj); pc = close_of(m, p) if p >= 0 else -1
                o = body_open(m, pc) if pc > 0 else -1
                if 0 < o < e: j = max(j, close_of(m, o))
            g, mp = nest_guard(m, i, dj), NESTPUB.search(m, i, dj)  # a member guard or member @Public beats the class guard
            g = g or (None if mp else cg)
            lab = "UseGuards(%s)" % g if g else "public" if cp or mp else "global guard, unverified" if glob else None
            for r in NESTM.finditer(m, i, j):
                o = r.end() - 1; c2 = close_of(m, o)
                for y in nest_paths(mk[o + 1:c2] if c2 > 0 else ""):
                    for p in pres: hs.append((r.start(), "ANY" if r[1] == "All" else r[1].upper(), join(p, y), [(i, j)], lab, None, None))
                ctx[r.start()] = cx
            for r in TSR.finditer(m, i, dj):  # ts-rest applies Nest's own verb decorator, so the controller prefix joins as above
                mt, y = ts_route(r[1], srv)
                for p in [None] if y.startswith("contract:") else pres: hs.append((r.start(), mt, y if p is None else join(p, y), [(i, j)], lab, None, None))
                ctx[r.start()] = cx
            i = j + 1
    return ctx


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


def raw_hs(m, mk, hs, gone):
    """Raw node:http / fetch-handler dispatch in a file that creates an http server or exports a fetch handler (SRV): one handler per `if (pathname === "/x" && req.method === "POST")` branch
    (either order, `==` or `===`, `url.pathname`, a `pathname` variable or `req.url`) and per `case "/x":` of a `switch (pathname)`. The method is the one the condition, the block or an enclosing
    `if` tests; a branch with no method test is skipped (skip rather than guess), and so is a branch inside a class that is not `export default class` (a Durable Object `fetch` is internal; a default-exported WorkerEntrypoint class and an `export default { fetch }` object stay public). The span is the block. Evidence before the dispatch in the enclosing function counts; an earlier branch's block does not.
    ponytail: fall-through `case "/a": case "/b":`, a `switch (req.method)` nested in a case and `fetch(`/`createServer(` inside a string literal are not read; any non-default class is read as internal (a named-export WorkerEntrypoint is missed); a block testing two methods is one `GET|POST` handler; `startsWith` dispatch, a router table and a method-first `switch` are not read."""
    if not SRV.search(m): return
    L, br, cs = list(ifs(m)), [], {t[1]: t["p"] for t in PCONST.finditer(mk)}  # br: (position, route, block span, condition span)
    for a, b, s, e in L:
        for t in PCMP.finditer(mk, a + 1, b):
            r = t["a"] or t["c"] or cs.get(t["b"] or t["d"])
            if r: br.append((a, r, (s, e + 1), (a, b)))
    for t in re.finditer(r"\bswitch\s*\(\s*" + PNAME + r"\s*\)\s*\{", mk):
        sc = close_of(mk, t.end() - 1)
        se = sc if sc > 0 else len(mk)  # an unclosed switch runs to the end of the file
        for c in PCASE.finditer(mk, t.end(), se):
            n = re.compile(r"\bcase\s|\bdefault\s*:").search(mk, c.end(), se)
            br.append((c.start(), c["p"], (c.end(), n.start() if n else se), (0, 0)))
    if not br: return
    fns = [(t.end(), close_of(m, t.end() - 1)) for t in re.finditer(r"\bcreateServer\s*\(|" + FETCH, m)] + list(decls(m).values())
    cls = [(t.end(), close_of(m, t.end() - 1)) for t in re.finditer(r"^(?!export\s+default\s+class\b)(?:export\s+)?(?:abstract\s+)?class\b[^{;]*\{", m, re.M)]  # classes that are not `export default class`
    br = [x for x in br if not any(a < x[0] < b for a, b in cls)]  # a Durable Object class fetch() is reachable only through a Worker stub
    hot = [f for f in fns if any(f[0] < x[0] < f[1] for x in br)]
    gone.extend((s, e + 1) for a, b, s, e in L if any(f[0] < s < f[1] for f in hot))  # an `if` body in a dispatching function is evidence only for its own branches, not module-level for all
    for pos, route, sp, cd in br:
        ms = methods(mk[cd[0]:cd[1]]) or methods(mk[sp[0]:sp[1]])
        up = [(s, a, b) for a, b, s, e in L if s < pos and sp[1] <= e + 1 and methods(mk[a:b])]  # enclosing ifs that test a method
        if not ms and up:
            a, b = max(up)[1:]  # the innermost: a `!==` test there gives no method
            ms = methods(mk[a:b].replace("!=", "#"))
        if not ms: continue
        st = max((a for a, b in fns if a < pos < b), default=0)
        gone.append(sp)
        hid = blank(m, [(s, e + 1) for a, b, s, e in L if not s <= pos < e] + [x[2] for x in br])  # only the function's top level and enclosing ifs are evidence
        hs.append((pos, "|".join(ms), route, [sp], ident(hid[st:max(pos, cd[1])]), None, None))


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


EXTRA = {}  # (file, line) -> (router path prefix, router-level guard text, router-level identity gate), filled by analyze() for --privileged


def jsctx(m, mk, fn):
    """[(receiver, pos, path, text)] per `<receiver>.use(...)` call: its arguments and the bodies of the functions they name."""
    out = []
    for t, op, cl, ps in callargs(m, mk, "use", RECEIVERS | set(RCV.findall(m))):
        lit = LIT.fullmatch(ps[0][1].strip())
        txt = mk[op:cl + 1]
        out.append((t.group(1), t.start(), lit and lit.group(2).rstrip("*/") or "", "\n".join([txt] + [mk[a:b] for w in set(re.findall(r"[\w$]+", txt)) if w in fn for a, b in [fn[w]]])))
    return out


def pyctx(m, mk):
    """{receiver: [prefix, guard text, gated]} for the routers, blueprints and apps built in one Python file: `prefix=` / `url_prefix=`, the constructor, `include_router` and
    `register_blueprint` arguments (dependencies=[...] is guard text), and `@x.before_request` bodies (gated when one aborts or raises)."""
    c = {}
    for t in re.finditer(r"\b(\w+)\s*=\s*(?:\w+\.)?(?:APIRouter|Blueprint|FastAPI|Flask)\(", m):
        op = t.end() - 1; cl = close_of(m, op)
        a = mk[op:cl + 1] if cl > 0 else ""
        c[t.group(1)] = ["", a, bool(re.search(r"Depends|Security", a))]
        x = re.search(r"\b(?:url_)?prefix\s*=\s*([\"'])([^\"']*)\1", a)
        if x: c[t.group(1)][0] = x.group(2)
    for t in re.finditer(r"\.(?:include_router|register_blueprint)\(\s*(\w+)", m):
        op = m.rfind("(", 0, t.end()); cl = close_of(m, op)
        a = mk[op:cl + 1] if cl > 0 else ""
        e = c.setdefault(t.group(1), ["", "", False])
        x = re.search(r"\b(?:url_)?prefix\s*=\s*([\"'])([^\"']*)\1", a)
        if x: e[0] = x.group(2) + e[0]
        e[1] += a; e[2] = e[2] or bool(re.search(r"Depends|Security", a))
    for t in re.finditer(r"^( *)@(\w+)\.before_(?:app_)?request\s*\n", m, re.M):
        d = PYDEF.search(m, t.end()); sc = close_of(m, d.end() - 1) if d else -1
        b = mk[d.start():outdent(m, sc, t.end(1) - t.start(1))] if sc > 0 else ""
        e = c.setdefault(t.group(2), ["", "", False])
        e[1] += b; e[2] = e[2] or bool(re.search(r"\babort\(|\braise\b|\b40[13]\b|redirect|Unauthorized|Forbidden", b))
    return c


def priv_ctx(ctx, rcv, route, pos, fn, mk):
    """(prefix, guard text, identity gate) the receiver's router-level setup adds to one handler: Python from pyctx, JS from the `.use(...)` calls declared before the route."""
    if isinstance(ctx, dict):
        e = ctx.get(rcv)
        return tuple(e) if e else ("", "", False)
    gt = "\n".join(t for r, p, u, t in ctx if r == rcv and p < pos and (route == u or route.startswith(u + "/")))
    return "", gt, False


NESTSAFE = set()  # (file, line) of NestJS @Head/@Options members: a safe method, never HIGH; other frameworks keep the GET-only rule (none emits a HEAD/OPTIONS row today: Express/Fastify/Next/Flask read VERBS only, Go's HEAD|OPTIONS rows never reach scan())
FWDROWS = set()  # (file, line) of handlers whose span forwards an Authorization/Bearer credential
BODY = {}  # (file, line) -> the handler's own and helper text with strings kept, filled by analyze() for --privileged
NESTCTX = {}  # (file, line) of a NestJS member -> (class decorator text, {name: type name}), filled by analyze() for --privileged's ownership rows
CLS = {}  # @Injectable class name -> the files that define it (a name two files define reads both), filled by scan() for --privileged's ownership rows
SKIPPED = []  # (file, first line) of each JS/TS file with a route-like decorator on a line no row came from, filled by scan()


def analyze(rel, raw, mws, sites=None, hooks=None, glob=False):
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
        n0 = len(hs)
        nctx = nest_hs(m, mk, hs, gone, glob)
        nestpos = {h[0] for h in hs[n0:] if h[1] in ("HEAD", "OPTIONS")}
        call_hs(m, mk, hs, uses, gone)
        raw_hs(m, mk, hs, gone)
    ctx = pyctx(m, mk) if py else jsctx(m, mk, fn)  # for --privileged only
    hide = gone + list(fn.values())
    mod = ident(blank(m, hide))  # module level: what is outside every handler, function definition and `.use` call; scanned once, per handler it would make a file with many routes quadratic
    out = []
    for pos, meth, route, spans, pre, rcv, mwb in hs:
        ln = lineno(m, pos)
        own = "\n".join(m[a:b] for a, b in spans)
        BODY[(rel, ln)] = "\n".join(mk[a:b] for a, b in spans + [fn[w] for w in set(re.findall(r"[\w$]+", own)) if w in fn])  # for --privileged only
        r_ = rcv or (re.compile(r"\s*@(\w+)\.").match(m, pos) or [0, None])[1]
        pfx, gt, gate = priv_ctx(ctx, r_, route, pos, fn, mk)
        EXTRA[(rel, ln)] = (pfx, gt, gate)
        if any(FWD.search(mk[a:b]) for a, b in spans): FWDROWS.add((rel, ln))
        if not py and pos in nestpos: NESTSAFE.add((rel, ln))
        if not py and pos in nctx: NESTCTX[(rel, ln)] = nctx[pos]
        got = [(ident(m[a:b]), tok(mk[a:b])) for a, b in spans + [fn[w] for w in sorted(set(re.findall(r"[\w$]+", own))) if w in fn]] + [(mod, False)]
        use = next((u[3] for u in uses if u[0] == rcv and u[1] < pos and (route == u[2] or route.startswith(u[2] + "/"))), None)
        pats = mws.get(mwb) if mwb is not None else None
        mw = "middleware" if pats and any(x.fullmatch(route) for x in pats) else None
        mine = [h for p, q, h in hooks.get(rcv, ()) if p < pos < q]  # hooks on this route's receiver declared before it, in a block that holds it
        lab = pre or use or next((g[0] for g in got if g[0]), None) or ("token" if any(g[1] for g in got) else None) or mw or ("root-hook" if gated(sites, route) or meth != "GET" and gated([("", mine)], route) else None) or ("presence-check" if any(EARLY401.search(mk[a:b]) for a, b in spans) else None) or ("forwarded" if forwarded("\n".join(mk[a:b] for a, b in spans + [fn[w] for w in set(re.findall(r"[\w$]+", own)) if w in fn]), meth == "ACTION") else None) or "none"
        if any(MARK in l for l in rl[max(0, ln - 2):ln]): lab = "public"
        out.append((rel, ln, meth, route, lab))
    return out


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8-sig", errors="replace") as f: return f.read()
    except OSError: return None


def scan(root):
    files, mf = [], set()
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIR)
        for f in fn:
            if f in ("nest-cli.json", "package.json", "main.ts", "tsconfig.app.json"):
                rl = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
                mf |= app_roots(rl, read(root, rl) if f == "nest-cli.json" else "")
        for f in sorted(fn):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            if f.endswith(EXT) and not TEST.search(rel): files.append(rel)
    known = set(files)
    NESTSAFE.clear(); FWDROWS.clear()
    NESTCTX.clear(); CLS.clear()
    TSRC.clear()
    glob, mws, rows, todo, cov, own, deco = set(), {}, [], [], {}, {}, {}  # todo: files with handlers; cov: file -> wiring() sites that wire it; own: file -> its own wiring() hooks; deco: file -> route-like decorator lines
    for rel in files:
        raw = read(root, rel) if MWF.fullmatch(os.path.basename(rel)) else None
        if raw is not None: mws[os.path.dirname(rel)] = mw_pats(mask(raw), mask(raw, True))
    for rel in files:
        raw = read(root, rel)
        if raw is None: continue
        if NESTGLOBAL.search(raw) and nest_global(mask(raw, True)): glob.add(app_of(rel, mf))
        if not rel.endswith(".py") and "@Injectable" in raw:
            for n in set(INJ.findall(raw)): CLS.setdefault(n, []).append(rel)
        if not rel.endswith(".py") and ".router" in raw:
            for n, v in ts_contracts(mask(raw), mask(raw, True)).items(): TSRC[n] = None if n in TSRC else v
        if not rel.endswith(".py") and ROUTEDECO.search(raw):
            mm = mask(raw)
            deco[rel] = sorted({lineno(mm, x.start()) for x in ROUTEDECO.finditer(mm)})
        if ".register" in raw or "addHook" in raw:
            own[rel], sites = wiring(rel, raw, known)
            for f, site in sites: cov.setdefault(f, []).append(site)
        if NAPP.match(rel) or NAPI.match(rel) or (PYDEC if rel.endswith(".py") else JSPRE).search(raw) or not rel.endswith(".py") and (NEST.search(raw) or SRV.search(raw)): todo.append((rel, raw))
    for rel, raw in todo: rows += analyze(rel, raw, mws, cov.get(rel), own.get(rel), app_of(rel, mf) in glob)
    got = {(r[0], r[1]) for r in rows}
    SKIPPED[:] = [(f, l[0]) for f, ls in sorted(deco.items()) for l in [[x for x in ls if (f, x) not in got]] if l]
    return sorted(rows), len(todo)


def coverage():
    """The coverage line for the last scan(): how many JS/TS files hold a route-like decorator (`@Get|Post|...(`, a ts-rest `@Api|TsRest|TsRestHandler(ref)`) on a line with no row, and the first few."""
    return "coverage: %d file(s) with route-like decorators this scan skipped%s" % (len(SKIPPED), "".join(" %s:%d" % (cl(f), ln) for f, ln in SKIPPED[:3]) + (" ..." if len(SKIPPED) > 3 else ""))


GOCH = r'((?:\.(?:With|Use)\((?:[^()]|\([^()]*\))*\)|\.(?:Group|PathPrefix)\(\s*"[^"]*"\s*\)|\.Subrouter\(\))*)'  # a call chain between receiver and route call: x.With(mw).Group("/a").Get(...)
GOCALL = re.compile(r'\b([\w$]+)' + GOCH + r'\.(HandleFunc|Handle|Get|Post|Put|Patch|Delete|GET|POST|PUT|PATCH|DELETE|Any|ANY)\(\s*"([^"]*)"\s*,')
GOMETH = re.compile(r'\b([\w$]+)' + GOCH + r'\.(?:Handle|Method|MethodFunc|Add)\(\s*"(%s)"\s*,\s*"([^"]*)"' % V, re.I)
GOCLI = re.compile(r"(?:http|resty|req|session|\w*client)$", re.I)  # receivers of outbound calls: client.Post("/x", "application/json", body)
GOGRP = re.compile(r'\b([\w$]+)\s*:?=\s*([\w$]+)\.(?:Group|PathPrefix)\(\s*"([^"]*)"')
GORT = re.compile(r'\.(?:Route|Mount)\(\s*"([^"]*)"\s*,\s*func\b[^{]*\{')
GOMS = re.compile(r'(?:\s*\.\w+\([^()]*\))*\s*\.Methods\(([^)]*)\)')  # chained calls before .Methods: .Name("x").Methods("POST")
JAVAM = re.compile(r'@(Get|Post|Put|Patch|Delete|Request)Mapping\b(?:\s*\(((?:[^()"]|"[^"]*"|\([^()]*\))*)\))?')
JAVAX = re.compile(r"\bmethod\s*=[^,)]*|\b(?:consumes|produces|headers|params)\s*=\s*(?:\{[^}]*\}|[^,)]*)")
DJ = re.compile(r'(?<![\w.])(re_path|path|url)\(\s*r?(["\'])(.*?)\2\s*,\s*(include\(\s*(?:r?["\']([\w.]+)["\'])?)?')
NOTSRC = re.compile(TEST.pattern + r"|_test\.go$|Tests?\.(?:java|kt|php)$")


def join(*ps):
    """Path segments joined with single slashes and a leading one: join("/api/", "x") is /api/x."""
    return "/".join(["", *(x.strip("/") for x in ps if x.strip("/"))]) or "/"


def goroute(p):
    """Go 1.22 / chi / gorilla path to a route: {id} -> :id, {rest...} -> :rest*, {$} dropped."""
    return pyroute(re.sub(r"\{(\w+)\.\.\.\}", r"{\1}*", p.replace("{$}", "")))


def go_routes(raw):
    """[(pos, METHOD, path)] of a Go file: net/http `HandleFunc|Handle("[METHOD ]/p", h)`, chi/gin/echo `x.Get|GET|Any("/p", h)`, `x.Handle|Method|Add("GET", "/p", h)`, gorilla
    `HandleFunc("/p", h).Methods("A","B")`, behind a `.With(mw)` / `.Group("/a")` chain, under `x := y.Group|PathPrefix("/a")` prefixes (the latest definition of x in a block that holds the
    route) and chi `x.Route|Mount("/a", func(...) {` blocks. Outbound calls (a client-like receiver, or no handler argument) are skipped."""
    mk, bm = mask(raw, True), mask(raw)
    blocks, st = [], []
    for i, c in enumerate(bm):
        if c == "{": st.append(i)
        elif c == "}" and st: blocks.append((st.pop(), i))
    defs_ = [(t.start(), t) for t in GOGRP.finditer(mk)]
    rts = [(t.start(), close_of(mk, t.end() - 1), t[1]) for t in GORT.finditer(mk)]
    def scope(pos): return min((b - a, a, b) for a, b in blocks if a < pos < b)[1:] if any(a < pos < b for a, b in blocks) else (-1, len(mk))
    def gp(var, pos):
        d = [t for q, t in defs_ if t[1] == var and q < pos and scope(q)[0] < pos < scope(q)[1]]
        return join(gp(d[-1][2], d[-1].start()), d[-1][3]) if d else ""
    def pf(pos, var, ch): return join(gp(var, pos), *re.findall(r'(?:Group|PathPrefix)\(\s*"([^"]*)"', ch), *(q for a, b, q in rts if a < pos < b))
    out = [(t.start(), t[3].upper(), join(pf(t.start(), t[1], t[2]), goroute(t[4]))) for t in GOMETH.finditer(mk)]
    for t in GOCALL.finditer(mk):
        k, p, q = t[3], t[4], pf(t.start(), t[1], t[2])
        if GOMETH.match(mk, t.start()): continue
        m = re.match(r"(%s)\s+(.*)" % V, p)
        if m: meth, p = m[1], m[2]
        elif k in ("Handle", "HandleFunc"):
            cl = close_of(mk, mk.index("(", t.end(3)))
            ms = GOMS.match(mk, cl + 1) if cl > 0 else None
            meth = "|".join(v for v in VERBS + ("HEAD", "OPTIONS") if re.search(r'"%s"|\bMethod%s\b' % (v, v.capitalize()), ms[1], re.I)) if ms else "ANY"  # .Methods("POST") or .Methods(http.MethodPost)
        elif GOCLI.match(t[1]): continue  # client.Get("/x", ...) is an outbound call
        else: meth = k.upper()
        if p.startswith("/") or p == "" and q != "/": out.append((t.start(), meth, join(q, goroute(p))))
    return out


def java_paths(a):
    """Paths of a mapping annotation's arguments (a): the strings of `value=` / `path=` (else the bare argument, `name=` and the other attributes dropped); a part that is no string
    literal (a constant, `BASE + "/x"`) reads `{?}`, so the row names an unresolved path, never a wrong one."""
    S = r'"(?:[^"\\]|\\.)*"'  # a Java string literal
    x = re.search(r"\b(?:value|path)\s*=\s*(\{(?:%s|[^}\"])*\}|\[(?:%s|[^\]\"])*\]|(?:%s|[^,)\"])*)" % (S, S, S), a)
    body = x[1] if x else re.sub(r"\b\w+\s*=\s*(?:\{(?:%s|[^}\"])*\}|\[(?:%s|[^\]\"])*\]|(?:%s|[^,)\"])*)" % (S, S, S), "", JAVAX.sub("", a)) if re.search(r"\b\w+\s*=", a) else a
    out = []
    for el in re.findall(r'(?:[^,"{}\[\]]|%s)+' % S, body):
        if el.strip(): out.append("".join(g[0] if g[0] or not g[1] else "{?}" for g in re.findall(r'"((?:[^"\\]|\\.)*)"|([\w.$]+)', el)))
    return out or [""]


def java_routes(raw):
    """[(pos, METHOD, path)] of a Spring file: `@Get|Post|Put|Patch|DeleteMapping` and `@RequestMapping(value|path = ..., method = RequestMethod.X)` (ANY without a method), every path
    of an array (java_paths), under the `@RequestMapping` of its own class (a method-less one with no `{` or `;` before the next `class`; each class or interface declaration resets
    the prefix, a nested class too).
    ponytail: a controller's nested class ends the outer prefix for the mappings after it."""
    mk = mask(raw, True)
    out, pre, pend = [], "", ""
    cls = [t.start() for t in re.finditer(r"\b(?:class|interface)\s+\w+", mk)]
    for t in JAVAM.finditer(mk):
        while cls and cls[0] < t.start(): cls.pop(0); pre, pend = pend, ""
        a = t[2] or ""
        ps = java_paths(a)
        if t[1] == "Request" and "method" not in a:
            c = re.search(r"\b(?:class|interface)\b", mk[t.end():])
            if c and not re.search(r"[{;]", mk[t.end():t.end() + c.start()]): pend = ps[0]; continue
        ms = re.findall(r"\b(%s)\b" % V, "".join(re.findall(r"\bmethod\s*=[^)]*", a))) if t[1] == "Request" else [t[1].upper()]
        out += [(t.start(), "|".join(ms) or "ANY", join(pre, pyroute(p))) for p in ps]
    return out


PHPN = re.compile(r"(?:\s+|\]|\*/|\*[^\n]*|@\w+[^\n]*|#\[[^\n]*|//[^\n]*|/\*.*?\*/|\b(?:final|abstract|readonly|public|protected|private|static)\b)*?\b(class|function)\b", re.S)  # tokens skipped between a Route and its declaration
PHPR = re.compile(r"(?:#\[\s*|@)Route\s*\(((?:[^()\"']|\"[^\"]*\"|'[^']*'|\([^()]*\))*)\)")  # a Symfony attribute or annotation
PHPL = re.compile(r"""\bRoute::(get|post|put|patch|delete|any)\(\s*['"]([^'"]*)['"]""", re.I)


def php_routes(raw):
    """[(pos, METHOD, path)] of a PHP file: Symfony `#[Route('/p', methods: ['POST'])]` and `@Route("/p", methods={"POST"})` (no methods: ANY), under the Route of its own class (one before a
    `class`), at the position of the Route; Laravel `Route::get|post|put|patch|delete|any('/p', ...)`.
    ponytail: Laravel `Route::prefix()` / `group()` nesting is not resolved; a Laravel controller array is not followed to its method. Upgrade when a repo needs it."""
    out, pre, cend, bm = [], "", 0, re.sub(r"#(?!\[)[^\n]*", lambda x: " " * len(x[0]), mask(raw))  # bm: comments (`#` too) and strings blanked, same length
    for t in PHPR.finditer(raw):
        a = t[1]
        m = re.search(r"""\bpath\s*[:=]\s*['"]([^'"]*)['"]""", a) or re.match(r"""\s*['"]([^'"]*)['"]""", a)
        ms = re.search(r"\bmethods\s*[:=]\s*[\[{]([^\]}]*)", a)
        nx = PHPN.match(raw, t.end(), t.end() + 400)  # the declaration right after the Route, in a bounded window
        if nx and nx[1] == "class":  # a Route right before a `class` is that class's prefix
            pre, cend = (m[1] if m else ""), nx.end(); continue
        if pre and re.search(r"(?<![:\w$>])class\s+\w", bm[cend:t.start()]): pre = ""  # a later class ends the prefix
        verbs = [v for v in VERBS if ms and re.search(r"['\"]%s['\"]" % v, ms[1], re.I)]
        out.append((t.start(), "|".join(verbs) or "ANY", join(pre, pyroute(m[1] if m else ""))))
    for t in PHPL.finditer(raw):
        out.append((t.start(), t[1].upper(), join(pyroute(t[2]))))
    return out


def groups(r):
    """Regex route r with each named group `(?P<id>...)` (nested parentheses balanced) replaced by `<id>`."""
    while True:
        x = re.search(r"\(\?P<(\w+)>", r)
        if not x: return r
        d, i = 1, x.end()
        while d and i < len(r):
            d += (r[i] == "(") - (r[i] == ")") if r[i - 1] != "\\" else 0
            i += 1
        r = r[:x.start()] + "<%s>" % x[1] + r[i:]


def django_routes(files):
    """[(rel, line, "ANY", path)] of Django urlconfs (files: {rel: raw}): `path|re_path|url("route", view)` (a view's methods are not read), under the prefixes of
    `include("pkg.urls")` calls that name a scanned file by its dotted path suffix (`include(module)`, a list and an unresolvable name are skipped). A urlconf some other one includes is read only under that prefix."""
    mks = {r: pymask(raw, True) for r, raw in files.items() if "urlpatterns" in raw}
    ents = {r: list(DJ.finditer(mk)) for r, mk in mks.items()}
    def find(spec): return next((r for r in mks if ("/" + r).endswith("/" + spec.replace(".", "/") + ".py")), None)
    inc = {find(t[5]) for ts in ents.values() for t in ts if t[5]}
    out = []
    def walk(rel, pre, path, seen):
        for t in ents[rel]:
            r = t[3]
            if t[1] != "path": r = groups(r).lstrip("^").rstrip("$")
            if not t[4]: out.append((rel, lineno(mks[rel], t.start()), "ANY", join(pre, pyroute(r)) if r.strip("/") else join(pre)))
            elif t[5] and find(t[5]) and find(t[5]) not in path: seen.add(find(t[5])); walk(find(t[5]), join(pre, r), path | {find(t[5])}, seen)
    seen = set()
    for r in [r for r in mks if r not in inc] + list(mks):  # then any urlconf an include cycle left unread
        if r not in seen: seen.add(r); walk(r, "", {r}, seen)
    return out


def other_routes(root):
    """[(METHOD, path, file, line)] of the routes scan() never judges, unsorted: Go, Spring, Kotlin, PHP and Django urlconfs (ANY). Walks root once; scan() is not re-run."""
    rows, files, django = [], {}, {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in sorted(dn) if d not in SKIP_DIR]
        for f in sorted(fn):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            if NOTSRC.search(rel): continue
            if f.endswith((".go", ".java", ".kt", ".php")): files[rel] = f
            elif f.endswith(".py") and "urlpatterns" in (raw := read(root, rel) or ""): django[rel] = raw
    for rel in files:
        raw = read(root, rel) or ""
        for pos, ms, p in (go_routes if rel.endswith(".go") else php_routes if rel.endswith(".php") else java_routes)(raw):
            rows += [(m, p, rel, lineno(raw, pos)) for m in ms.split("|")]
    rows += [(m, p, rel, ln) for rel, ln, m, p in django_routes(django)]
    return rows


def inventory(root):
    """[(METHOD, path, file, line)] of every route under root, sorted, one entry per method: the scan() handlers (JS/TS, Next, Python) plus other_routes()."""
    rows = [(m, r[3], r[0], r[1]) for r in scan(root)[0] for m in r[2].split("|")]
    return sorted(set(rows + other_routes(root)), key=lambda r: (r[1], r[0], r[2], r[3]))


PRIVSEG = re.compile(r"admin|administrator|superuser|backoffice", re.I)
PRIVROLE = re.compile(r"role|permission|privilege|grant|promote|demote", re.I)
PRIVREC = re.compile(r"(?:^|/)(?:users?|accounts?|members?|profiles?|customers?)/:\w+")  # another user's record: a collection then an id param
CALLER = r"(?:\breq(?:uest)?\.user|current_user|\bg\.user|\buser)"  # the signed-in user object
ROLEWORD = r"(?:roles?|permissions?|scopes?|perms|groups|authorities)"
ROLECHK = re.compile(  # check shapes, not words: `{role: req.body.role}` is the write being guarded, not a guard
    r"\b" + ROLEWORD + r"\b\s*(?:[!=]==?|\.(?:includes|has|some|indexOf)\(|\bin\b)|['\"`][^'\"`\n]+['\"`]\s+(?:not\s+)?in\s+[^\n]*?\b" + ROLEWORD + r"\b|\.admin\b"
    r"|is_?(?:admin|staff|superuser)|has_?(?:role|perm\w*)|require_?(?:role|admin|perm\w*)|permission_required|authori[sz](?:e\w*|er)\b|\bcans?\(|\bcan_|rbac|polic(?:y|ies)|abilit"
    # named guards: a call (checkRole('x'), ensure_staff(u), restrictTo('admin')), a middleware or dependency argument (adminOnly, Depends(get_admin)), a Security(scopes=[...]) dependency,
    # a permission object's .require(), and a comparison on a user attribute that is not an identifier (req.user.tier === 'staff')
    r"|\b(?:check|has|ensure|verify|assert|need|must|enforce|guard|allow|only|restrict)_?(?:to|roles?|perm\w*|scopes?|privileg\w*|access|admin|staff|owner)\w*\s*\("
    r"|(?:admin|staff|superuser|moderator)_?only|(?<=[(,])\s*[\w$.]*(?:admin|staff|superuser|moderator)[\w$]*\s*(?=[,)])"
    r"|Depends\(\s*\w*(?:admin|staff|superuser|moderator|role|perm|scope|privileg)|Security\([^)]*scopes\s*=|\w*(?:permission|role|admin|scope|staff|need)\w*\.(?:require|check|allow|enforce)\w*\("
    r"|" + CALLER + r"\.(?!\w*Id\b|\w*_id\b|id\b|pk\b|sub\b)\w+\s*(?:[!=]==?|\b(?:not\s+)?in\b)"
    r"|['\"`]\s*[!=]==?\s*" + CALLER + r"\.", re.I)
CID = CALLER + r"\.(?:\w*Id|\w*_id|id|pk|sub)\b"  # the caller's identifier
OWNCMP = CID + r"\s*[!=]==?|[!=]==?\s*" + CID  # the caller's identifier compared
OWNSET = r"\b(?:id|_id|pk|user_?id|owner\w*|\w*profile\w*|account_?id)\s*[:=]\s*" + CID  # an id or owner field set to the caller's identifier
OWNER = re.compile(OWNCMP + "|" + OWNSET, re.I)  # the record written is the caller's own: an identifier comparison or a scoped lookup on the caller's id
PRIVVERB = re.compile(r"/:\w+/(?:suspend|ban|unban|disable|enable|activate|deactivate|approve|reject|impersonate|refund|lock|unlock|status)(?:/|$)")
PATHLIT = re.compile(r"""(['"`])/[^'"`]*\1""")


def privileged(rows):
    """[(row, why)] for routes with identity evidence (auth is neither none nor public, or a router-level gate) that are privileged and whose handler, router-level guards and helper text hold no role, permission or admin check.
    Privileged: an admin path segment (non-GET: a read-only admin page is not listed), a role or permission path segment (non-GET), a state verb under a record (non-GET: /x/:id/suspend, /status) or PUT/PATCH/DELETE on `/users/:id` and kin
    unless the handler scopes the write to the caller's own id. Router-level evidence: JS `.use(...)` before the route, Python `prefix=` / `url_prefix=`, `dependencies=[...]`, `include_router`,
    `register_blueprint` and `before_request` in the same file. Heuristic: a quoted /path literal is dropped before the check search so the route itself does not count; a check done in a function
    the scan does not follow, a guard mounted from another file, or an imported router prefix is missed (lead, not proof)."""
    out = []
    for r in rows:
        rel, ln, meth, route, lab = r
        pfx, gt, gated = EXTRA.get((rel, ln), ("", "", False))
        if lab == "public" or lab == "none" and not gated: continue
        route = (pfx.rstrip("/") + route).rstrip("/") or "/"
        ms, parts = meth.split("|"), route.lower().split("/")
        why = ("admin path" if any(PRIVSEG.search(p) for p in parts) and ms != ["GET"] else
               "role or permission change" if any(PRIVROLE.search(p) for p in parts) and ms != ["GET"] else
               "state change on another user's record" if PRIVVERB.search(route) and ms != ["GET"] else
               "write on another user's record" if PRIVREC.search(route) and {"PUT", "PATCH", "DELETE", "ANY"} & set(ms) else None)
        body = PATHLIT.sub("", BODY.get((rel, ln), "") + "\n" + gt)
        if why and not ROLECHK.search(body) and not (why.endswith("record") and OWNER.search(body)): out.append(((rel, ln, meth, route, lab), why))
    return out


INJ = re.compile(r"@Injectable\s*\([^)]*\)[\s\S]{0,300}?\bclass\s+([$\w]+)")  # a NestJS provider class: the service a controller member delegates to
TSPARAM = re.compile(r"\bparams\s*(?:\??\.\s*([\w$]+)|:\s*\{\s*([\w$]+)(?=\s*[,}]))")  # a path parameter a ts-rest member reads: `params.uid`, `{ params: { uid } }`
SVCCALL = re.compile(r"\bthis\.([\w$]+)\.([\w$]+)\s*\(")  # `this.things.update(` in a controller member: field `things`, method `update`
# a write method call: `.update(`, `.deleteMany(`, Mongoose `.findByIdAndUpdate(` / `.replaceOne(` / `.bulkWrite(`, MikroORM `.nativeDelete(` / `.persistAndFlush(`, TypeORM `.increment(` / `.softRemove(`, Knex `.del(`, CQRS `commandBus.execute(`
WMETH = r"\.(?:update|upsert|delete|del(?![\w$])|(?<=commandBus\.)execute|remove|destroy|save|soft(?:Delete|Remove)|create|insert|find\w*And(?:Update|Delete|Remove|Replace)|replaceOne|bulk(?!Get)[A-Z]|native(?:Update|Delete)|persist(?!ence)|(?:in|de)crement(?!al))\w*\s*\("
WRITE = re.compile(WMETH + r"|\bconnect\s*:")
REQVAR = r"(?-i:requester|actor|caller|principal|current_?[uU]ser)"  # a variable named for the requester
REQOBJ = r"(?-i:user|auth|session|req(?:uest)?\.user|me)"  # the signed-in object's usual names
IDF = r"\.(?:id|uid|sub|user_?id|user_?uid)"  # an identifier field read off an object
REQID = r"\b(?:" + REQVAR + r"\w*?(?:" + IDF + r"|Id|Uid|_id|_uid)|" + REQOBJ + IDF + r")\b"  # `requesterUid`, `user.id`, `me.uid`; a bare `userId`, `authorId` or `memberId` is any id


def owner_checks(words):
    """(BODYOWNER, OWNCHK) for ownership(), built from the owner-word alternation words (ownership_sibling_check.OWNER_WORDS, so the list has one home).
    BODYOWNER: an owner id the client sends (`dto.ownerUid`). OWNCHK: a where opening the argument of `<model>.<method>({ where: {`, the model in group `a` or `b`
    (ownership() keeps it only on a model the text writes, and on a path with a record id only when the where names that id: the write's own call or the lookup of the record written), that sets an owner-word key to the requester's id
    (REQID or CID; a bare `id`, `uid` or `pk` names the requester's own row, so it is none), or names an owner-id key in shorthand (`where: { uid, ownerUid }`) declared from the
    requester's id earlier by a statement of its own (`const ownerUid = requester.uid;`) and not assigned again before the where (`ownerUid = dto.ownerUid;`). A field set from the
    requester's id is not one (an audit field), nor is a shorthand key passed in as a parameter or destructured with a default (`const { ownerUid = requester.uid } = dto`, on one
    line or several: the client's value wins).
    A comparison is requester_compare()'s, a decorator guard_decorator()'s."""
    w = r"\b(?P<%s>[\w$]+)\s*\.\s*[\w$]+\s*\(\s*\{\s*where\s*:\s*\{"  # ponytail: the where must be the first key (`{ data, where: {` is missed, the row stays OWN); read any key if such rows show up
    return (re.compile(r"\b[\w$]*(?:body|dto|input|payload|data)\.(?:" + words + r")\w*(?:Id|Uid|_id|_uid)\b", re.I), re.compile(
        w % "a" + r"[^{}]*\b(?!uid\s*:)(?:" + words + r")\w*\s*:\s*(?:" + REQID + "|" + CID + ")" +
        r"|\b(?:const|let|var)\s+(?P<k>(?:" + words + r")\w*?(?:Id|Uid|_id|_uid))\s*=\s*" + REQID + r"[ \t]*[;\n](?:(?!(?<![\w$.])(?P=k)\s*(?:\?\?|\|\||&&)?=(?![=>]))[\s\S])*?" + w % "b" + r"(?:[^{}]*,)?\s*(?P=k)\s*[,}]", re.I))


OPND = r"[A-Za-z_$][\w$]*(?:\??\.[\w$]+)*"  # a name or member chain (`t?.ownerUid`); a literal, a masked string or a call result is none
IDCMP = re.compile(r"(?<![\w$.?])(" + OPND + r")\s*[!=]==?\s*(" + OPND + r")(?![\w$?.]|\s*\()")
REQWHOLE = re.compile(REQID + "|" + CID, re.I)  # the requester's id, read whole (fullmatch)
LITERAL = re.compile(r"null|undefined|true|false|NaN|this|(?:[\w$]+\.)*[A-Z][A-Z\d_$]*")  # a literal or a named constant (`SYSTEM_UID`, `Acme.ROOT_ID`): no record's owner
CLIENT = re.compile(r"[\w$]*(?:body|dto|input|payload|data)\.", re.I)  # a field of what the client sent
CLIENTVAR = re.compile(r"\b(?:const|let|var)\s+(?:\{([^{}]*)\}|([\w$]+))\s*(?::[^=;\n]*)?=\s*(?:await\s+)?[\w$]*(?:body|dto|input|payload|data)\b", re.I)  # `const { ownerUid } = dto`, `const o = dto.ownerUid`


def requester_compare(t, body_ok):
    """The first `a === b` / `a != b` in t with one side the requester's id (REQWHOLE) and the other an owner-like field: a name or member chain (`t.holder`, `uid`) that is
    no literal or named constant (`null`, `undefined`, `SYSTEM_UID`, a masked string), not the requester's id again and, unless body_ok (the path holds no record id: a create that writes a client-sent owner id),
    no client body field, read directly or through a local declared from the body (CLIENTVAR: `const { ownerUid } = dto`, `const o = dto.ownerUid`).
    `t.ownerUid === null`, `req.user.id == null`, `dto.ownerUid !== t.ownerUid` and, on a path with a record id, `dto.ownerUid !== requester.uid` or `ownerUid !== requester.uid` after
    `const { ownerUid } = dto` (it checks the new owner, not the record's) are none. Else None. ponytail: such a local anywhere in t is the client's value everywhere in t."""
    al = set() if body_ok else {n for v in CLIENTVAR.finditer(t) for n in (re.findall(r"([\w$]+)\s*(?:=[^,]*)?(?:,|$)", v[1].strip()) if v[1] is not None else [v[2]])}
    for c in IDCMP.finditer(t):
        a, b = (x.replace("?", "") for x in c.groups())
        if any(REQWHOLE.fullmatch(x) and not REQWHOLE.fullmatch(y) and not LITERAL.fullmatch(y) and (body_ok or not CLIENT.match(y) and y.split(".")[0] not in al) for x, y in ((a, b), (b, a))): return c[0]


REQDECO = re.compile(r"(?<=[(,])\s*@[\w$]*(?:User|Member|Requester|Principal|Actor|Caller|Account|Session)[\w$]*\s*\([^()]*\)\s*([\w$]+)")  # a `@CurrentUser() member` parameter


def requester_text(own, t):
    """Masked t with the requester's names made plain for REQWHOLE: a `@CurrentUser() member`-style parameter of the masked member own (REQDECO) reads `requester__member`,
    and a REQOBJ or such name that t binds to a local from anything but the request (`const user = await this.prisma.user.findUnique(...)`: a record, not the requester)
    reads `user__rec`, so REQID and CID no longer match it; plain() undoes both. A parameter (`requester: AcmeUser`, passed `req.user`) stays the requester.
    ponytail: one such local anywhere in t un-requesters the name everywhere in t; a destructured, reassigned or callback-parameter rebinding is not seen."""
    obj = ("user", "auth", "session", "me")
    for n in dict.fromkeys(REQDECO.findall(own) + list(obj)):
        gone = re.search(r"\b(?:const|let|var)\s+%s\s*(?::[^=;\n]*)?=(?![=>])(?!\s*(?:await\s+)?req(?:uest)?\b)" % re.escape(n), t)
        if gone or n not in obj: t = re.sub(r"(?<![\w$.])%s(?![\w$])" % re.escape(n), n + "__rec" if gone else "requester__" + n, t)
    return t


def plain(s):
    """Snippet s of requester_text() output with its renames undone, whitespace collapsed, at most 60 characters."""
    return " ".join(re.sub(r"requester__([\w$]+)|([\w$]+?)__rec(?![\w$])", lambda x: x[1] or x[2], s).split())[:60]


AUTHZDECO = re.compile(r"@(?!Api)(?:[\w$]*(?:Roles?|Permissions?|Admin|Staff|Superuser|Moderator|Owner)[\w$]*|CheckPolic\w*|CheckAbilit\w*|Scopes?|UseGuards|Auth\w*|Require\w*)\s*\(")
PRIVWORD = re.compile(r"admin|staff|superuser|moderator|owner", re.I)  # a privileged role named
OBJGUARD = re.compile(r"\b[\w$]*?(?:Polic(?:y|ies)|Abilit(?:y|ies)|Casl[\w$]*)Guard\b")  # an object-level policy guard class: `PoliciesGuard`, `AcmePolicyGuard`, `CaslAbilityGuard`, `AbilitiesGuard`; case-sensitive, so `AvailabilityGuard` and `CapabilityGuard` are none (an owner guard names a privileged role)


def guard_decorator(t):
    """Text of the first guard or role decorator in t (class decorators and the member span) that names a privileged role or an object-level policy check, else None.
    Read: role decorators (`@Roles(...)`, `@RequirePermissions(...)`, `@Scopes(...)`, `@StaffOnly()`), `@CheckPolicies(...)`, `@CheckAbilit*(...)`, `@UseGuards(...)`, `@Auth*(...)`
    and `@Require*(...)`. One counts when its name names a privileged role (PRIVWORD: `@StaffOnly()`), it is `@CheckPolicies`/`@CheckAbilit*`, an argument is an OBJGUARD class
    (`PoliciesGuard`, `CaslAbilityGuard`), a `@UseGuards(...)` argument names one (`@UseGuards(AcmeOwnerGuard)`: every guard must pass), or every argument of any other (strings
    kept, split at `,` and `|`) names one (`@Roles('admin')`, `@Auth(Role.Admin)`): any listed role may call, so `@Roles('user', 'admin')` and `@Roles(Role.User, Role.Admin)` are none.
    `@Roles('user')`, `RolesGuard` and `@RequirePermissions('things:write')` say who may call, not whose record it is: none. No other decorator is read:
    `@UseInterceptors(StaffAuditInterceptor)`, `@UsePipes(...)`, Swagger `@Api*(...)` and parameter decorators check nothing."""
    m, k = mask(t), mask(t, True)
    for d in AUTHZDECO.finditer(m):
        if m[:d.start()].rstrip().endswith(("(", ",")): continue  # a parameter decorator (`@CurrentOwner() owner`) reads a value, it guards nothing
        e = close_of(m, d.end() - 1)
        s = k[d.start():e + 1 if e > 0 else d.end()]
        ps = [x for x in re.split(r"[,|]", s[d.end() - d.start():-1] if e > 0 else "") if x.strip()]
        if d[0].startswith(("@CheckPolic", "@CheckAbilit")) or PRIVWORD.search(d[0]) or OBJGUARD.search(s) or (
                PRIVWORD.search(s) if d[0].startswith("@UseGuards") else ps and all(PRIVWORD.search(x) for x in ps)): return " ".join(t[d.start():d.start() + len(s)].split())[:60]


MACHINE = re.compile(r"\b(?![\w$]*?(?:Jwt|User|Session|(?-i:Or[A-Z]))[\w$]*Guard\b)[\w$]*(?:Internal|Service|Integration|Machine|M2M)[\w$]*?(?:Auth|Key|Token)[\w$]*Guard\b", re.I)  # a machine credential guard (a bare or org `ApiKeyGuard` is often a user's or an org's key, so it is none): no end user, so no requester to compare (`JwtOrApiKeyGuard` and other user, session or either-or guards have one)


def body_open(m, pc):
    """Index of the body `{` after the parameter list that closes at m[pc], past a return type such as `: Promise<{ ok: boolean }>` or `: { a: T } | null`.
    -1 when a `;` comes first (an overload signature) or a brace does not close. Heuristic: a `{` inside open angle brackets or after `:`, `|`, `&`, `,`, `(`, `[` or `=>` is a type."""
    s = pc + 1
    while True:
        o = m.find("{", s)
        if o < 0 or ";" in m[s:o]: return -1
        t = m[pc + 1:o]
        if t.count("<") <= t.count(">") - t.count("=>") and not t.rstrip().endswith((":", "|", "&", ",", "(", "[", "=>")): return o
        s = close_of(m, o) + 1
        if s <= 0: return -1


SVC_CACHE = {}  # file -> (masked, masked keeping strings), shared by ownership() and authz_leads() so each service file is masked once


def service_text(root, own, types, cache):
    """(text, names) of the @Injectable service methods a NestJS member calls as `this.<field>.<method>(` (field typed in its class), with the same-class helpers they call as
    `this.<helper>(`; names lists `Class.method` per method read. ponytail: one hop, by class name (CLS: a name two files define reads both, the controller's import is not resolved), no inheritance or deeper repository layer; a method it cannot find adds nothing."""
    out, names = [], []
    for fld, meth, f in [(a, b, f) for a, b in dict.fromkeys(SVCCALL.findall(own)) for f in CLS.get(types.get(a, ""), ())]:
        if f not in cache:
            raw = read(root, f) or ""
            cache[f] = (mask(raw), mask(raw, True))
        m, mk = cache[f]
        c = re.search(r"\bclass\s+%s\b[^{]*" % re.escape(types[fld]), m)
        b = c.end() if c else -1
        e = close_of(m, b) if b >= 0 and m[b:b + 1] == "{" else -1
        if e < 0: continue
        def body(n):
            if (f, types[fld], n) in cache: return cache[f, types[fld], n]
            for t in re.finditer(r"^[ \t]*(?:(?:public|private|protected|static|async|override)\s+)*%s\s*(?:<[^>()]*>)?\s*\(" % re.escape(n), m[:e], re.M):
                if t.start() < b: continue
                pc = close_of(m, t.end() - 1); o = body_open(m, pc) if pc > 0 else -1
                if o > 0: cache[f, types[fld], n] = mk[t.start():close_of(m, o) + 1]; return cache[f, types[fld], n]
            cache[f, types[fld], n] = ""; return ""
        t = body(meth)
        if t: names.append("%s.%s" % (types[fld], meth))
        out += [t] + [body(h) for h in dict.fromkeys(re.findall(r"\bthis\.([\w$]+)\s*\(", t)) if h != meth]
    return "\n".join(out), list(dict.fromkeys(names))


def ownership(rows, root, skip=()):
    """[(row, why, cls, match)] for authenticated NestJS write routes (plain verb decorators and ts-rest) (CWE-639, OWASP API1:2023 BOLA). A row: PUT/PATCH/DELETE on a path with an `:id`
    parameter, or POST/PUT/PATCH that writes an owner id the client sends (`dto.ownerUid`), with a write call
    (WMETH: `.update(`, `.delete(`, `.findByIdAndUpdate(`, `.nativeDelete(`, Knex `.del(`, a CQRS `commandBus.execute(`, `connect:` ...) in the member or the service methods it calls; a service call whose body service_text() could not read (an inherited
    base-class method, a generic class whose type has braces, a decorator on the method's line) stays in the member text, so `this.things.update(` is the write. An unresolved ts-rest member (`contract:<key>`)
    is by id when it reads a path parameter (`params.uid`, `{ params: { uid } }`). Writes WMETH does not name make no row at all (MikroORM `em.flush()` after `wrap(t).assign(dto)`), and a Mongoose or
    MikroORM filter (`findOneAndUpdate({ _id: uid, owner: requester.uid }, dto)`) is no `where`, so its scope is not read and the row stays OWN.
    cls None (an OWN row): nothing read ties the write to the requester. Else the row is OWN-CHECKED, kept with the first check read and match, its text (at most 60 characters):
    `machine` (every class and member `@UseGuards` guard is a MACHINE credential guard: no end user; one user guard beside it keeps the row OWN), `decorator-guard` (guard_decorator() on the class
    decorators and the member span), or `requester-compare` (requester_compare(), OWNCHK from owner_checks in the guard label, class decorators, member or followed service text, all masked,
    with requester_text() names; an OWNCHK where counts only on a model the text writes and, on a path with a record id, only when it names that id). Nothing else counts: a role word, guard-helper call or 403/Forbidden throw in a body (`this.policies`, `hasOwner(t)`, a closed-status ForbiddenException), a string literal,
    a field set from the requester's id outside a where (`updatedBy: requester.uid`, `data: { ownerId: user.id }`) and a service taking a requester argument and never comparing it all keep the row OWN.
    Auth none or public is route-auth's row, not this one; rows in skip ((file, line, route) already PRIV) are dropped, so a member's other paths keep theirs. A public or unauthenticated GET on the collection path is named in why, since it hands out the ids.
    ponytail: text scan, one hop into the service (service_text); a check in a guard class body, a base class or a deeper repository is missed (lead, not proof)."""
    from ownership_sibling_check import OWNER_WORDS  # lazy: only --privileged needs it, and scripts that import this module may ship without it
    bodyowner, ownchk = owner_checks(OWNER_WORDS)
    lists = {r[3]: r[4] for r in rows if r[2] in ("GET", "ANY") and r[4] in ("public", "none")}
    out, cache = [], SVC_CACHE
    for r in rows:
        rel, ln, meth, route, lab = r
        if (rel, ln) not in NESTCTX or (rel, ln, route) in skip or lab in ("none", "public", "presence-check"): continue
        hdr, types = NESTCTX[(rel, ln)]
        own = BODY.get((rel, ln), "")
        svc, names = service_text(root, own, types, cache)
        txt = "\n".join((lab, hdr, own, svc))
        ms = set(meth.split("|"))
        cid = re.findall(r"/:(\w+)", route) or ([a or b for a, b in TSPARAM.findall(mask(own))] if route.startswith("contract:") else [])  # the client id: a path parameter, or what an unresolved ts-rest member reads off `params`
        why = ("client-sent owner id written" if ms & {"POST", "PUT", "PATCH", "ANY"} and bodyowner.search(txt) else
               "write by client-sent id" if ms & {"PUT", "PATCH", "DELETE", "ANY"} and cid else None)
        seen = SVCCALL.sub(lambda t: "" if "%s.%s" % (types.get(t[1], ""), t[2]) in names else t[0], own) + svc  # a service call whose body was read is no write; its body is
        if not why or not WRITE.search(seen): continue
        dm = mask(hdr + "\n" + own)
        gs = [n for n in nest_guards(dm, 0, len(dm)) if n != "new"]
        bt = requester_text(mask(own), mask(txt))
        cv = cid and re.compile(r"(?<![\w$.])(?:params\.)?(?:%s)(?![\w$])(?!\s*:)" % "|".join(map(re.escape, cid)))
        wr = set(re.findall(r"([\w$]+)\s*" + WMETH, bt))  # the models written
        def where(x):  # the where object of an OWNCHK match (it opens its call's argument); with a path id it must name that id, so a where on another row of a written model
            # (`notification.updateMany({ where: { userId: requester.uid } })`, a lookup without the id) scopes nothing, while a scoped lookup then `save(t)` or `update({ where: { id: t.id } })` keeps its check
            o = bt.find("{", bt.find("{", x.start("a" if x["a"] else "b")) + 1)
            return bt[o:close_of(bt, o) + 1]
        rc = requester_compare(bt, not cid) or next((x[0] for x in ownchk.finditer(bt) if (x["a"] or x["b"]) in wr and (not cv or cv.search(where(x)))), None)
        dg = guard_decorator(hdr + "\n" + own)
        cls, hit = (("machine", ", ".join(gs)[:60]) if gs and all(MACHINE.search(n) for n in gs) else ("decorator-guard", dg) if dg else
                    ("requester-compare", plain(rc)) if rc else (None, None))
        lst = lists.get(re.sub(r"/:\w+$", "", route)) if why.startswith("write") else None
        out.append((r, "%s; no requester-to-owner check in the member%s%s" % (why, "".join(" or " + n for n in names), "; ids listed by GET %s auth=%s" % (re.sub(r"/:\w+$", "", route), lst) if lst else ""), cls, hit))
    return out


PRIVF = r"(?:[Ii]s_?)?(?:roles?|[Aa]dmin|[Vv]erified|[Ss]uperuser|[Ss]taff)|is[A-Z]\w*Admin|(?:owner|creator|author)\w*(?:Uid|Id)|createdBy\w*"  # a field a client must not set on its own record
DEADGATE = re.compile(r"\bif\s*\((?:(?!\bif\b)[^;{]){0,200}?\bisEmpty\(\s*[\w$.?]+\.(?:(?:[Ii]s_?)?(?:[Aa]dmin|[Vv]erified|[Ss]uperuser|[Ss]taff)|is[A-Z]\w*Admin)\s*\)[^;{]*")  # lodash isEmpty on a boolean/number is always true: a gate on it never fires
OWNID = r"\w+(?:MemberUid|TeamUid)|(?:owner|author|creator)\w*(?:Uid|Id)|userId|createdBy\w*"  # an owner/author id a client must not set on a record (the NestJS `data:` path; free-text role fields are PRIVF only)
PRIVSTR = re.compile(r"""['"](%s)['"]""" % PRIVF)  # the field named in a string: an allowlist (`allowed = [..., 'role']`)
def stripped(txt, body):
    """True when txt removes a privileged field from, or keeps only chosen fields of, one of the client body names (`delete data.role`, `{ role, ...rest } = dto`, `pick(dto, [...])`, `plainToInstance(T, dto)`, `role: undefined`);
    the same call on another object (`pick(req.query, ...)`) hides nothing."""
    b = "|".join(map(re.escape, sorted(body)))
    # ponytail: handler-global: a pick/omit of the body anywhere in the handler hides a MASS lead, even if its result is not the name written; track the result name if that misses
    return bool(re.search(r"\bdelete\s+(?:%s)\??\.(?:%s)\b|\b(?:omit|pick|pickBy)\s*\(\s*(?:%s)\b|\b(?:plainToInstance|plainToClass)\s*\(\s*[\w$.]+\s*,\s*(?:%s)\b|\b(?:%s)\s*:\s*undefined\b|\{[^{}]*\b(?:%s)\b[^{}]*\.\.\.[\w$]+\s*\}\s*=\s*(?:await\s+)?(?:%s)\b" % (b, PRIVF, b, b, PRIVF, PRIVF, b), txt))
JSREQ = ((re.compile(r"\bawait\s+(?:req|request)\.(?:json|formData)\(\s*\)|\b(?:req|request)\.body\b"), "__body"), (re.compile(r"\b(?:req|request)\.params\b"), "__params"), (re.compile(r"\b(?:req|request)\.query\b"), "__query"))  # Express/Next request reads renamed so taint() can follow them
BCALL = re.compile(r"@Body\s*\(([^)]*)\)\s*([\w$]+)\s*\??\s*(?::\s*([\w$]+))?")  # `@Body() dto: CreateThingDto`: (argument, name, type)
PCALL = re.compile(r"@Param\s*\([^)]*\)\s*([\w$]+)")
AUTHFN = re.compile(r"\b[\w$]*(?:[Aa]uthori[sz]|[Aa]llowed|[Pp]ermit|[Vv]alidate|[Vv]erify|[Ee]nsure|[Cc]heck|[Aa]ssert|can[A-Z]|is\w*(?:Member|Admin|Owner|Editor|Lead))[\w$]*\s*\(([^()]*)\)")  # a call named for an access check, with its arguments
SINK = re.compile(r"(?:data\s*:\s*|\.\.\.\s*)([\w$]+)\b(?![\w$.(\[])")  # a whole name passed as write data: `data: dto`, `...dto`
DTOS = {}  # type name -> property names of a class of that name, filled lazily by dto_props()


def roots(e):
    """The identifier an expression starts from (`await`, `(`, `{ ...` skipped): `data?.uid` -> data."""
    m = re.match(r"[\s(]*(?:await\s+)?(?:\{\s*\.\.\.\s*)?([\w$]+)", e)
    return m[1] if m else ""


def taint(txt, seeds, loose=False):
    """Names that hold the seed data, a set: seeds, then every name assigned, destructured, looped or mapped from one, and every parameter a call passes one to (by position, signatures read from txt). loose: an assignment whose right side merely uses a seed counts (`const row = await this.find(pathId)`, the record the path id loads). ponytail: names are global in txt, no scopes."""
    s, sigs = set(seeds), {}
    if not s: return s
    hit = (lambda e: re.search(r"(?<![\w$.])(?:%s)\b" % "|".join(map(re.escape, s)), e)) if loose else (lambda e: roots(e) in s)
    for m in re.finditer(r"(?<![\w$.])([\w$]+)\s*\(([^()]*)\)\s*(?::[^{;=]*)?\{", txt):
        if m[1] not in ("if", "for", "while", "switch", "catch"): sigs[m[1]] = [re.split(r"[:=?]", a)[0].strip() for a in m[2].split(",")]
    for _ in range(3):
        n = len(s)
        for m in re.finditer(r"(?:const|let|var)\s+(\w[\w$]*)\s*(?::[^=\n]+)?=\s*([^;\n]*)", txt):
            if hit(m[2]): s.add(m[1])
        for m in re.finditer(r"(?:const|let|var)\s+\{([^}]*)\}\s*=\s*([^;\n]*)", txt):
            if roots(m[2]) in s: s |= {x.split(":")[-1].split("=")[0].strip().lstrip(".") for x in m[1].split(",")}
        for m in re.finditer(r"for\s*\(\s*(?:const|let|var)\s+(\w[\w$]*)\s+of\s+([^)]*)\)", txt):
            if roots(m[2]) in s: s.add(m[1])
        for m in re.finditer(r"([\w$]+)(?:\?\.|\.)(?:map|forEach|filter|flatMap|some|every)\(\s*(?:async\s*)?\(?\s*([\w$]+)", txt):
            if m[1] in s: s.add(m[2])
        for m in re.finditer(r"(?<![\w$])(?:this\.)?(?:[\w$]+\.)?([\w$]+)\s*\(([^()]*)\)", txt):
            for i, a in enumerate(m[2].split(",")):
                if m[1] in sigs and i < len(sigs[m[1]]) and roots(a) in s and sigs[m[1]][i]: s.add(sigs[m[1]][i])
        if len(s) == n: break
    return s - {""}


def dto_props(root, name):
    """Property names declared in `class <name> {` anywhere under root (the tree is walked once, then cached). Empty for a name no class has."""
    if not DTOS:
        DTOS[None] = set()
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if x not in SKIP_DIR]
            for f in fs:
                if not f.endswith((".ts", ".js")) or TEST.search(f): continue
                t = read(root, os.path.relpath(os.path.join(d, f), root)) or ""
                for m in re.finditer(r"\bclass\s+(\w[\w$]*)\b[^{]*\{", t):
                    DTOS[m[1]] = DTOS.get(m[1], set()) | set(re.findall(r"^\s*(?:readonly\s+)?([\w$]+)\s*[?!]?\s*[:=]", t[m.end():close_of(t, m.end() - 1)], re.M))
    return DTOS.get(name, set())


def guarded(txt, priv, before=-1):
    """True when an `if` throws Forbidden/401/403 in its own consequent or its `else` (a `{}` block, or one statement ended at `;` or a newline) and its condition names a privileged field (`if (ok || m.uid === p.createdBy) { return true } else { throw new ForbiddenException() }`), or, with `before` set, calls an access check (AUTHFN: `isMemberAllowedToEdit(...)`) and sits before `before` (the first write). The AUTHFN form does not read the field: it only says some access check ran first. A Forbidden elsewhere in the handler is no check on the field."""
    p = "|".join(map(re.escape, sorted(priv)))
    end = lambda t, at: close_of(t, at) if t[at] == "{" else min([i for i in (t.find(";", at), t.find("\n", at)) if i >= 0] or [-1])
    for m in re.finditer(r"\bif\s*\(", txt):
        c = close_of(txt, m.end() - 1)
        if c < 0 or not (re.search(r"\b(?:%s)\b" % p, txt[m.end():c]) or m.start() < before and AUTHFN.search(txt[m.end():c])): continue
        s = txt[c + 1:].lstrip()
        if not s: continue
        at = len(txt) - len(s)
        e = end(txt, at)
        if e > 0 and re.search(r"Forbidden|40[13]|[Uu]nauthori", txt[at:e + 1]): return True
        s = txt[e + 1:].lstrip() if e > 0 else ""
        if s.startswith("else") and s[4:].strip():  # the throw may sit in the else branch of a pass-through consequent
            a2 = len(txt) - len(s) + 4 + len(s[4:]) - len(s[4:].lstrip())
            e2 = end(txt, a2)
            if e2 > 0 and re.search(r"Forbidden|40[13]|[Uu]nauthori", txt[a2:e2 + 1]): return True
    return False


def sing(s):
    """Lowercase singular of a route segment or key base, separators dropped: `team-members` -> teammember, `categories` -> category, `addresses` -> address, `people` -> person."""
    s = re.sub(r"[-_]", "", s.lower())
    s = {"people": "person", "children": "child"}.get(s, s)
    return s[:-3] + "y" if s.endswith("ies") else s[:-2] if re.search(r"(?:ss|x|ch|sh)es$", s) else s[:-1] if s.endswith("s") and not s.endswith("ss") else s


def authz_leads(rows, root):
    """[(row, kind, why)] for authenticated NestJS write routes and Express / Next.js (app route handlers, pages/api) write handlers (req.body, req.params, `await req.json()`; one hop, no service layer) (CWE-915 mass assignment, CWE-639, CWE-863; OWASP API3:2023, API1:2023). Report-only leads, never proof: a text scan of the member and one hop into the service (service_text), client names followed by taint().
    MASS: the client body reaches a write as data (`data: dto`, `...dto`, or a name tainted by it) and can carry a privileged field (PRIVF: role, admin, verified, owner or createdBy ids) that the @Body type declares, a string allowlist names or the code reads off the body, with no removal or pick of the body (stripped(): a pick or omit of another object hides nothing). MASS-CHECKED: the same, but an `if` naming the field throws Forbidden or 401/403 in its consequent or `else` branch, or an `if` that calls an access check (AUTHFN) before the write throws (that form does not read the field: the row says so; the check is read, not judged: a wrong one still passes, except a gate on lodash `isEmpty(x.<boolean field>)`, which never fires and counts as no check). NestJS also has a narrow path: an owner-id field (`*MemberUid`, `*TeamUid`, `ownerId`, `authorId`, `userId`, `createdBy*`) read off the body inside a `data:` object, never from `where:` or free-text role fields; silent behind an Admin guard.
    IDMIX: an access-check call (AUTHFN) takes a path value while a write's `where` keys id/uid on a client body value and names no path value, so the check covers another record than the write.
    CHILD: a write sets a parent key (`teamUid`, `projectId`: a path parameter's name or the collection above one, not any `*Id`) from a client body value on a route with a path parameter, no path value sits in that write and no statement compares the body key to the path value, so the child can land under a parent the requester was never checked against.
    MASS-ADMIN: a MASS lead on a NestJS handler behind a class- or method-level `@UseGuards(...Admin...)`: info only. Limit: Express/Next `data: req.body` with no privileged field named anywhere (no DTO) stays silent; the privileged field must be named in the handler. Mongoose/Sequelize coverage is partial: `create`/`save`/`upsert` with a trailing options argument are not flagged, and a whole `req.body` passed positionally is not flagged (Prisma `data: req.body` is). The owner-id path also matches any `*MemberUid`/`*TeamUid`/`userId` reference.
    ponytail: names are global per route, one service hop, no inheritance; silence is not proof."""
    out, cache = [], SVC_CACHE
    for r in rows:
        rel, ln, meth, route, lab = r
        nest = (rel, ln) in NESTCTX
        if not (nest or (rel, ln) in BODY and rel.endswith(tuple(x for x in EXT if x != ".py"))) or lab in ("none", "public", "presence-check") or not set(meth.split("|")) & {"POST", "PUT", "PATCH", "DELETE", "ANY"}: continue
        own = BODY.get((rel, ln), "")
        if nest:
            types = NESTCTX[(rel, ln)][1]
            txt = own + "\n" + service_text(root, own, types, cache)[0]
            bs = BCALL.findall(txt)
            body = taint(txt, {b[1] for b in bs})
            path = taint(txt, set(PCALL.findall(txt)) or set(re.findall(r"/:(\w+)", route)), True)
        else:  # Express / Next.js handler: ponytail: the handler text and the same-file helpers it calls, no service hop
            txt, bs = own, []
            for rx, nm in JSREQ: txt = rx.sub({"__query": "__params" if re.search(r"(?:^|/)pages/api/", rel) else "__body"}.get(nm, nm), txt)  # pages/api gets its dynamic segments in req.query; elsewhere the query string is client-chosen
            body = taint(txt, {"__body"})
            path = taint(txt, {"__params", "params"} if re.search(r"/:\w+", route) else set(), True)
        wr = [(m.end(), close_of(txt, m.end() - 1)) for m in re.finditer(WMETH, txt)]
        if not body or not wr: continue
        pp = "|".join(map(re.escape, sorted(path))) or "\0"
        bn = "|".join(map(re.escape, sorted(body)))
        def pathy(t): return re.search(r"(?<![\w$.])(?:%s)\b(?!\s*:)" % pp, t)  # a path value used, not a key of that name
        fields = lambda rx: {p for b in bs for p in dto_props(root, b[2]) if re.fullmatch(rx, p)} | set(re.findall(r"\b(?:%s)\.(%s)\b" % (bn, rx), txt)) | {p for m in re.finditer(r"\{([^{}]*)\}\s*=\s*(?:await\s+)?(?:%s)\b" % bn, txt) for p in re.findall(r"[\w$]+", m[1]) if re.fullmatch(rx, p)}  # names a DTO declares, the code reads off the body, or destructures from it
        priv = fields(PRIVF) | set(PRIVSTR.findall(txt))
        ownp = fields(OWNID)  # NestJS: an owner/author id written in a `data:` object, the narrow path (no free-text role fields)
        # direct(): a field read off the body into a name, then written as data (`{ name, role }`) or read in place (`role: body.role`)
        def blank(t, o, c): return t[:o] + " " * (c + 1 - o) + t[c + 1:]
        def nowhere(t):  # the write call with its filter blanked: `where: {..}`, and a first positional object followed by a second argument (Mongoose `findOneAndUpdate(filter, update)`, TypeORM `update(criteria, data)`; Sequelize `update(values, { where })` keeps its values)
            f, first = re.match(r"\s*\{", t), None
            if f:
                c = close_of(t, f.end() - 1)
                if c > 0 and t[c + 1:].lstrip().startswith(",") and not re.match(r",\s*\{[^{}]*\bwhere\b", t[c + 1:].lstrip()): first = (f.end() - 1, c)
            for w in list(re.finditer(r"where\s*:\s*\{", t))[::-1]:
                c = close_of(t, w.end() - 1)
                if c > 0: t = blank(t, w.start(), c)
            return blank(t, *first) if first else t
        def dspan(t):  # only the `data: {..}` objects of a write call
            return " ".join(t[w.end() - 1:close_of(t, w.end() - 1) + 1] for w in re.finditer(r"\bdata\s*:\s*\{", t))
        def direct(t, fs):
            pf, af = "|".join(map(re.escape, sorted(fs & body))) or "\0", "|".join(map(re.escape, sorted(fs))) or "\0"
            return re.search(r"[{,]\s*(?:%s)\s*(?=[,}])|:\s*(?:%s)\b(?![\w$.(\[])|\b(?:%s)\??\.(?:%s)\b" % (pf, pf, bn, af), t)
        adm = re.search(r"@UseGuards\s*\([^)]*Admin", NESTCTX[(rel, ln)][0] + "\n" + own) if nest else None  # behind an admin guard the privileged write is the intended caller's: info only
        wide = priv and any(m[1] in body for a, e in wr for m in SINK.finditer(txt[a:e])) or priv and re.search(r"\b(?:copyObj|assign)\w*\(\s*(?:%s)\b" % bn, txt) or not nest and priv and any(direct(nowhere(txt[a:e]), priv) for a, e in wr)
        narrow = nest and ownp and any(direct(dspan(txt[a:e]), ownp) for a, e in wr) and not adm  # an admin sets owners by design: the narrow path stays silent there
        if wide or narrow:
            if not stripped(txt, body):
                fl = priv | ownp if nest else priv
                dtxt = DEADGATE.sub("if (DEADGATE)", txt)
                named = guarded(dtxt, fl)
                chk = named or guarded(dtxt, fl, min(a for a, _ in wr))
                out.append((r, "MASS-CHECKED" if chk else "MASS-ADMIN" if adm else "MASS", "client body reaches a write with %s unfiltered%s" % ("/".join(sorted(fl)), "; a check naming it is read" if named else "; an access check before the write is read (it does not name the field)" if chk else "")))
        authed = {a for m in AUTHFN.finditer(txt) for a in re.findall(r"[\w$]+", m[1] if nest else re.sub(r"\b(?:__params|params)\b(?!\s*\??\.\s*[\w$])", "", m[1])) if a in path}  # JS: a bare req.params (`schema.validate(req.params)`) is no access check on a path member
        for a, e in wr:
            w = re.search(r"where\s*:\s*\{", txt[a:e])
            if w and authed:
                o = a + w.end() - 1
                wt = txt[o:close_of(txt, o) + 1]
                for k, v in re.findall(r"([\w$]+)\s*:\s*([^,{}]+)", wt):
                    if k in ("id", "uid", "_id") and roots(v) in body and not pathy(wt):
                        out.append((r, "IDMIX", ("access check on path value %s but the write's where %s is client body value %s" % ("/".join(sorted(authed)), k, v.strip())).replace("__body", "req.body").replace("__params", "req.params")))
                        break
            ks = [(k, v.replace("?.", ".")) for k, v in re.findall(r"\b([\w$]*(?:Uid|Id))\s*:\s*([\w$]+(?:\??\.[\w$]+)+)", txt[a:e]) + [(k, k) for k in re.findall(r"[{,]\s*([\w$]*(?:Uid|Id))\s*(?=[,}])", txt[a:e])] + re.findall(r"\b([\w$]*(?:Uid|Id))\s*:\s*([\w$]+)\s*(?=[,}])", txt[a:e]) if k not in ("id", "uid")]  # dotted, shorthand (`{ teamId }`) or bare-name (`teamId: teamId`, destructured off the body) keys
            segs = [s.lower() for s in re.findall(r"/([\w-]+)/:", route)]  # a body key is a parent key only when it names a path parameter or the collection above one (`teamId` under `/teams/:id`), not a sibling reference (`memberUid`)
            ks = [x for x in ks if roots(x[1]) in body and (x[0] in path or x[0] in re.findall(r"/:(\w+)", route) or any(sing(s) == sing(re.sub(r"(?:Uid|Id)$", "", x[0])) for s in segs))]
            if ks and path and not pathy(txt[a:e]) and not any(re.search(r"[\w$]+\.%s\s*[!=]==?\s*(?:%s)\b|(?<![\w$.])(?:%s)\s*[!=]==?\s*[\w$]+\.%s\b" % (k, pp, pp, k), txt.replace("?.", ".")) for k, _ in ks):
                out.append((r, "CHILD", ("write sets parent key %s from client body value %s; no path value in the write and no comparison to one" % ks[-1]).replace("__body", "req.body").replace("__params", "req.params")))  # the last key: a composite where lists the parent last
    seen = set()
    return [x for x in out if not (x[:2] in seen or seen.add(x[:2]))]


def unjudged(root):
    """[(file, line, count, METHOD, path)] per file of other_routes() (Go, Spring, Kotlin, PHP, Django urlconfs; auth is never judged for these) that accepts a state-changing method (anything but GET/HEAD/OPTIONS; ANY counts). One row per file: count of such routes and the first one by line. Reads-the-handler leads, never HIGH."""
    by = {}
    for m, p, f, ln in other_routes(root):
        if any(x not in ("GET", "HEAD", "OPTIONS") for x in m.split("|")): by.setdefault(f, []).append((ln, m, p))
    return [(f, first[0], len(x), first[1], first[2]) for f, x in sorted(by.items()) for first in [min(x)]]


def cl(s):
    """s with every control character (a tab, newline or carriage return in a file name or route) as `?`: review_checks.sh splits a row at tabs and lines, so one would cut it."""
    return "".join(c if c.isprintable() else "?" for c in s)


def main(argv):
    a = [x for x in argv[1:] if x not in ("--paths", "--all", "--privileged")]
    if len(a) != 1 or not os.path.isdir(a[0]) or len({"--paths", "--all", "--privileged"} & set(argv[1:])) > 1:
        print("usage: route_auth_map.py [--paths | --all | --privileged] DIR", file=sys.stderr); return 2
    if {"--paths", "--all"} & set(argv[1:]):
        inv = inventory(a[0])
        print("heuristic; %d routes; silence is not proof of authentication" % len(inv), file=sys.stderr)
        print(coverage(), file=sys.stderr)
        if "--all" in argv[1:]:
            from attempt_limit_map import units  # lazy: it imports this module
            texts = {}
            view = {g: (f, u[0]) for f, us in units(a[0], texts).items() for u in us for g in u[4]}  # django: the resolved view's def line, else the urls.py line
            for m, p, f, ln in inv:
                t = texts.get(f) or ""
                if "urlpatterns" in t and DJ.search(t.split("\n")[ln - 1]): f, ln = view.get((f, ln), (f, ln))
                print("%s %s %s:%d" % (m, p, f, ln))
        else:
            for p in sorted({p for m, p, f, ln in inv if m in ("GET", "ANY")}): print(p)
        return 0
    rows, files = scan(a[0])
    if "--privileged" in argv[1:]:
        pv = privileged(rows)
        print("heuristic; %d privileged routes with authentication but no role check; silence is not proof" % len(pv), file=sys.stderr)
        for r, why in pv: print(cl("%s:%d: PRIV: %s %s auth=%s (%s)" % (*r[:2], *r[2:], why)))
        ow = ownership(rows, a[0], {(r[0], r[1], r[3]) for r, _ in pv})
        n = sum(1 for x in ow if x[2])
        print("heuristic; %d NestJS write routes with authentication but no requester-to-owner check (OWN), %d with a check the scan read (OWN-CHECKED); silence is not proof" % (len(ow) - n, n), file=sys.stderr)
        for r, why, cls, hit in ow: print(cl("%s:%d: OWN: %s %s auth=%s (%s)" % (*r[:2], *r[2:], why) if not cls else "%s:%d: OWN-CHECKED: %s %s auth=%s (class=%s; match=%s)" % (*r[:2], *r[2:], cls, hit)))
        az = authz_leads(rows, a[0])
        print("heuristic; %d write routes (NestJS, Express, Next.js) with a client-writable privileged field, a path-vs-body id mismatch or a body-set parent key (MASS, MASS-CHECKED, MASS-ADMIN, IDMIX, CHILD); silence is not proof" % len(az), file=sys.stderr)
        for r, k, why in az: print(cl("%s:%d: %s: %s %s auth=%s (%s)" % (*r[:2], k, *r[2:], why)))
        for f, ln in SKIPPED: print(cl("%s:%d: NOT-CHECKED: a route-like decorator here gave no route, so the handler under it (and any other unparsed one in this file) was not judged for privilege or ownership; read them" % (f, ln)))
        return 0
    print("heuristic; scanned %d files with %d handlers; silence is not proof of authentication" % (files, len(rows)), file=sys.stderr)
    print(coverage(), file=sys.stderr)
    out = [(r, "HIGH" if (r[4] == "none" or r[4] == "presence-check" and (r[0], r[1]) not in FWDROWS) and any(x != "GET" and (x not in ("HEAD", "OPTIONS") or (r[0], r[1]) not in NESTSAFE) for x in r[2].split("|")) else "INFO") for r in rows]
    for r, s in out: print(cl("%s:%d: %s: %s %s auth=%s" % (r[0], r[1], s, r[2], r[3], r[4])))
    hi = [(r, s) for r, s in out if s == "HIGH"]
    uj = unjudged(a[0])
    for f, ln, n, m, p in uj: print(cl("%s:%d: UNJUDGED: %d route(s) accept state-changing methods here (first %s %s); route-auth does not judge auth for this language, read the handlers" % (f, ln, n, m, p)))
    print(json.dumps({"tool": "route_auth_map", "handlers": len(rows), "files": files, "high": len(hi), "unjudged": sum(u[2] for u in uj),
                      "findings": [{"file": r[0], "line": r[1], "severity": s, "message": "%s %s auth=%s" % r[2:]} for r, s in hi]}))
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
