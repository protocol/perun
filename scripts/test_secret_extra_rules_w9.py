#!/usr/bin/env python3
"""Regression pins for the secret-gate rules added after held-out-12 (scripts/secret_scan.py): each new rule flags a live-format value, passes its decoy
twins, and scans a 20KB line fast; the banlist half's second pass (refilter) no longer reports a csrf_token value (D045), while a plain token still reports.
Tokens are built at runtime so no contiguous credential-shaped literal sits in this file. Offline.
"""
import contextlib, hashlib, importlib.util, io, pathlib, tempfile, time

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


SA = '{"type": "service_' 'account", "project_id": "acme-prod", "private_k' 'ey_id": "'
SAX = '{"type": "service_' 'account", "project_id": "acme-example-1", "private_k' 'ey_id": "'
RT = "1/" "/0"
LIVE = {
    "gcp-sa-private-key-id": ["{'private_k" "ey_id': '" + tok("k7", 40, HEX) + "', 'type': 'service_" "account'}", '{"private_k' 'ey_id": "' + tok("k8", 40, HEX) + '", "client_id": "1", "type": "service_' 'account"}', SA + tok("k1", 40, HEX) + '"}', SAX + tok("k2", 40, HEX) + '"}', '{\n  "type": "service_' 'account",\n  "project_id": "acme",\n  "private_k' 'ey_id": "' + tok("k3", 40, HEX) + '",\n}'],
    "mysql-pwd-assign": ["DB_MYSQL_" "PWD=" + tok("m3", 18) + "9", "MYSQL_" "PWD=" + tok("m1", 18) + "9", 'mysql_' 'pwd = "' + tok("m2", 20) + '#1"'],
    "google-refresh-token": ["FIREBASE_TOKEN=" + RT + tok("g1", 60, ALPHA + "-_"), "refresh_token: " + RT + tok("g2", 70, ALPHA + "-_")],
}
DECOY = [
    '{"type": "authorized_' 'user", "private_k' 'ey_id": "' + tok("k4", 40, HEX) + '"}',  # not a service account
    '{"private_k' 'ey_id": "' + tok("k5", 40, HEX) + '"}', SA + "0" * 40 + '"}', SA + '${KEY_ID}"}', SA + tok("k6", 39, HEX) + '"}', SA + "abab" * 10 + '"}',
    "MYSQL_" "PWD=${DB_PASS}", "MYSQL_" "PWD=changeme123", "MYSQL_" "PWD=short1", "MYSQL_" "PWD=", "MYSQL_" "PWD=<password1>",
    "refresh_token: " + RT + "short", "https://example.com/v1/" + RT + tok("g3", 60, ALPHA + "-_"), "x" + RT + tok("g4", 60, ALPHA + "-_"),
]
bad = [(r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("decoy", t) for t in DECOY if ids(t)]
assert not bad, bad
for pre in ('"type": "service_' 'account", ', "MYSQL_" "PWD=", RT):
    t0 = time.time(); ids(pre * (20000 // len(pre))); assert time.time() - t0 < 1.5, pre


def refiltered(text):
    """Files the banlist second pass keeps (stdout of ss.refilter) for one line of text."""
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "x.txt"; f.write_text(text + "\n"); out = io.StringIO()
        with contextlib.redirect_stdout(out): ss.refilter(r"(token)[A-Za-z_-]*[\"']?[ ]*[:=][ ]*[\"'][A-Za-z0-9+/_=-]{32,}[\"']", [str(f)])
        return bool(out.getvalue())


def refiltered_pat(text, pat):
    """Like refiltered, for an arbitrary ERE."""
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "x.txt"; f.write_text(text + "\n"); out = io.StringIO()
        with contextlib.redirect_stdout(out): ss.refilter(pat, [str(f)])
        return bool(out.getvalue())


V = tok("v", 34)
assert not refiltered("csrf_" "token = \"" + V + '"') and not refiltered("x-xsrf-" "token: \"" + V + '"')
assert refiltered("api_" "token = \"" + V + '"') and refiltered("a" * 5000 + "_" "token = \"" + V + '"')
for n in ("csrf_pass" "word=", "XSRF_SECRET_" "KEY=", "example_pass" "word=", "dummy_pass" "word=", "fake_api_" "key="):
    assert refiltered_pat(n + tok("deny", 24), n.rstrip("=").rsplit("_", 1)[-1] + "=[^ ]+"), n
W = tok("csrfdeny", 16)  # csrf in a password name is no placeholder; only a token name is
for n in ("csrf_pass" "word=", "csrf_sec" "ret=", "csrfpass" "word="):
    assert ids(n + W) and refiltered_pat(n + W, "(password|secret)=[^ ]+"), n
for n in ("csrf_" "token = ", "X-CSRF-" "Token: ", "csrfmiddleware" "token="):
    assert not ids(n + V) and (n[0] == "X" or not refiltered(n + '"' + V + '"')), n  # the banlist pattern is case-sensitive: X-CSRF-Token never reaches the second pass
print("secret extra rules w9: ok")
