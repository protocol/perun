#!/usr/bin/env python3
"""Hosts parity (2026-10-16): Qwen Code and Grok Build skill roots, safety lines, recorded docs, honest H10 counts.

Fixture repo and HOME live under $TMPDIR. Hosts that read `.agents/skills` (Devin CLI, Kimi Code, Pi, Antigravity) need
no new directory, so the test checks that the default install writes it."""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perun_doctor  # noqa: E402

os.environ["DCR_NO_PROBE"] = "1"
NEW = ((".qwen", "Qwen Code"), (".grok", "Grok Build"))
IDX = (ROOT / "docs/standards-index.md").read_text()
SEC = IDX.split("agent skill roots, hosts parity", 1)[1]
RIVAL = ("Claude Code", "Antigravity", "Codex App", "Codex CLI", "Cursor", "Devin CLI", "Factory Droid", "Gemini CLI",
         "GitHub Copilot CLI", "Grok Build CLI", "Kimi Code", "OpenCode", "Pi", "Qwen Code", "Hermes Agent", "Muse")


def run(*cmd):
    return subprocess.run(list(map(str, cmd)), capture_output=True, text=True)


def install(repo, *flags):
    p = run("bash", ROOT / "install.sh", *flags, repo)
    assert p.returncode == 0, p.stderr
    return p


def tree(repo):
    return sorted(str(p.relative_to(repo)) for p in Path(repo).rglob("*"))


class HostsParity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=os.environ.get("TMPDIR") or None))
        self.repo, self.home = self.tmp / "r", self.tmp / "h"
        self.repo.mkdir(); self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_new_roots_get_skill_with_matching_name_and_default_has_none(self):
        install(self.repo)
        self.assertFalse(any((self.repo / h).exists() for h, _ in NEW))
        self.assertTrue((self.repo / ".agents/skills/deep-code-review/SKILL.md").is_file())  # Devin CLI, Kimi, Pi, Antigravity
        install(self.repo, "--with-extra-hosts")
        for h, _ in NEW:
            md = (self.repo / h / "skills/deep-code-review/SKILL.md").read_text()
            self.assertRegex(md, r"(?m)^name: deep-code-review$", h)

    def test_doctor_sees_drift(self):
        with mock.patch.dict(os.environ, {"DCR_COPY_HOSTS": "1"}):  # real copies: symlinked hosts cannot drift
            install(self.repo, "--with-extra-hosts")
        self.assertEqual(perun_doctor.main([str(self.repo), "--home", str(self.home)]), 0)
        for h, _ in NEW:
            f = self.repo / h / "skills/deep-code-review/SKILL.md"
            f.write_text(f.read_text() + "\nedit\n")
        rows = {c: d for _, c, d in perun_doctor.check(self.repo, self.home)}
        for h, _ in NEW:
            self.assertIn(f"{h}/skills/deep-code-review/SKILL.md", rows["drifted copies"])

    def test_uninstall_leaves_nothing(self):
        before = tree(self.repo)
        install(self.repo, "--with-extra-hosts")
        p = run(sys.executable, ROOT / "scripts/perun_uninstall.py", self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(tree(self.repo), before)

    def test_install_prints_safety_line_with_doc_link(self):
        out = install(self.repo, "--with-extra-hosts").stderr
        for _, name in NEW:
            self.assertRegex(out, rf"(?m)^safety: {name}: .* https://", name)

    def test_safety_urls_and_skill_pages_recorded_in_index(self):
        rows = [l.split("\t") for l in (ROOT / ".claude/skills/agentic-delivery/templates/host-safety.tsv").read_text().splitlines() if l and not l.startswith("#")]
        for h, name in NEW:
            row = next(r for r in rows if r[0] == h)
            self.assertEqual(row[1], name)
            self.assertIn(row[4].rstrip("/"), SEC, h)  # safety page fetched this date
        for url in ("https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/", "https://docs.x.ai/build/features/skills-plugins-marketplaces"):
            self.assertIn(url, SEC)
        self.assertIn(".qwen/skills", SEC)
        self.assertIn(".grok/skills", SEC)

    def test_rival_list_recorded_and_h10_counts_honest(self):
        for name in RIVAL:
            self.assertIn(name, SEC, name)
        h10 = (ROOT / "docs/perun-vs-rivals.md").read_text()
        row = next(l for l in h10.splitlines() if l.startswith("| Native install hosts |"))
        self.assertRegex(row, r"\| 19: ")
        self.assertIn("16 names in its README", row)
        self.assertIn("1 smoke-tested (Codex)", row)
        self.assertNotRegex(h10, r"15 to 16|Perun's 11\b|How the 11 native")
        self.assertIn("Skipped: Muse", h10)  # no vendor docs found, so not claimed
        self.assertTrue(re.search(r"The other 17 are docs-validated only", h10))
        cell = row.split("|")[2]
        names = cell.split("19: ", 1)[1].replace(", plus (via `install.sh --with-extra-hosts` or the default roots) ", ", ").split(", ")
        self.assertEqual(len(names), 19)  # the stated count equals the names listed

if __name__ == "__main__":
    unittest.main()
