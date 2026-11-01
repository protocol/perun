#!/usr/bin/env python3
"""attempt_limit_map.py DIR -- heuristic lead-finder for password, one-time-code and reset-code checks with no attempt-limit evidence. Report-only, stdlib only.

Usage: python3 -I attempt_limit_map.py DIR

Read this when you review a sign-in, one-time-code or password-reset flow. A check that a client can retry without limit lets an attacker guess a password or a
short code, and dynamic_probe.py --rate-endpoint sees that only on a running app, for an endpoint you already named. This is the static side: it lists the files that
check a credential and says whether any attempt-limit code was found in the file or its package. A row is a lead, never a finding, and SILENCE IS NOT PROOF OF AN ATTEMPT
LIMIT: a gateway, host or auth service may limit attempts where this scan cannot see.

A candidate file calls a credential check or declares a sign-in route.
- Credential check, comments ignored. JS/TS: bcrypt or bcryptjs `compare`/`compareSync`; argon2 `verify`; a bare `compare` or `verify` imported by name from bcrypt,
  bcryptjs, argon2 or @node-rs/argon2; otplib `authenticator`, `totp` or `hotp` `check`/`verify` in a file that imports otplib; speakeasy `totp` or `hotp` `verify`.
  Python: bcrypt `checkpw`; `check_password_hash`; `check_password`; `.verify(` or `.verify_and_update(` in a file that imports passlib, argon2 or pyotp (not on the bare
  name jwt or jws); `authenticate(` imported from django.contrib.auth; a parameter annotated OAuth2PasswordRequestForm or OAuth2PasswordRequestFormStrict. A Python `def` of one of
  these names is not a call.
  timingSafeEqual, compare_digest, jwt.verify, scrypt and pbkdf2 are never checks.
- Sign-in route: a handler that route_auth_map.py lists, whose method is not GET-only (POST, PUT, PATCH, DELETE, ANY or a server ACTION) and whose path has a segment equal to
  login, signin, otp, mfa, 2fa, twofactor, totp, verifyotp, forgot, forgotpassword, resetpassword or passwordreset (case, `-` and `_` ignored; for an ACTION, the function name).

Evidence for a candidate, the first tier that hits wins:
1. a provider call in the file: supabase `auth.signInWithPassword`, `auth.signInWithOtp` or `auth.verifyOtp`, `signInWithEmailAndPassword`, `InitiateAuth`, `initiateAuth` or `passwordGrant`;
2. in the file: rate-limit, limiter, lockout, locked-until, failed-login, login-attempts, max-attempts, attempt-count, express-brute, slowapi, django-axes, the Axes middleware
   or backend, the NestJS throttler, express-slow-down, or `429` / `Too Many Requests`. A bare `throttle` is not evidence;
3. the same names (not 429) in any scanned file below the package root: the nearest ancestor directory (the file's own first, DIR last) holding package.json, pyproject.toml,
   requirements.txt, setup.py, setup.cfg or Pipfile, else DIR (a directory with no marker belongs to its nearest marked ancestor's package, so with no marker anywhere all of DIR is
   one package). Nested packages count, sibling packages do not;
4. a candidate with no credential check in its file (a route only): a provider call anywhere below the package root;
5. none: the row below.

Not read: node_modules, .git, dist, build, .next, coverage, vendor, .venv, __pycache__, out, venv, .vercel, .netlify, .nuxt, .output, .svelte-kit, .turbo and .cache directories;
directories named test, tests, __tests__, e2e, spec, specs, fixture, fixtures, doc, docs, example, examples or __mocks__; test files; files named *.test.*, *.spec.* or *.min.*;
symlinks; files over 1 MB; files that do not end in .ts, .tsx, .js, .jsx, .mjs, .cjs or .py. Paths are judged below DIR, so a checkout under a parent named tests is still scanned.

Rows: TSV on stdout, `file<TAB>line<TAB>rule<TAB>message`, paths relative to DIR with `/` (a control character or undecodable byte in a name prints as `?`), sorted by file, line, rule, message.
One row per candidate file, at its first trigger line
(a credential check or a sign-in route, whichever comes first; the route wins a tie).
- missing-attempt-limit: no tier hit. The message says a gateway, host or auth service may still limit attempts and points at dynamic_probe.py --rate-endpoint.
- attempt-limit-evidence: a tier hit; the message names the kind, the token and its file:line, so you can check it covers this route.
stderr: one summary line, "attempt-limit: N candidate files, M without attempt-limit evidence; silence is not proof of an attempt limit", or
"attempt-limit: no credential check or sign-in route found" when there is no candidate.
Exit 0; 2 with "usage: attempt_limit_map.py DIR" on stderr for no argument, extra arguments or a DIR that is not a directory. Reads files only; writes nothing.

ponytail: evidence is package-scoped (a limiter anywhere in the package counts, even one on another route); gateway, host, WAF and auth-service limits are not seen; aliased
imports and wrapper helpers are not followed; only the listed libraries are seen (scrypt, pbkdf2 and hand-written compares are not); keyword routes need a `scan()` handler
row and an exact segment match; files over 1 MB are skipped; string contents count; `mask` does not parse regex literals; a named-import list over 500 characters is not read, and a
`require` import only after `const`, `let` or `var` (those bounds keep every search linear). Upgrade to a parser per framework if precision matters more.
"""
import os, re, stat, sys

sys.dont_write_bytecode = True  # `python3 -I` drops this dir from sys.path: add it for the sibling imports and leave no __pycache__ behind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from header_config import MAX_BYTES, PRUNE, SKIP_FILE, relpath  # noqa: E402
from route_auth_map import EXT, TEST, pymask, read, scan  # noqa: E402
from tenant_scope_check import lineno, mask  # noqa: E402

MARKERS = ("package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile")  # a directory holding one is a package root
BODY = {"POST", "PUT", "PATCH", "DELETE", "ANY", "ACTION"}  # a method that is not GET-only
SEGMENTS = {"login", "signin", "otp", "mfa", "2fa", "twofactor", "totp", "verifyotp", "forgot", "forgotpassword", "resetpassword", "passwordreset"}
PRE = (("bcrypt", "argon2", "otplib", "speakeasy"),  # lowercase tokens: a file whose raw text holds none of them cannot hold a credential check (JS/TS, Python)
       ("bcrypt", "check_password", "passlib", "argon2", "pyotp", "django.contrib.auth", "oauth2passwordrequestform"))

PROVIDER_SRC = (r"(?<=\.auth\.)(?:signInWithPassword|signInWithOtp|verifyOtp)(?=\s*\()|\bsignInWithEmailAndPassword(?=\s*\()|\b(?:Admin)?InitiateAuth(?:Command)?\b"
                r"|\binitiateAuth(?=\s*\()|\bpasswordGrant(?=\s*\()")
STRONG_SRC = (r"(?i:rate[-_]?limit|(?<!de)limiter|lockout|locked[-_]?until|failed[-_]?(?:login|attempt)s?|login[-_]?attempts|max[-_]?(?:login[-_]?)?attempts"
              r"|attempt[-_]?count|express[-_]?brute|slowapi|django[-_]axes)"
              r"|Axes(?:Middleware|Backend|StandaloneBackend)|@nestjs/throttler|ThrottlerGuard|RateThrottle|DEFAULT_THROTTLE|express-slow-down|slowDown")
TOO_MANY_SRC = r"(?i:\b429\b|too many requests)"
RAW = re.compile("|".join((PROVIDER_SRC, STRONG_SRC, TOO_MANY_SRC)), re.I)  # superset of every evidence regex on the unmasked text: mask a file only when this hits
PROVIDER, STRONG, LIMIT = re.compile(PROVIDER_SRC), re.compile(STRONG_SRC), re.compile(STRONG_SRC + "|" + TOO_MANY_SRC)  # LIMIT: STRONG or 429 / Too Many Requests
TIERS = (("provider call", PROVIDER, False, False), ("attempt-limit code in this file", LIMIT, False, False),  # (kind, regex, whole package, route-only candidates only)
         ("attempt-limit code in this package", STRONG, True, False), ("provider call in this package", PROVIDER, True, True))
MISSING = ("%s: no attempt limit, lockout or auth provider found in this file or its package (a gateway, host or auth service may still limit attempts); "
           "confirm on a running instance with dynamic_probe.py --rate-endpoint")
FOUND = "%s: %s found (%s at %s:%d); check it covers this route"


def imp(name, lib):
    """Regex source: `name` imported by name from a module matching lib, as `import { x } from "m"` (a default import may come first) or `const { x } = require("m")`.
    The braces hold at most 500 characters each side of the name, so a file of unclosed braces cannot make the search quadratic."""
    n, q = r"\{[^}]{0,500}\b%s\b[^}]{0,500}\}" % name, r"""["'](?:%s)["']""" % lib
    return r"import\s+(?:[\w$]+\s*,\s*)?%s\s*from\s*%s|(?:const|let|var)\s*%s\s*=\s*require\(\s*%s\s*\)" % (n, q, n, q)


def isdef(m, i):
    """True when the name at m[i] is declared by a Python `def` just before it (`def check_password(`), not called."""
    return bool(re.search(r"\bdef\s+\Z", m[max(0, i - 40):i]))


def jwtrecv(m, i):
    """True when the `.` at m[i] follows the bare name jwt or jws (`jwt.verify(`): a token check, not a credential check."""
    return bool(re.search(r"(?<![\w.])(?:jwt|jws)\Z", m[max(0, i - 4):i]))


def table(rows):
    """Compile (call regex, gate regex or None, skip function or None) rows: a call counts only when its file matches the gate and skip(text, offset) is false."""
    return tuple((re.compile(a), g and re.compile(g, re.M), s) for a, g, s in rows)


PYIMP = r"^[ \t]*(?:import\s+(?:passlib|argon2|pyotp)\b|from\s+(?:passlib|argon2|pyotp)(?:\.\w+)*\s+import\b)"  # `[ \t]*`, not `\s*`: that would span blank lines and go quadratic
TRIGGERS = (
    table((  # JS/TS
        (r"\bbcrypt(?:js)?\.compare(?:Sync)?\s*\(", None, None),
        (r"(?<![.\w$])compare(?:Sync)?\s*\(", imp(r"compare(?:Sync)?", r"bcrypt(?:js)?"), None),
        (r"\bargon2\.verify\s*\(", None, None),
        (r"(?<![.\w$])verify\s*\(", imp("verify", "argon2|@node-rs/argon2"), None),
        (r"\b(?:authenticator|totp|hotp)\.(?:check|verify)\s*\(", r"""(?:require\(\s*|from\s+|import\s+|import\(\s*)["'](?:otplib|@otplib/[\w-]+)["']""", None),
        (r"\bspeakeasy\.(?:totp|hotp)\.verify(?:Delta)?\s*\(", None, None))),
    table((  # Python
        (r"\bcheckpw\s*\(", r"^[ \t]*(?:import\s+bcrypt\b|from\s+bcrypt(?:\.\w+)*\s+import\b)", isdef),
        (r"\bcheck_password_hash\s*\(", None, isdef),
        (r"\bcheck_password\s*\(", None, isdef),
        (r"\.verify(?:_and_update)?\s*\(", PYIMP, jwtrecv),
        (r"(?<![\w.])authenticate\s*\(", r"^[ \t]*from\s+django\.contrib\.auth\s+import\s+(?:\([^)]{0,500}\bauthenticate\b|[^\n(]*\bauthenticate\b)", isdef),
        (r":\s*(?:Annotated\[\s*)?OAuth2PasswordRequestForm(?:Strict)?\b", None, None))))


def walk(root):
    """([sorted paths below root, with `/`, of the files to scan], {directories below root, "" for root, that hold a package marker file that is a regular file, not a symlink}).
    A path is left out when a directory below root is in PRUNE, the name holds a SKIP_FILE part, TEST matches, the suffix is not in EXT, or the file is no regular file or over MAX_BYTES."""
    files, pkgs = [], set()
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in PRUNE]
        d = os.path.relpath(dp, root).replace(os.sep, "/")
        d = "" if d == "." else d
        for f in fn:
            rel = d + "/" + f if d else f
            code = f.endswith(EXT) and not any(s in f for s in SKIP_FILE) and not TEST.search(rel)
            if not (code or f in MARKERS): continue
            try: st = os.lstat(os.path.join(dp, f))
            except OSError: continue
            if not stat.S_ISREG(st.st_mode): continue  # a symlink is neither scanned nor a package marker
            if f in MARKERS: pkgs.add(d)
            if code and st.st_size <= MAX_BYTES: files.append(rel)
    return sorted(files), pkgs


def keyword(row):
    """True when a route_auth_map row (file, line, method, route, auth) is a state-changing sign-in, one-time-code or reset route."""
    _, _, meth, route, _ = row
    return any(s.lower().replace("-", "").replace("_", "") in SEGMENTS for s in route.split("/")) and any(t in BODY for t in meth.split("|"))


def first_trigger(m, py):
    """Offset of the first credential-check call in masked text m (the Python rules when py, else JS/TS), else None."""
    best = None
    for rx, gate, skip in TRIGGERS[py]:
        x = next((x for x in rx.finditer(m) if not (skip and skip(m, x.start()))), None)  # the gate is read only for a file that has the call
        if x and (best is None or x.start() < best) and (not gate or gate.search(m)): best = x.start()
    return best


def hit(rx, m, rel):
    """(rel, token, line) of the first match of rx in the masked text m of file rel, else None."""
    x = rx.search(m)
    return (rel, x.group(0), lineno(m, x.start())) if x else None


def shown(root, rel):
    """rel as printed: a control character or an undecodable byte in a file name becomes `?` (header_config.relpath), so a name cannot break or forge a TSV row."""
    return relpath(os.path.join(root, rel), root)


def pkgroot(rel, pkgs):
    """The nearest ancestor directory of rel (its own directory first) that is in pkgs, else "" (DIR)."""
    d = rel.rpartition("/")[0]
    while d and d not in pkgs: d = d.rpartition("/")[0]
    return d


def analyze(root):
    """(rows, candidates, missing) for the directory root: the sorted (file, line, rule, message) rows, the number of candidate files, and how many got a missing-attempt-limit row."""
    files, pkgs = walk(root)
    known, kw, texts, memo, rows = set(files), {}, {}, {}, []
    for r in scan(root)[0]:  # sorted, so the first row of a file is its smallest line
        if r[0] in known and keyword(r): kw.setdefault(r[0], r)
    for rel in files:
        raw, py = read(root, rel), rel.endswith(".py")
        if raw is None: continue
        low = raw.lower()
        if rel in kw or any(t in low for t in PRE[py]) or RAW.search(raw):
            texts[rel] = (pymask if py else mask)(raw, True)  # comments blanked, string contents kept; in sorted file order

    def pkghit(pk, rx):
        """hit() for the first file below package root pk, in sorted order, that rx matches; cached per root."""
        if (pk, rx) not in memo:
            memo[pk, rx] = None
            for f, t in texts.items():
                if not pk or f.startswith(pk + "/"):
                    memo[pk, rx] = hit(rx, t, f)
                    if memo[pk, rx]: break
        return memo[pk, rx]

    for rel, m in texts.items():
        tp, k = first_trigger(m, rel.endswith(".py")), kw.get(rel)
        if tp is None and k is None: continue
        tl = lineno(m, tp) if tp is not None else None
        if k and (tl is None or k[1] <= tl): line, what = k[1], " ".join(("%s %s" % k[2:4]).split())  # the route wins a tie
        else: line, what = tl, "credential check"
        pk, found = pkgroot(rel, pkgs), None
        for kind, rx, wide, route_only in TIERS:
            h = None if route_only and tp is not None else pkghit(pk, rx) if wide else hit(rx, m, rel)
            if h:
                found = FOUND % (what, kind, h[1], shown(root, h[0]), h[2])
                break
        out = shown(root, rel)
        rows.append((out, line, "attempt-limit-evidence", found) if found else (out, line, "missing-attempt-limit", MISSING % what))
    return sorted(rows), len(rows), sum(r[2] == "missing-attempt-limit" for r in rows)


def main(argv):
    """Print the rows for the directory argv[1] and the summary line on stderr; return 0, or 2 on a usage error."""
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: attempt_limit_map.py DIR", file=sys.stderr)
        return 2
    rows, n, missing = analyze(argv[1])
    for r in rows: print("%s\t%d\t%s\t%s" % r)
    print("attempt-limit: %d candidate files, %d without attempt-limit evidence; silence is not proof of an attempt limit" % (n, missing) if n
          else "attempt-limit: no credential check or sign-in route found", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
