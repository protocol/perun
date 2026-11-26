"""issue_gate.py and the finding_guard.py raw-create block: dedupe incl. closed, cap + flock, failed create not counted,
label fallback, shared state dir, area check, corrupt lines, queue titles. Hermetic: stub gh on PATH, temp dirs removed."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / ".claude/skills/agentic-delivery/scripts/issue_gate.py"
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/finding_guard.py"
OPEN = '[{"number":7,"title":"Retry queue stalls after timeout","state":"OPEN","url":"https://example.com/7"}]'
CLOSED = '[{"number":9,"title":"Parser drops quoted fields silently","state":"CLOSED","url":"https://example.com/9"}]'
STUB = r"""#!/bin/sh
d="$STUB_DIR"
if [ "$2" = list ]; then echo "${STUB_LIST:-[]}"; exit 0; fi
p=""; labels=0
for a in "$@"; do [ "$p" = --body-file ] && cat "$a" >> "$d/bodies"; [ "$a" = --label ] && labels=1; p="$a"; done
echo "$PERUN_ISSUE_GATE $*" >> "$d/calls"
[ -n "$STUB_CREATE_FAIL" ] && [ ! -f "$d/failed_once" -o "$STUB_CREATE_FAIL" = always ] && { touch "$d/failed_once"; echo "boom" >&2; exit 1; }
[ -n "$STUB_LABEL_FAIL" ] && [ "$labels" = 1 ] && { echo "could not add label: 'P2' not found" >&2; exit 1; }
echo https://example.com/1
"""


class T(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / "bin").mkdir()
        gh = self.d / "bin/gh"
        gh.write_text(STUB)
        gh.chmod(0o755)
        (self.d / "body.md").write_text("body")
        self.env = {**os.environ, "PATH": f"{self.d}/bin:{os.environ['PATH']}", "PERUN_DIR": str(self.d / "state"), "STUB_DIR": str(self.d)}
        self.env.pop("STUB_LIST", None)

    def run_gate(self, *args, env=None, cwd=None):
        return subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True, env=env or self.env, cwd=cwd or self.d)

    def file(self, title, sev="medium", pri="P2", area="ci", env=None, cwd=None):
        return self.run_gate("file", "--title", title, "--body-file", str(self.d / "body.md"), "--priority", pri, "--area", area,
                             "--severity", sev, env=env, cwd=cwd)

    def calls(self):
        p = self.d / "calls"
        return p.read_text().splitlines() if p.exists() else []

    def test_files_with_labels_and_gate_marker(self):
        r = self.file("Cache key ignores locale")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "https://example.com/1"))
        self.assertIn("1 issue create", self.calls()[0])
        self.assertIn("--label P2 --label area:ci", self.calls()[0])

    def test_refuses_low_and_nit(self):
        for s in ("low", "nit"):
            r = self.file("Typo in readme", s)
            self.assertEqual(r.returncode, 1)
            self.assertIn("fold into the next PR", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_open_and_closed_duplicates_via_file_finding(self):
        r = self.file("Retry queue stalls after timeout!", env={**self.env, "STUB_LIST": OPEN})
        self.assertEqual(r.returncode, 1)
        self.assertIn("#7", r.stderr)
        r = self.file("Parser drops quoted fields silently", env={**self.env, "STUB_LIST": CLOSED})
        self.assertEqual(r.returncode, 1)  # regression: a closed issue is still a duplicate
        self.assertIn("#9 [CLOSED]", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_fails_closed_when_search_fails(self):
        (self.d / "bin/gh").write_text("#!/bin/sh\nexit 1\n")
        self.assertEqual(self.file("Anything new here").returncode, 2)

    def test_cap_queues_overflow_exempts_critical_and_lists_titles(self):
        for t in ("Alpha widget leaks handles", "Bravo parser drops quotes", "Charlie cron skips sundays"):
            self.assertEqual(self.file(t).returncode, 0)
        self.assertEqual(self.file("Delta exporter truncates rows").returncode, 3)
        self.assertEqual(self.run_gate("queue").stdout.splitlines(), ["1", "Delta exporter truncates rows"])
        self.assertEqual(self.file("Echo token logged in plain text", "critical", "P0").returncode, 0)
        self.assertEqual(len(self.calls()), 4)

    def test_parallel_filings_never_exceed_the_cap(self):
        ps = [subprocess.Popen([sys.executable, str(GATE), "file", "--title", t, "--body-file", str(self.d / "body.md"), "--priority", "P2",
                                "--area", "ci"], env=self.env, cwd=self.d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
              for t in ("Aaa one thing", "Bbb two thing", "Ccc three thing", "Ddd four thing", "Eee five thing")]
        self.assertEqual(sorted(p.wait() for p in ps), [0, 0, 0, 3, 3])
        self.assertEqual(len(self.calls()), 3)

    def test_failed_create_is_not_counted_and_exits_2(self):
        env = {**self.env, "STUB_CREATE_FAIL": "always"}
        for i in range(3):
            r = self.file(f"Doomed filing number {i}x", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("boom", r.stderr)
        for t in ("Alpha widget leaks handles", "Bravo parser drops quotes", "Charlie cron skips sundays"):
            self.assertEqual(self.file(t).returncode, 0)  # the three failures did not use the cap

    def test_missing_label_retries_without_labels_and_puts_them_in_body(self):
        r = self.file("Cache key ignores locale", env={**self.env, "STUB_LABEL_FAIL": "1"})
        self.assertEqual(r.returncode, 0)
        last = self.calls()[-1]
        self.assertNotIn("--label", last)
        self.assertIn("Priority: P2\nArea: ci", (self.d / "bodies").read_text())

    def test_area_is_validated(self):
        self.assertEqual(self.file("Cache key ignores locale", area="bad area;rm").returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_default_state_dir_is_the_git_common_dir(self):
        repo = self.d / "repo"
        (repo / "sub").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        env = {k: v for k, v in self.env.items() if k != "PERUN_DIR"}
        self.assertEqual(self.file("Cache key ignores locale", env=env, cwd=repo / "sub").returncode, 0)
        self.assertTrue((repo / ".git/perun-issue-gate/issue-filed.jsonl").exists())
        self.assertFalse((repo / "sub/.perun").exists())

    def test_unwritable_state_dir_exits_2(self):
        (self.d / "blocker").write_text("file, not a dir")
        r = self.file("Cache key ignores locale", env={**self.env, "PERUN_DIR": str(self.d / "blocker/sub")})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_fallback_regex_allows_flags_between_gh_and_issue_create(self):
        sys.path.insert(0, str(GUARD.parent))
        import finding_guard as fg
        for c in ("gh -R o/r issue create", "FOO=1 gh --repo o/r issue create", "x; gh issue create", "env gh issue create"):
            self.assertTrue(fg.FALLBACK.search(c), c)
        for c in ("echo gh issue create", "gh issue list"):
            self.assertFalse(fg.FALLBACK.search(c), c)

    def test_corrupt_lines_are_skipped(self):
        s = self.d / "state"
        s.mkdir()
        (s / "issue-filed.jsonl").write_text("{not json\n")
        (s / "issue-queue.jsonl").write_text('garbage\n{"title": "Kept"}\n')
        self.assertEqual(self.file("Cache key ignores locale").returncode, 0)
        self.assertEqual(self.run_gate("queue").stdout.splitlines(), ["1", "Kept"])

    def hook(self, cmd, gate_env=False):
        env = {k: v for k, v in self.env.items() if k != "PERUN_ISSUE_GATE"}
        if gate_env:
            env["PERUN_ISSUE_GATE"] = "1"
        return subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                              capture_output=True, text=True, env=env).returncode

    def test_hook_blocks_every_raw_create_form(self):
        for c in ('gh issue create --title "Fresh" --body x', "PERUN_ISSUE_GATE=1 gh issue create --title Fresh",
                  "gh -R o/r issue create --title Fresh", "gh --repo=o/r issue create --title Fresh",
                  "cd x && gh issue create -t Fresh", "gh api repos/o/r/issues -f title=x", "gh api -X POST repos/o/r/issues",
                  "gh api repos/o/r/issues --input body.json", "gh api --method POST /repos/o/r/issues",
                  "true a#b; gh issue create --title t", "FOO=1 gh -R o/r issue create --title t", "env FOO=1 gh issue create -t x",
                  "sudo gh issue create -t x", "true\ngh issue create -t x", "(gh issue create -t x)", "x | gh issue create -t x"):
            self.assertEqual(self.hook(c), 2, c)
        self.assertEqual(self.hook('gh issue create --title "Fresh thing"', gate_env=True), 0)

    def test_hook_allows_mentions_and_reads(self):
        for c in ('git commit -m "docs: gh issue create is gated"', 'echo "gh issue create"', "gh issue list", "gh api repos/o/r/issues",
                  "gh api -X GET repos/o/r/issues", "gh pr create --title x",
                  "echo gh issue create", "cat <<EOF\nnote: gh issue create is gated\nEOF", "git commit -m x # gh issue create"):
            self.assertEqual(self.hook(c), 0, c)


if __name__ == "__main__":
    unittest.main()
