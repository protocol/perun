#!/usr/bin/env python3
"""Tests for the allow-list skips in perun.js.raw-sql-concat and perun.py.raw-sql-format: an interpolated value that passed a
constant Set/array membership check that exits (or wraps the query), or came from a helper in the same file that can only return
literals (a constant-map lookup with a literal fallback), is not reported; unchecked request input, and a check on a different
variable, still are. Fixtures use `// ruleid:` / `// ok:` and `# ruleid:` / `# ok:` (the NEXT line must / must not be a finding);
names are fictional. RULES=<dir|file> checks another copy. Without semgrep this prints SKIP."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
CASES = {
    "app.ts": ("js.yml", "perun.js.raw-sql-concat", r"^\s*//\s*(ruleid|ok):", '''
const ALLOWED_COLS = new Set(["name", "created_at"]);
const ALLOWED_DIRS = ["asc", "desc"];
const SORT = { name: "name", date: "created_at" };
function pickSortColumn(input) { return SORT[input] ?? "created_at"; }
export async function list(req, pool, col, dir, other) {
  if (!ALLOWED_COLS.has(col)) throw new Error("bad column");
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
  if (!ALLOWED_DIRS.includes(dir)) { throw new Error("bad dir"); }
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY name ${dir}`);
}
export async function wrapped(req, pool, col) {
  if (ALLOWED_COLS.has(col)) {
    // ok: perun.js.raw-sql-concat
    await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
  }
}
export async function viaHelper(req, pool, input) {
  const col = pickSortColumn(input);
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function viaVariable(req, pool, col) {
  if (!ALLOWED_COLS.has(col)) return;
  const q = `SELECT * FROM widgets ORDER BY ${col}`;
  // ok: perun.js.raw-sql-concat
  await pool.query(q);
}
function pickRaw(d, k) { return d[k] ?? "created_at"; }
export async function helperReturnsInput(req, pool, d, k) {
  const col = pickRaw(d, k);
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function requestDerivedSet(req, pool, col) {
  const allowed = new Set(req.query.list);
  if (!allowed.has(col)) throw new Error("bad");
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function requestDerivedList(req, pool, col) {
  if (!req.query.list.includes(col)) throw new Error("bad");
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function reassigned(req, pool, col) {
  if (!ALLOWED_COLS.has(col)) throw new Error("bad");
  col = req.query.sort;
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function reassignedHelper(req, pool, input) {
  let col = pickSortColumn(input);
  col += req.query.sort;
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function conditionalExit(req, pool, col, strict) {
  if (!ALLOWED_COLS.has(col)) { if (strict) { throw new Error("bad"); } }
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function logOnly(req, pool, col) {
  if (!ALLOWED_COLS.has(col)) { console.warn("bad column"); }
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function elseBranch(req, pool, col) {
  if (ALLOWED_COLS.has(col)) {
    return null;
  } else {
    // ruleid: perun.js.raw-sql-concat
    await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
  }
}
export async function logThenThrow(req, pool, col) {
  if (!ALLOWED_COLS.has(col)) { console.warn("bad column"); throw new Error("bad"); }
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function reassignedBeforeCheck(req, pool, col) {
  col = String(col).trim();
  if (!ALLOWED_COLS.has(col)) throw new Error("bad");
  // ok: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function otherVariable(req, pool, col, other) {
  if (!ALLOWED_COLS.has(other)) throw new Error("bad");
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${col}`);
}
export async function unchecked(req, pool) {
  // ruleid: perun.js.raw-sql-concat
  await pool.query(`SELECT * FROM widgets ORDER BY ${req.query.sort}`);
}
export async function uncheckedVariable(req, pool) {
  const col = req.query.sort;
  const q = `SELECT * FROM widgets ORDER BY ${col}`;
  // ruleid: perun.js.raw-sql-concat
  await pool.query(q);
}
'''),
    "app.py": ("py.yml", "perun.py.raw-sql-format", r"^\s*#\s*(ruleid|ok):", '''
ALLOWED_COLS = {"name", "created_at"}
SORT = {"name": "name", "date": "created_at"}


def pick_sort_column(value):
    return SORT.get(value, "created_at")


def pick_strict(value):
    return SORT[value]


def raising(cur, col):
    if col not in ALLOWED_COLS:
        raise ValueError("bad")
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def asserting(cur, col):
    assert col in ALLOWED_COLS  # python -O strips this check, so it does not allow-list col
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def wrapped(cur, col):
    if col in ALLOWED_COLS:
        # ok: perun.py.raw-sql-format
        cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def via_helper(cur, value):
    col = pick_sort_column(value)
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def via_strict_helper(cur, value):
    col = pick_strict(value)
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def via_variable(cur, col):
    if col not in ALLOWED_COLS:
        return None
    q = f"SELECT * FROM widgets ORDER BY {col}"
    # ok: perun.py.raw-sql-format
    cur.execute(q)


def pick_raw(d, k):
    return d.get(k, "created_at")


def pick_raw_index(d, k):
    return d[k]


def helper_returns_input(cur, d, k):
    col = pick_raw(d, k)
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def helper_returns_input_index(cur, d, k):
    col = pick_raw_index(d, k)
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def request_derived_list(cur, col, request):
    allowed = request.args.getlist("cols")
    if col not in allowed:
        raise ValueError("bad")
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def request_derived_attr(cur, col, request):
    if col not in request.args.getlist("cols"):
        raise ValueError("bad")
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def reassigned(cur, col, request):
    if col not in ALLOWED_COLS:
        raise ValueError("bad")
    col = request.args["sort"]
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def reassigned_helper(cur, value, request):
    col = pick_sort_column(value)
    col += request.args["sort"]
    q = f"SELECT * FROM widgets ORDER BY {col}"
    # ruleid: perun.py.raw-sql-format
    cur.execute(q)


def conditional_exit(cur, col, strict):
    if col not in ALLOWED_COLS:
        if strict:
            raise ValueError("bad")
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def log_only(cur, col):
    if col not in ALLOWED_COLS:
        print("bad column")
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def else_branch(cur, col):
    if col in ALLOWED_COLS:
        return None
    else:
        # ruleid: perun.py.raw-sql-format
        cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def log_then_raise(cur, col):
    if col not in ALLOWED_COLS:
        print("bad column")
        raise ValueError("bad")
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def reassigned_before_check(cur, col):
    col = str(col).strip()
    if col not in ALLOWED_COLS:
        raise ValueError("bad")
    # ok: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def other_variable(cur, col, other):
    if other not in ALLOWED_COLS:
        raise ValueError("bad")
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")


def unchecked(cur, request):
    # ruleid: perun.py.raw-sql-format
    cur.execute(f"SELECT * FROM widgets ORDER BY {request.args['sort']}")


def unchecked_variable(cur, request):
    col = request.args["sort"]
    q = f"SELECT * FROM widgets ORDER BY {col}"
    # ruleid: perun.py.raw-sql-format
    cur.execute(q)
'''),
}
if not shutil.which("semgrep"):
    if os.environ.get("REQUIRE_SEMGREP") == "1":
        sys.exit("FAIL: semgrep not installed but REQUIRE_SEMGREP=1, so the live check cannot be skipped")
    print("SKIP: semgrep not installed; the allow-list fixtures did not run")
    raise SystemExit(0)
for name, (yml, rid, ann, src) in CASES.items():
    rx = re.compile(ann + r"\s*(\S+)\s*$")
    lines = src.split("\n")
    want = {i for i, l in enumerate(lines, 2) if (m := rx.match(l)) and m.group(1) == "ruleid"}
    assert want and any("ok:" in l for l in lines)
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, name), "w").write(src)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        rules = RULES if os.path.isfile(RULES) else os.path.join(RULES, yml)
        run = subprocess.run(["semgrep", "--config", rules, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", name],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(rid)}
    assert got == want, (name, "unexpected", sorted(got - want), "missed", sorted(want - got))
print("ok")
