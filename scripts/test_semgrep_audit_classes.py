#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.raw-sql-concat, perun.py.raw-sql-format, perun.go.raw-sql-sprintf (string-built SQL
passed to a raw query API), perun.js.orm-where-unchecked-input (Prisma where-filter fed from req.body/req.query with no presence
check) and perun.js.guard-allows-missing-token / perun.py.guard-allows-missing-token (auth guard that returns true with no token).

Fixtures use `// ruleid: <id>` / `# ruleid: <id>` (the NEXT line must be a finding) and `// ok: <id>` / `# ok: <id>` (the next line
must stay clean); all names are fictional. RULES=<dir> checks another copy of the rules. Needs semgrep: without it the live check
prints SKIP (REQUIRE_SEMGREP=1 turns that into a failure); the rule-presence asserts always run."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
FWMODS = ["flask", "fastapi", "django", "rest_framework.views", "starlette.routing", "aiohttp", "tornado.web", "sanic", "bottle", "pyramid.view",
          "falcon", "quart", "litestar", "werkzeug.wrappers", "chalice", "cherrypy"]
FWNAMES = ["fw_%s.py" % m.split(".")[0] for m in FWMODS] + ["fw_import_form.py"]
KINDS = {"entry.py": ("ruleid",), "cli.py": ("ok",), "nofw.py": ("ruleid", "ok")}
KINDS.update({k: ("ruleid",) for k in FWNAMES})
IDS = {"js.ts": ["perun.js.raw-sql-concat", "perun.js.orm-where-unchecked-input", "perun.js.guard-allows-missing-token"],
       "app.py": ["perun.py.raw-sql-format", "perun.py.guard-allows-missing-token"], "db.go": ["perun.go.raw-sql-sprintf"],
       "entry.py": ["perun.py." + c for c in "sqli command-injection path-traversal ssrf deserialize ssti xss open-redirect".split()],
       "nofw.py": ["perun.py.path-traversal", "perun.py.deserialize"], **{k: ["perun.py.path-traversal"] for k in FWNAMES},
       "cli.py": ["perun.py." + c for c in "sqli command-injection path-traversal ssrf deserialize ssti xss open-redirect".split()]}

TS = '''
export async function search(req, res) {
  // ruleid: perun.js.raw-sql-concat
  await prisma.$queryRawUnsafe(`SELECT * FROM "Widget" WHERE name = '${req.query.name}'`);
  // ruleid: perun.js.raw-sql-concat
  await prisma.$executeRawUnsafe("DELETE FROM widgets WHERE id = " + req.body.id);
  // ruleid: perun.js.raw-sql-concat
  await knex.raw(`select * from widgets where owner = ${req.body.owner}`);
  // ruleid: perun.js.raw-sql-concat
  await sequelize.query("SELECT * FROM widgets WHERE name = '" + req.query.name + "'");
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ok: perun.js.raw-sql-concat
  await pool.query("SELECT * FROM widgets WHERE id = $1", [req.params.id]);
  // ok: perun.js.raw-sql-concat
  await prisma.$queryRawUnsafe("SELECT * FROM widgets WHERE id = $1", req.params.id);
  // ok: perun.js.raw-sql-concat
  await knex.raw("select * from widgets where owner = ?", [req.body.owner]);
  // ok: perun.js.raw-sql-concat
  await pool.query("SELECT * FROM widgets " + "WHERE id = $1", [req.params.id]);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${req.query.desc ? "name DESC" : "name ASC"}`);
  // ruleid: perun.js.raw-sql-concat
  await this.dataSource.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ruleid: perun.js.raw-sql-concat
  await em.query("SELECT * FROM widgets WHERE id = " + req.params.id);
  // ruleid: perun.js.raw-sql-concat
  await this.repo.manager.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ruleid: perun.js.raw-sql-concat
  await queryRunner.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ruleid: perun.js.raw-sql-concat
  await entityManager.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${(req.query.desc ? "name DESC" : "name ASC")}`);
  // ok: perun.js.raw-sql-concat
  await cache.query(`SELECT ${req.query.name}`);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT ${ROW_COLUMNS} FROM ${TABLE} WHERE id = $1`, [req.params.id]);
  // ok: perun.js.raw-sql-concat
  await prisma.$queryRawUnsafe(`${BASE_SELECT} WHERE owner = $1`, req.body.owner);
}

export async function listSorted(req, values) {
  let query = `SELECT * FROM widgets ORDER BY ${req.query.orderBy}`;
  // ruleid: perun.js.raw-sql-concat
  return await this.prisma.$queryRawUnsafe(query, ...values);
}

export async function listFiltered(req, values) {
  let query = "SELECT * FROM widgets WHERE 1 = 1";
  if (req.query.name) {
    query += ` AND name = '${req.query.name}'`;
  }
  // ruleid: perun.js.raw-sql-concat
  return await pool.query(query, values);
}

export async function listConst(req, values) {
  let query = `SELECT ${ROW_COLUMNS} FROM ${TABLE} WHERE id = $1`;
  // ok: perun.js.raw-sql-concat
  return await this.prisma.$queryRawUnsafe(query, ...values);
}

export async function listTaintedConst(req) {
  const TABLE = req.query.table;
  // tainted: perun.js.sqli
  return await pool.query(`SELECT * FROM ${TABLE}`);
}

export async function login(req, res) {
  // ruleid: perun.js.orm-where-unchecked-input
  const a = await prisma.user.findFirst({ where: { email: req.body.email } });
  // ruleid: perun.js.orm-where-unchecked-input
  const b = await prisma.user.findMany({ where: { email: { equals: req.query.email } } });
}

export async function lookup(req, res) {
  const { email } = req.body;
  // ruleid: perun.js.orm-where-unchecked-input
  const c = await prisma.user.findFirst({ where: { email } });
}

export async function lookupChecked(req, res) {
  const { email } = req.body;
  if (!email) return res.status(400).end();
  // ok: perun.js.orm-where-unchecked-input
  const c = await prisma.user.findFirst({ where: { email } });
}

export async function byId(req, res) {
  // ok: perun.js.orm-where-unchecked-input
  const d = await prisma.user.findUnique({ where: { id: req.params.id } });
  // ok: perun.js.orm-where-unchecked-input
  const e = await prisma.user.findUnique({ where: { email: req.body.email } });
}

class AuthGuard {
  canActivate(ctx) {
    const token = ctx.headers.authorization;
    if (!token) {
      // ruleid: perun.js.guard-allows-missing-token
      return true;
    }
    return verify(token);
  }
}

function requireAuth(req, res, next) {
  const token = req.headers.authorization;
  // ruleid: perun.js.guard-allows-missing-token
  if (!token) return next();
  return verify(token) ? next() : res.status(401).end();
}

function readOnlyGuard(request, res, next) {
  const token = request.headers.authorization;
  // ruleid: perun.js.guard-allows-missing-token
  if (!token && request.method === 'GET') { return true; }
  return verify(token);
}

function loggedGuard(req, res, next) {
  const token = process.env.WIDGET_TOKEN?.trim();
  // ruleid: perun.js.guard-allows-missing-token
  if (!token) {
    logger.warn('no token configured');
    return true;
  }
  return verify(token);
}

function loggedGuardSafe(req, res, next) {
  const token = process.env.WIDGET_TOKEN?.trim();
  // ok: perun.js.guard-allows-missing-token
  if (!token) {
    logger.warn('no token configured');
    return false;
  }
  return verify(token);
}

function sessionAuth(req, res, next) {
  const token = req.headers.authorization;
  // ruleid: perun.js.guard-allows-missing-token
  if (!token) { next(); return; }
  return verify(token) ? next() : res.status(401).end();
}

function strictAuth(req, res, next) {
  const token = req.headers.authorization;
  // ok: perun.js.guard-allows-missing-token
  if (!token && req.method === 'GET') { return res.status(401).end(); }
  return next();
}

class SafeGuard {
  canActivate(ctx) {
    const token = ctx.headers.authorization;
    // ok: perun.js.guard-allows-missing-token
    if (!token) return false;
    return verify(token);
  }
}
'''
# semgrep reports a finding at the matched statement, so the guard fixtures annotate the `if` line; keep both forms honest below.
TS = TS.replace('''    if (!token) {
      // ruleid: perun.js.guard-allows-missing-token
      return true;
    }''', '''    // ruleid: perun.js.guard-allows-missing-token
    if (!token) {
      return true;
    }''')

PY = '''
def run(cur, name, uid):
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets WHERE name = '{name}'")
    # ruleid: perun.py.raw-sql-format
    cur.execute("SELECT * FROM widgets WHERE name = '%s'" % name)
    # ruleid: perun.py.raw-sql-format
    cur.execute("SELECT * FROM widgets WHERE id = {}".format(uid))
    # ruleid: perun.py.raw-sql-format
    cur.execute("SELECT * FROM widgets WHERE name = '" + name + "'")
    # ok: perun.py.raw-sql-format
    cur.execute("SELECT * FROM widgets WHERE name = %s", (name,))
    # ok: perun.py.raw-sql-format
    cur.execute("SELECT * FROM widgets")
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM {TABLE} WHERE id = %s", (uid,))


def run_var(cur, order):
    sql = f"SELECT * FROM widgets ORDER BY {order}"
    # ruleid: perun.py.raw-sql-format
    cur.execute(sql)


def run_var_append(cur, name):
    sql = "SELECT * FROM widgets WHERE 1 = 1"
    sql += f" AND name = '{name}'"
    # ruleid: perun.py.raw-sql-format
    cur.execute(sql)


def run_var_const(cur, uid):
    sql = f"SELECT * FROM {TABLE} WHERE id = %s"
    # ok: perun.py.raw-sql-format
    cur.execute(sql, (uid,))


def run_tainted_const(cur, request):
    TABLE = request.args["t"]
    # tainted: perun.py.sqli
    cur.execute(f"SELECT * FROM {TABLE}")


def check_auth(request):
    token = request.headers.get("Authorization")
    # ruleid: perun.py.guard-allows-missing-token
    if not token:
        return True
    return verify(token)


def check_read_auth(request):
    token = request.headers.get("Authorization")
    # ruleid: perun.py.guard-allows-missing-token
    if not token and request.method == "GET":
        return True
    return verify(token)


def check_read_auth_safe(request):
    token = request.headers.get("Authorization")
    # ok: perun.py.guard-allows-missing-token
    if not token and request.method == "GET":
        return False
    return verify(token)


def check_logged_auth(request):
    token = request.headers.get("Authorization")
    # ruleid: perun.py.guard-allows-missing-token
    if not token:
        log.warning("no token configured")
        return True
    return verify(token)


def check_auth_safe(request):
    token = request.headers.get("Authorization")
    # ok: perun.py.guard-allows-missing-token
    if not token:
        return False
    return verify(token)
'''

GO = '''package db

import "fmt"

func find(db *sql.DB, name string) {
	// ruleid: perun.go.raw-sql-sprintf
	db.Query(fmt.Sprintf("SELECT * FROM widgets WHERE name = '%s'", name))
	// ruleid: perun.go.raw-sql-sprintf
	db.QueryContext(ctx, fmt.Sprintf("SELECT * FROM widgets WHERE name = '%s'", name))
	// ruleid: perun.go.raw-sql-sprintf
	db.Exec("DELETE FROM widgets WHERE name = '" + name + "'")
	// ruleid: perun.go.raw-sql-sprintf
	gdb.Raw(fmt.Sprintf("SELECT * FROM widgets WHERE name = '%s'", name))
	// ruleid: perun.go.raw-sql-sprintf
	gdb.Where("name = '" + name + "'")
	// ok: perun.go.raw-sql-sprintf
	gdb.Where("name = ?", name)
	// ok: perun.go.raw-sql-sprintf
	cache.Get(fmt.Sprintf("widget:%s", name))
	// ok: perun.go.raw-sql-sprintf
	http.Get(baseURL + name)
	// ok: perun.go.raw-sql-sprintf
	db.Query("SELECT * FROM widgets WHERE name = $1", name)
	// ok: perun.go.raw-sql-sprintf
	db.QueryContext(ctx, "SELECT * FROM widgets WHERE name = ?", name)
}

func findVar(db *sql.DB, name string) {
	q := fmt.Sprintf("SELECT * FROM widgets WHERE name = '%s'", name)
	// ruleid: perun.go.raw-sql-sprintf
	db.Query(q)
}

func findVarCtx(db *sql.DB, name string) {
	q := "SELECT * FROM widgets WHERE 1 = 1"
	q += " AND name = '" + name + "'"
	// ruleid: perun.go.raw-sql-sprintf
	db.QueryContext(ctx, q)
}

func findBound(db *sql.DB, name string) {
	q := "SELECT * FROM widgets WHERE name = $1"
	// ok: perun.go.raw-sql-sprintf
	db.Query(q, name)
}
'''
# Migration files are excluded from the SQL-format rules; every line here must stay clean.
MIG = {"migrations/0001_init.py": 'def upgrade(op, TABLE):\n    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN note text")\n    op.get_bind().execute(f"UPDATE widgets SET n = {len(TABLE)}")\n',
       "alembic/versions/a1.py": 'def upgrade(cur, col):\n    cur.execute(f"ALTER TABLE widgets ADD COLUMN {col} text")\n',
       "app/migrations/0002_x.py": 'def upgrade(cur, col):\n    cur.execute(f"ALTER TABLE widgets ADD COLUMN {col} text")\n',
       "db/alembic/versions/b2.py": 'def upgrade(cur, col):\n    cur.execute(f"ALTER TABLE widgets ADD COLUMN {col} text")\n',
       "migrations/001.ts": 'export async function up(pool, col) {\n  await pool.query(`ALTER TABLE widgets ADD COLUMN ${col} text`);\n}\n'}
# Non-migration code that merely sits under a directory named migrations/alembic must still be scanned (a request handler hid there).
NOTMIG = {"src/routes/migrations/run.ts": MIG["migrations/001.ts"], "src/routes/migrations/runner.py": MIG["alembic/versions/a1.py"]}

# Entry-point sources: route-decorated handler params and Django view params are sources; a plain helper/CLI parameter is not.
ENTRY = '''
import os, json, yaml, marshal, pickle, subprocess, requests
from flask import redirect, render_template_string, request
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.safestring import mark_safe
from jinja2 import Template

@app.route("/s/<q>")
def flask_sqli(q):
    # ruleid: perun.py.sqli
    cur.execute("SELECT * FROM widgets WHERE name = '" + q + "'")

@router.post("/c")
async def fastapi_cmd(host):
    # ruleid: perun.py.command-injection
    os.system("ping " + host)

@app.get("/f")
def fastapi_path(name: str):
    # ruleid: perun.py.path-traversal
    return open(name).read()

def django_ssrf(request, target):
    # ruleid: perun.py.ssrf
    return requests.get(target)

class WidgetView(View):
    def post(self, request, blob):
        # ruleid: perun.py.deserialize
        return pickle.loads(blob)

@app.route("/r1", methods=["POST"])
def body_get_data():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.get_data())

@app.route("/r2", methods=["POST"])
def body_data():
    # ruleid: perun.py.deserialize
    return yaml.load(request.data)

@app.route("/r3", methods=["POST"])
def body_stream():
    # ruleid: perun.py.deserialize
    return marshal.loads(request.stream.read())

def django_body(request):
    # ruleid: perun.py.deserialize
    return pickle.loads(request.body)

@router.post("/r5")
async def starlette_body(request):
    # ruleid: perun.py.deserialize
    return pickle.loads(await request.body())

@app.route("/r6", methods=["POST"])
def flask_seeds():
    # ruleid: perun.py.deserialize
    a = pickle.loads(flask.request.get_data())
    # ruleid: perun.py.deserialize
    b = yaml.load(flask.request.data)
    # ruleid: perun.py.deserialize
    return pickle.load(flask.request.stream.read())

@api.route("/t", methods=["POST"])
def flask_ssti(tpl):
    # ruleid: perun.py.ssti
    return Template(tpl).render()

@app.websocket("/w")
async def ws_xss(msg):
    # ruleid: perun.py.xss
    return HttpResponse(mark_safe(msg))

@app.put("/r")
def put_redirect(nxt):
    # ruleid: perun.py.open-redirect
    return redirect(nxt)

def plain_helper_in_framework_module(target):
    # ruleid: perun.py.ssrf
    return requests.get(target)
'''
CLI = '''
import os, json, yaml, pickle, requests
def cli_sqli(cur, q):
    # ok: perun.py.sqli
    cur.execute("SELECT * FROM widgets WHERE name = '" + q + "'")

def cli_cmd(host):
    # ok: perun.py.command-injection
    os.system("ping " + host)

def cli_path(name):
    # ok: perun.py.path-traversal
    return open(name).read()

def cli_ssrf(target):
    # ok: perun.py.ssrf
    return requests.get(target)

def body_clean():
    # ok: perun.py.deserialize
    a = json.loads(request.get_data())
    # ok: perun.py.deserialize
    b = yaml.safe_load(request.data)
    # ok: perun.py.deserialize
    return json.loads(request.stream.read())

def django_body_clean(request):
    # ok: perun.py.deserialize
    return json.loads(request.body)

async def starlette_body_clean(request):
    # ok: perun.py.deserialize
    return json.loads(await request.body())

def cli_deserialize(blob):
    # ok: perun.py.deserialize
    return pickle.loads(blob)

def cli_ssti(tpl):
    # ok: perun.py.ssti
    return Template(tpl).render()

def cli_xss(msg):
    # ok: perun.py.xss
    return HttpResponse(mark_safe(msg))

def cli_redirect(nxt):
    # ok: perun.py.open-redirect
    return redirect(nxt)

def cli_input_path():
    name = input("file? ")
    # ok: perun.py.path-traversal
    return open(name).read()

@app.errorhandler(404)
def not_a_route(e):
    # ok: perun.py.path-traversal
    return open(e).read()
'''
# No framework import anywhere: the entry branches must fire on their own, and a plain helper must not.
NOFW = '''
from pickle import loads

def body_flask():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.get_data())

def body_bare_data():
    # ruleid: perun.py.deserialize
    return yaml.load(request.data)

async def body_aiohttp():
    # ruleid: perun.py.deserialize
    return pickle.loads(await request.read())

async def body_starlette():
    # ruleid: perun.py.deserialize
    return marshal.loads(await request.body())

def body_django():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.body)

def body_clean():
    # ok: perun.py.deserialize
    a = json.loads(request.get_data())
    # ok: perun.py.deserialize
    b = yaml.safe_load(request.data)
    # ok: perun.py.deserialize
    return json.loads(request.body)

def src_get_json():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.get_json(force=True))

def src_json():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.json)

def src_stream():
    # ruleid: perun.py.deserialize
    return pickle.load(request.stream)

def src_post():
    # ruleid: perun.py.deserialize
    return yaml.load(request.POST)

def src_form():
    # ruleid: perun.py.deserialize
    return pickle.loads(request.form)

def src_files():
    # ruleid: perun.py.deserialize
    return pickle.load(request.files)

async def src_await_json():
    # ruleid: perun.py.deserialize
    return pickle.loads(await request.json())

async def src_await_post():
    # ruleid: perun.py.deserialize
    return yaml.load(await request.post())

class Handler:
    def src_self_body(self):
        # ruleid: perun.py.deserialize
        return pickle.loads(self.request.body)

    def src_self_data(self):
        # ruleid: perun.py.deserialize
        return yaml.load(self.request.data)

def src_flask_prefixed():
    # ruleid: perun.py.deserialize
    a = pickle.loads(flask.request.get_json(force=True))
    # ruleid: perun.py.deserialize
    b = pickle.loads(flask.request.json)
    # ruleid: perun.py.deserialize
    c = pickle.loads(flask.request.form)
    # ruleid: perun.py.deserialize
    d = pickle.loads(flask.request.files)
    # ruleid: perun.py.deserialize
    return pickle.load(flask.request.stream)

async def src_intermediate_var():
    d = await request.post()
    # ruleid: perun.py.deserialize
    return pickle.loads(d["x"])

def sink_variants():
    # ruleid: perun.py.deserialize
    a = dill.loads(request.data)
    # ruleid: perun.py.deserialize
    b = dill.load(request.stream)
    # ruleid: perun.py.deserialize
    d = marshal.load(request.stream)
    # ruleid: perun.py.deserialize
    e = pickle.Unpickler(request.stream)
    # ruleid: perun.py.deserialize
    return yaml.load(request.data, Loader=yaml.Loader)

def load_all_and_aliases():
    # ruleid: perun.py.deserialize
    a = yaml.load_all(request.data)
    # ruleid: perun.py.deserialize
    b = yaml.unsafe_load_all(request.data)
    # ruleid: perun.py.deserialize
    c = _pickle.loads(request.data)
    # ruleid: perun.py.deserialize
    d = cPickle.loads(request.data)
    # ruleid: perun.py.deserialize
    e = loads(request.data)
    # ruleid: perun.py.deserialize
    g = yaml.full_load(request.data)
    # ruleid: perun.py.deserialize
    h = yaml.full_load_all(request.data)
    # ok: perun.py.deserialize
    f = yaml.load_all(request.data, Loader=yaml.SafeLoader)
    # ok: perun.py.deserialize
    return yaml.load_all(request.data, yaml.CSafeLoader)

def safe_variants():
    # ok: perun.py.deserialize
    a = yaml.safe_load(request.data)
    # ok: perun.py.deserialize
    b = yaml.load(request.data, yaml.SafeLoader)
    # ok: perun.py.deserialize
    c = yaml.load(request.data, SafeLoader)
    # ok: perun.py.deserialize
    d = yaml.load(request.data, yaml.CSafeLoader)
    # ok: perun.py.deserialize
    return yaml.load(request.data, CSafeLoader)

def yaml_safe_loaders():
    # ok: perun.py.deserialize
    a = yaml.load(request.data, Loader=yaml.SafeLoader)
    # ok: perun.py.deserialize
    b = yaml.load(request.data, Loader=SafeLoader)
    # ok: perun.py.deserialize
    c = yaml.load(request.data, Loader=CSafeLoader)
    # ok: perun.py.deserialize
    return yaml.load(request.data, Loader=yaml.CSafeLoader)

def deserialize_param_not_source(blob):
    # ok: perun.py.deserialize
    return pickle.loads(blob)

def full_load_param_not_source(blob):
    # ok: perun.py.deserialize
    a = yaml.full_load(blob)
    # ok: perun.py.deserialize
    return yaml.full_load_all(blob)

@app.route("/a")
def route_h(p):
    # ruleid: perun.py.path-traversal
    return open(p).read()

@login_required
@app.route("/b")
def stacked_h(p):
    # ruleid: perun.py.path-traversal
    return open(p).read()

async def view_async(request, pk):
    # ruleid: perun.py.path-traversal
    return open(pk).read()

def view_req(req, pk):
    # ruleid: perun.py.path-traversal
    return open(pk).read()

class V:
    async def get(self, request, pk):
        # ruleid: perun.py.path-traversal
        return open(pk).read()

def lambda_handler(event, context):
    # ruleid: perun.py.path-traversal
    return open(event).read()

def wsgi_app(environ, start_response):
    # ruleid: perun.py.path-traversal
    return open(environ).read()

def plain_helper(p):
    # ok: perun.py.path-traversal
    return open(p).read()

def two_arg_helper(a, b):
    # ok: perun.py.path-traversal
    return open(a).read()
'''
# One plain-parameter function per framework import: the module-level source must recognise each name.
FWFILES = {"fw_%s.py" % m.split(".")[0]: "from %s import thing\n\ndef helper(p):\n    # ruleid: perun.py.path-traversal\n    return open(p).read()\n" % m for m in FWMODS}
FWFILES["fw_import_form.py"] = "import flask.views as fv\n\nasync def helper(p):\n    # ruleid: perun.py.path-traversal\n    return open(p).read()\n"

FILES = {"js.ts": TS, "app.py": PY, "db.go": GO, "entry.py": ENTRY, "cli.py": CLI, "nofw.py": NOFW, **FWFILES}


def annotated(body, kind, rid):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*(?://|#) {kind}: {re.escape(rid)}$", l)}


for fn, ids in IDS.items():
    for rid in ids:
        assert all(annotated(FILES[fn], k, rid) for k in KINDS.get(fn, ("ruleid", "ok"))), (fn, rid)
rules = "".join(open(os.path.join(RULES, f)).read() for f in ("js.yml", "py.yml", "go.yml"))
for ids in IDS.values():
    for rid in ids:
        assert f"- id: {rid}\n" in rules, f"rule missing: {rid}"

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for fn, body in {**FILES, **MIG, **NOTMIG}.items():
            os.makedirs(os.path.dirname(os.path.join(d, fn)), exist_ok=True)
            open(os.path.join(d, fn), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "."],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    for fn, ids in IDS.items():
        for rid in ids:
            want = annotated(FILES[fn], "ruleid", rid)
            got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(rid) and x["path"].endswith(fn)}
            assert got == want, (rid, "unexpected", sorted(got - want), "missed", sorted(want - got))
    # name-based UPPER_SNAKE skip must not hide tainted values: another (taint) rule has to report them
    for fn in ("js.ts", "app.py"):
        for m in re.finditer(r"(?://|\#) tainted: (\S+)\n", FILES[fn]):
            ln = FILES[fn][:m.end()].count("\n") + 1
            assert any(x["check_id"].endswith(m.group(1)) and x["path"].endswith(fn) and x["start"]["line"] == ln for x in r["results"]), (fn, ln, m.group(1))
    assert not [x["path"] for x in r["results"] if x["path"] in MIG and re.search(r"raw-sql-(concat|format|sprintf)$", x["check_id"])], [x["path"] for x in r["results"] if x["path"] in MIG and re.search(r"raw-sql-(concat|format|sprintf)$", x["check_id"])]
    hit = {x["path"] for x in r["results"] if re.search(r"raw-sql-(concat|format|sprintf)$", x["check_id"])}
    assert set(NOTMIG) <= hit, ("non-migration files under migrations/ were skipped", sorted(set(NOTMIG) - hit))
    # Handler->helper corpus (rules only). Same-file sinks in a module that imports a web framework are found; a helper in a module
    # with no framework import (helpers_a, helpers_b) is the stated limit. Clean controls: a CLI script has no hit; framework-module
    # helpers that receive only constants are a known false-positive cost of the any-parameter-in-a-framework-module source.
    CORPUS = os.path.join(ROOT, "scripts", "fixtures", "py-helper-corpus")
    ans = json.load(open(os.path.join(CORPUS, "answer.json")))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        cr = json.loads(subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "vuln", "clean"],
                                       capture_output=True, text=True, env=env, cwd=CORPUS).stdout)
    assert not cr["errors"], cr["errors"]
    C8 = re.compile(r"perun\.py\.(sqli|command-injection|path-traversal|ssrf|deserialize|ssti|xss|open-redirect)$")
    rows = [(x["path"], x["start"]["line"], C8.search(x["check_id"]).group(1)) for x in cr["results"] if C8.search(x["check_id"])]
    missed = {k for k, c in ans.items() if not any(f == k.rpartition(":")[0] and abs(l - int(k.rpartition(":")[2])) <= 2 and c == cl for f, l, cl in rows)}
    assert missed == {"vuln/helpers_a.py:5", "vuln/helpers_a.py:8", "vuln/helpers_b.py:5", "vuln/helpers_b.py:9", "vuln/helpers_b.py:12"}, sorted(missed)
    assert not [r for r in rows if r[0] == "clean/cli_tool.py"], rows
    assert len([r for r in rows if r[0].startswith("clean/")]) == 5, [r for r in rows if r[0].startswith("clean/")]
    print("semgrep-audit-classes: helper corpus ok (%d/%d)" % (len(ans) - len(missed), len(ans)))
    # JS prototype-pollution corpus (answer.json = 26 real sinks, clean/ = 10 safe controls). Old rule (for-in `target[key] = v` only, no
    # loop-source, fresh-target or constant-list filter): recall 6/21 and 3 clean hits. New rule must find all 26 and stay quiet on clean/.
    PP = os.path.join(ROOT, "scripts", "fixtures", "js-proto-corpus")
    pans = json.load(open(os.path.join(PP, "answer.json")))
    with tempfile.TemporaryDirectory() as d:  # copied out: the rule skips any path containing a "fixtures" directory
        shutil.copytree(PP, os.path.join(d, "c"))
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        pr = json.loads(subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "vuln", "clean"],
                                       capture_output=True, text=True, env=env, cwd=os.path.join(d, "c")).stdout)
    assert not pr["errors"], pr["errors"]
    prow = {"%s:%d" % (x["path"], x["start"]["line"]) for x in pr["results"] if x["check_id"].endswith("perun.js.prototype-pollution")}
    assert set(pans) <= prow, ("proto corpus missed", sorted(set(pans) - prow))
    assert prow == set(pans), ("proto corpus extra", sorted(prow - set(pans)))
    print("semgrep-audit-classes: js proto corpus ok (%d/%d)" % (len(set(pans) & prow), len(pans)))
    print("semgrep-audit-classes: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-audit-classes: ok")
