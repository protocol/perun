#!/usr/bin/env python3
"""Pins that the privacy gate's secret scanner (scripts/secret_scan.py, vendored gitleaks rules) flags Anthropic API/admin keys
and Airtable personal access tokens / legacy keys, and stays quiet on near-misses. These four rules were never exercised by a
test, so a rule edit could drop them unseen. Fixtures are built at runtime from a hash (no literal key-shaped string in this
file, so the gate does not fire on it) and are obviously fake: derived from a test seed, never issued by any provider. Offline."""
import hashlib, importlib.util, pathlib, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
B64URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"


def tok(seed, n, alpha=B64URL):
    """Deterministic string of length n over alpha, derived from seed."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


ANT = "sk-" + "ant-"
KEY = ANT + "api03-" + tok("ant-key", 93) + "AA"
ADMIN = ANT + "admin01-" + tok("ant-admin", 93) + "AA"
PAT = "pat" + tok("airtable-pat", 14, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") + "." + hashlib.sha256(b"airtable-pat").hexdigest()
LEGACY = "key" + tok("airtable-legacy", 14, "abcdefghijklmnopqrstuvwxyz0123456789")


class AnthropicAirtable(unittest.TestCase):
    def test_anthropic_api_key(self):
        for line in (f"ANTHROPIC_API_KEY={KEY}", f'client = Anthropic(api_key="{KEY}")', f"log.info('auth {KEY}')"):
            self.assertIn("anthropic-api-key", ids(line), line.replace(KEY, "<KEY>"))

    def test_anthropic_admin_key(self):
        self.assertIn("anthropic-admin-api-key", ids(f"ANTHROPIC_ADMIN_KEY={ADMIN}"))

    def test_airtable_personal_access_token(self):
        for line in (f"AIRTABLE_TOKEN={PAT}", f'headers = {{"Authorization": "Bearer {PAT}"}}  # airtable'):
            self.assertIn("airtable-personnal-access-token", ids(line), line.replace(PAT, "<PAT>"))  # rule id keeps the upstream spelling

    def test_airtable_legacy_key(self):
        self.assertIn("airtable-api-key", ids(f"AIRTABLE_API_KEY={LEGACY}"))

    def test_near_misses_are_clean(self):
        short = ANT + "api03-" + tok("s", 20) + "AA"  # too short
        self.assertNotIn("anthropic-api-key", ids(f"ANTHROPIC_API_KEY={short}"))
        self.assertNotIn("anthropic-api-key", ids(KEY[:-2] + "BB"))  # real keys end in AA
        self.assertEqual(ids("see sk-ant-... in the console, and airtable pat<id>.<hash> in the docs"), [])
        self.assertNotIn("airtable-personnal-access-token", ids(f"AIRTABLE_TOKEN={PAT[:-1]}"))  # 63 hex, not 64

    def test_cli_flags_the_file_and_never_prints_the_secret(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "env.txt"
            p.write_text(f"ANTHROPIC_API_KEY={KEY}\nAIRTABLE_TOKEN={PAT}\n")
            r = subprocess.run([sys.executable, str(ROOT / "scripts/secret_scan.py"), str(p)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("anthropic-api-key", r.stdout + r.stderr)
        self.assertNotIn(KEY[:30], r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
