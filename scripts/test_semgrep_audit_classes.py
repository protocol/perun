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
       "nofw.py": ["perun.py.path-traversal"], **{k: ["perun.py.path-traversal"] for k in FWNAMES},
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
import os, pickle, subprocess, requests
from flask import redirect, render_template_string
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
import os, pickle, requests
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
    print("semgrep-audit-classes: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-audit-classes: ok")
