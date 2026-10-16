"""Tests for perun_policy.py set/skip-ci, install.sh --policy, and the preamble/policy agreement."""
import json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PP = ROOT / ".claude/skills/agentic-delivery/scripts/perun_policy.py"
PRE = (ROOT / ".claude/skills/agentic-delivery/templates/lane-preamble.md").read_text()
ENV = {k: v for k, v in os.environ.items() if k != "PERUN_POLICY"}


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=ENV)


class PolicyUx(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def pp(self, *a):
        return run([sys.executable, str(PP), *a], self.d)

    def test_set_creates_validates_and_prints(self):
        r = self.pp("set", "github_actions", "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["github_actions"], "off")
        self.assertEqual(json.loads((Path(self.d) / ".perun/policy.json").read_text()), {"github_actions": "off"})
        self.assertEqual(self.pp("get", "github_actions").stdout.strip(), "off")
        self.assertEqual(self.pp("skip-ci").stdout.strip(), "[skip ci]")
        self.assertEqual(self.pp("set", "tokens", "500").returncode, 0)
        self.assertEqual(self.pp("get", "tokens").stdout.strip(), "500")

    def test_set_rejects_bad_input_and_keeps_file(self):
        self.pp("set", "local_cpu", "maximize")
        for a in (("tokens", "lots"), ("nope", "1"), ("share_learnings", "yes")):
            self.assertEqual(self.pp("set", *a).returncode, 2, a)
        self.assertEqual(self.pp("get", "local_cpu").stdout.strip(), "maximize")
        self.assertEqual(self.pp("skip-ci").stdout.strip(), "")

    def test_preamble_agrees_with_tokens_and_ci_policy(self):
        self.assertEqual(self.pp("get", "tokens").stdout.strip(), "efficient")
        self.assertIn("`efficient` (default) means: use the cheapest model tier that fits, no duplicate review passes, "
                      "fields-only hand-backs (logged by `handback_cap.py`), and at most 2 parallel lanes (enforced:", PRE)
        self.assertIn("perun_policy.py get tokens", PRE)
        self.assertRegex(PRE, r"`off`, end every commit message you push with `\[skip ci\]`")

    def test_tokens_dim_caps_lanes(self):
        for tok, want in (("efficient", "2"), ("maximize", None), ("off", "1"), ("3", "3")):
            self.pp("set", "local_cpu", "maximize")
            self.pp("set", "tokens", tok)
            for cmd in ("lanes", "heavy-slots"):
                got = int(self.pp(cmd).stdout)
                if want:
                    self.assertLessEqual(got, int(want), (tok, cmd))
                else:
                    self.assertGreaterEqual(got, 1)
        self.pp("set", "tokens", "maximize")
        import importlib.util
        spec = importlib.util.spec_from_file_location("pp", PP)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual([m.lanes("maximize", 16, 0, t) for t in ("efficient", "maximize", "off", 3)], [2, 16, 1, 3])
        self.assertEqual([m.heavy_slots(16, 0, t) for t in ("efficient", "maximize", "off", 5)], [2, 16, 1, 5])

    def test_set_repairs_bad_key_and_rejects_nonascii_digits(self):
        (Path(self.d) / ".perun").mkdir()
        (Path(self.d) / ".perun/policy.json").write_text('{"tokens": "lots"}')
        self.assertEqual(self.pp("get", "tokens").returncode, 2)
        self.assertEqual(self.pp("set", "tokens", "5").returncode, 0)
        self.assertEqual(self.pp("get", "tokens").stdout.strip(), "5")
        r = self.pp("set", "tokens", "\u0663\u00b2")
        self.assertEqual((r.returncode, "Traceback" in r.stderr), (2, False))

    def test_skip_ci_honors_env(self):
        self.assertEqual(run([sys.executable, str(PP), "skip-ci"], self.d).stdout.strip(), "")
        r = subprocess.run([sys.executable, str(PP), "skip-ci"], cwd=self.d, capture_output=True, text=True,
                           env={**ENV, "PERUN_GITHUB_ACTIONS": "off"})
        self.assertEqual(r.stdout.strip(), "[skip ci]")

    def test_install_policy_pinned_to_target_and_malformed_pairs(self):
        outer = tempfile.mkdtemp()
        (Path(outer) / ".perun").mkdir()
        (Path(outer) / ".perun/policy.json").write_text('{"network": "off"}')
        t = Path(outer) / "proj"
        t.mkdir()
        r = subprocess.run(["bash", str(ROOT / "install.sh"), "--policy", "tokens=7", str(t)], cwd=ROOT,
                           capture_output=True, text=True, env={**ENV, "PERUN_POLICY": str(Path(outer) / "x.json")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((t / ".perun/policy.json").read_text()), {"tokens": 7})
        self.assertEqual(json.loads((Path(outer) / ".perun/policy.json").read_text()), {"network": "off"})
        self.assertFalse((Path(outer) / "x.json").exists())
        for bad in ("tokens", "tokens=", "tokens=1,tokens=2", "=1", "nope=1"):
            t2 = tempfile.mkdtemp()
            b = run(["bash", str(ROOT / "install.sh"), "--policy", bad, t2], ROOT)
            self.assertEqual(b.returncode, 2, bad)
        self.assertFalse((Path(t2) / ".perun").exists())

    def test_self_target_refusal_leaves_no_policy(self):
        r = run(["bash", str(ROOT / "install.sh"), "--policy", "tokens=7", str(ROOT)], ROOT)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((ROOT / ".perun/policy.json").exists())

    def test_install_policy_flag(self):
        t = tempfile.mkdtemp()
        r = run(["bash", str(ROOT / "install.sh"), "--policy", "local_cpu=maximize,github_actions=off,share_learnings=auto", t], ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((Path(t) / ".perun/policy.json").read_text()),
                         {"local_cpu": "maximize", "github_actions": "off", "share_learnings": "auto"})
        self.assertRegex(r.stdout, r'Policy: \{.*"github_actions": "off"')
        bad = run(["bash", str(ROOT / "install.sh"), "--policy", "tokens=lots", tempfile.mkdtemp()], ROOT)
        self.assertEqual(bad.returncode, 2)

    def test_perun_run_auto_shares_after_policy_check(self):
        s = (ROOT / "commands/perun-run.md").read_text()
        self.assertRegex(s, r"get share_learnings` prints `auto`.*share_learning\.py.*--send")


if __name__ == "__main__":
    unittest.main()
