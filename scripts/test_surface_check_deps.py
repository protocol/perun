#!/usr/bin/env python3
"""surface_check.py `deps`: a dependency diff must resolve its packages inside the worktree, not a parent checkout's node_modules.

Hermetic: throwaway git repos in a temp dir; the "parent checkout" is the directory holding the worktree, so Node's walk up the
tree would find its stale node_modules. Nothing is installed and no network is used.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts/surface_check.py"
sys.path.insert(0, str(SC.parent))
import surface_check  # noqa: E402

# One hermetic env for every git and python child: no inherited GIT_* (a hook's GIT_DIR/GIT_INDEX_FILE would aim git at the wrong repo),
# no system or global git config.
ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, env=ENV)


def pkg_json(path, **fields):
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps(fields))


class Deps(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.parent = Path(self.t.name).resolve()
        self.wt = self.parent / "wt"
        pkg_json(self.wt, name="app", dependencies={"zod": "^3.0.0"})
        (self.wt / "README.md").write_text("x")
        git(self.wt, "init", "-q", "-b", "main")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "base")
        git(self.wt, "checkout", "-qb", "lane")
        pkg_json(self.parent / "node_modules" / "zod", name="zod", version="3.0.0")  # the leak: stale parent dep

    def tearDown(self):
        self.t.cleanup()

    def bump(self, spec="^4.0.0"):
        pkg_json(self.wt, name="app", dependencies={"zod": spec})
        git(self.wt, "commit", "-qam", "bump")

    def own(self, version):
        pkg_json(self.wt / "node_modules" / "zod", name="zod", version=version)

    def run_deps(self, repo=None):
        r = subprocess.run([sys.executable, str(SC), "deps", "--repo", str(repo or self.wt), "--base", "main"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, env=ENV)
        return r.returncode, r.stdout

    def lane(self, **fields):
        """Rewrite the worktree's package.json with `fields`, commit it, and give the worktree its own node_modules."""
        pkg_json(self.wt, name="app", **fields)
        git(self.wt, "commit", "-qam", "lane")
        (self.wt / "node_modules").mkdir(exist_ok=True)

    def own_pkg(self, name, version):
        pkg_json(self.wt / "node_modules" / name, name=name, version=version)

    def test_no_node_modules_in_worktree_fails_with_npm_ci(self):
        self.bump()
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("no node_modules of its own", out)
        self.assertIn(f"cd {self.wt} && npm ci", out)
        self.assertFalse((self.wt / "node_modules").exists(), "detection only: it must never install")

    def test_package_missing_from_own_node_modules_resolves_parent_and_fails(self):
        self.bump()
        (self.wt / "node_modules").mkdir()
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("zod ^4.0.0 resolves OUTSIDE the worktree", out)
        self.assertIn("(3.0.0)", out)

    def test_package_installed_nowhere_fails(self):
        self.bump()
        (self.wt / "node_modules").mkdir()
        (self.parent / "node_modules" / "zod" / "package.json").unlink()
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("zod ^4.0.0 not installed", out)

    def test_symlinked_node_modules_pointing_outside_fails(self):
        self.bump()
        (self.wt / "node_modules").symlink_to(self.parent / "node_modules")
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("OUTSIDE the worktree", out)

    def test_worktree_local_old_version_fails(self):
        self.bump()
        self.own("3.0.0")
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("wants ^4.0.0, installed 3.0.0", out)

    def test_worktree_local_bumped_version_passes(self):
        self.bump()
        self.own("4.1.2")
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("1 changed spec(s) resolve inside the worktree", out)

    def test_uncommitted_bump_is_in_the_diff(self):
        pkg_json(self.wt, name="app", dependencies={"zod": "^4.0.0"})
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)

    def test_no_dependency_change_skips(self):
        (self.wt / "README.md").write_text("y")
        git(self.wt, "commit", "-qam", "docs")
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("skip:", out)

    def test_lockfile_only_needs_own_node_modules_and_says_no_version_compared(self):
        (self.wt / "package-lock.json").write_text("{}")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "lock")
        self.assertEqual(self.run_deps()[0], 1)
        (self.wt / "node_modules").mkdir()
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("no version was compared", out)

    def test_bad_base_is_could_not_check(self):
        r = subprocess.run([sys.executable, str(SC), "deps", "--repo", str(self.wt), "--base", "nope"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, env=ENV)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_prerelease_install_does_not_satisfy_plain_caret(self):
        self.bump()
        self.own("4.0.0-rc.1")
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("wants ^4.0.0, installed 4.0.0-rc.1", out)

    def test_partial_specs_are_compared(self):
        for spec, ver, rc in [("^4", "4.2.0", 0), ("^4", "3.9.0", 1), ("~4.1", "4.1.9", 0), ("~4.1", "4.2.0", 1),
                              ("4.x", "4.7.0", 0), ("4.x", "5.0.0", 1), ("4", "4.0.1", 0), ("4.1", "4.2.0", 1)]:
            with self.subTest(spec=spec, ver=ver):
                self.tearDown()
                self.setUp()
                self.bump(spec)
                self.own(ver)
                out = self.run_deps()
                self.assertEqual(out[0], rc, out)
                self.assertNotIn("unjudged (range/tag)", out[1])

    def test_unjudged_specs_are_reported_not_passed_as_compared(self):
        self.own("3.0.0")
        specs = {"a": ">=1", "b": "*", "c": "^3 || ^4", "d": "latest", "e": "npm:zod@^4", "f": "workspace:*", "g": "^3.0.0"}
        for n in specs:
            self.own_pkg(n, "3.5.0")
        (self.wt / "node_modules").mkdir(exist_ok=True)
        self.lane(dependencies=specs)
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("1 changed spec(s) resolve inside the worktree at a version satisfying the spec", out)
        self.assertIn("6 unjudged (range/tag), version not compared", out)

    def test_untracked_and_nonrelative_paths_with_unicode_dir(self):
        git(self.wt, "config", "diff.relative", "true")  # repo config that makes `git diff` paths cwd-relative
        sub = self.wt / "ünï dir"
        pkg_json(sub, name="sub", dependencies={"zod": "^3.0.0"})
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "sub")
        pkg_json(sub, name="sub", dependencies={"zod": "^4.0.0"})
        git(self.wt, "commit", "-qam", "bump")
        (self.wt / "node_modules").mkdir()
        rc, out = self.run_deps(repo=sub)  # --repo is a subdirectory of the worktree
        self.assertEqual(rc, 1, out)
        self.assertIn("zod ^4.0.0 resolves OUTSIDE the worktree", out)

    def test_untracked_package_json_is_in_the_diff(self):
        pkg_json(self.wt / "packages" / "new", name="new", dependencies={"zod": "^4.0.0"})
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("packages/new/package.json", out)

    def test_peer_dependency_is_checked_and_a_missing_one_is_unjudged(self):
        self.lane(peerDependencies={"react": "^19.0.0"})
        self.own_pkg("react", "18.0.0")
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("react wants ^19.0.0, installed 18.0.0", out)
        self.own_pkg("react", "19.1.0")
        self.assertEqual(self.run_deps()[0], 0)
        (self.wt / "node_modules" / "react" / "package.json").unlink()
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("1 unjudged (range/tag), version not compared", out)

    def test_overrides_resolutions_and_pnpm_overrides_are_checked_by_name(self):
        self.own("3.0.0")
        for fields in ({"overrides": {"zod": "^4.0.0"}}, {"resolutions": {"zod@<4": "^4.0.0"}},
                       {"pnpm": {"overrides": {"zod": "^4.0.0"}}}):
            with self.subTest(fields=fields):
                self.lane(**fields)
                rc, out = self.run_deps()
                self.assertEqual(rc, 1, out)
                self.assertIn("zod wants ^4.0.0, installed 3.0.0", out)
        self.lane(overrides={"zod": {".": "^4.0.0", "x": "1"}, "**/zod": "^4", "$zod": "x"})
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)
        self.assertIn("3 unjudged (range/tag), version not compared", out)

    def test_bun_lockfiles_need_node_modules_and_print_the_bun_install(self):
        for lock in ("bun.lock", "bun.lockb"):
            with self.subTest(lock=lock):
                (self.wt / lock).write_text("x")
                git(self.wt, "add", "-A")
                git(self.wt, "commit", "-qm", lock)
                rc, out = self.run_deps()
                self.assertEqual(rc, 1, out)
                self.assertIn("bun install --frozen-lockfile", out)

    def test_node_modules_is_required_at_each_touched_package_not_only_the_root(self):
        for d in ("a", "b"):
            pkg_json(self.wt / "packages" / d, name=d, dependencies={"zod": "^3.0.0"})
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "ws")
        for d in ("a", "b"):
            pkg_json(self.wt / "packages" / d, name=d, dependencies={"zod": "^4.0.0"})
        git(self.wt, "commit", "-qam", "bump")
        (self.wt / "packages" / "a" / "node_modules").mkdir()
        pkg_json(self.wt / "packages" / "a" / "node_modules" / "zod", name="zod", version="4.0.0")
        rc, out = self.run_deps()
        self.assertEqual(rc, 1, out)
        self.assertIn("packages/b/package.json changed but", out)
        self.assertNotIn("packages/a/package.json changed but", out)
        (self.wt / "node_modules").mkdir()  # a root node_modules covers every package below it
        pkg_json(self.wt / "node_modules" / "zod", name="zod", version="4.0.0")
        pkg_json(self.wt / "packages" / "b" / "node_modules" / "zod", name="zod", version="4.0.0")
        self.assertEqual(self.run_deps()[0], 0)

    def test_nested_node_modules_alone_satisfies_its_own_package(self):
        pkg_json(self.wt / "packages" / "a", name="a", dependencies={"zod": "^4.0.0"})
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "ws")
        pkg_json(self.wt / "packages" / "a" / "node_modules" / "zod", name="zod", version="4.0.0")  # no root node_modules
        rc, out = self.run_deps()
        self.assertEqual(rc, 0, out)

    def test_wrong_json_shapes_exit_2_not_a_traceback(self):
        for raw in ('[]', '"x"', '{"dependencies": []}', '{"dependencies": {"zod": 4}}', '{"overrides": 3}',
                    '{"pnpm": []}', '{"dependencies": {"zod": {"a": 1}}}'):
            with self.subTest(raw=raw):
                (self.wt / "package.json").write_text(raw)
                git(self.wt, "commit", "-qam", "bad")
                (self.wt / "node_modules").mkdir(exist_ok=True)
                r = subprocess.run([sys.executable, str(SC), "deps", "--repo", str(self.wt), "--base", "main"],
                                   capture_output=True, text=True, stdin=subprocess.DEVNULL, env=ENV)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def test_invalid_package_names_fail(self):
        for name in ("../evil", "/abs", "@s/../x", "a/b", ".hidden", ""):
            with self.subTest(name=name):
                self.lane(dependencies={name: "^1.0.0"})
                rc, out = self.run_deps()
                self.assertEqual(rc, 1, out)
                self.assertIn("is not a valid npm package name", out)


class Satisfies(unittest.TestCase):
    def test_table(self):
        for ver, spec, want in [("4.0.0", "4.0.0", True), ("4.0.1", "4.0.0", False), ("4.2.0", "^4.0.0", True),
                                ("3.9.9", "^4.0.0", False), ("5.0.0", "^4.0.0", False), ("0.2.9", "^0.2.3", True),
                                ("0.3.0", "^0.2.3", False), ("0.0.4", "^0.0.3", False), ("1.2.9", "~1.2.3", True),
                                ("1.3.0", "~1.2.3", False), ("1.2.2", "~1.2.3", False), ("2.0.0", ">=1", None),
                                ("2.0.0", "latest", None), ("1.0.0", "file:../x", None),
                                ("4.0.0-rc.1", "^4.0.0", False), ("4.1.0-rc.1", "^4.0.0-rc.1", False),
                                ("4.0.0-rc.2", "^4.0.0-rc.1", True), ("4.0.0-rc.1", "^4.0.0-rc.2", False),
                                ("4.0.0", "^4.0.0-rc.1", True), ("4.0.0-rc.1", "4.0.0-rc.1", True), ("4.0.0", "4.0.0-rc.1", False),
                                ("4.0.0-rc.10", "^4.0.0-rc.9", True), ("4.0.0+build", "4.0.0", True),
                                ("4.5.0", "^4", True), ("5.0.0", "^4", False), ("4.1.5", "~4.1", True), ("4.2.0", "~4.1", False),
                                ("4.9.0", "~4", True), ("4.9.0", "4.x", True), ("4.9.0", "4.x.x", True), ("4.9.0", "4.*", True),
                                ("4.1.9", "4.1", True), ("4.2.0", "4.1.x", False), ("0.0.9", "^0.0", True), ("0.1.0", "^0.0", False),
                                ("0.5.0", "^0", True), ("1.0.0", "^0", False), ("1.0.0", "*", None), ("1.0.0", "x", None),
                                ("1.0.0", "^1 || ^2", None), ("1.0.0", "npm:foo@1", None), ("1.0.0", "workspace:*", None),
                                ("1.0.0", "4.x.3", None), ("1.0.0", "4.x-rc", None), ("weird", "^1", None)]:
            self.assertIs(surface_check._satisfies(ver, spec), want, (ver, spec))


if __name__ == "__main__":
    unittest.main()
