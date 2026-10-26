#!/usr/bin/env python3
"""Regression pins for secrets wave 13 (review of wave 12): case-insensitive `ApiKey` scheme, linear Laravel/CLI regexes, letters-only and spaced
CLI/openssl/gpg/PowerShell literals, Terraform metadata-name and nested-block handling, CloudFormation NoEcho comment/CRLF/JSON forms. Offline."""
import hashlib, importlib.util, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
AN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n, alpha=AN):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


LOW = "abcdefghijklmnopqrstuvwxyz"
pw = tok("pw", 11) + "!"  # digit + symbol
lw = tok("lw", 14, LOW)  # letters only
sp = tok("a", 5) + " 2 " + tok("b", 6)  # holds spaces
sp2 = tok("c", 3, LOW) + " " + tok("d", 3, LOW) + " " + tok("e", 5) + "1"
dg = "12345678"
b64 = tok("ak", 44)
LIVE = {
    "authorization-apikey": ["Authorization: apikey " + b64 + "=", "Authorization: APIKEY " + b64 + "=", "Authorization: ApiKey " + b64 + "="],
    "cli-flag-password-quoted": [f"sshpass -p {lw} ssh x", f"snowsql -p '{sp}' -q 'select 1'", f"mongosh -p '{sp2}' --host h", f'mysql -u root -p"{sp}"', f"sshpass -p '{pw}' ssh x"],
    "openssl-pass-arg": [f"openssl enc -aes-256-cbc -pass pass:{lw} -in a", f"openssl enc -aes-256-cbc -k {pw} -in a", f"openssl enc -k {lw} -in a"],
    "passphrase-flag": [f'gpg --passphrase "{sp}" -c f', f"gpg --passphrase {lw} -c f", f"gpg --passphrase {dg} -c f", f"gpg --batch --passphrase={pw} -c f"],
    "tf-variable-secret-default": [
        f'variable "db_password" {{ validation {{ condition = true }} default = "{pw}" }}',
        f'variable "db_password" {{\n  type = string\n  validation {{\n    condition = length(var.db_password) > 3\n  }}\n  default = "{pw}"\n}}'],
    "cfn-noecho-default": [
        f"    NoEcho: true  # secret\n    Default: {pw}", f"    NoEcho: true\r\n    Default: {pw}", f"    Default: {pw}\r\n    NoEcho: true",
        f'{{"NoEcho": true, "Type": "String", "Default": "{pw}"}}', f'{{"Default": "{pw}", "Type": "String", "NoEcho": true}}'],
    "securestring-plaintext": [
        f'ConvertTo-SecureString -AsPlainText "{pw}" -Force', f"ConvertTo-SecureString -String '{pw}' -Force -AsPlainText", f'ConvertTo-SecureString "{lw}" -AsPlainText -Force',
        f'ConvertTo-SecureString "{sp}" -AsPlainText -Force', f'ConvertTo-SecureString "{pw}" -Force -AsPlainText'],
}
for rid, rows in LIVE.items():
    for r in rows: assert rid in ids(r), (rid, r)

CLEAN = [  # references, placeholders and non-secret metadata stay quiet
    'variable "token_endpoint" { default = "https://example.com/oauth/token" }', 'variable "token_url" { default = "https://idp.test/t0ken" }',
    'variable "db_password_secret_arn" { default = "arn:aws:secretsmanager:eu-west-1:1234:secret:x" }', 'variable "secret_path" { default = "/var/run/secrets/x1" }',
    'variable "api_token" { default = "https://idp.test/t0ken" }',
    "Authorization: ApiKey ${API_KEY}", "mysql -p mydatabase", "snowsql -p 8443", "sshpass -p $PW ssh x", "sshpass -p '${PW}' ssh x", "snowsql -p 'my database'",
    "openssl enc -pass pass:$PW", "openssl enc -pass env:PW", "openssl enc -k $PW", "gpg --passphrase-file pw.txt -c f", 'gpg --passphrase "$PW" -c f', "gpg --passphrase password",
    'ConvertTo-SecureString -AsPlainText "$env:PW" -Force', "ConvertTo-SecureString $pw -AsPlainText -Force", "    NoEcho: true\n    Default: !Ref Other",
]
for c in CLEAN: assert not ids(c), (c, ids(c))

ADV = {  # worst-case 100KB lines; LINE_MAX caps the live scanner, so time the rules directly too
    "laravel": "APP_KEY" + " " * 4000 + "\n", "sshpass": "sshpass " * 12000, "tf": 'variable "x_password" { ' * 4000, "cfn": "NoEcho: true, " * 7000,
    "securestring": "ConvertTo-SecureString " * 4000, "openssl": "openssl " * 12000,
}
for name, line in ADV.items():
    for rid, rx, g, ent in ss.EXTRA:
        t = time.time(); rx.search((line * 25 if name == "laravel" else line)[:100_000]); assert time.time() - t < 0.2, (name, rid, time.time() - t)
print("secrets wave 13 pins: ok")
