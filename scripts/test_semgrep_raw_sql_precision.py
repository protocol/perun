#!/usr/bin/env python3
"""Tests for the perun.js.raw-sql-concat precision skips: interpolations that build bind-parameter indexes ($N placeholders:
params.length, n + 1, i * 2 + 1, args.push(x)), a quoted identifier (ident()/quoteIdent()) or a map-to-$N-placeholders .join()
are not reported, while a value spliced into the SQL text still is. Fixtures use `// ruleid:` / `// ok:` (the NEXT line must / must not
be a finding); all names are fictional. RULES=<dir|file> checks another copy. Without semgrep the live part prints SKIP and the
offline regex check still runs."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.js.raw-sql-concat"
TS = '''
export async function search(req, pool, db, items, from, n) {
  const params = [];
  const args = [req.body.id];
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE id = $${params.length}`, params);
  // ok: perun.js.raw-sql-concat
  await pool.query(`UPDATE widgets SET a = $1 WHERE id = $${n + 1} AND b = $${n * 2 + 2}`, params);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE owner = $${args.push(req.body.owner)}`, args);
  // ok: perun.js.raw-sql-concat
  await db.query(`SELECT count(*) FROM ${ident(req.query.table)}`);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE state IN (${from.map((_, i) => `$${n + 3 + i}`).join(", ")})`, params);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ${whereSql}`, params);
  // ok: perun.js.raw-sql-concat
  await pool.query(`UPDATE widgets SET ${sets.join(", ")}, n = $${params.length} WHERE id = $1`, params);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE id = ${req.params.id}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${req.query.orderBy}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE ${userFilter.name}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE id = ${req.params.id + 1}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE id = ${req.params.id.slice(1)}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets WHERE state IN (${from.map((s) => `'${s}'`).join(", ")})`);
  // ruleid: perun.js.raw-sql-concat
  await db.query(`SELECT * FROM widgets ORDER BY ${req.query.sort}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY name ${order}`);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets LIMIT ${limit}`);
}
'''
ANN = re.compile(r"^\s*//\s*(ruleid|ok):\s*(\S+)\s*$")
want = {i + 1 for i, l in enumerate(TS.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == "ruleid"}
assert want and any("// ok:" in l for l in TS.split("\n"))
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.ts"), "w").write(TS)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.ts"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline regex check below does")
# Offline: the interpolation regex ($X) in both query shapes skips the safe forms and keeps the data forms (semgrep anchors at the start, like re.match).
SRC = open(RULES if os.path.isfile(RULES) else os.path.join(RULES, "js.yml")).read()
blk = SRC.split(f"- id: {ID}\n")[1].split("\n- id:")[0]
rxs = re.findall(r"metavariable: \$X\n\s+regex: '(.*)'", blk)
assert len(rxs) == 2 and rxs[0] == rxs[1], "direct and variable shapes share one $X regex"
rx = re.compile(rxs[0].replace("''", "'"))
for safe in ("params.length", "n + 1", "i * 2 + 1", "HISTORY_PAGE + 1", "args.push(opts.company_id)", "ident(table)",
             "pg.escapeIdentifier(name)", 'from.map((_, i) => `$${n + 3 + i}`).join(", ")', "TABLE", "123", "whereSql", "idClause", "tuples", 'sets.join(", ")'):
    assert not rx.match(safe), safe
for data in ("req.params.id", "req.params.id + 1", "name", "name + id", "items.map((s) => `'${s}'`).join(', ')", "ident(a) + b", "req.query.orderBy", "req.limit", "userFilter.name", "tableName", "orderBy", "order", "limit", "offset"):
    assert rx.match(data), data
print("ok")
