"""pii_data_map.py (personal data kept or sent in the clear): committed national-id literals, unencrypted national-id columns, raw email or phone sent to an analytics host, opaque-ref and hashed
decoys, the usage contract and the review_checks.sh --full wiring. Fictional fixtures; one new file per feature."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import pii_data_map as P  # noqa: E402
PH = "-".join(("123", "45", "6789"))  # built at runtime: the privacy gate bans SSN-shaped literals

SEED, COL, SEND = "plaintext-national-id", "unencrypted-national-id-column", "raw-pii-to-third-party"


def rows(files):
    """(file, line, rule) rows from analyze() for a fresh temp repo built from {relative path: lines}."""
    with tempfile.TemporaryDirectory() as t:
        for rel, lines in files.items():
            p = Path(t) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [(f, ln, r) for f, ln, r, _ in P.analyze(t)[0]]


JS = [
    "const seed = [",
    "  { name: 'Jane Smith', ssn: '900-11-2222', dob: '1990-01-01' },",
    "  { name: 'Joe Bloggs', ssn: '900-11-3333', dob: '1991-01-01' },",
    "  { customerRef: 'cus_1a2b', vaultRef: 'vault://pii/1a2b' },",
    "];",
    "axios.post('https://analytics.vendor.example.com/collect', { email: req.body.email, phone: req.body.phone });",
    "axios.post('https://analytics.vendor.example.com/collect', { user: sha(req.body.email) });",
    "axios.post('http://localhost:9000/collect', { email: req.body.email });",
]


class T(unittest.TestCase):
    def test_seed_literal_one_row_per_run_and_opaque_refs_clean(self):
        self.assertEqual([("a.js", 2, SEED), ("a.js", 6, SEND)], rows({"a.js": JS}))

    def test_placeholder_and_test_paths_are_skipped(self):
        self.assertEqual([], rows({"a.js": [f"const s = '{PH}', z = '000-00-0000';"], "a.test.js": JS}))

    def test_python_column_and_trailing_comment_is_not_code(self):
        py = ["class U:", "    ssn = ''  # stored unencrypted", "    national_id = EncryptedField()", "    email = ''"]
        self.assertEqual([("m.py", 2, COL)], rows({"m.py": py}))

    def test_go_payload_built_above_the_call_and_hashed_decoy(self):
        go = ['p, _ := json.Marshal(map[string]string{"email": r.FormValue("email")})',
              'http.Post("https://analytics.vendor.example.com/c", "x", bytes.NewReader(p))',
              'q, _ := json.Marshal(map[string]string{"user": sha(r.FormValue("email"))})',
              'http.Post("https://analytics.vendor.example.com/c", "x", bytes.NewReader(q))']
        self.assertEqual([("a.go", 2, SEND)], rows({"a.go": go}))

    def test_java_com_example_package_is_scanned(self):
        j = ['new Customer(1, "Jane Smith", "900-11-2222");']
        self.assertEqual([("src/com/example/A.java", 1, SEED)], rows({"src/com/example/A.java": j}))

    def test_round2_name_edges_placeholders_comments(self):
        js = ["const user_ssn = '900-11-2222';", "", "const customer_tax_id = '12345678901';", f"const ssn = '{PH}';", "", f"const x = ['{PH}', '900-11-4444'];",
              "// ssn = '900-11-5555'", "# ssn = '900-11-6666'"]
        self.assertEqual([("a.js", 1, SEED), ("a.js", 3, SEED), ("a.js", 6, SEED)], rows({"a.js": js}))
        send = ["axios.post('https://analytics.vendor.example.com/c', { user_email: e, phone_number: p, auth_token: t });"]
        self.assertEqual([("a.js", 1, SEND)], rows({"a.js": send}))
        self.assertEqual([], rows({"a.js": ["axios.post('https://analytics.vendor.example.com/c', { myemail: 1 });"]}))

    def test_round2_multiline_calls_and_payload_scope(self):
        py = ["requests.post(", '    "https://analytics.vendor.example.com/c",', '    json={"email": e})']
        self.assertEqual([("a.py", 2, SEND)], rows({"a.py": py}))
        far = ["email = form.get('email')", "x = 1", "y = 2", "z = 3", "requests.post('https://analytics.vendor.example.com/c', json={'n': 1})"]
        self.assertEqual([], rows({"a.py": far}))
        near = ["payload = {'email': e}", "requests.post('https://analytics.vendor.example.com/c', json=payload)"]
        self.assertEqual([("a.py", 2, SEND)], rows({"a.py": near}))
        unrelated = ["other = {'email': e}", "requests.post('https://analytics.vendor.example.com/c', json=payload)"]
        self.assertEqual([], rows({"a.py": unrelated}))

    def test_round2_multiline_column_encrypted(self):
        py = ["class U:", "    ssn = Column(", "        EncryptedType(String), nullable=False)", "    tax_id = Column(String(20))"]
        self.assertEqual([("m.py", 4, COL)], rows({"m.py": py}))

    def test_round2_walk_regular_files_and_cap(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "real.go").write_text('x := "900-11-2222"\n')
            os.symlink(Path(t) / "real.go", Path(t) / "link.go")
            big = Path(t) / "big.java"
            big.write_text('String s = "900-11-2222";\n' + " " * (P.MAX_BYTES + 1))
            self.assertEqual([("real.go", 1, SEED)], [(f, ln, r) for f, ln, r, _ in P.analyze(t)[0]])

    def test_round2_main_prints_no_value(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "a.js").write_text("const s = '900-11-2222', e = 'jane@example.com';\naxios.post('https://analytics.vendor.example.com/c', { email: 'jane@example.com' });\n")
            p = subprocess.run([sys.executable, "-I", str(SK / "pii_data_map.py"), t], capture_output=True, text=True)
            self.assertEqual(2, len(p.stdout.splitlines()))
            self.assertNotIn("900-11-2222", p.stdout + p.stderr)
            self.assertNotIn("jane@example.com", p.stdout + p.stderr)

    def test_round3_camel_case_and_block_headers(self):
        send = ["fetch('https://analytics.vendor.example.com/c', { body: JSON.stringify({ userEmail: r.userEmail }) });"]
        self.assertEqual([("a.js", 1, SEND)], rows({"a.js": send}))
        keyed = ["const userSSN = '900-11-2222';", "", "const userSsn = '123456789012';"]
        self.assertEqual([("a.js", 1, SEED), ("a.js", 3, SEED)], rows({"a.js": keyed}))
        for head in ("function track(email) {", "if (user.email) {"):
            self.assertEqual([], rows({"a.js": [head, "  fetch('https://analytics.vendor.example.com/c');", "}"]}), head)

    def test_round3_comment_stripped_call_text(self):
        py = ["track('https://analytics.vendor.example.com/c',", "      email)  # hash it later"]
        self.assertEqual([("a.py", 1, SEND)], rows({"a.py": py}))

    def test_round4_url_is_last_argument(self):
        js = ["track(", "  user.email,", "  'https://analytics.vendor.example.com/c');"]
        self.assertEqual([("a.js", 3, SEND)], rows({"a.js": js}))
        self.assertEqual([], rows({"a.js": ["track(", "  user.name,", "  'https://analytics.vendor.example.com/c');"]}))

    def test_round5_probe_table(self):
        H = "https://analytics.vendor.example.com/c"
        table = [  # (files, expected rows)
            ({"a.js": ["const user_ssn = '900-11-2222';", "", "const phone_number = '5551234567';"]}, [("a.js", 1, SEED)]),
            ({"a.js": [f"const ssn = '{PH}';"]}, []),
            ({"a.js": ["// ssn = '900-11-2222'"], "a.py": ["# ssn = '900-11-2222'"]}, []),
            ({"a.js": ["fetch('%s', { email: e, auth_token: t });" % H]}, [("a.js", 1, SEND)]),
            ({"a.py": ["requests.post(", '    "%s",' % H, '    json={"email": e})']}, [("a.py", 2, SEND)]),
            ({"a.js": ["function track(email) {", "  fetch('%s');" % H, "}"]}, []),
            ({"a.js": ["if (user.email) {", "  fetch('%s');" % H, "}"]}, []),
            ({"a.js": ["fetch('%s', { body: userEmail });" % H]}, [("a.js", 1, SEND)]),
            ({"a.js": ["track(", "  user.email,", "  '%s');" % H]}, [("a.js", 3, SEND)]),
            ({"a.js": ["useEffect(() => {", "  const e = user.email;", "  fetch('%s', { id: 1 });" % H, "}, []);"]}, []),
            ({"a.js": ["const xs = ['jane@example.com', email];", "fetch('%s', { id: 1 });" % H]}, []),
            ({"a.js": ["track({", "  email: e,", "  url: '%s'," % H, "});"]}, [("a.js", 3, SEND)]),
        ]
        for files, want in table:
            self.assertEqual(want, rows(files), files)

    def test_usage_and_wiring(self):
        p = subprocess.run([sys.executable, "-I", str(SK / "pii_data_map.py")], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stderr), (2, "usage: pii_data_map.py DIR\n"))
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, text):
                g = Path(t) / name
                g.mkdir()
                (g / "app.js").write_text(text, encoding="utf-8")
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            rc = SK / "review_checks.sh"
            r = subprocess.run(["bash", str(rc), "--full", "--repo", str(repo("g", "\n".join(JS) + "\n"))], capture_output=True, text=True, env=env)
            got = [(x["file"], x["line"], x["rule"]) for x in json.loads(r.stdout) if x["tool"] == "pii-data"]
            self.assertEqual([("app.js", 2, SEED), ("app.js", 6, SEND)], sorted(got, key=lambda g: g[1]))
            r = subprocess.run(["bash", str(rc), "--full", "--repo", str(repo("g2", "export const a = 1;\n"))], capture_output=True, text=True, env=env)
            self.assertEqual([], [x for x in json.loads(r.stdout) if x["tool"] == "pii-data"])


if __name__ == "__main__":
    unittest.main()
