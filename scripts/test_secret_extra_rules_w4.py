#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-7 (scripts/secret_scan.py): each new or widened rule flags a live-format value
and passes its decoy twins. Skipped on purpose: L013 (base64 of a bare key in a k8s Secret has no credential shape of its own; needs decode-and-rescan). Tokens are built at runtime. Offline.
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


DOCKERCFG = "eyJhdXRocyI6eyJnaGNyLmlvIjp7InVzZXJuYW1lIjoiY2kiLCJwYXNz" + tok("d", 40)
LIVE = {
    "sentry-org-token": [f"SENTRY_AUTH_TOKEN=sntrys_eyJ{tok('s', 90, ALPHA + '-_')}"],
    "fcm-server-key": [f"val serverKey = \"AAAA{tok('f', 7)}:APA91b{tok('g', 130, ALPHA + '-_')}\""],
    "twitter-bearer": [f"TWITTER_BEARER_TOKEN={'A' * 21}{tok('t', 80)}%2F{tok('u', 10)}%3D"],
    "dockerconfigjson-auth": [f"data:\\n  .dockerconfigjson: {DOCKERCFG}", f'{{"data": {{".dockerconfigjson": "{DOCKERCFG}"}}}}', f"{{'.dockerconfigjson': '{DOCKERCFG}'}}", f"data:\n  .dockerconfigjson: |\n    {DOCKERCFG}", f"data:\\n  .dockerconfigjson: |\\n    {DOCKERCFG}"],
    "twitter-bearer-url": [f"x = '{'A' * 22}{tok('t', 60)}%2F{tok('u', 10)}%3D'"],
    "docker-login-password": [f"sh 'docker login -u buildbot -p {tok('p', 18)} registry.acme.example.com'", f"docker login -u ci --password={tok('q', 20)} ghcr.io"],
    "password-literal": [f'db_pass{"word"} = "*^0VR0b*{tok("w", 12)}"', f'admin_pass{"word"}: "{tok("x", 14)}"'],
}
DECOY = [
    f"SENTRY_AUTH_TOKEN=sntrys_${{SENTRY_TOKEN}}", "SENTRY_AUTH_TOKEN=sntrys_eyJshort", "SENTRY_DSN_PREFIX=sntrys_",
    f"val serverKey = \"AAAA{tok('f', 7)}:APA91b{tok('g', 20)}\"", f"val sender = \"AAAA{tok('f', 7)}\"",
    f"TWITTER_BEARER_TOKEN={'A' * 40}", f"padding = {'A' * 21}short", "TWITTER_BEARER_TOKEN=${TWITTER_BEARER}",
    "data:\\n  .dockerconfigjson: eyJhdXRocyI6e319", ".dockerconfigjson: ${DOCKERCFG_B64}", f".dockerconfigjson: {tok('e', 60)}",
    '{".dockerconfigjson": "${DOCKERCFG_B64}"}', '".dockerconfigjson": "e30="', "data:\\n  .dockerconfigjson: |\\n    e30=", '{"auths":{}}',
    f"blob = '/{'A' * 30}{tok('z', 80)}'", f"b64 = 'x+{'A' * 25}{tok('y', 70)}'", f"Authorization: Bearer ${{TOK}}",
    "docker login -u ci -p $REGISTRY_TOKEN ghcr.io", "docker login -u ci -p ${{ secrets.GHCR_TOKEN }} ghcr.io", "docker login -u ci --password-stdin ghcr.io",
    "docker login -u ci -p password ghcr.io", "docker run -p 8080:80 nginx", "docker login ghcr.io -u ci -p <token>",
    'db_password = "********"', 'db_password = "**redacted**"', 'db_password = "${DB_PASSWORD}"', 'db_password = "changeme1"', 'db_password_policy = "8abcdefghij"',
    'db_password = "<password>"', "db_password = os.environ['DB_PASSWORD']",
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
assert not bad, bad
print("secret extra rules w4: ok")
