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
    ("apps/g-code401", "api/x", "/api/x", "middleware"), ("apps/g-code403", "api/x", "/api/x", "middleware"),  # `.code(401)` (spaced) and `.code(403)`
    ("apps/g-stat401", "api/x", "/api/x", "middleware"), ("apps/g-stat403", "api/x", "/api/x", "middleware"),  # `statusCode=401` and `statusCode = 403` assignments
    ("apps/g-unauth", "api/x", "/api/x", "middleware"), ("apps/g-forbid", "api/x", "/api/x", "middleware"),  # `.unauthorized(` and `.forbidden(` helpers
    ("apps/g-decoys", "api/x", "/api/x", "none"),  # a comparison, other statuses, look-alike names and a definition are no refusal
    ("apps/g-ident", "acme-api/x", "/acme-api/x", "none"),  # a path in an `if` that only calls an identity check (it cannot refuse) stays an allow-list entry
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

# Refusal spellings of a Fastify-style reply: `.code(401|403)`, `statusCode = 401|403`, `.unauthorized(`, `.forbidden(`.
FX["apps/g-code401/proxy.ts"] = gate("  if (!isMemberSession(req)) return reply.code( 401 ).send();\n")
FX["apps/g-code403/proxy.ts"] = gate("  if (!isMemberSession(req)) return reply.code(403).send();\n")
FX["apps/g-stat401/proxy.ts"] = gate("  if (!isMemberSession(req)) { reply.statusCode=401; return reply.send(); }\n")
FX["apps/g-stat403/proxy.ts"] = gate("  if (!isMemberSession(req)) { reply.statusCode = 403; return reply.send(); }\n")
FX["apps/g-unauth/proxy.ts"] = gate("  if (!isMemberSession(req)) return reply.unauthorized('denied');\n")
FX["apps/g-forbid/proxy.ts"] = gate("  if (!isMemberSession(req)) return reply.forbidden();\n")
FX["apps/g-decoys/proxy.ts"] = gate(
    "  const a = res.statusCode === 401;\n  const b = xstatusCode = 401;\n  const c = barcode(401) + reply.code(402) + reply.code(404);\n  reply.statusCode = 402;\n"
    "  const d = stats.unauthorizedCount(1) + stats.forbiddenTotal;\n  function unauthorized() { return 1; }\n")
FX["apps/g-ident/proxy.ts"] = gate(
    "  if (req.nextUrl.pathname.startsWith('/acme-api/')) { requireAuth(req); }\n"
    "  if (!isMemberSession(req)) return new NextResponse('Unauthorized', { status: 401 });\n")

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

# Typed registrations: `app.post<{ ... }>("/path", h)` is a route; the type-argument list is read by a bounded balanced `<...>` scan, so a comparison is not one.
FX["api/typed.ts"] = (
    'import Fastify from "fastify";\nconst app = Fastify();\n\n'
    'app.post<{ Params: { id: string }; Body: Widget }>("/acme-api/widgets/:id", async (req, reply) => reply.send({ ok: true }));\n'
    'app.post("/acme-api/widgets", async (req, reply) => reply.send({ ok: true }));\n'
    'app.put<{ Body: Widget }>("/acme-api/typed-auth", { preHandler: [app.authenticate] }, async (req) => req.body);\n'
    'app.get<Map<string, Array<Widget>>>("/acme-api/nested", async () => []);\n'
    'app.delete<() => void>("/acme-api/arrow", async () => ({}));\n'
    'app.all<[string, number]>("/acme-api/tuple", async () => ({}));\n'
    'app.patch<{ Body: Widget }> ("/acme-api/spaced", async () => ({}));\n')
FX["api/typed-use.ts"] = 'const app = express();\napp.use<Opts>(requireAuth);\napp.post("/acme-api/after-use", (req, res) => res.send("x"));\n'
FX["api/typed-hook.ts"] = 'const app = Fastify();\napp.addHook<Req>("onRequest", requireAuth);\napp.post("/acme-api/after-hook", async () => ({}));\n'
FX["api/typed-only.ts"] = 'app.post<{ Body: Widget }>("/acme-api/only", async () => ({}));\n'  # the only thing in the file that says it holds a route
FX["api/longtype.ts"] = (  # the closing `>` is the last character read at 1999 columns from the `<`: 2000 is too far
    'app.use<requireAuth, ' + "A" * 1986 + '>(x);\n'  # too far: no use, and nothing is read from the file's start for it (the routes below keep no auth)
    'app.post<' + "A" * 1998 + '>("/acme-api/long-ok", h);\n'
    'app.post<' + "A" * 1999 + '>("/acme-api/long-far", h);\n')
FX["lib/cmp.ts"] = (  # not routes: a comparison, and `<...>` lists that break a rule or lead to no call
    "const a = x.get < y && f(z);\n"
    'app.post<a && b>("/acme-api/d1", h);\n'
    'app.post<a || b>("/acme-api/d2", h);\n'
    'app.post<a; b>("/acme-api/d3", h);\n'
    'f(app.post<a), (b>("/acme-api/d4", h));\n'
    'app.post<T> + wrap("/acme-api/d5", h);\n'
    "app.get<y && f(z);\n"
    "app.get<Foo")  # ends inside the list, no final newline
GOLD += [
    ("api/typed.ts", '"/acme-api/widgets/:id"', "HIGH: POST /acme-api/widgets/:id auth=none"),
    ("api/typed.ts", '"/acme-api/widgets"', "HIGH: POST /acme-api/widgets auth=none"),
    ("api/typed.ts", '"/acme-api/typed-auth"', "INFO: PUT /acme-api/typed-auth auth=authenticate"),
    ("api/typed.ts", '"/acme-api/nested"', "INFO: GET /acme-api/nested auth=none"),
    ("api/typed.ts", '"/acme-api/arrow"', "HIGH: DELETE /acme-api/arrow auth=none"),
    ("api/typed.ts", '"/acme-api/tuple"', "HIGH: ANY /acme-api/tuple auth=none"),
    ("api/typed.ts", '"/acme-api/spaced"', "HIGH: PATCH /acme-api/spaced auth=none"),
    ("api/typed-use.ts", '"/acme-api/after-use"', "INFO: POST /acme-api/after-use auth=requireAuth"),
    ("api/typed-hook.ts", '"/acme-api/after-hook"', "INFO: POST /acme-api/after-hook auth=requireAuth"),
    ("api/typed-only.ts", '"/acme-api/only"', "HIGH: POST /acme-api/only auth=none"),
    ("api/longtype.ts", '"/acme-api/long-ok"', "HIGH: POST /acme-api/long-ok auth=none"),
]


# Fastify root hooks: `app.addHook("onRequest", ...)` on a `Fastify()` receiver whose handler can refuse (or names an identity check) covers, as `auth=root-hook`, what the hook file
# wires onto that receiver after the hook: the files it imports AND passes to `register(` or calls with the instance first, and its own non-GET routes, less the paths the hook
# text exempts or scopes. Scenarios live under rh/<name>/.
def rts(path, routes, fn="routes"):
    """One POST route per (route, expected auth) in the file path, and the GOLD rows for them."""
    FX[path] = "export default async function %s(app) {\n" % fn + "".join('  app.post("%s", async () => ({ ok: true }));\n' % r for r, _ in routes) + "}\n"
    GOLD.extend((path, '"%s"' % r, "%s: POST %s auth=%s" % ("HIGH" if a == "none" else "INFO", r, a)) for r, a in routes)


RH = 'import Fastify from "fastify";\nimport routes from "./routes";\n\nconst app = Fastify();\n\n'


def rh(name, hook, *routes, head=RH, tail="\napp.register(routes);\n"):
    """rh/<name>/app.ts is head + hook + tail; its rh/<name>/routes.ts (when routes are given) is registered by it."""
    FX["rh/%s/app.ts" % name] = head + hook + tail
    if routes: rts("rh/%s/routes.ts" % name, routes)


HK = 'app.addHook("onRequest", async (req, reply) => reply.code(401).send());\n'
rh("scope", 'const quiet = !process.env.DEBUG;\n\napp.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/admin") && !req.user) return reply.code(403).send();\n});\n',
   ("/acme-api/admin/users", "root-hook"), ("/acme-api/admin", "root-hook"), ("/acme-api/administrator", "none"), ("/acme-api/widgets", "none"))  # a refusing `if` names a path: that is the hook's scope
rh("identity", 'app.addHook("preValidation", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/priv")) {\n    await app.authenticate(req, reply);\n  }\n});\n',
   ("/acme-api/priv/data", "root-hook"), ("/acme-api/priv", "root-hook"), ("/acme-api/private", "none"), ("/acme-api/pub", "none"))  # an identity check under a path test scopes it too
rh("neg", 'app.addHook("onRequest", async (req, reply) => {\n  if (!req.url.startsWith("/acme-api/open")) {\n    return reply.code(401).send();\n  }\n});\n',
   ("/acme-api/open/ping", "none"), ("/acme-api/x", "none"))  # a negated path test: which side is open is unknown, so the hook covers nothing
rh("named", 'export async function guard(req, reply) {\n  limit(2);\n  if ([...open, ...docs, ...misc].includes(req.url)) return;\n  if (!req.headers.authorization) return reply.unauthorized("denied");\n}\n\nfunction limit(n) {\n  return n ? limit(n - 1) : n;\n}\n\n'
            'function build() {\n  const open = ["/acme-api/status"];\n  let docs = ["/acme-api/docs/*"];\n  var misc = ["/acme-api/misc"];\n  return ["/acme-api/other"];\n}\n\napp.addHook("preHandler", guard);\n',
   ("/acme-api/status", "none"), ("/acme-api/docs/page", "none"), ("/acme-api/docs", "none"), ("/acme-api/misc", "none"), ("/acme-api/other", "root-hook"), ("/acme-api/widgets", "root-hook"))  # a named handler, the allow-lists it reads two hops away (any indent, const/let/var, not the line after them) and a recursive helper
rh("hops", 'async function guard(req, reply) {\n  await check(req, reply);\n}\n\nasync function check(req, reply) {\n  if (!req.headers.authorization) return reply.code(401).send();\n}\n\napp.addHook("onRequest", guard);\n',
   ("/acme-api/hops", "root-hook"))  # the refusal is in a function the named handler calls: declarations are followed transitively
rh("dollar", 'async function $guard(req, reply) {\n  if ($open.includes(req.url)) return;\n  return reply.code(403).send();\n}\n\nconst $open = ["/acme-api/status"];\n\napp.addHook("onRequest", $guard);\n',
   ("/acme-api/status", "none"), ("/acme-api/widgets", "root-hook"))  # a handler and an allow-list named with `$`
rh("ref", 'app.addHook("preParsing", app.authenticate);\n', ("/acme-api/any", "root-hook"),
   head='import fastify from "fastify";\nimport routes from "./routes";\n\nconst app = fastify();\n\n')  # a bare identity reference is a hook; `fastify()` binds a receiver too
rh("plugin", "", ("/acme-api/plug", "none"), head='import routes from "./routes";\n\nexport default async function plugin(fastify) {\n  ' + HK.replace("app.", "fastify."),
   tail="  fastify.register(routes);\n}\n")  # the receiver is a parameter, no `Fastify()` call binds it: that hook stays file-local
rh("late", HK, ("/acme-api/late", "none"), tail="", head='import Fastify from "fastify";\nimport routes from "./routes";\n\nconst app = Fastify();\n\napp.register(routes);\n\n')  # a hook added after the register call does not reach it
rh("send", 'app.addHook("onSend", async (req, reply) => reply.code(401).send());\n', ("/acme-api/sent", "none"))  # only request hooks gate
rh("eof", 'app.addHook("onRequest", gate);\n', ("/acme-api/eof", "root-hook"),
   tail="\napp.register(routes);\n\nfunction gate(req, reply) { return reply.code(401).send(); }\n")  # the handler is the last line of the file
rh("resp", 'app.addHook("onRequest", async () => new Response("Unauthorized"));\n', ("/acme-api/resp", "root-hook"))  # a refusal that is spelled in a string
rh("refplain", 'app.addHook("onRequest", logRequest);\n', ("/acme-api/plain", "none"))  # a bare reference to a name that is no identity check
rh("short", 'app.addHook("onRequest");\n', ("/acme-api/short", "none"))  # a hook call with no handler
rh("after", 'app.addHook("onRequest", async (req, reply) => {\n  if (!req.headers.authorization) return reply.code(401).send();\n  if (req.url === "/acme-api/ping") return;\n});\n',
   ("/acme-api/ping", "none"), ("/acme-api/other", "root-hook"))  # a positive path test with a bare return after the refusing `if` is still an allow-list entry (kept as it was), and the `!` before the refusal is no negated scope test
rh("two", 'app.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/admin")) return reply.code(403).send();\n});\n\n'
          'app.addHook("preHandler", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/billing")) return reply.code(403).send();\n});\n',
   ("/acme-api/admin/x", "root-hook"), ("/acme-api/billing/y", "root-hook"), ("/acme-api/pub", "none"))  # each of two hooks covers its own scope
# A path test is read by its operator, as JS runs it: `startsWith` exempts every route whose raw path starts with the literal, `===` and `==` only the path itself.
EQ = 'app.addHook("onRequest", async (req, reply) => {\n  %s\n  if (!req.headers.authorization) return reply.code(401).send();\n});\n'
rh("eqfree", EQ % 'if (req.url === "/acme-api/ping") return;\n  if (req.url == "/acme-api/pong") return;\n  if ("/acme-api/pang" === req.url) return;\n  if ("/acme-api/peng" == req.url) return;',
   ("/acme-api/ping", "none"), ("/acme-api/ping/deep", "root-hook"), ("/acme-api/pingz", "root-hook"), ("/acme-api/pong", "none"), ("/acme-api/pong/deep", "root-hook"),
   ("/acme-api/pang", "none"), ("/acme-api/pang/deep", "root-hook"), ("/acme-api/peng", "none"), ("/acme-api/peng/deep", "root-hook"),
   ("/acme-api/other", "root-hook"))  # `===` and `==`, on either side, let through the path itself: not what is under it, not a longer name
rh("eqroot", EQ % 'if (req.url === "/") return;', ("/", "none"), ("/acme-api/any", "root-hook"))  # an exact "/" is the root only
rh("incfree", EQ % 'if (["/", "/acme-api/status"].includes(req.url)) return;', ("/", "none"), ("/acme-api/status", "none"), ("/acme-api/status/x", "none"), ("/acme-api/statusz", "none"),
   ("/acme-api/any", "root-hook"))  # any other test exempts by raw prefix, but its "/" is still the root only
rh("swroot", EQ % 'if (req.url.startsWith("/")) return;', ("/", "none"), ("/acme-api/any", "none"))  # every path starts with "/": the hook covers nothing
rh("swscope", 'app.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/") && !req.user) return reply.code(401).send();\n});\n',
   ("/", "root-hook"), ("/acme-api/any", "none"))  # a `startsWith("/")` scope reads as the root alone (a noisy HIGH, never a quiet one)
rh("eqscope", 'app.addHook("onRequest", async (req, reply) => {\n  if (req.url === "/acme-api/admin") return reply.code(403).send();\n});\n',
   ("/acme-api/admin", "root-hook"), ("/acme-api/admin/users", "none"), ("/acme-api/other", "none"))  # `===` in a refusing `if` scopes the path itself, not what is under it
rh("eqtwo", 'app.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/admin")) return reply.code(403).send();\n});\n\n'
            'app.addHook("preHandler", async (req, reply) => {\n  if (req.url === "/acme-api/billing") return reply.code(403).send();\n});\n',
   ("/acme-api/admin", "root-hook"), ("/acme-api/admin/x", "root-hook"), ("/acme-api/administrator", "none"), ("/acme-api/billing", "root-hook"), ("/acme-api/billing/y", "none"))  # a `startsWith` scope still covers what is under its path, next to an `===` one that does not
rh("incscope", 'app.addHook("onRequest", async (req, reply) => {\n  if (["/acme-api/admin"].includes(req.url)) return reply.code(403).send();\n});\n',
   ("/acme-api/admin", "root-hook"), ("/acme-api/admin/users", "none"))  # any other test scopes the path itself too
rh("neqscope", EQ % 'if (req.url !== "/acme-api/admin") return;', ("/acme-api/admin", "root-hook"), ("/acme-api/admin/users", "none"), ("/acme-api/other", "none"))  # `!==` returns every other path unanswered: only the path itself is refused
# `==` and `===` name the path itself only against a plain name or member chain: a call or an index (`slice(0, n)`, `substring(0, n)`, `path.dirname(x)`, `split("?")[0]`) can make it a prefix
# or derived-value test, so an exemption on either side of the operator reads as a prefix test and the deeper route is not covered (a noisy HIGH, never a quiet one).
rh("eqslice", EQ % 'if (req.url.slice(0, 15) === "/acme-api/admin") return;', ("/acme-api/admin", "none"), ("/acme-api/admin/users", "none"), ("/acme-api/other", "root-hook"))
rh("eqsubstr", EQ % 'if (req.url.substring(0, 15) == "/acme-api/admin") return;', ("/acme-api/admin", "none"), ("/acme-api/admin/users", "none"), ("/acme-api/other", "root-hook"))
rh("eqdirname", EQ % 'if (path.dirname(req.url) === "/acme-api") return;', ("/acme-api/foo", "none"), ("/other/x", "root-hook"))
rh("eqindex", EQ % 'if (req.url.split("?")[0] === "/acme-api/ping") return;', ("/acme-api/ping", "none"), ("/acme-api/ping/deep", "none"), ("/acme-api/other", "root-hook"))
rh("eqcallrev", EQ % 'if ("/acme-api/admin" === req.url.slice(0, 15)) return;\n  if ("/acme-api/pong" == req.url?.substring(0, 14)) return;\n  if ("/acme-api/ping" === parts[0]) return;',
   ("/acme-api/admin/users", "none"), ("/acme-api/pong/deep", "none"), ("/acme-api/ping/deep", "none"), ("/acme-api/other", "root-hook"))  # the same on the other side of the operator
FX["rh/bare/app.ts"] = ('import a from "a";\nconst b = require("b");\nconst app = Fastify();\n\n' + HK
                        + '\napp.register(a);\napp.register(b);\napp.register(require("c"));\napp.register(import("d"));\n')  # packages, not the files next to it
for n in "abcd": rts("rh/bare/%s.ts" % n, [("/acme-api/" + n, "none")], n)
rh("scopevar", 'app.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/admin")) return reply.code(403).send();\n});\n',
   ("/acme-api/admin/x", "none"), tail="\nconst opts = loadOptions();\napp.register(routes, opts);\n")  # a scoped hook cannot be judged against a mount that is unknown
rh("other", HK, ("/acme-api/elsewhere", "none"), tail="\nconst other = Fastify();\nother.register(routes);\n")  # the hook is on `app`, the register call on `other`
rh("log", 'app.addHook("onRequest", async (req) => {\n  req.log.info("verify(token) skipped");\n  const auth = req.headers["x-auth"];\n  req.log.info({ auth });\n});\n\napp.register(a);\n\n' + HK, tail="\napp.register(b);\n",
   head='import Fastify from "fastify";\nimport a from "./a";\nimport b from "./b";\n\nconst app = Fastify();\n\n')  # logging is no gate (an identity name in a string, a bare variable): `a` stays open, `b` sits behind the refusing hook
rts("rh/log/a.ts", [("/acme-api/audited", "none")], "a")
rts("rh/log/b.ts", [("/acme-api/gated", "root-hook")], "b")
FX["rh/main/app.ts"] = (
    'import Fastify, { FastifyInstance } from "fastify";\nimport widgets from "./routes/widgets";\nimport unused from "./routes/unused";\nimport "./routes/side";\n\n'
    "const app: FastifyInstance = Fastify();\n\napp.get(\"/acme-api/early\", async () => ({ ok: true }));\n\napp.addHook(\n  \"onRequest\",\n  async (req, reply) => {\n"
    '    if (req.url.startsWith("/acme-api/health")) return;\n    if (req.url === "/") return;\n'
    '    if (!req.headers.authorization) return reply.code(401).send({ error: "unauthorized" });\n  },\n);\n\n'
    'app.get("/acme-api/ping", async () => ({ ok: true }));\napp.register(widgets);\napp.register(corsPlugin);\n')
FX["rh/main/routes/widgets.ts"] = (
    "export default async function widgets(app) {\n"
    '  app.post<{ Params: { id: string }; Body: Widget }>("/acme-api/widgets/:id", async (req, reply) => reply.send({ ok: true }));\n'
    '  app.delete("/acme-api/widgets/:id", async () => ({ ok: true }));\n'
    '  app.post("/acme-api/health", async () => ({ ok: true }));\n  app.post("/acme-api/health/check", async () => ({ ok: true }));\n'
    '  app.post("/acme-api/healthz", async () => ({ ok: true }));\n  app.post("/acme-api/ping", async () => ({ ok: true }));\n'
    '  app.post("/", async () => ({ ok: true }));\n  app.post("/acme-api/early", async () => ({ ok: true }));\n'
    '  app.post("/acme-api/own", { preHandler: [app.authenticate] }, async () => ({ ok: true }));\n}\n')
for n in ("orphan", "unused", "side"):  # never imported / imported, never registered / imported for its side effects only
    rts("rh/main/routes/%s.ts" % n, [("/acme-api/" + n, "none")], n)
GOLD += [
    ("rh/main/app.ts", '"/acme-api/ping"', "INFO: GET /acme-api/ping auth=none"),  # a GET of the hook's own file keeps its own evidence (INFO either way)
    ("rh/main/app.ts", '"/acme-api/early"', "INFO: GET /acme-api/early auth=none"),
    ("rh/main/routes/widgets.ts", 'app.post("/acme-api/early"', "INFO: POST /acme-api/early auth=root-hook"),  # a route registration before the hook is no exemption either
    ("rh/main/routes/widgets.ts", '>("/acme-api/widgets/:id"', "INFO: POST /acme-api/widgets/:id auth=root-hook"),
    ("rh/main/routes/widgets.ts", 'app.delete("/acme-api/widgets/:id"', "INFO: DELETE /acme-api/widgets/:id auth=root-hook"),
    ("rh/main/routes/widgets.ts", '"/acme-api/health"', "HIGH: POST /acme-api/health auth=none"),  # exempt by the hook's text
    ("rh/main/routes/widgets.ts", '"/acme-api/health/check"', "HIGH: POST /acme-api/health/check auth=none"),  # and what is under it
    ("rh/main/routes/widgets.ts", '"/acme-api/healthz"', "HIGH: POST /acme-api/healthz auth=none"),  # `startsWith` is a raw string prefix: the hook lets a longer name through too
    ("rh/main/routes/widgets.ts", '"/acme-api/ping"', "INFO: POST /acme-api/ping auth=root-hook"),  # a route registration is no exemption
    ("rh/main/routes/widgets.ts", 'app.post("/"', "HIGH: POST / auth=none"),  # the exempt "/" is the root only
    ("rh/main/routes/widgets.ts", '"/acme-api/own"', "INFO: POST /acme-api/own auth=authenticate"),  # a route's own evidence comes first
]
for n in ("a", "b"):  # one routes file registered at a hooked and at an unhooked site: every site must be gated, in whichever order they come
    FX["rh/sites/%s-app.ts" % n] = ('import Fastify from "fastify";\nimport r1 from "./r1";\nimport r2 from "./r2";\n\nconst app = Fastify();\n\n'
                                    + ("app.register(r2);\n" + HK + "app.register(r1);\n" if n == "a" else "app.register(r1);\n" + HK + "app.register(r2);\n"))
    rts("rh/sites/r%s.ts" % ("1" if n == "a" else "2"), [("/acme-api/r" + ("1" if n == "a" else "2"), "none")], "r" + ("1" if n == "a" else "2"))
PFX = (("lit", '{ prefix: "/acme-api/" }', ("/widgets", "root-hook"), ("/health", "none")),
       ("pre", '{ prefix: "/acme-api", logLevel: "info" }', ("/widgets", "root-hook"), ("/health", "none")),  # the literal prefix is joined to the route, then judged against the hook's paths
       ("bare", '{ logLevel: "info" }', ("/acme-api/widgets", "root-hook"), ("/acme-api/health", "none")),  # options without a prefix mount at the root
       ("var", "opts", ("/widgets", "none")), ("spread", '{ ...base, prefix: "/acme-api" }', ("/widgets", "none")), ("short", "{ prefix }", ("/widgets", "none")),
       ("cat", '{ prefix: "/acme-api" + base }', ("/widgets", "none")), ("cat2", '{ prefix: BASE + "/acme-api" }', ("/widgets", "none")))  # an unknown mount cannot be judged against paths
rh("prefix", 'const opts = { prefix: "/acme-api" };\nconst base = "";\nconst prefix = "/acme-api";\n\napp.addHook("onRequest", async (req, reply) => {\n  if (req.url.startsWith("/acme-api/health")) return;\n'
             '  if (!req.headers.authorization) return reply.code(401).send();\n});\n',
   head='import Fastify from "fastify";\n' + "".join('import %s from "./routes/%s";\n' % (n, n) for n, *_ in PFX) + "\nconst app = Fastify();\n\n",
   tail="\n" + "".join("app.register(%s, %s);\n" % (n, o) for n, o, *_ in PFX))
for n, _, *rs in PFX: rts("rh/prefix/routes/%s.ts" % n, rs, n)
IMPS = (("esm.ts", 'import esm from "./routes/esm";', "esm"), ("ren.ts", "import { a as renamed } from './routes/ren';", "renamed"), ("ns.ts", 'import * as ns from "./routes/ns";', "ns.default"),
        ("dir/index.ts", 'import dir from "./routes/dir";', "dir, opts"), ("js.ts", 'import js from "./routes/js.js";', "js"), ("jsx.tsx", 'import jsx from "./routes/jsx.jsx";', "jsx"),
        ("exact.ts", 'import exact from "./routes/exact.ts";', "exact"), ("cjs.ts", 'const cjs = require("./routes/cjs");', "cjs"), ("dst.ts", "const { named } = require('./routes/dst');", "named"),
        ("inl.ts", "", 'require("./routes/inl")'), ("inl2.ts", "", "require('./routes/inl2')"), ("dyn.ts", "", 'import("./routes/dyn")'),
        ("awt.ts", 'const awt = await import("./routes/awt");', "awt.default"), ("dol.ts", 'import $dol from "./routes/dol";', "$dol"))  # (routes file, how app.ts imports it, the register argument)
FX["rh/imports/app.ts"] = ("".join(i + "\n" for _, i, _ in IMPS if i) + 'const app = require("fastify")({ logger: true });\n\napp.addHook("onRequest", app.authenticate);\n\n'
                           + "".join("app.register(%s);\n" % a for *_, a in IMPS))  # a global hook covers every file it registers, whatever the mount
for f, *_ in IMPS: rts("rh/imports/routes/" + f, [("/acme-api/" + f.rsplit(".", 1)[0].replace("/", "-"), "root-hook")], "r")


# Fixture A: a Fastify instance built in a factory function, its routes declared below the hook and its route modules called with the instance (no `register`). Fixture B: a top-level
# hook with an optional-chaining scope test, an allow-list held in a declaration and an identity check under a bare return. `variant` writes one under rh/<dir>/ with `edits` ((old, new),
# each old text once) applied to its first file, and `flip` ({row: auth}) naming the rows that edit changes: the variants below are the fixture mutants M1-M5.
FA = '''import Fastify, { type FastifyInstance } from "fastify";
import { widgetRoutes } from "./widgets.ts";
import { gadgetRoutes } from "./gadgets.ts";
import { earlyRoutes } from "./early.ts";
import { orphanRoutes } from "./orphan.ts";
import { verifySession } from "./session.ts";

const ROLE_RULES: Record<string, string[]> = { "/acme-api/admin/purge": ["owner"], "/acme-api/widgets": ["member", "owner"] };
function rolesFor(url: string): string[] { return ROLE_RULES[url] ?? ["owner"]; }

export function buildServer(opts: { region: string }): FastifyInstance {
  const app = Fastify({ logger: false });
  app.addHook("onSend", async (_req, reply) => { reply.header("x-content-type-options", "nosniff"); });
  app.post("/acme-api/before", async () => ({ ok: true }));
  earlyRoutes(app);
  app.addHook("onRequest", async (req, reply) => {
    if (!req.url.startsWith("/acme-api/")) return;
    if (req.url === "/acme-api/ping") return;
    const session = await verifySession(req.headers.authorization);
    if (!session) return reply.code(401).send({ error: "Sign in first" });
    if (!rolesFor(req.url).includes(session.role)) return reply.code(403).send({ error: "Role not allowed" });
    if (session.kind === "service" && req.url.startsWith("/acme-api/admin")) return reply.code(403).send({ error: "Service tokens cannot do this" });
    req.user = session;
  });
  app.post<{ Body: { name: string } }>("/acme-api/widgets", async () => ({ ok: true }));
  app.post("/acme-api/ping", async () => ({ pong: true }));
  app.post("/inbound/hook", async () => ({ ok: true }));
  widgetRoutes(app);
  gadgetRoutes(app, opts.region);
  return app;
}
'''
FB = '''import Fastify from "fastify";
import { verifyToken } from "./tokens.ts";
const PUBLIC_PATHS = ["/api/status"];
const app = Fastify();
app.addHook("preHandler", async (req, reply) => {
  if (!req.routeOptions.url?.startsWith("/api/")) return;
  if (PUBLIC_PATHS.includes(req.routeOptions.url)) return;
  if (await verifyToken(req.headers.authorization)) return;
  return reply.code(401).send({ error: "Missing or wrong token" });
});
app.post("/api/orders", async () => ({ ok: true }));
app.post("/api/status", async () => ({ ok: true }));
export default app;
'''


def fam(fn, args, *routes):
    """A route module of Fixture A: `export function fn(args)` holding one `app.<verb>(path, handler)` per (verb, path)."""
    return 'import type { FastifyInstance } from "fastify";\n\nexport function %s(%s) {\n' % (fn, args) + "".join('  app.%s("%s", async () => ({ ok: true }));\n' % r for r in routes) + "}\n"


FA_ALL = {"server.ts": FA,
          "widgets.ts": fam("widgetRoutes", "app: FastifyInstance", ("post", "/acme-api/widgets/:id/archive"), ("delete", "/inbound/widgets/:id")),
          "gadgets.ts": fam("gadgetRoutes", "app: FastifyInstance, region: string", ("put<{ Params: { id: string } }>", "/acme-api/gadgets/:id")),
          "early.ts": fam("earlyRoutes", "app: FastifyInstance", ("post", "/acme-api/early")),
          "orphan.ts": fam("orphanRoutes", "app: FastifyInstance", ("post", "/acme-api/orphan")),
          "session.ts": 'export async function verifySession(authorization: string | undefined) {\n  return authorization ? { role: "owner", kind: "user" } : null;\n}\n'}  # no route: the pre-filter skips it
FA_ROWS = (  # (file, marker, row, auth)
    ("server.ts", '"/acme-api/before"', "POST /acme-api/before", "none"),  # above the hook
    ("server.ts", '}>("/acme-api/widgets"', "POST /acme-api/widgets", "root-hook"),  # typed, below it: the role table's "/acme-api/widgets" is no allow-list entry
    ("server.ts", 'app.post("/acme-api/ping"', "POST /acme-api/ping", "none"),  # allow-listed by the hook's `return` test
    ("server.ts", '"/inbound/hook"', "POST /inbound/hook", "none"),  # outside the hook's scope
    ("widgets.ts", '"/acme-api/widgets/:id/archive"', "POST /acme-api/widgets/:id/archive", "root-hook"),  # called with the instance below the hook
    ("widgets.ts", '"/inbound/widgets/:id"', "DELETE /inbound/widgets/:id", "none"),  # the same module, outside the scope
    ("gadgets.ts", '"/acme-api/gadgets/:id"', "PUT /acme-api/gadgets/:id", "root-hook"),  # a second argument after the instance
    ("early.ts", '"/acme-api/early"', "POST /acme-api/early", "none"),  # called above the hook
    ("orphan.ts", '"/acme-api/orphan"', "POST /acme-api/orphan", "none"))  # imported, never called
FB_ROWS = (("api.ts", 'app.post("/api/orders"', "POST /api/orders", "root-hook"), ("api.ts", 'app.post("/api/status"', "POST /api/status", "none"))  # the second is allow-listed through PUBLIC_PATHS


def variant(d, files, rows, edits=(), flip=None):
    """Write `files` under rh/<d>/ (edits applied to the first, each old text once) and a GOLD row for each (file, marker, row, auth) of rows, `flip` ({row: auth}) overriding auth."""
    first = next(iter(files))
    text = files[first]
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    FX.update(("rh/%s/%s" % (d, f), text if f == first else t) for f, t in files.items())
    for f, marker, row, auth in rows:
        a = (flip or {}).get(row, auth)
        GOLD.append(("rh/%s/%s" % (d, f), marker, "%s: %s auth=%s" % ("HIGH" if a == "none" else "INFO", row, a)))


HOT = dict.fromkeys(("POST /acme-api/widgets", "POST /acme-api/widgets/:id/archive", "PUT /acme-api/gadgets/:id"), "none")  # Fixture A's root-hook rows, all open
variant("fa", FA_ALL, FA_ROWS)
variant("fa-m1", FA_ALL, FA_ROWS, [('    if (req.url === "/acme-api/ping") return;\n', '    if (req.url === "/acme-api/ping") return;\n    if (req.headers["x-acme-preview"] === "1") return;\n')], HOT)  # M1: a bypass voids the hook
variant("fa-m2", FA_ALL, FA_ROWS, [('if (!req.url.startsWith("/acme-api/")) return;', 'if (req.url.startsWith("/acme-api/")) return;')],
        {**HOT, "POST /inbound/hook": "root-hook", "DELETE /inbound/widgets/:id": "root-hook"})  # M2: without its `!` the scope test is an allow-list entry
variant("fa-m3", FA_ALL, FA_ROWS, [("  widgetRoutes(app);\n", ""), ("  earlyRoutes(app);\n", "  earlyRoutes(app);\n  widgetRoutes(app);\n")],
        {"POST /acme-api/widgets/:id/archive": "none"})  # M3: called above the hook
variant("fa-m5", FA_ALL, FA_ROWS, [("  widgetRoutes(app);\n", "  const other = Fastify();\n  widgetRoutes(other);\n")], {"POST /acme-api/widgets/:id/archive": "none"})  # M5: called with another instance
variant("fb", {"api.ts": FB}, FB_ROWS)
variant("fb-m4", {"api.ts": FB}, FB_ROWS, [("{ verifyToken }", "{ lookupCart }"), ("await verifyToken(", "await lookupCart(")], {"POST /api/orders": "none"})  # M4: the bare return is no identity check


# The corners of those rules, one scenario each: `ah` writes an onRequest hook around its body lines.
def ah(*body):
    return 'app.addHook("onRequest", async (req, reply) => {\n' + "".join("  %s\n" % l for l in body) + "});\n"


R401 = "if (!req.headers.authorization) return reply.code(401).send();"
OPEN = 'function %s(req) {\n  if (req.url === "/acme-api/open") return;\n}\n\n'
rh("retb", ah('if (req.url === "/acme-api/ping") { return }', 'if (req.url === "/acme-api/ready") return', 'if (!req.headers.authorization) return reply.code(401).send({ login: "/sign-in" });'),
   ("/acme-api/ping", "none"), ("/acme-api/ready", "none"), ("/acme-api/widgets", "root-hook"))  # a bare return is `return }` or a `return` ending its line; a path in a refusal's body is no scope
for w in ("done", "next"):  # `done()` and `next()` let the request through unanswered: a bare return that is no path test and no identity check
    rh(w, 'app.addHook("onRequest", (req, reply, %s) => {\n  if (req.method === "HEAD") return %s( );\n  %s\n  %s();\n});\n' % (w, w, R401, w), ("/acme-api/" + w, "none"))
rh("outside", HK, ("/acme-api/open", "root-hook"), ("/acme-api/other", "root-hook"), head=RH + OPEN % "earlier", tail="\napp.register(routes);\n\n" + OPEN % "later")  # an `if` outside the hook and the declarations it names says nothing
rh("lateret", ah(R401, 'if (req.method === "HEAD") return;'), ("/acme-api/late", "root-hook"))  # a bare return after the first refusal is not checked as a bypass
rh("lateneg", ah(R401, 'if (!req.url.startsWith("/acme-api/")) return;'), ("/inbound/x", "root-hook"), ("/acme-api/y", "root-hook"))  # nor read as a scope
for n, op in (("and", "&&"), ("or", "||")):  # a negated path test AND-ed or OR-ed with anything: which side is open is unknown, so the hook covers nothing
    rh("cneg-" + n, ah('if (!req.url.startsWith("/acme-api/") %s req.method === "GET") return;' % op, R401), ("/acme-api/x", "none"))
rh("keycmp", ah('if (req.headers["x-api-key"] === expected) return;', "return reply.code(401).send();"), ("/acme-api/key", "root-hook"))  # comparing a secret-looking value is an identity check, not a bypass
rh("bypass-sec", ah('if (req.headers["x-token"]) return;', "return reply.code(401).send();"), ("/acme-api/preview", "none"))  # a secret-looking name with no comparison is a bypass
rh("bypass-str", ah('if (req.headers["x-verify(1)"]) return;', "return reply.code(401).send();"), ("/acme-api/str", "none"))  # an identity call spelled in a string is no identity check
rh("strret", ah('if (req.url === "/acme-api/ping") reply.header("x-note", "return;");', R401), ("/acme-api/ping", "root-hook"))  # a `return;` spelled in a string is no bare return, so the path test exempts nothing
rh("lateresp", ah('if (!req.headers.authorization) return new Response("Forbidden");', 'if (!req.url.startsWith("/acme-api/")) return;'), ("/inbound/x", "root-hook"))  # a refusal spelled as a Response string cuts the rules there too
rh("respstr", ah('if (req.url.startsWith("/acme-api/admin")) return new Response("Forbidden");'), ("/acme-api/admin/x", "root-hook"), ("/acme-api/other", "none"))  # and its path test is a scope
rh("groups", ah('if (!req.url.startsWith("/acme-api/")) return;', 'if (!req.url.startsWith("/acme-api/admin")) return;', R401),
   ("/acme-api/admin/x", "root-hook"), ("/acme-api/admin", "root-hook"), ("/acme-api/widgets", "none"), ("/inbound/x", "none"))  # each negated test is a scope of its own: a route must be under all of them
rh("factory", HK, ("/acme-api/fac", "root-hook"), tail="\napp.register(routes(deps));\n")  # a plugin factory called inside register is the register site, not a second site
rh("onroute", 'app.addHook("onRoute", async (req, reply) => reply.code(401).send());\napp.addHook("onListen", async (req, reply) => reply.code(401).send());\n', ("/acme-api/life", "none"))  # lifecycle hooks gate no request
rh("callsp", "  " + HK, ("/acme-api/sp", "root-hook"), head='import Fastify from "fastify";\nimport routes from "./routes";\n\nexport function build(opts) {\n  const app = Fastify();\n',
   tail="  routes( app , opts.region );\n}\n")  # a spaced direct call with the instance first, below the hook in the same function
rh("names", HK, ("/acme-api/names", "root-hook"), tail="\nroutes(app);\nmyroutes(other);\n$routes(other);\nreg.routes(other);\n")  # only a call of the imported name itself is a site: not a longer name, a `$` name or a member
rh("regcall", HK, ("/acme-api/regcall", "none"), tail="\napp.register(routes);\nroutes(other);\n")  # registered under the hook, and also called with another instance
rh("callfirst", HK, ("/acme-api/cf", "none"), tail="\nroutes(other);\napp.register(routes);\n")  # the same call above the register: a call that is not inside it is a site of its own
rh("dollarcall", HK, ("/acme-api/dc", "root-hook"), head=RH.replace("import routes", "import $routes"), tail="\n$routes(app);\n")  # an imported name written with `$`
rh("encdc", "function setup(app) {\n  " + HK + "}\n", ("/acme-api/encdc", "none"), tail="\nroutes(app);\n")  # a direct call after the block that holds the hook is not covered
rh("nohook", HK, ("/acme-api/nohook", "none"))
FX["rh/nohook/b.ts"] = RH + "app.register(routes);\n"  # a second file registers the same routes with no hook above
FX["rh/enc/app.ts"] = RH + 'app.register(async function (app) {\n  ' + HK + '  app.post("/acme-api/inside", async () => ({ ok: true }));\n});\n\napp.post("/acme-api/outside", async () => ({ ok: true }));\n\napp.register(routes);\n'
rts("rh/enc/routes.ts", [("/acme-api/enc", "none")])
FX["rh/recv/app.ts"] = 'import Fastify from "fastify";\n\nconst app = Fastify();\nconst other = Fastify();\n\n' + HK + 'app.post("/acme-api/mine", async () => ({ ok: true }));\nother.post("/acme-api/theirs", async () => ({ ok: true }));\n'
FX["rh/reqfy/app.ts"] = ('const app = require("fastify")();\n\napp.addHook("onRequest", async (req, reply) => {\n  const session = await verifySession(req.headers.authorization);\n'
                        '  if (!session) return reply.code(401).send();\n});\napp.post("/acme-api/req", async () => ({ ok: true }));\n')
FX["api/legacy-hook.ts"] = 'export default async function plugin(fastify) {\n  fastify.addHook("onRequest", async (req, reply) => { await authenticate(req, reply); });\n  fastify.post("/acme-api/plugged", async () => ({ ok: true }));\n}\n'
FX["api/named-ref.ts"] = 'import Fastify from "fastify";\n\nconst app = Fastify();\napp.addHook("onRequest", requireAuth);\napp.post("/acme-api/named", async () => ({ ok: true }));\n'
FX["api/short-hook.ts"] = 'import Fastify from "fastify";\n\nconst app = Fastify();\napp.addHook("onRequest");\napp.post("/acme-api/shorthook", async () => ({ ok: true }));\n'
GOLD += [
    ("api/short-hook.ts", '"/acme-api/shorthook"', "HIGH: POST /acme-api/shorthook auth=none"),  # a hook call with no handler in a file that holds a route is no evidence
    ("rh/enc/app.ts", '"/acme-api/inside"', "INFO: POST /acme-api/inside auth=root-hook"),  # a hook in a plugin function covers what follows it in that function
    ("rh/enc/app.ts", '"/acme-api/outside"', "HIGH: POST /acme-api/outside auth=none"),  # and nothing after it
    ("rh/recv/app.ts", '"/acme-api/mine"', "INFO: POST /acme-api/mine auth=root-hook"),  # a hook covers the routes of its own receiver
    ("rh/recv/app.ts", '"/acme-api/theirs"', "HIGH: POST /acme-api/theirs auth=none"),  # and of no other instance
    ("rh/reqfy/app.ts", '"/acme-api/req"', "INFO: POST /acme-api/req auth=root-hook"),  # `require("fastify")()` binds a Fastify instance too
    ("api/legacy-hook.ts", '"/acme-api/plugged"', "INFO: POST /acme-api/plugged auth=authenticate"),  # a hook on a receiver no `Fastify()` call binds keeps the by-name rule
    ("api/named-ref.ts", '"/acme-api/named"', "INFO: POST /acme-api/named auth=requireAuth"),  # so does a named guard on a `Fastify()` receiver
]


JS_T = 'const app = require("express")();\napp.post("/t", (req, res) => res.send("t"));\n'
FX["webapp/api/route.ts"] = POST1  # `webapp/` is not an `app/` directory: not a Next route
for rel in ("test/app.js", "tests/app.js", "src/tests/app.js", "e2e/app.js", "__tests__/app.js", "src/x.spec.js", "src/x.test.js"):  # one silent file per TEST alternative
    FX[rel] = JS_T
for rel in ("api/conftest.py", "api/items_test.py", "api/test_items.py"):
    FX[rel] = '@app.post("/t")\ndef t():\n    return 1\n'
QUIET = ("lib/client.js", "lib/keys.js", "lib/plain.ts", "lib/cmp.ts")  # scanned (they look like they hold a route) but yield no handler row


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


LIT_POST = r'\s*={2,3}(?!=)\s*[\w$.]+(?=\s*[^\s\w$.?(\[])", post)'  # lit()'s test of what follows the literal
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
    (r"=\s*(?:await\s+)?(?:new\s+)?(?:express", r"=\s*(?:new\s+)?(?:express"), (r"(?:new\s+)?", ""), (r"\b(\w+)\s*(?::[^=\n]+)?=\s*(?:await", r"\b(\w+)\s*=\s*(?:await"),
    (r"""\b(\w+)\s*(?::[^=\n]+)?=\s*(?:[Ff]astify""", r"""\b(\w+)\s*=\s*(?:[Ff]astify"""), (r"=\s*(?:await\s+)?(?:require|import)", r"=\s*(?:require|import)"),
    (r"^([ \t]*)@", r"^()@"), (r"@\w+\.(%s|route)", r"@\w\.(%s|route)"), (r'(%s|route)\(" % H, re.M)', r'(%s)\(" % H, re.M)'),
    (r'" % H, re.M)', r'" % H)'),
    (r"(?:%s|all)[(<]|use", r"(?:%s)[(<]|use"), (r"(?:%s|all)[(<]|use", r"(?:%s|all)\(|use"), (r"(?:%s|all)[(<]|use", r"(?:%s|all)[<]|use"), (r'|use server"', '"'),
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
    *[(c + "40[13]", c + v) for c in (r"\bstatus[:(]\s*", r"\.code\(\s*", r"\bstatusCode\s*=\s*") for v in ("40[1]", "40[3]", "40[123]", "40.")],
    (r"|\.code\(\s*", r"|code\(\s*"), (r"\.code\(\s*", r"\.code\("), (r"\bstatusCode\s*=\s*", r"\bstatusCode\s*={1,3}\s*"), (r"\bstatusCode\s*=\s*", r"\bstatusCode\s*="),
    (r"|\bstatusCode", r"|statusCode"), *each(r"\.(?:unauthorized|forbidden)\(", "(?:", ")", "|"),
    (r"|\.(?:unauthorized|forbidden)\(", r"|(?:unauthorized|forbidden)\("), (r"\.(?:unauthorized|forbidden)\(", r"\.(?:unauthorized|forbidden)"),
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
    ("a = t.end() - 1", "a = t.end()"), ("b = close_of(m, a)", "b = close_of(mk, a)"), ("[(a, b) for a, b, s, e in ifs(m)", "[(a, e) for a, b, s, e in ifs(m)"),
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
    ("if REFUSE.search(mk[s:e + 1])]", "]"), ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk)"),
    ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk[s:])"), ("REFUSE.search(mk[s:e + 1])", "REFUSE.search(mk[:e + 1])"), ("yield a, b, s, e", "yield a, b, s, b"),
    ('REFUSE.pattern + "|" + CALL.pattern', "REFUSE.pattern"), ('REFUSE.pattern + "|" + CALL.pattern', "CALL.pattern"),
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
    ('"use|addHook|%s|all" % H', '"addHook|%s|all" % H'), ('"use|addHook|%s|all" % H', '"use|%s|all" % H'), ('"use|addHook|%s|all" % H', '"use|addHook|%s" % H'),
    ("if rcv is not None and t.group(1) not in rcv: continue", "pass"), ("rcv is not None and ", ""), ("t.group(1) not in rcv", "t.group(1) in rcv"),
    ("if ps: yield t, op, cl, ps", "yield t, op, cl, ps"), ("p0 = ps[0][1].strip()", "p0 = ps[0][1]"), ("lit = LIT.fullmatch(p0)", "lit = LIT.match(p0)"),
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
    ("pm = ps and re.fullmatch(", "pm = re.fullmatch("), (r'\1""", ps[0][1].strip())', r'\1""", ps[0][1])'), ("HOOK.fullmatch(ps[0][1].strip())", "HOOK.fullmatch(ps[0][1])"),
    (r"""(/[^"']*|)""", r"""(/[^"']*)"""), (r"""(["'])(/[^"']*|)""", r"""(["])(/[^"']*|)"""), (r"""(["'])(/[^"']*|)""", r"""(['])(/[^"']*|)"""),
    ("dm = PYDEF.search(m, cl) if pm else None", "dm = PYDEF.search(m, cl)"), ("if sc < 0: continue", "if False: continue"),
    (r"[\[(]([^\])]*)", r"\[([^\])]*)"),
    ('meths = [t.group(2).upper()]', "meths = [t.group(2)]"), ("km.group(1), re.I)]", "km.group(1))]"),
    (r"""['"]%s['"]""", r"""["]%s["]"""), (r"""['"]%s['"]""", r"""[']%s[']"""),
    ('else: meths = ["GET"]', 'else: meths = ["ANY"]'), ("if not meths: continue", "if not meths: pass"),
    (r"[ \t]{0,%d}(?=\S)", r"[ \t]{%d}(?=\S)"), ("% n).search(m, i)", "% 0).search(m, i)"), ("return e.start() if e else len(m)", "return e.start() if e else 0"),
    ("outdent(m, sc, len(t.group(1)))", "outdent(m, sc, 0)"), ("outdent(m, t.end(), len(t.group(1)))", "outdent(m, t.end(), 0)"),
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
    ('or ("token" if any(g[1] for g in got) else None) or mw', "or mw"),
    ('or mw or ("root-hook" if gated(sites, route)', 'or ("root-hook" if gated(sites, route)'),
    ('or ("root-hook" if gated(sites, route) or meth != "GET" and gated([("", mine)], route) else None) or "none"', 'or "none"'), ("if gated(sites, route) or meth", "if sites or meth"),
    ('or ("token" if any(g[1] for g in got) else None) or mw or ("root-hook"', 'or mw or ("token" if any(g[1] for g in got) else None) or ("root-hook"'),
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
    ("if raw is None: continue", "if raw is None: pass"), ("if NAPP.match(rel) or NAPI", "if NAPI"), ("or NAPI.match(rel) or (PYDEC", "or (PYDEC"),
    ('(PYDEC if rel.endswith(".py") else JSPRE)', '(JSPRE if rel.endswith(".py") else PYDEC)'), ("len(todo)", "len(todo) + 1"),
    # typed registrations: the `<...>` scan in opener, and where callargs looks for it
    ('if m[i:i + 1] == "(": return i', 'if m[i:i + 1] == "(": return -1'), ("o = a = 0", "o = a = 1"),
    ("min(len(m), i + 2000)", "i + 2000"), ("min(len(m), i + 2000)", "len(m)"), ("i + 2000", "i + 1999"), ("i + 2000", "i + 2001"),
    ('if c in "([{": o += 1', 'if c in "([": o += 1'), ('if c in "([{": o += 1', 'if c in "({": o += 1'), ('if c in "([{": o += 1', 'if c in "[{": o += 1'),
    ('elif c in ")]}":', 'elif c in ")]":'), ('elif c in ")]}":', 'elif c in ")}":'), ('elif c in ")]}":', 'elif c in "]}":'),
    ("if o < 0: return -1", "pass"), ("elif o == 0:", "elif True:"), ('if c == "<": a += 1', 'if c == "<": a += 2'),
    ('elif c == ">" and m[k - 1] != "=":', 'elif c == ">":'), ('elif c == ">" and m[k - 1] != "=":', 'elif c == ">" and m[k + 1] != "=":'),
    ("a -= 1", "a -= 2"), ("a -= 1", "pass"), ("if a == 0:", "if a == 1:"),
    ("OPEN.match(m, k + 1)", "OPEN.match(m, k)"), ("OPEN.match(m, k + 1)", "OPEN.match(m, k + 2)"), ("OPEN.match(m, k + 1)", "OPEN.search(m, k + 1)"),
    (r'OPEN = re.compile(r"\s*\(")', r'OPEN = re.compile(r"\(")'), (r'OPEN = re.compile(r"\s*\(")', r'OPEN = re.compile(r"\s+\(")'),
    ("return x.end() - 1 if x else -1", "return x.end() if x else -1"),
    ('elif c == ";" or m[k:k + 2] in ("&&", "||"): return -1', 'elif m[k:k + 2] in ("&&", "||"): return -1'),
    ('elif c == ";" or m[k:k + 2] in ("&&", "||"): return -1', 'elif c == ";" or m[k:k + 2] in ("||",): return -1'),
    ('elif c == ";" or m[k:k + 2] in ("&&", "||"): return -1', 'elif c == ";" or m[k:k + 2] in ("&&",): return -1'),
    ('elif c == ";" or m[k:k + 2] in ("&&", "||"): return -1', 'elif c == ";" or m[k:k + 1] in ("&&", "||"): return -1'),
    (r'(?=[(<])" % names', r'(?=[(])" % names'), (r'(?=[(<])" % names', r'(?=[<])" % names'),
    # hook handlers: what makes a hook gate, and which paths its text scopes or exempts
    ("if w in dc and w not in seen: seen.add(w); sp.append(dc[w])", "if w in dc: seen.add(w); sp.append(dc[w])"),
    ("seen.add(w); sp.append(dc[w])", "seen.add(w)"), ("for x, y in sp:  # grows as it goes", "for x, y in list(sp):  # grows as it goes"),
    ('REFUSE.search("\\n".join(mk[x:y] for x, y in sp))', 'REFUSE.search("\\n".join(m[x:y] for x, y in sp))'),
    ('CALL.search("\\n".join(m[x:y] for x, y in sp))', 'CALL.search("\\n".join(mk[x:y] for x, y in sp))'),
    (r'or (re.fullmatch(r"[\w$.]+", m[a:b].strip()) and USE.search(m[a:b]))', "or False"),
    (r're.fullmatch(r"[\w$.]+", m[a:b].strip())', r're.match(r"[\w$.]+", m[a:b].strip())'), ("and USE.search(m[a:b])", "and True"),
    (r'r"[\w$.]+", m[a:b].strip()', r'r"[\w$]+", m[a:b].strip()'), (r"m[a:b].strip()) and USE", r"m[a:b]) and USE"),
    ('"!" in m[o:g.start()]', '"!" in m[:g.start()]'), ('"!" in m[o:g.start()]', '"!" in m[o:]'), ('"!" in m[o:g.start()]', '"!" in m[o:c]'),
    ('if "!" in m[o:g.start()]: return None', 'if "!" in m[o:g.start()]: pass'), ("scope.add(lit(mk, g))", "free.add(lit(mk, g))"),
    ("scope.add(lit(mk, g))", 'scope.add((litpath(g), "?"))'), ("lits = {lit(mk, g) for", 'lits = {(litpath(g), "?") for'),
    # lit: how the text tests a hook's path (`==`/`===` on either side against a plain name, `startsWith(`, anything else)
    ('"=" if re.search(', '"?" if re.search('), ('"^" if re.search(', '"?" if re.search('),
    (r'={2,3}\s*$", pre)', r'={3}\s*$", pre)'), (r'={2,3}\s*$", pre)', r'={2}\s*$", pre)'), (r'={2,3}\s*$", pre)', r'={2,3}$", pre)'),
    (r'[\w$]\s*={2,3}\s*$", pre)', r'\s*={2,3}\s*$", pre)'), (r'[\w$]\s*={2,3}\s*$", pre)', r'[\w$)]\s*={2,3}\s*$", pre)'), (r'[\w$]\s*={2,3}\s*$", pre)', r'[\w$\]]\s*={2,3}\s*$", pre)'),
    (LIT_POST, LIT_POST.replace("{2,3}", "{3}")), (LIT_POST, LIT_POST.replace("{2,3}", "{2}")), (LIT_POST, LIT_POST[3:]), (LIT_POST, LIT_POST.replace(r"\s*[\w$.]+(?=\s*[^\s\w$.?(\[])", "")),
    (LIT_POST, LIT_POST.replace("(?!=)\\s*", "(?!=)")), (LIT_POST, LIT_POST.replace("[\\w$.]+", "[\\w$]+")), (LIT_POST, LIT_POST.replace("$.?(", "$.?")), (LIT_POST, LIT_POST.replace(r"?(\[", r"?(")),
    (LIT_POST, LIT_POST.replace("$.?(", "$.(")),
    (r'startsWith\(\s*$', r'startsWith\s*$'), ("mk[max(0, g.start() - 40):g.start()]", "mk[g.start():g.start()]"), ("mk[g.end():g.end() + 40]", "mk[g.end():g.end()]"),
    ("return ([sorted(scope)] if scope else []) + groups, sorted(free)", "return ([sorted(free)] if free else []) + groups, sorted(scope)"),
    ("LIT.finditer(mk, x, y)", "LIT.finditer(m, x, y)"), ("LIT.finditer(mk, x, y)", "LIT.finditer(mk, x)"), ("LIT.finditer(mk, x, y)", "LIT.finditer(mk, 0, y)"),
    ("cut[x, y] = r.start() if r else y", "cut[x, y] = y"), ("cut[x, y] = r.start() if r else y", "cut[x, y] = x"), ("REFUSE.search(mk, x, y)", "REFUSE.search(m, x, y)"),
    ("before = o < cut[span]", "before = True"), ("before = o < cut[span]", "before = o > cut[span]"),
    ("if p[0] <= o < p[1]", "if o < p[1]"), ("if p[0] <= o < p[1]", "if p[0] <= o"), ("span = next((p for p in sp if p[0] <= o < p[1]), None)", "span = sp[0]"), ("if span is None: continue", "pass"),
    ("if GATE.search(mk[s:e + 1]):\n            if not before: continue", "if GATE.search(mk[s:e + 1]):\n            pass"), ("elif not before: continue", "elif False: continue"),
    ("if GATE.search(mk[s:e + 1]):", "if REFUSE.search(mk[s:e + 1]):"), ("if GATE.search(mk[s:e + 1]):", "if GATE.search(m[s:e + 1]):"),
    ("for g in LIT.finditer(mk, o, c):", "for g in LIT.finditer(mk, s, e):"), ("elif BARE.search(m[s:e + 1]):", "elif BARE.search(mk[s:e + 1]):"),
    ('if lits and "!" not in m[o:c]: free |= lits', "if lits: free |= lits"), ('if lits and "!" not in m[o:c]: free |= lits', 'if lits and "!" in m[o:c]: free |= lits'),
    ('if lits and "!" not in m[o:c]: free |= lits', 'if lits and "!" not in m[o:]: free |= lits'), ('if lits and "!" not in m[o:c]: free |= lits', 'if lits and "!" not in m[:c]: free |= lits'),
    ("elif lits: groups.append(sorted(lits))", "elif lits: free |= lits"),
    (r'elif lits and re.search(r"&&|\|\|", m[o:c]): return None', "elif False: return None"), (r'elif lits and re.search(r"&&|\|\|", m[o:c]): return None', r'elif lits and re.search(r"\|\|", m[o:c]): return None'),
    (r'elif lits and re.search(r"&&|\|\|", m[o:c]): return None', r'elif lits and re.search(r"&&", m[o:c]): return None'),
    ("and SEC.search(mk[o:c])): return None", "and SEC.search(mk[o:c])): pass"), ("elif not (CALL.search(m[o:c]) or ", "elif not ("), ("CMP.search(mk[o:c]) and SEC", "SEC"), (" and SEC.search(mk[o:c])", ""),
    ("CMP.search(mk[o:c]) and SEC", "CMP.search(mk[o:c]) or SEC"), ("and SEC.search(mk[o:c])", "and SEC.search(m[o:c])"), ("CALL.search(m[o:c]) or", "CALL.search(mk[o:c]) or"),
    ("return ([sorted(scope)] if scope else []) + groups, sorted(free)", "return [sorted(scope)] + groups, sorted(free)"), ("return ([sorted(scope)] if scope else []) + groups, sorted(free)", "return ([sorted(scope)] if scope else []), sorted(free)"),
    (r'\b(?:done|next)\(\s*\)', r'\b(?:next)\(\s*\)'), (r'\b(?:done|next)\(\s*\)', r'\b(?:done)\(\s*\)'), (r'\b(?:done|next)\(\s*\)', r'\b(?:done|next)\(\)'),
    (r'\breturn\s*(?:;|\}|$)', r'\breturn\s*(?:;|$)'), (r'\breturn\s*(?:;|\}|$)', r'\breturn\s*(?:;|\})'), (r'\breturn\s*(?:;|\}|$)', r'\breturn\s*(?:\}|$)'), (r'\breturn\s*(?:;|\}|$)', r'\breturn\s+(?:;|\}|$)'),
    # declarations at any indent
    (r'DECL = re.compile(r"^([ \t]*)', r'DECL = re.compile(r"^()'), (r"^([ \t]*)(?:export\s+)?(?:async", r"^([ \t]*)(?:async"),
    (r"(?:export\s+)?(?:async\s+)?(?:function|const|let|var)", r"(?:export\s+)?(?:function|const|let|var)"),
    *each(r"(?:function|const|let|var)", "(?:", ")", "|"),
    ("{t.group(2): (t.end()", "{t.group(1): (t.end()"),
    # mount: the prefix a register call gives its plugin
    ('ps[1][1].strip() if len(ps) > 1 else "{}"', 'ps[1][1].strip() if len(ps) > 1 else ""'), ('ps[1][1].strip() if len(ps) > 1 else "{}"', 'ps[1][1].strip() if len(ps) > 2 else "{}"'),
    ('if o[:1] != "{" or "..." in o: return None', 'if "..." in o: return None'), ('if o[:1] != "{" or "..." in o: return None', 'if o[:1] != "{": return None'),
    (r'if not re.search(r"\bprefix\b", o): return ""', r'if not re.search(r"\bprefix\b", o): return None'),
    (r'LIT.pattern + r"\s*[,}]", o)', r'LIT.pattern + r"", o)'), (r'LIT.pattern + r"\s*[,}]", o)', r'LIT.pattern + r"\s*[,]", o)'), (r'LIT.pattern + r"\s*[,}]", o)', r'LIT.pattern + r"\s*[}]", o)'),
    ('return g[2].rstrip("/") if g else None', 'return g[2] if g else None'), ('return g[2].rstrip("/") if g else None', 'return g[1].rstrip("/") if g else None'),
    ('return g[2].rstrip("/") if g else None', 'return g[2].rstrip("/") if g else ""'),
    # resolve: which scanned file an import names
    ("posixpath.join(posixpath.dirname(rel), spec)", "posixpath.join(rel, spec)"),
    ("posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))", "posixpath.join(posixpath.dirname(rel), spec)"),
    (r'for c in (b, re.sub(r"\.jsx?$", "", b)):', "for c in (b,):"), (r're.sub(r"\.jsx?$", "", b)', r're.sub(r"\.js$", "", b)'),
    ('("",) + EXT + tuple("/index" + e for e in EXT)', 'EXT + tuple("/index" + e for e in EXT)'), ('("",) + EXT + tuple("/index" + e for e in EXT)', '("",) + EXT'),
    ("if c + s in known: return c + s", "if c + s in known: return b"),
    # regs: the imports, the hooks and the register calls of a file
    ("m, mk = mask(raw), mask(raw, True)", "m, mk = mask(raw, True), mask(raw, True)"),
    ("for _, b in items(", "for b, _ in items("), ('re.sub(r"[{}]", "", t[1])', "t[1]"), ("resolve(rel, t[3], known)", "resolve(rel, t[2], known)"), ("for t in rx.finditer(mk):", "for t in rx.finditer(m):"),
    (r"""from\s*(["'])(\.""", r"""from\s*(["'])("""), (r"""from\s*(["'])(\.""", r"""from\s*(["])(\."""), (r"""from\s*(["'])(\.""", r"""from\s*(['])(\."""),
    (r"""\(\s*(["'])(\.""", r"""\(\s*(["'])("""), (r"""\(\s*(["'])(\.""", r"""\(\s*(["])(\."""), (r"""\(\s*(["'])(\.""", r"""\(\s*(['])(\."""),
    (r"""\(\s*["'](\.""", r"""\(\s*["']("""), (r"""\(\s*["'](\.""", r"""\(\s*["](\."""), (r"""\(\s*["'](\.""", r"""\(\s*['](\."""),
    (r"[Ff]astify|require", "Fastify|require"), (r"[Ff]astify|require", "fastify|require"), (r"""|require\(\s*["']fastify["']\s*\)""", ""), ('callargs(m, mk, "addHook", set(FRCV.findall(mk)))', 'callargs(m, mk, "addHook", set(FRCV.findall(m)))'),
    ("set(RCV.findall(m)), set(FRCV.findall(mk))", "set(RCV.findall(m)), set(FRCV.findall(m))"),
    ("INL.findall(ps[0][1])", "INL.findall(ps[0][0])"), ("imp.get(w)", "imp[w]"), (r' | {imp.get(w) for w in re.findall(r"[\w$]+", ps[0][0])}', ""),
    ("len(ps) < 2 or ", ""), ("a = op + 2 + len(ps[0][0])", "a = op + 1 + len(ps[0][0])"), ("a = op + 2 + len(ps[0][0])", "a = op + 3 + len(ps[0][0])"),
    ("if h: hooks", "if True: hooks"), ("hooks.setdefault(t[1], [])", "hooks.setdefault(None, [])"), ("(t.start(), block_end(m, t.start()), h)", "(0, block_end(m, t.start()), h)"),
    ("(t.start(), block_end(m, t.start()), h)", "(t.start(), len(m), h)"), ("(t.start(), block_end(m, t.start()), h)", "(t.start(), 0, h)"),
    ("[h for p, q, h in hooks.get(t[1], []) if p < t.start() < q]", "[h for v in hooks.values() for p, q, h in v if p < t.start() < q]"),
    ("hooks.get(t[1], [])", "hooks[t[1]]"), ("hooks.get(t[1], []) if p < t.start() < q]", "hooks.get(t[1], []) if p < t.start()]"),
    ("hooks.get(t[1], []) if p < t.start() < q]", "hooks.get(t[1], []) if t.start() < q]"), ("site = (mount(ps), ", 'site = ("", '),
    # block_end, the direct calls and the hook handlers' registration, call_hs's own-receiver rule
    ('m.rfind("\\n", 0, i) + 1', 'm.rfind("\\n", 0, i)'), ("outdent(m, i, n - 1) if n else len(m)", "outdent(m, i, n) if n else len(m)"), ("outdent(m, i, n - 1) if n else len(m)", "outdent(m, i, n - 1) if not n else len(m)"),
    (r're.match(r"[ \t]*", m[', r're.match(r"[ \t]+", m['),
    (r'ARG1 = re.compile(r"\s*([\w$]+)\s*[,)]")', r'ARG1 = re.compile(r"([\w$]+)\s*[,)]")'), (r'ARG1 = re.compile(r"\s*([\w$]+)\s*[,)]")', r'ARG1 = re.compile(r"\s*([\w$]+)[,)]")'),
    (r'ARG1 = re.compile(r"\s*([\w$]+)\s*[,)]")', r'ARG1 = re.compile(r"\s*([\w$]+)\s*[,]")'), (r'ARG1 = re.compile(r"\s*([\w$]+)\s*[,)]")', r'ARG1 = re.compile(r"\s*([\w$]+)\s*[)]")'),
    ("hooks.get(x and x[1], [])", "hooks.get(t[1], [])"), ("hooks.get(x and x[1], [])", 'hooks.get("app", [])'), ("hooks.get(x and x[1], [])", "hooks.get(None, [])"), ("hooks.get(x and x[1], [])", "hooks.get(x[1], [])"),
    ("x = ARG1.match(m, t.end())", "x = None"), ("sites.append((imp[t[1]], (", "sites.append((None, ("), ('("", [h for p, q, h in hooks.get(x and x[1], [])', '(None, [h for p, q, h in hooks.get(x and x[1], [])'),
    ("hooks.get(x and x[1], []) if p < t.start() < q]", "hooks.get(x and x[1], []) if p < t.start()]"), ("hooks.get(x and x[1], []) if p < t.start() < q]", "hooks.get(x and x[1], []) if t.start() < q]"),
    ("for _, op, cl, _ in regs): continue", "for _, op, cl, _ in regs): pass"), ("if any(op < t.start() < cl for", "if any(op < t.start() for"), ("if any(op < t.start() < cl for", "if any(t.start() < cl for"),
    ("if names else ()", "if True else ()"), ("[re.escape(w) for w, f in imp.items() if f]", "[w for w, f in imp.items() if f]"), (r'% "|".join(names)', r'% "".join(names)'),
    (r'(?<![\w$.])(%s)\(', r'(?<![$.])(%s)\('), (r'(?<![\w$.])(%s)\(', r'(?<![\w.])(%s)\('), (r'(?<![\w$.])(%s)\(', r'(?<![\w$])(%s)\('), (r'(?<![\w$.])(%s)\(', r'(?<![\w$.])(%s)'),
    ("len(ps) > 1 and not re.fullmatch", "len(ps) > 0 and not re.fullmatch"), ("r in frcv", "True"), (r' and not re.fullmatch(r"[\w$.]+", ps[1][0].strip())', ""), ("ps[1][0].strip()): continue", "ps[1][0].strip()): pass"),
    (r"|preParsing)\1", r"|preParsing|onRoute)\1"), (r"|preParsing)\1", r"|preParsing|onListen)\1"), (r"|preParsing)\1", r"|preParsing|onSend)\1"),
    # gated: the route (mount + route) against the hook's scope and exempt paths, at every registration site
    ("bool(q) and ", ""), ('p == q or op == "^"', 'op == "^"'), ('p == q or op != "="', 'op != "="'), ('p.startswith(q + "/")', "p.startswith(q)"),
    ('op == "^" and bool(q)', 'op != "=" and bool(q)'), ('p == q or op == "^" and bool(q)', "p == q or bool(q)"),
    ('op != "=" and (op == "^" or bool(q))', '(op == "^" or bool(q))'), ('(op == "^" or bool(q))', "bool(q)"), ('(op == "^" or bool(q))', "True"),
    ("bool(q)) and p.startswith(q)", 'bool(q)) and p.startswith(q + "/")'),
    ("if not (sc or ex): return True", "pass"), ("if not (sc or ex): return True", "if not sc: return True"), ("if not (sc or ex): return True", "if not ex: return True"),
    ("if pre is None: return False", "pass"), ('(pre + route).rstrip("/")', "pre + route"),
    ("all(any(cover(p, q) for q in g) for g in sc)", "any(any(cover(p, q) for q in g) for g in sc)"), ("all(any(cover(p, q) for q in g) for g in sc)", "all(any(exempt(p, q) for q in g) for g in sc)"),
    ("for g in sc)", "for g in sc[:1])"), ("and not any(exempt(p, q) for q in ex)", ""), ("and not any(exempt(p, q) for q in ex)", "and any(exempt(p, q) for q in ex)"),
    ("and not any(exempt(p, q) for q in ex)", "and not any(cover(p, q) for q in ex)"),
    ("any(ok(pre, *h) for h in hs)", "all(ok(pre, *h) for h in hs)"), ("all(any(ok(pre, *h)", "any(any(ok(pre, *h)"), ("return bool(sites) and all(", "return all("),
    # scan: which files register which
    ("known = set(files)", "known = set()"), ("cov.setdefault(f, []).append(site)", "cov[f] = [site]"), ("cov.get(rel)", "None"),
    ("o -= 1", "o -= 2"), ("o -= 1", "pass"), ("    return -1\n\n\ndef callargs", "    return i\n\n\ndef callargs"),
    ("opener(m, t.end())", "opener(m, t.end() - 1)"), ("opener(m, t.end())", "opener(m, t.end() + 1)"), ("close_of(m, op) if op > 0 else -1", "close_of(m, op)"),
    ("sp, seen = [(a, b)], set()", "sp, seen = [], set()"), (r're.findall(r"[\w$]+", m[x:y])', r're.findall(r"\w+", m[x:y])'), (r're.findall(r"[\w$]+", ps[0][0])', r're.findall(r"\w+", ps[0][0])'),
    (r"\s+([\w$]+)", r"\s+(\w+)"), ("for x, y in reach(m, dc, o, c + 1) for g in LIT", "for x, y in [(o, c + 1)] for g in LIT"),
    ("for x, y in reach(m, dc, o, c + 1) for g in LIT", "for x, y in sp for g in LIT"), ("{}, decls(m), {}", "{}, {}, {}"),
    ("for rx in IMP:", "for rx in IMP[:1]:"), ("for rx in IMP:", "for rx in IMP[1:]:"), ("a + len(ps[1][0]))", "a + len(ps[0][0]))"),
    # analyze: a hook on the route's own receiver; scan: which files get wired
    ('gated(sites, route) or meth != "GET" and gated([("", mine)], route)', "gated(sites, route)"), ('meth != "GET" and gated(', "gated("), ('meth != "GET" and gated(', 'meth == "GET" and gated('),
    ('gated([("", mine)], route)', "gated([(None, mine)], route)"), ("hooks.get(rcv, ())", "hooks.get(None, ())"), ("hooks.get(rcv, ())", 'hooks.get("app", ())'),
    ("hooks.get(rcv, ()) if p < pos < q]", "hooks.get(rcv, ()) if p < pos]"), ("hooks.get(rcv, ()) if p < pos < q]", "hooks.get(rcv, ()) if pos < q]"),
    ('hooks, py = hooks or {}, rel.endswith(".py")', 'hooks, py = hooks, rel.endswith(".py")'), ("own.get(rel))", "None)"),
    ('".register" in raw or "addHook" in raw', '".register" in raw'), ('".register" in raw or "addHook" in raw', '"addHook" in raw'),
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
