#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.fetch-no-timeout, perun.js.auth-cookie-flags and
perun.js.cors-credentials-any-origin (js.yml).

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` comment marks the NEXT line as a required finding, an
`// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too (so must a
copy of each fixture under a test path). All names and values are fictional. RULES=<dir> checks another copy of the rules (used to
show the cases fail without them). The live check needs semgrep and prints SKIP without it (CI installs none); the offline checks
always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
FETCH, COOKIE, CORS = "perun.js.fetch-no-timeout", "perun.js.auth-cookie-flags", "perun.js.cors-credentials-any-origin"
IDS = (FETCH, COOKIE, CORS)

FETCH_APP = r'''
export async function GET(request) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items");
  return Response.json(await r.json());
}
export async function POST(request) {
  const body = await request.json();
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items", { method: "POST", body: JSON.stringify(body) });
  // ok: perun.js.fetch-no-timeout
  const s = await fetch("https://api.acme.example/v1/audit", { method: "POST", signal: AbortSignal.timeout(5000) });
  return Response.json([await r.json(), s.status]);
}
export async function PUT(request) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(new URL("/v1/items", UPSTREAM), { method: "PUT", headers: { accept: "application/json" } });
  return Response.json(await r.json());
}
export async function PATCH(request) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { method: "PATCH" });
  return Response.json(await r.json());
}
export async function DELETE(request) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { method: "DELETE" });
  return Response.json(await r.json());
}
app.get("/acme-api/items", async (req, res) => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items", { headers: { accept: "application/json" } });
  res.json(await r.json());
});
router.post("/acme-api/items", function (req, res) {
  // ruleid: perun.js.fetch-no-timeout
  fetch(UPSTREAM + "/v1/items", { method: "POST", body: JSON.stringify(req.body) }).then((r) => res.sendStatus(r.status));
});
fastify.delete("/acme-api/items/:id", { schema }, async (request, reply) => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items/${request.params.id}`, { method: "DELETE" });
  return reply.code(r.status).send();
});
app.all("/acme-api/*", (req, res) => {
  // ruleid: perun.js.fetch-no-timeout
  fetch(UPSTREAM);
  res.end();
});
app.patch("/acme-api/items/:id", async function (req, res) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items/${req.params.id}`, { method: "PATCH" });
  res.json(await r.json());
});

// Near misses: a signal of any kind, options that may carry one, and code that is not a request handler.
app.get("/acme-api/health", async (req, res) => {
  // ok: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/health", { signal: AbortSignal.timeout(5000) });
  res.sendStatus(r.status);
});
app.post("/acme-api/sync", async (req, res) => {
  const ctl = new AbortController();
  // ok: perun.js.fetch-no-timeout
  const a = await fetch(UPSTREAM, { method: "POST", signal: ctl.signal, body: req.body });
  // ok: perun.js.fetch-no-timeout
  const b = await fetch(UPSTREAM, { signal });
  res.json([a.status, b.status]);
});
app.put("/acme-api/items/:id", async (req, res) => {
  // ok: perun.js.fetch-no-timeout
  const r = await fetch(UPSTREAM, { ...baseInit, method: "PUT" });
  res.json(await r.json());
});
async function warmCache() {
  // ok: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/warm");
}
// ok: perun.js.fetch-no-timeout
await fetch("https://api.acme.example/v1/ping");
function ItemsWidget() {
  useEffect(() => {
    // ok: perun.js.fetch-no-timeout
    fetch("/acme-api/items").then((r) => r.json()).then(setItems);
  }, []);
}
cache.get("items", async () => {
  // ok: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/items");
});
async function GET(request) {
  // ok: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/items");
}
'''

FETCH_PAGES = r'''
export default async function handler(req, res) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`https://api.acme.example/v1/items/${req.query.id}`);
  // ruleid: perun.js.fetch-no-timeout
  const s = await fetch("https://api.acme.example/v1/stats", { headers: { accept: "application/json" } });
  // ok: perun.js.fetch-no-timeout
  const t = await fetch("https://api.acme.example/v1/slow", { signal: AbortSignal.timeout(2000) });
  res.status(200).json([await r.json(), await s.json(), await t.json()]);
}
'''

# Next route handlers declared as a const arrow (no parameters, one or two), with the methods HEAD and OPTIONS. A signal, a spread
# options object and an export that is not a method name stay clean.
FETCH_ARROWS = r'''
export const GET = async () => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items");
  return Response.json(await r.json());
};
export const POST = async (request) => {
  const body = await request.json();
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items", { method: "POST", body: JSON.stringify(body) });
  return Response.json(await r.json());
};
export const HEAD = async (request, context) => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { method: "HEAD" });
  return new Response(null, { status: r.status });
};
export const OPTIONS = async (request) => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { method: "OPTIONS" });
  return new Response(null, { status: r.status });
};
export const DELETE = async () => {
  // ok: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { method: "DELETE", signal: AbortSignal.timeout(5000) });
  return new Response(null, { status: r.status });
};
export const PATCH = async (request) => {
  // ok: perun.js.fetch-no-timeout
  const r = await fetch(`${UPSTREAM}/v1/items`, { ...baseInit, method: "PATCH" });
  return Response.json(await r.json());
};
export const getStats = async () => {
  // ok: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/stats");
  return Response.json(await r.json());
};
'''

# Next route handlers declared as a plain export function (not async): GET, HEAD and OPTIONS, with and without parameters.
FETCH_FUNCS = r'''
export function GET(request) {
  // ruleid: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/items");
}
export function HEAD() {
  // ruleid: perun.js.fetch-no-timeout
  return fetch(`${UPSTREAM}/v1/items`, { method: "HEAD" });
}
export function OPTIONS(request, context) {
  // ruleid: perun.js.fetch-no-timeout
  return fetch(`${UPSTREAM}/v1/items`, { method: "OPTIONS" });
}
export function POST(request) {
  // ok: perun.js.fetch-no-timeout
  return fetch(UPSTREAM, { method: "POST", signal: AbortSignal.timeout(5000) });
}
export function PUT(request) {
  // ok: perun.js.fetch-no-timeout
  return fetch(UPSTREAM, { ...baseInit, method: "PUT" });
}
export function loadItems() {
  // ok: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/items");
}
'''

# A typed Next.js handler and typed pages API handler: the TypeScript parser must reach them too.
FETCH_TS = r'''
export async function GET(request: NextRequest): Promise<Response> {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch(`https://api.acme.example/v1/items?q=${request.nextUrl.searchParams.get("q")}`);
  return Response.json(await r.json());
}
export const PUT = async (request: NextRequest): Promise<Response> => {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items", { method: "PUT", body: await request.text() });
  return Response.json(await r.json());
};
export function POST(request: NextRequest): Promise<Response> {
  // ruleid: perun.js.fetch-no-timeout
  return fetch("https://api.acme.example/v1/items", { method: "POST", body: request.body });
}
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  // ruleid: perun.js.fetch-no-timeout
  const r = await fetch("https://api.acme.example/v1/items", { method: "POST", body: JSON.stringify(req.body) });
  // ok: perun.js.fetch-no-timeout
  const s = await fetch("https://api.acme.example/v1/items", { signal: AbortSignal.timeout(2000) });
  res.status(r.status).json(await s.json());
}
'''

COOKIE_JS = r'''
app.post("/acme-api/login", (req, res) => {
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("session", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("auth_token", token, { httpOnly: true });
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("sid", sid, { secure: true });
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("jwt", jwt, { httpOnly: false, secure: true });
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("session", token, { httpOnly: true, secure: false });
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("session", token, { secure: false, httpOnly: true });
  res.end();
});
app.post("/acme-api/names", (req, res) => {
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("connect.sid", sid);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("authToken", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("access-token", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("next-auth.session-token", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("__Host-session", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("PHPSESSID", sid);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("sessionid", sid);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("appSession", token);
  // ruleid: perun.js.auth-cookie-flags
  res.cookie("sessionKey", token);
  res.end();
});
fastify.post("/acme-api/login", async (request, reply) => {
  // ruleid: perun.js.auth-cookie-flags
  reply.setCookie("session", token, { path: "/", maxAge: 3600 });
  // ruleid: perun.js.auth-cookie-flags
  return reply.setCookie("Session-ID", token, { httpOnly: true });
});
export async function POST(request) {
  // ruleid: perun.js.auth-cookie-flags
  cookies().set("auth_token", token, { httpOnly: true });
  // ruleid: perun.js.auth-cookie-flags
  cookies().set({ name: "session", value: token, httpOnly: true });
  // ruleid: perun.js.auth-cookie-flags
  cookies().set({ secure: true, name: "session", value: token });
  // ruleid: perun.js.auth-cookie-flags
  (await cookies()).set("jwt", token);
  const response = NextResponse.json({});
  // ruleid: perun.js.auth-cookie-flags
  response.cookies.set("session-token", token, { secure: true });
  // ruleid: perun.js.auth-cookie-flags
  res.cookies.set("session", token);
  // ruleid: perun.js.auth-cookie-flags
  response.cookies.set("session", v);
  return response;
}

// Receivers whose libraries default httpOnly (and secure over HTTPS) on: only a literal false is reported there.
router.post("/acme-api/login", (ctx) => {
  // ruleid: perun.js.auth-cookie-flags
  ctx.cookies.set("session", v, { httpOnly: false });
  // ruleid: perun.js.auth-cookie-flags
  ctx.cookies.set("session", v, { httpOnly: true, secure: false });
  // ruleid: perun.js.auth-cookie-flags
  ctx.cookies.set({ name: "sid", value: v, secure: false });
  // ruleid: perun.js.auth-cookie-flags
  context.cookies.set("auth_token", v, { secure: false });
  // ruleid: perun.js.auth-cookie-flags
  this.cookies.set("jwt", v, { httpOnly: false });
  // ruleid: perun.js.auth-cookie-flags
  event.cookies.set("session", v, { path: "/", secure: false });
  // ruleid: perun.js.auth-cookie-flags
  cookies.set("sessionid", v, { path: "/", httpOnly: false });
  // ruleid: perun.js.auth-cookie-flags
  cookies.set({ name: "session", value: v, httpOnly: false });
});

// A cookies() store bound to a variable is a response store like cookies().set: a missing or literal-false flag is reported.
export async function PUT(request) {
  const cookieStore = await cookies();
  // ruleid: perun.js.auth-cookie-flags
  cookieStore.set("session", t);
  // ruleid: perun.js.auth-cookie-flags
  cookieStore.set({ name: "session", value: t, httpOnly: true });
  // ruleid: perun.js.auth-cookie-flags
  cookieStore.set("sid", t, { httpOnly: true, secure: false });
}
export function PATCH(request) {
  let jar = cookies();
  // ruleid: perun.js.auth-cookie-flags
  jar.set("authToken", t, { httpOnly: true });
}

// Near misses: both flags (either order, any value but a literal false), other cookie names, csrf cookies, clears,
// request-side cookies, options or names that are not literals, and (below) the library-default receivers.
app.get("/acme-api/prefs", (req, res) => {
  // ok: perun.js.auth-cookie-flags
  res.cookie("session", token, { httpOnly: true, secure: true, sameSite: "lax" });
  // ok: perun.js.auth-cookie-flags
  res.cookie("sid", sid, { secure: process.env.NODE_ENV === "production", httpOnly: true });
  // ok: perun.js.auth-cookie-flags
  reply.setCookie("auth", token, { httpOnly: true, secure });
  // ok: perun.js.auth-cookie-flags
  res.cookie("session", token, { httpOnly, secure: true });
  // ok: perun.js.auth-cookie-flags
  cookies().set({ name: "session", value: token, httpOnly: true, secure: true });
  // ok: perun.js.auth-cookie-flags
  res.cookie("session", token, opts);
  // ok: perun.js.auth-cookie-flags
  res.cookie("session", token, { ...base, path: "/" });
  // ok: perun.js.auth-cookie-flags
  res.cookie(name, token);
  res.end();
});
app.get("/acme-api/names", (req, res) => {
  // ok: perun.js.auth-cookie-flags
  res.cookie("authorized", "yes");
  // ok: perun.js.auth-cookie-flags
  res.cookie("tokenizer_mode", "fast");
  // ok: perun.js.auth-cookie-flags
  res.cookie("assessment", "done");
  // ok: perun.js.auth-cookie-flags
  res.cookie("csrftoken", token);
  // ok: perun.js.auth-cookie-flags
  res.cookie("XSRF-TOKEN", token);
  // ok: perun.js.auth-cookie-flags
  res.cookie("csrf_token", token);
  // ok: perun.js.auth-cookie-flags
  res.cookie("_csrf", token);
  // ok: perun.js.auth-cookie-flags
  res.cookie("theme", "dark");
  // ok: perun.js.auth-cookie-flags
  res.cookie("sidebar_state", "open");
  res.end();
});
app.post("/acme-api/logout", (req, res) => {
  // ok: perun.js.auth-cookie-flags
  res.cookie("session", "", { path: "/" });
  // ok: perun.js.auth-cookie-flags
  res.cookie("sid", sid, { maxAge: 0 });
  // ok: perun.js.auth-cookie-flags
  cookies().set("session", token, { expires: new Date(0) });
  // ok: perun.js.auth-cookie-flags
  cookies().set({ name: "session", value: "", path: "/" });
  res.end();
});
export function middleware(request) {
  // ok: perun.js.auth-cookie-flags
  request.cookies.set("session", token);
  // ok: perun.js.auth-cookie-flags
  req.cookies.set("auth_token", token);
  // ok: perun.js.auth-cookie-flags
  event.request.cookies.set("session", token);
  // ok: perun.js.auth-cookie-flags
  cookieStore.set("session", token, { maxAge: 60 });
  // ok: perun.js.auth-cookie-flags
  Cookies.set("auth_token", token);
  // ok: perun.js.auth-cookie-flags
  cache.set("session", value);
}
// Receivers whose libraries default httpOnly (and secure over HTTPS) on: a missing flag passes.
router.get("/acme-api/prefs", (ctx) => {
  // ok: perun.js.auth-cookie-flags
  ctx.cookies.set("session", v);
  // ok: perun.js.auth-cookie-flags
  context.cookies.set("auth_token", v, { maxAge: 3600 });
  // ok: perun.js.auth-cookie-flags
  this.cookies.set("jwt", v);
  // ok: perun.js.auth-cookie-flags
  event.cookies.set("session", v, { path: "/" });
  // ok: perun.js.auth-cookie-flags
  cookies.set("sessionid", v, { path: "/" });
  // ok: perun.js.auth-cookie-flags
  cookies.set({ name: "session", value: v });
  // ok: perun.js.auth-cookie-flags
  ctx.cookies.set("session", v, { httpOnly: true, secure: true });
  // ok: perun.js.auth-cookie-flags
  event.cookies.set("session", v, { path: "/", secure: process.env.NODE_ENV === "production" });
});
// A bound store with both flags passes, as do other names and clears; a .set on anything not bound from cookies()
// (the browser Cookie Store API, a cache, a parameter named like a store) passes even beside a bound store.
export async function DELETE(request) {
  const cookieStore = await cookies();
  // ok: perun.js.auth-cookie-flags
  cookieStore.set("session", t, { httpOnly: true, secure: true });
  // ok: perun.js.auth-cookie-flags
  cookieStore.set("theme", "dark");
  // ok: perun.js.auth-cookie-flags
  cookieStore.set("session", "", { maxAge: 0 });
}
export async function OPTIONS(request) {
  const jar = await cookies();
  let plain = cookies();
  // ok: perun.js.auth-cookie-flags
  cookieStore.set("session", t);
  // ok: perun.js.auth-cookie-flags
  cache.set("session", t);
  return Response.json({ id: jar.get("id"), n: plain.get("n") });
}
export function HEAD(jar) {
  // ok: perun.js.auth-cookie-flags
  jar.set("session", t);
}
'''

CORS_JS = r'''
// ruleid: perun.js.cors-credentials-any-origin
app.register(cors, { origin: true, credentials: true });
// ruleid: perun.js.cors-credentials-any-origin
fastify.register(fastifyCors, { credentials: true, origin: true });
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ origin: /.*/, credentials: true }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, cb) => cb(null, true) }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, cb) => cb(null, origin) }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, cb) => cb(null, !!origin) }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, callback) => { callback(null, true); } }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, cb) => { cb(null, origin); } }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ credentials: true, origin: (origin, cb) => { cb(null, !!origin); } }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ origin: function (origin, cb) { cb(null, true); }, credentials: true }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ origin: function (origin, cb) { cb(null, origin); }, credentials: true }));
// ruleid: perun.js.cors-credentials-any-origin
app.use(cors({ origin: function (origin, cb) { cb(null, !!origin); }, credentials: true }));
export async function GET(request) {
  const headers = new Headers();
  // ruleid: perun.js.cors-credentials-any-origin
  headers.set("Access-Control-Allow-Origin", request.headers.get("origin") ?? "");
  headers.set("Access-Control-Allow-Credentials", "true");
  return new Response("{}", { headers });
}
app.get("/acme-api/me", (req, res) => {
  // ruleid: perun.js.cors-credentials-any-origin
  res.set("Access-Control-Allow-Origin", req.get("origin"));
  res.set("Access-Control-Allow-Credentials", "true");
  res.json({});
});
app.use(function (req, res, next) {
  const o = req.header("Origin");
  // ruleid: perun.js.cors-credentials-any-origin
  res.header("Access-Control-Allow-Origin", o);
  res.header("Access-Control-Allow-Credentials", "true");
  next();
});
app.get("/acme-api/boolean", (req, res) => {
  // ruleid: perun.js.cors-credentials-any-origin
  res.setHeader("Access-Control-Allow-Origin", req.header("Origin"));
  res.setHeader("Access-Control-Allow-Credentials", true);
  res.end();
});
app.options("/acme-api/*", (req, res) => {
  const o = req.get("Origin");
  if (req.accepts("json")) res.status(204);
  // ruleid: perun.js.cors-credentials-any-origin
  res.set("Access-Control-Allow-Origin", o);
  res.set("Access-Control-Allow-Credentials", "true");
  res.end();
});

// Near misses: a named origin or allowlist, a literal "*" (browsers refuse it on credentialed requests), no credentials,
// credentials false, a header that is not the origin header, and a reflected origin checked against an allowlist first.
// ok: perun.js.cors-credentials-any-origin
app.register(fastifyCors, { credentials: true, origin: "*" });
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: "*", credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.register(cors, { origin: "https://app.acme.example", credentials: true });
// ok: perun.js.cors-credentials-any-origin
app.register(cors, { origin: true });
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: "*" }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: ALLOWED, credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: (o, cb) => cb(null, ALLOWED.has(o)), credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: (o, cb) => cb(null, other), credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: (o, cb) => { cb(null, ALLOWED.has(o)); }, credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: (o, cb) => { if (ALLOWED.has(o)) { cb(null, true); } else { cb(new Error("origin")); } }, credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.use(cors({ origin: function (o, cb) { if (ALLOWED.includes(o)) cb(null, true); else cb(new Error("origin")); }, credentials: true }));
// ok: perun.js.cors-credentials-any-origin
app.register(cors, { origin: true, credentials: false });
// ok: perun.js.cors-credentials-any-origin
app.register(sensiblePlugin, { origin: true, credentials: true });
export async function POST(request) {
  const headers = new Headers();
  // ok: perun.js.cors-credentials-any-origin
  headers.set("Access-Control-Allow-Origin", "https://app.acme.example");
  headers.set("Access-Control-Allow-Credentials", "true");
  return new Response("{}", { headers });
}
export async function PUT(request) {
  const headers = new Headers();
  // ok: perun.js.cors-credentials-any-origin
  headers.set("Access-Control-Allow-Origin", request.headers.get("origin") ?? "");
  return new Response("{}", { headers });
}
app.get("/acme-api/echo", (req, res) => {
  // ok: perun.js.cors-credentials-any-origin
  res.set("X-Acme-Echo", req.get("origin"));
  res.set("Access-Control-Allow-Credentials", "true");
  res.json({});
});
app.get("/acme-api/off", (req, res) => {
  // ok: perun.js.cors-credentials-any-origin
  res.set("Access-Control-Allow-Origin", req.get("origin"));
  res.set("Access-Control-Allow-Credentials", "false");
  res.json({});
});
app.get("/acme-api/has", (req, res) => {
  const o = req.header("Origin");
  if (ALLOWED.has(o)) {
    // ok: perun.js.cors-credentials-any-origin
    res.header("Access-Control-Allow-Origin", o);
  }
  res.header("Access-Control-Allow-Credentials", "true");
  res.end();
});
app.get("/acme-api/includes", (req, res) => {
  if (ALLOWED.includes(req.get("origin"))) {
    // ok: perun.js.cors-credentials-any-origin
    res.set("Access-Control-Allow-Origin", req.get("origin"));
  }
  res.set("Access-Control-Allow-Credentials", "true");
  res.end();
});
app.get("/acme-api/test", (req, res) => {
  const o = req.header("Origin");
  // ok: perun.js.cors-credentials-any-origin
  if (ALLOWED_RE.test(o)) res.header("Access-Control-Allow-Origin", o);
  res.header("Access-Control-Allow-Credentials", "true");
  res.end();
});
app.use(function (req, res, next) {
  const o = req.header("Origin");
  if (!ALLOWED.has(o)) return next();
  // ok: perun.js.cors-credentials-any-origin
  res.header("Access-Control-Allow-Origin", o);
  res.header("Access-Control-Allow-Credentials", "true");
  next();
});
app.get("/acme-api/else", (req, res) => {
  const o = req.header("Origin");
  if (ALLOWED.has(o)) {
    // ok: perun.js.cors-credentials-any-origin
    res.header("Access-Control-Allow-Origin", o);
  } else {
    res.status(403);
  }
  res.header("Access-Control-Allow-Credentials", "true");
  res.end();
});
'''

FILES = {
    "app/api/acme-api/route.js": FETCH_APP, "app/api/acme-api/route.ts": FETCH_APP, "pages/api/acme-api/items.js": FETCH_PAGES,
    "pages/api/acme-api/typed.ts": FETCH_TS, "app/auth/login.js": COOKIE_JS, "app/auth/login.ts": COOKIE_JS,
    "app/web/cors.js": CORS_JS, "app/web/cors.ts": CORS_JS,
    "app/api/acme-arrows/route.js": FETCH_ARROWS, "app/api/acme-arrows/route.ts": FETCH_ARROWS,
    "app/api/acme-funcs/route.js": FETCH_FUNCS, "app/api/acme-funcs/route.ts": FETCH_FUNCS,
}
# Test, fixture and mock paths are excluded from every one of these rules: nothing in these copies may be reported.
SKIPPED = {"tests/route.test.js": FETCH_APP, "app/login.spec.ts": COOKIE_JS, "app/fixtures/cors.js": CORS_JS,
           "tests/arrows.test.js": FETCH_ARROWS, "app/funcs.spec.ts": FETCH_FUNCS}
ANN = re.compile(r"^\s*(?://|#)\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= set(IDS), out
    return out


# Offline: the spec's floor of 3 findings and 3 near misses per rule, counted over distinct fixtures (the .js and .ts copies
# of one fixture are one set of cases).
for rid in IDS:
    for kind in ("ruleid", "ok"):
        n = sum(1 for body in {*FILES.values()} for _, r in annotated(body, kind) if r == rid)
        assert n >= 3, (rid, kind, n)
assert all(annotated(b, "ok") and annotated(b, "ruleid") for b in FILES.values())
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES, *SKIPPED],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.<lang>.<name> tail
    for x in r["results"]:
        rid = "perun." + x["check_id"].rsplit("perun.", 1)[-1]
        if rid in IDS:
            got.add((x["path"], x["start"]["line"], rid))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: ids, severities, shared test-path exclusions, and the regexes (semgrep anchors metavariable-regex at the start,
# as Python's re.match does) that carry the precision. CI installs no semgrep, so each guard the live fixtures prove is
# pinned here too: dropping one fails this file even when the live part is skipped.
JS = open(os.path.join(RULES, "js.yml")).read()
block = lambda rid: JS.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
excl = lambda b: (re.search(r"paths:\n\s+exclude: (\[.*\])", b) or [0, 0])[1]
for rid, sev in ((FETCH, "INFO"), (COOKIE, "WARNING"), (CORS, "WARNING")):
    b = block(rid)
    assert f"  severity: {sev}\n" in b and JS.count(f"- id: {rid}\n") == 1, rid
    assert excl(b) and excl(b) == excl(block("perun.js.hardcoded-credential-compare")), f"{rid} skips the credential rules' test paths"
rx = lambda b, mv: re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", b)
fb, kb, cb = block(FETCH), block(COOKIE), block(CORS)
assert fb.count("pattern-not: ") == 2 and fb.count("signal: $S") == 1 and "...$X" in fb, "a signal option or a spread exempts the call"
assert "regex: ^[/*]" in fb and "get|post|put|patch|delete|all" in fb, "route path and verb guards"
mh = rx(fb, "M")
assert len(mh) == 1 and all(re.match(mh[0], s) for s in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")), mh
assert not any(re.match(mh[0], s) for s in ("Get", "GET2", "getStats", "handler", "ALL", "TRACE", "")), mh
assert all(s in fb for s in ("export async function $M(...) {...}", "export function $M(...) {...}", "export const $M = async (...) => {...}")), "Next handler forms"
assert "export default async function handler(...) {...}" in fb and fb.count("pattern-inside: $A.$H(") == 4, "pages and Express-callback branches stay"
cn, cs = rx(kb, "N")
cc, cx = rx(kb, "C")
assert all(re.match(cn, s) for s in ("session", "connect.sid", "authToken", "auth_token", "access-token", "next-auth.session-token", "jwt",
           "__Host-session", "Session-ID", "PHPSESSID", "sessionId", "appSession", "sessionKey", "sess", "sessid", "sessionid", "authtoken", "phpsessid",
           "sid", "token", "auth")), cn
assert not any(re.match(cn, s) for s in ("authorized", "tokenizer_mode", "assessment", "csrftoken", "theme", "sidebar_state", "side", "ssid", "tokens")), cn
assert all(re.match(cs, s) for s in ("session", "auth_token")) and not any(re.match(cs, s) for s in ("XSRF-TOKEN", "csrf_token", "_csrf", "x-csrf-token")), cs
assert all(re.match(cc, s) for s in ("res.cookie", "reply.setCookie", "cookies().set", "(await cookies()).set", "response.cookies.set", "res.cookies.set")), cc
assert not any(re.match(cc, s) for s in ("Cookies.set", "map.set", "cache.set", "cookieJar.set", "res.send", "cookieStore.set", "request.cookies.set",
               "req.cookies.set", "event.request.cookies.set")), cc
assert all(re.match(cx, s) for s in ("cookies.set", "ctx.cookies.set", "context.cookies.set", "event.cookies.set", "this.cookies.set")), cx
assert not any(re.match(cx, s) for s in ("res.cookies.set", "response.cookies.set", "this.ctx.cookies.set", "Cookies.set", "ctx.cookies.setx", "xctx.cookies.set",
               "cookies().set", "(await cookies()).set", "res.cookie", "reply.setCookie", "event.request.cookies.set")), cx
assert kb.count("pattern-not: '$C(..., {..., httpOnly: false, ...})'") == kb.count("pattern-not: '$C(..., {..., secure: false, ...})'") == 1, "only a literal false counts there"
assert rx(kb, "H") == rx(kb, "S") == ["^(?!false$)"], "a literal false httpOnly or secure is reported, any other value passes"
assert kb.count("$STORE.set(") == 3 and kb.count("$STORE = await cookies();") == kb.count("$STORE = cookies();") == 1, "a cookies() store bound to a variable is read through its binding"
assert "headers.origin" not in cb, "the registry cors-misconfiguration rule owns req.headers.origin"
assert 'origin: "*"' not in cb, "browsers refuse a literal * origin on credentialed requests, so it is not this defect"
ct, ck = rx(cb, "T")[0], rx(cb, "K")[0]
assert all(re.match(ct, s) for s in ("true", '"true"', "'true'", "`true`")) and not any(re.match(ct, s) for s in ("false", '"false"', "1", "trueish")), ct
assert all(re.match(ck, s) for s in ("has", "includes", "test")) and not any(re.match(ck, s) for s in ("some", "indexOf", "match")), ck
print("ok")
