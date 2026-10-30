#!/usr/bin/env python3
"""Regression pins for secrets wave 12 (held-out-15 blind): snowsql/sshpass/mysql quoted -p, Figma figd_, LaunchDarkly sdk-/mob-, Elastic `ApiKey <b64>`,
Laravel APP_KEY=base64:, openssl -pass pass:, --passphrase, Terraform variable default, CloudFormation NoEcho Default, ConvertTo-SecureString -AsPlainText,
named apiToken literals. Tokens built at runtime. Offline."""
import hashlib, importlib.util, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
AN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
HEX = "0123456789abcdef"


def tok(seed, n, alpha=AN):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


pw = tok("pw", 12) + "#9"
LIVE = {
    "cli-flag-password-quoted": ["snowsql -a acme-xy1 -u svc -p '" + pw + "' -q 'select 1'", "sshpass -p '%" + pw + "' ssh deploy@10.0.3.7", "sshpass -p " + pw + " ssh deploy@10.0.3.7",
                                 'sshpass -p "' + pw + '" scp a b', "mysql -u root -p'" + pw + "' db", "snowsql -p" + pw],
    "figma-pat": ["FIGMA_PAT=fig" "d_" + tok("f", 40), "token: fig" "d_" + tok("f2", 40, AN + "_-")],
    "launchdarkly-key": ["LD_SDK_KEY=sdk-" + tok("l", 36, HEX), "LD_SDK_KEY=sdk-" + "-".join(tok("l" + str(i), n, HEX) for i, n in enumerate((8, 4, 4, 4, 12))), "key: mob-" + tok("l3", 36, HEX)],
    "authorization-apikey": ["ELASTIC_API_KEY=ApiKey " + tok("e", 60) + "==", 'curl -H "Authorization: ApiKey ' + tok("e2", 56) + '" https://es.example.com', "Authorization: ApiKey '" + tok("e3", 48) + "'"],
    "laravel-app-key": ["APP_KEY=base64:" + tok("k", 43, AN + "+/") + "=", 'APP_KEY="base64:' + tok("k2", 43) + '="', "'key' => 'base64:" + tok("k3", 43) + "=',", "APP_KEY: base64:" + tok("k4", 43) + "="],
    "openssl-pass-arg": ["openssl enc -aes-256-cbc -in a -out b -pass pass:" + pw, "openssl enc -d -pass pass:'" + pw + "'", "openssl rsa -in k -passin pass:" + pw, "openssl enc -pass=pass:" + pw],
    "passphrase-flag": ["gpg --batch --passphrase " + pw + " -d b.gpg", "gpg --passphrase='" + pw + "' -d b.gpg", 'gpg --passphrase "' + pw + '" -c f', "gpg2 --passphrase=" + pw],
    "tf-variable-secret-default": ['variable "db_password" {\n  default = "' + pw + '"\n}', 'variable "api_token" {\n  type = string\n  default = "' + pw + '"\n}', 'variable "db_password" { default = "' + pw + '" }'],
    "cfn-noecho-default": ["Parameters:\n  DbPass:\n    Type: String\n    NoEcho: true\n    Default: " + pw, "DbPass:\n  NoEcho: true\n  Default: '" + pw + "'",
                           "DbPass:\n  Default: " + pw + "\n  NoEcho: true", '"DbPass": {"NoEcho": true, "Default": "' + pw + '"}', '"DbPass": {"Default": "' + pw + '", "NoEcho": "true"}'],
    "securestring-plaintext": ['$p = ConvertTo-SecureString "' + pw + '" -AsPlainText -Force', "ConvertTo-SecureString '" + pw + "' -AsPlainText", "ConvertTo-SecureString -String '" + pw + "' -AsPlainText -Force",
                               '"' + pw + '" | ConvertTo-SecureString -AsPlainText -Force', "ConvertTo-SecureString -AsPlainText -Force -String '" + pw + "'"],
    "named-token-literal": ['const apiToken = "tk_' + tok("n", 40) + '"', "api_token: '" + tok("n2", 40) + "'", 'private_key = "' + tok("n3", 34) + '"', 'const accessToken="' + tok("n4", 36) + '";'],
}
DECOY = [
    "snowsql -a acme -u svc -p $SNOWSQL_PWD", "snowsql -p 5439", "sshpass -p '$SSH_PASS' ssh h", "sshpass -p ${PASS} ssh h", "sshpass -p {{ vault_pass }} ssh h", "sshpass -p <password> ssh h", "sshpass -p changeme1 ssh h",
    "sshpass -f /run/secrets/pw ssh h", "sshpass -p 'short' ssh h", "mysql -p", "sshpass -p %s ssh h",
    "figd_${FIGMA}", "FIGMA_PAT=figd_short", "figd_<token>",
    "LD_SDK_KEY=sdk-${LD}", "sdk-short", "sdk-" + tok("d1", 36, HEX) + "-linux.tar.gz", "LD_CLIENT_ID=" + tok("d2", 24, HEX),
    "ApiKey $ELASTIC_API_KEY", "Authorization: ApiKey ${KEY}", "ApiKey <your key>", "ApiKey short", "Authorization: ApiKey " + tok("d3", 20),
    "APP_KEY=", "APP_KEY=base64:", "APP_KEY=base64:${KEY}", "APP_KEY=base64:short=", "APP_KEY=${APP_KEY}",
    "openssl enc -pass env:PW", "openssl enc -pass file:/run/secrets/pw", "openssl enc -pass pass:$PW", "openssl enc -pass pass:changeme1", "openssl enc -pass stdin",
    "gpg --passphrase-file /run/secrets/pw -d f", "gpg --passphrase-fd 0 -d f", "gpg --passphrase $GPG_PW -d f", "gpg --passphrase ${GPG_PW}", "gpg --passphrase '' -d f", "gpg --passphrase short",
    'variable "db_password" {\n  type = string\n}', 'variable "db_password" {\n  default = ""\n}', 'variable "db_password" {\n  default = "${var.other}"\n}', 'variable "region" {\n  default = "us-east-1-prod-1"\n}',
    "DbPass:\n  NoEcho: true\n  Default: !Ref Other", "DbPass:\n  NoEcho: false\n  Default: " + pw, "Region:\n  Default: us-east-1-prod\n  Type: String",
    '$p = ConvertTo-SecureString $env:PW -AsPlainText -Force', '$p = ConvertTo-SecureString "$env:PW" -AsPlainText -Force', "ConvertTo-SecureString 'changeme1' -AsPlainText", "ConvertTo-SecureString $blob",
    "const apiToken = process.env.API_TOKEN;", 'const apiToken = "${API_TOKEN}"', 'const apiToken = "' + "x" * 40 + '"', 'api_token = "short1A"',
    'const apiKey = "https://example.com/v1/some/long/path/to/resource/1Ab"', 'api_token = "settings.api_token_value_that_is_long_enough_1A"',
    "DbPass:\n  NoEcho: true\n  Type: String",  # last: the raw-file privacy scan reads the \n as a line break and must not see a Default after it
]
bad = [("miss", r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("fp", t, ids(t)) for t in DECOY if ids(t)]
assert not bad, bad
# 100KB adversarial lines stay fast
for line in ("sshpass " * 12000, "ConvertTo-SecureString '" + "a" * 100000, "NoEcho: true\n" * 8000, 'variable "x_password" {' + " " * 100000, "ApiKey " + "A" * 100000, "--passphrase " + "a" * 100000, "-pass pass:" * 9000):
    t0 = time.time(); ids(line); assert time.time() - t0 < 2.0, (line[:30], time.time() - t0)
print("secret extra rules w12: ok")
