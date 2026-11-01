#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.secret-env-fallback, perun.js.public-env-secret (js.yml) and
perun.py.secret-env-fallback (py.yml).

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` (JavaScript) or `# ruleid: <id>` (Python) comment marks
the NEXT line as a required finding, an `ok: <id>` comment marks the next line as one that must stay clean, and every
unannotated line must stay clean too (so must a copy of a fixture under a test path or a test-runner config name). All names and
values are fictional.
RULES=<dir> checks another copy of the rules (used to show the cases fail without them). The live check needs semgrep and
prints SKIP without it (CI installs none); the offline checks always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
JSFB, PUB, PYFB = "perun.js.secret-env-fallback", "perun.js.public-env-secret", "perun.py.secret-env-fallback"
IDS = (JSFB, PUB, PYFB)

# A secret-named read with a literal fallback is reported unless its name carries a public prefix (that is the other rule's);
# a public-prefixed read whose name ends in a secret stem is reported with or without a fallback.
ENV_JS = r'''
// Secret-named reads with a string-literal fallback.
// ruleid: perun.js.secret-env-fallback
const jwtSecret = process.env.ACME_JWT_SECRET || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const dbPassword = process.env.ACME_DB_PASSWORD ?? "acme-dev-password";
// ruleid: perun.js.secret-env-fallback
const ghToken = process.env.ACME_GH_TOKEN || 'acme-dev-token';
// ruleid: perun.js.secret-env-fallback
const secretKey = process.env.ACME_SECRET_KEY ?? "acme-dev-key";
// ruleid: perun.js.secret-env-fallback
const apiKey = process.env.ACME_API_KEY || "acme-dev-key";
// ruleid: perun.js.secret-env-fallback
const smtpPass = process.env.ACME_SMTP_PASS || "acme-dev-pass";
// ruleid: perun.js.secret-env-fallback
const dbPwd = process.env.ACME_DB_PWD ?? "acme-dev-pwd";
// ruleid: perun.js.secret-env-fallback
const hook = process.env.ACME_WEBHOOK_SECRET ?? "acme-dev-hook";
// ruleid: perun.js.secret-env-fallback
const sshPassphrase = process.env.ACME_SSH_PASSPHRASE || "acme-dev-pass";
// ruleid: perun.js.secret-env-fallback
const serviceRole = process.env.ACME_SERVICE_ROLE_KEY ?? "acme-dev-role";
// ruleid: perun.js.secret-env-fallback
const keystorePw = process.env.ACME_KEYSTORE_PASSWORD || "acme-dev-keystore";
// ruleid: perun.js.secret-env-fallback
const lowerName = process.env.acme_jwt_secret || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const camelName = process.env.acmeJwtSecret || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const notPublic = process.env.ACME_NEXT_PUBLIC_SECRET || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const bracket = process.env["ACME_JWT_SECRET"] || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const bracketNullish = process.env['ACME_JWT_SECRET'] ?? "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const meta = import.meta.env.ACME_JWT_SECRET || "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
const metaNullish = import.meta.env.ACME_API_TOKEN ?? "acme-dev-token";
// ruleid: perun.js.secret-env-fallback
jwt.sign(payload, process.env.ACME_JWT_SECRET || "acme-dev-secret");
// ruleid: perun.js.secret-env-fallback
const cfg = { secret: process.env.ACME_JWT_SECRET ?? "acme-dev-secret", ttl: 60 };
// ruleid: perun.js.secret-env-fallback
const wrapped = String(process.env.ACME_JWT_SECRET || "acme-dev-secret");
// ruleid: perun.js.secret-env-fallback
const split = process.env.ACME_JWT_SECRET
  || "acme-dev-secret";

// Logical-assignment defaults on process.env (||= and ??=), dot or bracket form, either quote style.
// ruleid: perun.js.secret-env-fallback
process.env.ACME_JWT_SECRET ||= "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
process.env.ACME_JWT_SECRET ??= 'acme-dev-secret';
// ruleid: perun.js.secret-env-fallback
process.env["ACME_JWT_SECRET"] ||= "acme-dev-secret";
// ruleid: perun.js.secret-env-fallback
process.env["ACME_JWT_SECRET"] ??= "acme-dev-secret";
// ok: perun.js.secret-env-fallback
process.env.ACME_TOKEN_TTL ||= "3600";
// ok: perun.js.secret-env-fallback
process.env.ACME_JWT_SECRET ||= readSecret();

// A destructuring default from process.env: const, let or var, alone or with other keys around it.
// ruleid: perun.js.secret-env-fallback
const { ACME_SECRET_KEY = "acme-dev-secret" } = process.env;
// ruleid: perun.js.secret-env-fallback
let { ACME_PORT, ACME_DB_PWD = "acme-dev-pwd" } = process.env;
// ruleid: perun.js.secret-env-fallback
var { ACME_HOST = "localhost", ACME_WEBHOOK_SECRET = "acme-dev-hook", ACME_REGION } = process.env;
// ruleid: perun.js.secret-env-fallback
const {
  ACME_STAGE = "dev",
  ACME_JWT_SECRET = "acme-dev-secret",
  ...restEnv
} = process.env;

// Near misses: a name that does not end in a secret stem, however secret-looking its start or middle.
// ok: perun.js.secret-env-fallback
const tokenTtl = process.env.ACME_TOKEN_TTL || "3600";
// ok: perun.js.secret-env-fallback
const resetUrl = process.env.ACME_PASSWORD_RESET_URL ?? "/acme/reset";
// ok: perun.js.secret-env-fallback
const expires = process.env.ACME_JWT_EXPIRES_IN || "1h";
// ok: perun.js.secret-env-fallback
const secretName = process.env.ACME_SECRET_NAME || "acme-secret";
// ok: perun.js.secret-env-fallback
const maxTokens = process.env.ACME_MAX_TOKENS || "100";
// ok: perun.js.secret-env-fallback
const cacheKey = process.env.ACME_CACHE_KEY || "acme-cache";
// ok: perun.js.secret-env-fallback
const accessKeyId = process.env.ACME_ACCESS_KEY_ID || "acme-key-id";
// ok: perun.js.secret-env-fallback
const workDir = process.env.PWD || "/srv/acme";
// ok: perun.js.secret-env-fallback
const camelTtl = process.env.acmeTokenTtl || "3600";

// Near misses: a literal that is empty, one character or a sentinel, and fallbacks that are not string literals.
// ok: perun.js.secret-env-fallback
const emptyFallback = process.env.ACME_JWT_SECRET || "";
// ok: perun.js.secret-env-fallback
const oneChar = process.env.ACME_JWT_SECRET ?? "x";
// ok: perun.js.secret-env-fallback
const sentinel = process.env.ACME_JWT_SECRET || "none";
// ok: perun.js.secret-env-fallback
const sentinelUndefined = process.env.ACME_API_KEY ?? "undefined";
// ok: perun.js.secret-env-fallback
const fromCall = process.env.ACME_JWT_SECRET || readSecret();
// ok: perun.js.secret-env-fallback
const fromVariable = process.env.ACME_JWT_SECRET ?? fallbackSecret;
// ok: perun.js.secret-env-fallback
const undef = process.env.ACME_JWT_SECRET || undefined;
// ok: perun.js.secret-env-fallback
const asNull = process.env.ACME_JWT_SECRET ?? null;
// ok: perun.js.secret-env-fallback
const noFallback = process.env.ACME_JWT_SECRET;
// ok: perun.js.secret-env-fallback
const bracketNoFallback = process.env["ACME_JWT_SECRET"];
// ok: perun.js.secret-env-fallback
const { ACME_JWT_SECRET } = process.env;
// ok: perun.js.secret-env-fallback
const { ACME_PORT = "3000", ACME_HOST = "localhost" } = process.env;
// ok: perun.js.secret-env-fallback
const { ACME_API_KEY = "" } = process.env;
// ok: perun.js.secret-env-fallback
const { ACME_API_TOKEN = readSecret() } = process.env;
// ok: perun.js.secret-env-fallback
const { ACME_JWT_SECRET = "acme-dev-secret" } = config;
// ok: perun.js.secret-env-fallback
const fromConfig = config.ACME_JWT_SECRET || "acme-dev-secret";

// A fallback that is a file path (starts with /, ./, ../ or ~/, or ends in a key, certificate or config extension) is
// where to look for a secret, not a known secret.
// ok: perun.js.secret-env-fallback
const credentialsFile = process.env.ACME_APPLICATION_CREDENTIALS || "./acme-sa.json";
// ok: perun.js.secret-env-fallback
const pemPath = process.env.ACME_PRIVATE_KEY ?? "/etc/acme/dev.pem";
// ok: perun.js.secret-env-fallback
const upDir = process.env.ACME_JWT_SECRET || "../acme/secret";
// ok: perun.js.secret-env-fallback
const homeDir = process.env.ACME_JWT_SECRET ?? "~/acme/secret";
// ok: perun.js.secret-env-fallback
const keyFile = process.env.ACME_SIGNING_KEY || "acme-signing.key";
// ok: perun.js.secret-env-fallback
const storeFile = process.env.ACME_SECRET || "acme-dev.keystore";
// ok: perun.js.secret-env-fallback
const yamlFile = process.env.ACME_SECRET || "acme.yml";
// ok: perun.js.secret-env-fallback
const upperExt = process.env.ACME_SECRET || "ACME-DEV.PEM";

// A public-prefixed name is left to perun.js.public-env-secret: a secret-looking name is reported there, with or without a
// fallback (and not twice), and a token or other browser-safe name with a fallback is reported by neither.
// ruleid: perun.js.public-env-secret
const sr = process.env.NEXT_PUBLIC_ACME_SERVICE_ROLE_KEY;
// ruleid: perun.js.public-env-secret
const adminPw = process.env.VITE_ACME_ADMIN_PASSWORD;
// ruleid: perun.js.public-env-secret
const secretBracket = process.env["REACT_APP_ACME_SECRET_KEY"];
// ruleid: perun.js.public-env-secret
const clientSecret = import.meta.env.EXPO_PUBLIC_ACME_CLIENT_SECRET;
// ruleid: perun.js.public-env-secret
const nuxtPrivate = process.env.NUXT_PUBLIC_ACME_PRIVATE_KEY;
// ruleid: perun.js.public-env-secret
const gatsbySigning = process.env.GATSBY_ACME_SIGNING_KEY;
// ruleid: perun.js.public-env-secret
const publicEncryption = process.env.PUBLIC_ACME_ENCRYPTION_KEY;
// ruleid: perun.js.public-env-secret
const storybookPasswd = process.env.STORYBOOK_ACME_PASSWD;
// ruleid: perun.js.public-env-secret
const vuePasscode = process.env.VUE_APP_ACME_PASSCODE;
// ruleid: perun.js.public-env-secret
const vitePwd = import.meta.env.VITE_ACME_DB_PWD;
// ruleid: perun.js.public-env-secret
const roleAlone = process.env.NEXT_PUBLIC_ACME_SERVICE_ROLE;
// ruleid: perun.js.public-env-secret
const withFallback = process.env.NEXT_PUBLIC_ACME_SECRET || "acme-dev-secret";
// ruleid: perun.js.public-env-secret
const metaFallback = import.meta.env.VITE_ACME_ADMIN_PASSWORD ?? "acme-dev-password";
// ruleid: perun.js.public-env-secret
const noUnderscore = process.env.NEXT_PUBLIC_ACME_SECRETKEY;
// ruleid: perun.js.public-env-secret
const sshPass = import.meta.env.VITE_ACME_SSH_PASSPHRASE;
// The rule matches any use of the name, a write included (a logical assignment is reported once, here, not by the fallback rule).
// ruleid: perun.js.public-env-secret
process.env.VITE_ACME_ADMIN_PASSWORD = readSecret();
// ruleid: perun.js.public-env-secret
process.env.NEXT_PUBLIC_ACME_SECRET ||= "acme-dev-secret";
// ok: perun.js.secret-env-fallback
const publicToken = process.env.NEXT_PUBLIC_ACME_API_TOKEN || "acme-dev-token";

// Near misses for the public-prefix rule: keys that are public by design, names that do not end in a secret stem, and
// a secret-looking name with no public prefix at its start.
// ok: perun.js.public-env-secret
const anon = process.env.NEXT_PUBLIC_ACME_ANON_KEY;
// ok: perun.js.public-env-secret
const publishable = process.env.NEXT_PUBLIC_ACME_PUBLISHABLE_KEY;
// ok: perun.js.public-env-secret
const maps = import.meta.env.VITE_ACME_MAPS_API_KEY;
// ok: perun.js.public-env-secret
const resetPage = process.env.NEXT_PUBLIC_ACME_PASSWORD_RESET_URL;
// ok: perun.js.public-env-secret
const beta = process.env.NEXT_PUBLIC_ACME_PRIVATE_BETA;
// ok: perun.js.public-env-secret
const siteKey = process.env.REACT_APP_ACME_SITE_KEY;
// ok: perun.js.public-env-secret
const publicTokenRead = process.env.NEXT_PUBLIC_ACME_API_TOKEN;
// ok: perun.js.public-env-secret
const serverSide = process.env.ACME_SECRET_KEY;
// ok: perun.js.public-env-secret
const prefixNotFirst = process.env.ACME_NEXT_PUBLIC_SECRET;
// ok: perun.js.public-env-secret
const fromConfigRead = config.NEXT_PUBLIC_ACME_SECRET;
// ok: perun.js.public-env-secret
const publishableKey = process.env.NEXT_PUBLIC_ACME_PUBLISHABLEKEY;
// ok: perun.js.public-env-secret
const passphraseHint = process.env.NEXT_PUBLIC_ACME_PASSPHRASE_HINT;
'''

# The fallback rule skips a test runner's own config (it is not the service), wherever the file sits; the same body in any
# other path is reported. It has no public-prefixed name: the public-prefix rule does not skip these files.
RUNNER_JS = r'''
// ruleid: perun.js.secret-env-fallback
const jwtSecret = process.env.ACME_JWT_SECRET || "acme-dev-secret";
// ok: perun.js.secret-env-fallback
const tokenTtl = process.env.ACME_TOKEN_TTL || "3600";
'''

ENV_PY = r'''
import os
from os import environ, getenv

# Secret-named reads with a non-empty string default.
# ruleid: perun.py.secret-env-fallback
JWT_SECRET = os.environ.get("ACME_JWT_SECRET", "acme-dev-secret")
# ruleid: perun.py.secret-env-fallback
DB_PASSWORD = os.getenv("ACME_DB_PASSWORD", "acme-dev-password")
# ruleid: perun.py.secret-env-fallback
GH_TOKEN = os.environ.get("ACME_GH_TOKEN", default="acme-dev-token")
# ruleid: perun.py.secret-env-fallback
SECRET_KEY = os.getenv("ACME_SECRET_KEY", default="acme-dev-key")
# ruleid: perun.py.secret-env-fallback
os.environ.setdefault("ACME_API_KEY", "acme-dev-key")
# ruleid: perun.py.secret-env-fallback
os.environ.setdefault("ACME_DB_PWD", default="acme-dev-pwd")
# ruleid: perun.py.secret-env-fallback
SMTP_PASS = os.environ.get("ACME_SMTP_PASS") or "acme-dev-pass"
# ruleid: perun.py.secret-env-fallback
HOOK = os.getenv("ACME_WEBHOOK_SECRET") or "acme-dev-hook"
# ruleid: perun.py.secret-env-fallback
LOWER = os.getenv('acme_api_token', 'acme-dev-token')
# ruleid: perun.py.secret-env-fallback
CAMEL = os.environ.get("acmeJwtSecret", "acme-dev-secret")
# ruleid: perun.py.secret-env-fallback
SSH_PASSPHRASE = os.environ.get("ACME_SSH_PASSPHRASE", "acme-dev-pass")
# ruleid: perun.py.secret-env-fallback
SERVICE_ROLE = os.getenv("ACME_SERVICE_ROLE_KEY", "acme-dev-role")
# ruleid: perun.py.secret-env-fallback
KEYSTORE_PW = os.getenv("ACME_KEYSTORE_PASSWORD", "acme-dev-keystore")
# ruleid: perun.py.secret-env-fallback
SPLIT = os.environ.get(
    "ACME_JWT_SECRET",
    "acme-dev-secret",
)

# The from-import spellings are the same reads.
# ruleid: perun.py.secret-env-fallback
FROM_GET = environ.get("ACME_JWT_SECRET", "acme-dev-secret")
# ruleid: perun.py.secret-env-fallback
FROM_GETENV = getenv("ACME_JWT_SECRET", "acme-dev-secret")
# ruleid: perun.py.secret-env-fallback
FROM_KEYWORD = environ.get("ACME_JWT_SECRET", default="acme-dev-secret")
# ruleid: perun.py.secret-env-fallback
FROM_GETENV_OR = getenv("ACME_JWT_SECRET") or "acme-dev-secret"
# ruleid: perun.py.secret-env-fallback
FROM_GET_OR = environ.get("ACME_JWT_SECRET") or "acme-dev-secret"
# ruleid: perun.py.secret-env-fallback
environ.setdefault("ACME_JWT_SECRET", "acme-dev-secret")

# Near misses: a name that does not end in a secret stem, however secret-looking its start or middle.
# ok: perun.py.secret-env-fallback
TOKEN_TTL = os.environ.get("ACME_TOKEN_TTL", "3600")
# ok: perun.py.secret-env-fallback
RESET_URL = os.getenv("ACME_PASSWORD_RESET_URL", "/acme/reset")
# ok: perun.py.secret-env-fallback
EXPIRES = os.environ.get("ACME_JWT_EXPIRES_IN", "1h")
# ok: perun.py.secret-env-fallback
SECRET_NAME = os.environ.get("ACME_SECRET_NAME", "acme-secret")
# ok: perun.py.secret-env-fallback
MAX_TOKENS = os.environ.get("ACME_MAX_TOKENS", "100")
# ok: perun.py.secret-env-fallback
CACHE_KEY = os.getenv("ACME_CACHE_KEY", "acme-cache")
# ok: perun.py.secret-env-fallback
ACCESS_KEY_ID = os.getenv("ACME_ACCESS_KEY_ID", "acme-key-id")
# ok: perun.py.secret-env-fallback
WORK_DIR = os.environ.get("PWD", "/srv/acme")
# ok: perun.py.secret-env-fallback
PORT_DEFAULT = os.environ.setdefault("ACME_PORT", "8080")

# Near misses: no default, None, an empty or one-character string, a sentinel, and defaults that are not string literals.
# ok: perun.py.secret-env-fallback
NO_DEFAULT = os.environ.get("ACME_JWT_SECRET")
# ok: perun.py.secret-env-fallback
NONE_DEFAULT = os.environ.get("ACME_JWT_SECRET", None)
# ok: perun.py.secret-env-fallback
EMPTY_DEFAULT = os.getenv("ACME_JWT_SECRET", "")
# ok: perun.py.secret-env-fallback
NONE_KEYWORD = os.getenv("ACME_JWT_SECRET", default=None)
# ok: perun.py.secret-env-fallback
EMPTY_OR = os.environ.get("ACME_JWT_SECRET") or ""
# ok: perun.py.secret-env-fallback
NONE_OR = os.environ.get("ACME_JWT_SECRET") or None
# ok: perun.py.secret-env-fallback
ONE_CHAR = os.environ.get("ACME_JWT_SECRET", "x")
# ok: perun.py.secret-env-fallback
SENTINEL = os.getenv("ACME_JWT_SECRET", "none")
# ok: perun.py.secret-env-fallback
INDEXED = os.environ["ACME_JWT_SECRET"]
# ok: perun.py.secret-env-fallback
FROM_CALL = os.environ.get("ACME_JWT_SECRET", read_secret())
# ok: perun.py.secret-env-fallback
FROM_VARIABLE = os.getenv("ACME_JWT_SECRET", fallback_secret)
# ok: perun.py.secret-env-fallback
OR_CALL = os.environ.get("ACME_JWT_SECRET") or read_secret()
# ok: perun.py.secret-env-fallback
FROM_CONFIG = config.get("ACME_JWT_SECRET", "acme-dev-secret")
# ok: perun.py.secret-env-fallback
FROM_SETTINGS = settings.get("ACME_JWT_SECRET") or "acme-dev-secret"

# A fallback that is a file path (starts with /, ./, ../ or ~/, or ends in a key, certificate or config extension) is where
# to look for a secret, not a known secret.
# ok: perun.py.secret-env-fallback
PEM_PATH = os.getenv("ACME_PRIVATE_KEY", "/etc/acme/dev.pem")
# ok: perun.py.secret-env-fallback
CREDENTIALS_FILE = os.environ.get("ACME_APPLICATION_CREDENTIALS", "./acme-sa.json")
# ok: perun.py.secret-env-fallback
HOME_PATH = os.environ.get("ACME_JWT_SECRET") or "~/acme/secret"
# ok: perun.py.secret-env-fallback
YAML_PATH = os.environ.setdefault("ACME_JWT_SECRET", "acme.yaml")
'''

FILES = {"app/config/env.js": ENV_JS, "app/config/env.ts": ENV_JS, "app/config/settings.py": ENV_PY, "app/runner.js": RUNNER_JS}
# Test, fixture and mock paths are excluded from every one of these rules, and test-runner configs from the fallback rule:
# nothing in these copies may be reported.
SKIPPED = {"tests/env.js": ENV_JS, "app/env.spec.ts": ENV_JS, "tests/settings.py": ENV_PY, "app/test_settings.py": ENV_PY,
           "app/fixtures/settings.py": ENV_PY, "app/playwright.config.ts": RUNNER_JS, "app/vitest.config.ts": RUNNER_JS,
           "web/jest.config.js": RUNNER_JS, "web/cypress.config.ts": RUNNER_JS}
ANN = re.compile(r"^\s*(?://|#)\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` or `# <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= set(IDS), out
    return out


# Offline: the floor of 3 findings and 3 near misses per rule, counted over distinct fixtures (the .js and .ts copies of one
# fixture are one set of cases).
for rid in IDS:
    for kind in ("ruleid", "ok"):
        n = sum(1 for body in {*FILES.values()} for _, r in annotated(body, kind) if r == rid)
        assert n >= 3, (rid, kind, n)
assert all(annotated(b, "ok") and annotated(b, "ruleid") for b in FILES.values())
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES, *SKIPPED],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.<lang>.<name> tail
    for x in r["results"]:
        rid = "perun." + x["check_id"].rsplit("perun.", 1)[-1]
        if rid in IDS:
            got.add((x["path"], x["start"]["line"], rid))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: ids, severities, shared test-path exclusions, and the regexes (semgrep anchors metavariable-regex at the start,
# as Python's re.match does) that carry the precision. CI installs no semgrep, so each guard the live fixtures prove is
# pinned here too: dropping one fails this file even when the live part is skipped.
JS, PY = (open(os.path.join(RULES, f)).read() for f in ("js.yml", "py.yml"))
block = lambda src, rid: src.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
excl = lambda b: (re.search(r"paths:\n\s+exclude: (\[.*\])", b) or [0, 0])[1]
rx = lambda b, mv: re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", b)
sibling = {JSFB: block(JS, "perun.js.hardcoded-credential-compare"), PUB: block(JS, "perun.js.hardcoded-credential-compare"),
           PYFB: block(PY, "perun.py.hardcoded-credential-compare")}
blocks = {JSFB: block(JS, JSFB), PUB: block(JS, PUB), PYFB: block(PY, PYFB)}
RUNNERS = ["playwright.config.*", "vitest.config.*", "jest.config.*", "cypress.config.*"]
for rid, b in blocks.items():
    assert "  severity: WARNING\n" in b and (JS if rid != PYFB else PY).count(f"- id: {rid}\n") == 1, rid
    # the credential rules' test paths, plus the four test-runner configs for the JavaScript fallback rule and nothing else
    assert excl(b) and sorted(json.loads(excl(b))) == sorted(json.loads(excl(sibling[rid])) + (RUNNERS if rid == JSFB else [])), \
        f"{rid} skips the credential rules' test paths"
    assert b.count("message: ") == 1, rid
assert all("Fail at startup" in blocks[r] for r in (JSFB, PYFB)) and "server-side" in blocks[PUB], "each message says the fix"
# a bundler inlines such a variable into client code that reads it: the claim stops there (not "every visitor", not "the bundle")
CLAIM = "inlines such variables into any client code that reads them, so the value can reach every visitor's browser"
assert CLAIM in blocks[PUB] and JS.count(CLAIM) == 2 and "browser bundle" not in JS and "ships to every visitor" not in JS, "public rule claim"
for rid in (JSFB, PYFB):  # the first literal rule is the credential-compare rule's, copied; the second skips file paths
    assert len(rx(blocks[rid], "L")) == 2 and rx(blocks[rid], "L")[:1] == rx(sibling[rid], "L"), rid
assert rx(blocks[JSFB], "L") == rx(blocks[PYFB], "L"), "the two languages share the literal rules"
lit, path = rx(blocks[JSFB], "L")
assert all(re.match(lit, s) for s in ("acme-dev-secret", "changeme", "dev1", "ab")), lit
assert not any(re.match(lit, s) for s in ("", "x", "-", "  ", "none", "None", "NULL", "undefined", "true", "FALSE", "bearer", "Basic")), lit
# a file path is where to look for a secret, not a known one; a word that merely ends like an extension still is
assert all(re.match(path, s) for s in ("acme-dev-pass", "acme-dev-secret", "changeme", "acme-dev-keystore", "acme-dev-key", "acme-json",
                                       "acme.keys", "key.jsonl", "acme.json.dev", "acme~/x", "a/b")), path
assert not any(re.match(path, s) for s in ("./acme-sa.json", "/etc/acme/dev.pem", "../acme/secret", "~/acme/secret", "/", "acme-signing.key",
                                           "acme.keystore", "acme.p12", "acme.PEM", "a.crt", "a.cer", "a.der", "a.pfx", "a.jks", "a.yaml",
                                           "a.yml", "a.json", ".json")), path

# One name rule for both languages: it ends in a secret stem after an optional prefix that ends in _ or . (or a camelCase
# boundary), and pwd counts only after one of those, so a bare PWD (the shell working directory) is not a secret.
name_js, name_py = rx(blocks[JSFB], "N")[0], rx(blocks[PYFB], "N")[0]
assert name_js == name_py and len(rx(blocks[PYFB], "N")) == 1, "the two languages share one name rule"
YES = ("ACME_WEBHOOK_SECRET", "ACME_DB_PASSWORD", "ACME_GH_TOKEN", "ACME_SECRET_KEY", "ACME_API_KEY", "ACME_SMTP_PASS", "ACME_DB_PWD",
       "SECRET", "TOKEN", "PASSWORD", "PASS", "API_KEY", "APIKEY", "ACME_APIKEY", "ACME_PASSWD", "ACME_PASSCODE", "ACME_CREDENTIAL", "ACME_CREDENTIALS",
       "acme_token", "acme_db_password", "jwtSecret", "dbPassword", "acmeApiKey", "dbPwd", "appSecretKey", "NEXT_PUBLIC_ACME_TOKEN",
       "ACME_SSH_PASSPHRASE", "PASSPHRASE", "sshPassphrase", "ACME_SERVICE_ROLE_KEY",
       *(f"ACME_{c}_KEY" for c in "SECRET PRIVATE SIGNING ENCRYPTION SESSION JWT HMAC MASTER ACCESS AUTH CLIENT APP SERVICE SERVICE_ROLE WEBHOOK".split()),
       *(f"ACME_{c}KEY" for c in "SECRET PRIVATE SIGNING ENCRYPTION SESSION JWT HMAC MASTER ACCESS AUTH CLIENT APP SERVICE SERVICE_ROLE WEBHOOK".split()))
NO = ("ACME_TOKEN_TTL", "ACME_PASSWORD_RESET_URL", "ACME_JWT_EXPIRES_IN", "ACME_SECRET_NAME", "ACME_MAX_TOKENS", "ACME_CACHE_KEY", "ACME_ACCESS_KEY_ID",
      "PWD", "pwd", "KEY", "ACME_KEY", "ACME_PUBLIC_KEY", "ACME_BYPASS", "NODE_ENV", "PORT",
      "bypass", "maxTokens", "cacheKey", "accessKeyId", "acmeTokenTtl", "ACME_PASSPHRASE_HINT", "ACME_SERVICE_ROLE_ARN")
assert all(re.match(name_js, s) for s in YES), [s for s in YES if not re.match(name_js, s)]
assert not any(re.match(name_js, s) for s in NO), [s for s in NO if re.match(name_js, s)]

# The JavaScript fallback rule leaves a name behind a public prefix to the public-prefix rule, which owns it; both rules read
# the same prefix list.
PREFIXES = "NEXT_PUBLIC_ VITE_ REACT_APP_ EXPO_PUBLIC_ NUXT_PUBLIC_ GATSBY_ PUBLIC_ STORYBOOK_ VUE_APP_".split()
left_out, (pub_prefix, pub_stems) = rx(blocks[JSFB], "N")[1], rx(blocks[PUB], "N")
assert len(rx(blocks[JSFB], "N")) == 2 and len(rx(blocks[PUB], "N")) == 2
assert re.fullmatch(r"\^\(\?!\(\?:(.*)\)\)", left_out)[1] == re.fullmatch(r"\^\(\?:(.*)\)", pub_prefix)[1] == "|".join(PREFIXES), (left_out, pub_prefix)
rule1 = lambda n: bool(re.match(name_js, n) and re.match(left_out, n))
rule2 = lambda n: bool(re.match(pub_prefix, n) and re.match(pub_stems, n))
assert rule1("ACME_JWT_SECRET") and all(not rule1(f"{p}ACME_JWT_SECRET") and not rule1(f"{p}ACME_API_TOKEN") for p in PREFIXES)
assert rule1("ACME_NEXT_PUBLIC_SECRET") and rule1("PUBLISHER_SECRET") and not rule1("VITE_ACME_API_KEY"), "only a leading prefix is left out"
PUB_YES = ("NEXT_PUBLIC_ACME_SERVICE_ROLE_KEY", "VITE_ACME_ADMIN_PASSWORD", "REACT_APP_ACME_SECRET_KEY", "EXPO_PUBLIC_ACME_CLIENT_SECRET",
           "NUXT_PUBLIC_ACME_PRIVATE_KEY", "GATSBY_ACME_SIGNING_KEY", "PUBLIC_ACME_ENCRYPTION_KEY", "STORYBOOK_ACME_PASSWD", "VUE_APP_ACME_PASSCODE",
           "VITE_ACME_DB_PWD", "NEXT_PUBLIC_ACME_SERVICE_ROLE", "NEXT_PUBLIC_ACME_SECRET", "VITE_ACME_SERVICE_ROLE_KEY",
           "NEXT_PUBLIC_ACME_SECRETKEY", "VITE_ACME_SSH_PASSPHRASE", "GATSBY_ACME_PRIVATEKEY", "PUBLIC_ACME_SERVICE_ROLEKEY")
PUB_NO = ("NEXT_PUBLIC_ACME_ANON_KEY", "NEXT_PUBLIC_ACME_PUBLISHABLE_KEY", "VITE_ACME_MAPS_API_KEY", "NEXT_PUBLIC_ACME_PASSWORD_RESET_URL",
          "NEXT_PUBLIC_ACME_PRIVATE_BETA", "ACME_SECRET_KEY", "ACME_NEXT_PUBLIC_SECRET", "NEXT_PUBLIC_ACME_API_TOKEN", "NEXT_PUBLIC_ACME_SITE_KEY",
          "VITE_ACME_KEY", "VITE_PWD_HINT", "NEXT_PUBLIC_ACME_CLIENT_ID", "ACME_SERVICE_ROLE_KEY", "NEXT_PUBLIC_ACME_PUBLIC_KEY",
          "NEXT_PUBLIC_ACME_PUBLISHABLEKEY", "VITE_ACME_ANONKEY", "NEXT_PUBLIC_ACME_PASSPHRASE_HINT")
assert all(rule2(n) for n in PUB_YES), [n for n in PUB_YES if not rule2(n)]
assert not any(rule2(n) for n in PUB_NO), [n for n in PUB_NO if rule2(n)]
assert not any(rule1(n) and rule2(n) for n in PUB_YES + PUB_NO), "no name is reported by both rules"

# The pattern shapes the spec lists, so one cannot be dropped unseen when semgrep is absent.
b1, b2, b3 = blocks[JSFB], blocks[PUB], blocks[PYFB]
for p in ('process.env.$N || "$L"', 'process.env.$N ?? "$L"', 'process.env["$N"] || "$L"', 'process.env["$N"] ?? "$L"',
          'process.env.$N ||= "$L"', 'process.env.$N ??= "$L"', 'process.env["$N"] ||= "$L"', 'process.env["$N"] ??= "$L"',
          'import.meta.env.$N || "$L"', 'import.meta.env.$N ?? "$L"', *(f'{k} {{ $N = "$L" }} = process.env' for k in ("const", "let", "var"))):
    assert f"- pattern: {p}\n" in b1, p
for p in ("process.env.$N", 'process.env["$N"]', "import.meta.env.$N"):
    assert f"- pattern: {p}\n" in b2, p
for p in ('os.environ.get("$N", "$L")', 'os.getenv("$N", "$L")', 'os.environ.get("$N", default="$L")', 'os.getenv("$N", default="$L")',
          'os.environ.setdefault("$N", "$L")', 'os.environ.setdefault("$N", default="$L")', 'os.environ.get("$N") or "$L"', 'os.getenv("$N") or "$L"'):
    assert f"- pattern: {p}\n" in b3, p
print("ok")
