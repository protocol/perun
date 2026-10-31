#!/usr/bin/env python3
"""Update hygiene: re-running install.sh after a version bump adds no skill backup and no .new file when you edited nothing,
and vendor_drift.py reads an install-placeholder stub as the docs/ file install.sh copies over it.

Principle: install never overwrites anything you may have edited and never deletes a file it did not create in this run. The
one thing it drops is the fresh backup it just moved aside, and only when that is provably a copy it shipped. An edited skill
keeps its backup, an edited or pre-Perun slash command is never touched (a differing .new is written), and every .new survives.

Fixtures: a tiny fictional release source (the real install.sh, scripts/ and commands/, one skill with two placeholder
stubs and their docs/ originals, four gate templates) plus an empty target repo, all under $TMPDIR. A "version bump"
rewrites that source. Every process runs with a scratch HOME and no network probe."""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perun_marker  # noqa: E402

DRIFT = ROOT / ".claude/skills/agentic-delivery/scripts/vendor_drift.py"
MARKER = ROOT / "scripts/perun_marker.py"
REVIEW = ".claude/commands/review.md"


def run(*cmd, env=None):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=os.environ.get("TMPDIR") or None))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class Release(Tmp):
    """A fictional release source and an empty target repo; `release(n)` makes the source version n."""

    def setUp(self):
        super().setUp()
        self.src, self.repo, self.home = self.tmp / "src", self.tmp / "repo", self.tmp / "home"
        self.skill = self.src / ".claude/skills/deep-code-review"
        for d in (self.skill / "references", self.skill / "templates", self.src / "docs", self.repo, self.home):
            d.mkdir(parents=True)
        shutil.copy(ROOT / "install.sh", self.src)
        (self.src / "scripts").symlink_to(ROOT / "scripts")
        shutil.copytree(ROOT / "commands", self.src / "commands")
        self.review = (self.src / "commands/review.md").read_text()
        for n in ("dcr-gates.yml", "dcr-gates.sh", "pre-push-verify.sh", "integrator-gate.sh"):
            (self.skill / "templates" / n).write_text(f"# fictional {n}\n")
        for n in ("standards-index", "example-review-report"):
            (self.skill / "references" / f"{n}.md").write_text(f"# {n} (install placeholder)\n\nstub\n")
            (self.src / "docs" / f"{n}.md").write_text(f"# {n}\n\nfull text\n")
        self.env = {**os.environ, "HOME": str(self.home), "XDG_CACHE_HOME": str(self.home / ".cache"), "DCR_NO_PROBE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        self.release(1)

    def release(self, n):
        (self.skill / "SKILL.md").write_text(f"---\nname: deep-code-review\ndescription: fictional\n---\nbody v{n}\n")
        (self.skill / "VERSION").write_text(f"{n}.0.0\n")
        (self.src / "commands/review.md").write_text(self.review + f"\nrelease {n} note\n")

    def install(self, *flags):
        p = run("bash", self.src / "install.sh", *flags, self.repo, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def backups(self):
        d = self.repo / ".claude/skill-backups"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def news(self, under=".claude/commands"):
        base = self.repo / under
        return sorted(str(p.relative_to(base)) for p in base.rglob("*.new*"))

    def marker(self):
        return json.loads((self.repo / ".claude/.perun-install.json").read_text())


class VendorDriftStubs(Release):
    """A: a stub in the canonical source is compared as <src root>/docs/<same name>, what install.sh copies over it."""

    def drift(self):
        p = run(sys.executable, "-I", DRIFT, self.repo, "--src", self.src / ".claude/skills")
        return p.returncode, p.stdout.strip()

    def test_installed_docs_copy_is_not_drift_but_an_edit_is(self):
        self.install()
        ref = self.repo / ".claude/skills/deep-code-review/references/standards-index.md"
        self.assertEqual(ref.read_text(), "# standards-index\n\nfull text\n")  # install put the docs file over the stub
        self.assertEqual(self.drift(), (0, "no drift"))
        ref.write_text(ref.read_text() + "my edit\n")
        self.assertEqual(self.drift(), (1, "DRIFT deep-code-review/references/standards-index.md"))  # the swap must not hide an edit

    def test_stub_left_in_the_copy_is_drift(self):
        self.install()
        ref = self.repo / ".claude/skills/deep-code-review/references/example-review-report.md"
        ref.write_text("# example-review-report (install placeholder)\n\nstub\n")  # the overlay never happened
        self.assertEqual(self.drift(), (1, "DRIFT deep-code-review/references/example-review-report.md"))

    def test_missing_docs_file_fails_closed_against_the_stub(self):
        self.install()
        (self.src / "docs/standards-index.md").unlink()
        self.assertEqual(self.drift(), (1, "DRIFT deep-code-review/references/standards-index.md"))  # a full copy is not the stub
        (self.repo / ".claude/skills/deep-code-review/references/standards-index.md").write_text("# standards-index (install placeholder)\n\nstub\n")
        self.assertEqual(self.drift(), (0, "no drift"))  # only the stub itself matches the stub

    def test_only_a_first_line_marks_a_stub(self):
        note = self.skill / "references/notes.md"
        note.write_text("# notes\n\nA stub says (install placeholder) on its first line.\n")  # mentions the phrase, but is not a stub
        (self.src / "docs/notes.md").write_text("# a different file that happens to share the name\n")
        self.install()
        self.assertEqual((self.repo / ".claude/skills/deep-code-review/references/notes.md").read_text(), note.read_text())
        self.assertEqual(self.drift(), (0, "no drift"))  # compared as itself, not as docs/notes.md

    def test_real_install_has_no_drift_against_the_real_source(self):
        p = run("bash", ROOT / "install.sh", "--minimal", self.repo, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        d = run(sys.executable, "-I", DRIFT, self.repo, "--src", ROOT / ".claude/skills")
        self.assertEqual((d.returncode, d.stdout.strip()), (0, "no drift"), d.stderr)


class UpdateBackups(Release):
    """B: a backup of an earlier release nobody edited is not kept; every other backup is."""

    def test_version_bumps_add_no_backup(self):
        self.install()
        for n in (2, 3):
            self.release(n)
            self.install()
        self.assertEqual(self.backups(), [])
        self.assertIn("body v3", (self.repo / ".claude/skills/deep-code-review/SKILL.md").read_text())

    def test_version_bumps_add_no_backup_on_copied_hosts(self):
        self.env["DCR_COPY_HOSTS"] = "1"  # a real copy in every host root, not a symlink to the .claude one
        self.install()
        for n in (2, 3):
            self.release(n)
            self.install()
        self.assertGreater(len([p for p in self.repo.glob(".*/skills/deep-code-review") if not p.is_symlink()]), 1)
        self.assertEqual(list(self.repo.glob(".*/skill-backups/*")), [])

    def test_version_bumps_with_a_relative_target_add_nothing(self):  # `install.sh .`: the marker keys must still match the paths install.sh builds
        def install_here():
            p = subprocess.run(["bash", str(self.src / "install.sh"), "."], cwd=self.repo, capture_output=True, text=True, env=self.env)
            self.assertEqual(p.returncode, 0, p.stderr)
        install_here()
        for n in (2, 3):
            self.release(n)
            install_here()
        self.assertEqual((self.backups(), self.news()), ([], []))
        self.assertTrue((self.repo / REVIEW).read_text().endswith("release 3 note\n"))

    def test_edited_skill_keeps_its_backup_and_later_bumps_add_none(self):
        self.install()
        skill = self.repo / ".claude/skills/deep-code-review"
        (skill / "SKILL.md").write_text("my edit\n")
        self.release(2)
        self.install()
        (skill / "notes.md").write_text("my notes\n")  # an added file is an edit too
        self.release(3)
        self.install()
        for n in (4, 5):  # unedited since the last install: nothing more is kept
            self.release(n)
            self.install()
        kept = self.repo / ".claude/skill-backups"
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual([p.read_text() for p in kept.glob("*/notes.md")], ["my notes\n"])
        self.assertEqual([p.read_text() for p in kept.glob("*/SKILL.md")].count("my edit\n"), 1)

    def test_pre_perun_copy_is_kept(self):
        skill = self.repo / ".claude/skills/deep-code-review"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("mine, from before Perun\n")
        self.install()
        kept = self.backups()
        self.assertEqual(len(kept), 1)
        self.release(2)
        self.install()  # the first install's own copy is dropped, the pre-Perun one is not
        self.assertEqual(self.backups(), kept)
        self.assertEqual((self.repo / ".claude/skill-backups" / kept[0] / "SKILL.md").read_text(), "mine, from before Perun\n")


class DedupeAgainstPrevious(Tmp):
    """perun_marker.drop_identical_backup with `prev`: the marker's hashes of what the last install wrote."""

    def setUp(self):
        super().setUp()
        self.root, self.dest = self.tmp / "skill-backups", self.tmp / "dest"
        for d in (self.root, self.dest):
            d.mkdir()
        (self.dest / "SKILL.md").write_text("this release\n")
        self.prev = {"SKILL.md": sha("last release\n")}

    def backup(self, name="demo-20260101-000000", text="last release\n"):
        d = self.root / name
        d.mkdir()
        (d / "SKILL.md").write_text(text)
        return d

    def drop(self, new, prev):
        return perun_marker.drop_identical_backup(self.root, new, self.dest, prev)

    def test_unedited_copy_of_the_last_install_is_dropped(self):
        new = self.backup()
        self.assertIn("previous install", self.drop(new, self.prev))
        self.assertFalse(new.exists())

    def test_pycache_is_ignored_like_hash_dir(self):
        new = self.backup()
        (new / "__pycache__").mkdir()
        (new / "__pycache__/x.cpython-311.pyc").write_bytes(b"\0")
        self.assertIn("previous install", self.drop(new, self.prev))
        self.assertFalse(new.exists())

    def test_anything_else_is_kept(self):
        extra = self.backup("extra-20260101-000000")
        (extra / "notes.md").write_text("mine\n")
        edited = self.backup("edited-20260101-000000", "my edit\n")
        plain = self.backup("plain-20260101-000000")
        cached = self.backup("cached-20260101-000000")
        (cached / "__pycache__").mkdir()
        (cached / "__pycache__/data.txt").write_text("mine\n")  # only bytecode is ignored under __pycache__
        for new, prev in ((extra, self.prev), (edited, self.prev), (cached, self.prev), (plain, None), (plain, {})):
            with self.subTest(new=new.name, prev=prev):
                self.assertIn("kept", self.drop(new, prev))
                self.assertTrue(new.is_dir())

    def test_an_entry_the_last_install_did_not_write_is_kept(self):
        empty = self.backup("empty-20260101-000000")
        (empty / "mine").mkdir()  # no file inside, so hash_dir cannot see it
        nested = self.backup("nested-20260101-000000")
        (nested / "a/b").mkdir(parents=True)
        fifo = self.backup("fifo-20260101-000000")
        os.mkfifo(fifo / "pipe")
        for new in (empty, nested, fifo):
            with self.subTest(new=new.name):
                self.assertIn("kept", self.drop(new, self.prev))
                self.assertTrue(new.is_dir())

    def test_a_symlink_inside_is_never_followed_or_deleted(self):
        user = self.tmp / "user.txt"
        user.write_text("user data\n")
        new = self.backup()
        (new / "link").symlink_to(user)
        prev = {**self.prev, "link": sha("user data\n")}  # hash_dir follows the link, so only the symlink gate keeps this backup
        self.assertIn("kept", self.drop(new, prev))
        self.assertTrue((new / "link").is_symlink())
        self.assertEqual(user.read_text(), "user data\n")

    def test_cli_reads_the_marker_entry_for_the_dir(self):
        key = ".claude/skills/demo"
        marker = self.tmp / ".claude/.perun-install.json"
        marker.parent.mkdir()
        cases = [(json.dumps({"skills": {key: self.prev}}), True), ("{not json", False), (json.dumps({"skills": {}}), False), (None, False)]
        for i, (text, dropped) in enumerate(cases):
            with self.subTest(marker=text):
                marker.unlink(missing_ok=True)
                if text is not None:
                    marker.write_text(text)
                new = self.backup(f"demo-2026010{i}-000000")
                p = run(sys.executable, "-I", MARKER, "dedupe", self.root, new, self.dest, self.tmp, key)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(new.exists(), not dropped)


class RefreshUnedited(Tmp):
    """perun_marker.py refresh: overwrite a file only when the marker says install wrote it and nobody edited it."""

    def setUp(self):
        super().setUp()
        self.repo, self.rel, self.shipped = self.tmp / "repo", ".claude/commands/demo.md", self.tmp / "shipped.md"
        self.dest = self.repo / self.rel
        self.dest.parent.mkdir(parents=True)
        self.shipped.write_text("v2\n")
        self.marker = self.repo / ".claude/.perun-install.json"

    def refresh(self):
        return run(sys.executable, "-I", MARKER, "refresh", self.repo, self.rel, self.shipped).returncode

    def test_overwrites_an_unedited_file_and_leaves_every_new_sibling_alone(self):
        self.dest.write_text("v1\n")
        self.marker.write_text(json.dumps({"files": {self.rel: sha("v1\n")}}))
        (self.dest.parent / "demo.md.new").write_text("v2\n")  # identical to the shipped file, and still not install's to delete
        (self.dest.parent / "demo.md.new-1").write_text("mine\n")
        self.assertEqual(self.refresh(), 0)
        self.assertEqual(self.dest.read_text(), "v2\n")
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir()), ["demo.md", "demo.md.new", "demo.md.new-1"])
        self.assertEqual([(self.dest.parent / n).read_text() for n in ("demo.md.new", "demo.md.new-1")], ["v2\n", "mine\n"])

    def test_leaves_everything_else_alone(self):
        user = self.tmp / "user.md"
        user.write_text("v1\n")
        for what in ("edited", "unrecorded", "no marker", "corrupt marker", "symlink"):
            with self.subTest(what):
                self.dest.unlink(missing_ok=True)
                self.marker.unlink(missing_ok=True)
                if what == "symlink":
                    self.dest.symlink_to(user)  # the recorded sha matches the link target: only the symlink gate refuses
                else:
                    self.dest.write_text("my edit\n" if what == "edited" else "v1\n")
                files = {} if what == "unrecorded" else {self.rel: sha("v1\n")}
                if what != "no marker":
                    self.marker.write_text("{not json" if what == "corrupt marker" else json.dumps({"files": files}))
                self.assertEqual(self.refresh(), 1)
                self.assertEqual(self.dest.read_text(), "my edit\n" if what == "edited" else "v1\n")
                self.assertEqual(user.read_text(), "v1\n")


class UpdateCommands(Release):
    """C: a slash command install wrote and you left alone is refreshed in place; one you edited, or never from Perun, gets a .new."""

    def test_version_bumps_refresh_an_unedited_command_in_place(self):
        self.install()
        for n in (2, 3):
            self.release(n)
            self.install()
        cmd = self.repo / REVIEW
        self.assertTrue(cmd.read_text().endswith("release 3 note\n"))
        self.assertEqual(self.news(), [])
        self.assertEqual(self.marker()["files"][REVIEW], sha(cmd.read_text()))  # re-recorded, so uninstall still knows install wrote it
        p = run(sys.executable, ROOT / "scripts/perun_uninstall.py", self.repo, "--apply", env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(cmd.exists())

    def test_edited_command_gets_a_new_file_and_stays_untouched(self):
        self.install()
        cmd = self.repo / REVIEW
        cmd.write_text("my edit\n")
        self.release(2)
        self.install()
        self.assertEqual(cmd.read_text(), "my edit\n")
        self.assertEqual(self.news(), ["review.md.new"])
        self.assertTrue((cmd.parent / "review.md.new").read_text().endswith("release 2 note\n"))
        self.install()  # same release again: the .new already holds it
        self.assertEqual(self.news(), ["review.md.new"])
        self.release(3)
        self.install()  # a different release is a different file
        self.assertEqual(self.news(), ["review.md.new", "review.md.new-1"])
        self.assertEqual(cmd.read_text(), "my edit\n")

    def test_pre_perun_command_is_never_refreshed(self):
        cmd = self.repo / REVIEW
        cmd.parent.mkdir(parents=True)
        cmd.write_text("mine\n")
        self.install()
        self.install()  # no marker entry for it: kept, and the identical .new is not written twice
        self.assertEqual(self.news(), ["review.md.new"])
        self.release(2)
        self.install()
        self.assertEqual(self.news(), ["review.md.new", "review.md.new-1"])
        self.assertEqual(cmd.read_text(), "mine\n")

    def test_a_lookalike_name_does_not_stand_in_for_the_new_file(self):
        cmd = self.repo / REVIEW
        cmd.parent.mkdir(parents=True)
        cmd.write_text("mine\n")
        (cmd.parent / "review.md.new-1abc").write_text((self.src / "commands/review.md").read_text())  # the shipped bytes, but not a .new-N name
        self.install()
        self.install()
        self.assertEqual(self.news(), ["review.md.new", "review.md.new-1abc"])

    def test_refresh_deletes_no_new_file_and_adds_none(self):
        self.install()
        self.release(2)
        shipped = (self.src / "commands/review.md").read_text()
        cmds = self.repo / ".claude/commands"
        (cmds / "review.md.new").write_text(shipped)  # identical to what the refresh writes, and still not install's to delete
        (cmds / "review.md.new-1").write_text("my notes\n")
        (cmds / "review.md.new-notes").write_text(shipped)
        (cmds / "review.md.new-2").symlink_to(self.src / "commands/review.md")
        self.install()
        self.assertEqual((cmds / "review.md").read_text(), shipped)
        self.assertEqual(self.news(), ["review.md.new", "review.md.new-1", "review.md.new-2", "review.md.new-notes"])
        self.assertEqual([(cmds / n).read_text() for n in ("review.md.new", "review.md.new-1", "review.md.new-notes")], [shipped, "my notes\n", shipped])
        self.assertTrue((cmds / "review.md.new-2").is_symlink())

    def test_a_symlinked_new_file_does_not_stand_in_for_the_shipped_one(self):
        self.install()
        cmd = self.repo / REVIEW
        cmd.write_text("my edit\n")
        shipped = (self.src / "commands/review.md").read_text()
        mine = self.tmp / "mine.md"
        mine.write_text(shipped)  # the shipped bytes, in a file install does not own
        link = cmd.parent / "review.md.new"
        link.symlink_to(mine)
        self.install()
        self.assertEqual((os.readlink(link), mine.read_text(), cmd.read_text()), (str(mine), shipped, "my edit\n"))
        real = cmd.parent / "review.md.new-1"
        self.assertTrue(real.is_file() and not real.is_symlink())
        self.assertEqual(real.read_text(), shipped)
        self.install()
        self.assertEqual(self.news(), ["review.md.new", "review.md.new-1"])  # the regular copy now stands in

    def test_gate_outputs_add_no_new_file_on_rerun_and_an_edit_survives(self):
        self.install("--with-gates")
        self.install("--with-gates")
        self.assertEqual(self.news("."), [])
        gate = self.repo / "scripts/dcr-gates.sh"
        gate.write_text("my gate\n")
        self.install("--with-gates")
        self.install("--with-gates")
        self.assertEqual(gate.read_text(), "my gate\n")
        self.assertEqual(self.news("."), ["scripts/dcr-gates.sh.new"])


if __name__ == "__main__":
    unittest.main()
