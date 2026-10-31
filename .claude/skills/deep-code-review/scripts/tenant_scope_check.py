#!/usr/bin/env python3
"""tenant_scope_check.py DIR -- heuristic lead-finder for cross-tenant authz holes in Prisma server code (report-only, stdlib only).

Read this when a repo has a Prisma schema with workspaceId/orgId/tenantId/teamId models: a server action
that finds, updates or deletes a tenant row by `id` alone lets one tenant touch another tenant's data, and
generic linters do not see it. Run `python3 -I tenant_scope_check.py DIR`. A hit is a lead to verify, and
SILENCE IS NOT PROOF OF TENANT ISOLATION: the scan only sees the call shapes listed below.

1. Parse every *.prisma under DIR. A model is TENANT-SCOPED when it has a field named in SCOPE_FIELDS.
2. In server files (SERVER_GLOBS) find `<client>.<model>.(CALLS)(...)` on a tenant-scoped model whose
   top-level `where: {...}` has `id` but no scope -> HIGH.
3. A model with NO scope field that owns a singular `@relation(fields:...)` to a tenant-scoped model or tenant root
   (Workspace, Org, ...) and is called with a CALLS method in a server file -> MED (scope via a parent relation if present).

Scope guard: the scope field must be a TOP-LEVEL key of `where` (bare, quoted `"workspaceId":` or computed
`["workspaceId"]:`), part of a compound key such as `id_workspaceId`, or a top-level key inside a top-level `AND`. Mere
text (`id: input.workspaceId`) or a scope under `OR`/`NOT` does not count. Also not flagged: the matching relation key
(`workspace:`) is in `where`; `where` is a variable, spread or absent (cannot be judged); the model is global; the text
is in a comment or string; the call line or the line above carries `tenant-scope-ok`; node_modules/build dirs, test files.

Known limits (NOT covered, so silence proves nothing): a client that is aliased, awaited or optional-chained
(`(await getDb()).m`, `db?.m`, `const { m } = db`), scoped-extension clients (`scopedDb.m`, which may or may not scope);
`where` built from a variable; methods outside CALLS (findMany, count, aggregate, groupBy, create, raw SQL); template-literal
or computed-method calls; files outside SERVER_GLOBS. `{id, userId}` ownership scoping is NOT recognized as tenant scope, so
such a call is flagged as a lead, and is not a guarantee either way. Chains deeper than one relation hop are not followed.

Output: one `path:line: SEV: message` per finding, then one JSON summary line (with `server_files`), and a stderr line
`heuristic; scanned N server files`. Exit 0 always on a readable DIR (report-only: never fails a build on its own), 2 on
usage error. Reads files only; writes nothing.
ponytail: text scan, not an AST -- regex literals with quotes or a backtick inside a `${}` can desync the masker.
Upgrade to a TS parser if precision matters more.
"""
import json, os, re, sys

SCOPE_FIELDS = ("workspaceId", "orgId", "tenantId", "teamId")  # configurable: a model with any of these is tenant-scoped
SERVER_GLOBS = ("app/**/actions.ts", "app/**/actions.tsx", "app/**/actions.js", "app/api/**", "server/**", "*.server.ts")
CALLS = ("findUnique", "findUniqueOrThrow", "findFirst", "findFirstOrThrow", "update", "updateMany", "upsert", "delete", "deleteMany")
ROOTS = {f[:-2].capitalize() for f in SCOPE_FIELDS} | {"Organization"}  # Workspace, Org, Tenant, Team, Organization
CODE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs")
SKIP_DIR = {"node_modules", ".git", "dist", "build", ".next", "vendor", ".venv", "__pycache__", "coverage"}
SUPPRESS = "tenant-scope-ok"


def glob_re(g):
    r = re.escape(g).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile(r"(?:^|.*/)" + r + "$")


SERVER_RE = [glob_re(g) for g in SERVER_GLOBS]


def mask(s, keep=False):
    """Same length/newlines as s, but comments and string contents blanked (quotes kept); keep=True leaves string contents."""
    o, i, n, q = list(s), 0, len(s), None
    def blank(a, b, text=False):
        if text and keep: return
        for k in range(a, min(b, n)):  # a backslash ending the text inside a string has no character to escape
            if o[k] != "\n": o[k] = " "
    while i < n:
        c = s[i]
        if q:
            if c == "\n" and q != "`": q = None  # ' and " strings cannot span lines: resync after a stray apostrophe
            elif c == "\\": blank(i, i + 2, True); i += 2; continue
            elif c == q: q = None
            else: blank(i, i + 1, True)
        elif s.startswith("//", i):
            j = s.find("\n", i); j = n if j < 0 else j; blank(i, j); i = j; continue
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2); j = n if j < 0 else j + 2; blank(i, j); i = j; continue
        elif c in "'\"`": q = c
        i += 1
    return "".join(o)


def close_of(m, i):
    """Index of the bracket closing the one at m[i], or -1."""
    d = 0
    for k in range(i, len(m)):
        if m[k] in "([{": d += 1
        elif m[k] in ")]}":
            d -= 1
            if d == 0: return k
    return -1


KEY = re.compile(r"""(?:(\w+)|(["'])(\w+)\2|\[\s*(["'`])(\w+)\4\s*\])\s*(?::|$)""")


def parts(m, k):
    """Depth-0 comma segments [(masked, text)] of a body (m: structure, k: same text with strings kept); None on a spread."""
    out, d, s = [], 0, 0
    for i, c in enumerate(m + ","):
        if c in "([{": d += 1
        elif c in ")]}": d -= 1
        elif c == "," and d == 0:
            out.append((m[s:i], k[s:i])); s = i + 1
    return None if any(x[0].strip().startswith("...") for x in out) else out


def analyze(m, k, sf, rels):
    """(top-level keys, scoped?) of an object body; keys None when it holds a spread (cannot be judged)."""
    ps = parts(m, k)
    if ps is None: return None, True
    keys, scoped = set(), False
    for ms, ks in ps:
        ms, ks = ms.lstrip(), ks.lstrip()
        mt = KEY.match(ks)
        if not mt: continue
        key = mt.group(1) or mt.group(3) or mt.group(5)
        keys.add(key)
        if key in rels or any(x in sf for x in key.split("_")): scoped = True
        elif key == "AND":
            mv, kv = ms[mt.end():].strip(), ks[mt.end():].strip()
            if mv[:1] == "[" and mv[-1:] == "]": items = parts(mv[1:-1], kv[1:-1])
            else: items = [(mv, kv)]
            if items is None: scoped = True  # spread inside AND: cannot be judged
            else:
                for im, ik in items:
                    im, ik = im.strip(), ik.strip()
                    if im[:1] == "{" and im[-1:] == "}" and analyze(im[1:-1], ik[1:-1], sf, rels)[1]: scoped = True
    return keys, scoped


def parse_models(root):
    """{model: {"scope": [fields], "roots": [relation targets owned via FK]}} over every *.prisma."""
    models = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIR]
        for f in fn:
            if not f.endswith(".prisma"): continue
            txt = re.sub(r"//[^\n]*", "", open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
            for mt in re.finditer(r"\bmodel\s+(\w+)\s*\{(.*?)\n\s*\}", txt, re.S):
                scope, rels = [], []
                for ln in mt.group(2).splitlines():
                    t = ln.split()
                    if len(t) < 2 or t[0].startswith("@"): continue
                    if t[0] in SCOPE_FIELDS: scope.append(t[0])
                    if "@relation(" in ln and "fields:" in ln and not t[1].endswith("[]"): rels.append(t[1].rstrip("?"))
                models[mt.group(1)] = {"scope": scope, "rels": rels}
    return models


def lower1(n): return n[0].lower() + n[1:]


def lineno(s, i): return s.count("\n", 0, i) + 1


def scan(root):
    models = parse_models(root)
    tenant = {lower1(n): v["scope"] for n, v in models.items() if v["scope"]}
    parents = ROOTS | {n for n, v in models.items() if v["scope"]}
    unkeyed = {lower1(n): n for n, v in models.items() if not v["scope"] and n not in ROOTS and any(r in parents for r in v["rels"])}
    out, files = [], 0
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIR)
        for f in sorted(fn):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            if not f.endswith(CODE_EXT) or re.search(r"\.(test|spec)\.", f) or not any(r.match(rel) for r in SERVER_RE): continue
            raw = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
            m, mk, rl, seen = mask(raw), mask(raw, True), raw.splitlines(), set()
            files += 1
            for mt in re.finditer(r"\b\w+\.(\w+)\.(\w+)\s*\(", m):
                acc, meth = mt.group(1), mt.group(2)
                ln = lineno(m, mt.start(1))
                if any(SUPPRESS in l for l in rl[max(0, ln - 2):ln]): continue
                if acc in unkeyed and meth in CALLS and (acc, rel) not in seen:
                    seen.add((acc, rel))
                    out.append((rel, ln, "MED", f"model missing tenant key: {unkeyed[acc]} links to a tenant model but has none of {'/'.join(SCOPE_FIELDS)}; scope via a parent relation if present"))
                if acc not in tenant or meth not in CALLS: continue
                op = mt.end() - 1; cl = close_of(m, op)
                if cl < 0: continue
                args, kargs = m[op + 1:cl], mk[op + 1:cl]
                for w in re.finditer(r"\bwhere\s*:\s*\{", args):
                    if sum(args[:w.start()].count(c) for c in "([{") - sum(args[:w.start()].count(c) for c in ")]}") != 1: continue  # not the call's own where
                    bo = w.end() - 1; bc = close_of(args, bo)
                    if bc < 0: continue
                    sf = tenant[acc]
                    keys, scoped = analyze(args[bo + 1:bc], kargs[bo + 1:bc], sf, {x[:-2] for x in sf})
                    if keys is None or "id" not in keys or scoped: continue
                    out.append((rel, ln, "HIGH", f"unscoped tenant access: db.{acc}.{meth} where has id but not {'/'.join(sf)}"))
                    break
    return sorted(set(out)), sorted(tenant), files


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: tenant_scope_check.py DIR", file=sys.stderr); return 2
    found, tm, files = scan(argv[1])
    print(f"heuristic; scanned {files} server files", file=sys.stderr)
    for p, l, s, msg in found: print(f"{p}:{l}: {s}: {msg}")
    print(json.dumps({"tool": "tenant_scope_check", "tenant_models": tm, "server_files": files,
                      "high": sum(f[2] == "HIGH" for f in found), "med": sum(f[2] == "MED" for f in found),
                      "findings": [{"file": p, "line": l, "severity": s, "message": m} for p, l, s, m in found]}))
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
