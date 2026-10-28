#!/usr/bin/env python3
"""Pin tests: scrub_env.sh isolates a child from the real GitHub account and network, and run-ci-tests.sh routes through it.

A fake `gh` is run by ABSOLUTE path (a PATH stub would be bypassed that way) and records the env a real gh would use; the test
fails if a real-looking token, a stored config dir or a routable network could reach it. Also covers bg_admit.py and job_lease --admit.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import bg_admit  # noqa: E402

GOOD = "# disk-cap: 2G\n# disk-stop: stop below 5G free\ntrap 'rm -rf \"$d\"' EXIT\nif [ \"$(df -k . | wc -l)\" -lt 1 ]; then exit 1; fi\n"


class T(unittest.TestCase):
    def test_child_env_is_scrubbed_even_past_a_path_stub(self):
        with tempfile.TemporaryDirectory() as d:
            gh = Path(d) / "gh"  # stands in for the real binary reached by absolute path
            gh.write_text('#!/bin/sh\nenv\nls -A "$GH_CONFIG_DIR" | wc -l\n')
            gh.chmod(0o755)
            env = dict(os.environ, SSH_AUTH_SOCK="/agent", GH_TOKEN="ghp_realtoken", GITHUB_TOKEN="ghp_real", GH_CONFIG_DIR="/real/gh", HTTPS_PROXY="http://real:1",
                       GIT_DIR="/x", CLAUDE_PROJECT_DIR="/hook", GH_ENTERPRISE_TOKEN="e")
            r = subprocess.run(["bash", str(SC / "scrub_env.sh"), str(gh)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.splitlines()
        self.assertIn("GH_TOKEN=invalid", out)
        self.assertFalse([l for l in out if l.startswith("SSH_AUTH_SOCK=")])
        self.assertIn("GIT_SSH_COMMAND=false", out)
        self.assertIn("GIT_CONFIG_GLOBAL=/dev/null", out)
        self.assertIn("NO_PROXY=127.0.0.1,localhost,::1", out)
        self.assertIn("GITHUB_TOKEN=invalid", out)
        self.assertIn("HTTPS_PROXY=http://127.0.0.1:9", out)
        self.assertNotIn("GH_ENTERPRISE_TOKEN=e", out)
        self.assertFalse([l for l in out if l.startswith(("GIT_DIR=", "GH_CONFIG_DIR=/real"))])
        self.assertEqual(out[-1].strip(), "0")  # GH_CONFIG_DIR existed and was empty
        cfg = [l for l in out if l.startswith("GH_CONFIG_DIR=")][0].split("=", 1)[1]
        self.assertFalse(os.path.exists(cfg), "throwaway config dir removed on exit")

    def test_hook_env_prefix_scrub_and_net_opt_out(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR="/hook", SCRUB_PREFIXES="CLAUDE")
        r = subprocess.run(["bash", str(SC / "scrub_env.sh"), "env"], env=env, capture_output=True, text=True)
        self.assertNotIn("CLAUDE_PROJECT_DIR=/hook", r.stdout)
        r = subprocess.run(["bash", str(SC / "scrub_env.sh"), "env"], env=dict(env, PERUN_ALLOW_NET="1", HTTPS_PROXY="http://ok:1"), capture_output=True, text=True)
        self.assertIn("HTTPS_PROXY=http://ok:1", r.stdout)

    def test_run_ci_tests_runs_each_test_through_scrub_env(self):
        # behavior is pinned by test_run_ci_gates.py (its ci-test asserts GH_TOKEN=invalid and no SSH_AUTH_SOCK); here: the line is live code
        lines = (ROOT / "scripts/run-ci-tests.sh").read_text().splitlines()
        self.assertTrue([l for l in lines if "scrub_env.sh bash -e" in l and not l.lstrip().startswith("#")])

    def test_proxy_refuses_a_connection_not_the_real_network(self):
        r = subprocess.run(["bash", str(SC / "scrub_env.sh"), sys.executable, "-c",
                            "import urllib.request,sys\ntry:\n urllib.request.urlopen('http://example.com',timeout=5)\nexcept Exception as e:\n print('refused')\n sys.exit(0)\nsys.exit(1)"],
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "refused"), r.stderr)

    def test_admit_refuses_missing_declarations(self):
        with tempfile.TemporaryDirectory() as d:
            ok, bad = Path(d) / "ok.sh", Path(d) / "bad.sh"
            ok.write_text(GOOD)
            bad.write_text("# disk-cap: 1G\nx=$(mktemp -d)\n")
            self.assertEqual(bg_admit.missing(str(ok)), [])
            m = bg_admit.missing(str(bad))
            self.assertEqual(len(m), 2)  # trap and disk-stop
            self.assertEqual(bg_admit.missing(str(Path(d) / "gone.sh"))[0][:10], "unreadable")
            (Path(d) / "c.sh").write_text("# disk-stop: x\n# df is nice\n" + GOOD.split("\n", 1)[0] + "\ntrap : EXIT\n")
            self.assertTrue(bg_admit.missing(str(Path(d) / "c.sh")), "a comment mentioning df is not a stop check")

    def test_job_lease_admit_checks_the_script_that_runs(self):
        with tempfile.TemporaryDirectory() as d:
            bad, ok = Path(d) / "bad.sh", Path(d) / "ok.sh"
            bad.write_text("echo hi\n")
            ok.write_text(GOOD.replace("df -k . >/dev/null", 'if [ "$(df -k . | wc -l)" -lt 1 ]; then exit 1; fi'))
            run = lambda *c: subprocess.run([sys.executable, str(SC / "job_lease.py"), "run", "--admit", "--", *c], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run("bash", str(bad)).returncode, 2)
            self.assertEqual(run(str(bad)).returncode, 2)
            self.assertEqual(run("true").returncode, 2)  # not a script file: refused
            self.assertEqual(run("bash", str(ok)).returncode, 0)
            self.assertIn("REFUSE", run("bash", str(bad)).stderr)

    def test_mktemp_without_trap_is_linted_against_baseline(self):
        self.assertEqual(bg_admit.mktemp_untrapped(str(ROOT)), ([], []))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "scripts").mkdir()
            (Path(d) / "scripts/mktemp-trap-baseline.tsv").write_text("# c\n")
            (Path(d) / "scripts/a.sh").write_text('t=$(mktemp -d "${TMPDIR:-/tmp}/a.XXXXXX")\n')
            (Path(d) / "scripts/b.sh").write_text('t=$(mktemp -d "${TMPDIR:-/tmp}/b.XXXXXX"); trap \'rm -rf "$t"\' EXIT\n')
            self.assertEqual(bg_admit.mktemp_untrapped(d), (["scripts/a.sh"], []))
            (Path(d) / "scripts/lib").mkdir()
            (Path(d) / "scripts/lib/c.sh").write_text("t=$(mktemp -d x.XXXXXX); trap '' INT\n")  # nested dir, non-EXIT trap
            self.assertEqual(bg_admit.mktemp_untrapped(d)[0], ["scripts/a.sh", "scripts/lib/c.sh"])

    def test_baseline_is_shrink_only(self):
        rows = [l for l in (ROOT / "scripts/mktemp-trap-baseline.tsv").read_text().splitlines() if l.strip() and not l.startswith("#")]
        self.assertLessEqual(len(rows), 10, "baseline may only shrink: fix the script instead of adding a row")

    def test_admit_rejects_gamed_declarations(self):
        with tempfile.TemporaryDirectory() as d:
            g = Path(d) / "g.sh"
            g.write_text("# disk-cap: 0\n# disk-stop: x\necho ok # df -lt 1\necho hi # trap x EXIT\ndisk_usage=1\n")
            self.assertEqual(len(bg_admit.missing(str(g))), 3)


if __name__ == "__main__":
    unittest.main()
