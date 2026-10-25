#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-11 (scripts/secret_scan.py): each new rule flags a live-format value, passes its decoy
twins (L056, a bare `pass =` ini key holding letters only, is skipped on purpose: no shape of its own), and scans a 20KB line fast. Tokens are built at
runtime so no contiguous credential-shaped literal sits in this file. Offline.
"""
import hashlib, importlib.util, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
HEX = "0123456789abcdef"


def tok(seed, n, alpha=ALPHA):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


UP = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
AWS = tok("aws1", 40, ALPHA + "/+")
LIVE = {
    "slack-webhook-any-host": ["https://hooks.example.com/serv" "ices/T" + tok("t", 9, UP) + "/B" + tok("b", 11, UP) + "/" + tok("s", 24)],
    "aws-secret-access-key-assign": ["aws configure set aws_secret_" "access_key " + AWS, "AWS_SECRET_" "ACCESS_KEY=" + AWS],
    "typed-password-literal": ['password: str = "' + tok("p1", 14) + '#7"', "db_password: string = '" + tok("p2", 16) + "9'"],
    "datadog-key-assign": ["DATADOG_API_" "KEY=" + tok("d1", 32, HEX), "DD_APP_" "KEY: " + tok("d2", 40, HEX)],
    "plaid-secret-assign": ["PLAID_SE" "CRET=" + tok("l1", 30, HEX), "plaid_client_se" "cret = '" + tok("l2", 30, HEX) + "'"],
    "ldap-dn-password": ["ldap://cn=admin,dc=acme,dc=example,dc=com:" + tok("n1", 18) + "9@ldap.example.com", "ldaps://uid=svc:" + tok("n2", 14) + "7@dir.example.org"],
    "redis-cli-auth": ["redis-cli -h cache.example.com -a " + tok("r1", 24), "redis-cli -a '" + tok("r2", 20) + "' ping"],
}
DECOY = [
    "aws_secret_" "access_key_id_x = 1", "aws_secret_" "access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "aws_secret_" "access_key = <your-secret-key>",
    "aws configure set aws_secret_" "access_key " + tok("a2", 39), "aws_secret_" "access_key = " + "a" * 40,
    "https://hooks.example.com/serv" "ices/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX", "https://example.com/serv" "ices/api/v1/" + tok("x", 24),
    'password: str = ""', 'password: str = os.environ["DB_PASSWORD"]', 'password: str = "${DB_PASSWORD}"', 'password: str = "changeme123"', 'password: str = "short1"',
    "password: string = 'letters-only-value'",
    "DATADOG_API_" "KEY=${DD_KEY}", "DATADOG_API_" "KEY=" + tok("d3", 31, HEX), "OTHER_API_" "KEY=" + tok("d5", 32, HEX),
    "PLAID_SE" "CRET=${PLAID_SECRET}", "PLAID_SE" "CRET=" + tok("l3", 29, HEX), "PLAID_SE" "CRET=" + tok("l4", 31, HEX), "PLAID_ENV=sandbox",
    "ldap://cn=admin,dc=acme,dc=com:${LDAP_PASS}@ldap.example.com", "ldap://cn=admin,dc=acme,dc=com:changeme123@ldap.example.com", "ldap://cn=admin,dc=acme,dc=com:short1@ldap.example.com",
    "ldap://ldap.example.com:389", "ldap://cn=admin,dc=acme,dc=com@ldap.example.com",
    "redis-cli -h cache.example.com ping", "redis-cli -a ${REDIS_PASS} ping", "redis-cli -a short1 ping", "redis-cli -a changeme1234", "redis-cli -a password",
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
assert not bad, bad
for pre in ("redis-cli -a ", "password: str = '", "ldap://cn=" , "aws_secret_" "access_key=", "/serv" "ices/T", "DD_API_" "KEY="):
    t0 = time.time(); ids(pre * (20000 // len(pre))); assert time.time() - t0 < 1.5, pre
print("secret extra rules w8: ok")
