"""route_auth_map.py (static missing-authentication lead-finder, CWE-306/862): golden rows over fictional fixtures, the JSON / stderr /
--paths / exit-code contract, the review_checks.sh --full wiring, and a mutation table proving each rule is pinned (a mutated copy of the
script must change the output). Fixtures are fictional (Acme, example.com); one new file per feature, nothing appended to a shared spec."""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
SCRIPT = SK / "route_auth_map.py"
RC = SK / "review_checks.sh"

FX = {
    # Next App Router: per-handler scoping, file-level helper guard, const/wrapped exports, destructured + re-exported verbs.
    "app/api/notes/route.ts": r'''import { getServerSession } from "next-auth";

export async function GET() {
  return Response.json([]);
}

export async function POST(req: Request) {
  const session = await getServerSession();
  if (!session) return new Response("no", { status: 401 });
  return Response.json({ ok: true });
}

export async function PUT(req: Request) {
  return Response.json({ ok: true });
}
''',
    "app/api/helper/route.ts": r'''async function guard() {
  const session = await auth();
  if (!session) throw new Error("unauthorized");
}

export async function POST(req: Request) {
  await guard();
  return Response.json({ ok: true });
}
''',
    "app/api/export/route.ts": r'''import { withAuth } from "@/lib/with-auth";

export const GET = async () => {
  return Response.json([]);
};

export const PATCH = withAuth(async (req: Request) => {
  return Response.json({ ok: true });
});

export const POST = compose(logger, async (req: Request) => {
  return Response.json({ ok: true });
});
''',
    "app/api/oneliner/route.ts": r'''export const GET = () => Response.json([]);
export const POST = async () => {
  await auth();
  return Response.json({ ok: true });
};
''',
    "app/api/modlevel/route.ts": r'''export async function GET() {
  return Response.json([]);
}

await auth();

export async function POST() {
  return Response.json({ ok: true });
}
''',
    "app/api/auth/[...nextauth]/route.ts": r'''import { handlers } from "@/auth";

// route-auth-ok: NextAuth handlers are public by design
export const { GET, handlePost: POST, auth } = handlers;
''',
    "app/api/legacy/route.js": r'''async function handler(req) {
  return Response.json({ ok: true });
}

async function secured() {
  await auth();
  return Response.json({ ok: true });
}

export { handler as PUT, handler as DELETE, secured as PATCH, handler as dynamic };
''',
    "app/api/reexport/route.ts": r'''export { GET, POST } from "./impl";
''',
    "app/api/unused/route.ts": r'''async function neverCalled() {
  await auth();
}

export async function POST() {
  return Response.json({ ok: true });
}
''',
    "app/api/vars/route.js": r'''export let GET = async () => Response.json([]);
export var POST = async () => Response.json({ ok: true });
export function DELETE() {
  return Response.json({ ok: true });
}
export const DELETED = 1;
''',
    "app/api/helpers/route.ts": r'''const g1 = async () => {
  await auth();
};

const g2 = () => {
  requireAuth();
};

const g3 = function () {
  getUser();
};

export async function POST() {
  await g1();
  return Response.json({ ok: true });
}

export async function PUT() {
  g2();
  return Response.json({ ok: true });
}

export async function PATCH() {
  g3();
  return Response.json({ ok: true });
}

export async function DELETE() {
  return Response.json({ ok: true });
}
''',
    "app/docs/[[...slug]]/route.mjs": r'''export async function GET() { return new Response("docs"); }
''',
    "app/(shop)/orders/[id]/route.ts": r'''export async function DELETE(req: Request) {
  await requireUser(req);
  return new Response(null, { status: 204 });
}
''',
    "app/api/token/route.ts": r'''export async function POST(req: Request) {
  if (req.headers.get("authorization") !== process.env.ACME_API_KEY) {
    return new Response("no", { status: 401 });
  }
  return Response.json({ ok: true });
}
''',
    "app/api/ping/route.ts": r'''export async function POST(req: Request) {
  if (req.headers.get("x-kind") !== "ping") {
    return new Response("no", { status: 400 });
  }
  return Response.json({ ok: true });
}
''',
    # Next middleware: root matcher, monorepo lookahead matcher + base scoping, no-matcher auth export, identity-free i18n middleware.
    "middleware.ts": r'''export { default } from "next-auth/middleware";

export const config = { matcher: ["/dashboard/:path*", "/api/private/:path*"] };
''',
    "app/api/private/data/route.ts": r'''export async function POST(req: Request) {
  return Response.json({ ok: true });
}
''',
    "app/api/public/data/route.ts": r'''export async function POST(req: Request) {
  return Response.json({ ok: true });
}
''',
    "apps/web/middleware.ts": r'''import { auth } from "@/auth";

export default auth((req) => {
  if (!req.auth) return Response.redirect(new URL("/login", req.url));
});

export const config = {
  matcher: ["/((?!api|_next|.*\\.(?:png|ico)).*)"],
};
''',
    "apps/web/app/dashboard/route.ts": r'''export async function POST() {
  return Response.json({ ok: true });
}
''',
    "apps/web/app/api/hook/route.ts": r'''export async function POST() {
  return Response.json({ ok: true });
}
''',
    "apps/web2/app/dashboard/route.ts": r'''export async function POST() {
  return Response.json({ ok: true });
}
''',
    "apps/admin/middleware.ts": r'''export { auth as middleware } from "@/auth";
''',
    "apps/admin/app/api/users/route.ts": r'''export async function DELETE() {
  return new Response(null, { status: 204 });
}
''',
    "apps/site/middleware.ts": r'''import createMiddleware from "next-intl/middleware";

export default createMiddleware({ locales: ["en", "de"], defaultLocale: "en" });

export const config = { matcher: ["/((?!api|_next).*)"] };
''',
    "apps/m/a-middleware.ts": "export const x = 1;\n",  # decoys: not middleware files, must not shadow the real one
    "apps/m/middleware.jsx": "export const y = 1;\n",
    "apps/js/middleware.js": 'export { auth as middleware } from "@/auth";\n',
    "apps/sq/middleware.ts": "export { auth as middleware } from '@/auth';\n\nexport const config = { matcher: '/sq/:path*' };\n",
    "apps/bt/middleware.ts": "export { auth as middleware } from '@/auth';\n\nexport const config = { matcher: `/bt/:path*` };\n",
    "apps/neg/middleware.ts": r'''import { auth } from "@/auth";

export default auth(() => {});

export const config = { matcher: ["/((?!api|_next/static|favicon.ico).*)"] };
''',
    "apps/m/middleware.ts": r'''export { auth as middleware } from "@/auth";

export const config = { matcher: ["/a/:path*", '/b/:path+', "/c/:id", "/d/:opt?", `/(?:e|f)/x`, "/(unclosed"] };
''',
    "apps/dyn/middleware.ts": r'''import { auth } from "@/auth";

const patterns = ["/x"];

export default auth(() => {});

export const config = { matcher: patterns };

export const fallback = "/x";
''',
    "apps/proxy/proxy.ts": r'''import { auth } from "@/auth";

export default auth(() => {});

export const config = { matcher: "/admin/:path*" };
''',
    "apps/old/middleware.ts": r'''export { default } from "next-auth/middleware";
''',
    "apps/old/pages/api/orders.ts": r'''export default function handler(req, res) {
  if (req.method === "POST") return res.json({ ok: true });
  return res.status(405).end();
}
''',
    # Next pages/api: method detection, ANY default, index stripped.
    "pages/api/users/[id].ts": r'''import type { NextApiRequest, NextApiResponse } from "next";

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === "DELETE") return res.status(204).end();
  if (req.method === "GET") return res.json({ id: req.query.id });
  return res.status(405).end();
}
''',
    "pages/api/health.ts": r'''export default function handler(req, res) {
  res.status(200).json({ ok: true });
}
''',
    "pages/api/me.ts": r'''import { getServerSession } from "next-auth";

export default async function handler(req, res) {
  const session = await getServerSession(req, res);
  res.json(session);
}
''',
    "pages/api/orders/index.ts": r'''export default async function handler(req, res) {
  if (req.method != "POST") return res.status(405).end();
  const session = await getSession({ req });
  res.json({ ok: !!session });
}
''',
    "pages/api/items.ts": r'''export default function handler(req, res) {
  switch (req.method) {
    case "PUT":
      return res.json({ ok: true });
    case 'PATCH':
      return res.json({ ok: true });
  }
  if ("DELETE" === req.method) return res.status(204).end();
  return res.status(405).end();
}
''',
    "pages/about.tsx": r'''export default function About() {
  return null;
}
''',
    # 'use server' actions: exported async functions only; a function's own name is not evidence.
    "app/actions.ts": r'''// Acme notes actions
"use server";

export async function saveNote(text: string) {
  return text;
}

export async function getUser(id: string) {
  return id;
}

export const removeNote = async (id: string) => {
  const session = await auth();
  return session ? id : null;
};

export function syncHelper() {
  return 1;
}

async function internal() {
  return 1;
}

export const NOTE_LIMIT = 5;
''',
    "app/bom/actions.ts": '﻿"use server";\n\nexport async function savePrefs(x: string) {\n  return x;\n}\n',
    "app/form/actions.jsx": r'''"use server";

export async function submitForm(data) {
  return data;
}
''',
    "app/form/more.tsx": r'''"use server";

export async function saveMore(data: string) {
  return data;
}
''',
    "lib/plain.ts": r'''const label = "use server";

export async function saveThing(x: string) {
  return x;
}
''',
    # Express / Hono / Fastify: receivers, middle-arg middleware, positional .use / addHook, prefix boundary, markers.
    "server/app.js": r'''const express = require("express");
const { requireAuth, authenticate } = require("./auth");

const app = express();
const admin = express.Router();

app.get("/health", (req, res) => res.send("ok"));
app.post("/orders", (req, res) => res.json({ ok: true }));
app.put("/orders/:id", requireAuth, (req, res) => res.json({ ok: true }));
app.delete("/orders/:id", (req, res) => {
  authenticate(req);
  res.json({ by: req.user.id });
});
app.patch("/orders/:id", (req, res) => res.json({ ok: true }));
app.all("/hook", (req, res) => res.sendStatus(200));
app.get(process.env.PATH_X, (req, res) => res.send("x"));
const port = app.get("port");
app.get("/solo");
// app.post("/commented", (req, res) => res.send("c"));
const note = 'app.post("/in-string", handler)';
app.get('/sq', (req, res) => res.send("q"));
app.get(`/tpl`, (req, res) => res.send("t"));
app.get(`/t/${id}`, (req, res) => res.send("t"));

app.post("/signin", authenticate);
app.post("/me/update", (req, res) => res.json({ id: req.user.id }));
app.post("/preauth", (req, res) => {
  preauth(req);
  $auth(req);
  res.send("x");
});
app.get("/pre", preauth, (req, res) => res.send("p"));
app.post("/bare", (req, res) => res.json({ ok: isLoggedIn }));
app.post("/verify", (req, res) => {
  verifyToken(req);
  res.send("v");
});
app.post("/store-key", (req, res) => {
  const header = req.headers["x-acme-token"];
  res.json({ stored: header });
});
app.post("/signup2", (req, res) => {
  if (req.body.password === process.env.ACME_PASSWORD) return res.sendStatus(200);
  res.sendStatus(403);
});
app.post("/hook2", (req, res) => {
  const ok = crypto.timingSafeEqual(Buffer.from(req.headers["x-hook-key"] || ""), Buffer.from(process.env.ACME_HOOK_SECRET || ""));
  res.sendStatus(ok ? 200 : 403);
});
app.post("/hook3", (req, res) => {
  if (req.get("Authorization") === process.env.ACME_SHARED_SECRET) return res.sendStatus(200);
  res.sendStatus(403);
});
app.post("/hook4", (req, res) => {
  if (req.headers.authorization !== process.env.ACME_PASSWORD) return res.sendStatus(403);
  res.sendStatus(200);
});
app.post("/hook5", (req, res) => {
  if (req.header("x-acme-sig") != process.env.ACME_ACCESS_TOKEN) return res.sendStatus(403);
  res.sendStatus(200);
});
app.post("/hook6", (req, res) => {
  if (req.headers["x-api-key"] !== process.env.ACME_KEY) return res.sendStatus(403);
  res.sendStatus(200);
});

app.post("/two", (req, res) => {
  if (!req.user) return res.sendStatus(401);
  authenticate(req);
  res.send("t");
});
app.post("/ra", (req, res) => res.json(req.auth));
app.post("/ru", (request, res) => res.json(request.user));
app.post("/hook7", (req, res) => {
  if (req.headers.authorization !== process.env.ACME_APIKEY) return res.sendStatus(403);
  res.sendStatus(200);
});
app.post("/spread", ...guards, (req, res) => res.send("s"));

admin.use(requireAuth);
admin.post("/users", (req, res) => res.json({ ok: true }));

app.post("/before-mark", (req, res) => res.json({ ok: true }));
// route-auth-ok: public sign-up
app.post("/signup", (req, res) => res.json({ ok: true }));
app.post("/login", (req, res) => res.json({ ok: true })); // route-auth-ok

app.post("/after-login", (req, res) => res.json({ ok: true }));
''',
    "routes/items.js": r'''const router = require("express").Router();

router.get("/early", (req, res) => res.json([]));
router.post("/x", (req, res) => res.json({ ok: true }));
router.use("/other", requireAuth());
router.post("/other/y", (req, res) => res.json({ ok: true }));
router.post("/others", (req, res) => res.json({ ok: true }));
router.use("/trail/", requireAuth);
router.post("/trail/z", (req, res) => res.json({ ok: true }));
router.use("/exact", requireAuth);
router.post("/exact", (req, res) => res.json({ ok: true }));
router.use("/wild/*", requireAuth);
router.post("/wild/q", (req, res) => res.json({ ok: true }));
router.use(requireAuth);
router.post("/y", (req, res) => res.json({ ok: true }));
router.all("*", (req, res) => res.sendStatus(404));
''',
    "routes/users.js": r'''const express = require("express");
const users = express.Router();

users.delete("/:id", (req, res) => res.sendStatus(204));
''',
    "server/receivers.ts": r'''import express, { Router } from "express";
import { Hono } from "hono";
import Fastify from "fastify";

const users = express.Router();
const api: Router = Router();
const edge = new Hono();
const srv = await Fastify();
const f2 = fastify();
const web = new Elysia();
const cache = new Map();

users.delete("/u/:id", (req, res) => res.sendStatus(204));
api.post("/a", (req, res) => res.sendStatus(204));
edge.put("/e", (c) => c.text("ok"));
srv.patch("/s", async () => ({ ok: true }));
f2.post("/f", async () => ({ ok: true }));
web.get("/w", () => "ok");
server.delete("/srv/:id", (req, res) => res.sendStatus(204));
cache.get("/c");
''',
    "server/esm.mjs": r'''import express from "express";

const app = express();

export function checkAuth(req) {
  return requireUser(req);
}

export async function checkAsync(req) {
  return getSession(req);
}

export const checkArrow = async (req) => {
  return currentUser(req);
};

app.post("/guarded", (req, res) => {
  checkAuth(req);
  res.send("ok");
});
app.post("/open-esm", (req, res) => res.send("o"));
''',
    "server/legacy.cjs": r'''const app = require("express")();
app.post("/legacy", (req, res) => res.send("ok"));
''',
    "server/one.js": 'const app = require("express")(); app.post("/one-liner", (req, res) => res.send("x")); // route-auth-ok\nconst later = 1;\n',
    "lib/latin1.js": b'const app = require("express")();\n// caf\xe9\napp.post("/latin", (req, res) => res.send("ok"));\n',
    "api/f3.js": r'''const fastify = require("fastify")();

fastify.addHook("onSend", fastify.authenticate);
fastify.post("/late", async (req) => ({ ok: true }));
''',
    "server/oldstyle.js": r'''var app = require("express")();
var guard = function (req, res, next) {
  if (!req.user) return res.sendStatus(401);
  next();
};
let guard2 = function (req, res, next) {
  authenticate(req);
  next();
};

app.post("/old-var", guard, function (req, res) {
  res.send("ok");
});
app.post("/old-let", guard2, function (req, res) {
  res.send("ok");
});
app.post("/old-open", function (req, res) {
  res.send("ok");
});
''',
    "server/attestation.js": 'const app = require("express")();\napp.post("/attest", (req, res) => res.send("ok"));\n',
    "api/hooks.js": r'''const a = Fastify();
const b = Fastify();
const c = Fastify();

a.addHook("preParsing", a.authenticate);
a.post("/pp", async () => ({ ok: true }));
b.addHook("preValidation", b.authenticate);
b.post("/pv", async () => ({ ok: true }));
c.addHook("preHandler", c.authenticate);
c.post("/ph", async () => ({ ok: true }));
''',
    "verbs/all.js": 'app.all(\n  "/v-all",\n  h\n);\n',
    "lib/keys.js": "const v = cache.get(key);\n",
    "app/route.ts": "export async function GET() {\n  return Response.json({ ok: true });\n}\n",
    "app/api/modparen/route.ts": r'''export async function GET() {
  return Response.json([]);
}
(async () => { await auth(); })();
export async function POST() {
  return Response.json({ ok: true });
}
''',
    "pages/api/old.js": "// Acme legacy handler\nmodule.exports = function handler(req, res) {\n  res.status(200).end();\n};\n",
    "pages/api/ping2.mjs": 'export default (req, res) => res.end("pong");\n',
    "lib/client.js": r'''const axios = require("axios");
const api = axios.create({ baseURL: "https://example.com" });
const cache = new Map();

async function load() {
  await api.get("/items");
  await api.post("/items", { a: 1 });
  return cache.get("/items");
}
module.exports = { load };
''',
    "src/index.ts": r'''import { Hono } from "hono";
import { jwt } from "hono/jwt";

const app = new Hono();

app.use("/api/*", jwt({ secret: "acme-test-secret" }));

app.get("/api/me", (c) => c.json({ me: true }));
app.post("/api/items", (c) => c.json({ ok: true }));
app.post("/public/items", (c) => c.json({ ok: true }));
''',
    "api/f1.js": r'''const fastify = require("fastify")();

fastify.post("/early", async (req) => ({ ok: true }));
fastify.addHook("onRequest", fastify.authenticate);
fastify.post("/late", async (req) => ({ ok: true }));
''',
    "api/f2.js": r'''const fastify = require("fastify")();

fastify.post("/secure", { preHandler: [fastify.authenticate] }, async (req) => ({ ok: true }));
fastify.post("/open", { config: { auth: false } }, async (req) => ({ ok: true }));
''',
    # FastAPI / Flask.
    "api/main.py": r'''from fastapi import Depends, FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/items")
def create_item(item: dict):
    return item


@app.patch("/items/{item_id}")
def patch_item(item_id: int):
    return {"patched": item_id}


@app.delete("/items/{item_id}")
def delete_item(item_id: int, user=Depends(get_current_user)):
    return {"deleted": item_id}


@app.get("/files/{file_path:path}")
def read_file(file_path: str):
    return file_path


@app.get("/verify_email")
def verify_email():
    return {"ok": True}


@app.post("/db")
def db_route(s=Depends(get_session)):
    return {"ok": True}


@app.post("/spaced")
def spaced(u=Depends( get_user )):
    return {"ok": True}


@app.post("/scoped")
def scoped(u=Security(get_current_active_user, scopes=["me"])):
    return {"ok": True}


@app.post("/commented-sig")
def with_comment(a,  # old signature (
                 b):
    return 1


@app.post("/cu")
def cu(u=Depends(CurrentUser)):
    return {"ok": True}


@app.get(PREFIX + "/dyn")
def dyn():
    return 1


@app.post("/strs")
def strs(a="x#(", b='y#('):
    return 1


@app.post("/esc")
def esc(a="q\"(", b='q\'('):
    return 1


async def refresh_user():
    return g.user


# @app.post("/commented")
def commented():
    """Docs.
    @app.post("/in-doc") looks like a route
    """
    return 1
''',
    "api/authrouter.py": r'''from fastapi import APIRouter

auth = APIRouter()


@auth.post("/register")
def register(data: dict):
    return data
''',
    "api/triple.py": r"""@app.get("/t1")
def t1():
    return '''
@app.post("/in-sq-doc")
def fake():
    pass
'''
""",
    "api/secured.py": r'''from fastapi import APIRouter, Depends

router = APIRouter(dependencies=[Depends(verify_token)])


@router.get("/secure/ping")
def ping():
    return {"ok": True}


@router.post("/secure/items")
def create():
    return {"ok": True}


@router.get("")
def root():
    return {"ok": True}
''',
    "web/views.py": r'''from flask import Blueprint, g
from flask_login import current_user, login_required

bp = Blueprint("views", __name__)


@bp.route("/profile")
@login_required
def profile():
    return "ok"


@bp.route("/profile/<int:uid>", methods=["POST", "DELETE"])
def edit_profile(uid):
    return "ok"


@bp.route("/tag/<slug>")
def tag(slug):
    return slug


@bp.route("/opt", methods=["OPTIONS"])
def opt():
    return ""


@bp.route("/lower", methods=["post"])
def lower():
    return ""


@bp.route("/tuple", methods=('PUT',))
def tuple_route():
    return ""


@jwt_required()
@bp.route("/above", methods=["POST"])
def above():
    return "ok"


@login_required
def helper_not_a_route():
    return 1


@bp.route("/pub")
def pub():
    return "ok"


@bp.route("/secret")
@login_required
def secret():
    return "ok"


@bp.route("/gme")
def gme():
    return g.user.name


@bp.route("/me")
def me():
    return current_user.name
''',
    "web/auth_bp.py": r'''from flask import Blueprint

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["POST"])
def login():
    return "ok"


@auth.route("/me")
@auth.route("/whoami")
def me():
    return "ok"
''',
    "web/factory.py": r'''from flask import Flask
from flask_login import login_required


def create_app():
    app = Flask(__name__)

    @app.route("/ping", methods=["POST"])
    def ping():
        return "pong"

    @app.route("/inner")
    @login_required
    def inner():
        return "ok"

    return app
''',
    "web/hooks.py": r'''import hmac
from flask import Blueprint, request

bp = Blueprint("hooks", __name__)
SHARED_SECRET = "acme-test-secret"


@bp.route("/hook", methods=["POST"])
def hook():
    if not hmac.compare_digest(request.headers.get("X-Sig", ""), SHARED_SECRET):
        return "no", 401
    return "ok"
''',
    # Silent: vendored dirs, test files, non-code files.
    "node_modules/pkg/index.js": 'const app = require("express")();\napp.post("/vendored", (req, res) => res.send("v"));\n',
    "app/api/foo/route.test.ts": 'export async function POST() { return Response.json({}); }\n',
    "tests/api.test.ts": 'const app = express();\napp.post("/t", (req, res) => res.send("t"));\n',
    "test_api.py": '@app.post("/t")\ndef t():\n    return 1\n',
    "tests/test_x.py": '@app.post("/t")\ndef t():\n    return 1\n',
    "docs/notes.md": 'app.post("/doc", (req, res) => res.send("d"));\n',
}

GOLD = [  # (file, text unique to the handler line, "SEV: METHOD route auth=X"); line numbers are looked up, never typed
    ("app/api/notes/route.ts", "function GET", "INFO: GET /api/notes auth=none"),
    ("app/api/notes/route.ts", "function POST", "INFO: POST /api/notes auth=getServerSession"),
    ("app/api/notes/route.ts", "function PUT", "HIGH: PUT /api/notes auth=none"),
    ("app/api/helper/route.ts", "function POST", "INFO: POST /api/helper auth=auth"),
    ("app/api/export/route.ts", "const GET", "INFO: GET /api/export auth=none"),
    ("app/api/export/route.ts", "const PATCH", "INFO: PATCH /api/export auth=withAuth"),
    ("app/api/export/route.ts", "const POST", "HIGH: POST /api/export auth=none"),
    ("app/api/oneliner/route.ts", "const GET", "INFO: GET /api/oneliner auth=none"),
    ("app/api/oneliner/route.ts", "const POST", "INFO: POST /api/oneliner auth=auth"),
    ("app/api/modlevel/route.ts", "function GET", "INFO: GET /api/modlevel auth=auth"),
    ("app/api/modlevel/route.ts", "function POST", "INFO: POST /api/modlevel auth=auth"),
    ("app/api/auth/[...nextauth]/route.ts", "export const { GET", "INFO: GET /api/auth/:nextauth* auth=public"),
    ("app/api/auth/[...nextauth]/route.ts", "export const { GET", "INFO: POST /api/auth/:nextauth* auth=public"),
    ("app/api/legacy/route.js", "export { handler", "HIGH: PUT /api/legacy auth=none"),
    ("app/api/legacy/route.js", "export { handler", "HIGH: DELETE /api/legacy auth=none"),
    ("app/api/legacy/route.js", "export { handler", "INFO: PATCH /api/legacy auth=auth"),
    ("app/api/reexport/route.ts", "export {", "INFO: GET /api/reexport auth=none"),
    ("app/api/reexport/route.ts", "export {", "HIGH: POST /api/reexport auth=none"),
    ("app/api/unused/route.ts", "function POST", "HIGH: POST /api/unused auth=none"),
    ("app/api/vars/route.js", "let GET", "INFO: GET /api/vars auth=none"),
    ("app/api/vars/route.js", "var POST", "HIGH: POST /api/vars auth=none"),
    ("app/api/vars/route.js", "function DELETE", "HIGH: DELETE /api/vars auth=none"),
    ("app/api/helpers/route.ts", "function POST", "INFO: POST /api/helpers auth=auth"),
    ("app/api/helpers/route.ts", "function PUT", "INFO: PUT /api/helpers auth=requireAuth"),
    ("app/api/helpers/route.ts", "function PATCH", "INFO: PATCH /api/helpers auth=getUser"),
    ("app/api/helpers/route.ts", "function DELETE", "HIGH: DELETE /api/helpers auth=none"),
    ("app/docs/[[...slug]]/route.mjs", "function GET", "INFO: GET /docs/:slug* auth=none"),
    ("app/(shop)/orders/[id]/route.ts", "function DELETE", "INFO: DELETE /orders/:id auth=requireUser"),
    ("app/api/token/route.ts", "function POST", "INFO: POST /api/token auth=token"),
    ("app/api/ping/route.ts", "function POST", "HIGH: POST /api/ping auth=none"),
    ("app/api/private/data/route.ts", "function POST", "INFO: POST /api/private/data auth=middleware"),
    ("app/api/public/data/route.ts", "function POST", "HIGH: POST /api/public/data auth=none"),
    ("apps/web/app/dashboard/route.ts", "function POST", "INFO: POST /dashboard auth=middleware"),
    ("apps/web/app/api/hook/route.ts", "function POST", "HIGH: POST /api/hook auth=none"),
    ("apps/web2/app/dashboard/route.ts", "function POST", "HIGH: POST /dashboard auth=none"),
    ("apps/admin/app/api/users/route.ts", "function DELETE", "INFO: DELETE /api/users auth=middleware"),
    ("apps/old/pages/api/orders.ts", "export default", "INFO: POST /api/orders auth=middleware"),
    ("pages/api/users/[id].ts", "export default", "HIGH: GET|DELETE /api/users/:id auth=none"),
    ("pages/api/health.ts", "export default", "HIGH: ANY /api/health auth=none"),
    ("pages/api/me.ts", "export default", "INFO: ANY /api/me auth=getServerSession"),
    ("pages/api/orders/index.ts", "export default", "INFO: POST /api/orders auth=getSession"),
    ("pages/api/items.ts", "export default", "HIGH: PUT|PATCH|DELETE /api/items auth=none"),
    ("app/actions.ts", "function saveNote", "HIGH: ACTION saveNote auth=none"),
    ("app/actions.ts", "function getUser", "HIGH: ACTION getUser auth=none"),
    ("app/actions.ts", "const removeNote", "INFO: ACTION removeNote auth=auth"),
    ("app/bom/actions.ts", "function savePrefs", "HIGH: ACTION savePrefs auth=none"),
    ("app/form/actions.jsx", "function submitForm", "HIGH: ACTION submitForm auth=none"),
    ("app/form/more.tsx", "function saveMore", "HIGH: ACTION saveMore auth=none"),
    ("server/app.js", 'app.get("/health"', "INFO: GET /health auth=none"),
    ("server/app.js", 'app.post("/orders"', "HIGH: POST /orders auth=none"),
    ("server/app.js", 'app.put("/orders/:id"', "INFO: PUT /orders/:id auth=requireAuth"),
    ("server/app.js", 'app.delete("/orders/:id"', "INFO: DELETE /orders/:id auth=authenticate"),
    ("server/app.js", 'app.patch("/orders/:id"', "HIGH: PATCH /orders/:id auth=none"),
    ("server/app.js", 'app.all("/hook"', "HIGH: ANY /hook auth=none"),
    ("server/app.js", "app.get('/sq'", "INFO: GET /sq auth=none"),
    ("server/app.js", "app.get(`/tpl`", "INFO: GET /tpl auth=none"),
    ("server/app.js", 'app.post("/signin"', "HIGH: POST /signin auth=none"),
    ("server/app.js", 'app.post("/me/update"', "INFO: POST /me/update auth=req.user"),
    ("server/app.js", 'app.post("/preauth"', "HIGH: POST /preauth auth=none"),
    ("server/app.js", 'app.get("/pre"', "INFO: GET /pre auth=none"),
    ("server/app.js", 'app.post("/bare"', "HIGH: POST /bare auth=none"),
    ("server/app.js", 'app.post("/verify"', "INFO: POST /verify auth=verifyToken"),
    ("server/app.js", 'app.post("/store-key"', "HIGH: POST /store-key auth=none"),
    ("server/app.js", 'app.post("/signup2"', "HIGH: POST /signup2 auth=none"),
    ("server/app.js", 'app.post("/hook2"', "INFO: POST /hook2 auth=token"),
    ("server/app.js", 'app.post("/hook3"', "INFO: POST /hook3 auth=token"),
    ("server/app.js", 'app.post("/hook4"', "INFO: POST /hook4 auth=token"),
    ("server/app.js", 'app.post("/hook5"', "INFO: POST /hook5 auth=token"),
    ("server/app.js", 'app.post("/hook6"', "INFO: POST /hook6 auth=token"),
    ("server/app.js", 'admin.post("/users"', "INFO: POST /users auth=requireAuth"),
    ("server/app.js", 'app.post("/before-mark"', "HIGH: POST /before-mark auth=none"),
    ("server/app.js", 'app.post("/signup"', "INFO: POST /signup auth=public"),
    ("server/app.js", 'app.post("/login"', "INFO: POST /login auth=public"),
    ("server/app.js", 'app.post("/after-login"', "HIGH: POST /after-login auth=none"),
    ("routes/items.js", 'router.get("/early"', "INFO: GET /early auth=none"),
    ("routes/items.js", 'router.post("/x"', "HIGH: POST /x auth=none"),
    ("routes/items.js", 'router.post("/other/y"', "INFO: POST /other/y auth=requireAuth"),
    ("routes/items.js", 'router.post("/others"', "HIGH: POST /others auth=none"),
    ("routes/items.js", 'router.post("/trail/z"', "INFO: POST /trail/z auth=requireAuth"),
    ("routes/items.js", 'router.post("/exact"', "INFO: POST /exact auth=requireAuth"),
    ("routes/items.js", 'router.post("/y"', "INFO: POST /y auth=requireAuth"),
    ("routes/users.js", 'users.delete("/:id"', "HIGH: DELETE /:id auth=none"),
    ("server/receivers.ts", 'users.delete("/u/:id"', "HIGH: DELETE /u/:id auth=none"),
    ("server/receivers.ts", 'api.post("/a"', "HIGH: POST /a auth=none"),
    ("server/receivers.ts", 'edge.put("/e"', "HIGH: PUT /e auth=none"),
    ("server/receivers.ts", 'srv.patch("/s"', "HIGH: PATCH /s auth=none"),
    ("server/receivers.ts", 'f2.post("/f"', "HIGH: POST /f auth=none"),
    ("server/receivers.ts", 'web.get("/w"', "INFO: GET /w auth=none"),
    ("server/esm.mjs", 'app.post("/guarded"', "INFO: POST /guarded auth=requireUser"),
    ("server/legacy.cjs", 'app.post("/legacy"', "HIGH: POST /legacy auth=none"),
    ("server/one.js", 'app.post("/one-liner"', "INFO: POST /one-liner auth=public"),
    ("lib/latin1.js", 'app.post("/latin"', "HIGH: POST /latin auth=none"),
    ("src/index.ts", 'app.get("/api/me"', "INFO: GET /api/me auth=jwt"),
    ("src/index.ts", 'app.post("/api/items"', "INFO: POST /api/items auth=jwt"),
    ("src/index.ts", 'app.post("/public/items"', "HIGH: POST /public/items auth=none"),
    ("api/f1.js", 'fastify.post("/early"', "HIGH: POST /early auth=none"),
    ("api/f1.js", 'fastify.post("/late"', "INFO: POST /late auth=authenticate"),
    ("api/f2.js", 'fastify.post("/secure"', "INFO: POST /secure auth=authenticate"),
    ("api/f2.js", 'fastify.post("/open"', "HIGH: POST /open auth=none"),
    ("api/f3.js", 'fastify.post("/late"', "HIGH: POST /late auth=none"),
    ("api/main.py", '@app.get("/health")', "INFO: GET /health auth=none"),
    ("api/main.py", '@app.post("/items")', "HIGH: POST /items auth=none"),
    ("api/main.py", '@app.patch("/items/{item_id}")', "HIGH: PATCH /items/:item_id auth=none"),
    ("api/main.py", '@app.delete("/items/{item_id}")', "INFO: DELETE /items/:item_id auth=Depends(get_current_user)"),
    ("api/main.py", '@app.get("/files/{file_path:path}")', "INFO: GET /files/:file_path auth=none"),
    ("api/main.py", '@app.get("/verify_email")', "INFO: GET /verify_email auth=none"),
    ("api/main.py", '@app.post("/db")', "HIGH: POST /db auth=none"),
    ("api/main.py", '@app.post("/spaced")', "INFO: POST /spaced auth=Depends(get_user)"),
    ("api/main.py", '@app.post("/scoped")', "INFO: POST /scoped auth=Security(get_current_active_user)"),
    ("api/main.py", '@app.post("/commented-sig")', "HIGH: POST /commented-sig auth=none"),
    ("api/secured.py", '@router.get("/secure/ping")', "INFO: GET /secure/ping auth=Depends(verify_token)"),
    ("api/secured.py", '@router.post("/secure/items")', "INFO: POST /secure/items auth=Depends(verify_token)"),
    ("api/secured.py", '@router.get("")', "INFO: GET / auth=Depends(verify_token)"),
    ("web/views.py", '@bp.route("/profile")', "INFO: GET /profile auth=login_required"),
    ("web/views.py", '@bp.route("/profile/<int', "HIGH: POST|DELETE /profile/:uid auth=none"),
    ("web/views.py", '@bp.route("/tag/<slug>")', "INFO: GET /tag/:slug auth=none"),
    ("web/views.py", '@bp.route("/lower"', "HIGH: POST /lower auth=none"),
    ("web/views.py", '@bp.route("/above"', "HIGH: POST /above auth=none"),
    ("web/views.py", '@bp.route("/pub")', "INFO: GET /pub auth=none"),
    ("web/views.py", '@bp.route("/secret")', "INFO: GET /secret auth=login_required"),
    ("web/views.py", '@bp.route("/gme")', "INFO: GET /gme auth=g.user"),
    ("web/views.py", '@bp.route("/me")', "INFO: GET /me auth=current_user"),
    ("web/auth_bp.py", '@auth.route("/login"', "HIGH: POST /login auth=none"),
    ("web/auth_bp.py", '@auth.route("/me")', "INFO: GET /me auth=none"),
    ("web/auth_bp.py", '@auth.route("/whoami")', "INFO: GET /whoami auth=none"),
    ("web/hooks.py", '@bp.route("/hook"', "INFO: POST /hook auth=token"),
    ("app/route.ts", "function GET", "INFO: GET / auth=none"),
    ("app/api/modparen/route.ts", "function GET", "INFO: GET /api/modparen auth=auth"),
    ("app/api/modparen/route.ts", "function POST", "INFO: POST /api/modparen auth=auth"),
    ("pages/api/old.js", "module.exports", "HIGH: ANY /api/old auth=none"),
    ("pages/api/ping2.mjs", "export default", "HIGH: ANY /api/ping2 auth=none"),
    ("server/app.js", 'app.post("/two"', "INFO: POST /two auth=req.user"),
    ("server/app.js", 'app.post("/ra"', "INFO: POST /ra auth=req.auth"),
    ("server/app.js", 'app.post("/ru"', "INFO: POST /ru auth=request.user"),
    ("server/app.js", 'app.post("/hook7"', "INFO: POST /hook7 auth=token"),
    ("routes/items.js", 'router.post("/wild/q"', "INFO: POST /wild/q auth=requireAuth"),
    ("server/receivers.ts", 'server.delete("/srv/:id"', "HIGH: DELETE /srv/:id auth=none"),
    ("server/esm.mjs", 'app.post("/open-esm"', "HIGH: POST /open-esm auth=none"),
    ("server/oldstyle.js", 'app.post("/old-var"', "INFO: POST /old-var auth=req.user"),
    ("server/oldstyle.js", 'app.post("/old-let"', "INFO: POST /old-let auth=authenticate"),
    ("server/oldstyle.js", 'app.post("/old-open"', "HIGH: POST /old-open auth=none"),
    ("server/attestation.js", 'app.post("/attest"', "HIGH: POST /attest auth=none"),
    ("api/hooks.js", 'a.post("/pp"', "INFO: POST /pp auth=authenticate"),
    ("api/hooks.js", 'b.post("/pv"', "INFO: POST /pv auth=authenticate"),
    ("api/hooks.js", 'c.post("/ph"', "INFO: POST /ph auth=authenticate"),
    ("verbs/all.js", "app.all(", "HIGH: ANY /v-all auth=none"),
    ("api/main.py", '@app.post("/cu")', "INFO: POST /cu auth=Depends(CurrentUser)"),
    ("api/main.py", '@app.post("/strs")', "HIGH: POST /strs auth=none"),
    ("api/main.py", '@app.post("/esc")', "HIGH: POST /esc auth=none"),
    ("api/authrouter.py", '@auth.post("/register")', "HIGH: POST /register auth=none"),
    ("api/triple.py", '@app.get("/t1")', "INFO: GET /t1 auth=none"),
    ("web/factory.py", '@app.route("/ping"', "HIGH: POST /ping auth=none"),
    ("web/factory.py", '@app.route("/inner")', "INFO: GET /inner auth=login_required"),
    ("web/views.py", '@bp.route("/tuple"', "HIGH: PUT /tuple auth=none"),
]

POST1 = "export async function POST() {\n  return Response.json({ ok: true });\n}\n"
MW = [  # (app dir, route dir, route, auth): which routes the app's Next middleware covers
    ("apps/site", "contact", "/contact", "none"),  # an i18n middleware names no identity check
    ("apps/web", "og.png", "/og.png", "none"),  # its matcher excludes .png through an escaped dot
    ("apps/m", "a", "/a", "middleware"), ("apps/m", "a/x", "/a/x", "middleware"),
    ("apps/m", "b", "/b", "none"), ("apps/m", "b/x", "/b/x", "middleware"), ("apps/m", "b/x/y", "/b/x/y", "middleware"),
    ("apps/m", "c/[id]", "/c/:id", "middleware"), ("apps/m", "c", "/c", "none"),
    ("apps/m", "d", "/d", "middleware"), ("apps/m", "d/x/y", "/d/x/y", "none"),
    ("apps/dyn", "x", "/x", "none"),  # a matcher held in a variable cannot be read: covers nothing
    ("apps/proxy", "admin", "/admin", "middleware"), ("apps/proxy", "open", "/open", "none"),
    ("apps/m", "e/x", "/e/x", "middleware"),  # a `(?:` group in a matcher is not a :name parameter
    ("apps/js", "x", "/x", "middleware"),  # a middleware.js without a matcher covers everything
    ("apps/sq", "sq/x", "/sq/x", "middleware"), ("apps/bt", "bt/x", "/bt/x", "middleware"),  # string matchers: single quote, backtick
    ("apps/neg", "x", "/x", "middleware"), ("apps/neg", "api", "/api", "none"),  # the stock negative-lookahead matcher
    ("apps/strmw", "auth/x", "/auth/x", "none"),  # a middleware that merely mentions `auth` in a matcher string checks nothing
    ("apps/gate", "api/x", "/api/x", "middleware"),  # a proxy that can answer 401 gates what its matcher covers, whatever its session check is called
    ("apps/gate-colon", "api/x", "/api/x", "middleware"), ("apps/gate-call", "api/x", "/api/x", "middleware"),  # `status: 403` and `.status(401)`
    ("apps/gate-body", "api/x", "/api/x", "middleware"), ("apps/gate-forbidden", "api/x", "/api/x", "middleware"),  # an Unauthorized / Forbidden response
    ("apps/gate-headers", "api/x", "/api/x", "none"),  # a proxy that only sets headers gates nothing
    ("apps/gate-decoys", "api/x", "/api/x", "none"),  # other statuses, `http_status`, a bare "Forbidden" and a commented-out refusal are no gate
    ("apps/gate-part", "in/x", "/in/x", "middleware"), ("apps/gate-part", "out/x", "/out/x", "none"),  # the matcher decides which routes the refusal covers
    ("apps/open", "acme-api/v1.0/notes", "/acme-api/v1.0/notes", "middleware"),  # a gate that lists public paths still covers the rest
    ("apps/open", "acme-api/v1.0/hook", "/acme-api/v1.0/hook", "none"), ("apps/open", "acme-api/v1.0/hook/ping", "/acme-api/v1.0/hook/ping", "none"),  # a listed path and what is under it
    ("apps/open", "acme-api/v1.0/hooks", "/acme-api/v1.0/hooks", "middleware"),  # a sibling that merely shares the string prefix is not exempt
    ("apps/open", "acme-api/v1.0/legacy", "/acme-api/v1.0/legacy", "none"), ("apps/open", "acme-api/v1.0/a+b", "/acme-api/v1.0/a+b", "none"),  # trailing slash, regex characters
    ("apps/open", "acme-api/v1.0/late", "/acme-api/v1.0/late", "none"),  # a literal written after the matcher counts too
    ("apps/open", "admin/x", "/admin/x", "middleware"), ("apps/open", "billing", "/billing", "middleware"),  # a literal that is a matcher entry is a scope check, not a way out
    ("apps/open-all", "api/pay", "/api/pay", "none"), ("apps/open-all", "api/notes", "/api/notes", "middleware"),  # a middleware without a matcher: the whole file is read
    ("apps/scope", "acme-api/x", "/acme-api/x", "middleware"),  # a path in the condition of an `if` that refuses scopes the gate, it is no way out, whatever the matcher
    ("apps/scope-deep", "acme-api/x", "/acme-api/x", "middleware"),  # the refusal may sit deeper in the block, after an inner block closed, be a bare response string, and brackets in strings do not count
    ("apps/scope-line", "acme-api/x", "/acme-api/x", "middleware"),  # an unbraced body on the next line runs to the end of its multi-line call
    ("apps/scope-line", "acme-skip/x", "/acme-skip/x", "none"), ("apps/scope-line", "acme-login", "/acme-login", "none"),  # a body without `;` ends at its line; a path in the refusal itself is no scope
    ("apps/scope-stmt", "acme-skip/x", "/acme-skip/x", "none"), ("apps/scope-stmt", "acme-open/x", "/acme-open/x", "none"),  # a later statement on the line and an else branch are no part of the body
    ("apps/scope-neg", "acme-web/x", "/acme-web/x", "middleware"),  # ceiling: a negated refusal is not read, so the open part reads covered
    ("apps/set", "acme-health", "/acme-health", "none"), ("apps/set", "acme-api/boot", "/acme-api/boot", "none"),  # a Set allow-list is a literal list like any other
    ("apps/set", "acme-api/notes", "/acme-api/notes", "middleware"), ("apps/set", "acme-late", "/acme-late", "none"),  # siblings stay covered; a literal after the refusing condition is an exemption
    ("apps/scope-cont", "acme-skip/x", "/acme-skip/x", "none"),  # a line break that carries nothing on still ends the body
    ("apps/scope-cont", "acme-api/x", "/acme-api/x", "middleware"), ("apps/scope-cont", "acme-and/x", "/acme-and/x", "middleware"),  # a ternary or `&&` body runs over its lines; comments between them hide nothing
    ("apps/scope-cont", "acme-chain/x", "/acme-chain/x", "middleware"),  # each line start (. ? : && ||) and line end (? : && ||) that carries the statement on
    ("apps/scope-eq", "acme-api/x", "/acme-api/x", "middleware"),  # the path may be the last operand of the condition
    ("apps/open-brace", "acme-open/x", "/acme-open/x", "none"),  # brackets inside an allow-list body close again: the refusal after it is not part of the body
    ("apps/scope-arr", "acme-arr/x", "/acme-arr/x", "middleware"),  # a line break inside an open bracket does not end the body
    ("apps/glob", "sign-in/x", "/sign-in/x", "none"), ("apps/glob", "acme-api/webhooks/stripe", "/acme-api/webhooks/stripe", "none"),  # a glob list (Clerk createRouteMatcher): a trailing (.*) ...
    ("apps/glob", "acme-glob/x", "/acme-glob/x", "none"), ("apps/glob", "acme-path/x", "/acme-path/x", "none"),  # ... /* or /:name* names the path before it
    ("apps/glob", "acme-seg/x", "/acme-seg/x", "none"),  # the slash before a wildcard goes too
    ("apps/glob", "acme-api/other", "/acme-api/other", "middleware"), ("apps/glob", "acme-mid/x", "/acme-mid/x", "middleware"),  # siblings stay covered; a wildcard inside the path is not read
]
for base, d, route, lab in MW:
    FX["%s/app/%s/route.ts" % (base, d)] = POST1
    GOLD.append(("%s/app/%s/route.ts" % (base, d), "function POST", "%s: POST %s auth=%s" % ("HIGH" if lab == "none" else "INFO", route, lab)))


def gate(body, matcher='"/:path*"'):
    """A Next proxy.ts that names no identity check and runs body before it lets the request through (no config at all when matcher is empty)."""
    return ('import { NextResponse, type NextRequest } from "next/server";\n\nexport function proxy(req: NextRequest) {\n%s  return NextResponse.next();\n}\n%s'
            % (body, "\nexport const config = { matcher: %s };\n" % matcher if matcher else ""))


FX["apps/gate/proxy.ts"] = gate('  if (!isMemberSession(req)) return new NextResponse("Unauthorized", { status: 401 });\n')
FX["apps/gate-colon/proxy.ts"] = gate('  if (!isMemberSession(req)) return NextResponse.json({ ok: false }, { status: 403 });\n')
FX["apps/gate-call/proxy.ts"] = gate('  if (!isMemberSession(req)) return reply.status(401).send("denied");\n')
FX["apps/gate-body/proxy.ts"] = gate('  if (!isMemberSession(req)) {\n    return new Response(\n      "Unauthorized request",\n      { status: code },\n    );\n  }\n')
FX["apps/gate-forbidden/proxy.ts"] = gate("  if (!isMemberSession(req)) return new NextResponse('Forbidden', init);\n")
FX["apps/gate-headers/proxy.ts"] = gate('  req.headers.set("x-acme-region", "eu");\n')
FX["apps/gate-decoys/proxy.ts"] = gate(
    '  // return new NextResponse("Unauthorized", { status: 401 });\n  const log = { http_status: 401 };\n  const reason = "Forbidden";\n'
    "  if (isOverQuota(req)) return new NextResponse(null, { status: 402 });\n  if (isGone(req)) return new NextResponse(null, { status: 404 });\n")
FX["apps/gate-part/proxy.ts"] = gate('  if (!isMemberSession(req)) return new NextResponse(null, { status: 401 });\n', '["/in/:path*"]')
# Allow-lists: a quoted "/path" anywhere in the file is a route the function lets through, unless it is a prefix of a matcher entry (a scope check).
FX["apps/open/proxy.ts"] = gate(
    '  const open = ["/acme-api/v1.0/hook", "/acme-api/v1.0/legacy/", "/acme-api/v1.0/a+b"];\n  const path = req.nextUrl.pathname;\n'
    '  // "/acme-api/v1.0/notes" is gated like the rest: a path in a comment lets nothing through\n'
    '  if (path === "/") return NextResponse.next();\n  if (!path.startsWith("/acme-api") || path === "/acme-api/v1.0") return NextResponse.next();\n'
    '  if (open.some((p) => path.startsWith(p))) return NextResponse.next();\n'
    '  if (path === "/billing" && !isMemberSession(req)) return new NextResponse(null, { status: 403 });\n'
    '  if (!isMemberSession(req)) return new NextResponse(null, { status: 401 });\n',
    '["/admin/:path*", "/acme-api/v1.0/:path*", "/billing"]') + 'export const late = ["/acme-api/v1.0/late"];\n'
FX["apps/open-all/proxy.ts"] = gate(
    '  if (req.nextUrl.pathname === "/") return NextResponse.next();\n  if (req.nextUrl.pathname.startsWith("/api/pay")) return NextResponse.next();\n'
    '  if (!isMemberSession(req)) return new NextResponse(null, { status: 401 });\n', "")
# Scope checks: a quoted path in the condition of an `if` whose body can refuse protects that area, it does not let it through (a catch-all matcher has no entry to be a prefix of).
FX["apps/scope/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n"
    "  if (p.startsWith('/acme-api/') || p.startsWith('/_next/')) { return new NextResponse('Unauthorized', { status: 401 }) }\n")
FX["apps/scope-deep/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n  if(p.startsWith('/acme-api/') && !req.method.includes(':)')) {\n    if (req.method === ':)') { return NextResponse.next() }\n"
    "    if (!isMemberSession(req)) return new NextResponse('Unauthorized', init);\n  }\n")
FX["apps/scope-line/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname\n  if (p.startsWith('/acme-skip/')) return NextResponse.next()\n"
    "  if (p.startsWith('/acme-api/'))\n    return NextResponse.json(\n      { error: 'denied', login: '/acme-login' },\n      { status: 403 },\n    )\n")
FX["apps/scope-stmt/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n"
    "  if (p.startsWith('/acme-skip/')) return NextResponse.next(); if (!isMemberSession(req)) return new NextResponse('Unauthorized', { status: 401 });\n"
    "  if (p.startsWith('/acme-open/')) { return NextResponse.next() } else { return new NextResponse('Unauthorized', { status: 401 }) }\n")
FX["apps/scope-neg/proxy.ts"] = gate(
    "  if (!req.nextUrl.pathname.startsWith('/acme-web')) return new NextResponse('Unauthorized', { status: 401 });\n")
FX["apps/set/proxy.ts"] = gate(
    "  const open = new Set(['/acme-health', '/acme-api/boot']);\n  const pathname = req.nextUrl.pathname;\n  if (open.has(pathname)) return NextResponse.next();\n"
    "  if (!isMemberSession(req)) return new NextResponse('Unauthorized', { status: 401 });\n") + "export const late = ['/acme-late'];\n"
# A braceless body runs over a line break that cannot end a statement; the chain needs every continuation at once (one per line break).
FX["apps/scope-cont/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n  if (p.startsWith('/acme-skip/')) return NextResponse.next()\n"
    "  if (p.startsWith('/acme-api/'))\n    return !getToken(req)\n      ? new NextResponse('Unauthorized', { status: 401 })\n      : NextResponse.next();\n"
    "  if (p.startsWith('/acme-and/'))\n    return !getToken(req) && // no session\n      // refuse\n      new NextResponse('Unauthorized', { status: 401 });\n"
    "  if (p.startsWith('/acme-chain/'))\n    return isOpen(req)\n      ? ctx.res\n          .next()\n      : isStaff(req) &&\n        isBot(req) ||\n        isMember(req)\n        && isTeam(req)\n"
    "        || isGuest(req) ?\n        isAdmin(req) :\n        NextResponse.json({ error: 'denied' }, { status: 403 })\n")
FX["apps/scope-eq/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n  if (p === '/acme-api') return new NextResponse(null, { status: 401 });\n")
FX["apps/open-brace/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n  if (p.startsWith('/acme-open')) return NextResponse.next({ headers: [req.headers] });\n"
    "  if (!isMemberSession(req)) return new NextResponse('Unauthorized', { status: 401 });\n")
FX["apps/scope-arr/proxy.ts"] = gate(
    "  const p = req.nextUrl.pathname;\n  if (p.startsWith('/acme-arr/'))\n    return [\n      new NextResponse('Unauthorized', { status: 401 })\n    ][0];\n")
FX["apps/glob/proxy.ts"] = gate(
    "  const open = createRouteMatcher(['/sign-in(.*)', '/acme-api/webhooks(.*)', '/acme-seg/(.*)', '/acme-glob/*', '/acme-path/:path*', '/acme-mid/*/x']);\n"
    "  if (open(req)) return NextResponse.next();\n  if (!isMemberSession(req)) return new NextResponse('Unauthorized', { status: 401 });\n")

DEPKW = ("user", "auth", "token", "current", "bearer", "jwt", "api_key", "apikey", "verify", "login")  # one FastAPI route per Depends keyword
FX["api/deps.py"] = "from fastapi import Depends, FastAPI\n\napp = FastAPI()\n" + "".join(
    '\n\n@app.post("/d-%s")\ndef d_%s(x=Depends(f_%s_dep)):\n    return 1\n' % (k, k, k) for k in DEPKW)
GOLD += [("api/deps.py", '@app.post("/d-%s")' % k, "INFO: POST /d-%s auth=Depends(f_%s_dep)" % (k, k)) for k in DEPKW]

JSID = ("getServerSession", "getSession", "getToken", "getAuth", "auth", "currentUser", "getUser", "getCurrentUser", "requireAuth", "requireAuthLevel", "requireUserRole",
        "requireSessionX", "requireLoginX", "requireAdminX", "withAuth", "authMiddleware", "authGuard", "authenticate", "authenticateUser", "authorize", "authorizeRole",
        "isAuthenticated", "isLoggedIn", "ensureAuth", "ensureAuthX", "ensureLoggedInX", "protect", "validateRequest", "verify", "verifyToken", "constructEvent",
        "jwt", "expressjwt", "checkJwt", "bearerAuth", "basicAuth", "clerkMiddleware")  # one Express route per IDENTITY name that reads as a call; the bare forms pin the `\w*` suffixes
FX["server/idents.js"] = 'const app = require("express")();\n' + "".join('app.post("/i-%s", (req, res) => { %s(req); res.send("ok"); });\n' % (n, n) for n in JSID)
GOLD += [("server/idents.js", '"/i-%s"' % n, "INFO: POST /i-%s auth=%s" % (n, n)) for n in JSID]
PYID = ("login_required", "jwt_required", "token_required", "auth_required", "requires_auth", "permission_required", "get_current_admin")  # one Flask route per decorator name
FX["api/idents.py"] = "from flask import Flask\n\napp = Flask(__name__)\n" + "".join('\n\n@app.post("/p-%s")\n@%s\ndef f_%s():\n    return 1\n' % (n, n, n) for n in PYID)
GOLD += [("api/idents.py", '@app.post("/p-%s")' % n, "INFO: POST /p-%s auth=%s" % (n, n)) for n in PYID]

FX["server/latest.js"] = 'const app = require("express")();\napp.post("/latest", (req, res) => res.send("x"));\n'  # `test.` inside a file name does not make a test file
FX["lib/contests/api.js"] = 'const app = require("express")();\napp.post("/contest", (req, res) => res.send("x"));\n'  # nor does `tests/` inside a directory name
FX["app/api/og/route.tsx"] = POST1  # JSX route handlers are routes too
FX["pages/api/legacy.jsx"] = 'export default function handler(req, res) {\n  res.end("x");\n}\n'
FX["pages/api/app/route.js.py"] = "x = 1\n"  # a Python file named like a Next route: only a missing `$` anchor would scan it
GOLD += [("server/latest.js", 'app.post("/latest"', "HIGH: POST /latest auth=none"), ("lib/contests/api.js", 'app.post("/contest"', "HIGH: POST /contest auth=none"),
         ("app/api/og/route.tsx", "function POST", "HIGH: POST /api/og auth=none"), ("pages/api/legacy.jsx", "export default", "HIGH: ANY /api/legacy auth=none")]

# One fixture per rule the mutation table pins: a mutated copy of the script must change these rows.
FX["server/decoys.js"] = 'const app = require("express")();\n\napp.post("/dollar", $auth, (req, res) => res.send("x"));\napp.get("/a" + suffix, (req, res) => res.send("x"));\n'  # `$auth` is no `auth`; a computed path is no route
FX["server/order.js"] = 'const app = require("express")();\n\napp.use(requireAuth);\napp.post("/both", checkJwt, (req, res) => res.send("x"));\n'  # the route's own guard is named before the router-level one
FX["server/guard.js"] = 'const app = require("express")();\n\napp.post("/g", (req, res) => { guard(req); res.send("ok"); });\napp.post("/g2", (req, res) => res.send("ok"));\n\nfunction guard(req) { return auth(); }\n'  # a one-line function that ends the file
FX["api/f4.js"] = "const fastify = require(\"fastify\")();\n\nfastify.addHook('onRequest', requireAuth);\nfastify.post(\"/sq-hook\", async (req) => ({ ok: true }));\n"
FX["api/contest_api.py"] = '@app.post("/contest-entry")\ndef contest_entry():\n    return 1\n'  # `test_` inside a file name does not make a test file
FX["api/misc.py"] = r'''from flask import Flask

app = Flask(__name__)


@app.post("/dotted")
@auth.login_required
def dotted():
    return 1


@app.get('/sq-deco')
def sq_deco():
    return 1


@app.get( "/pad" )
def pad():
    return 1


def make():
    app = Flask(__name__)

    @app.post("/nested-last")
    def nested_last():
        return 1


@login_required
def other():
    return 2


@app.get("/unclosed"
'''
FX["api/strings.py"] = r'''from flask import Flask

app = Flask(__name__)
NOTE = """say \""" then x"""


@app.post("/after-esc")
@login_required
def after_esc():
    """Docs."""
    return 1


def e1(a=''):
    return 1


@app.post("/e-route")
@login_required
def e2(b=''):
    return 2


@app.post("/esc-dq")
def esc_dq(a="\\", b="x("):
    return 1


@app.post("/esc-sq")
def esc_sq(a='\\', b='x('):
    return 1


@app.get("/d1")
def d1():
    """
    @app.post("/in-dq-doc")
    def fake():
        pass
    """
    return 1
'''
FX["app/api/lastline/route.ts"] = 'export async function GET() {\n  return Response.json([]);\n}\n\nexport const POST = async () => { await auth(); return Response.json({}); };\n'  # a one-line export that ends the file
FX["app/api/nexts/route.ts"] = 'export async function POSTER() {\n  return Response.json({ ok: true });\n}\n\nexport let { GET } = h;\nexport var { PUT } = h;\n'  # POSTER is no POST
FX["app/api/reqdecoy/route.ts"] = 'export async function POST(req: Request) {\n  const a = prereq.user;\n  const b = req.username;\n  return Response.json({ a, b });\n}\n'
FX["app/api/split/route.ts"] = 'export async function POST(req: Request) {\n  const kind = req.headers.get("x-kind");\n  if (kind !== "ping") return new Response("no", { status: 400 });\n  const token = await mintToken();\n  return Response.json({ token });\n}\n'  # header, comparison and secret word on three lines
FX["pages/api/rev.js"] = 'export default function handler(req, res) {\n  if ("POST" == req.method) return res.json({ ok: true });\n  return res.status(405).end();\n}\n'
FX["pages/api/private/export.ts"] = 'export default function handler(req, res) {\n  res.status(200).json({ ok: true });\n}\n'  # the root middleware matcher covers it
FX["pages/api/helped.ts"] = 'function check(req) {\n  return getServerSession(req);\n}\n\nexport default function handler(req, res) {\n  res.end("x");\n}\n'  # a pages/api handler is the whole file
FX["app/sq/actions.js"] = "'use server';\n\nexport async function sqAction(x) {\n  return x;\n}\n"
FX["apps/m/app/a/tok/route.ts"] = 'export async function POST(req: Request) {\n  if (req.headers.get("x-api-key") !== process.env.ACME_KEY) return new Response("no", { status: 401 });\n  return Response.json({ ok: true });\n}\n'  # a token check outranks the covering middleware
FX["apps/m/middleware.tsx"] = "export const z = 1;\n"  # sorts after the real middleware.ts: must not replace it
FX["apps/rootm/middleware.ts"] = 'export { auth as middleware } from "@/auth";\n\nexport const config = { matcher: ["/:id"] };\n'
FX["apps/rootm/app/route.ts"] = POST1  # `/:id` needs a segment: it does not cover `/`
FX["apps/strmw/middleware.ts"] = 'export function middleware() {}\n\nexport const config = { matcher: ["/auth/:path*"] };\n'  # `auth` only inside a string is no identity check
GOLD += [
    ("server/decoys.js", 'app.post("/dollar"', "HIGH: POST /dollar auth=none"),
    ("server/order.js", 'app.post("/both"', "INFO: POST /both auth=checkJwt"),
    ("server/guard.js", 'app.post("/g"', "INFO: POST /g auth=auth"),
    ("server/guard.js", 'app.post("/g2"', "HIGH: POST /g2 auth=none"),
    ("api/f4.js", 'fastify.post("/sq-hook"', "INFO: POST /sq-hook auth=requireAuth"),
    ("api/contest_api.py", '@app.post("/contest-entry")', "HIGH: POST /contest-entry auth=none"),
    ("api/misc.py", '@app.post("/dotted")', "INFO: POST /dotted auth=login_required"),
    ("api/misc.py", "@app.get('/sq-deco')", "INFO: GET /sq-deco auth=none"),
    ("api/misc.py", '@app.get( "/pad" )', "INFO: GET /pad auth=none"),
    ("api/misc.py", '@app.post("/nested-last")', "HIGH: POST /nested-last auth=none"),
    ("api/strings.py", '@app.post("/after-esc")', "INFO: POST /after-esc auth=login_required"),
    ("api/strings.py", '@app.post("/e-route")', "INFO: POST /e-route auth=login_required"),
    ("api/strings.py", '@app.post("/esc-dq")', "HIGH: POST /esc-dq auth=none"),
    ("api/strings.py", '@app.post("/esc-sq")', "HIGH: POST /esc-sq auth=none"),
    ("api/strings.py", '@app.get("/d1")', "INFO: GET /d1 auth=none"),
    ("app/api/lastline/route.ts", "function GET", "INFO: GET /api/lastline auth=none"),
    ("app/api/lastline/route.ts", "const POST", "INFO: POST /api/lastline auth=auth"),
    ("app/api/nexts/route.ts", "export let { GET }", "INFO: GET /api/nexts auth=none"),
    ("app/api/nexts/route.ts", "export var { PUT }", "HIGH: PUT /api/nexts auth=none"),
    ("app/api/reqdecoy/route.ts", "function POST", "HIGH: POST /api/reqdecoy auth=none"),
    ("app/api/split/route.ts", "function POST", "HIGH: POST /api/split auth=none"),
    ("pages/api/rev.js", "export default", "HIGH: POST /api/rev auth=none"),
    ("pages/api/private/export.ts", "export default", "INFO: ANY /api/private/export auth=middleware"),
    ("pages/api/helped.ts", "export default", "INFO: ANY /api/helped auth=getServerSession"),
    ("app/sq/actions.js", "function sqAction", "HIGH: ACTION sqAction auth=none"),
    ("apps/m/app/a/tok/route.ts", "function POST", "INFO: POST /a/tok auth=token"),
    ("apps/rootm/app/route.ts", "function POST", "HIGH: POST / auth=none"),
]

JS_T = 'const app = require("express")();\napp.post("/t", (req, res) => res.send("t"));\n'
FX["webapp/api/route.ts"] = POST1  # `webapp/` is not an `app/` directory: not a Next route
for rel in ("test/app.js", "tests/app.js", "src/tests/app.js", "e2e/app.js", "__tests__/app.js", "src/x.spec.js", "src/x.test.js"):  # one silent file per TEST alternative
    FX[rel] = JS_T
for rel in ("api/conftest.py", "api/items_test.py", "api/test_items.py"):
    FX[rel] = '@app.post("/t")\ndef t():\n    return 1\n'
QUIET = ("lib/client.js", "lib/keys.js", "lib/plain.ts")  # scanned (they look like they hold a route) but yield no handler row


def write(root, files):
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes): p.write_bytes(text)
        else: p.write_text(text, encoding="utf-8")


def run(script, d, *flags):
    return subprocess.run([sys.executable, "-I", str(script), *flags, str(d)], capture_output=True, text=True)


def golden():
    out = []
    for path, marker, expect in GOLD:
        src = FX[path].decode("latin-1") if isinstance(FX[path], bytes) else FX[path]
        hits = [n for n, line in enumerate(src.splitlines(), 1) if marker in line]
        assert len(hits) == 1, (path, marker, hits)
        out.append("%s:%d: %s" % (path, hits[0], expect))
    return out


def split(res):
    lines = res.stdout.splitlines()
    return lines[:-1], json.loads(lines[-1])


def each(old, a, b, sep=", "):
    """(old, new) mutants that each drop one `sep`-separated member of old (the text between its first `a` and its last `b`)."""
    i, j = old.index(a) + len(a), old.rindex(b)
    ms = old[i:j].split(sep)
    return [(old, old[:i] + sep.join(ms[:k] + ms[k + 1:]) + old[j:]) for k in range(len(ms))]


# One row per rule: replacing `old` (which must occur exactly once in route_auth_map.py) by `new` must change what the script prints.
MUTANTS = [
    # header: the sibling import must work under -I and leave no bytecode beside the script
    ("sys.dont_write_bytecode = True", "sys.dont_write_bytecode = False"),
    ("sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))", "pass"),
    # configuration
    *each('RECEIVERS = {"app", "router", "server", "fastify"}', "{", "}"),
    *each('EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")', "(", ")"),
    *each('VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")', "(", ")"),
    ('MARK = "route-auth-ok"', 'MARK = "route-auth-no"'),
    ("H = V.lower()", "H = V"),
    # IDENTITY regex members (the plain members are mutated one by one in identity_mutants)
    *each(r"require(?:Auth|User|Session|Login|Admin)\w*", "(?:", ")", "|"),
    *each(r"auth(?:Middleware|Guard)", "(?:", ")", "|"),
    *each(r"ensure(?:Auth|LoggedIn)\w*", "(?:", ")", "|"),
    (r"require(?:Auth|User|Session|Login|Admin)\w*", r"require(?:Auth|User|Session|Login|Admin)"),
    (r"ensure(?:Auth|LoggedIn)\w*", r"ensure(?:Auth|LoggedIn)"),
    (r"authenticate\w*", "authenticate"), (r"authorize\w*", "authorize"), (r'verify\w*"', 'verify"'), (r'get_current_\w+"', 'get_current_"'),
    # CALL / USE: a called or bare identity name, not the tail of a longer name or an object key
    (r"(?<![\w$])(%s)\(", r"(?<![\w])(%s)\("), (r"(?<![\w$])(%s)\(", r"(%s)\("), (r"(?<![\w$])(%s)\(", r"(?<![\w$])(%s)"),
    (r"(?<![\w$])(%s)\b(?!:)", r"(?<![\w])(%s)\b(?!:)"), (r"(?<![\w$])(%s)\b(?!:)", r"(%s)\b(?!:)"),
    (r"(?<![\w$])(%s)\b(?!:)", r"(?<![\w$])(%s)(?!:)"), (r"(?<![\w$])(%s)\b(?!:)", r"(?<![\w$])(%s)\b"),
    # DECO: a decorator, not a route decorator on a blueprint that happens to be named like an identity check
    (r"@(?:\w+\.)*(%s)", r"@(%s)"),
    (r"(%s)\b(?!\.(?:%s|route)\()", r"(%s)(?!\.(?:%s|route)\()"),
    (r'(%s)\b(?!\.(?:%s|route)\()" % (ID, H))', r'(%s)\b" % ID)'),
    (r"(?:%s|route)", r"(?:%s)"),
    (r'(?!\.(?:%s|route)\()" % (ID, H))', r'(?!\.route\()" % ID)'),
    # DEP: Depends/Security with an identity-looking dependency
    (r"(?:Depends|Security)", "Depends"), (r"(?:Depends|Security)", "Security"),
    (r"\(\s*[\w.]*(?:user", r"\([\w.]*(?:user"), (r"\(\s*[\w.]*(?:user", r"\(\s*(?:user"),
    *each(r"(?:user|auth|token|current|bearer|jwt|api_?key|verify|login)", "(?:", ")", "|"),
    (r"api_?key", "api_key"), (r"api_?key", "apikey"),
    (r'login)\w*", re.I)', r'login)", re.I)'), (r'login)\w*", re.I)', r'login)\w*")'),
    # REQ: the request's user, not a mere import of the name
    (r'"\b((?:req', r'"((?:req'), (r'g\.user)\b")', r'g\.user)")'),
    (r"(?:req|request)", "(?:request)"), (r"(?:req|request)", "(?:req)"),
    (r"(?:user|auth)", "(?:user)"), (r"(?:user|auth)", "(?:auth)"),
    (r"|current_user(?=\.)", ""), (r"current_user(?=\.)", "current_user"), (r"|g\.user)", ")"),
    # token: a header read plus a secret comparison on one line
    *each(r"[!=]=|timingSafeEqual|compare_digest", "", "", "|"),
    (r"[!=]=|timingSafeEqual", r"==|timingSafeEqual"), (r"[!=]=|timingSafeEqual", r"!=|timingSafeEqual"),
    *each(r"secret|token|api.?key|password", "", "", "|"),
    (r"api.?key", "api.key"), (r"api.?key", "apikey"), (r'password", re.I)', 'password")'),
    (r'header|authorization", re.I)', r'headers|authorization", re.I)'),
    (r'header|authorization", re.I)', r'authorization", re.I)'), (r'header|authorization", re.I)', r'header", re.I)'),
    (r'header|authorization", re.I)', r'header|authorization")'),
    # TEST: test files are skipped, a name that merely contains the word is not
    (r"\.(?:test|spec)\.", r".(?:test|spec)."), (r"\.(?:test|spec)\.", r"(?:test|spec)\."),
    (r"\.(?:test|spec)\.", r"\.(?:test)\."), (r"\.(?:test|spec)\.", r"\.(?:spec)\."),
    (r"(?:^|/)(?:__tests__", r"/(?:__tests__"), (r"(?:^|/)(?:__tests__", r"^(?:__tests__"), (r"(?:^|/)(?:__tests__", r"(?:__tests__"),
    *each(r"(?:__tests__|tests?|e2e)", "(?:", ")", "|"),
    (r"tests?|e2e", "tests|e2e"), (r"tests?|e2e", "test|e2e"),
    (r"(?:^|/)(?:test_[^/]*", r"/(?:test_[^/]*"), (r"(?:^|/)(?:test_[^/]*", r"^(?:test_[^/]*"), (r"(?:^|/)(?:test_[^/]*", r"(?:test_[^/]*"),
    *each(r"(?:test_[^/]*|[^/]*_test|conftest)", "(?:", ")", "|"),
    (r"test_[^/]*|", "test_|"), (r"|[^/]*_test|", "|_test|"),
    # Next file conventions
    (r"(?:(.*)/)?app/", r"(?:(.*)/)app/"), (r"app/(?:(.*)/)?route", r"app/(?:(.*)/)route"),
    (r"route\.(?:[tj]sx?|mjs)$", r"route\.(?:tsx?|mjs)$"), (r"route\.(?:[tj]sx?|mjs)$", r"route\.(?:jsx?|mjs)$"), (r"route\.(?:[tj]sx?|mjs)$", r"route\.(?:[tj]s|mjs)$"),
    (r"route\.(?:[tj]sx?|mjs)$", r"route\.(?:[tj]sx?)$"), (r"route\.(?:[tj]sx?|mjs)$", r"route\.(?:[tj]sx?|mjs)"),
    (r"(?:(.*)/)?pages/", r"(?:(.*)/)pages/"),
    (r"(api/.+)\.(?:[tj]sx?|mjs)$", r"(api/.+)\.(?:tsx?|mjs)$"), (r"(api/.+)\.(?:[tj]sx?|mjs)$", r"(api/.+)\.(?:jsx?|mjs)$"), (r"(api/.+)\.(?:[tj]sx?|mjs)$", r"(api/.+)\.(?:[tj]s|mjs)$"),
    (r"(api/.+)\.(?:[tj]sx?|mjs)$", r"(api/.+)\.(?:[tj]sx?)$"), (r"(api/.+)\.(?:[tj]sx?|mjs)$", r"(api/.+)\.(?:[tj]sx?|mjs)"),
    (r"(?:middleware|proxy)\.[jt]s", r"(?:middleware)\.[jt]s"), (r"(?:middleware|proxy)\.[jt]s", r"(?:proxy)\.[jt]s"),
    (r"(?:middleware|proxy)\.[jt]s", r"(?:middleware|proxy)\.ts"), (r"(?:middleware|proxy)\.[jt]s", r"(?:middleware|proxy)\.js"),
    # span ends and function tables
    (r'END = re.compile(r"^\S", re.M)', r'END = re.compile(r"^\S")'), (r'END = re.compile(r"^\S", re.M)', r'END = re.compile(r"^\w", re.M)'),
    (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", r"^(?:async\s+)?function\s+(\w+)"),
    (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", r"^(?:export\s+)?function\s+(\w+)"),
    (r"|^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", r"|^(?:const|let|var)\s+(\w+)\s*="),
    (r"(?:const|let|var)\s+(\w+)\s*=", r"(?:let|var)\s+(\w+)\s*="), (r"(?:const|let|var)\s+(\w+)\s*=", r"(?:const|var)\s+(\w+)\s*="),
    (r"(?:const|let|var)\s+(\w+)\s*=", r"(?:const|let)\s+(\w+)\s*="),
    *each(r"(?:async\b|function\b|\()", "(?:", ")", "|"),
    (r'|\()", re.M)', r'|\()")'),
    (r"^(?:@[^\n]*\n)*(?:async[ \t]+)?def", r"^(?:async[ \t]+)?def"), (r"^(?:@[^\n]*\n)*(?:async[ \t]+)?def", r"^(?:@[^\n]*\n)*def"),
    (r'def[ \t]+(\w+)", re.M)', r'def[ \t]+(\w+)")'),
    # PYSTR: comments, triple quotes, double and single quoted strings (escapes included) are masked
    (r"#[^\n]*|", ""),
    ('("""|' + r"\'\'\')", r"(\'\'\')"), ('("""|' + r"\'\'\')", '(""")'),
    (r'|"(?:\\.|[^"\\\n])*"|', "|"), (r"|\'(?:\\.|[^\'\\\n])*\'", ""),
    (r'"(?:\\.|[^"\\\n])*"', r'"(?:[^"\\\n])*"'), (r"\'(?:\\.|[^\'\\\n])*\'", r"\'(?:[^\'\\\n])*\'"),
    (r"(?:\\.|(?!\1).)*?\1", r"(?:(?!\1).)*?\1"),
    (r"\'\'\'", r"\'\'"),
    # route-call literals, Fastify hooks, receivers declared in the file
    (r"""(["'`])(/""", r"""(['`])(/"""), (r"""(["'`])(/""", r"""(["`])(/"""), (r"""(["'`])(/""", r"""(["'])(/"""),
    (r"""[^"'`$]*""", r"""[^"'`]*"""),
    *each(r"(?:onRequest|preHandler|preValidation|preParsing)", "(?:", ")", "|"),
    (r"""(["'])(?:onRequest""", r"""(["])(?:onRequest"""), (r"""(["'])(?:onRequest""", r"""(['])(?:onRequest"""),
    *each(r"(?:express|Router|Hono|Fastify|fastify|Elysia)", "(?:", ")", "|"),
    (r"(?:await\s+)?", ""), (r"(?:new\s+)?", ""), (r"(?::[^=\n]+)?", ""),
    (r"^([ \t]*)@", r"^()@"), (r"@\w+\.(%s|route)", r"@\w\.(%s|route)"), (r'(%s|route)\(" % H, re.M)', r'(%s)\(" % H, re.M)'),
    (r'" % H, re.M)', r'" % H)'),
    (r"(?:%s|all)\(|use", r"(?:%s)\(|use"), (r'|use server"', '"'),
    # pymask
    (r'if t[0] == "#": return sp(t)', r'if t[0] == "#": return t'),
    # ident
    ("(CALL, DECO, DEP, REQ)", "(DECO, DEP, REQ)"), ("(CALL, DECO, DEP, REQ)", "(CALL, DEP, REQ)"),
    ("(CALL, DECO, DEP, REQ)", "(CALL, DECO, REQ)"), ("(CALL, DECO, DEP, REQ)", "(CALL, DECO, DEP)"),
    ("((USE,) if bare else ())", "()"), ("((USE,) if bare else ())", "(USE,)"),
    ("min(hits)[1]", "hits[0][1]"), ("min(hits)[1]", "max(hits)[1]"),
    ("if rx is DEP else x.group(1)", "if rx is CALL else x.group(1)"),
    ('re.sub(r"\\s+", "", x.group(0)) + ")"', 'x.group(0) + ")"'),
    # tok
    ("bool(HDR.search(k)) and any(", "any("), ("bool(HDR.search(k)) and any(", "bool(HDR.search(k)) or any("),
    ("any(CMP.search(l) and SEC.search(l) for l in k.splitlines())", "all(CMP.search(l) and SEC.search(l) for l in k.splitlines())"),
    ("CMP.search(l) and SEC.search(l)", "CMP.search(l) or SEC.search(l)"), ("for l in k.splitlines()", "for l in [k]"),
    # seg / nroute / pyroute
    (r"\[\[?\.\.\.", r"\[\.\.\."), (r"(\w+)\]?\]", r"(\w+)\]"), ('":%s*"', '":%s"'),
    (r'if not re.fullmatch(r"\(.*\)", s)', "if True"), ('return "/" + "/".join(', 'return "/".join('),
    (r"<(?:[\w.]+:)?(\w+)>", r"<(\w+)>"), (r"\{(\w+)(?::[^}]*)?\}", r"\{(\w+)\}"),
    ('return p if p.startswith("/") else "/" + p', "return p"),
    # methods / items
    (r"\bmethod\s*[!=]==?", r"\bmethod\s*==="), (r"[!=]==?\s*\w+\.method", r"===\s*\w+\.method"),
    (r"""k.replace("'", '"')""", "k"), ("[v for v in VERBS if v in found]", "sorted(found)"),
    (r"(?::|\bas\b)", r"(?::)"), (r"(?::|\bas\b)", r"(?:\bas\b)"),
    ("(p[0], p[-1])", "(p[0], p[0])"), ("(p[0], p[-1])", "(p[-1], p[-1])"),
    # nextdecl / defs
    ("END.search(m, i + 1)", "END.search(m, i)"), ("return x.start() if x else len(m)", "return x.start() if x else 0"),
    ("(PYFN if py else JSFN)", "(JSFN if py else PYFN)"), ("e.start() if e else len(m))", "e.start() if e else 0)"),
    # p2re
    (r're.sub(r"/:\w+\*", "(?:/.*)?", p)', "p"), (r'"(?:/.*)?"', r'"/.*"'),
    (r're.sub(r"/:\w+\+", "/.+", p)', "p"),
    (r're.sub(r"/:\w+\?", "(?:/[^/]+)?", p)', "p"), (r'"(?:/[^/]+)?"', r'"(?:/.+)?"'),
    (r"(?<!\?):\w+", r":\w+"), (r'"[^/]+", p)', r'"[^/]*", p)'),
    # mw_pats
    ('if not (ident(m, True) or "next-auth/middleware" in mk or REFUSE.search(mk)): return []', 'if not (ident(m, True) or REFUSE.search(mk)): return []'),
    ('if not (ident(m, True) or "next-auth/middleware" in mk or REFUSE.search(mk)): return []', 'if not ("next-auth/middleware" in mk or REFUSE.search(mk)): return []'),
    ('if not (ident(m, True) or "next-auth/middleware" in mk or REFUSE.search(mk)): return []', 'if not (ident(m) or "next-auth/middleware" in mk or REFUSE.search(mk)): return []'),
    # REFUSE: a middleware that can answer 401/403 gates what its matcher covers (the comment is the call site, the rest the regex)
    ('"next-auth/middleware" in mk or REFUSE.search(mk)', '"next-auth/middleware" in mk'), ("or REFUSE.search(mk)", "or True"),
    ("or REFUSE.search(mk)", "and REFUSE.search(mk)"), ("REFUSE.search(mk)", "REFUSE.search(m)"),
    ("mw_pats(mask(raw), mask(raw, True))", "mw_pats(mask(raw), raw)"),
    (r"\bstatus[:(]", r"status[:(]"), (r"[:(]\s*40", r"[(]\s*40"), (r"[:(]\s*40", r"[:]\s*40"),
    (r"[:(]\s*40", r"[:(]40"), (r"[:(]\s*40", r"[:(]\s40"), (r"[:(]\s*40", r"[:(]\s+40"),
    ("40[13]|", "40[1]|"), ("40[13]|", "40[3]|"), ("40[13]|", "40[123]|"), ("40[13]|", "40.|"),
    (r"""\bstatus[:(]\s*40[13]|Response""", "Response"), (r"""|Response\(\s*["'](?:Unauthorized|Forbidden)""", ""),
    (r"""|Response\(\s*["']""", r"""|["']"""), (r"""|Response\(""", r"""|\bResponse\("""),
    (r"Response\(\s*", r"Response\s*"), (r"Response\(\s*", r"Response\("),
    (r"""["'](?:Unauthorized""", r"""["](?:Unauthorized"""), (r"""["'](?:Unauthorized""", r"""['](?:Unauthorized"""),
    ("(?:Unauthorized|Forbidden)", "(?:Unauthorized)"), ("(?:Unauthorized|Forbidden)", "(?:Forbidden)"),
    ('if not x: return [re.compile(opn + ".*")]', "if not x: return []"), ('re.compile(opn + ".*")', 're.compile(opn + ".")'),
    ('re.compile(opn + ".*")', 're.compile(".*")'), ("x.end() if x else len(m)", "x.start() if x else len(m)"),
    ('close_of(m, i) if c == "["', 'close_of(m, i) if c == "("'), ("m.find(c, i + 1)", "m.find(c, i)"),
    ("""c in ("'", '"', "`") else -1""", """c in ('"', "`") else -1"""), ("""c in ("'", '"', "`") else -1""", """c in ("'", "`") else -1"""),
    ("""c in ("'", '"', "`") else -1""", """c in ("'", '"') else -1"""), ("""c in ("'", '"', "`") else -1""", """c in ("'", '"', "`") else len(m)"""),
    ("mk[i:j + 1]", "mk[i:j]"), (r'p.replace("\\\\", "\\")', "p"), ("except re.error: pass", "except re.error: raise"),
    # allow-lists: a quoted /path in the file takes its route and what is under it out of the matcher's coverage, unless it is a scope check
    ("pats.append(re.compile(opn + p2re(p)))", "pats.append(re.compile(p2re(p)))"), ('"(?!%s(?:/|$))"', '"(?=%s(?:/|$))"'),
    ("%s(?:/|$))", "%s(?:/))"), ("%s(?:/|$))", "%s(?:$))"), ("%s(?:/|$))", "%s)"),
    ("re.escape(q)", "q"), ('GLOB.sub("", g[2]).rstrip("/")', 'GLOB.sub("", g[2])'), ('GLOB.sub("", g[2]).rstrip("/")', 'GLOB.sub("", g[1]).rstrip("/")'),
    # glob-style literals (a Clerk createRouteMatcher list): a trailing (.*), /* or /:name* is dropped, and only a trailing one, before the slash is
    ('GLOB.sub("", g[2]).rstrip("/")', 'g[2].rstrip("/")'), ('GLOB.sub("", g[2]).rstrip("/")', 'GLOB.sub("", g[2].rstrip("/"))'),
    (r"(?:\(\.\*\)|/\*|/:\w+\*)$", r"(?:/\*|/:\w+\*)$"), (r"(?:\(\.\*\)|/\*|/:\w+\*)$", r"(?:\(\.\*\)|/:\w+\*)$"),
    (r"(?:\(\.\*\)|/\*|/:\w+\*)$", r"(?:\(\.\*\)|/\*)$"), (r"(?:\(\.\*\)|/\*|/:\w+\*)$", r"(?:\(\.\*\)|/\*|/:\w\*)$"),
    (r"(?:\(\.\*\)|/\*|/:\w+\*)$", r"(?:\(\.\*\)|/\*|/:\w+\*)"),
    ("if q and not any(p.startswith(q) for p in ms)", "if not any(p.startswith(q) for p in ms)"),
    ("if q and not any(p.startswith(q) for p in ms)", "if q"), ("if q and not any(p.startswith(q) for p in ms)", "if q and any(p.startswith(q) for p in ms)"),
    ("p.startswith(q) for p in ms", 'p.startswith(q + "/") for p in ms'), ("p.startswith(q) for p in ms", "p == q for p in ms"),
    ("LIT.finditer(mk)", "LIT.finditer(m)"), ("LIT.finditer(mk)", "LIT.finditer(mk[:i])"), ("LIT.finditer(mk)", "LIT.finditer(mk[j + 1:])"),
    # scope checks: a quoted /path in the condition of an `if` whose body can refuse protects its area, it is no exemption
    ("sc = refusing_ifs(m, mk)", "sc = []"), ("sc = refusing_ifs(m, mk)", "sc = refusing_ifs(m, m)"),
    ("if not any(a < g.start() < b for a, b in sc)", "if not sc"), ("if not any(a < g.start() < b for a, b in sc)", "if any(a < g.start() < b for a, b in sc)"),
    ("a < g.start() < b", "a < g.start()"), ("a < g.start() < b", "g.start() < b"), ("a < g.start() < b", "a < g.end() < b"),
    (r'r"\bif\s*\("', r'r"\bif\("'), (r'r"\bif\s*\("', r'r"\bif\s+\("'), (r'r"\bif\s*\("', r'r"\bif \("'),
    ("a = t.end() - 1", "a = t.end()"), ("b = close_of(m, a)", "b = close_of(mk, a)"), ("out.append((a, b))", "out.append((a, e))"),
    # the body: where it starts, a braced block (not its else) or one statement that ends at `;` or a line break outside brackets
    ("s = b + 1", "s = b"), ("while m[s:s + 1].isspace(): s += 1", 'while m[s:s + 1] == " ": s += 1'),
    ('if m[s:s + 1] == "{": e = close_of(m, s)', 'if m[s:s + 1] == "(": e = close_of(m, s)'),
    ("e = close_of(m, s)", "e = close_of(mk, s)"), ("e = close_of(m, s)", "e = len(m)"), ("e = close_of(m, s)", 'e = m.find("}", s)'),
    ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in ")]}") - (j[e] in "([{")'), ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "([{") - (j[e] in ")]")'),
    ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "([") - (j[e] in ")]}")'), ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "({") - (j[e] in ")]}")'),
    ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "[{") - (j[e] in ")]}")'), ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "([{") - (j[e] in "]}")'),
    ('d += (j[e] in "([{") - (j[e] in ")]}")', 'd += (j[e] in "([{") - (j[e] in ")}")'),
    ('if d < 1 and j[e] in ";\\n": break', 'if d < 2 and j[e] in ";\\n": break'), ('if d < 1 and j[e] in ";\\n": break', 'if d < 0 and j[e] in ";\\n": break'),
    ('if d < 1 and j[e] in ";\\n": break', 'if j[e] in ";\\n": break'), ('j[e] in ";\\n"', 'j[e] in "\\n"'), ('j[e] in ";\\n"', 'j[e] in ";"'),
    # a statement that carries on over a line break (the next line starts with . ? : && ||, or this one ends in ? : && ||) stays one body: JOIN reads those breaks as spaces
    ('if d < 1 and j[e] in ";\\n": break', 'if d < 1 and m[e] in ";\\n": break'), ('j = JOIN.sub(lambda x: x[0].replace("\\n", " "), m)', "j = m"),
    ('x[0].replace("\\n", " ")', "x[0]"), ('x[0].replace("\\n", " ")', 'x[0].replace("\\n", "")'),
    (r"(?:[?:]|&&|\|\|)\s*", r"(?:[:]|&&|\|\|)\s*"), (r"(?:[?:]|&&|\|\|)\s*", r"(?:[?]|&&|\|\|)\s*"),
    (r"(?:[?:]|&&|\|\|)\s*", r"(?:[?:]|\|\|)\s*"), (r"(?:[?:]|&&|\|\|)\s*", r"(?:[?:]|&&)\s*"),
    (r"(?:[?:]|&&|\|\|)\s*", r"(?:[?:]|&&|\|\|)"), (r"(?:[?:]|&&|\|\|)\s*", r"(?:[?:]|&&|\|\|)[ \t]*"),
    (r"(?<!\s)\s+(?=", r"(?<!\s)[ \t]+(?="), (r"(?<!\s)\s+(?=", r"(?<!s)\s+(?="),
    (r"(?=[.?:]|&&|\|\|)", r"(?=[?:]|&&|\|\|)"), (r"(?=[.?:]|&&|\|\|)", r"(?=[.:]|&&|\|\|)"), (r"(?=[.?:]|&&|\|\|)", r"(?=[.?]|&&|\|\|)"),
    (r"(?=[.?:]|&&|\|\|)", r"(?=[.?:]|\|\|)"), (r"(?=[.?:]|&&|\|\|)", r"(?=[.?:]|&&)"),
    ("if REFUSE.search(mk[s:e + 1]):", "if True:"), ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk)"),
    ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk[s:])"), ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk[:e + 1])"),
    # next_hs
    (r"(?:async\s+)?function\s+(%s)\b", r"function\s+(%s)\b"),
    (r"(?:const|let|var)\s+(%s)\b", r"(?:let|var)\s+(%s)\b"), (r"(?:const|let|var)\s+(%s)\b", r"(?:const|var)\s+(%s)\b"),
    (r"(?:const|let|var)\s+(%s)\b", r"(?:const|let)\s+(%s)\b"),
    (r"function\s+(%s)\b|", r"function\s+(%s)|"), (r'\s+(%s)\b" % (V, V)', r'\s+(%s)" % (V, V)'),
    ("% (V, V), m, re.M)", "% (V, V), m)"),
    ("hs.append((t.start(), t.group(1) or t.group(2), route", "hs.append((t.start(), t.group(1), route"),
    (r"(?:const|let|var)\s*\{", r"(?:let|var)\s*\{"), (r"(?:const|let|var)\s*\{", r"(?:const|var)\s*\{"), (r"(?:const|let|var)\s*\{", r"(?:const|let)\s*\{"),
    ("for _, ex in items(t.group(1)) if ex in VERBS", "for _, ex in items(t.group(1))"),
    ("for lo, ex in items(t.group(1)) if ex in VERBS", "for lo, ex in items(t.group(1))"),
    ("[fn[lo]] if lo in fn else []", "[fn[lo]]"),
    # call_hs
    ("rcv = RECEIVERS | set(RCV.findall(m))", "rcv = RECEIVERS"),
    (r"(use|addHook|%s|all)", r"(addHook|%s|all)"), (r"(use|addHook|%s|all)", r"(use|%s|all)"), (r"(use|addHook|%s|all)", r"(use|addHook|%s)"),
    ("cl = close_of(m, op) if r in rcv else -1", "cl = close_of(m, op)"),
    ("if not ps: continue", "if not ps: pass"), ("p0 = ps[0][1].strip()", "p0 = ps[0][1]"), ("lit = LIT.fullmatch(p0)", "lit = LIT.match(p0)"),
    ('if k in ("use", "addHook"):', 'if k == "use":'), ("gone.append((t.start(), cl + 1))", "pass"),
    ('if k == "addHook" and not HOOK.fullmatch(p0): continue', "pass"), ('if k == "addHook" and not HOOK.fullmatch(p0): continue', 'if k == "addHook" and HOOK.fullmatch(p0): continue'),
    ('lab = ident(",".join(a[0] for a in ps), True)', 'lab = ident(",".join(a[0] for a in ps))'),
    ("uses.append((r, t.start(),", "uses.append((None, t.start(),"), ("uses.append((r, t.start(),", "uses.append((r, 0,"),
    ('.rstrip("*/") if lit else ""', '.rstrip("*") if lit else ""'), ('.rstrip("*/") if lit else ""', '.rstrip("/") if lit else ""'),
    ('.rstrip("*/") if lit else ""', 'if lit else ""'), ('.rstrip("*/") if lit else ""', '.rstrip("*/") if lit else "/"'),
    ("elif lit and len(ps) > 1:", "elif lit:"), ("elif lit and len(ps) > 1:", "elif lit and len(ps) > 2:"), ("gone.append((op, cl + 1))", "pass"),
    ('"ANY" if k == "all" else k.upper()', "k.upper()"), ('"ANY" if k == "all" else k.upper()', '"ANY" if k == "all" else k'),
    ("lit.group(2), [(op", "lit.group(0), [(op"),
    ('ident(",".join(a[0] for a in ps[:-1]), True), r, None', 'ident(",".join(a[0] for a in ps), True), r, None'),
    ('ident(",".join(a[0] for a in ps[:-1]), True), r, None', 'ident(",".join(a[0] for a in ps[:-1])), r, None'),
    ('ident(",".join(a[0] for a in ps[:-1]), True), r, None', 'ident(",".join(a[0] for a in ps[:-1]), True), None, None'),
    # py_hs
    ("pm = ps and re.fullmatch(", "pm = re.fullmatch("), ("ps[0][1].strip())", "ps[0][1])"),
    (r"""(/[^"']*|)""", r"""(/[^"']*)"""), (r"""(["'])(/[^"']*|)""", r"""(["])(/[^"']*|)"""), (r"""(["'])(/[^"']*|)""", r"""(['])(/[^"']*|)"""),
    ("dm = PYDEF.search(m, cl) if pm else None", "dm = PYDEF.search(m, cl)"), ("if sc < 0: continue", "if False: continue"),
    (r"[\[(]([^\])]*)", r"\[([^\])]*)"),
    ('meths = [t.group(2).upper()]', "meths = [t.group(2)]"), ("km.group(1), re.I)]", "km.group(1))]"),
    (r"""['"]%s['"]""", r"""["]%s["]"""), (r"""['"]%s['"]""", r"""[']%s[']"""),
    ('else: meths = ["GET"]', 'else: meths = ["ANY"]'), ("if not meths: continue", "if not meths: pass"),
    (r"[ \t]{0,%d}(?=\S)", r"[ \t]{%d}(?=\S)"), ("% len(t.group(1))", "% 0"), ("end = e.start() if e else len(m)", "end = e.start() if e else 0"),
    ("[(t.start(), dm.start()), (dm.end() - 1, end)]", "[(dm.start(), dm.start()), (dm.end() - 1, end)]"),
    ("[(t.start(), dm.start()), (dm.end() - 1, end)]", "[(t.start(), dm.start())]"),
    # analyze
    ("mk_ = pymask if py else mask", "mk_ = mask"),
    ('nroute(n.group(2) or "")', "nroute(n.group(2))"), ('n.group(1) or "", hs', "n.group(1), hs"), ('p.group(1) or ""))', "p.group(1)))"),
    ('"|".join(methods(mk)) or "ANY"', '"|".join(methods(mk)) or "GET"'),
    ('segs[:-1] if segs[-1] == "index" else segs', "segs"), ('segs[-1] == "index"', 'segs[-1] != "index"'), ("[(0, len(m))]", "[(0, 0)]"),
    (r"(?:export\s+default|module\.exports)", r"(?:module\.exports)"), (r"(?:export\s+default|module\.exports)", r"(?:export\s+default)"),
    (r'module\.exports)", m, re.M)', r'module\.exports)", m)'),
    ("d.start() if d else 0", "0"),
    ("if re.match(", "if re.search("), (r"""r"\s*(['\"])use server\1", mk)""", r"""r"(['\"])use server\1", mk)"""),
    (r"""r"\s*(['\"])use server\1", mk)""", r"""r"\s*(['])use server\1", mk)"""), (r"""r"\s*(['\"])use server\1", mk)""", r"""r"\s*([\"])use server\1", mk)"""),
    (r"^export\s+async\s+function\s+(\w+)|", r"^export\s+function\s+(\w+)|"),
    (r"|^export\s+const\s+(\w+)\s*=\s*async\b", r"|^export\s+const\s+(\w+)\s*=\s*"),
    ("hide = gone + list(fn.values())", "hide = gone"), ("hide = gone + list(fn.values())", "hide = list(fn.values())"),
    ("mod = ident(blank(m, hide))", "mod = ident(m)"),
    ("+ [(mod, False)]", ""), ("+ [(mod, False)]", "+ [(mod, True)]"),
    ('for a, b in spans + [fn[w] for w in sorted(set(re.findall(r"[\\w$]+", own))) if w in fn]]', "for a, b in spans]"),
    ("tok(mk[a:b])", "tok(m[a:b])"), ("ident(m[a:b])", "ident(m[a:b], True)"),
    ("u[0] == rcv and u[1] < pos and", "u[1] < pos and"), ("u[0] == rcv and u[1] < pos and", "u[0] == rcv and"),
    ('(route == u[2] or route.startswith(u[2] + "/"))', 'route.startswith(u[2] + "/")'),
    ('(route == u[2] or route.startswith(u[2] + "/"))', "(route == u[2] or route.startswith(u[2]))"),
    ('(route == u[2] or route.startswith(u[2] + "/"))', "route == u[2]"),
    ("mws.get(mwb) if mwb is not None else None", "mws.get(mwb) if mwb else None"),
    ("x.fullmatch(route)", "x.match(route)"), ("x.fullmatch(route)", "x.search(route)"),
    ("any(x.fullmatch(route) for x in pats)", "all(x.fullmatch(route) for x in pats)"),
    ("lab = pre or use or", "lab = use or"), ("lab = pre or use or", "lab = pre or"), ("lab = pre or use or", "lab = use or pre or"),
    ('next((g[0] for g in got if g[0]), None) or ("token"', '("token"'),
    ('or ("token" if any(g[1] for g in got) else None) or mw', "or mw"), ("else None) or mw or \"none\"", 'else None) or "none"'),
    ('or ("token" if any(g[1] for g in got) else None) or mw or "none"', 'or mw or ("token" if any(g[1] for g in got) else None) or "none"'),
    ("any(g[1] for g in got)", "all(g[1] for g in got)"),
    ("rl[max(0, ln - 2):ln]", "rl[max(0, ln - 1):ln]"), ("rl[max(0, ln - 2):ln]", "rl[max(0, ln - 3):ln]"),
    ("rl[max(0, ln - 2):ln]", "rl[max(0, ln - 2):ln - 1]"), ("rl[max(0, ln - 2):ln]", "rl[max(0, ln - 2):ln + 1]"), ("rl[max(0, ln - 2):ln]", "rl[ln - 2:ln]"),
    # read / scan
    ('encoding="utf-8-sig"', 'encoding="utf-8"'), ('errors="replace"', 'errors="strict"'), ("except OSError: return None", "except OSError: raise"),
    ("dn[:] = sorted(d for d in dn if d not in SKIP_DIR)", "dn[:] = sorted(dn)"),
    ("if f.endswith(EXT) and not TEST.search(rel)", "if f.endswith(EXT)"), ("TEST.search(rel)", "TEST.match(rel)"),
    ("MWF.fullmatch(os.path.basename(rel))", "MWF.fullmatch(rel)"), ("MWF.fullmatch(os.path.basename(rel))", "MWF.match(os.path.basename(rel))"),
    ("MWF.fullmatch(os.path.basename(rel))", "MWF.search(os.path.basename(rel))"),
    ("mw_pats(mask(raw), mask(raw, True))", "mw_pats(mask(raw, True), mask(raw, True))"),
    ("if raw is None or not (NAPP", "if not (NAPP"), ("not (NAPP.match(rel) or NAPI", "not (NAPI"), ("or NAPI.match(rel) or (PYDEC", "or (PYDEC"),
    ('(PYDEC if rel.endswith(".py") else JSPRE)', '(JSPRE if rel.endswith(".py") else PYDEC)'), ("seen += 1", "seen += 2"),
    # main
    ("len(a) != 1 or not os.path.isdir(a[0])", "len(a) < 1 or not os.path.isdir(a[0])"), ("len(a) != 1 or not os.path.isdir(a[0])", "len(a) != 1"),
    ("print(\"usage: route_auth_map.py [--paths] DIR\", file=sys.stderr); return 2", "print(\"usage: route_auth_map.py [--paths] DIR\", file=sys.stderr); return 1"),
    ('if "--paths" in argv[1:]:', 'if "--paths" in argv[2:]:'),
    ('{"GET", "ANY"} & set(r[2].split("|"))', '{"GET"} & set(r[2].split("|"))'), ('{"GET", "ANY"} & set(r[2].split("|"))', '{"ANY"} & set(r[2].split("|"))'),
    ('{"GET", "ANY"} & set(r[2].split("|"))', '{"GET", "ANY"} & {r[2]}'),
    ("        return 0\n    out =", "        return 1\n    out ="),
    ('r[4] == "none" and any(x != "GET" for x in r[2].split("|"))', 'r[4] != "public" and any(x != "GET" for x in r[2].split("|"))'),
    ('r[4] == "none" and any(x != "GET" for x in r[2].split("|"))', 'r[4] == "none" and all(x != "GET" for x in r[2].split("|"))'),
    ('r[4] == "none" and any(x != "GET" for x in r[2].split("|"))', 'r[4] == "none" and any(x == "POST" for x in r[2].split("|"))'),
    ('r[4] == "none" and any(x != "GET" for x in r[2].split("|"))', 'any(x != "GET" for x in r[2].split("|"))'),
    ('"%s:%d: %s: %s %s auth=%s" % (r[0], r[1], s, r[2], r[3], r[4])', '("%s:%d: %s: %s %s auth=%s" % (r[0], r[1], s, r[2], r[3], r[4]))[:-1]'),
]


def mutants(src):
    """([(label, mutated script)], [bad rows]): every MUTANTS row applied once, plus each IDENTITY name replaced by a nonsense one."""
    ok, bad = [], []
    for old, new in MUTANTS:
        if src.count(old) == 1 and old != new: ok.append((old[:70], src.replace(old, new)))
        else: bad.append(old[:70])
    a, b = src.index("IDENTITY = ("), src.index("RECEIVERS =")
    ok += [(t.group(0), src[:a + t.start()] + '"zz9"' + src[a + t.end():]) for t in re.finditer(r'r?"[^"\n]*"', src[a:b])]
    return ok, bad


def verdict(text, fx, base):
    """Run a copy of the script holding text (beside its sibling) over the probes: "killed" when any output differs from base, "broken" when it does not compile, else "alive"."""
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(SK / "tenant_scope_check.py", d)
        script = Path(d) / "route_auth_map.py"
        script.write_text(text, encoding="utf-8")
        try: compile(text, "mutant", "exec")
        except SyntaxError: return "broken"
        for argv, want in zip(probes(fx), base):
            try:
                r = subprocess.run([sys.executable, "-I", str(script), *argv], capture_output=True, encoding="utf-8", errors="replace", timeout=30)
            except subprocess.TimeoutExpired:
                return "killed"
            if (r.returncode, r.stdout, r.stderr) != want: return "killed"
        return "killed" if sorted(os.listdir(d)) != ["route_auth_map.py", "tenant_scope_check.py"] else "alive"  # a leftover __pycache__ is a change too


def probes(fx):
    """argv lists, the most telling first (a killed mutant stops at its first difference): the scan, --paths, then the usage errors."""
    return [[str(fx)], ["--paths", str(fx)], [], [str(fx), str(fx)], [str(fx) + "/nope"]]


class RouteAuthMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.td.cleanup)
        cls.fx = Path(cls.td.name) / "fx"
        write(cls.fx, FX)
        os.symlink("missing-target.js", cls.fx / "broken.js")  # a file that cannot be read must be skipped, not crash the scan
        cls.res = run(SCRIPT, cls.fx)
        cls.gold = golden()

    def test_rows_match_golden(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)
        rows, _ = split(self.res)
        self.assertEqual(sorted(rows), sorted(self.gold))
        keys = [(r.split(":")[0], int(r.split(":")[1])) for r in rows]
        self.assertEqual(keys, sorted(keys), "rows are ordered by (path, line)")

    def test_json_summary_and_stderr(self):
        _, j = split(self.res)
        high = [g for g in self.gold if ": HIGH: " in g]
        self.assertEqual((j["tool"], j["handlers"], j["high"]), ("route_auth_map", len(self.gold), len(high)))
        got = {(f["file"], f["line"], f["severity"], f["message"]) for f in j["findings"]}
        exp = set()
        for g in high:
            head, _, msg = g.partition(": HIGH: ")
            path, _, ln = head.rpartition(":")
            exp.add((path, int(ln), "HIGH", msg))
        self.assertEqual(got, exp)
        self.assertEqual(j["files"], len({g.split(":")[0] for g in self.gold}) + len(QUIET))  # every file with a row, plus the files that look like routes but yield none
        self.assertEqual(self.res.stderr, "heuristic; scanned %d files with %d handlers; silence is not proof of authentication\n" % (j["files"], j["handlers"]))

    def test_paths_lists_get_routes(self):
        res = run(SCRIPT, self.fx, "--paths")
        want = set()
        for g in self.gold:
            m = re.search(r": (?:INFO|HIGH): (\S+) (\S+) auth=", g)
            if {"GET", "ANY"} & set(m.group(1).split("|")):
                want.add(m.group(2))
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.splitlines(), sorted(want))
        self.assertIn("/health", want)
        self.assertNotIn("saveNote", want)
        self.assertNotIn("/orders", want)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            res = run(SCRIPT, t)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(json.loads(res.stdout)["handlers"], 0)
            for argv in ([], [t, t], ["--paths"], ["--bogus", t], [os.path.join(t, "nope")]):
                r = subprocess.run([sys.executable, "-I", str(SCRIPT), *argv], capture_output=True, text=True)
                self.assertEqual(r.returncode, 2, argv)
                self.assertIn("usage: route_auth_map.py [--paths] DIR", r.stderr)

    def test_writes_nothing_beside_the_script(self):
        with tempfile.TemporaryDirectory() as t:
            for f in (SCRIPT, SK / "tenant_scope_check.py"):
                shutil.copy(f, t)
            self.assertEqual(run(Path(t) / "route_auth_map.py", self.fx).returncode, 0)
            self.assertEqual(sorted(os.listdir(t)), ["route_auth_map.py", "tenant_scope_check.py"])

    def test_review_checks_full_wiring(self):
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, files):
                g = Path(t) / name
                write(g, files)
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g", FX))], capture_output=True, text=True, env=env)
            rows = [x for x in json.loads(r.stdout) if x["tool"] == "route-auth"]
            want = {g.split(": HIGH: ")[0] + "|" + g.split(": HIGH: ")[1] for g in self.gold if ": HIGH: " in g}
            got = {"%s:%d|%s" % (x["file"], x["line"], x["message"]) for x in rows}
            self.assertEqual(got, want)
            self.assertEqual({x["rule"] for x in rows}, {"missing-auth"})
            self.assertIn("route-auth: heuristic; scanned %d handlers; silence is not proof of authentication" % len(self.gold), r.stderr)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g2", {"a.ts": "export const a = 1;\n"}))], capture_output=True, text=True, env=env)
            self.assertIn("route-auth (SKIPPED: no HTTP handlers)", r.stderr)
            self.assertEqual([(x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "route-auth"], [("not-checked", "SKIPPED: no HTTP handlers")])

    def test_every_rule_is_mutation_checked(self):
        src = SCRIPT.read_text(encoding="utf-8")
        ms, bad = mutants(src)
        self.assertEqual(bad, [], "MUTANTS rows whose old text is missing, repeated or equal to the new text")
        base = [(r.returncode, r.stdout, r.stderr) for r in (subprocess.run([sys.executable, "-I", str(SCRIPT), *a], capture_output=True, encoding="utf-8", errors="replace") for a in probes(self.fx))]
        self.assertEqual(base[0][0], 0)
        self.assertEqual(verdict(src, self.fx, base), "alive")  # control: the unmutated script is not killed
        with concurrent.futures.ThreadPoolExecutor(min(8, os.cpu_count() or 2)) as ex:
            res = list(ex.map(lambda m: verdict(m[1], self.fx, base), ms))
        left = [(v, m[0]) for m, v in zip(ms, res) if v != "killed"]
        self.assertEqual(left, [], "mutations the tests do not notice (alive) or that do not run (broken)")


if __name__ == "__main__":
    unittest.main()
