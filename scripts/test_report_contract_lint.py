#!/usr/bin/env python3
"""Tests: report_contract_lint.py passes a clean report and fails one seeded negative per rule, plus paraphrased safety claims."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LINT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/report_contract_lint.py"
HEAD = "| Item | Status | Basis | Files | Negative |\n|---|---|---|---|---|\n"
ROWS = {
    "tool": "| A1 | pass | tool:semgrep | src/app.py:2 | |\n",
    "guided": "| A2 | pass | guided:g1-07 | src/app.py | `run(escape(x))` |\n",
    "nc": "| A3 | not-checked | tool:zap | | |\n",
}
TAIL = "\n## NOT CHECKED\n- A3: needs runtime\n\n## NOT RUN\n- zap: no running target\n\n## Static vs runtime\nWAF needs a deployed system.\n\n## Dependencies\nLockfile read.\n"


def report(rows=ROWS["tool"] + ROWS["guided"] + ROWS["nc"], tail=TAIL, extra=""):
    return "# Audit\n\n## Per-standard table\n" + HEAD + rows + extra + tail


def lint(text):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "src").mkdir()
        (Path(d) / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
        r = Path(d) / "report.md"
        r.write_text(text)
        p = subprocess.run([sys.executable, str(LINT), str(r), "--root", d], capture_output=True, text=True)
        return p.returncode, p.stdout


class Contract(unittest.TestCase):
    def bad(self, text, rule):
        rc, out = lint(text)
        self.assertEqual(rc, 1, out)
        self.assertIn(f": {rule}:", out)

    def test_clean_positive(self):
        self.assertEqual(lint(report()), (0, "ok\n"))

    def test_missing_sections(self):
        self.bad(report(tail=TAIL.replace("## NOT CHECKED", "## Other")), "missing-not-checked")
        self.bad(report(tail=TAIL.replace("## Static vs runtime", "## Other")), "missing-static-runtime")
        self.bad(report(tail=TAIL.replace("## Dependencies", "## Other")), "missing-dependencies")
        self.bad("# Audit\n" + TAIL, "missing-table")

    def test_unstatused_item(self):
        self.bad(report(extra="| A4 | | tool:semgrep | | |\n"), "unstatused-item")

    def test_missing_cited_path_and_line(self):
        self.bad(report(extra="| A4 | fail | tool:semgrep | src/nope.py:1 | |\n"), "bad-citation")
        self.bad(report(extra="| A4 | fail | tool:semgrep | src/app.py:99 | |\n"), "bad-citation")
        self.bad(report(extra="See `src/gone.py:3` for details.\n"), "bad-citation")

    def test_guided_pass_needs_files_and_negative(self):
        self.bad(report(extra="| A4 | pass | guided:g1-08 | | `x` |\n"), "guided-pass-no-files")
        self.bad(report(extra="| A4 | pass | guided:g1-08 | src/app.py | none |\n"), "guided-pass-no-negative")

    def test_pass_for_tool_not_run(self):
        self.bad(report(extra="| A4 | pass | tool:zap | | |\n"), "pass-tool-not-run")
        self.bad(report(extra="| A4 | pass | | | |\n"), "pass-no-check")

    def test_too_many_not_checked(self):
        rows = ROWS["tool"] + "| B | not-checked | | | |\n" * 2
        self.bad(report(rows=rows), "too-many-not-checked")
        # a NOT RUN reason excuses them
        self.assertEqual(lint(report(rows=ROWS["tool"] + ROWS["nc"] * 2))[0], 0)

    def test_safety_claim_and_paraphrases(self):
        for s in ["No vulnerabilities were found.", "The app is secure.", "This is completely safe.",
                  "The codebase appears hardened against injection.", "Zero security issues remain.",
                  "Safe to deploy.", "The service is vulnerability-free.", "Nothing exploitable here.",
                  "It is compliant with OWASP ASVS.", "No issues were identified."]:
            with self.subTest(s=s):
                self.bad(report(extra=s + "\n"), "safety-claim")

    def test_negated_and_quoted_text_not_a_claim(self):
        self.assertEqual(lint(report(extra="This report does not say the app is secure. `is_safe = True`\n"))[0], 0)
        self.assertEqual(lint(report(extra="I won't state a version is current or safe from memory.\n"))[0], 0)
        self.bad(report(extra="I do not claim it is perfect and is secure.\n"), "safety-claim")
        self.bad(report(extra="The app is, without exception, secure.\n"), "safety-claim")
        self.bad(report(extra="The app is fast and secure.\n"), "safety-claim")

    # round 2: independent-review probes
    def test_scoped_tool_count_not_a_claim(self):
        t = TAIL.replace("Lockfile read.", "osv-scanner: 0 vulnerabilities in package-lock.json.")
        self.assertEqual(lint(report(tail=t))[0], 0)
        self.assertEqual(lint(report(tail=TAIL + "\nScanned: no vulnerabilities in `src/app.py`.\n"))[0], 0)

    def test_not_secure_is_not_a_claim(self):
        self.assertEqual(lint(report(extra="The app is not secure against CSRF.\n"))[0], 0)

    def test_without_secure_listing_is_not_a_claim(self):
        self.assertEqual(lint(report(extra="The cookie is set without httpOnly, secure.\n"))[0], 0)
        self.bad(report(extra="The app is secure without any tuning.\n"), "safety-claim")

    def test_route_paths_not_citations(self):
        self.assertEqual(lint(report(extra="Routes `/admin/users`, `/notes/2`, `/preview`, `/login`, `GET /x`.\n"))[0], 0)
        self.bad(report(extra="See `/etc/hosts` and `src/nope.py:1`.\n"), "bad-citation")

    def test_claim_after_distant_negator(self):
        self.bad(report(extra="We did not test X; the app is secure.\n"), "safety-claim")
        self.bad(report(extra="We did not test X and the app is secure.\n"), "safety-claim")

    def test_backticked_prose_and_second_match(self):
        self.bad(report(extra="`The app is secure`\n"), "safety-claim")
        self.bad(report(extra="The app is not secure, but the API is secure.\n"), "safety-claim")

    def test_more_paraphrases(self):
        for s in ["Nothing found.", "All clear.", "The app is free of vulnerabilities.",
                  "No high-severity findings.", "The API is not vulnerable to SQL injection."]:
            with self.subTest(s=s):
                self.bad(report(extra=s + "\n"), "safety-claim")

    def test_item_column_exempt(self):
        self.assertEqual(lint(report(extra="| Is the app secure by default | fail | tool:semgrep | | |\n"))[0], 0)

    def test_nested_headings_and_fences(self):
        t = TAIL.replace("## Static vs runtime\n", "## Static vs runtime\n### Subsection\n")
        self.assertEqual(lint(report(tail=t))[0], 0)
        fenced = "```\n## Dependencies\n```\n"
        self.bad("# A\n\n## Per-standard table\n" + HEAD + ROWS["tool"] + "\n## NOT CHECKED\n## Static vs runtime\n" + fenced, "missing-dependencies")

    def test_multiple_tables_and_separator(self):
        self.bad(report(extra="\n| Item | Status |\n| A9 | pass |\n"), "malformed-table")
        rc, out = lint(report(extra="\n" + HEAD + "| B1 | fail | tool:semgrep | | |\n"))
        self.assertEqual((rc, out), (0, "ok\n"))

    def test_pipe_in_backticks_and_escaped(self):
        self.assertEqual(lint(report(extra="| A5 | fail | tool:semgrep | src/app.py | `a || b` and x\\|y |\n"))[0], 0)

    def test_guided_negative_must_be_in_cited_file_and_file_real(self):
        self.bad(report(extra="| A4 | pass | guided:g1-09 | src/app.py | `not in file` |\n"), "guided-pass-negative-not-in-files")
        self.bad(report(extra="| A4 | pass | guided:g1-09 | n/a | `run(escape(x))` |\n"), "guided-pass-no-files")
        self.bad(report(extra="| A4 | pass | guided: | src/app.py | `x` |\n"), "pass-no-check")

    def test_unparseable_and_escaping_citations(self):
        for f in ["src/app.py:2:5", "src/app.py#L2", "/etc/hosts", "../../../../etc/hosts:1"]:
            with self.subTest(f=f):
                self.bad(report(extra=f"| A4 | fail | tool:semgrep | {f} | |\n"), "bad-citation")

    def test_symlink_escape(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "root").mkdir()
            os.symlink("/etc/hosts", Path(d) / "root/link.txt")
            r = Path(d) / "r.md"
            r.write_text(report(extra="| A4 | fail | tool:semgrep | link.txt | |\n"))
            p = subprocess.run([sys.executable, str(LINT), str(r), "--root", str(Path(d) / "root")], capture_output=True, text=True)
            self.assertIn("escapes --root", p.stdout)

    def test_status_normalized(self):
        for st in ["**pass**", "Not checked", "not_checked"]:
            with self.subTest(st=st):
                rows = ROWS["tool"] + ROWS["guided"] + ROWS["nc"]
                self.assertEqual(lint(report(rows=rows, extra=f"| A4 | {st} | tool:semgrep | | |\n"))[0], 0)

    def test_not_run_fail_closed(self):
        self.bad(report(tail=TAIL.replace("- zap: no running target", "- zap")), "not-run-no-reason")
        self.bad(report(tail=TAIL.replace("- zap: no running target", "- zap:")), "not-run-no-reason")
        self.bad(report(tail=TAIL.replace("## NOT RUN", "## Tools Not Run"), extra="| A4 | pass | tool:zap | | |\n"), "pass-tool-not-run")

    def test_basis_tokenized_against_not_run(self):
        self.bad(report(extra="| A4 | pass | tool:semgrep+zap | | |\n"), "pass-tool-not-run")
        self.bad(report(extra="| A4 | pass | tool: zap, semgrep | | |\n"), "pass-tool-not-run")

    def test_usage_error_exit_2(self):
        p = subprocess.run([sys.executable, str(LINT), "/nonexistent.md", "--root", "/"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    # round 3: held-out probes (normalization, asides, cookie context)
    def test_normalized_and_aside_claims(self):
        tl = lambda s: report(tail=TAIL + "\n" + s + "\n")
        for s in ["The service is **secure**.", "Overall the codebase is\nsecure.", "The app is, in our view, secure.",
                  "The app is really quite secure.", "The app is ~~insecure~~ _safe_.", "The repository is free of vulnerabilities.",
                  "This project is production-ready from a security standpoint.", "No vulnerabilities were found."]:
            with self.subTest(s=s):
                self.bad(tl(s), "safety-claim")

    def test_honest_text_not_flagged(self):
        tl = lambda s: report(tail=TAIL + "\n" + s + "\n")
        for s in ["Session cookies are marked Secure and HttpOnly.", "The cookie has the Secure flag.",
                  "The Dockerfile is not hardened: it runs as root.", "gitleaks (ran): 0 secrets in git history.",
                  "semgrep: no findings in src/."]:
            with self.subTest(s=s):
                self.assertEqual(lint(tl(s))[0], 0)
        self.assertEqual(lint(report(extra="| Verify the application is secure by default | fail | tool:semgrep | src/app.py:1 | |\n"))[0], 0)
        self.assertEqual(lint(report(rows="| A1 | **pass** | tool:semgrep | src/app.py:2 | |\n" + ROWS["guided"] + ROWS["nc"]))[0], 0)

    def test_probe2_structural(self):
        self.bad(report(extra="| A3 | pass | tool:zap | src/app.py:1 | |\n"), "pass-tool-not-run")
        self.bad(report(rows="| A1 | pass | tool:semgrep | src/app.py:99 | |\n" + ROWS["guided"] + ROWS["nc"]), "bad-citation")
        self.bad(report(tail=TAIL.replace("## NOT CHECKED\n- A3: needs runtime\n", "")), "missing-not-checked")

    # round 4
    def test_passes_all_checks_claim(self):
        for s in ["The codebase passes all security checks.", "Every security scan passed.", "The app cleared all tests."]:
            with self.subTest(s=s):
                self.bad(report(extra=s + "\n"), "safety-claim")
        self.assertEqual(lint(report(extra="semgrep: 12 checks passed in src/.\n"))[0], 0)


if __name__ == "__main__":
    unittest.main()
