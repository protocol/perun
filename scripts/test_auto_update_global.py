#!/usr/bin/env python3
"""Hook mode also targets a user-global install (~/.claude/.perun-install.json). Offline, temp HOME."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_auto_update as base  # noqa: E402

au = base.au


class GlobalInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.remote = base.fake_remote(self.tmp)
        self.proj = base.fake_installed(self.tmp, self.remote)
        env = mock.patch.dict(os.environ, {"HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.proj),
                                           "XDG_CACHE_HOME": str(self.tmp / "cache")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PERUN_POLICY", None)

    def global_install(self):  # a non-git home with a marker and no managed skill files
        m = json.loads((self.proj / ".claude/.perun-install.json").read_text())
        (self.home / ".claude/.perun-install.json").write_text(json.dumps({**m, "skills": {}}))

    @mock.patch.object(au.subprocess, "Popen")
    def test_hook_targets_project_and_global_home_with_own_stamps(self, popen):
        self.global_install()
        au.main([])
        self.assertEqual([c.args[0][-1] for c in popen.call_args_list], [str(self.proj.resolve()), str(self.home.resolve())])
        popen.reset_mock()
        au.main([])  # both stamps fresh: throttled
        popen.assert_not_called()

    @mock.patch.object(au.subprocess, "Popen")
    def test_no_global_marker_means_project_only_and_home_as_project_spawns_once(self, popen):
        au.main([])
        self.assertEqual(popen.call_count, 1)
        self.global_install()
        popen.reset_mock()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.home)}):
            au.main([])
        self.assertEqual(popen.call_count, 1)  # home == project target: no double spawn

    @mock.patch.object(au.subprocess, "Popen")
    def test_unresolvable_home_falls_back_to_project_only(self, popen):
        self.global_install()
        with mock.patch.object(au.Path, "home", side_effect=RuntimeError("no home")):
            self.assertEqual(au.main([]), 0)
        self.assertEqual([c.args[0][-1] for c in popen.call_args_list], [str(self.proj.resolve())])

    @mock.patch.object(au.subprocess, "Popen")
    def test_project_opt_out_skips_home_too(self, popen):
        self.global_install()
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun/policy.json").write_text('{"auto_update": "off"}')
        au.main([])
        popen.assert_not_called()

    def test_pr_step_never_runs_for_home(self):
        with mock.patch.object(au, "enabled", return_value=True), mock.patch.object(au, "update_pr") as pr:
            au.pr_step(self.home.resolve())
            pr.assert_not_called()
            pr.return_value = "ok"
            au.pr_step(self.proj.resolve())
            pr.assert_called_once()

    def test_non_git_home_updates(self):
        self.global_install()
        self.assertEqual(au.run(self.home.resolve()), 0)
        self.assertEqual((self.home / ".claude/ran").read_text(), "1 v1.10.0\n")
        self.assertIn("updated 1.2.0 -> v1.10.0", (au.cache() / "auto-update.log").read_text())


if __name__ == "__main__":
    unittest.main()
