#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-5 and -6 (scripts/secret_scan.py): each new EXTRA rule flags a live-format value
and passes its decoy twins, and the narrowed PLACEHOLDER words no longer hide real-shaped values. Tokens are built at runtime. Offline.
"""
import base64, hashlib, importlib.util, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n):
    """Deterministic high-entropy alphanumeric string of length n."""
    return "".join(ALPHA[b % 62] for b in hashlib.sha256(seed.encode()).digest() * 3)[:n]


def pw(seed):
    """Password-shaped value: letters, a symbol and digits."""
    return tok(seed, 11) + "!047"


def ids(text, precise=True):
    return ss.gitleaks_rule(text + "\n", "x.txt", precise)


HEX = hashlib.sha256(b"h").hexdigest()
JWT = lambda sig: "ey" + tok("j1", 20) + ".ey" + tok("j2", 20) + "." + sig
LIVE = {
    "sentry-dsn": [f"SENTRY_DSN=https://{HEX[:32]}:{HEX[32:]}@o848691.ingest.sentry.io/1498296"],
    "cli-token-flag": [f"run: ./deploy.sh --token {HEX[:40]}", f"deploy --api-key={tok('k', 30)}"],
    "password-assign": [f"password: {pw('a')}", "DB_PASS" "WORD=admin2Qz9xP7vLr", f"DB_PASSWORD={pw('b')}", f"MYSQL_ROOT_PASSWORD: {pw('c')}", f"PGPASSWORD={pw('f')} psql -h db -U admin", f'smtp_password: "{pw("g")}"'],
    "conn-string-password": [f"jdbc:sqlserver://sql.acme.example.com:1433;databaseName=acme;user=jane;password={pw('h')}"],
    "auth-basic": ["Authorization: Basic " + base64.b64encode(f"jane:{tok('bs', 12)}".encode()).decode()],
    "vault-token": [f"VAULT_TOKEN=hvs.{tok('v', 40)}"],
    "telegram-bot-token": [f"TELEGRAM_BOT_TOKEN=4476550354:{tok('t', 35)}"],
}
DECOY = [
    f"SENTRY_DSN=https://{HEX[:32]}@o123456.ingest.sentry.io/7890123",  # key-only DSN: public by design
    f"SENTRY_DSN=https://{HEX[:32]}:${{SENTRY_SECRET}}@o1.ingest.sentry.io/4",
    "SENTRY_DSN=https://abc@o1.ingest.sentry.io/4", "SENTRY_DSN=https://${SENTRY_KEY}@o1.ingest.sentry.io/4",
    "run: ./deploy.sh --token $DEPLOY_TOKEN", "run: ./deploy.sh --token-file ./token.txt", "deploy --password=${DEPLOY_PW}", "deploy --token=<token>", "run --secret=/etc/ci/secrets/prod_store.yaml", "run --token ./tokens/ci_token_file.json", "run --token=prod_store_credentials.txt",
    "deploy --token abc", f"deploy --api-key=os.environ.get_key_value",
    "TEST_PASSWORD=password123", "password policy: rotate every 90 days", "password requirements apply to all accounts", "redis://:{{ redis_password }}@cache.acme.example.com:6379/0",
    "password: changeme1", 'password_min_length = "8abcdefgh"', "password_policy: 8abcdefghij", "password_max_age=90daysabc", "password abc12345xyz in prose", "DB_PASS" "WORD=admin2024", "password: ${DB_PASSWORD}", "password: hunter2", "password: <your password>", "DB_PASSWORD=letmein2024", "ADMIN_PASSWORD=admin12345",
    "jdbc:sqlserver://h:1433;user=jane;password=${DB_PASS}", "jdbc:sqlserver://h:1433;user=jane;password=changeme1", "jdbc:sqlserver://h:1433;password=short",
    "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ=", "Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==", "Authorization: Basic ${BASIC_CREDS}",
    "VAULT_TOKEN=hvs.<token>", "VAULT_TOKEN=hvs." + "x" * 40, "VAULT_TOKEN=hvs.short",
    "TELEGRAM_BOT_TOKEN=12345678:short", "ts=1700000000:ok",
    "SLACK_BOT_TOKEN=xoxb-your-token-here",
    "AIza" + tok("g", 35) + "  # public maps key restricted by referrer in the docs",
    "AIza" + tok("g", 35) + " // referrer-restricted browser key",
    JWT(""),
]
EXTRA_IDS = {r[0] for r in ss.EXTRA}
for rule, texts in LIVE.items():
    for t in texts:
        assert rule in ids(t), ("live secret not flagged", rule, t)
        assert not set(ids(t, False)) & EXTRA_IDS, ("EXTRA id leaked into the rival bench path", rule)
for t in DECOY:
    assert not ids(t), ("decoy flagged", t, ids(t))
K1, K2 = "AIza" + tok("g1", 35), "AIza" + tok("g2", 35)
for t in (f"# public key restricted by referrer\n{K1}", f"# public referrer-restricted: {K1}", f"{K1} {K2}  # public key restricted by referrer", f"{K1}  # TODO rotate\n{K2}  # public key restricted by referrer"):
    assert "gcp-api-key" in ids(t), ("a public comment hid a key it does not follow", t)
for t in ("ENV ADMIN_PASS" "WORD " + pw("n"), "machine git.acme.example.com login svc pass" "word " + pw("m")):
    assert "password-env-netrc" in ids(t), t
assert "gcp-api-key" in ids("AIza" + tok("g", 35)) and "jwt" in ids(JWT(tok("s", 30)))  # the narrowed passes keep the plain twins
for p in ("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "token=example", "api_key=Example", "your-token-here", "your_api_key"):
    assert ss.PLACEHOLDER.search(p), ("placeholder missed", p)
for p in ("AcmeExampleToken0123456789", "sk_" "live_acmeJaneExample0123", "AKIAACMEEXAMPLE12", "user@example.com", "myexamplepassword", "xoxb-1234"):
    assert not ss.PLACEHOLDER.search(p), ("real-shaped value hidden", p)
print("extra secret rules w3: ok")
