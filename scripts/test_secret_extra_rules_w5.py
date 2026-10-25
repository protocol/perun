#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-8 (scripts/secret_scan.py): each new or widened rule flags a live-format value
and passes its decoy twins. Skipped on purpose: L004 (a ghp_ token 2 characters short of the real length is no real format), L060 (a bare string
argument to Client::new has no shape of its own). Tokens are built at runtime. Offline.
"""
import hashlib, importlib.util, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n, alpha=ALPHA):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


P = "pass" "word"
LIVE = {
    "url-password": [f"DATABASE_URL=postgres://svc:{tok('a', 3)}**{tok('b', 9)}1@db.acme.example.com/orders", f"DATABASE_URL=postgres://svc:{tok('a', 8)}*{tok('b', 9)}@db.acme.example.com:5432/orders"],
    "password-literal": [f'smtp_pass: "{tok("c", 18)}"', f"db_pass = '{tok('d', 14)}'"],
    "environ-default-secret": [f"x = os.getenv('authToken', '{tok('v1', 20)}')", f"x = os.getenv('SESSION_TOKEN_V2', '{tok('v2', 20)}')", f"x = os.getenv('MY_SECRET_KEY_BASE', '{tok('v3', 20)}')", f"x = os.getenv('DB_{P.upper()}_FILE', '{tok('v4', 20)}')", f"{P} = os.environ.get('DB_PASS', '{tok('e', 16)}')", f"x = os.getenv(\"API_TOKEN\", \"{tok('f', 24)}\")"],
    "typed-secret-literal": [f'let secret: &str = "{tok("g", 40)}";', f'const apiToken: string = "{tok("h", 32)}";'],
    "terraform-variable-default": [f'variable "db_{P}" {{\n  default = "{tok("i", 20)}"\n}}', f'variable "db_{P}" {{\\n  default = "{tok("i", 20)}"\\n}}'],
    "k8s-env-value": [f'- name: DB_{P.upper()}\n  value: "{tok("j", 20)}"', f'- name: DB_{P.upper()}\\n  value: "{tok("j", 20)}"'],
    "dockerfile-env-secret": [f"ENV API_TOKEN {hashlib.sha256(b'hx').hexdigest()[:40]}", f"ENV SESSION_SECRET {tok('k', 40)}", f"RUN a\\nARG AUTH_TOKEN {tok('l', 32)}\\nRUN b"],
    "netrc-password": [f"machine git.acme.example.com login ci {P} {tok('m', 14)}"],
    "pagerduty-key": [f"PAGERDUTY_KEY=u+{tok('n', 18)}", f'pagerduty_api_key: "u+{tok("o", 18)}"'],
    "mysqli-password": [f"$m = new mysqli('10.4.1.7', 'root', '{tok('p', 16)}', 'shop');"],
}
DECOY = [
    "DATABASE_URL=postgres://svc:********@db.acme.example.com/orders", "DATABASE_URL=postgres://svc:${DB_PASS}@db.acme.example.com/orders",
    'smtp_pass: "${SMTP_PASS}"', "smtp_pass: changeme1", 'bypass: "abcdefgh12345678"', 'smtp_pass: ""',
    "x = os.environ.get('DB_PASS', '')", "x = os.environ.get('DB_PASS', 'changeme')", "SECRET_KEY = os.getenv('SECRET_KEY', 'dev-only-not-secret')", "x = os.environ.get('CACHE_DIR', '/var/cache/appdata')", "x = os.getenv('API_URL', 'https://api.acme.example.com/v1')",
    'let secret: &str = "short";', 'let secret: &str = env!("SECRET_VALUE");', 'let name: &str = "' + tok("g", 40) + '";', 'const apiToken: string = "${API_TOKEN_VALUE}";',
    'variable "region" {\n  default = "' + tok("i", 20) + '"\n}', 'variable "db_' + P + '" {\n  type = string\n}', 'variable "db_' + P + '" {\n  default = "<set-me>"\n}',
    '- name: DB_HOST\n  value: "' + tok("j", 20) + '"', '- name: DB_' + P.upper() + '\n  valueFrom:\n    secretKeyRef:\n      name: db', '- name: DB_' + P.upper() + '\n  value: "${DB_PASS}"',
    "ENV SESSION_SECRET_FILE /run/secrets/session1A", "ENV SESSION_SECRET ${SESSION_SECRET_VALUE}", "ENV TOKEN_URL https://auth.acme.example.com/token1", "ENV SESSION_SECRET short1A",
    f"machine git.acme.example.com login ci {P} ${{NETRC_PASS}}", f"machine git.acme.example.com login ci {P} short",
    "PAGERDUTY_KEY=u+short", "PAGERDUTY_KEY=${PD_KEY}", "PAGERDUTY_KEY=u+abc",
    "x = os.getenv('KEYCLOAK_URL', 'https://keycloak1.acme.example.com/auth')", "x = os.getenv('API_TOKEN', 'arn:aws:iam::123456789012:role/app1')", 'const TOKEN_HEADER: string = "Authorization-Header";',
    "ENV TOKEN_ARN arn:aws:secretsmanager:eu-west-1:123456789012:secret1",
    "ENV SECRET_VERSION 20230115123456789012", "ENV TOKEN_TTL 36000036000036000036", "DATABASE_URL=postgres://svc:abcdefgh********@db.acme.example.com/orders",
    "$m = new mysqli('10.4.1.7', 'root', '', 'shop');", "$m = new mysqli($host, $user, $pass, 'shop');", "$m = new mysqli('10.4.1.7', 'root', '${DB_PASS}', 'shop');",
    # public-by-design values the placeholder pass now drops
    f'data-sitekey="6Lc{tok("sk", 37)}"', f"CACHE_KEY=v2-{tok('ck', 16)}",
    'anon_key = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.' + tok("a", 43) + '"',
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
# twins of the public-value drops stay flagged: a service_role JWT, a cache-named secret that is not a cache key, a real api key
bad += [("twin", t) for t in (f"SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.{tok('a', 43)}", f"STRIPE_API_KEY={tok('q', 40)}") if not ids(t)]
assert not bad, bad
print("secret extra rules w5: ok")
