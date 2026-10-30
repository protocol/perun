#!/usr/bin/env python3
"""Offline tests for clock_lint.py's `timing bet under load` rule on js/ts test files (#2141): each pattern, escape,
negatives, fake-timer exemption, block scoping, --block-added and fail-open. Stdlib only."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = ".claude/skills/agentic-delivery/scripts/clock_lint.py"
MSG = "timing bet under load"


def lint(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, REL), *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def it(*body):
    """A test block whose body is the given lines (2-space indented): `it('a', async () => {` is line 1."""
    return "it('a', async () => {\n" + "".join("  %s\n" % l for l in body) + "});\n"


class JsTimingBet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))

    def put(self, name, text):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def hits(self, text, name="a.test.ts"):
        rc, out = lint(self.put(name, text))
        return rc, [l.split(":")[1] for l in out.splitlines() if MSG in l]

    def test_each_pattern_flagged_at_its_line(self):
        cases = (
            (it("await sleep(500);", "expect(ready()).toBe(true);"), "2"),
            (it("await delay(1000);", "assert.ok(ready());"), "2"),
            ("test('a', async ({ page }) => {\n  await page.waitForTimeout(500);\n  await expect(page.locator('x')).toBeVisible();\n});\n", "2"),
            (it("cy.wait(500);", "cy.get('x').should('exist');"), "2"),
            (it("await new Promise((resolve) => setTimeout(resolve, 500));", "expect(ready()).toBe(true);"), "2"),
            (it("setTimeout(() => {", "  expect(ready()).toBe(true);", "}, 100);"), "2"),  # the assert runs after the delay
            (it("await waitFor(() => ready(), { timeout: 1000 });"), "2"),
            (it("execSync(cmd, { timeout: 2000 });"), "2"),
            (it("await screen.findByText('x', {}, { timeout: 500 });"), "2"),
            (it("await expect(page.locator('x')).toBeVisible({ timeout: 1000 });"), "2"),
            (it("await waitFor(() => ready(), {", "  interval: 50,", "  timeout: 1_000,", "});"), "2"),  # options on their own lines
            (it("const t0 = Date.now();", "run();", "expect(Date.now() - t0).toBeLessThan(100);"), "4"),
            (it("expect(elapsed).toBeLessThanOrEqual(2000);"), "2"),
            (it("expect(timer.elapsed()).to.be.below(2000);"), "2"),
            (it("expect(took).to.be.at.most(2000);"), "2"),
            (it("expect(took).to.be.lte(2000);"), "2"),
            (it("expect(took).to.be.lt(2000);"), "2"),
            (it("expect(took).to.be.lessThan(2000);"), "2"),
            (it("assert(elapsed < 2000);"), "2"),
            (it("assert.ok(performance.now() - t0 <= 50);"), "2"),
            (it("await new Promise((r) => /\\)/.test(x) && setTimeout(r, 500));", "expect(ok()).toBe(true);"), "2"),  # an escaped bracket in a regex
        )
        for src, line in cases:
            self.assertEqual(self.hits(src), (1, [line]), src)

    def test_every_elapsed_name_flagged_and_others_not(self):  # mutating ELAPSED must fail here
        for w in ("elapsed", "duration", "latency", "took", "runtime", "wall"):
            self.assertEqual(self.hits(it("expect(r.%s).toBeLessThanOrEqual(500);" % w)), (1, ["2"]), w)
        for src in (it("expect(count).toBeLessThan(2);"), it("assert(size < 2);"), it("expect(elapsed).toBeGreaterThan(2);"),
                    it("expect(elapsed).not.toBeLessThan(2000);"), it("expect(elapsed).toBeLessThan(limit);"),
                    it("expect(rows.filter((r) => r.duration).length).toBeLessThan(3);")):
            self.assertEqual(self.hits(src), (0, []), src)

    def test_escape_honored(self):
        for src in (it("await sleep(500); // clock-lint: allow", "expect(ok()).toBe(true);"),
                    it("// clock-lint: allow", "expect(elapsed).toBeLessThan(2);"),
                    it("await waitFor(", "  () => ready(),", "  { timeout: 1000 }, // clock-lint: allow", ");")):
            self.assertEqual(self.hits(src), (0, []), src)
        self.assertEqual(self.hits(it("await sleep(500); // clock-lint: allow", "await sleep(500);", "expect(ok()).toBe(true);")),
                         (1, ["3"]))  # the escape covers its own call only

    def test_not_flagged(self):
        no = (it("await sleep(500);", "done();"),  # sleep, no assert after
              it("expect(ok()).toBe(true);", "await sleep(500);"),
              it("await sleep(ms);", "expect(ok()).toBe(true);"),
              it("await sleep(0);", "expect(ok()).toBe(true);"),
              it("setTimeout(emit, 10);", "expect(ok()).toBe(true);"),  # scheduling a producer is not a sleep
              it("await waitFor(() => ready(), { timeout: 30000 });"),
              it("await p.wait({ timeout: 0 });"),  # 0 means no timeout
              it("await waitFor(() => ready(), { timeout: ms });"),
              it("const s = new Server({ timeout: 100 });"),  # not a call the test waits on
              it("expect(elapsed).toBeGreaterThan(2);"),
              it("// await sleep(500);", "expect(ok()).toBe(true);"),
              it("const s = 'await sleep(500); expect(1)';", "expect(ok()).toBe(true);"),
              it("const c = `await sleep(500)`;", "expect(ok()).toBe(true);"),  # template literal text
              it("await waitFor(() => other({ timeout: 100 }));"),  # not the options of the call being waited on
              it("expect(performance.now()).toBeLessThan(5000);"),  # a clock read that is not a difference
              "/**\n * await sleep(500);\n * expect(x).toBe(1);\n */\n" + it("expect(1).toBe(1);"),
              "it('a', async () => {\n  await sleep(500);\n});\nit('b', () => {\n  expect(1).toBe(1);\n});\n",  # the assert is in the next block
              "const fixture = async () => { await sleep(500); };\n" + it("expect(1).toBe(1);"))
        for src in no:
            self.assertEqual(self.hits(src), (0, []), src)

    def test_fake_timers_exempt_the_file(self):
        bet = it("setTimeout(f, 10);", "expect(elapsed).toBeLessThan(2000);", "await sleep(500);", "expect(1).toBe(1);")
        self.assertEqual(self.hits(bet), (1, ["3", "4"]))  # unpinned, the file has two bets
        for marker in ("beforeEach(() => { jest.useFakeTimers(); });\n", "vi.useFakeTimers();\n", "const clock = sinon.useFakeTimers();\n",
                       "jest.setSystemTime(0);\n"):
            self.assertEqual(self.hits(marker + bet), (0, []), marker)
        self.assertEqual(self.hits("// jest.useFakeTimers() later\n" + bet), (1, ["4", "5"]))  # a comment pins nothing
        self.assertEqual(self.hits("import { useFakeTimers } from './x';\n" + bet), (1, ["4", "5"]))  # a bare import pins nothing

    def test_every_js_extension_and_tests_dir_helper(self):
        src = it("await sleep(500);", "expect(ok()).toBe(true);")
        for name in ("a.test.js", "a.spec.tsx", "a.test.mjs", "b.test.cjs", "c.spec.mts", "__tests__/h.ts", "tests/h.js"):
            self.assertEqual(self.hits(src, name), (1, ["2"]), name)
        rc, out = lint(self.put("app.ts", src))
        self.assertEqual((rc, MSG in out), (0, False))  # not a test file

    def test_odd_text_never_crashes(self):
        for src in ("it('a', () => {\n  await sleep(500;\n  expect(1)\n", "(((((", ")))", "expect(", "assert(", "setTimeout(",
                    "it('a', () => { `unterminated\n expect(a).toBeLessThan(1)", "expect(a).toBeLessThan(", "", "\n\n",
                    "it('a', () => { expect(/\\(/.test(x)).toBe(true); });\nit('b', () => { expect(1).toBe(1); });\n"):
            rc, out = lint(self.put("odd.test.ts", src))
            self.assertEqual((rc, "COULD_NOT_CHECK" in out, MSG in out), (0, False, False), src)

    def test_crash_fails_open(self):
        sys.path.insert(0, os.path.dirname(os.path.join(ROOT, REL)))
        import clock_lint as cl

        def boom(*_):
            raise RuntimeError("boom")
        real, cl.jstiming = cl.jstiming, boom
        try:
            self.assertEqual(cl.run(self.d, None, [self.put("c.test.ts", it("expect(1).toBe(1);"))]), 2)
        finally:
            cl.jstiming = real

    def test_block_added_only_new_files_exit_1(self):
        g = lambda *a: subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                                      cwd=self.d, check=True, capture_output=True, text=True)
        g("init", "-q", "-b", "main")
        self.put("tests/old.test.ts", it("await sleep(500);", "expect(ok()).toBe(true);"))
        g("add", "."), g("commit", "-qm", "base")
        base = g("rev-parse", "HEAD").stdout.strip()
        self.put("tests/old.test.ts", it("await sleep(600);", "expect(ok()).toBe(true);"))  # modified: still a bet
        self.put("tests/new.test.ts", it("await sleep(500);", "expect(ok()).toBe(true);"))
        g("add", "."), g("commit", "-qm", "new")
        rc, out = lint("--root", self.d, "--base", base)  # default mode: both files are findings
        self.assertEqual((rc, out.count(MSG)), (1, 2), out)
        rc, out = lint("--root", self.d, "--base", base, "--block-added")  # both print, only the added one blocks
        self.assertEqual((rc, out.count(MSG)), (1, 2), out)
        self.put("tests/new.test.ts", it("expect(ok()).toBe(true);"))
        g("add", "."), g("commit", "-qm", "fix")
        rc, out = lint("--root", self.d, "--base", base, "--block-added")  # the old file's bet is only a warning now
        self.assertEqual((rc, out.count(MSG)), (0, 1), out)


if __name__ == "__main__":
    unittest.main()
