#!/usr/bin/env python3
"""secret_exposure_triage.py: three placements (HEAD, history only, tag-only) plus a clean twin repo. Offline, hermetic temp repos, fake secrets."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import secret_exposure_triage as st  # noqa: E402

S_HEAD, S_HIST, S_TAG = "FAKEKEY-head-0000000000000001", "FAKEKEY-hist-0000000000000002", "FAKEKEY-tag-00000000000000003"
def _j(*parts):  # built at runtime so no literal in this file looks like a credential
    return "".join(parts)


FX1 = _j("q8Zk3", "Rt7Wm", "1Xv5B", "n9Lc2", "Hd6Jf", "4Sg0P", "a")  # fake, high-entropy enough for a generic-api-key rule
FX2 = _j("m3Vb8", "Nc5Xz", "1Lk7Q", "w4Er9", "Ty2Ui", "6Op0A", "s")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "Jane Smith", "GIT_AUTHOR_EMAIL": "jane@example.com", "GIT_COMMITTER_NAME": "Jane Smith", "GIT_COMMITTER_EMAIL": "jane@example.com"}


def g(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True, env=ENV).stdout


def commit(repo, name, text):
    (repo / name).write_text(text)
    g(repo, "add", name)
    g(repo, "commit", "-qm", f"edit {name}")


def finding(name, secret, line=1):
    return {"RuleID": "generic-api-key", "File": name, "StartLine": line, "Secret": secret, "Match": "key=" + secret, "Fingerprint": f"{name}:generic-api-key:{line}"}


def cli(rep, repo, *extra):
    return subprocess.run([sys.executable, "-I", str(SK / "secret_exposure_triage.py"), str(rep), str(repo), *extra], capture_output=True, text=True, check=True)


class T(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name) / "repo"
        self.repo.mkdir()
        g(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self.td.cleanup()

    def test_three_placements(self):
        r = self.repo
        commit(r, "a.env", f"KEY={S_HEAD}\n")
        commit(r, "b.env", f"KEY={S_HIST}\n")
        commit(r, "b.env", "KEY=removed\n")
        g(r, "checkout", "-qb", "side")
        commit(r, "c.env", f"KEY={S_TAG}\n")
        g(r, "tag", "v1")
        g(r, "checkout", "-q", "main")
        g(r, "branch", "-qD", "side")
        commit(r, "d.txt", "later\n")
        rows = st.triage([finding("c.env", S_TAG), finding("b.env", S_HIST), finding("a.env", S_HEAD), finding("a.env", S_HEAD, 2)], str(r), visibility="private")
        self.assertEqual([x["priority"] for x in rows], [1, 2, 3])
        head, hist, tag = rows
        self.assertTrue(head["at_head"] and head["in_default"])
        self.assertEqual(head["commits_since"], 3)
        self.assertFalse(hist["at_head"])
        self.assertTrue(hist["in_default"])
        self.assertTrue(tag["in_tag"] and not tag["in_default"] and not tag["at_head"])
        self.assertTrue(head["first_date"])

    def test_public_tag_or_remote_branch_is_p0(self):
        """Public or unknown visibility: a tag or a remote-tracking branch is as public as the default branch (P0); a local-only branch stays P3."""
        r = self.repo
        commit(r, "base.txt", "x\n")
        for br, name, sec in (("side", "t.env", S_TAG), ("feature", "f.env", S_HIST), ("local", "l.env", S_HEAD)):
            g(r, "checkout", "-qb", br, "main")
            commit(r, name, f"KEY={sec}\n")
        g(r, "tag", "v1", "side")
        g(r, "update-ref", "refs/remotes/origin/feature", "feature")
        g(r, "checkout", "-q", "main")
        g(r, "branch", "-qD", "side", "feature")
        fs = [finding("t.env", S_TAG), finding("f.env", S_HIST), finding("l.env", S_HEAD)]
        for vis, want in (("public", {"t.env": 0, "f.env": 0, "l.env": 3}), ("unknown", {"t.env": 0, "f.env": 0, "l.env": 3}), ("private", {"t.env": 3, "f.env": 3, "l.env": 3})):
            self.assertEqual({x["file"]: x["priority"] for x in st.triage(fs, str(r), visibility=vis)}, want, vis)

    def test_output_never_prints_secret(self):
        commit(self.repo, "a.env", f"KEY={S_HEAD}\n")
        rep = Path(self.td.name) / "rep.json"
        rep.write_text(json.dumps([finding("a.env", S_HEAD)]))
        for extra in ([], ["--json"]):
            out = cli(rep, self.repo, *extra)
            self.assertNotIn(S_HEAD, out.stdout + out.stderr)
        self.assertIn("a.env:1", cli(rep, self.repo).stdout)

    def test_binary_blob_and_redacted(self):
        r = self.repo
        (r / "bin.dat").write_bytes(b"\xff\xfe\x00" + S_HEAD.encode() + b"\x80\n")
        g(r, "add", "bin.dat")
        g(r, "commit", "-qm", "binary blob")
        rows = st.triage([finding("bin.dat", S_HEAD), {**finding("bin.dat", "REDACTED", 9), "Fingerprint": "red:1"}], str(r), visibility="private")
        self.assertEqual([x["priority"] for x in rows], [1, 4])
        self.assertTrue(rows[0]["at_head"])
        self.assertIsNone(rows[1]["first_commit"])

    def test_visibility_and_moved_file(self):
        r = self.repo
        commit(r, "old.env", f"KEY={S_HEAD}\n")
        g(r, "mv", "old.env", "moved.env")
        g(r, "commit", "-qm", "move")
        rep = [finding("old.env", S_HEAD)]  # the report still names the old path
        for vis, want in (("public", 0), ("unknown", 0), ("private", 1)):
            row = st.triage(rep, str(r), visibility=vis)[0]
            self.assertEqual(row["priority"], want, vis)
            self.assertTrue(row["at_default"], "moved file must still count as present")
        self.assertIn("assume compromised", st.NAMES[0])

    def test_bad_repo_exits_2_cleanly(self):
        rep = Path(self.td.name) / "r.json"
        rep.write_text("[]")
        p = subprocess.run([sys.executable, "-I", str(SK / "secret_exposure_triage.py"), str(rep), str(Path(self.td.name) / "nope")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("not a git repository", p.stderr)

    def test_tsv_redaction_from_fixture_report(self):  # no gitleaks needed: a fixture report in gitleaks' JSON shape
        commit(self.repo, "a.env", f"KEY={S_HEAD}\n")
        rep = Path(self.td.name) / "fx.json"
        rep.write_text(json.dumps([finding("a.env", S_HEAD)]))
        out = cli(rep, self.repo, "--tsv", "--visibility", "public")
        self.assertNotIn(S_HEAD, out.stdout + out.stderr)
        self.assertTrue(out.stdout.startswith("a.env\t1\texposure-p0\t"), out.stdout)

    def test_dangling_commit_is_unranked(self):
        commit(self.repo, "a.txt", "x\n")
        dangling = "0" * 40
        row = st.triage([{"RuleID": "k", "File": "gone.txt", "StartLine": 1, "Fingerprint": "f:1", "Commit": dangling, "Date": "2020-01-01T00:00:00Z"}], str(self.repo))[0]
        self.assertEqual(row["priority"], 4)

    def test_usage_prints_paragraph(self):
        p = subprocess.run([sys.executable, "-I", str(SK / "secret_exposure_triage.py")], capture_output=True, text=True)
        self.assertIn("REPORT.json [REPO]", p.stderr)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_review_checks_history_row(self):
        commit(self.repo, "cfg.env", f'api_key = "{FX1}"\n')
        commit(self.repo, "cfg.env", "api_key = removed\n")
        out = subprocess.run(["bash", str(SK / "review_checks.sh"), "--repo", str(self.repo), "--base", "main", "--full-history"], capture_output=True, text=True, env={**ENV, "REVIEW_HEAVY_LEASE": "0"}, check=False)
        text = out.stdout + out.stderr
        self.assertNotIn(FX1, text)
        self.assertIn("secret-exposure", text)
        self.assertIn("exposure-p0", text)

    def test_keep_filters_unlisted(self):
        commit(self.repo, "a.env", f"KEY={S_HEAD}\n")
        commit(self.repo, "b.env", f"KEY={S_HIST}\n")
        rows = st.triage([finding("a.env", S_HEAD), finding("b.env", S_HIST)], str(self.repo), keep={("b.env", "1", "generic-api-key")})
        self.assertEqual([x["file"] for x in rows], ["b.env"])

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_review_checks_skips_suppressed_fingerprint(self):
        r = self.repo
        commit(r, "ignored.env", f'api_key = "{FX1}"\n')
        commit(r, "kept.env", f'api_key = "{FX2}"\n')
        rep = Path(self.td.name) / "gl.json"
        subprocess.run(["gitleaks", "detect", "--no-banner", "--exit-code", "0", "-f", "json", "-r", str(rep), "-s", str(r)], check=True, capture_output=True)
        fp = next(x["Fingerprint"] for x in json.loads(rep.read_text()) if x["File"] == "ignored.env")
        commit(r, ".gitleaksignore", fp + "\n")
        out = subprocess.run(["bash", str(SK / "review_checks.sh"), "--repo", str(r), "--base", "main", "--full-history"], capture_output=True, text=True, env=ENV, check=False)
        self.assertTrue(out.stdout.lstrip().startswith("["), "default output is JSON")
        files = {x["file"] for x in json.loads(out.stdout) if x["tool"] == "secret-exposure"}
        self.assertIn("kept.env", files, out.stdout + out.stderr)
        self.assertNotIn("ignored.env", files)
        self.assertNotIn(FX2, out.stdout + out.stderr)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_review_checks_likely_fixture_and_corroboration(self):
        r = self.repo
        commit(r, "kept.env", f'api_key = "{FX1}"\n')
        commit(r, "pins.lock", f'integrity_api_key = "{FX2}"\n')  # lf(): a content hash in a lockfile tags the row [likely-fixture: ...]
        out = subprocess.run(["bash", str(SK / "review_checks.sh"), "--repo", str(r), "--base", "main", "--full-history"], capture_output=True, text=True, env=ENV, check=False)
        rows = json.loads(out.stdout)
        exp = [x for x in rows if x["tool"] == "secret-exposure"]
        self.assertTrue(any(x["file"] == "kept.env" for x in exp), out.stdout + out.stderr)
        # a likely-fixture gitleaks row is never triaged, so it gets no exposure row
        self.assertTrue(any(x.get("hint") == "likely-fixture" for x in rows if x["file"] == "pins.lock"), out.stdout)
        self.assertFalse([x for x in exp if x["file"] == "pins.lock"], out.stdout)
        # a secret-exposure row never counts as corroboration (it derives from the gitleaks report)
        self.assertTrue(all("tools" not in x and "corroborated" not in x["message"] for x in exp), out.stdout)

    def test_clean_twin(self):
        commit(self.repo, "a.txt", "nothing here\n")
        self.assertEqual(st.triage([], str(self.repo)), [])
        rep = Path(self.td.name) / "clean.json"
        rep.write_text("[]")
        self.assertEqual(cli(rep, self.repo).stdout.strip(), "no findings")


if __name__ == "__main__":
    unittest.main()
