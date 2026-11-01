"""attempt_limit_map.py (static lead-finder for password, one-time-code and reset-code checks with no attempt-limit evidence): every credential-check
trigger and import gate, the non-triggers, every evidence tier and message, package scoping, sign-in route keywords, ignored paths and size and encoding
limits, hostile input, the usage and exit-code contract, and the review_checks.sh --full wiring. Fixtures are fictional (acme, hello); one new file per
feature, nothing appended to a shared spec."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # the in-process imports below must not leave a __pycache__ in the skill's scripts dir

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
SCRIPT = SK / "attempt_limit_map.py"
RC = SK / "review_checks.sh"
sys.path.insert(0, str(SK))
import attempt_limit_map as A  # noqa: E402
import header_config  # noqa: E402
import route_auth_map  # noqa: E402
import tenant_scope_check  # noqa: E402

MISSING, EVIDENCE, CRED = "missing-attempt-limit", "attempt-limit-evidence", "credential check"
FILE_KIND, PKG_KIND, PROVIDER_KIND, PROVIDER_PKG_KIND = ("attempt-limit code in this file", "attempt-limit code in this package", "provider call", "provider call in this package")
MARKER_FILES = ("package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile")
USAGE = "usage: attempt_limit_map.py DIR\n"
NO_CANDIDATE = "attempt-limit: no credential check or sign-in route found\n"
SUMMARY = "attempt-limit: %d candidate files, %d without attempt-limit evidence; silence is not proof of an attempt limit\n"


def src(*lines):
    """A source file from its lines."""
    return "\n".join(lines) + "\n"


def miss(what):
    """The missing-attempt-limit message, spelled out here so a wording change in the script fails a test."""
    return ("%s: no attempt limit, lockout or auth provider found in this file or its package (a gateway, host or auth service may still limit attempts); "
            "confirm on a running instance with dynamic_probe.py --rate-endpoint") % what


def found(what, kind, token, at):
    """The attempt-limit-evidence message."""
    return "%s: %s found (%s at %s); check it covers this route" % (what, kind, token, at)


LOGIN = src('const bcrypt = require("bcrypt");', "async function ok(pw, hash) {", "  return bcrypt.compare(pw, hash);", "}")  # a credential check on line 3; four lines
PY_LOGIN = src("import bcrypt", "", "ok = bcrypt.checkpw(pw, hashed)")  # a credential check on line 3
LIMIT = src('const x = "rateLimit";')  # attempt-limit evidence on line 1 (STRONG token "rateLimit")
EXPRESS = src('const express = require("express");', "const app = express();")  # a route added on line 3


def write(root, files):
    """Create every relative path -> str or bytes under root."""
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes): p.write_bytes(text)
        else: p.write_text(text, encoding="utf-8")


def scan(files, under=None, prep=None):
    """(rows, candidates, missing) from analyze() for a fresh temp repo holding files; under puts the repo below a parent directory of that name; prep(dir) adds what write() cannot."""
    with tempfile.TemporaryDirectory() as t:
        d = Path(t, under, "acme") if under else Path(t, "acme")
        write(d, files)
        if prep: prep(d)
        return A.analyze(str(d))


def rows(files, **kw):
    """The rows alone."""
    return scan(files, **kw)[0]


def run(*argv, **kw):
    """The script under `python3 -I`, as a user runs it."""
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, argv)], capture_output=True, text=True, **kw)


# (case, file, source, line the row is on): one credential check each, with no attempt-limit evidence anywhere
TRIGGERS = (
    ("bcrypt.compare", "a.js", src('const bcrypt = require("bcrypt");', "const ok = await bcrypt.compare(pw, hash);"), 2),
    ("bcryptjs.compare", "a.js", src('import bcryptjs from "bcryptjs";', "const ok = await bcryptjs.compare(pw, hash);"), 2),
    ("bcrypt.compareSync", "a.ts", src('import * as bcrypt from "bcrypt";', "const ok: boolean = bcrypt.compareSync(pw, hash);"), 2),
    ("bcryptjs.compareSync", "a.js", src('const bcryptjs = require("bcryptjs");', "const ok = bcryptjs.compareSync(pw, hash);"), 2),
    ("bare compare, ESM import", "a.ts", src('import { compare } from "bcryptjs";', "const ok = await compare(pw, hash);"), 2),
    ("bare compareSync, default and named ESM import", "a.js", src('import bcrypt, { compareSync } from "bcrypt";', "const ok = compareSync(pw, hash);"), 2),
    ("bare compare, require", "a.js", src('const { compare } = require("bcrypt");', "const ok = await compare(pw, hash);"), 2),
    ("bare compareSync, multi-line require", "a.cjs", src("const {", "  hash,", "  compareSync,", '} = require("bcryptjs");', "const ok = compareSync(pw, h);"), 5),
    ("argon2.verify", "a.mjs", src('import argon2 from "argon2";', "const ok = await argon2.verify(hash, pw);"), 2),
    ("bare verify, argon2", "a.js", src('import { verify } from "argon2";', "const ok = await verify(hash, pw);"), 2),
    ("bare verify, @node-rs/argon2", "a.ts", src('import { verify } from "@node-rs/argon2";', "const ok = await verify(hash, pw);"), 2),
    ("authenticator.check", "a.tsx", src('import { authenticator } from "otplib";', "const ok = authenticator.check(code, secret);"), 2),
    ("totp.verify, require", "a.js", src('const { totp } = require("otplib");', "const ok = totp.verify({ token: code, secret });"), 2),
    ("hotp.check, scoped otplib package", "a.jsx", src('import { hotp } from "@otplib/preset-default";', "const ok = hotp.check(code, secret, 1);"), 2),
    ("speakeasy.totp.verify", "a.js", src('const speakeasy = require("speakeasy");', 'const ok = speakeasy.totp.verify({ secret, encoding: "base32", token: code });'), 2),
    ("speakeasy.hotp.verify", "a.js", src('const speakeasy = require("speakeasy");', "const ok = speakeasy.hotp.verify({ secret, counter, token: code });"), 2),
    ("speakeasy.totp.verifyDelta", "a.js", src('const speakeasy = require("speakeasy");', "const d = speakeasy.totp.verifyDelta({ secret, token: code });"), 2),
    ("bcrypt.checkpw", "a.py", src("import bcrypt", "", "ok = bcrypt.checkpw(pw, hashed)"), 3),
    ("checkpw, from import", "a.py", src("from bcrypt import checkpw", "", "ok = checkpw(pw, hashed)"), 3),
    ("check_password_hash", "a.py", src("from werkzeug.security import check_password_hash", "", "ok = check_password_hash(pw_hash, pw)"), 3),
    ("check_password", "a.py", src("ok = user.check_password(pw)"), 1),
    ("passlib verify", "a.py", src("from passlib.context import CryptContext", "", "ok = CryptContext(schemes=['bcrypt']).verify(pw, hashed)"), 3),
    ("passlib verify_and_update", "a.py", src("from passlib.context import CryptContext", "", "ok, new = ctx.verify_and_update(pw, hashed)"), 3),
    ("argon2 verify", "a.py", src("import argon2", "", "ok = argon2.PasswordHasher().verify(pw_hash, pw)"), 3),
    ("pyotp verify", "a.py", src("import pyotp", "", "ok = pyotp.TOTP(secret).verify(code)"), 3),
    ("pyotp verify, from import", "a.py", src("from pyotp import TOTP", "", "ok = TOTP(secret).verify(code)"), 3),
    ("django authenticate", "a.py", src("from django.contrib.auth import authenticate, login", "", "user = authenticate(request, username=name, password=pw)"), 3),
    ("django authenticate, parenthesized import", "a.py", src("from django.contrib.auth import (", "    login,", "    authenticate,", ")", "", "user = authenticate(username=name, password=pw)"), 6),
    ("OAuth2PasswordRequestForm parameter", "a.py", src("from fastapi.security import OAuth2PasswordRequestForm", "", "async def token(form: OAuth2PasswordRequestForm = Depends()):", "    return form"), 3),
    ("Annotated OAuth2PasswordRequestForm parameter", "a.py", src("from typing import Annotated", "from fastapi.security import OAuth2PasswordRequestForm", "",
                                                                  "async def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]):", "    return form"), 4),
    ("OAuth2PasswordRequestFormStrict parameter", "a.py", src("from fastapi.security import OAuth2PasswordRequestFormStrict", "", "async def token(form: OAuth2PasswordRequestFormStrict = Depends()):", "    return form"), 3),
    ("Annotated OAuth2PasswordRequestFormStrict parameter", "a.py", src("from typing import Annotated", "from fastapi.security import OAuth2PasswordRequestFormStrict", "",
                                                                         "async def token(form: Annotated[OAuth2PasswordRequestFormStrict, Depends()]):", "    return form"), 4),
    ("a def does not hide a later call", "a.py", src("def check_password(self, raw):", "    return raw", "", "ok = check_password(pw)"), 4),
)

# (case, file, source): no credential check, so no row and no candidate
QUIET = (
    ("compare on another receiver, bcrypt named import", "a.js", src('import { compare } from "bcryptjs";', "const n = collator.compare(a, b);")),
    ("compare on a non-bcrypt receiver", "a.js", src('const bcrypt = require("bcrypt");', "const n = collator.compare(a, b);")),
    ("bare compare without the import", "a.js", src("function compare(a, b) { return a - b; }", "const n = compare(1, 2);")),
    ("bare compare imported from another module", "a.js", src('import { compare } from "semver";', 'const n = compare("1.0.0", "1.1.0");')),
    ("bcrypt import that does not name compare", "a.js", src('import { hash } from "bcrypt";', "function compare(a, b) { return 0; }", "compare(1, 2);")),
    ("bare verify without the import", "a.js", src("const c = verify(token, key);")),
    ("bare verify imported from another module", "a.js", src('import { verify } from "jsonwebtoken";', "const c = verify(token, key);")),
    ("jwt.verify", "a.js", src('const jwt = require("jsonwebtoken");', "const c = jwt.verify(token, key);")),
    ("jwt.verify beside an argon2 verify import", "a.js", src('import { verify } from "argon2";', "const c = jwt.verify(token, key);")),
    ("timingSafeEqual", "a.js", src('const crypto = require("crypto");', "const ok = crypto.timingSafeEqual(a, b);")),
    ("scrypt and pbkdf2", "a.js", src('const crypto = require("crypto");', "const k = crypto.scryptSync(pw, salt, 64);", 'crypto.pbkdf2Sync(pw, salt, 1, 64, "sha512");')),
    ("otplib call without the import", "a.js", src("const ok = authenticator.check(code, secret);")),
    ("authenticator from another library", "a.js", src('import { authenticator } from "otpauth";', "authenticator.check(c, s);")),
    ("the calls only in comments", "a.js", src("// bcrypt.compare(pw, hash)", "/* argon2.verify(h, pw)", "   speakeasy.totp.verify(x) */", "const x = 1;")),
    ("Python def check_password", "a.py", src("def check_password(self, raw):", "    return raw == self.raw")),
    ("Python async def check_password_hash", "a.py", src("async def check_password_hash(h, pw):", "    return True")),
    ("Python def checkpw", "a.py", src("import bcrypt", "", "def checkpw(pw, hashed):", "    return True")),
    ("Python def authenticate", "a.py", src("from django.contrib.auth import authenticate", "", "def authenticate(request):", "    return None")),
    ("authenticate without the django import", "a.py", src("user = backend.authenticate(request)", "user = authenticate(request)")),
    ("authenticate from another module", "a.py", src("from myapp.auth import authenticate", "user = authenticate(request)")),
    ("checkpw without a bcrypt import", "a.py", src("ok = checkpw(pw, hashed)")),
    (".verify without a library import", "a.py", src("ok = signer.verify(sig, data)")),
    ("Python jwt.verify beside a passlib import", "a.py", src("from passlib.context import CryptContext", "payload = jwt.verify(token)")),
    ("Python jws.verify beside an argon2 import", "a.py", src("import argon2", "ok = jws.verify(token)")),
    ("compare_digest", "a.py", src("import hmac", "ok = hmac.compare_digest(a, b)")),
    ("Python scrypt and pbkdf2", "a.py", src("import hashlib", "k = hashlib.scrypt(pw, salt=s, n=2, r=1, p=1)", "hashlib.pbkdf2_hmac('sha256', pw, s, 1)")),
    ("OAuth2PasswordRequestForm import only", "a.py", src("from fastapi.security import OAuth2PasswordRequestForm")),
    ("OAuth2PasswordRequestForm parenthesized import only", "a.py", src("from fastapi.security import (", "    OAuth2PasswordRequestForm,", "    OAuth2PasswordBearer,", ")")),
    ("a longer name that starts with OAuth2PasswordRequestForm", "a.py", src("async def token(form: OAuth2PasswordRequestFormExtra = Depends()):", "    return form")),
    ("a longer name that starts with OAuth2PasswordRequestFormStrict", "a.py", src("async def token(form: OAuth2PasswordRequestFormStrictly = Depends()):", "    return form")),
    ("Python call in a comment", "a.py", src("# bcrypt.checkpw(pw, h)", "import bcrypt")),
    ("a Python name in a JS file", "a.js", src("const ok = check_password(pw);")),
    ("a JS call in a Python file", "a.py", src("ok = bcrypt.compare(pw, hash)")),
)

# (provider call line, token the row names)
PROVIDERS = (
    ("await supabase.auth.signInWithPassword({ email, password });", "signInWithPassword"),
    ("await supabase.auth.signInWithOtp({ email });", "signInWithOtp"),
    ('await supabase.auth.verifyOtp({ email, token, type: "email" });', "verifyOtp"),
    ("await signInWithEmailAndPassword(auth, email, password);", "signInWithEmailAndPassword"),
    ("const out = await client.send(new InitiateAuthCommand(params));", "InitiateAuthCommand"),
    ("await idp.send(new AdminInitiateAuthCommand(input));", "AdminInitiateAuthCommand"),
    ('const op = "InitiateAuth";', "InitiateAuth"),
    ("cognito.initiateAuth(params, cb);", "initiateAuth"),
    ("const tok = await passwordGrant(user, pw);", "passwordGrant"),
)

# a token that is attempt-limit evidence, written as it appears in code (the row names the matched text)
LIMIT_TOKENS = ("rate-limit", "rate_limit", "ratelimit", "RateLimit", "limiter", "Limiter", "lockout", "locked-until", "locked_until", "lockedUntil", "failed-login", "failed_logins",
                "failedLogin", "failed_attempt", "failedAttempts", "login_attempts", "loginAttempts", "max-attempts", "max_login_attempts", "maxLoginAttempts", "attempt-count",
                "attemptCount", "express-brute", "express_brute", "slowapi", "django-axes", "django_axes", "AxesMiddleware", "AxesBackend", "AxesStandaloneBackend",
                "@nestjs/throttler", "ThrottlerGuard", "RateThrottle", "DEFAULT_THROTTLE", "express-slow-down", "slowDown", "429", "Too Many Requests", "too many requests")
# a token that is not: a bare throttle, a case-sensitive name in the wrong case, a word that only contains a token
NOT_LIMIT_TOKENS = ("delimiter", "Delimiter", "DELIMITER", "throttle", "Throttle", "throttleRequests", "slowdown", "axesmiddleware", "throttlerguard", "4290", "x429y")

# (verb, route, METHOD the row names, whether the route is a sign-in, one-time-code or reset candidate)
ROUTES = tuple(("post", p, "POST", True) for p in (
    "/login", "/Login", "/LOGIN", "/log-in", "/log_in", "/sign-in", "/sign_in", "/signin", "/otp", "/verify-otp", "/verify_otp", "/mfa", "/2fa", "/two-factor", "/twoFactor", "/totp",
    "/forgot", "/forgot-password", "/reset-password", "/password-reset", "/passwordReset", "/api/v1/auth/login/", "/users/:id/login")) + (
    ("put", "/login", "PUT", True), ("patch", "/login", "PATCH", True), ("delete", "/login", "DELETE", True), ("all", "/login", "ANY", True), ("get", "/login", "GET", False)) + tuple(
    ("post", p, "POST", False) for p in ("/logout", "/login-help", "/signup", "/register", "/verify-email", "/password-strength", "/password", "/reset", "/otp-settings", "/users", "/auth/token"))

GOLD = {  # three candidate files: a route first, a check with a 429 in the same file, a Python check; and one that is no candidate
    "package.json": '{ "name": "acme-shop" }\n',
    "src/server.js": src('const express = require("express");', 'const bcrypt = require("bcrypt");', "const app = express();", "",
                         'app.post("/signin", async (req, res) => {', '  const ok = await bcrypt.compare(req.body.password, "hash");', "  res.json({ ok });", "});"),
    "src/otp.js": src('const { authenticator } = require("otplib");', "", "function check(code) {", '  return authenticator.check(code, "secret");', "}", "function slow() {", "  return 429;", "}"),
    "lib/auth.py": src("import bcrypt", "", "", "def ok(pw, hashed):", "    return bcrypt.checkpw(pw, hashed)"),
    "lib/plain.js": src("exports.add = (a, b) => a + b;"),
}
GOLD_ROWS = [
    ("lib/auth.py", 5, MISSING, miss(CRED)),
    ("src/otp.js", 4, EVIDENCE, found(CRED, FILE_KIND, "429", "src/otp.js:7")),
    ("src/server.js", 5, MISSING, miss("POST /signin")),
]


class AttemptLimitMap(unittest.TestCase):
    def test_every_credential_check_is_a_row(self):
        for name, rel, text, line in TRIGGERS:
            with self.subTest(name):
                self.assertEqual(scan({rel: text}), ([(rel, line, MISSING, miss(CRED))], 1, 1))

    def test_non_checks_give_no_row(self):
        for name, rel, text in QUIET:
            with self.subTest(name):
                self.assertEqual(scan({rel: text}), ([], 0, 0))

    def test_a_provider_call_in_the_file_is_the_first_tier(self):
        for line, token in PROVIDERS:
            with self.subTest(token):
                self.assertEqual(rows({"a.js": LOGIN + line + "\n"}), [("a.js", 3, EVIDENCE, found(CRED, PROVIDER_KIND, token, "a.js:5"))])
        self.assertEqual(rows({"a.js": LOGIN + "await client.signInWithPassword(creds);\n"}), [("a.js", 3, MISSING, miss(CRED))], "only the .auth. call is a provider call")
        both = LOGIN + 'const x = "rateLimit";\nawait supabase.auth.signInWithOtp({ email });\n'
        self.assertEqual(rows({"a.js": both}), [("a.js", 3, EVIDENCE, found(CRED, PROVIDER_KIND, "signInWithOtp", "a.js:6"))], "a provider call outranks a limiter in the same file")

    def test_attempt_limit_code_in_the_file_is_the_second_tier(self):
        for token in LIMIT_TOKENS:
            with self.subTest(token):
                self.assertEqual(rows({"a.js": LOGIN + 'const x = "%s";\n' % token}), [("a.js", 3, EVIDENCE, found(CRED, FILE_KIND, token, "a.js:5"))])
        for token in NOT_LIMIT_TOKENS:
            with self.subTest("not evidence: " + token):
                self.assertEqual(rows({"a.js": LOGIN + 'const x = "%s";\n' % token}), [("a.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"a.js": LOGIN + 'const delimiter = ",";\nconst parts = text.split(delimiter);\n'}), [("a.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"a.py": PY_LOGIN + "limit = unlimited_requests\n"}), [("a.py", 3, MISSING, miss(CRED))])

    def test_a_429_is_evidence_only_in_the_file_itself(self):
        self.assertEqual(rows({"src/login.js": LOGIN, "src/other.js": src("res.status(429).end();")}), [("src/login.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"src/login.js": LOGIN, "src/other.js": src('res.send("Too Many Requests");')}), [("src/login.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"src/login.js": LOGIN + "res.status(429).end();\n"}), [("src/login.js", 3, EVIDENCE, found(CRED, FILE_KIND, "429", "src/login.js:5"))])

    def test_a_token_only_in_a_comment_is_not_evidence(self):
        for rel, base, text in (("a.js", LOGIN, "// rateLimit(app)\n/* lockout\n   Too Many Requests */\n"), ("a.py", PY_LOGIN, "# rate_limit = 5\n# 429\n")):
            with self.subTest(rel):
                self.assertEqual(rows({rel: base + text}), [(rel, 3, MISSING, miss(CRED))])
                self.assertEqual(rows({"src/login" + rel[1:]: base, "src/other" + rel[1:]: text}), [("src/login" + rel[1:], 3, MISSING, miss(CRED))])

    def test_attempt_limit_code_in_the_package_is_the_third_tier_and_the_first_file_wins(self):
        files = {"package.json": "{}\n", "src/login.js": LOGIN, "src/z.js": src('const a = "lockout";'), "src/limits.js": src("const b = 1;", 'const r = require("express-rate-limit");')}
        self.assertEqual(rows(files), [("src/login.js", 3, EVIDENCE, found(CRED, PKG_KIND, "rate-limit", "src/limits.js:2"))])
        self.assertEqual(rows({"src/login.js": LOGIN, "src/a.js": src("", "", "export const l = lockedUntil;", "x(failedLogin);")}),
                         [("src/login.js", 3, EVIDENCE, found(CRED, PKG_KIND, "lockedUntil", "src/a.js:3"))], "the first match in the file")

    def test_a_package_marker_limits_the_search_to_its_directory(self):
        cases = (
            ("a nested directory of the package", {"package.json": "{}", "apps/web/package.json": "{}", "apps/web/login.js": LOGIN, "apps/web/lib/limit.js": LIMIT}, "apps/web/lib/limit.js:1"),
            ("a nested package below the candidate's", {"apps/web/package.json": "{}", "apps/web/login.js": LOGIN, "apps/web/pkgs/rl/package.json": "{}", "apps/web/pkgs/rl/index.js": LIMIT}, "apps/web/pkgs/rl/index.js:1"),
            ("no marker anywhere: DIR is the package", {"a/login.js": LOGIN, "b/limit.js": LIMIT}, "b/limit.js:1"),
            ("the marker is below the candidate", {"login.js": LOGIN, "deep/package.json": "{}", "deep/limit.js": LIMIT}, "deep/limit.js:1"),
        )
        for name, files, at in cases:
            with self.subTest(name):
                got = rows(files)
                self.assertEqual(len(got), 1, got)
                self.assertEqual(got[0][2:], (EVIDENCE, found(CRED, PKG_KIND, "rateLimit", at)))
        for name, files in (("a sibling package", {"apps/web/package.json": "{}", "apps/web/login.js": LOGIN, "apps/api/package.json": "{}", "apps/api/limit.js": LIMIT}),
                            ("the parent package", {"package.json": "{}", "lib/limit.js": LIMIT, "apps/web/package.json": "{}", "apps/web/login.js": LOGIN})):
            with self.subTest("no evidence from " + name):
                self.assertEqual([r[2] for r in rows(files)], [MISSING])

    def test_every_package_marker_file_makes_a_package_root(self):
        for marker in MARKER_FILES:
            with self.subTest(marker):
                files = {"svc/login.js": LOGIN, "other/limit.js": LIMIT}
                self.assertEqual([r[2] for r in rows(files)], [EVIDENCE], "without the marker the whole DIR is the package")
                self.assertEqual([r[2] for r in rows({**files, "svc/" + marker: "x\n"})], [MISSING], "the marker makes svc a package of its own")

    def test_a_route_only_candidate_falls_back_to_a_provider_call_in_the_package(self):
        route = ("app/api/login/route.ts", src("export async function POST(request: Request) {", "  return new Response(null);", "}"))
        provider = ("lib/auth.ts", src("export const go = () => supabase.auth.signInWithPassword(c);"))
        at = "POST /api/login"
        self.assertEqual(rows(dict([route, provider, ("package.json", "{}")])), [(route[0], 1, EVIDENCE, found(at, PROVIDER_PKG_KIND, "signInWithPassword", "lib/auth.ts:1"))])
        limit = ("lib/limit.js", LIMIT)
        self.assertEqual(rows(dict([route, provider, limit])), [(route[0], 1, EVIDENCE, found(at, PKG_KIND, "rateLimit", "lib/limit.js:1"))], "the package limiter tier comes first")
        self.assertEqual(rows(dict([route])), [(route[0], 1, MISSING, miss(at))])
        own = (route[0], route[1].replace("return", "await supabase.auth.verifyOtp(x);\n  return"))
        self.assertEqual(rows(dict([own])), [(route[0], 1, EVIDENCE, found(at, PROVIDER_KIND, "verifyOtp", route[0] + ":2"))])
        self.assertEqual(rows({"package.json": "{}", "x/package.json": "{}", route[0]: route[1], "x/lib/auth.ts": provider[1]}),
                         [(route[0], 1, EVIDENCE, found(at, PROVIDER_PKG_KIND, "signInWithPassword", "x/lib/auth.ts:1"))], "a provider call in a nested package")
        sibling = {"apps/web/package.json": "{}", "apps/web/" + route[0]: route[1], "apps/api/package.json": "{}", "apps/api/" + provider[0]: provider[1]}
        self.assertEqual(rows(sibling), [("apps/web/" + route[0], 1, MISSING, miss(at))], "a provider call in a sibling package")

    def test_a_candidate_with_a_credential_check_ignores_a_provider_elsewhere_in_the_package(self):
        files = {"package.json": "{}", "src/login.js": LOGIN, "lib/auth.ts": src("export const go = () => supabase.auth.signInWithPassword(c);")}
        self.assertEqual(rows(files), [("src/login.js", 3, MISSING, miss(CRED))])

    def test_a_file_that_is_not_source_is_no_evidence(self):
        files = {"src/login.js": LOGIN, "package.json": '{ "dependencies": { "express-rate-limit": "7" } }\n', "docs.md": "rateLimit\n", "limits.txt": "lockout\n", "ci.yml": "429\n", "src/a.json": '{"x": "limiter"}'}
        self.assertEqual(rows(files), [("src/login.js", 3, MISSING, miss(CRED))])

    def test_route_keywords_and_methods(self):
        files = {"r%02d.js" % i: EXPRESS + 'app.%s("%s", (req, res) => res.end());\n' % (verb, route) for i, (verb, route, _, _) in enumerate(ROUTES)}
        want = [("r%02d.js" % i, 3, MISSING, miss("%s %s" % (meth, route))) for i, (_, route, meth, yes) in enumerate(ROUTES) if yes]
        got = rows(files)
        self.assertEqual(got, want)
        self.assertGreater(len(want), 25)
        self.assertEqual([m for _, _, m, yes in ROUTES if not yes][:1], ["GET"])

    def test_python_route_methods(self):
        head = src("from flask import Flask", "", "app = Flask(__name__)", "", "")
        files = {"both.py": head + src('@app.route("/login", methods=["GET", "POST"])', "def login():", '    return "x"'),
                 "get.py": head + src('@app.route("/signin", methods=["GET"])', "def signin():", '    return "x"'),
                 "default.py": head + src('@app.route("/mfa")', "def mfa():", '    return "x"'),
                 "post.py": head + src('@app.post("/forgot-password")', "def forgot():", '    return "x"')}
        self.assertEqual(rows(files), [("both.py", 6, MISSING, miss("GET|POST /login")), ("post.py", 6, MISSING, miss("POST /forgot-password"))])

    def test_server_actions(self):
        files = {"a/actions.ts": src('"use server";', "", "export async function saveNote(text: string) {", "  return text;", "}", "", "export async function signIn(data: FormData) {", "  return data;", "}"),
                 "b/actions.ts": src('"use server";', "", "export async function saveNote(text: string) {", "  return text;", "}"),
                 "c/actions.ts": src('"use server";', "", "export const resetPassword = async (email: string) => {", "  return email;", "};"),
                 "d/actions.ts": src("export async function signIn(data: FormData) {", "  return data;", "}")}
        self.assertEqual(rows(files), [("a/actions.ts", 7, MISSING, miss("ACTION signIn")), ("c/actions.ts", 3, MISSING, miss("ACTION resetPassword"))])

    def test_the_row_is_at_the_first_trigger_and_the_route_wins_a_tie(self):
        route_first = EXPRESS + src("", 'const bcrypt = require("bcrypt");', 'app.post("/login", async (req, res) => {', "  const ok = await bcrypt.compare(pw, h);", "  res.json({ ok });", "});")
        check_first = src('const express = require("express");', 'const bcrypt = require("bcrypt");', "const check = (pw, h) => bcrypt.compare(pw, h);", "const app = express();",
                          'app.post("/login", async (req, res) => {', "  res.json({ ok: await check(1, 2) });", "});")
        same_line = src('const express = require("express");', 'const bcrypt = require("bcrypt");', "const app = express();",
                        'app.post("/login", async (req, res) => { res.json({ ok: await bcrypt.compare(req.body.pw, "h") }); });')
        many = LOGIN + src("const again = bcrypt.compareSync(a, b);", "const more = bcrypt.compare(c, d);")
        self.assertEqual(rows({"a.js": route_first}), [("a.js", 5, MISSING, miss("POST /login"))])
        self.assertEqual(rows({"a.js": check_first}), [("a.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"a.js": same_line}), [("a.js", 4, MISSING, miss("POST /login"))])
        self.assertEqual(rows({"a.js": many + EXPRESS + 'app.post("/login", f);\napp.post("/mfa", f);\n'}), [("a.js", 3, MISSING, miss(CRED))], "one row per candidate file")

    def test_ignored_files_give_no_row(self):
        files = {d + "/a.js": LOGIN for d in sorted(header_config.PRUNE)}
        files.update({"src/vendor/deep/a.js": LOGIN, "src/nested/tests/a.js": LOGIN, "src/a.test.js": LOGIN, "src/a.spec.ts": LOGIN, "src/app.min.js": LOGIN,
                      "src/test_a.py": PY_LOGIN, "src/a_test.py": PY_LOGIN, "conftest.py": PY_LOGIN, "src/a.mts": LOGIN, "src/a.txt": LOGIN, "notes.md": LOGIN, "src/a.json": LOGIN})
        self.assertGreater(len(files), 30)
        self.assertEqual(scan(files), ([], 0, 0))

    def test_ignored_files_are_no_evidence(self):
        files = {d + "/a.js": LIMIT for d in sorted(header_config.PRUNE)}
        files.update({"src/vendor/deep/a.js": LIMIT, "src/nested/tests/a.js": LIMIT, "src/a.test.js": LIMIT, "src/a.spec.ts": LIMIT, "src/app.min.js": LIMIT,
                      "src/test_a.py": LIMIT, "src/a_test.py": LIMIT, "conftest.py": LIMIT, "src/a.mts": LIMIT})
        files["src/login.js"] = LOGIN
        self.assertEqual(rows(files), [("src/login.js", 3, MISSING, miss(CRED))])

    def test_symlinks_are_not_followed_or_counted(self):
        with tempfile.TemporaryDirectory() as out:
            write(out, {"outside/limit.js": LIMIT, "outside/login.js": LOGIN})

            def link(d):
                os.symlink("real.js", d / "link.js")
                os.symlink("sub", d / "linkdir")
                os.symlink("missing.js", d / "broken.js")
                os.symlink(Path(out) / "outside", d / "elsewhere")
                os.symlink(Path(out) / "outside" / "login.js", d / "far.js")
                os.symlink(Path(out) / "outside" / "limit.js", d / "sub" / "limit.js")

            self.assertEqual(rows({"real.js": LOGIN, "sub/in.js": LOGIN}, prep=link),
                             [("real.js", 3, MISSING, miss(CRED)), ("sub/in.js", 3, MISSING, miss(CRED))], "a symlink to a login file, a directory or outside DIR adds no row and no evidence")

    def test_a_symlinked_package_marker_does_not_split_the_package(self):
        files = {"svc/login.js": LOGIN, "other/limit.js": LIMIT, "base.json": "{}\n"}
        for marker in MARKER_FILES:
            for target in ("../base.json", "gone.json"):  # a live link and a dangling one
                with self.subTest("%s -> %s" % (marker, target)):
                    got = rows(files, prep=lambda d: os.symlink(target, d / "svc" / marker))
                    self.assertEqual([r[2] for r in got], [EVIDENCE], "svc stays inside the one package, so the limiter in other/ counts")

    def test_an_escaped_slash_in_a_regex_literal_opens_no_comment(self):
        trim = r'const trim = (s) => s.replace(/\/*$/, "");'  # `\/*` once opened a block comment that blanked the rest of the file
        slash = r"const ok = (p, pw, h) => /\//.test(p) && bcrypt.compare(pw, h);"  # `\//` once opened a line comment over the call
        self.assertEqual(rows({"a.js": src('const bcrypt = require("bcrypt");', trim, "const ok = (pw, h) => bcrypt.compare(pw, h);")}), [("a.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"b.js": src('const bcrypt = require("bcrypt");', slash)}), [("b.js", 2, MISSING, miss(CRED))])
        self.assertEqual(rows({"c.js": EXPRESS + trim + '\napp.post("/login", (req, res) => res.end());\n'}), [("c.js", 4, MISSING, miss("POST /login"))], "a route after the literal")
        self.assertEqual(rows({"d.js": src('const bcrypt = require("bcrypt");', trim, "/* bcrypt.compare(pw, h) */", "// bcrypt.compare(pw, h)")}), [], "a real comment after the literal is still a comment")

    def test_mask_keeps_the_code_after_an_escaped_slash(self):
        mask = tenant_scope_check.mask
        self.assertIs(route_auth_map.mask, mask)
        self.assertIs(header_config.mask, mask)
        for code in (r's.replace(/\/*$/, ""); bcrypt.compare(a, b);', r"x = /\//.test(p); bcrypt.compare(a, b);"):
            with self.subTest(code):
                self.assertEqual(mask(code), code)
                self.assertEqual(mask(code + " /* gone */ // gone"), code + " " * 19, "comments after it are still blanked")
        self.assertEqual((mask("// a\nx"), mask("/* a */x")), ("    \nx", "       x"), "a comment at offset 0 is still a comment")

    def test_a_file_over_1_mb_is_skipped_and_one_at_the_limit_is_read(self):
        self.assertEqual(header_config.MAX_BYTES, 1_000_000)
        limit = A.MAX_BYTES

        def padded(text, size):
            return text + "//" + "x" * (size - len(text) - 2) + "\n"

        self.assertEqual(len(padded(LOGIN, limit).encode()), limit + 1)
        at = padded(LOGIN, limit - 1)
        self.assertEqual(len(at.encode()), limit)
        self.assertEqual(rows({"big.js": at}), [("big.js", 3, MISSING, miss(CRED))])
        self.assertEqual(rows({"big.js": padded(LOGIN, limit)}), [])
        self.assertEqual(rows({"login.js": LOGIN, "big.js": padded(LIMIT, limit)}), [("login.js", 3, MISSING, miss(CRED))], "a skipped file is no evidence")

    def test_a_repo_below_a_parent_named_tests_is_still_scanned(self):
        want = rows(GOLD)
        self.assertEqual(want, GOLD_ROWS)
        for parent in ("tests", "test", "fixtures", "docs", "node_modules", ".cache", "__tests__"):
            with self.subTest(parent):
                self.assertEqual(rows(GOLD, under=parent), want)

    def test_bad_bytes_and_a_bom_do_not_drop_a_file(self):
        files = {"bad.js": b'const bcrypt = require("bcrypt");\nconst s = "\xff\xfe";\nbcrypt.compare(a, b); // caf\xe9\n',
                 "bom.js": b'\xef\xbb\xbfimport { compare } from "bcryptjs";\nconst ok = compare(a, b);\n'}
        self.assertEqual(rows(files), [("bad.js", 3, MISSING, miss(CRED)), ("bom.js", 2, MISSING, miss(CRED))])

    def test_an_unreadable_file_is_skipped(self):
        def lock(d): os.chmod(d / "locked.js", 0)

        with tempfile.TemporaryDirectory() as t:
            write(t, {"locked.js": LOGIN})
            os.chmod(Path(t) / "locked.js", 0)
            readable = os.access(Path(t) / "locked.js", os.R_OK)
        if readable: self.skipTest("file permissions are not enforced here")
        self.assertEqual(scan({"locked.js": LOGIN, "ok.js": LOGIN}, prep=lock), ([("ok.js", 3, MISSING, miss(CRED))], 1, 1))

    def test_rows_are_sorted_and_tab_separated_on_stdout(self):
        res = run(self.gold_dir)
        self.assertEqual((res.returncode, res.stderr), (0, SUMMARY % (3, 2)))
        self.assertEqual(res.stdout, "".join("%s\t%d\t%s\t%s\n" % r for r in GOLD_ROWS))
        files = {"z.js": LOGIN, "a/b.js": LOGIN, "a.js": LOGIN, "m.py": PY_LOGIN}
        got = rows(files)
        self.assertEqual([r[0] for r in got], ["a.js", "a/b.js", "m.py", "z.js"])
        self.assertEqual(got, sorted(got))

    def test_no_candidate_summary(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, {"lib/plain.js": src("exports.add = (a, b) => a + b;")})
            res = run(t)
            self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", NO_CANDIDATE))
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(run(t).stderr, NO_CANDIDATE, "an empty directory")

    def test_a_repeat_run_gives_identical_output(self):
        first, second = run(self.gold_dir), run(self.gold_dir)
        self.assertEqual((first.returncode, first.stdout, first.stderr), (second.returncode, second.stdout, second.stderr))
        self.assertEqual(first.stdout.count("\n"), 3)

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, {"f.js": LOGIN})
            for argv in ([], [t, t], [os.path.join(t, "nope")], [os.path.join(t, "f.js")], ["--bogus"]):
                with self.subTest(argv):
                    res = run(*argv)
                    self.assertEqual((res.returncode, res.stdout, res.stderr), (2, "", USAGE))

    def test_a_control_character_in_a_file_name_cannot_forge_a_row(self):
        with tempfile.TemporaryDirectory() as t:
            try: write(t, {"we\tird.js": LOGIN, "a\nb.js": LOGIN})
            except OSError: self.skipTest("this file system refuses such names")
            res = run(t)
            self.assertEqual(res.returncode, 0, res.stderr)
            got = [line.split("\t") for line in res.stdout.splitlines()]
            self.assertEqual([g[0] for g in got], ["a?b.js", "we?ird.js"])
            self.assertTrue(all(len(g) == 4 for g in got), got)
            self.assertEqual(res.stderr, SUMMARY % (2, 2))

    def test_hostile_files_stay_fast(self):
        """Each file is under 1 MB and would take minutes with a gate regex that spans blank lines, an unbounded brace list or an unanchored require brace."""
        cases = {
            "blank lines after a python import": ({"x.py": "import bcrypt\n" + "\n" * 900000 + "ok = bcrypt.checkpw(a, b)\n"}, [("x.py", 900002, MISSING, miss(CRED))]),
            "unclosed import braces": ({"x.js": 'const x = require("bcryptjs");\n' + "import {" * 40000 + "\ncompare(a, b);\n"}, []),
            "a run of braces": ({"x.js": 'const x = require("bcryptjs");\n' + "{" * 900000 + "\ncompare(a, b);\n"}, []),
            "unclosed python import parentheses": ({"x.py": "from django.contrib.auth import (\n" * 25000 + "x = 1\n" * 100 + "authenticate(u)\n"}, []),
        }
        for name, (files, want) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as t:
                write(t, files)
                res = run(t, timeout=120)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual([tuple(l.split("\t")[:3]) for l in res.stdout.splitlines()], [(w[0], str(w[1]), w[2]) for w in want])

    def test_the_sibling_helpers_are_reused_not_copied(self):
        for mod, names in ((header_config, ("PRUNE", "SKIP_FILE", "MAX_BYTES")), (route_auth_map, ("scan", "read", "TEST", "EXT", "pymask")), (tenant_scope_check, ("mask", "lineno"))):
            for name in names:
                with self.subTest(name):
                    self.assertIs(getattr(A, name), getattr(mod, name))
        self.assertIs(A.PRUNE, header_config.PRUNE)

    def test_writes_nothing_beside_the_script(self):
        names = ["attempt_limit_map.py", "dynamic_probe.py", "header_config.py", "route_auth_map.py", "tenant_scope_check.py"]
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as fx:
            for n in names:
                shutil.copy(SK / n, t)
            write(fx, GOLD)
            res = subprocess.run([sys.executable, "-I", str(Path(t) / "attempt_limit_map.py"), fx], capture_output=True, text=True)
            self.assertEqual((res.returncode, res.stdout), (0, "".join("%s\t%d\t%s\t%s\n" % r for r in GOLD_ROWS)))
            self.assertEqual(sorted(os.listdir(t)), names)
            self.assertEqual(sorted(os.listdir(fx)), ["lib", "package.json", "src"])

    def test_review_checks_full_wiring(self):
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, files):
                g = Path(t) / name
                write(g, files)
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g", {"a/package.json": "{}", "a/src/a.js": LOGIN, "b/package.json": "{}", "b/src/b.js": LOGIN + LIMIT,
                                                                                   "c/package.json": "{}", "c/src/c.js": LOGIN + "const x = await supabase.auth.verifyOtp(y);\n"}))],
                               capture_output=True, text=True, env=env)
            got = [(x["file"], x["line"], x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "attempt-limit"]
            self.assertEqual(got, [("a/src/a.js", 3, MISSING, miss(CRED))], "the evidence rows stay in the script's own output")
            self.assertIn(SUMMARY % (3, 1), r.stderr)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g2", {"a.ts": "export const a = 1;\n"}))], capture_output=True, text=True, env=env)
            self.assertIn("attempt-limit (SKIPPED: no credential check or sign-in route)", r.stderr)
            self.assertEqual([(x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "attempt-limit"], [("not-checked", "SKIPPED: no credential check or sign-in route")])

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.td.cleanup)
        cls.gold_dir = Path(cls.td.name) / "gold"
        write(cls.gold_dir, GOLD)


if __name__ == "__main__":
    unittest.main()
