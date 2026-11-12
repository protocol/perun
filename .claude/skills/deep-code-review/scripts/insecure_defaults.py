#!/usr/bin/env python3
"""insecure_defaults.py DIR -- deterministic lead-finder for fail-open and insecure-by-default code (CWE-1188, 636, 295, 942, 347). Report-only, stdlib only.

Usage: python3 -I insecure_defaults.py DIR

Read this when you review a service for what happens when config is unset or a check throws: an env flag whose default turns a protection off, an auth check that
answers "allow" on an exception, TLS or JWT verification disabled in code, debug on by default, a wildcard CORS origin that also sends credentials. A row is a lead,
never a finding: a deploy that always sets the flag, or a dev-only branch, may make it harmless. SILENCE IS NOT PROOF of secure defaults.

Rows are `file<TAB>line<TAB>rule<TAB>message`; stderr gets one summary line. Rules (precision first, one literal pattern each):
- `default-on-security-flag`: an env/config read whose literal default disables a protection (`AUTH_DISABLED` default true, `SKIP_TLS_VERIFY` default 1) or leaves a required one off
  (`REQUIRE_AUTH` default false, `VERIFY_SSL` default 0): Python `getenv`/`environ.get`/`env.get`/`config`, JS `process.env.X ?? true` or `|| "true"`.
- `fail-open-exception`: a broad `except` (bare, Exception, BaseException) or JS `catch` inside a function named like an auth, permission or token check that returns True or calls `next()`.
- `tls-verify-off`: `verify=False`, `verify_ssl=False`, `check_hostname = False`, `CERT_NONE`, `_create_unverified_context`, `rejectUnauthorized: false`, `strictSSL: false`,
  `NODE_TLS_REJECT_UNAUTHORIZED = 0`, `InsecureSkipVerify: true`. A line naming localhost / 127.0.0.1 is skipped.
- `jwt-unverified`: `algorithms=["none"]`, `alg: "none"`, `verify_signature: False`, or a jwt/jose call with `verify=False`.
- `debug-on-default`: `DEBUG = True` at module level (file not named dev/local/test/example/demo), or a DEBUG / FLASK_DEBUG / APP_DEBUG / DEV_MODE env read whose default is true.
- `cors-wildcard-credentials`: a `*` allowed origin within 3 lines of a credentials-true setting (Django `CORS_*` constants: anywhere in the file) (Express cors, flask-cors, Django corsheaders, raw headers).

Skipped by design: test, spec, fixtures, mocks and e2e paths, node_modules and similar (attempt_limit_map.walk rules plus `_test.go`); comments are blanked. Fail-closed variants
(`rejectUnauthorized: true`, `verify=True`, a default of false for a disable flag, a specific CORS origin) never fire.
ponytail: line-and-window text scan, not data flow; a flag set to a safe value elsewhere, or a wrapper around the check, reads as a hit. Upgrade to per-framework AST rules if needed.
"""
import os, re, stat, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from header_config import MAX_BYTES, PRUNE, relpath  # noqa: E402
from route_auth_map import TEST, pymask, read  # noqa: E402
from tenant_scope_check import mask  # noqa: E402

EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go")
DEVFILE = re.compile(r"(?:^|[/_.-])(?:dev|local|development|test|tests|example|examples|sample|demo|debug)(?:[/_.-]|$)", re.I)
TRUE, FALSE = {"true", "1", "yes", "on"}, {"false", "0", "no", "off"}
SEC = re.compile(r"AUTH|SECUR|TLS|SSL|CERT|VERIFY|CSRF|SIGNATURE|JWT|PERMISSION|ACL|MFA|2FA|CORS|HTTPS|ENCRYPT")
NEG = re.compile(r"DISABLE|SKIP|BYPASS|NO_|ALLOW_ALL|ALLOW_ANON|ALLOW_ANY|TRUST_ALL|INSECURE|UNSAFE")
POS = re.compile(r"REQUIRE|ENFORCE|ENABLE|VERIFY|CHECK|VALIDATE|STRICT|SECURE")
DEBUGNAME = {"DEBUG", "FLASK_DEBUG", "APP_DEBUG", "DJANGO_DEBUG", "DEV_MODE", "DEVELOPMENT_MODE", "DEBUG_MODE", "ENABLE_DEBUG", "DEBUG_ENABLED"}
ENV = (re.compile(r"(?:getenv|environ\.get|env\.get|env\.bool|env|config|getboolean)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']\s*,\s*(?:default\s*=\s*)?([\"']?)(\w+)\2\s*[,)]"),
       re.compile(r"(?:process\.env|import\.meta\.env)(?:\.([A-Z][A-Z0-9_]*)|\[[\"']([A-Z][A-Z0-9_]*)[\"']\])\s*(?:\?\?|\|\|)\s*([\"']?)(\w+)\3"))
AUTHFN = re.compile(r"authenticat|authoriz|is_?allowed|has_?perm|check_?(?:auth|token|perm|password|signature|access|credential)|"
                    r"verify_?(?:token|signature|jwt|password|auth|hmac|request|credential)|validate_?(?:token|jwt|signature|session|credential)|can_?access", re.I)
DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|\bfunction\s*\*?\s*(\w+)|(\w+)\s*[:=]\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>)|^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{")
PYEXC = re.compile(r"^(\s*)except(?:\s+(?:Exception|BaseException)(?:\s+as\s+\w+)?)?\s*:")
JSCATCH = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{")
OPEN = re.compile(r"\breturn\s+True\b|\breturn\s+true\b|\bnext\s*\(\s*\)")
TLS = re.compile(r"\bverify(?:_ssl)?\s*=\s*False\b|check_hostname\s*=\s*False|\bCERT_NONE\b|_create_unverified_context|rejectUnauthorized[\"']?\s*:\s*false|"
                 r"strictSSL\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED[\"']?\]?\s*=\s*[\"']?0|InsecureSkipVerify\s*:\s*true")
JWT = re.compile(r"algorithms?[\"']?\s*[:=](?!=)\s*\[?\s*[\"']none[\"']|\balg[\"']?\s*[:=](?!=)\s*[\"']none[\"']|verify_signature[\"']?\s*[:=]\s*(?:False|false)", re.I)
JWTV = re.compile(r"(?:jwt|jose|token)\w*\.decode\(.*\bverify\s*=\s*False\b", re.I)
WILD = re.compile(r"(?:origins?|allow_origins?)[\"']?\s*[:=(]\s*\[?\s*[\"']\*[\"']|Allow-Origin[\"']?\s*[:,=)]\s*[\"']\*[\"']|ALLOW_ALL_ORIGINS\s*=\s*True|CORS_ORIGIN_ALLOW_ALL\s*=\s*True", re.I)
CRED = re.compile(r"credentials[\"']?\s*[:=]\s*(?:true|True)|Allow-Credentials[\"']?\s*[:,=)]\s*[\"']true|ALLOW_CREDENTIALS\s*=\s*True", re.I)


def files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in PRUNE]
        d = os.path.relpath(dp, root).replace(os.sep, "/")
        for f in fn:
            rel = f if d == "." else d + "/" + f
            if not f.endswith(EXT) or TEST.search(rel) or f.endswith("_test.go") or f.endswith(".d.ts"): continue
            try: st = os.lstat(os.path.join(dp, f))
            except OSError: continue
            if stat.S_ISREG(st.st_mode) and st.st_size <= MAX_BYTES: out.append(rel)
    return sorted(out)


def fname(lines, i):
    """Name of the nearest function definition at or before line index i, else ""."""
    for k in range(i, max(i - 60, -1), -1):
        m = DEF.search(lines[k])
        if m: return next(g for g in m.groups() if g)
    return ""


def scan_file(rel, text):
    py = rel.endswith(".py")
    lines = (pymask(text, keep=True) if py else mask(text, keep=True)).split("\n")
    dev = bool(DEVFILE.search(rel))
    rows = []
    def add(i, rule, msg):
        r = (rel, i + 1, rule, msg)
        if r not in rows: rows.append(r)
    wild, cred = [], []
    for i, ln in enumerate(lines):
        local = re.search(r"localhost|127\.0\.0\.1|::1", ln)
        for rx in ENV:
            for m in rx.finditer(ln):
                g = [x for x in m.groups() if x is not None]
                name, v = g[0], g[-1].lower()
                if name in DEBUGNAME:
                    if v in TRUE and not dev: add(i, "debug-on-default", "%s defaults to %s: debug stays on when the variable is unset" % (name, v))
                elif v in TRUE and SEC.search(name) and NEG.search(name) or v in TRUE and re.search("INSECURE|BYPASS", name):
                    add(i, "default-on-security-flag", "%s defaults to %s: the protection is off when the variable is unset" % (name, v))
                elif v in FALSE and SEC.search(name) and POS.search(name):
                    add(i, "default-on-security-flag", "%s defaults to %s: the protection is off when the variable is unset" % (name, v))
        if TLS.search(ln) and not local and not JWTV.search(ln) and not JWT.search(ln): add(i, "tls-verify-off", "certificate or hostname verification is switched off in code")
        if JWT.search(ln) or JWTV.search(ln): add(i, "jwt-unverified", "JWT algorithm none or signature verification off")
        if py and not dev and re.match(r"DEBUG\s*=\s*True\b", ln): add(i, "debug-on-default", "module-level DEBUG = True")
        if WILD.search(ln): wild.append((i, "ALLOW_ALL" in ln))
        if CRED.search(ln): cred.append((i, "ALLOW_CREDENTIALS" in ln and "CORS_" in ln))
        m = PYEXC.match(ln) if py else None
        if m and AUTHFN.search(fname(lines, i)):
            ind = len(m.group(1))
            for k in range(i + 1, min(i + 6, len(lines))):
                b = lines[k]
                if b.strip() and len(b) - len(b.lstrip()) <= ind: break
                if OPEN.search(b): add(k, "fail-open-exception", "broad except in %s() returns allow instead of denying" % fname(lines, i)); break
        elif not py and JSCATCH.search(ln) and AUTHFN.search(fname(lines, i)):
            depth, body = 0, ""
            for k in range(i, min(i + 8, len(lines))):
                body += lines[k][lines[k].index("catch"):] if k == i else lines[k]
                depth += lines[k].count("{") - lines[k].count("}")
                if depth <= 0: break
            if OPEN.search(body): add(i, "fail-open-exception", "catch in %s() allows the request instead of denying" % fname(lines, i))
    for w, wd in wild:  # same call within 3 lines, or the two Django settings constants anywhere in the file
        if any(abs(w - c) <= 3 or wd and cd for c, cd in cred): add(w, "cors-wildcard-credentials", "wildcard origin with credentials enabled")
    return rows


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: insecure_defaults.py DIR", file=sys.stderr); return 2
    root, rows, n = argv[1], [], 0
    for rel in files(root):
        t = read(root, rel)
        if t is None: continue
        n += 1
        rows += [(relpath(os.path.join(root, a), root), b, c, d) for a, b, c, d in scan_file(rel, t)]
    for r in rows: print("%s\t%d\t%s\t%s" % r)
    print("insecure-defaults: %d files, %d leads; silence is not proof of secure defaults" % (n, len(rows)) if n else "insecure-defaults: no source files", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
