#!/usr/bin/env python3
"""csrf_cookie_map.py DIR -- heuristic lead-finder for cookie-session handlers with no CSRF defence and session cookies set without Secure, HttpOnly or SameSite (CWE-352/614/1004/1275). Report-only, stdlib only.

Usage: python3 -I csrf_cookie_map.py DIR

Read this when you review a cookie-session web app: a browser sends the session cookie on a cross-site form post, so a state-changing handler with no anti-forgery token, Origin check or
SameSite protection acts for whoever the victim is logged in as, and a session cookie without Secure/HttpOnly/SameSite leaks to plain HTTP, to script, or to cross-site requests.
A row is a lead, never a finding, and SILENCE IS NOT PROOF: a gateway, a framework default or a flag set in app config may cover what this scan cannot see.

Rows are `file<TAB>line<TAB>rule<TAB>message`; stderr gets one summary line.
- `missing-csrf-protection`: a POST/PUT/PATCH/DELETE handler (route_auth_map.py inventory via attempt_limit_map.units: Express/Next/Flask/FastAPI, Go, Spring, Django) in a file that reads or sets a session
  cookie (or uses a login/session decorator) whose own text shows no CSRF defence. Reported at the handler's last statement, where the change is committed. Defence = `csrf`/`xsrf` or a
  `Sec-Fetch-Site`/`Origin`/`Referer` header COMPARED in the handler (a bare read is not a defence), a repo-wide CSRF layer named anywhere under DIR (Django `CsrfViewMiddleware`, csurf,
  csrf-csrf, lusca, `CSRFProtect`, nosurf, gorilla/csrf, a Spring `SecurityFilterChain`) unless the repo disables it (`csrf().disable()`, `csrf(c -> c.disable())`,
  `csrf(AbstractHttpConfigurer::disable)`; the disable wins whatever the file order), or any SameSite=Strict/Lax cookie in the repo. Django `@csrf_exempt` removes the layer cover from the handler
  and, on a view with no method check, makes it a POST. Only a session-named cookie (or a session read) makes a handler or its path realm cookie-session; a `theme` cookie does not. Login, signup, register, webhook, callback and oauth routes are skipped.
- `missing-cookie-flags`: a cookie that looks like a session/auth cookie (name has sess, sid, auth, token, jwt, login, admin, remember or user, or is not a literal) set by Go `http.Cookie{...}`,
  Express `res.cookie(...)`, Flask/Django `set_cookie(...)`, Java `new Cookie(...)` + `addCookie` or `ResponseCookie`, or a `Set-Cookie` header string, that lacks one of Secure, HttpOnly, SameSite.
  Reported at the call (Java: the `addCookie` line). Expiry cookies (max-age 0, empty value), csrf/xsrf-named cookies, and cookies whose options argument is a bare identifier or a spread are skipped.

ponytail: file-level cookie evidence and repo-wide CSRF evidence (one csurf line anywhere clears every handler); flags are read from the call's own text, so a flag set by app config
(`SESSION_COOKIE_SECURE`, `server.servlet.session.cookie.*`) reads as missing. Upgrade to per-framework parsing if precision matters more.
"""
import os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attempt_limit_map import PRUNE, shown, units, walk  # noqa: E402
from route_auth_map import pymask, read  # noqa: E402
from tenant_scope_check import mask  # noqa: E402

STATE = {"POST", "PUT", "PATCH", "DELETE"}
SESSION = re.compile(r"\b(?:r|req|request)\.Cookie\(|\bcookies\(\)|\b(?:req|request)\.cookies\b|@CookieValue"
                     r"|\bsession\[|\bsession\.get\(|\brequest\.session\b|\breq\.session\b|\bgetSession\(|\bHttpSession\b")
DEFENCE = re.compile(r"csrf|xsrf", re.I)
HDR = re.compile(r"sec-fetch-site|\borigin\b|\breferer\b", re.I)
CMP = re.compile(r"===?|!==?|\bin\b|startswith|endswith|\.includes\(|\.has\(|\.equals\(|\.indexOf\(|\.test\(|\.match\(|compare", re.I)
SAMESITE = re.compile(r"same_?site[\"'`\s:=(.]{0,6}(?:strict|lax)\b", re.I)
NOVALUE = re.compile(r"(?:[!=]=+|\bis(?:\s+not)?)\s*(?:undefined|null|None|nil)\b|\b(?:undefined|null|None|nil)\s*[!=]=+")
DISABLE = re.compile(r"csrf\s*\(\s*\)\s*\.\s*disable|csrf\.disable|csrf\s*\(\s*\w+\s*->\s*\w+\s*\.\s*disable\s*\(|csrf\s*\(\s*AbstractHttpConfigurer::disable")
NAME = re.compile(r"""(?:Name\s*:|\(\s*|Set-Cookie["'`]?\s*[:,]\s*)["'`]([^"'`=;$]*)""")
GLOBAL = re.compile(r"CsrfViewMiddleware|\bcsurf\b|csrf-csrf|\blusca\b|CSRFProtect|\bnosurf\b|gorilla/csrf|SecurityFilterChain|\bcsrf_protect\b")
EXEMPT = re.compile(r"@csrf_exempt\b|@csrf\.exempt\b|\bcsrf\s*\(\s*\)\s*\.\s*disable\b|\bcsrf\.disable\b")
PUBLIC = re.compile(r"login|signin|sign-in|signup|sign-up|register|webhook|callback|oauth|logout", re.I)
SESSNAME = re.compile(r"sess|sid|auth|token|jwt|login|admin|remember|user", re.I)
EXPIRY = re.compile(r"""max_?age\s*[:=]\s*-?0\b|MaxAge\s*[:=]\s*-\d|expires\s*[:=]\s*(?:0\b|new Date\(0\))|Max-Age=0|\bsetMaxAge\(\s*(?:0|-\d+)\s*\)""", re.I)
FLAGS = (("Secure", r"secure"), ("HttpOnly", r"http_?only"), ("SameSite", r"same_?site"))
GOCOOKIE = re.compile(r"http\.Cookie\s*\{")
EXPRESS = re.compile(r"\bres\.cookie\(")
PYSET = re.compile(r"\bset_cookie\(")
HEADER = re.compile(r"""["'`]Set-Cookie["'`]|\bSet-Cookie\s*:""", re.I)
JNEW = re.compile(r"\b(\w+)\s*=\s*new\s+Cookie\(")
JADD = re.compile(r"\baddCookie\(\s*(\w+)\s*\)")
RESP = re.compile(r"ResponseCookie\s*\.\s*from\(")


def call_text(t, i):
    """Text of the call or literal opened by the first ( or { at or after offset i of t, brackets balanced (strings are kept in the masked text)."""
    n = len(t)
    while i < n and t[i] not in "({": i += 1
    d, j = 0, i
    while j < n:
        d += t[j] in "({"; d -= t[j] in ")}"
        j += 1
        if d == 0: break
    return t[i:j]


def line_of(t, off):
    """1-based line of offset off in t."""
    return t.count("\n", 0, off) + 1


def args(call):
    """Top-level comma-separated arguments of the bracketed call text."""
    out, d, cur = [], 0, ""
    for c in call[1:-1] if call[-1:] in ")}" else call[1:]:
        d += c in "({["; d -= c in ")}]"
        if c == "," and d == 0: out.append(cur); cur = ""
        else: cur += c
    return out + [cur]


def sessionish(body):
    """True if body reads session state or sets a cookie that is not named csrf/xsrf and is session-named or dynamically named."""
    if SESSION.search(body): return True
    for m in re.finditer(r"\b(?:res\.cookie|set_cookie|SetCookie)\(|\baddCookie\(|new Cookie\(|Set-Cookie", body):
        n = NAME.search(body[m.start():m.start() + 200])
        name = n[1] if n else ""
        if not re.search(r"csrf|xsrf", name, re.I) and (not name or SESSNAME.search(name)): return True
    return False


def missing(text):
    """Names of the flags Secure/HttpOnly/SameSite that the cookie text does not set (a flag set false/False/off counts as missing)."""
    out = []
    for name, rx in FLAGS:
        m = re.search(r"(?:\b|[;\s\"'`])%s\b\s*(?:[:=(]\s*(\w+))?" % rx, text, re.I)
        if not m or (m[1] or "").lower() in ("false", "none", "off", "0"): out.append(name)
    return out


def cookie_rows(rel, t, cover=None):
    """[(line, message)] for the session-looking cookies set in masked text t that lack a flag; cover (a list) gets one item per session-named or dynamic cookie with SameSite Strict/Lax."""
    sites = []  # (offset, text, name-or-None)
    for rx in (GOCOOKIE, EXPRESS, PYSET):
        for m in rx.finditer(t): sites.append((m.start(), call_text(t, m.end() - 1 if rx is GOCOOKIE else m.start())))
    for m in HEADER.finditer(t):  # the rest of the line: a header value like `sid=..; Path=/`, not a read like `getHeader("Set-Cookie")` with no `=`
        e = t.find("\n", m.end())
        sites.append((m.start(), t[m.start():e if e > 0 else len(t)]))
    for m in RESP.finditer(t): sites.append((m.start(), t[m.start():t.find(";", m.end())]))
    out = []
    for off, s in sites:
        n = NAME.search(s)
        name = n[1] if n else ""
        if (name and not SESSNAME.search(name)) or re.search(r"csrf|xsrf", name, re.I) or EXPIRY.search(s): continue
        if re.match(r"res\.cookie|set_cookie", t[off:off + 12]):  # options passed as a variable or spread: flags unknown
            a = args(s)
            if re.search(r"\.\.\.|\*\*", s) or (len(a) > 2 and re.fullmatch(r"\s*[A-Za-z_$][\w$.]*\s*", a[2])): continue
        if re.search(r"""Value\s*:\s*["']{2}|,\s*["']{2}\s*[,)]""", s): continue
        if HEADER.search(s) and not re.search(r"=", s.split("Set-Cookie", 1)[-1]): continue
        miss = missing(s)
        if cover is not None and SAMESITE.search(s): cover.append(off)
        if miss: out.append((line_of(t, off), "session cookie %s sets no %s" % (repr(name) if name else "(dynamic)", ", ".join(miss))))
    # Java: `Cookie c = new Cookie(..)` + c.setSecure/setHttpOnly + addCookie(c); reported at addCookie. Flags set on the variable or a Set-Cookie header string below it count.
    for m in JNEW.finditer(t):
        v = m[1]
        nm = re.match(r"""\s*\(\s*["']([^"']*)""", t[m.end() - 1:])
        add = re.compile(r"\baddCookie\(\s*%s\s*\)" % re.escape(v)).search(t, m.end())
        if not add or (nm and not SESSNAME.search(nm[1])): continue
        win = re.split(r"\n[ \t]*\}[ \t]*(?:\n|$)", t[m.end():add.end() + 400])[0]  # to the end of the method
        blk = "\n".join(l for l in win.split("\n") if re.search(r"\b%s\.set\w+\(|Set-Cookie" % re.escape(v), l) or "Set-Cookie" in l)
        got = {"Secure": bool(re.search(r"\b%s\.setSecure\(\s*true" % v, blk)), "HttpOnly": bool(re.search(r"\b%s\.setHttpOnly\(\s*true" % v, blk)),
               "SameSite": bool(re.search(r"%s\.setAttribute\(\s*[\"']SameSite|SameSite\s*=" % v, blk))}
        if re.search(r"Set-Cookie", blk):  # a hand-built Set-Cookie header carries its own flags
            h = blk[blk.find("Set-Cookie"):]
            got.update({k: got[k] or bool(re.search(k, h, re.I)) for k in got})
        gone = [k for k, ok in got.items() if not ok]
        if cover is not None and got["SameSite"]: cover.append(m.start())
        if gone and not EXPIRY.search(win): out.append((line_of(t, add.start()), "session cookie %s sets no %s" % (repr(nm[1]) if nm else "(dynamic)", ", ".join(gone))))
    return sorted(set(out))


def last_stmt(lines, a, b):
    """1-based line of the last statement of the handler on lines a..b: the last line that is not blank or only closing brackets."""
    for i in range(min(b, len(lines)), a - 1, -1):
        if re.sub(r"[\s)}\];,]", "", lines[i - 1]): return i
    return a


def analyze(root):
    """(rows, handlers): sorted (file, line, rule, message) rows for DIR root and the handler count."""
    texts = {}
    us = units(root, texts, True)
    layer = kill = False
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in PRUNE]
        for f in fn:
            if f.endswith((".py", ".js", ".ts", ".mjs", ".java", ".kt", ".go", ".xml", ".gradle", ".kts", ".json", ".cfg", ".toml", ".txt")):
                p = os.path.join(dp, f)
                if os.path.getsize(p) <= 1 << 20 and "node_modules" not in p:
                    raw = read(root, os.path.relpath(p, root).replace(os.sep, "/")) or ""
                    layer, kill = layer or bool(GLOBAL.search(raw)), kill or bool(DISABLE.search((pymask if f.endswith(".py") else mask)(raw)))
    for rel in walk(root)[0]:
        if rel not in texts:
            raw = read(root, rel)
            if raw is not None: texts[rel] = (pymask if rel.endswith(".py") else mask)(raw, True)
    cov = []
    crows = {rel: cookie_rows(rel, t, cov) for rel, t in texts.items() if t is not None}
    # a SameSite=Strict/Lax cookie covers the repo only when no session cookie lacks SameSite; ponytail: repo-wide, not per route
    glob = (layer and not kill) or (cov and not any("SameSite" in m for r in crows.values() for _, m in r))
    rows, n = [], sum(map(len, us.values()))
    seg = lambda r: (r or "").strip("/").split("/")[0]
    # a cookie realm is the first path segment of a route whose handler sets a session cookie: its other state-changing handlers are cookie-session too
    realms = {seg(u[3]) for rel, rs in us.items() if texts.get(rel) for u in rs if sessionish("\n".join(texts[rel].split("\n")[u[0] - 1:max(u[1], u[0])])) and not PUBLIC.search(u[3] or "")} - {""}
    for rel, t in sorted(texts.items()):
        if t is None: continue
        rows += [(shown(root, rel), ln, "missing-cookie-flags", m) for ln, m in crows[rel]]
        lines = t.split("\n")
        for u in us.get(rel, []):
            a, b, ms, route = u[0], u[1], u[2].split("|"), u[3]
            ln = min((r[1] for r in u[4] if r[0] == rel), default=a)
            if b < ln and rel.endswith((".java", ".kt")): a = b = ln  # dense one-line Java: the inventory span ends before its own mapping line
            body = "\n".join(lines[a - 1:max(b, a)])
            if rel.endswith(".py") and "ANY" in ms and re.search(r"require_http_methods\(\s*\[[^\]]*\]", body):  # Django: the allowed methods are in the decorator
                ms = [m.strip(" \"'") for m in re.search(r"require_http_methods\(\s*\[([^\]]*)\]", body)[1].split(",")]
            elif "ANY" in ms and (re.search(r"@require_POST\b|@csrf_exempt\b|\brequest\.POST\b|\brequest\.method\s*==\s*[\"']POST", body)): ms = ["POST"]
            if not STATE & set(ms) or PUBLIC.search(route or ""): continue
            if not (sessionish(body) or seg(route) in realms): continue
            exempt = EXEMPT.search(body)
            if not exempt and (glob or DEFENCE.search(body) or any(HDR.search(l) and CMP.search(NOVALUE.sub("", l)) for l in body.split("\n"))): continue
            what = "csrf_exempt" if exempt else "no anti-forgery token or Origin check"
            rows.append((shown(root, rel), last_stmt(lines, a, b), "missing-csrf-protection", "%s %s in a cookie-session file: %s (cross-site form post can act as the logged-in user)" % ("/".join(sorted(STATE & set(ms))), route or "handler", what)))
    return sorted(set(rows)), n


def main(argv):
    """Print the rows for the directory argv[1] and the summary line on stderr; return 0, or 2 on a usage error."""
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: csrf_cookie_map.py DIR", file=sys.stderr)
        return 2
    rows, n = analyze(argv[1])
    for r in rows: print("%s\t%d\t%s\t%s" % r)
    print("csrf-cookie: %d handlers, %d leads; silence is not proof of a CSRF defence or of cookie flags" % (n, len(rows)) if n or rows else "csrf-cookie: no HTTP handler or cookie found", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
