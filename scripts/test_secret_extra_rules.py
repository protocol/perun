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
# Rules added after held-out-7 (decoy twins and more live shapes: test_secret_extra_rules_w4.py).
LIVE.update({"sentry-org-token": "SENTRY_AUTH_TOKEN=sntrys_eyJ" + tok("so", 45) + tok("sp", 45), "fcm-server-key": "key = AAAA" + tok("fk", 7) + ":APA91b" + tok("fl", 60) + tok("fm", 60) + tok("fn", 20),
             "twitter-bearer": "TWITTER_BEARER_TOKEN=" + "A" * 21 + tok("tb", 40) + tok("tc", 40), "dockerconfigjson-auth": ".dockerconfigjson: eyJhdXRocyI6eyJnaGNyLmlvIjp7" + tok("dj", 60),
             "twitter-bearer-url": "x = " + "A" * 22 + tok("tu", 60) + "%2F" + tok("tv", 10), "docker-login-password": "docker login -u ci -p " + tok("dl", 18) + " ghcr.io"})
# Rules added after held-out-8 (decoy twins and more live shapes: test_secret_extra_rules_w5.py).
LIVE.update({"environ-default-secret": "x = os.environ.get('DB_PASS', '" + tok("ed", 16) + "')", "typed-secret-literal": 'let secret: &str = "' + tok("ts", 40) + '";',
             "terraform-variable-default": 'variable "db_pass' 'word" {\n  default = "' + tok("tv2", 20) + '"\n}', "k8s-env-value": '- name: DB_PASS' 'WORD\n  value: "' + tok("ke", 20) + '"',
             "dockerfile-env-secret": "ENV SESSION_SECRET " + tok("de", 40), "netrc-password": "machine git.acme.example.com login ci pass" "word " + tok("np", 14),
             "pagerduty-key": "PAGERDUTY_KEY=u+" + tok("pk", 18), "mysqli-password": "$m = new mysqli('10.4.1.7', 'root', '" + tok("my", 16) + "', 'shop');"})
# Rules added after held-out-9 (decoy twins, ReDoS bounds: test_secret_extra_rules_w6.py).
LIVE.update({"resend-key": "re" "_" + tok("r1", 8) + "_" + tok("r2", 24), "okta-ssws-token": "Authorization: SS" "WS 00" + tok("o", 38), "cli-password-attached": "mysql -p" + tok("c1", 16) + " -e 'select 1'",
             "pass-key-assign": "ansible_become_pass: " + tok("p1", 18), "url-query-token": "GET /v1/items?access_token=" + tok("u1", 32) + "&limit=10",
             "xml-add-key-value": '<add key="StorageKey" value="' + tok("x1", 42) + '==" />', "xml-password-element": "<pass" "word>" + tok("x5", 14) + "</pass" "word>",
             "bracket-secret-assign": "$config['jwt_sec" "ret'] = '" + tok("b1", 40) + "';"})
# Rules added after held-out-10 (decoy twins: test_secret_extra_rules_w7.py).
LIVE.update({"php-var-pass": '$db' 'pass = "' + tok("w7a", 22) + '";', "wp-key-salt-define": "define('AUTH_" "KEY', '" + tok("w7b", 64) + "');",
             "basic-auth-symbol-password": "cur" "l -u deploy:P4ssw0rd!x https://x.example.com", "azure-sas-sig": "https://a.example.com/c?sv=2022-11-02&sig=" + tok("w7c", 44) + "%3D&se=1"})
# Rules added after held-out-11 (decoy twins: test_secret_extra_rules_w8.py).
LIVE.update({"slack-webhook-any-host": "https://hooks.example.com/serv" "ices/T" + tok("w8a", 9).upper() + "/B" + tok("w8b", 10).upper() + "/" + tok("w8c", 24),
             "aws-secret-access-key-assign": "aws configure set aws_secret_" "access_key " + tok("w8d", 12) + "aA1" + tok("w8e", 25), "typed-password-literal": 'password: str = "' + tok("w8f", 14) + '#7"',
             "datadog-key-assign": "DATADOG_API_" "KEY=" + hashlib.sha256(b"w8g").hexdigest()[:32], "plaid-secret-assign": "PLAID_SE" "CRET=" + hashlib.sha256(b"w8h").hexdigest()[:30],
             "ldap-dn-password": "ldap://cn=admin,dc=acme,dc=example,dc=com:" + tok("w8i", 18) + "9@ldap.example.com", "redis-cli-auth": "redis-cli -h cache.example.com -a " + tok("w8j", 24)})
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
