#!/usr/bin/env python3
"""insecure_defaults.py: one positive per rule, decoys that must stay silent, and the review_checks.sh --full row. Fictional code only."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"
ENV = dict(os.environ, PATH="/usr/bin:/bin:" + os.environ.get("PATH", ""))

POS = {
    "flag.py": ('import os\nAUTH_OFF = os.environ.get("AUTH_DISABLED", "true")\nREQ = os.getenv("REQUIRE_AUTH", "false")\nV = os.getenv("VERIFY_SSL", default="0")\n',
                {(2, "default-on-security-flag"), (3, "default-on-security-flag"), (4, "default-on-security-flag")}),
    "flag.js": ('const off = process.env.AUTH_DISABLED ?? true;\nconst x = process.env.SKIP_TLS_VERIFY || "1";\n',
                {(1, "default-on-security-flag"), (2, "default-on-security-flag")}),
    "auth.py": ("def is_authorized(token):\n    try:\n        return check(token)\n    except Exception:\n        log()\n        return True\n", {(6, "fail-open-exception")}),
    "auth_if.js": ("function isAuthorized(req) {\n  if (req.token) {\n    try { return check(req) } catch (e) {\n      return true;\n    }\n  }\n}\n", {(3, "fail-open-exception")}),
    "auth.js": ("async function verifyToken(req, res, next) {\n  try { await check(req) } catch (e) {\n    return next();\n  }\n}\n", {(2, "fail-open-exception")}),
    "tls.py": ("import requests\nrequests.get(url, verify=False)\nctx.check_hostname = False\n", {(2, "tls-verify-off"), (3, "tls-verify-off")}),
    "tls.js": ("const a = new https.Agent({ rejectUnauthorized: false });\n", {(1, "tls-verify-off")}),
    "tls.go": ("c := &tls.Config{InsecureSkipVerify: true}\n", {(1, "tls-verify-off")}),
    "jwt.py": ('jwt.decode(t, key, algorithms=["none"])\njwt.decode(t, options={"verify_signature": False})\njwt.decode(t, key, verify=False)\n',
               {(1, "jwt-unverified"), (2, "jwt-unverified"), (3, "jwt-unverified")}),
    "jwt.js": ("const h = { alg: 'none' };\n", {(1, "jwt-unverified")}),
    "settings.py": ('DEBUG = True\nD = os.environ.get("FLASK_DEBUG", "1")\n', {(1, "debug-on-default"), (2, "debug-on-default")}),
    "cors.js": ("app.use(cors({\n  origin: '*',\n  credentials: true,\n}));\n", {(2, "cors-wildcard-credentials")}),
    "cors.py": ('CORS(app, origins="*", supports_credentials=True)\n', {(1, "cors-wildcard-credentials")}),
    "dj.py": ("CORS_ORIGIN_ALLOW_ALL = True\nX = 1\n" * 3 + "CORS_ALLOW_CREDENTIALS = True\n", {(1, "cors-wildcard-credentials"), (3, "cors-wildcard-credentials"), (5, "cors-wildcard-credentials")}),
}
DECOYS = {
    "tests/test_a.py": "requests.get(u, verify=False)\nDEBUG = True\n",
    "src/a.spec.ts": "const a = { rejectUnauthorized: false };\n",
    "tls_ok.js": "const a = { rejectUnauthorized: true };\nconst b = { rejectUnauthorized: process.env.NODE_ENV === 'production' };\n",
    "tls_ok.py": "requests.get(u, verify=True)\nrequests.get('https://localhost:8443', verify=False)\n# verify=False\n",
    "tls_ok.go": "c := &tls.Config{InsecureSkipVerify: false}\n",
    "flag_ok.py": 'a = os.getenv("AUTH_DISABLED", "false")\nb = os.getenv("REQUIRE_AUTH", "true")\nc = os.getenv("SKIP_MIGRATIONS", "true")\nd = os.getenv("AUTH_DISABLED")\n',
    "enable_ok.py": 'a = os.getenv("ENABLE_CORS", "false")\nb = os.getenv("ENABLE_SSL", "0")\n',
    "flag_ok.js": "const a = process.env.AUTH_DISABLED ?? false;\nconst b = process.env.REQUIRE_AUTH ?? true;\n",
    "auth_ok.py": "def is_authorized(t):\n    try:\n        return check(t)\n    except Exception:\n        return False\ndef parse_int(v):\n    try:\n        return int(v)\n    except Exception:\n        return True\n",
    "auth_ok.js": "async function verifyToken(req, res, next) {\n  try { await check(req) } catch (e) { return next(e); }\n}\n",
    "jwt_ok.py": 'jwt.decode(t, key, algorithms=["HS256"])\nif alg == "none":\n    raise ValueError\n',
    "dev_settings.py": "DEBUG = True\n",
    "debug_ok.py": 'DEBUG = False\nD = os.environ.get("DEBUG", "false")\n',
    "cors_ok.js": "app.use(cors({ origin: '*' }));\n\n\n\n\napp.use(cors({ origin: 'https://app.example.com', credentials: true }));\n",
}


def scan(files):
    with tempfile.TemporaryDirectory() as t:
        for n, s in files.items():
            p = Path(t, n)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(s)
        r = subprocess.run(["python3", "-I", str(S / "insecure_defaults.py"), t], capture_output=True, text=True, env=ENV)
        return {tuple(x.split("\t")[:3]) for x in r.stdout.splitlines()}, r.stderr


class InsecureDefaults(unittest.TestCase):
    def test_positives_exact(self):
        got, _ = scan({n: s for n, (s, _) in POS.items()})
        want = {(n, str(l), r) for n, (_, e) in POS.items() for l, r in e}
        self.assertEqual(got, want)

    def test_decoys_silent(self):
        got, err = scan(DECOYS)
        self.assertEqual(got, set())
        self.assertIn("0 leads", err)

    def test_no_source(self):
        self.assertIn("no source files", scan({"a.txt": "verify=False"})[1])

    def test_review_checks_full_row(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "a.js").write_text(POS["tls.js"][0])
            for a in (["init", "-q"], ["add", "a.js"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "f"]):
                subprocess.run(["git", "-C", t, *a], check=True, capture_output=True, env=ENV)
            r = subprocess.run(["bash", str(S / "review_checks.sh"), "--full", "--repo", t], capture_output=True, text=True, env=dict(ENV, PATH="/usr/bin:/bin"))
        rows = [x for x in json.loads(r.stdout) if x["tool"] == "insecure-defaults"]
        self.assertEqual([(x["file"], x["line"], x["rule"]) for x in rows], [("a.js", 1, "tls-verify-off")])


if __name__ == "__main__":
    unittest.main()
