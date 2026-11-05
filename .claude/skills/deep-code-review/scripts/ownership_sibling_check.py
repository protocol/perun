#!/usr/bin/env python3
"""ownership_sibling_check.py PATH... -- lead-finder for broken object-level authorization (OWASP API1, CWE-639) by sibling comparison. Report-only, stdlib only.

Read this when you review an API for IDOR / BOLA: a handler that loads a record by an id the client sends, in a file where another
handler loading the same model or store DOES check ownership, is the strongest static signal that the check was forgotten. Run
`python3 -I ownership_sibling_check.py PATH...` (files or directories; test, tests, fixtures, mocks, e2e, node_modules and similar
segments are skipped). SILENCE IS NOT PROOF OF OBJECT-LEVEL AUTHORIZATION: a file with no checking sibling is out of scope by design.

Scope: Express (JS/TS), Flask, FastAPI and Django (incl. DRF class views) handlers. Per handler the scan finds a single-record lookup
(Mongoose / Sequelize / Prisma / TypeORM / knex calls; Django ORM, `get_object_or_404`, Flask-SQLAlchemy / SQLAlchemy `query` / `get` /
`select`; a module-level dict, list or Map used as a store) whose id comes from the client (path / query / body parameter, a handler
parameter, `request.*` / `req.*`, or a local assigned from them). A SIBLING handler of the same file "checks ownership" when it loads
the same model or store with the current user in the lookup (`filter(owner=request.user)`, `{ _id: id, owner: req.user.id }`), or loads
it and compares the record's owner field with the current user. The handler is reported only when it does neither.

Output: one line per finding, `REL/PATH:LINE: OWNERSHIP: <handler> loads <model> by client id; sibling <handler2> checks ownership`, LINE
being the lookup line; exit 0 always (2 on bad usage). Stays silent when the handler itself scopes the lookup, compares an owner, calls a
guard helper (owner / authorize / can_* / policy ...), raises 403, mentions the current user beyond a bare authenticated check, is
guarded by a decorator / `Depends` / route middleware / class-level `get_queryset` or permission whose name says owner or authorize;
when the id is not client-supplied; or when the sibling scopes a different model.

Known limits (NOT covered, so silence proves nothing): lookups hidden in a helper function or service layer (only code inside the
handler is read); a current user derived indirectly (`u = load_session(); ... u.id`) unless the name is user / owner shaped; handlers
registered only through `app.add_url_rule`, `router.register` or a controller class without a `request` parameter; Go / Java / Rails;
raw SQL; GraphQL resolvers; tenant (not owner) scoping, see tenant_scope_check.py. ponytail: text scan, not an AST.
"""
import os
import re
import sys

SKIP_SEG = {"test", "tests", "__tests__", "fixtures", "fixture", "mocks", "mock", "__mocks__", "e2e", "node_modules", "dist", "build",
            ".git", "venv", ".venv", "__pycache__", "site-packages", "migrations", "vendor"}
JS_EXT, PY_EXT = (".js", ".jsx", ".ts", ".mjs", ".cjs"), (".py",)
SKIP_NAME = re.compile(r"(^test_|_test\.py$|^conftest\.py$|\.(test|spec)\.\w+$|\.d\.ts$)")

# The current user: STRONG tokens always count; WEAK bare words count unless the handler takes that name from the client.
STRONG = re.compile(r"(?:self\.)?(?:req|request)\.(?:user|auth|userId|user_id)(?:\.\w+)*|(?:req|request)\.session\.\w+(?:\.\w+)*|\bcurrent_user(?:\.\w+)*|"
                    r"\bg\.user(?:\.\w+)*|res\.locals\.user(?:\.\w+)*|ctx\.state\.user(?:\.\w+)*|\bsession\.user(?:\.\w+)*|get_jwt_identity\(\)|"
                    r"\bget_current_user\w*\(\)?|\bcurrentUser(?:\.\w+)*")
WEAK = ("user", "user_id", "userId", "uid", "owner", "owner_id", "ownerId", "created_by", "createdBy", "author_id", "authorId",
        "tenant_id", "tenantId", "org_id", "orgId", "account_id", "accountId", "team_id", "teamId")
WEAK_RE = re.compile(r"(?<![\w.])(" + "|".join(WEAK) + r")\b")
OWN_ATTR = re.compile(r"\.\s*(?:owner|user|author|creator|created_?by|account|tenant|org|team|member|uid)\w*", re.I)
COMPARE = re.compile(r"[!=]==?|\.equals\(|\bnot in\b|\bis not\b|\bin\b|\.includes\(|\.toString\(\)\s*[!=]")
# A call/decorator/Depends/route-middleware whose NAME says the object owner is checked (a bare "permission" or "login" is not enough).
GUARD = re.compile(r"owner|ownership|owns\b|authori[sz]e|\bcan_?(?:access|edit|view|read|write|delete|update|modify|manage)|policy|has_?access|"
                   r"check_?access|verify_?access|ensure_?access|require_?access|get_?owned|user_passes_test|abilit|object_?permission|"
                   r"Is\w*(?:Author|Creator)\b|belongs_?to", re.I)
GUARD_CALL = re.compile(r"\b\w*(?:" + GUARD.pattern + r")\w*\s*\(", re.I)
DENY = re.compile(r"\b403\b|Forbidden|PermissionDenied|PermissionError")
AUTH_ONLY = re.compile(r"(?:!|\bnot\s)\s*\(?[\w.?]*(?:user|session|auth)\w*\)?\s*(?:[:){]|$)|is_?[Aa]uthenticated|\.isAuthenticated\(")
INFRA = {"self", "cls", "request", "req", "res", "response", "next", "db", "session", "current_user", "user", "background_tasks", "args", "kwargs"}
PY_SRC = r"request\.(?:args|GET|POST|json|form|data|query_params|values|view_args|get_json|body)|kwargs"
JS_SRC = r"req\.(?:params|query|body)"
PY_ROUTE = re.compile(r"@\s*\w+(?:\.\w+)*\.(?:route|get|post|put|patch|delete|api_route)\s*\(|@api_view\b")
PY_CHAIN_ONE = {"get", "first", "last", "one", "one_or_none", "get_or_404", "first_or_404", "scalar"}
JS_FIND = (r"findById|findByPk|findOne|findUnique|findFirst|findUniqueOrThrow|findFirstOrThrow|findOneBy|findOneOrFail|findByIdAndUpdate|"
           r"findByIdAndDelete|findOneAndUpdate|findOneAndDelete|findByIdAndRemove")
MODELISH = r"[A-Z][a-z]\w*"


def mask(s, py):
    """Blank comments (and Python docstrings) keeping offsets and newlines; strings are kept (table names, route paths)."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if py and c == "#" or not py and s.startswith("//", i):
            j = s.find("\n", i); j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif not py and s.startswith("/*", i):
            j = s.find("*/", i + 2); j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", s[i:j])); i = j
        elif py and s.startswith(('"""', "'''"), i):
            q = s[i:i + 3]; j = s.find(q, i + 3); j = n if j < 0 else j + 3
            out.append(q + re.sub(r"[^\n]", " ", s[i + 3:j - 3]) + q if j - i >= 6 else s[i:j]); i = j
        elif c in "\"'`":
            j = skip_str(s, i); out.append(s[i:j]); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def skip_str(s, i):
    q, j = s[i], i + 1
    while j < len(s) and s[j] != q and (q == "`" or s[j] != "\n"):
        j += 2 if s[j] == "\\" else 1
    return min(j + 1, len(s))


def stmt_end(s, i):
    """End offset of the expression statement starting at i: bracket-balanced, continuing across a newline when the next line starts with `.`."""
    d, k, n = 0, i, len(s)
    while k < n:
        c = s[k]
        if c in "\"'`":
            k = skip_str(s, k); continue
        if c in "([{": d += 1
        elif c in ")]}":
            d -= 1
            if d < 0: break
        elif d == 0 and c in "\n;":
            if c == ";" or not re.match(r"\s*\.", s[k + 1:k + 40]): break
        k += 1
    return k


def chain_names(stmt):
    """Method names called at bracket depth 0 of an expression: `a.b(x).first()` -> [b, first]."""
    d, out, k = 0, [], 0
    while k < len(stmt):
        c = stmt[k]
        if c in "\"'`":
            k = skip_str(stmt, k); continue
        if c in "([{": d += 1
        elif c in ")]}": d -= 1
        elif c == "." and d == 0:
            m = re.match(r"\.\s*(\w+)", stmt[k:])
            if m: out.append(m.group(1))
        k += 1
    return out


def close_of(s, i):
    """Offset after the bracket opened at s[i] (string-aware)."""
    d, k = 0, i
    while k < len(s):
        c = s[k]
        if c in "\"'`": k = skip_str(s, k); continue
        if c in "([{": d += 1
        elif c in ")]}":
            d -= 1
            if d == 0: return k + 1
        k += 1
    return len(s)


def norm(m):
    m = m.lower()
    return m[:-1] if m.endswith("s") and len(m) > 3 else m


def lineno(s, i): return s.count("\n", 0, i) + 1


def words(names, text, py):
    """Does text use one of `names` as a value (not as `.attr`, nor as a keyword / object key)?"""
    for w in names:
        for m in re.finditer(r"(?<![\w.])" + re.escape(w) + r"\b(?!\s*=(?!=))" + ("" if py else r"(?!\s*:(?!:))"), text):
            return True
    return False


def cur_hit(text, client):
    return bool(STRONG.search(text)) or any(m.group(1) not in client for m in WEAK_RE.finditer(text))


def own_compare(body, client):
    for ln in body.split("\n"):
        if COMPARE.search(ln) and OWN_ATTR.search(STRONG.sub(" ", ln)) and cur_hit(ln, client): return True
    return False


class H:
    """One handler: name, body text with its offset, decorator/signature/guard context, client-supplied names."""
    def __init__(self, name, start, body, ctx, client, js):
        self.name, self.start, self.body, self.ctx, self.client, self.js = name, start, body, ctx, client, js
        self.lookups = []  # (model, offset, stmt)


def py_handlers(s, stores):
    lines = s.split("\n")
    offs = [0]
    for ln in lines: offs.append(offs[-1] + len(ln) + 1)
    hs = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(", ln)
        if not m: continue
        ind = len(m.group(1))
        j, d = i, 0
        while j < len(lines):  # signature ends at the line closing its brackets and ending in `:`
            d += sum(lines[j].count(c) for c in "([{") - sum(lines[j].count(c) for c in ")]}")
            if d <= 0 and lines[j].rstrip().endswith(":"): break
            j += 1
        sig = "\n".join(lines[i:j + 1])
        e = j + 1
        while e < len(lines) and (not lines[e].strip() or len(lines[e]) - len(lines[e].lstrip()) > ind): e += 1
        deco, k = [], i - 1
        while k >= 0 and (lines[k].lstrip().startswith("@") or lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) > ind
                          or lines[k].lstrip().startswith(")")):
            deco.append(lines[k]); k -= 1
        deco = "\n".join(deco)
        params = split_params(sig[sig.index("(") + 1:sig.rindex(")")] if ")" in sig else "")
        names = [p[0] for p in params]
        first = next((n for n in names if n not in ("self", "cls")), "")
        if not (PY_ROUTE.search(deco) or first in ("request", "req")): continue
        client = {n for n, ann, dflt in params if n not in INFRA and "Request" not in ann and not re.search(r"\b(?:Depends|Security)\(", dflt)}
        body = "\n".join(lines[j + 1:e])
        for a in re.finditer(r"^\s*([\w, ]+?)\s*=\s*(.*)$", body, re.M):
            if re.search(PY_SRC, a.group(2)): client |= {x.strip() for x in a.group(1).split(",") if x.strip().isidentifier()}
        ctx = deco + "\n" + sig + "\n" + class_ctx(lines, i, ind)
        h = H(m.group(2), offs[j + 1], body, ctx, client, False)
        h.sig = sig
        hs.append(h)
    return hs


def split_params(txt):
    out, d, cur = [], 0, ""
    for c in txt + ",":
        if c in "([{": d += 1
        elif c in ")]}": d -= 1
        if c == "," and d == 0:
            p = cur.strip(); cur = ""
            m = re.match(r"\*{0,2}(\w+)\s*(?::\s*([^=]*?))?\s*(?:=\s*(.*))?$", p, re.S)
            if m and not p.startswith("*"): out.append((m.group(1), m.group(2) or "", m.group(3) or ""))
        else: cur += c
    return out


def class_ctx(lines, i, ind):
    """Header + attribute lines + gate-method bodies of the class that contains the def at line i (for DRF / Django class views)."""
    c = i - 1
    while c >= 0 and not (re.match(r"\s*class\s+\w+", lines[c]) and len(lines[c]) - len(lines[c].lstrip()) < ind): c -= 1
    if c < 0 or ind == 0: return ""
    cind = len(lines[c]) - len(lines[c].lstrip())
    out, k, gate = [lines[c]], c + 1, False
    while k < len(lines) and (not lines[k].strip() or len(lines[k]) - len(lines[k].lstrip()) > cind):
        x = lines[k]; xi = len(x) - len(x.lstrip())
        if x.strip() and xi == cind + 4:
            dm = re.match(r"\s*(?:async\s+)?def\s+(\w+)", x)
            gate = bool(dm and re.match(r"get_queryset|get_object|has_object_permission|check_object_permissions|dispatch|test_func|get_permissions", dm.group(1)))
            if not dm: out.append(x)
        if gate or xi == cind + 4 and not x.lstrip().startswith(("def ", "async def ")): out.append(x)
        k += 1
    return "\n".join(out)


def js_handlers(s):
    hs = []
    pats = [r"(?:async\s+)?function\s*(\w*)\s*\(\s*(?:req|request)\b", r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(\s*(?:req|request)\b",
            r"()(?:async\s*)?\(\s*(?:req|request)\b[^)]*\)\s*(?::[^=>{]*)?=>"]
    seen = set()
    for p in pats:
        for m in re.finditer(p, s):
            op = s.rfind("(", m.start(), m.end()) if p.startswith("()") else s.find("(", m.start())
            cl = close_of(s, op)
            b = re.compile(r"\s*(?::[^{=>]*)?(?:=>)?\s*").match(s, cl)
            bs0 = b.end() if b else cl
            body_end = close_of(s, bs0) if s[bs0:bs0 + 1] == "{" else stmt_end(s, bs0)  # block or concise arrow body
            if bs0 in seen: continue
            seen.add(bs0)
            ls = s.rfind("\n", 0, m.start()) + 1
            hdr = s[ls:bs0]
            if m.group(1): name = m.group(1)
            else:
                rm = None
                for rm in re.finditer(r"\.(get|post|put|patch|delete|all|use)\s*\(\s*([`'\"][^`'\"]*[`'\"])", hdr): pass
                name = f"{rm.group(1).upper()} {rm.group(2)[1:-1]}" if rm else f"anonymous@{lineno(s, m.start())}"
            ctx = hdr if not m.group(1) else "\n".join(l for l in s.split("\n") if re.search(r"\b" + re.escape(name) + r"\b", l) and not re.search(r"function\s+" + name + r"\b|(?:const|let|var)\s+" + name + r"\b", l))
            body = s[bs0:body_end]
            client = set()
            for a in re.finditer(r"(?:const|let|var)\s+(\{[^}]*\}|\w+)\s*=\s*([^;\n]*)", body):
                if re.search(JS_SRC, a.group(2)):
                    lhs = a.group(1)
                    if lhs.startswith("{"):
                        for it in lhs[1:-1].split(","):
                            nm = it.split(":")[-1].split("=")[0].strip()
                            if nm.isidentifier(): client.add(nm)
                    else: client.add(lhs)
            hs.append(H(name, bs0, body, ctx, client, True))
    return sorted(hs, key=lambda h: h.start)


def find_lookups(h, py, stores):
    body, base = h.body, h.start
    cands = []
    if py:
        for m in re.finditer(r"\b(" + MODELISH + r")\.(?:objects|query)\b", body): cands.append((m.group(1), m.start(), m.start(), "orm"))
        for m in re.finditer(r"\bget_object_or_404\s*\(\s*(" + MODELISH + r")\b", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"\.get\(\s*(" + MODELISH + r")\s*,", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"\.query\(\s*(" + MODELISH + r")\b", body): cands.append((m.group(1), m.start(), m.start(), "orm"))
        for m in re.finditer(r"\bselect\(\s*(" + MODELISH + r")\b", body):
            if re.search(r"scalar_one|\.scalar\(|\.first\(\)|\.one\(\)|one_or_none", body) and ".all()" not in body:
                cands.append((m.group(1), m.start(), m.start(), "one"))
        for st in stores:
            for m in re.finditer(r"(?<![\w.])" + re.escape(st) + r"(?:\[|\.get\()", body): cands.append((st, m.start(), m.start(), "store"))
    else:
        for m in re.finditer(r"\b(" + MODELISH + r")\.(?:" + JS_FIND + r")\s*\(", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"\b(?:prisma|db|client|tx)\.([a-z]\w*)\.(?:" + JS_FIND + r")\s*\(", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"\b(\w+?)(?:Repo|Repository)\.(?:findOne|findOneBy|findOneOrFail)\s*\(", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"getRepository\(\s*(\w+)\s*\)\.(?:findOne|findOneBy|findOneOrFail)\s*\(", body): cands.append((m.group(1), m.start(), m.start(), "one"))
        for m in re.finditer(r"\b(?:db|knex)\(\s*['\"](\w+)['\"]\s*\)", body): cands.append((m.group(1), m.start(), m.start(), "knex"))
        for st in stores:
            for m in re.finditer(r"(?<![\w.])" + re.escape(st) + r"(?:\[|\.get\(|\.find\()", body): cands.append((st, m.start(), m.start(), "store"))
    for model, off, st0, kind in cands:
        if kind != "store" and kind != "one" and not (set(chain_names(body[st0:stmt_end(body, st0)])) & (PY_CHAIN_ONE if py else {"first"})): continue
        stmt = body[st0:stmt_end(body, st0)]
        if kind == "store" and re.match(r"[^=\n]*\]\s*=(?!=)", body[st0 + len(model):st0 + len(model) + 80]) and "." not in stmt[:len(model) + 1]:
            continue  # store write `STORE[k] = v`
        h.lookups.append((norm(model), base + off, stmt))
    h.lookups.sort(key=lambda x: x[1])


def client_id(h, stmt, py):
    if re.search(PY_SRC if py else JS_SRC, stmt): return True
    return words(h.client, stmt, py)


def scoped(h, stmt): return cur_hit(stmt, h.client)


def checks(h):
    """Models this handler loads under an ownership check: scoped lookup, or any lookup plus an owner-vs-user comparison."""
    out = {m for m, _, st in h.lookups if scoped(h, st)}
    if h.lookups and own_compare(h.body, h.client): out |= {m for m, _, _ in h.lookups}
    return out


def exempt(h, py):
    """The handler itself has some ownership evidence beyond the sibling comparison."""
    if GUARD.search(h.ctx) or GUARD_CALL.search(h.body) or DENY.search(h.body) or own_compare(h.body, h.client): return True
    for ln in h.body.split("\n"):
        if cur_hit(ln, h.client) and not AUTH_ONLY.search(ln): return True
    return False


def stores_of(s, py):
    pat = r"^([A-Za-z_]\w*)\s*(?::[^=\n]+)?=\s*(?:\{|\[|dict\(|list\()" if py else r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=\n]+)?=\s*(?:new\s+Map\b|\{|\[)"
    return set(re.findall(pat, s, re.M))


def scan_file(path, rel):
    py = path.endswith(PY_EXT)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh: raw = fh.read()
    except OSError:
        return []
    if py and not re.search(r"\b(?:flask|fastapi|django|rest_framework|starlette)\b", raw, re.I): return []
    if not py and "express" not in raw: return []
    s = mask(raw, py)
    stores = stores_of(s, py)
    hs = py_handlers(s, stores) if py else js_handlers(s)
    if len(hs) < 2: return []
    for h in hs: find_lookups(h, py, stores)
    out = []
    for h in hs:
        if exempt(h, py) or any(m in checks(h) for m, _, _ in h.lookups): continue
        seen = set()
        for model, off, stmt in h.lookups:
            if model in seen or not client_id(h, stmt, py): continue
            sib = next((o for o in hs if o is not h and model in checks(o)), None)
            if sib is None: continue
            seen.add(model)
            out.append((rel, lineno(s, off), f"{rel}:{lineno(s, off)}: OWNERSHIP: {h.name} loads {model} by client id; sibling {sib.name} checks ownership"))
    return out


def files_of(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for d, ds, fs in os.walk(p):
            ds[:] = sorted(x for x in ds if x not in SKIP_SEG)
            for f in sorted(fs):
                if f.endswith(PY_EXT + JS_EXT) and not SKIP_NAME.search(f): yield os.path.join(d, f)


def main(argv):
    if len(argv) < 2 or any(not os.path.exists(a) for a in argv[1:]):
        print("usage: ownership_sibling_check.py PATH...", file=sys.stderr); return 2
    seen, n = set(), 0
    for f in files_of(argv[1:]):
        rel = os.path.relpath(f)
        if rel.startswith(".."): rel = os.path.abspath(f)
        if f in seen: continue
        seen.add(f)
        for _, _, line in scan_file(f, rel):
            print(line); n += 1
    print(f"heuristic; scanned {len(seen)} files; silence is not proof of object-level authorization", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
