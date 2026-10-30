#!/usr/bin/env python3
"""Offline tests for clock_lint.py's `timing bet under load` rule: each pattern, escape, negatives, --added, hook wiring."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = ".claude/skills/agentic-delivery/scripts/clock_lint.py"
HOOK = os.path.join(ROOT, ".claude/skills/deep-code-review/templates/pre-push-verify.sh")
MSG = "timing bet under load"


def lint(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, REL), *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class TimingBet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))

    def put(self, name, text):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def hits(self, text, name="test_t.py"):
        rc, out = lint(self.put(name, text))
        return rc, [l.split(":")[1] for l in out.splitlines() if MSG in l]

    def test_each_pattern_flagged(self):
        for src in ("def test_a():\n    time.sleep(0.5)\n    assert ready()\n",
                    "from time import sleep\ndef test_a():\n    sleep(1)\n    assert ready()\n",
                    "def test_a():\n    subprocess.run(cmd, timeout=5)\n",
                    "def test_a():\n    p.communicate(timeout=1)\n",
                    "def test_a():\n    q.get(timeout=1)\n",
                    "def test_a():\n    t0 = time.time()\n    assert time.time() - t0 < 2\n",
                    "def test_a():\n    assert timer.elapsed() < 2\n"):
            self.assertEqual(len(self.hits(src)[1]), 1, src)

    def test_every_elapsed_name_flagged_and_others_not(self):  # mutating ELAPSED must fail here
        for w in ("elapsed", "duration", "latency", "took", "runtime", "wall"):
            self.assertEqual(self.hits("def test_a():\n    assert r.%s <= 0.5\n" % w)[1], ["2"], w)
        for w in ("count", "size", "retries"):
            self.assertEqual(self.hits("def test_a():\n    assert %s < 2\n" % w)[1], [], w)
        self.assertEqual(self.hits("def test_a():\n    assert elapsed > 2\n")[1], [])

    def test_escape_honored(self):
        self.assertEqual(self.hits("def test_a():\n    time.sleep(1)  # clock-lint: allow\n    assert ok()\n"), (0, []))
        self.assertEqual(self.hits("def test_a():\n    # clock-lint: allow\n    assert elapsed < 2\n"), (0, []))
        self.assertEqual(self.hits("def test_a():\n    run(\n        c,  # clock-lint: allow\n        timeout=1)\n"), (0, []))

    def test_not_flagged(self):
        no = ("def test_a():\n    time.sleep(1)\n    do()\n",  # sleep, no assert after
              "def test_a():\n    assert ok()\n    time.sleep(1)\n",
              "def test_a():\n    subprocess.run(cmd, timeout=30)\n",
              "def test_a():\n    time.sleep(n)\n    assert ok()\n",
              "def test_a():\n    time.sleep(0)\n    assert ok()\n",
              "async def test_a():\n    await asyncio.sleep(1)\n    assert ok()\n",
              "def test_a():\n    sleep(1)\n    assert ok()\n",  # sleep not imported from time
              "def test_a():\n    if c:\n        time.sleep(1)\n    else:\n        assert ok()\n",
              "def helper():\n    time.sleep(1)\n    assert ok()\n")
        for src in no:
            self.assertEqual(self.hits(src)[1], [], src)

    def test_path_is_repo_relative(self):
        helper = "def helper():\n    subprocess.run(c, timeout=1)\n"
        self.assertEqual(self.hits(helper, "tests/h.py"), (1, ["2"]))
        root = os.path.join(self.d, "tests", "repo")  # an absolute path under a tests dir is not a tests/ file
        p = self.put("tests/repo/test_x.py", helper + "def test_a():\n    p.wait(timeout=1)\n")
        rc, out = lint("--root", root, p)
        self.assertEqual((rc, [l.split(":")[1] for l in out.splitlines()]), (1, ["4"]))

    def test_unparseable_is_could_not_check(self):
        rc, out = lint(self.put("test_bad.py", "def test_a(:\n"))
        self.assertEqual(rc, 2)
        self.assertIn("COULD_NOT_CHECK", out)

    def test_crash_fails_open(self):
        sys.path.insert(0, os.path.dirname(os.path.join(ROOT, REL)))
        import clock_lint as cl
        def boom(*_):
            raise RuntimeError("boom")
        real, cl.timing = cl.timing, boom
        try:
            self.assertEqual(cl.run(self.d, None, [self.put("test_c.py", "def test_a():\n    pass\n")]), 2)
        finally:
            cl.timing = real

    def repo(self):
        g = lambda *a, cwd=self.d: subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com", *a],
                                                  cwd=cwd, check=True, capture_output=True, text=True)
        g("init", "-q", "-b", "main")
        self.put("tests/test_old.py", "def test_a():\n    subprocess.run(c, timeout=1)\n")
        g("add", "."), g("commit", "-qm", "base")
        base = g("rev-parse", "HEAD").stdout.strip()
        self.put("tests/test_old.py", "def test_a():\n    subprocess.run(c, timeout=2)\n")  # modified: still a bet
        self.put("tests/test_new.py", "def test_a():\n    subprocess.run(c, timeout=1)\n")
        g("add", "."), g("commit", "-qm", "new")
        return g, base

    def test_block_added_only_new_files_exit_1(self):
        g, base = self.repo()
        rc, out = lint("--root", self.d, "--base", base)  # default mode: both files are findings
        self.assertEqual((rc, out.count(MSG)), (1, 2), out)
        rc, out = lint("--root", self.d, "--base", base, "--block-added")  # both print, only the added one blocks
        self.assertEqual((rc, out.count(MSG)), (1, 2), out)
        self.put("tests/test_new.py", "def test_a():\n    t = time.time()\n")  # a real-clock read in a new file only warns
        g("add", "."), g("commit", "-qm", "fix")
        rc, out = lint("--root", self.d, "--base", base, "--block-added")
        self.assertEqual((rc, out.count(MSG), out.count("real clock in test")), (0, 1, 1), out)
        self.assertEqual(lint("--block-added")[0], 2)  # needs --base

    def test_hook_blocks_added_warns_existing(self):
        g, base = self.repo()
        shutil.copy(os.path.join(ROOT, REL), os.path.join(self.d, "cl.py"))
        os.makedirs(os.path.join(self.d, os.path.dirname(REL)), exist_ok=True)
        os.replace(os.path.join(self.d, "cl.py"), os.path.join(self.d, REL))
        rem = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
        g("init", "-q", "--bare", cwd=rem)
        g("remote", "add", "origin", rem)
        g("push", "-q", "origin", "%s:refs/heads/main" % base), g("remote", "set-head", "origin", "main")
        g("add", "."), g("commit", "-qm", "lint")  # clock_lint.py itself is an added non-test file
        sha = g("rev-parse", "HEAD").stdout.strip()
        line = "refs/heads/feat %s refs/heads/feat %s\n" % (sha, base)
        run = lambda: subprocess.run(["bash", HOOK, "origin"], input=line, cwd=self.d, capture_output=True, text=True,
                                     env={**os.environ, "DCR_PREPUSH_CMD": "true"})
        p = run()
        self.assertNotEqual(p.returncode, 0, p.stderr)
        self.assertIn("timing bet in a NEW test file", p.stderr)
        os.remove(os.path.join(self.d, "tests/test_new.py"))  # only the modified (existing) file still has a bet
        g("add", "."), g("commit", "-qm", "drop")
        line = "refs/heads/feat %s refs/heads/feat %s\n" % (g("rev-parse", "HEAD").stdout.strip(), base)
        p = run()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(MSG, p.stderr)


if __name__ == "__main__":
    unittest.main()
