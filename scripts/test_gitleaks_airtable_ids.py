#!/usr/bin/env python3
"""Tests: review_checks.sh drops Airtable object IDs (rec/app/tbl/fld/viw + 14 alnum) from gitleaks airtable-api-key rows
in tree (--full), diff and history modes, with and without a repo .gitleaks.toml, while a legacy key-shaped value is still
reported. Real gitleaks >= 8.25.1 only; SKIPs (exit 0) when gitleaks is missing or older. Values are fictional and built at runtime."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RC = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/review_checks.sh"
REC = "rec" + "AbCdEfGh123456"  # fictional Airtable record ID (17 chars), built here so no source line matches a real key
KEY = "key" + "AbCdEfGh123456"  # fictional legacy-shaped key (17 chars): must still be reported
DATA = '{\n"airtableRecId": "%s",\n"airtableKey": "%s"\n}\n' % (REC, KEY)  # REC on line 2, KEY on line 3
REC_LINE, KEY_LINE = 2, 3
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def gitleaks_version():
    if not shutil.which("gitleaks"):
        return None
    out = subprocess.run(["gitleaks", "version"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else None


def run_rc(repo, *args):
    p = subprocess.run(["bash", str(RC), *args], cwd=repo, capture_output=True, text=True)
    rows = json.loads(p.stdout or "[]")
    return [r for r in rows if r.get("tool") in ("gitleaks", "gitleaks-history") and r.get("file") == "src/d.json"]


def make_repo(root, config=None):
    repo = Path(root)
    repo.mkdir(parents=True)
    subprocess.run(GIT + ["init", "-q", str(repo)], check=True)
    subprocess.run(GIT + ["-C", str(repo), "commit", "-q", "--allow-empty", "-m", "base"], check=True)
    subprocess.run(["git", "-C", str(repo), "branch", "base"], check=True)
    (repo / "src").mkdir()
    (repo / "src/d.json").write_text(DATA)
    if config is not None:
        (repo / ".gitleaks.toml").write_text(config)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(GIT + ["-C", str(repo), "commit", "-q", "-m", "data"], check=True)
    return repo


MODES = {"tree": ["--full"], "diff": ["--base", "base"], "history": ["--history", "--base", "base"]}
OWN_CONFIG = '[extend]\nuseDefault = true\n[allowlist]\npaths = [\'\'\'^docs/\'\'\']\n'
# a change that adds this config would allowlist its own secret if the per-file scan loaded the working-tree file
ATTACK_CONFIG = '[extend]\nuseDefault = true\n[allowlist]\npaths = [\'\'\'src/\'\'\']\n'
# no useDefault: no airtable-api-key rule exists, so a targetRules block would fail to load
CUSTOM_CONFIG = '[[rules]]\nid = "custom-rec"\ndescription = "fixture rule"\nregex = \'\'\'rec[A-Za-z0-9]{14}\'\'\'\nkeywords = ["rec"]\n'


class AirtableIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.version = gitleaks_version()
        if cls.version is None or cls.version < (8, 25, 1):
            raise unittest.SkipTest("gitleaks missing or older than 8.25.1")
        cls.tmp = tempfile.TemporaryDirectory(prefix="dcr-test-glab-")
        cls.plain = make_repo(Path(cls.tmp.name) / "plain")
        cls.owncfg = make_repo(Path(cls.tmp.name) / "owncfg", OWN_CONFIG)
        cls.attack = make_repo(Path(cls.tmp.name) / "attack", ATTACK_CONFIG)
        cls.custom = make_repo(Path(cls.tmp.name) / "custom", CUSTOM_CONFIG)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tmp", None):
            cls.tmp.cleanup()

    def lines(self, repo, mode):
        rows = run_rc(repo, *MODES[mode])
        if mode == "history":
            rows = [r for r in rows if r.get("tool") == "gitleaks-history"]
        else:
            rows = [r for r in rows if r.get("tool") == "gitleaks"]
        return {r.get("line") for r in rows}

    def test_rec_id_suppressed_and_key_reported_in_each_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                found = self.lines(self.plain, mode)
                self.assertNotIn(REC_LINE, found, "Airtable record ID still reported")
                self.assertIn(KEY_LINE, found, "legacy key-shaped value no longer reported")

    def test_repo_own_config_still_suppresses_rec_id(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                found = self.lines(self.owncfg, mode)
                self.assertNotIn(REC_LINE, found, "Airtable record ID reported under repo .gitleaks.toml")
                self.assertIn(KEY_LINE, found, "legacy key not reported under repo .gitleaks.toml")

    def test_config_added_by_change_cannot_allowlist_its_own_secret(self):
        found = self.lines(self.attack, "diff")
        self.assertIn(KEY_LINE, found, "a change's own .gitleaks.toml hid a key-shaped value in diff mode")

    def test_custom_rule_repo_config_without_usedefault_still_scans(self):
        # Without useDefault the config has no airtable-api-key rule: a [[allowlists]] targetRules on it is a load error
        # that would drop the whole scan, so the block is skipped and the custom rule must still fire.
        found = self.lines(self.custom, "diff")
        self.assertIn(REC_LINE, found, "custom-rule repo config did not scan (block load error?)")

    def test_config_added_by_change_cannot_hide_its_own_commit(self):
        # history reads .gitleaks.toml as of BASE: the attack commit's own config must not allowlist its key in history mode
        self.assertIn(KEY_LINE, self.lines(self.attack, "history"), "a change's own .gitleaks.toml hid its commit in history mode")



if __name__ == "__main__":
    if gitleaks_version() is None or gitleaks_version() < (8, 25, 1):
        print("SKIP gitleaks missing or older than 8.25.1")
        print("Tests: 0/0")
        sys.exit(0)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AirtableIds)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    total = res.testsRun
    passed = total - len(res.failures) - len(res.errors)
    print(f"Tests: {passed}/{total}")
    sys.exit(0 if res.wasSuccessful() else 1)
