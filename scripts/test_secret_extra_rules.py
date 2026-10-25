#!/usr/bin/env python3
"""Regression pins for the gate's EXTRA secret rules (scripts/secret_scan.py): each rule flags a live-format value and passes its decoy twins.

Tokens are built at runtime from a deterministic generator, so no literal secret sits in this file. EXTRA runs only with precise=True (the gate);
the rival-bench path (precise=False) must never report an EXTRA rule id. Offline.
"""
import hashlib, importlib.util, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n):
    """Deterministic high-entropy alphanumeric string of length n."""
    h = hashlib.sha256(seed.encode()).digest() * 3
    return "".join(ALPHA[b % 62] for b in h)[:n]


def uuid(seed):
    h = hashlib.sha256(seed.encode()).hexdigest()
    return "-".join((h[:8], h[8:12], h[12:16], h[16:20], h[20:32]))


T = tok("a", 40)
LIVE = {
    "discord-webhook": f"DISCORD_WEBHOOK=https://discord.com/api/webhooks/{'3' * 18}/{tok('d', 66)}",
    "url-password": "redis://:" + tok("r", 24) + "@cache.acme.example.com:6379/0",
    "secret-key-literal": "app.config['SECRET_KEY'] = '" + tok("s", 32) + "'",
    "jwt-literal-secret": "jwt.sign(payload, '" + tok("j", 32) + "', { expiresIn: '1h' })",
    "google-client-secret": "GOOGLE_CLIENT_SECRET=GOCSPX-" + tok("g", 28),
    "uuid-credential": "heroku config:set API_KEY=" + uuid("u"),
    "auth-header-token": "INFO retrying headers={Authorization: Bearer " + tok("b", 38) + "} status=401",
    "password-literal": '# TODO\\npassword = "' + tok("p", 16) + '"',
    "cli-password": "mysql -u root -p'" + tok("m", 16) + "' -h db.acme.example.com",
    "telegram-bot-token": "TELEGRAM_BOT_TOKEN=3153487448:AA" + tok("t", 35),
}
LIVE["password-json"] = '{"password": "' + tok("pj", 16) + '"}'
LIVE["uuid-client-secret"] = "client_secret=" + uuid("cs")
LIVE["url-password-user-at"] = "smtps://alerts@acme.example.com:" + tok("q", 20) + "@smtp.acme.example.com:465"
LIVE["cli-password-sshpass"] = "sshpass -p '" + tok("w", 16) + "' ssh deploy@build.acme.example.com"
# Rules added after held-out-5/6 (decoy twins and more live shapes: test_secret_extra_rules_w3.py).
LIVE.update({"sentry-dsn": "SENTRY_DSN=https://" + tok("sd", 32) + ":" + tok("se", 32) + "@o848691.ingest.sentry.io/1498296", "cli-token-flag": "./deploy.sh --token " + tok("tf", 40),
             "auth-basic": "Authorization: Basic " + tok("ab", 24), "vault-token": "VAULT_TOKEN=hvs." + tok("vt", 40)})
LIVE["password-assign"] = "DB_PASS" "WORD=" + tok("pa", 11) + "!047"
LIVE["password-env-netrc"] = "ENV ADMIN_PASS" "WORD " + tok("pe", 11) + "!047"
LIVE["conn-string-password"] = "jdbc:sqlserver://h:1433;user=jane;pass" "word=" + tok("cp", 16)
DECOY = [
    "DISCORD_WEBHOOK=https://discord.com/api/webhooks/<id>/<token>",
    "see https://discord.com/api/webhooks/123456789012345678 for the docs",
    "redis://:${REDIS_PASSWORD}@cache.acme.example.com:6379/0",
    "postgres://app:password@localhost:5432/dev",
    "https://example.com:8080/path?a=b@c",
    "SECRET_KEY = os.environ['SECRET_KEY']",
    "app.config['SECRET_KEY'] = '" + "x" * 32 + "'",
    "SECRET_KEY = '${SECRET_KEY_FROM_VAULT}'",
    "jwt.sign(payload, process.env.JWT_SECRET, { expiresIn: '1h' })",
    "jwt.sign(payload, '" + "a" * 32 + "')",
    "GOOGLE_CLIENT_SECRET=GOCSPX-" + "x" * 28,
    "heroku config:set API_KEY=00000000-0000-0000-0000-000000000000",
    "request: trace_id=" + uuid("trace"),
    "Authorization: Bearer ${API_TOKEN}",
    "Authorization: Bearer <token>",
    "Authorization: Bearer abc",
    'password = "changeme123"',
    'password = "********"',
    'password = "hunter2"',
    'password = "${DB_PASSWORD}"',
    "mysql -u root -p -h db.acme.example.com",
    "mysql -u root -p'$MYSQL_PWD' -h db",
    "sshpass -p 'replace_me' ssh deploy@build",
    "TELEGRAM_BOT_TOKEN=123456789:AA" + "x" * 35,
    "TELEGRAM_BOT_TOKEN=12345678:AA",
    'password="os.environ[PASSWORD]"',
    'password = "passwordRequired"',
    "password = 'string_required_value'",
    'secret_key="config.secret_key_value"',
    "jwt.sign(p, \"process.env.JWT_SECRET_KEY\")",
    "next_token=" + uuid("n"), "pageToken=" + uuid("pg"), "secret_id=" + uuid("sid"), "token=" + uuid("tk"),
    "Authorization: Bearer getAuthorizationTokenFromStore123",
    "Authorization: Bearer your_access_token_value_here",
    "TELEGRAM_BOT_TOKEN=3153487448:AA" + "ab" * 17,
]


def ids(text, precise=True):
    return ss.gitleaks_rule(text + "\n", "x.txt", precise)


EXTRA_IDS = {r[0] for r in ss.EXTRA}
for rule, text in LIVE.items():
    assert ids(text), ("live secret not flagged", rule)
    assert not set(ids(text, False)) & EXTRA_IDS, ("EXTRA id leaked into the rival bench path", rule)
assert {i for t in LIVE.values() for i in ids(t)} >= {r[0] for r in ss.EXTRA}, "an EXTRA rule has no live pin"
for text in DECOY:
    assert not set(ids(text)) & EXTRA_IDS, ("decoy flagged by an EXTRA rule", text, ids(text))  # gitleaks' own rules may still flag (e.g. generic-api-key on uuids)
print("extra secret rules: ok")
