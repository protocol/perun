#!/usr/bin/env python3
"""Tests for the injection rules in the bundled semgrep templates: perun.js.postgrest-filter-injection,
perun.js.git-argument-injection and perun.py.git-argument-injection, plus the app-router sources and unsafe raw-SQL sinks added
to perun.js.sqli and the app-router sources added to perun.js.command-injection (js.yml, py.yml).

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` (or `# ruleid: <id>`) comment marks the NEXT line as a
required finding, an `// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay
clean too. All names and values are fictional. RULES=<dir> checks another copy of the rules (used to show the cases fail without
them). The live check needs semgrep and prints SKIP without it (CI installs none); the offline checks always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
SQLI, CMD = "perun.js.sqli", "perun.js.command-injection"
PG, GIT, PYGIT = "perun.js.postgrest-filter-injection", "perun.js.git-argument-injection", "perun.py.git-argument-injection"
NEW = (PG, GIT, PYGIT)
IDS = (SQLI, CMD, *NEW)

# sqli with an Express-style source: unsafe raw-SQL sinks, and tagged templates (they bind their values) that stay clean.
SQLI_EXPRESS_TS = r'''
declare const app: any;
declare const prisma: any;
declare const tx: any;
declare const db: any;
declare const sql: any;
declare const Prisma: any;
declare const sqlc: any;

// An unsafe raw-SQL call takes the whole string: $queryRawUnsafe and $executeRawUnsafe on any receiver, sql.raw and sql.unsafe.
app.get("/acme/items", async (req: any, res: any) => {
  // ruleid: perun.js.sqli
  await prisma.$queryRawUnsafe(`select * from acme_items where name = '${req.query.name}'`);
  // ruleid: perun.js.sqli
  await prisma.$executeRawUnsafe("delete from acme_items where id = " + req.params.id);
  // ruleid: perun.js.sqli
  await tx.$queryRawUnsafe(`select * from acme_items where owner = '${req.body.owner}'`);
  // ruleid: perun.js.sqli
  await db.execute(sql.raw(`select * from acme_items order by ${req.query.sort}`));
  // ruleid: perun.js.sqli
  await sql.unsafe(`select * from acme_items where name = '${req.query.name}'`);
  res.end();
});

// A tagged template binds its values: prisma.$queryRaw, a sql or Prisma.sql tag, also passed to db.execute(...) or held in a variable.
// A bound parameter after the query string, a constant or a number is clean. ponytail limit: a receiver not named sql is not followed.
app.get("/acme/bound", async (req: any, res: any) => {
  // ok: perun.js.sqli
  await prisma.$queryRaw`select * from acme_items where name = ${req.query.name}`;
  // ok: perun.js.sqli
  await db.execute(sql`select * from acme_items where name = ${req.query.name}`);
  // ok: perun.js.sqli
  await db.execute(Prisma.sql`select * from acme_items where name = ${req.query.name}`);
  const query = sql`select * from acme_items where owner = ${req.body.owner}`;
  // ok: perun.js.sqli
  await db.execute(query);
  // ok: perun.js.sqli
  await prisma.$queryRawUnsafe("select * from acme_items where name = $1", req.query.name);
  // ok: perun.js.sqli
  await sql.raw("select 1");
  // ok: perun.js.sqli
  await sql.raw(String(Number(req.query.limit)));
  // ok: perun.js.sqli
  await sqlc.unsafe(`select * from acme_items where name = '${req.query.name}'`);
  res.end();
});

// A sql.raw call is a sink wherever it sits: on its own, outside any execute call, and inside a tagged template (the tag binds the
// values it is given, not the raw text). ponytail limit: a template that holds a sql.raw call is not treated as safe.
app.get("/acme/raw", async (req: any, res: any) => {
  // ruleid: perun.js.sqli
  const fragment = sql.raw(req.query.sort);
  // ruleid: perun.js.sqli
  await db.execute(sql`select * from acme_items order by ${sql.raw(req.query.sort)}`);
  res.end();
});
'''

# Part 1 sources, read through sqli and command-injection: URL parameters and each body reader of an exported route handler.
APP_URL_TS = r'''
import { NextRequest } from "next/server";
import { exec } from "node:child_process";

declare const pool: any;
declare const base: string;

// nextUrl.searchParams, new URL(request.url) with and without a base, a variable holding the URL.
export async function GET(request: NextRequest) {
  const a = request.nextUrl.searchParams.get("a");
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where a = '${a}'`);
  const b = new URL(request.url).searchParams.get("b");
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where b = '${b}'`);
  const c = new URL(request.url, base).searchParams.get("c");
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where c = '${c}'`);
  const url = new URL(request.url);
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where d = '${url.searchParams.get("d")}'`);
  // ruleid: perun.js.command-injection
  exec(`ls ${a}`);
  // ok: perun.js.sqli
  await pool.query("select * from acme_reports where a = $1", [a]);
  return new Response("ok");
}

// searchParams destructured from the URL, and from nextUrl.
export async function HEAD(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where e = '${searchParams.get("e")}'`);
  return new Response(null);
}
export async function OPTIONS(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where f = '${searchParams.get("f")}'`);
  return new Response(null);
}

// The JSON body, whole and destructured; the form body with get(...), inline and through a variable; the text body.
export async function POST(request: Request) {
  const body = await request.json();
  // ruleid: perun.js.sqli
  await pool.query("select * from acme_reports where owner = '" + body.owner + "'");
  return new Response("ok");
}
export async function PUT(request: Request) {
  const { title } = await request.json();
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where title = '${title}'`);
  // ruleid: perun.js.command-injection
  exec(`echo ${title}`);
  return new Response("ok");
}
export async function PATCH(request: Request) {
  const form = await request.formData();
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where g = '${form.get("g")}'`);
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where h = '${(await request.formData()).get("h")}'`);
  return new Response("ok");
}
export async function DELETE(request: Request) {
  const text = await request.text();
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where note = '${text}'`);
  // ruleid: perun.js.command-injection
  exec(`echo ${text}`);
  return new Response("ok");
}
'''

# The other declaration forms: export const with an arrow function (typed, with a return type), and a plain export function.
APP_FORMS_TS = r'''
declare const pool: any;

export const GET = async (request: Request): Promise<Response> => {
  const id = new URL(request.url).searchParams.get("id");
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where id = '${id}'`);
  return new Response("ok");
};
export function POST(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  // ruleid: perun.js.sqli
  pool.query(`select * from acme_reports where id = '${id}'`);
  return new Response("ok");
}
export async function PUT(request: Request, context: { params: { id: string } }) {
  const { title } = await request.json();
  // ruleid: perun.js.sqli
  await pool.query(`select * from acme_reports where title = '${title}'`);
  // ok: perun.js.sqli
  await pool.query("select * from acme_reports where id = $1", [context.params.id]);
  return new Response("ok");
}
'''

# Not a route handler: a helper, a function that is not exported, an export under another name, a default export, and a handler
# name in another case. Their request reads are not sources for sqli, postgrest or git, even though the sinks are the same.
NOT_HANDLER_TS = r'''
import { exec, execFile } from "node:child_process";

declare const pool: any;
declare const db: any;

export async function readAcmeItem(req: Request) {
  const q = new URL(req.url).searchParams.get("q");
  // ok: perun.js.sqli
  return pool.query(`select * from acme_items where name = '${q}'`);
}
export async function listAcmeDir(req: Request) {
  const q = new URL(req.url).searchParams.get("q");
  // ok: perun.js.command-injection
  exec(`ls ${q}`);
}
async function GET(request: Request) {
  const q = request.nextUrl.searchParams.get("q");
  // ok: perun.js.postgrest-filter-injection
  return db.from("acme_items").select("*").or(`name.ilike.%${q}%`);
}
export async function Get(request: Request) {
  const { branch } = await request.json();
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", branch]);
}
export default async function POST(request: Request) {
  const body = await request.json();
  // ok: perun.js.sqli
  return pool.query("select * from acme_items where owner = '" + body.owner + "'");
}
'''

# postgrest filter strings, app-router handlers: a request value built into an or(...) argument (template, variable, concatenation,
# a TS cast, String(...), a second argument) or the in list of filter/not.
PG_APP_TS = r'''
import { NextRequest, NextResponse } from "next/server";

declare const db: any;
declare const z: any;
declare function buildAcmeFilter(value: string | null): string;

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q");
  // ruleid: perun.js.postgrest-filter-injection
  const a = await db.from("acme_items").select("*").or(`name.ilike.%${q}%`);
  const filter = `name.ilike.%${q}%,owner.eq.${q}`;
  // ruleid: perun.js.postgrest-filter-injection
  const b = await db.from("acme_items").select("*").or(filter);
  // ruleid: perun.js.postgrest-filter-injection
  const c = await db.from("acme_items").select("*").or("name.eq." + q);
  const joined = "owner.eq." + q + ",kind.eq.acme";
  // ruleid: perun.js.postgrest-filter-injection
  const d = await db.from("acme_items").select("*").or(joined);
  // ruleid: perun.js.postgrest-filter-injection
  const e = await db.from("acme_items").select("*").or(`name.eq.${q}` as string);
  const typed: string = `name.eq.${q}`;
  // ruleid: perun.js.postgrest-filter-injection
  const f = await db.from("acme_items").select("*").or(typed as string);
  // ruleid: perun.js.postgrest-filter-injection
  const g = await db.from("acme_items").select("*").or(`name.eq.${String(q)}`);
  // ruleid: perun.js.postgrest-filter-injection
  const h = await db.from("acme_items").select("*").or(`name.eq.${q}`, { referencedTable: "acme_owners" });
  return NextResponse.json({ a, b, c, d, e, f, g, h });
}

export async function POST(request: Request) {
  const { ids, name } = await request.json();
  // ruleid: perun.js.postgrest-filter-injection
  const a = await db.from("acme_items").select("*").filter("id", "in", `(${ids})`);
  // ruleid: perun.js.postgrest-filter-injection
  const b = await db.from("acme_items").select("*").not("id", "in", `(${ids.join(",")})`);
  // ruleid: perun.js.postgrest-filter-injection
  const c = await db.from("acme_items").select("*").or(`name.eq.${name}`);
  return Response.json({ a, b, c });
}

// Value methods pass a request value as data, not as filter syntax.
export async function PUT(request: Request) {
  const { name, ids } = await request.json();
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").eq("name", name);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").neq("name", name);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").ilike("name", `%${name}%`);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").like("name", `%${name}%`);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").in("id", ids);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").match({ name });
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").filter("name", "eq", name);
  return Response.json({});
}

// An or(...) with a call or a schema value is not a filter string, also with a request value inside the call. A constant string,
// and a value through Number, parseInt or parseFloat, are clean. ponytail limit: a helper call building the string is not followed.
export async function PATCH(request: Request) {
  const { name, count } = await request.json();
  // ok: perun.js.postgrest-filter-injection
  const s = z.string().or(z.literal(`acme-${name}`));
  // ok: perun.js.postgrest-filter-injection
  const t = z.string().or(z.number());
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or(buildAcmeFilter(name));
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or("kind.eq.acme,kind.eq.hello");
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or(`kind.eq.acme`);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or(`count.eq.${Number(count)}`);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or(`count.eq.${parseInt(count, 10)}`);
  // ok: perun.js.postgrest-filter-injection
  await db.from("acme_items").select("*").or(`count.eq.${parseFloat(count)}`);
  return Response.json({ s, t });
}
'''

# postgrest filter strings, Express-style sources (plain JavaScript).
PG_EXPRESS_JS = r'''
const db = makeAcmeClient();

app.get("/acme/items", async (req, res) => {
  // ruleid: perun.js.postgrest-filter-injection
  const a = await db.from("acme_items").select("*").or(`name.ilike.%${req.query.q}%`);
  const filter = `owner.eq.${req.params.owner}`;
  // ruleid: perun.js.postgrest-filter-injection
  const b = await db.from("acme_items").select("*").or(filter);
  // ruleid: perun.js.postgrest-filter-injection
  const c = await db.from("acme_items").select("*").or("name.eq." + req.body.name);
  // ruleid: perun.js.postgrest-filter-injection
  const d = await db.from("acme_items").select("*").not("id", "in", `(${req.query.ids})`);
  // ok: perun.js.postgrest-filter-injection
  const e = await db.from("acme_items").select("*").eq("owner", req.params.owner);
  // ok: perun.js.postgrest-filter-injection
  const f = await db.from("acme_items").select("*").or(`id.eq.${Number(req.query.id)}`);
  // ok: perun.js.postgrest-filter-injection
  const g = await db.from("acme_items").select("*").or("kind.eq.acme");
  res.json({ a, b, c, d, e, f, g });
});
'''

# git argv, app-router handlers: a request value after the command with no terminator; the terminator and the guard clear it.
GIT_APP_TS = r'''
import { execFile, execFileSync, spawn, spawnSync } from "node:child_process";

declare const dir: string;

export async function POST(request: Request) {
  const { repo, branch } = await request.json();
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["clone", repo, dir], () => {});
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["fetch", "origin", branch]);
  // ruleid: perun.js.git-argument-injection
  spawn("git", ["checkout", String(branch)]);
  // ruleid: perun.js.git-argument-injection
  spawnSync("/usr/bin/git", ["ls-remote", repo.trim()]);
  return new Response("ok");
}

export async function GET(request: Request) {
  const rev = new URL(request.url).searchParams.get("rev");
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["log", "-n", "5", rev as string]);
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["show", `${rev}:README.md`]);
  return new Response("ok");
}

export async function PUT(request: Request) {
  const form = await request.formData();
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["clone", form.get("repo") as string, dir]);
  return new Response("ok");
}

export async function PATCH(request: Request) {
  const text = await request.text();
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["checkout", text]);
  return new Response("ok");
}

// The terminator before the value, a guard that returns before the call (also joined with ||), and constant argv are clean.
export async function DELETE(request: Request) {
  const { branch } = await request.json();
  // ok: perun.js.git-argument-injection
  execFileSync("git", ["checkout", "--end-of-options", branch]);
  // ok: perun.js.git-argument-injection
  execFileSync("git", ["status", "--short"]);
  return new Response("ok");
}

export async function HEAD(request: Request) {
  const rev = new URL(request.url).searchParams.get("rev") ?? "";
  if (rev.startsWith("-")) return new Response("bad", { status: 400 });
  // ok: perun.js.git-argument-injection
  execFileSync("git", ["log", rev]);
  return new Response("ok");
}

export async function OPTIONS(request: Request) {
  const { branch } = await request.json();
  if (!branch || branch.length > 80 || branch.startsWith("-")) {
    return new Response("bad", { status: 400 });
  }
  // ok: perun.js.git-argument-injection
  execFileSync("git", ["checkout", branch]);
  return new Response("ok");
}
'''

# git argv, Express-style sources (plain JavaScript): each shape of the call, each source field, each guard and non-guard.
GIT_EXPRESS_JS = r'''
const { execFile, execFileSync, spawn, spawnSync } = require("node:child_process");
const child_process = require("node:child_process");

app.post("/acme/clone", (req, res) => {
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["clone", req.body.repo, "/srv/acme"], (err) => res.end());
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["clone", "--depth", "1", req.body.repo, "/srv/acme"]);
  // ruleid: perun.js.git-argument-injection
  child_process.execFile("git", ["fetch", "origin", req.body.branch]);
  // ruleid: perun.js.git-argument-injection
  child_process.spawn("git", ["ls-remote", req.body.url]);
  // ruleid: perun.js.git-argument-injection
  spawnSync("git", ["checkout", req.body.branch.trim()]);
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["clone", `${req.body.repo}.git`, "/srv/acme"]);
});

app.get("/acme/log", (req, res) => {
  // ruleid: perun.js.git-argument-injection
  execFileSync("git", ["log", "-n", "5", req.query.rev]);
  // ruleid: perun.js.git-argument-injection
  spawnSync("/usr/bin/git", ["show", req.params.sha]);
  // ruleid: perun.js.git-argument-injection
  spawn("git", ["ls-remote", String(req.query.url)]);
  res.end();
});

// A terminator after the value does not protect it. Nor does a guard that is not a startsWith("-") test that returns or throws.
app.post("/acme/weak", (req, res) => {
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["fetch", req.body.repo, "--"]);
  const a = req.body.a;
  if (a.length > 4 && a.startsWith("-")) return;
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["checkout", a]);
  const b = req.body.b;
  if (!b.startsWith("-")) return;
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["checkout", b]);
  const c = req.body.c;
  if (c.startsWith("-")) { console.log("bad"); }
  // ruleid: perun.js.git-argument-injection
  execFile("git", ["checkout", c]);
});

// Clean: a terminator before the value, constant argv, a binary that is not git, a template that starts with constant text, a
// value that is not from the request, and a guard that returns or throws (alone, joined with ||, or with a longer block).
app.post("/acme/safe", (req, res) => {
  // ok: perun.js.git-argument-injection
  execFile("git", ["clone", "--", req.body.repo, "/srv/acme"]);
  // ok: perun.js.git-argument-injection
  execFile("git", ["fetch", "--end-of-options", req.body.branch]);
  // ok: perun.js.git-argument-injection
  execFile("git", ["fetch", '--', req.body.branch]);
  // ok: perun.js.git-argument-injection
  execFile("git", ["status", "--short"]);
  // ok: perun.js.git-argument-injection
  execFile("ls", ["-l", req.body.dir]);
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", `origin/${req.body.branch}`]);
  // ok: perun.js.git-argument-injection
  execFile("git", ["clone", process.env.ACME_REPO, "/srv/acme"]);
  const d = req.body.d;
  if (d.startsWith("-")) return res.status(400).end();
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", d]);
  const e = String(req.body.e).trim();
  if (e.startsWith("-")) throw new Error("bad ref");
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", e]);
  const f = req.body.f;
  if (!f || f.startsWith("-")) { return res.status(400).end(); }
  // ok: perun.js.git-argument-injection
  execFile("git", ["clone", f, "/srv/acme"]);
  const g = req.body.g;
  if (g.startsWith("-") || g.length > 80) { res.status(400).end(); return; }
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", g]);
  const h = req.body.h;
  if (typeof h !== "string" || h.length > 80 || h.startsWith("-")) throw new Error("bad ref");
  // ok: perun.js.git-argument-injection
  execFile("git", ["checkout", h]);
  res.end();
});
'''

# Python: request reads (also get_json) as a list element passed first to subprocess with git; plain parameters and input() are not
# sources; the terminator, an if ... startswith("-") that returns or raises (also in an or condition) and constant lists are clean.
GIT_PY = r'''
import subprocess

import flask
from flask import Flask, request

app = Flask(__name__)


@app.post("/acme/fetch")
def fetch():
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "fetch", "origin", request.json["branch"]], check=True)
    # ruleid: perun.py.git-argument-injection
    subprocess.check_output(["/usr/bin/git", "log", request.args["rev"]])
    # ruleid: perun.py.git-argument-injection
    subprocess.call(["git", "checkout", request.args.get("ref")])
    # ruleid: perun.py.git-argument-injection
    subprocess.Popen(["git", "show", flask.request.args.get("sha")])
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "log", flask.request.args["rev"]])
    data = request.get_json()
    # ruleid: perun.py.git-argument-injection
    subprocess.check_call(["git", "pull", "origin", data["branch"]])
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "clone", request.form.get("repo", "").strip(), "/srv/acme"])
    branch = request.values.get("branch", "")
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", f"{branch}"])
    return "ok"


@app.post("/acme/weak")
def weak():
    a = request.args.get("a", "")
    if len(a) > 4 and a.startswith("-"):
        return "bad", 400
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", a])
    b = request.args.get("b", "")
    if b.startswith("-"):
        print("bad")
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", b])
    # ruleid: perun.py.git-argument-injection
    subprocess.run(["git", "fetch", request.args.get("c"), "--"])
    return "ok"


@app.post("/acme/safe")
def safe(url, ref):
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "clone", "--", request.json["repo"], "/srv/acme"])
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "fetch", "--end-of-options", request.json["branch"]])
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "status", "--short"])
    # ok: perun.py.git-argument-injection
    subprocess.run(["ls", "-l", request.args.get("dir")])
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", f"origin/{request.args.get('branch')}"])
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "clone", url, "/srv/acme"])
    typed = input("ref: ")
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", typed])
    d = request.args.get("d", "")
    if d.startswith("-"):
        return "bad", 400
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", d])
    e = request.args.get("e", "")
    if not e or e.startswith("-"):
        raise ValueError("bad ref")
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", e])
    f = request.args.get("f", "")
    if f.startswith("-") or len(f) > 80:
        print("bad")
        return "bad", 400
    # ok: perun.py.git-argument-injection
    subprocess.run(["git", "checkout", f])
    return "ok"
'''

FILES = {
    "server/acme-sql.ts": SQLI_EXPRESS_TS, "app/api/acme/report/route.ts": APP_URL_TS, "app/api/acme/forms/route.ts": APP_FORMS_TS,
    "lib/acme-helpers.ts": NOT_HANDLER_TS, "app/api/acme/items/route.ts": PG_APP_TS, "server/acme-items.js": PG_EXPRESS_JS,
    "app/api/acme/repo/route.ts": GIT_APP_TS, "server/acme-repo.js": GIT_EXPRESS_JS, "svc/acme_repo.py": GIT_PY,
}
ANN = re.compile(r"^\s*(?://|#)\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= set(IDS), out
    return out


# Offline: the floor of 3 findings and 3 near misses per new rule, counted over distinct fixtures; every fixture has both kinds.
for rid in NEW:
    for kind in ("ruleid", "ok"):
        n = sum(1 for body in {*FILES.values()} for _, r in annotated(body, kind) if r == rid)
        assert n >= 3, (rid, kind, n)
assert all(annotated(b, "ok") and annotated(b, "ruleid") for p, b in FILES.items() if p != "lib/acme-helpers.ts")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in FILES.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES],
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

# Offline: ids and order, message, languages, severity, then the sources, sinks, sanitizers, guards and the regexes (semgrep
# anchors metavariable-regex at the start, as Python's re.match does) that carry the precision. CI installs no semgrep, so each
# guard the live fixtures prove is pinned here too: dropping one fails this file even when the live part is skipped.
JS = open(os.path.join(RULES, "js.yml")).read()
PY = open(os.path.join(RULES, "py.yml")).read()
block = lambda src, rid: src.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
rx = lambda b, mv: re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", b)
jids, pids = re.findall(r"^- id: (\S+)$", JS, re.M), re.findall(r"^- id: (\S+)$", PY, re.M)
assert jids[jids.index(SQLI) + 1] == PG and jids[jids.index(CMD) + 1] == GIT, "each new rule follows the rule it extends"
assert pids[pids.index("perun.py.command-injection") + 1] == PYGIT
assert sum(1 for l in JS.split("\n") if l.startswith("# Also") and "postgrest-filter-injection" in l and "git-argument-injection" in l) == 1
assert sum(1 for l in PY.split("\n") if l.startswith("# Also git-argument-injection")) == 1
for src, rid, lang in ((JS, PG, "[javascript, typescript]"), (JS, GIT, "[javascript, typescript]"), (PY, PYGIT, "[python]")):
    b = block(src, rid)
    assert src.count(f"- id: {rid}\n") == 1 and "  mode: taint\n" in b and f"  languages: {lang}\n" in b and "  severity: WARNING\n" in b, rid
    msg = re.search(r"\n  message: (.+)\n", b)[1]
    assert msg.endswith(".") and len(msg.split()) >= 12 and "`" not in msg and not msg.startswith(("'", '"')), f"{rid} has a plain message: risk, then fix"
    assert "focus-metavariable: $" in b and re.search(r"^\s+# ponytail: ", b, re.M), f"{rid} states its limit in a rule comment"

# App-router sources: the same block, word for word, in the four JS rules that read it; perun.js.xss-response is left as it was.
APP = re.compile(r"^    # App-router input.*?\n(?=  (?:#|pattern-sinks:))", re.M | re.S)
apps = [APP.search(block(JS, rid)) for rid in (SQLI, CMD, PG, GIT)]
assert all(apps) and len({a[0] for a in apps}) == 1, "one app-router block, no drift between rules"
ab = apps[0][0]
for s in ("export async function $H($R, ...) { ... }", "export function $H($R, ...) { ... }", "export const $H = async ($R, ...) => { ... }",
          "$R.nextUrl.searchParams", "new URL($R.url, ...).searchParams", "$U = new URL($R.url, ...);", "{ ..., $K, ... } = new URL($R.url, ...)",
          "{ ..., $K, ... } = $R.nextUrl", "await $R.json()", "await $R.formData()", "await $R.text()"):
    assert s in ab, s
assert rx(ab, "K") == ["^searchParams$"] and "ponytail: a handler is recognized only as export" in ab
hn = rx(ab, "H")[0]
assert all(re.match(hn, s) for s in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")), hn
assert not any(re.match(hn, s) for s in ("Get", "GET2", "handler", "getAll", "POSTS", "ALL", "")), hn
xb = block(JS, "perun.js.xss-response")
assert "export" not in xb and not re.search(r"\$H\b", xb) and "await" not in xb, "xss-response keeps its own sources"
for rid in (SQLI, CMD, PG, GIT):
    b = block(JS, rid)
    for f in ("req.query.$P", "req.body", "req.params.$P", "req.cookies", "request.headers.$P", "request.query"):
        assert f"- pattern: {f}\n" in b, (rid, f)  # the Express-style sources stay

# sqli: the old sources, sinks and sanitizers stay; the unsafe sinks and the tagged-template sanitizers are added.
sb = block(JS, SQLI)
assert all(f"- pattern: {s}\n" in sb for s in ("$DB.query($S, ...)", "$DB.execute($S, ...)", "$DB.raw($S, ...)", "parseInt(...)", "Number(...)")), "sqli keeps its sinks and sanitizers"
assert rx(sb, "DB") == ["^(db|pool|client|conn|connection|knex|sequelize|mysql|pg)$"]
sinks, sans = sb.split("  pattern-sinks:\n")[1].split("  pattern-sanitizers:\n")
for s in ("$X.$queryRawUnsafe($S, ...)", "$X.$executeRawUnsafe($S, ...)", "sql.raw($S)", "sql.unsafe($S, ...)"):
    assert f"- pattern: {s}\n" in sinks, s
assert "- pattern: sql`...`\n" in sans and "- pattern: Prisma.sql`...`\n" in sans, "a sql or Prisma.sql tagged template is a sanitizer"
nest = "pattern-not: $T`...${<... sql.raw(...) ...>}...`"
assert nest in sans and "sql.raw" not in sans.replace(nest, "") and sinks.count("sql.raw($S)") == 1, "sql.raw stays a sink, nested in a tagged template too"
assert "# ponytail: sql.raw and sql.unsafe are matched only on a receiver named sql." in sb and "bound ones included" in sb
assert "$queryRawUnsafe" not in block(JS, CMD) and "sql`" not in block(JS, CMD), "command-injection gets the sources only"

# postgrest-filter-injection.
pb = block(JS, PG)
assert re.findall(r"- pattern: (.*)", pb.split("  pattern-sanitizers:\n")[1]) == ["Number(...)", "parseInt(...)", "parseFloat(...)"]
for s in ("$Q.or($A + $B, ...)", "$Q.or(`...`, ...)", "$Q.filter($C, \"in\", $S)", "$Q.not($C, \"in\", $S)"):
    assert f"- pattern: {s}\n" in pb, s
assert "- pattern-inside: |\n          $S = `...`;\n          ...\n" in pb and "- pattern-inside: |\n          $S = $A + $B;\n          ...\n" in pb, "a local variable assigned a template or concatenation"
psinks = pb.split("  pattern-sinks:\n")[1].split("  pattern-sanitizers:\n")[0]
assert psinks.count("pattern: $Q.or($S, ...)\n") == 2 and not re.search(r"\.(eq|neq|ilike|like|in|match)\(", psinks), "value methods are not sinks"
assert "an .or(...) argument built by a helper call" in pb and "schema-library .or(...)" in pb and "earlier in the same block" in pb

# git-argument-injection (JS).
gb = block(JS, GIT)
fn, bin_, el = rx(gb, "F")[0], rx(gb, "B")[0], rx(gb, "E")[0]
assert all(re.match(fn, s) for s in ("execFile", "execFileSync", "spawn", "spawnSync", "child_process.execFile", "child_process.spawnSync")), fn
assert not any(re.match(fn, s) for s in ("exec", "execSync", "execa", "cp.spawn", "spawnX", "execFileX", "child_process.exec", "util.spawn")), fn
assert all(re.match(bin_, s) for s in ('"git"', "'git'", "`git`", '"/usr/bin/git"', '"./bin/git"', "'/opt/acme/git'")), bin_
assert not any(re.match(bin_, s) for s in ('"gitk"', '"git-lfs"', '"echo"', '"/usr/bin/github"', "gitBin", '"git status"', "git", '"/usr/bin/git-lfs"')), bin_
assert all(re.match(el, s) for s in ("req.body.repo", "String(req.body.repo)", "branch", "rev as string", "`${rev}:README.md`", "form.get(\"repo\") as string")), el
assert not any(re.match(el, s) for s in ('"clone"', "'origin'", '"--"', "`origin/${branch}`", "`clone`")), el
assert '$F($B, [..., $E, ...], ...)' in gb and 'pattern-not: $F($B, [..., "--", ..., $E, ...], ...)' in gb and 'pattern-not: $F($B, [..., "--end-of-options", ..., $E, ...], ...)' in gb
guards = re.findall(r"pattern-not-inside: \|\n\s+if \((.*)\) (\{ \.\.\. )?(return|throw)", gb)
conds = ('$E.startsWith("-")', '<... ($A || $E.startsWith("-")) ...>', '<... ($E.startsWith("-") || $A) ...>')
assert sorted(guards) == sorted((c, b2, t) for c in conds for b2 in ("", "{ ... ") for t in ("return", "throw")), "12 guards: 3 conditions, return or throw, bare or block"
assert "pattern-sanitizers" not in gb, "no sanitizer: a negative number is an option too"
assert "an argv array built elsewhere" in gb and "(--opt=${v}) is not reported" in gb

# git-argument-injection (Python).
yb = block(PY, PYGIT)
srcs = yb.split("  pattern-sinks:\n")[0]
assert re.findall(r"- pattern: (.*)", srcs) == ["request.$A.get(...)", "request.$A[...]", "flask.request.$A.get(...)", "flask.request.$A[...]", "request.get_json(...)", "flask.request.get_json(...)"], "request reads only: no plain parameters, no input()"
m, b3, e3 = rx(yb, "M")[0], rx(yb, "B")[0], rx(yb, "E")[0]
assert all(re.match(m, s) for s in ("run", "call", "check_call", "check_output", "Popen")), m
assert not any(re.match(m, s) for s in ("getoutput", "check", "run2", "getstatusoutput", "Popener")), m
assert all(re.match(b3, s) for s in ('"git"', "'git'", '"/usr/bin/git"', "'/opt/acme/git'")), b3
assert not any(re.match(b3, s) for s in ('"gitk"', '"git-lfs"', '"echo"', '"/usr/bin/github"', "git", '"git status"')), b3
assert all(re.match(e3, s) for s in ('request.args.get("ref")', 'request.json["branch"]', 'data["branch"]', 'branch.strip()', 'f"{branch}"', 'f"{b}:main"', 'rf"{b}"')), e3
assert not any(re.match(e3, s) for s in ('"clone"', "'origin'", 'f"origin/{branch}"', 'b"x"', 'r"x"', 'u"x"', 'f"{{x}}"', 'F"origin/{b}"')), e3
assert 'subprocess.$M([$B, ..., $E, ...], ...)' in yb and 'pattern-not: subprocess.$M([$B, ..., "--", ..., $E, ...], ...)' in yb and 'pattern-not: subprocess.$M([$B, ..., "--end-of-options", ..., $E, ...], ...)' in yb
pg = re.findall(r"pattern-not-inside: \|\n\s+if (.*):\n\s+\.\.\.\n\s+(return|raise) \.\.\.", yb)
pconds = ('$E.startswith("-")', '<... ($A or $E.startswith("-")) ...>', '<... ($E.startswith("-") or $A) ...>')
assert sorted(pg) == sorted((c, t) for c in pconds for t in ("return", "raise")), "6 guards: 3 conditions, return or raise"
assert "a list built elsewhere" in yb and '(f"--opt={v}") is not reported' in yb
print("ok")
