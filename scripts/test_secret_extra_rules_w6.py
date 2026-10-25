#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-9 (scripts/secret_scan.py): each new rule flags a live-format value, passes its decoy
twins, and scans a 20KB line fast. Skipped on purpose: L029 (a service-account private_key_id is an identifier, not the key, and 38 hex is not the real 40),
L038 (a sed replacement into a conf file) and L056 (a bare string argument to Session::new) have no shape of their own. Tokens are built at runtime
with each credential-shaped literal split by a helper, so no contiguous token sits in this file. Offline.
"""
import hashlib, importlib.util, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n, alpha=ALPHA):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


def cat(*parts):
    """Join parts at runtime so a vendor prefix never sits next to its body in this file."""
    return "".join(parts)


HEX = "0123456789abcdef"
LIVE = {
    "resend-key": [cat("re", "_", tok("r1", 8), "_", tok("r2", 24))],
    "okta-ssws-token": [cat("Authorization: SS", "WS 00", tok("o", 38, ALPHA + "-_"))],
    "cli-password-attached": [f"mysql -p{tok('c1', 16)} -e 'select 1'", f"x\\n    command = \"mysql -p{tok('c2', 16)} -e 'select 1'\"\\n  }}"],
    "pass-key-assign": [f"ansible_become_pass: {tok('p1', 18)}", f"ansible-vault-pass: {tok('p2', 24)}\\nvault_id: prod", f"ansible_become_pass={tok('p3', 18)}"],
    "url-query-token": [f"GET /v1/items?access_token={tok('u1', 40, HEX)}&limit=10 HTTP/1.1", f"https://api.acme.example.com/x?api_key={tok('u2', 32)}"],
    "xml-add-key-value": [f'<add key="StorageKey" value="{tok("x1", 42)}==" />'],
    "xml-password-element": [f"<password>{tok('x5', 14)}</password>"],
    "bracket-secret-assign": [f"$config['jwt_secret'] = '{tok('b1', 40, HEX)}';", f'os.environ["SIGNING_KEY"] = "{tok("b2", 40)}"'],
}
DECOY = [
    "recaptcha_site_key = 6Le" + tok("d0", 37), "mysql -p -e 'select 1'", "mysql -pretty -e 'select 1'", "mysql -p${DB_PASSWORD} -e 'select 1'", "mysql -p $DB_PASSWORD",
    "ansible_become_pass: !vault |", "ansible_become_pass: '{{ vault_become_pass }}'", "ansible_become_pass: changeme1", "ansible_become_pass: short1", "no_pass: some_snake_value_1",
    "GET /v1/items?access_token=${TOKEN}&limit=10", "GET /v1/items?access_token=short1", "GET /v1/items?token=" + tok("d1", 40, HEX), "https://acme.example.com/x?api_key=YOUR_API_KEY_HERE1",
    '<add key="StorageKey" value="${STORAGE_KEY}" />', '<add key="PageSize" value="' + tok("d2", 42) + '" />', '<add key="StorageKey" value="short1" />',
    "<password>${DB_PASSWORD}</password>", "<password>********</password>", "<password>short1</password>", "<passwordPolicy>" + tok("d3", 14) + "</passwordPolicy>",
    "$config['jwt_secret'] = getenv('JWT_SECRET');", "$config['jwt_secret'] = '';", "$config['base_url'] = '" + tok("d4", 40, HEX) + "';", "$config['jwt_secret'] = 'https://acme.example.com/secret1';",
    'os.environ["SIGNING_KEY_PATH"] = \'/etc/keys/signing_key_v2.pem\'', 'os.environ["SIGNING_KEY_PATH"] = "./keys/signing_key_v2_abc"', 'os.environ["SIGNING_KEY_FILE"] = "keys/signing_key_v2.pem"',
    'os.environ["CACHE_KEY"] = "' + tok("d5", 40) + '"', 'os.environ["SIGNING_KEY"] = "short1"', 're_' + "abcdefgh_short", "re_" + tok("d6", 8) + "_" + tok("d7", 24) + "x",
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
# the site-key drop must not hide a recaptcha secret
bad += [("twin", t) for t in ("recaptcha_secret_key = 6Le" + tok("d0", 37), "SITE_KEY_SE" "CRET=" + tok("s1", 40), "site_key_pri" "vate: " + tok("s2", 40), "site_key_se" "cret=" + tok("s3", 40, HEX), "SITEKEY_SE" "CRET=" + tok("s4", 40), "sitekey_pri" "vate: " + tok("s5", 40)) if not ids(t)]
assert not bad, bad
# bounded: no ReDoS on 20KB lines of each rule's trigger text
for pre in ("mysql -p", "ansible_become_pass: ", "?access_token=", '<add key="', "<password>", "$config['", "ansible-" * 500 + "x"):
    t0 = time.time(); ids(pre * (20000 // len(pre))); assert time.time() - t0 < 1.5, pre
print("secret extra rules w6: ok")
