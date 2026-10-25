#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-10 (scripts/secret_scan.py): each new rule flags a live-format value, passes its decoy
twins (L009, a letters-only spring.datasource.password, is skipped on purpose: no shape of its own), and scans a 20KB line fast; the placeholder-word drop keeps a basic-auth placeholder password clean but a real value flagged. Tokens are built at runtime
so no contiguous credential-shaped literal sits in this file. Offline.
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


SYM = ALPHA + "@#%^&+=!"
LIVE = {
    "php-var-pass": ['$dbpass = "' + tok("a", 22) + '";  // wp-config.php'],
    "wp-key-salt-define": ["define('AUTH_" "KEY', '" + tok("w1", 64, SYM) + "');", 'define("NONCE_' 'SALT", "' + tok("w2", 64) + '");'],
    "basic-auth-symbol-password": ["cur" "l -u deploy:P4ssw0rd!x https://x.example.com", "cur" "l --user svc:" + tok("k1", 12) + "!# https://x.example.com"],
    "azure-sas-sig": ['sas_url = "https://acme.blob.core.example.com/c?sv=2022-11-02&sig=' + tok("s1", 44) + '%3D&se=2027-01-01"'],
}
DECOY = [
    "cur" "l -u deploy:${PASS}! https://x.example.com", "cur" "l -u deploy:short1! https://x.example.com",
    "$dbpass = getenv('DB_PASS');", '$dbpass = "";', '$dbpass = "short1";', '$dbpass = "${DB_PASS}";', "$pass = 'changeme1234';",
    "define('AUTH_" "KEY', 'put your unique phrase here');", "define('DB_NAME', '" + tok("d1", 40) + "');",
    "define('AUTH_" "KEY', 'short1');", "define('CACHE_" "KEY', '" + tok("d2", 40) + "');", "define('AUTH_" "KEY', getenv('AUTH_KEY'));",
    "https://acme.blob.core.example.com/c?sv=2022-11-02&se=2027-01-01", "https://acme.blob.core.example.com/c?sv=2022-11-02&sig=${SIG}&se=1", "https://example.com/c?sig=" + tok("d3", 44),
    "cur" "l -u user:PASSWORD https://api.example.com", "cur" "l -u user:password https://api.example.com", "cur" "l -u user:SECRET https://api.example.com",
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
bad += [("basic-auth-real", t) for t in ("cur" "l -u user:" + tok("c1", 20) + " https://api.example.com", "cur" "l -u svc:secret https://api.example.com", "$dbpass = \"a1b2c3d4e5f6\";") if not ids(t)]
# encrypted/hashed names are not a plaintext password (older rules may still flag the _pass suffix; only php-var-pass is pinned here)
bad += [("php-hash", t) for t in ('$encrypted_' 'pass = "a1b2c3d4e5f6";', '$hash' 'pass = "' + tok("e1", 20) + '";') if "php-var-pass" in ids(t)]
assert not bad, bad
for pre in ("$dbpass = '", "define('A_" "KEY', '", "?sv=2022-11-02&sig=", "password=Aa@", "x_password" * 500 + "x"):
    t0 = time.time(); ids(pre * (20000 // len(pre))); assert time.time() - t0 < 1.5, pre
print("secret extra rules w7: ok")
