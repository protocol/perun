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
IDS = {"js.ts": ["perun.js.raw-sql-concat", "perun.js.orm-where-unchecked-input", "perun.js.guard-allows-missing-token"],
       "app.py": ["perun.py.raw-sql-format", "perun.py.guard-allows-missing-token"], "db.go": ["perun.go.raw-sql-sprintf"]}

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
'''
FILES = {"js.ts": TS, "app.py": PY, "db.go": GO}


def annotated(body, kind, rid):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*(?://|#) {kind}: {re.escape(rid)}$", l)}


for fn, ids in IDS.items():
    for rid in ids:
        assert annotated(FILES[fn], "ruleid", rid) and annotated(FILES[fn], "ok", rid), rid
rules = "".join(open(os.path.join(RULES, f)).read() for f in ("js.yml", "py.yml", "go.yml"))
for ids in IDS.values():
    for rid in ids:
        assert f"- id: {rid}\n" in rules, f"rule missing: {rid}"

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for fn, body in FILES.items():
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
    print("semgrep-audit-classes: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-audit-classes: ok")
