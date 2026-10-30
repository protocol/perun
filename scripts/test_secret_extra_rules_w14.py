#!/usr/bin/env python3
"""Regression pins for secrets wave 14: the 13 blind held-out-16 union misses (redis requirepass, mosquitto -P, SQL WITH PASSWORD, short `pwd:` key, plist
<key>/<string>, Clojure def, Erlang tuple, nginx proxy_set_header, Apache SetEnv, az login -p, bare private_key_id, CloudFormation secret-named parameter,
bare netrc password line) plus review-1 of wave 13 (placeholder prose, first-`-p` sshpass, openssl `/` paths, Terraform `_id`/`_name` secrets). Offline."""
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


_h = hashlib.md5(b"u").hexdigest(); UU = "-".join([_h[:8], _h[8:12], _h[12:16], _h[16:20], _h[20:]])
v12, v18, v24, v30, v40 = tok("a", 12), tok("b", 18), tok("c", 24), tok("d", 30), hashlib.sha1(b"e").hexdigest()
LIVE = {
    "redis-requirepass": [f"requirepass {v24}", f"masterauth {v24}", f'requirepass "{v24}"'],
    "mosquitto-password-flag": [f"mosquitto_pub -h h -u acme -P {v18} -t t -m ok", f"mosquitto_sub -P '{v18}' -t t"],
    "sql-password-literal": [f"CREATE USER app WITH PASSWORD '{v18}';", f"CREATE ROLE r WITH ENCRYPTED PASSWORD '{v18}'", f"CREATE USER app IDENTIFIED BY '{v18}';", f"SET PASSWORD = '{v18}'"],
    "pwd-literal": [f"db.createUser({{user:'acme',pwd:'{v18}'}})", f"db.updateUser('a', {{pwd: '{v18}'}})"],
    "plist-secret-string": [f"<key>ACMEApiKey</key>\\n<string>{v30}</string>", f"<key>DbPassword</key>\n  <string>{v18}</string>"],
    "clojure-secret-def": [f'(def db-pass "{v18}")', f'(defonce api-token "{v30}")', f'{{:user "acme" :password "{v18}"}}'],
    "erlang-secret-tuple": [f'{{api_key, <<"{v30}">>}}', f'{{password, "{v18}"}}'],
    "proxy-header-secret": [f"proxy_set_header X-Api-Key {v30};", f'proxy_set_header X-Auth-Token "{v30}";'],
    "setenv-secret": [f"SetEnv ACME_SECRET {v30}", f"fastcgi_param APP_TOKEN {v30};"],
    "az-login-password": [f"az login --service-principal -u 00000000-0000-0000-0000-000000000000 -p {v30} --tenant example.com", f"az login --service-principal -u a -p '{v30}' -t t", f"az login --password={v30}"],
    "private-key-id-bare": [f"gcloud auth activate-service-account --key-file=sa.json  # private_key_id {v40}"],
    "cfn-param-default-secret": [f"Parameters:\\n  DbPassword:\\n    Type: String\\n    Default: {v18}", f"Parameters:\n  ApiToken:\n    Type: String\n    Description: x\n    Default: {v18}\n",
                                 f"  DbPassword:\r\n    Type: String\r\n    Default: {v18}"],
    "netrc-bare-password": [f"password {v18}  # ~/.netrc machine api.example.com login jane", f"machine h\nlogin jane\npassword {v18}"],
    "tf-variable-secret-id-default": [f'variable "secret_id" {{ default = "{UU}" }}', f'variable "token_name" {{ default = "{v30}" }}'],
}
for rid, rows in LIVE.items():
    for r in rows: assert rid in ids(r), (rid, r, ids(r))

# review-1 items: previously false positives, now quiet
FP = [
    "openssl enc -k /path/to/keyfile", "openssl enc -k mypassword", "openssl enc -k yourpassword", "openssl enc -pass pass:mypassword", "openssl enc -pass pass:yourpassword",
    "sshpass -p yourpassword ssh x", "sshpass -p mypassword ssh x", "sshpass -e ssh -p production-bastion host",
    'gpg --passphrase "your passphrase" -c f', 'ConvertTo-SecureString "your password" -AsPlainText -Force', 'ConvertTo-SecureString "enter password" -AsPlainText -Force',
    'ConvertTo-SecureString "Enter-Your-Password" -AsPlainText -Force',
    # new rules: references, placeholders and metadata stay quiet
    "requirepass $REDIS_PW", "requirepass ${REDIS_PW}", "requirepass changeme123", "mosquitto_pub -p 1883 -h h", "mosquitto_pub -P $PW", "CREATE USER a WITH PASSWORD 'x';", "CREATE USER a WITH PASSWORD '$PW';",
    "CREATE USER a IDENTIFIED BY ?", "pwd = '/home/jane'", "pwd=$(pwd)", "<key>ApiKey</key><string>${API_KEY}</string>", "<key>CFBundleName</key><string>Acme1234567890abc</string>",
    '(def db-pass (env :db-pass))', '(def db-pass "")', '{api_key, <<"${KEY}">>}', "proxy_set_header X-Api-Key $http_x_api_key;", "proxy_set_header X-Real-IP $remote_addr;",
    "SetEnv ACME_SECRET ${SECRET}", "az login --service-principal -u a -p $SP_PW", "az login --use-device-code", "private_key_id", "Parameters:\n  DbPassword:\n    Type: String\n    Default: ''\n",
    "Parameters:\n  DbPassword:\n    Type: String\n    Default: !Ref Other\n", "password",
    'variable "secret_id" { default = "projects/x/secrets/y" }', 'variable "token_name" { default = "prod-token" }',
]
for c in FP: assert not ids(c), (c, ids(c))

sp_ = tok('s', 5) + ' 2 ' + tok('t', 6)

# wave 14 review: more live forms (key name implies a secret, so no digit needed) and more quiet forms
Z = "Zq@x" + v12 + "!"  # no digit guarantee: symbol + mixed case
for rid, rows in {
    "cli-flag-password-quoted": [f"sshpass -f x -p {Z} ssh u@h", f"sshpass -P assword -p {Z} ssh", f"sshpass -d 3 -p {Z} ssh", f"sshpass -e -p '{Z}' ssh", f"sshpass -f x -p '{sp_}' ssh"],
    "redis-requirepass": [f"requirepass {Z}", f"sentinel auth-pass mymaster {Z}"],
    "mosquitto-password-flag": [f"mosquitto_pub -h h --pw {Z} -t t", f'mosquitto_pub -P "{sp_}"', f"mosquitto_passwd -b pwfile jane {Z}"],
    "sql-password-literal": [f"ALTER ROLE x PASSWORD '{Z}'", f"CREATE ROLE x LOGIN PASSWORD '{v18}'", f"ALTER USER scott IDENTIFIED BY {Z};", f"SET PASSWORD FOR 'b'@'%' = PASSWORD('{Z}')", f"IDENTIFIED BY '{Z}'"],
    "pwd-literal": [f"db.createUser({{user:'a',pwd:'{Z}'}})"],
    "plist-secret-string": [f"<key>password</key>\n<string>{Z}</string>", f"<key>ApiToken</key><string>{Z}</string>"],
    "clojure-secret-def": [f'(def db-pass "{Z}")', f'(def db-pass\n  "{Z}")'],
    "erlang-secret-tuple": [f"{{password, '{Z}'}}", f'{{password,\n  <<"{Z}">>}}'],
    "proxy-header-secret": [f'proxy_set_header Authorization "Bearer {Z}";', f"proxy_set_header Authorization {Z};", f"proxy_set_header X-Api-Key {Z};", f'RequestHeader set X-Api-Key "{Z}"',
                            f"Header set X-Token {Z}", f"proxy_set_header Proxy-Authorization 'Basic {tok('b', 20)}';"],
    "setenv-secret": [f"PassengerEnvVar SECRET_KEY_BASE {Z}"],
    "az-login-password": [f"az acr login -n r -u u -p {Z}", f"az login --service-principal -u u -p {Z} --tenant t"],
    "cfn-param-default-secret": [f"Parameters:\n  DbPassword:\n    Default: {Z}\n    Type: String", f"Parameters:\n  DbPassword:\n    Description: a\n    MinLength: 8\n    MaxLength: 40\n    AllowedPattern: x\n    Type: String\n    Default: {Z}",
                                 f'"DbPassword": {{"Type":"String","Default":"{Z}"}}'],
    "netrc-bare-password": [f"machine h\nlogin jane\npassword {Z}", f"password '{Z}'  # ~/.netrc machine api.example.com login jane"],
    "tf-variable-secret-id-default": [f'variable "secret_id" {{\n  description = "{"lorem " * 70}"\n  default = "{UU}"\n}}'],
}.items():
    for r in rows: assert rid in ids(r), (rid, r, ids(r))
for c in [
    "Risks are identified by Operations.", "identified by regulators.", "requirepass /run/secrets/redis_pw_1", "requirepass configuration", "mosquitto_passwd -b pwfile jane x",
    "ALTER ROLE x PASSWORD 'test1234abcd';", "-- IDENTIFIED BY 'my-secret-123' is bad", "pwd = 'dir/sub1/app'", "const pwd = 'dirname2go'", "pwd = '/home/user1/Projects'",
    "<key>TokenEndpointPath</key>\n<string>oauth2/v2/token1</string>", '(def compass-heading "north-by-east-12")', '(def bypass-rule "allow-all-rules-12")', '(def tokenizer-name "wordpiece-uncased-v1")',
    '(def secret-path "resources/secrets1.edn")', '(def token-url "https://auth.example.org/token1")', '{:token-count "1234567890abc"}',
    '{secret_file, "/etc/secrets/app1.key"}', '{token_type, "bearer-token-v1"}', '{passwd_file, "/etc/passwd-backup1.txt"}', '{api_key_header, "X-Api-Key-Header-1"}',
    'proxy_set_header X-Forwarded-Key "forward-key-header-v2";', "SetEnv SECRET_FILE /etc/app/secrets/main1.txt", "SetEnv TOKEN_NAME application-token-v2", "fastcgi_param SECRET_FILE /etc/app/secret1.txt;",
    "SetEnv TOKEN_ENDPOINT https://auth.example.org/oauth/token1", "SetEnv PASSWD_FILE /etc/apache2/passwd-file-1",
    "az login --service-principal -u u -p /path/to/cert1.pem --tenant t", "az login --service-principal -u u -p ~/certs/sp1.pem", "az login --service-principal -u u -p cert-file-v2.pem",
    "Parameters:\n  SecretArn:\n    Type: String\n    Default: arn:aws:secretsmanager:eu-west-1:1234:secret:x", "Parameters:\n  SecretName:\n    Type: String\n    Default: prod/db/password-v1",
    "Parameters:\n  PasswordFile:\n    Type: String\n    Default: /etc/app/password-file-1", "Parameters:\n  TokenBucket:\n    Type: String\n    Default: my-token-bucket-12345",
    "Parameters:\n  TokenTTL:\n    Type: String\n    Default: 3600seconds",
    "password Policy1MustContainDigits", "Password Requirements1Apply", "password Enter1YourPasswordHere",
    'variable "secret_name" {default = "prod/db/Secret-abcdefghijklmnop1"}', 'variable "secret_id" {default = "prod/payments/StripeKeyV2abcdefghijk1"}',
    "sshpass -p Enter-Your-Password1 ssh x", "openssl enc -k stdin1234", "sshpass -e ssh -p production-bastion host",
]: assert not ids(c), (c, ids(c))

# the earlier rules must still catch real secrets that merely contain the placeholder words
for r in [f"openssl enc -k {tok('f', 14)}1", f"gpg --passphrase mypassword{v12}", f"sshpass -e -p {v12} ssh x", f'ConvertTo-SecureString "mypassword{v12}1" -AsPlainText -Force']:
    assert ids(r), r

ADV = {
    "redis": "requirepass " * 9000, "mosq": "mosquitto_pub " * 7000, "sql": "with password " * 7000, "plist": "<key>" * 20000, "clj": "(def " * 25000,
    "erl": "{ " * 50000, "proxy": "proxy_set_header X-" * 5000, "az": "az login " * 11000, "cfn": "Password:\n  " * 9000, "netrc": "password " * 12000,
    "sshpass": "sshpass -e " * 9000, "sshpass2": "sshpass -f x " * 7000, "sshpass3": "sshpass " + "-d 3 " * 20000, "auth": "auth-pass a " * 8000, "hdr": "RequestHeader set " * 5000, "cfn2": "P:\n  Password:\n" + "    a: b\n" * 12000, "tfl": 'variable "x_secret_id" { ' + "a " * 40000, "tf": 'variable "x_password_id" { ' * 4000, "ws": "a:" + " " * 100_000,
}
for name, line in ADV.items():
    for rid, rx, g, ent in ss.EXTRA:
        t = time.time(); rx.search(line[:100_000]); assert time.time() - t < 2.0, (name, rid, time.time() - t)
print("secrets wave 14 pins: ok")

# review-2 regressions (recall restored vs base ec383ee36): each must flag. Values and prefixes sit in separate lists and
# are joined at run time, so no literal sits whole in this file (the privacy gate runs these same rules over the repo).
VALS = ['Qw8zX3vLm92"', "Qw8zX3vLm92Ab'", "Abcdef123456Xyz", "Abcdef123456Xyz", "9f86d081-884c-4d65-a8fc-3b7c4e5f6a7b",
        "Zm9vYmFy/Y2hhcmxpZQ/x9Kd8s7Fj2", "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'", "Testing1234Xy'", "correct-horse-battery-staple-9",
        'Zm9vYmFy/Y2hhcmxpZQ0123abcdEFGH" }', "Qw8zX3vLm92Ab</string>"]
ROWS = [("pwd-literal", 'pwd = "'), ("pwd-literal", "pwd: '"), ("netrc-bare-password", "password "),
        ("netrc-bare-password", "  password "), ("redis-requirepass", "requirepass "), ("redis-requirepass", "requirepass "),
        ("sql-password-literal", "CREATE USER a PASSWORD '"), ("sql-password-literal", "CREATE USER a WITH PASSWORD '"),
        ("redis-requirepass", "requirepass "), ("tf-variable-secret-id-default", 'variable "secret_id" { default = "'),
        ("plist-secret-string", "<key>apiKeyName</key><string>")]
assert len(VALS) == len(ROWS)
for (rid, pre), val in zip(ROWS, VALS):
    row = pre + val; assert rid in ids(row), (rid, row, ids(row))
