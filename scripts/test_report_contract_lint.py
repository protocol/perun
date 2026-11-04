#!/usr/bin/env python3
"""Tests: report_contract_lint.py passes a clean report and fails one seeded negative per rule, plus paraphrased safety claims."""
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OK = "ok: emit this exact draft as your final answer, verbatim\n"
PLAIN = "ok\n"  # REPORT and - modes
LINT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/report_contract_lint.py"
HEAD = "| Item | Status | Basis | Files | Negative |\n|---|---|---|---|---|\n"
ROWS = {
    "tool": "| A1 | pass | tool:semgrep | src/app.py:2 | |\n",
    "guided": "| A2 | pass | guided:g1-07 | src/app.py | `run(escape(x))` |\n",
    "nc": "| A3 | not-checked | tool:zap | | |\n",
}
TAIL = "\n## NOT CHECKED\n- A3: needs runtime\n\n## NOT RUN\n- zap: no running target\n\n## Static vs runtime\nWAF needs a deployed system.\n\n## Dependencies\nLockfile read.\n\n## Route inventory\n- GET /a src/app.py:1 auth=none rate-limit=no\n"


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
        self.assertEqual(lint(report()), (0, PLAIN))

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
        self.bad(report(extra="I do not claim it is perfect but it is secure.\n"), "safety-claim")
        for s in ["I cannot say whether the app is secure and ready to ship.", "Not claiming no issues were found."]:
            self.assertEqual(lint(report(extra=s + "\n"))[0], 0, s)
        self.bad(report(extra="The app is, without exception, secure.\n"), "safety-claim")
        self.bad(report(extra="The app is fast and secure.\n"), "safety-claim")

    # round 2: independent-review probes
    def test_scoped_tool_count_not_a_claim(self):
        t = TAIL.replace("Lockfile read.", "osv-scanner: 0 vulnerabilities in package-lock.json.")
        self.assertEqual(lint(report(tail=t))[0], 0)
        self.assertEqual(lint(report(tail=TAIL.replace("\n## Route inventory", "\nScanned: no vulnerabilities in `src/app.py`.\n\n## Route inventory")))[0], 0)

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
        self.assertEqual((rc, out), (0, PLAIN))

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
        tl = lambda s: report(tail=TAIL.replace("\n## Route inventory", "\n" + s + "\n\n## Route inventory"))
        for s in ["The service is **secure**.", "Overall the codebase is\nsecure.", "The app is, in our view, secure.",
                  "The app is really quite secure.", "The app is ~~insecure~~ _safe_.", "The repository is free of vulnerabilities.",
                  "This project is production-ready from a security standpoint.", "No vulnerabilities were found."]:
            with self.subTest(s=s):
                self.bad(tl(s), "safety-claim")

    def test_honest_text_not_flagged(self):
        tl = lambda s: report(tail=TAIL.replace("\n## Route inventory", "\n" + s + "\n\n## Route inventory"))
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

    # findings format
    def test_finding_class(self):
        ok = "\n## Findings\n- [pii-data] src/app.py:2 high: serves SSNs. evidence: src/app.py:1\n- [hardcoded-secret] src/app.py:3 high: key in source\n"
        self.assertEqual(lint(report(extra=ok))[0], 0)
        self.assertEqual(lint(report(extra="\n## Findings\n1. **[xss]** src/app.py:2 high: x\n2) [csrf] src/app.py:3 low: y\n"))[0], 0)
        self.bad(report(extra="\n## Findings\n- src/app.py:2 high: serves SSNs\n"), "finding-no-class")
        self.bad(report(extra="\n## Findings\n- [privacy] src/app.py:2 high: serves SSNs\n"), "finding-no-class")
        self.bad(report(extra="\n## Findings\n- [xss] app.py:2 high: x\n"), "bad-citation")
        self.bad(report(extra="\n## Findings\n- [xss] src/app.py high: x\n"), "bad-citation")

    def test_finding_single_cite(self):
        self.bad(report(extra="\n## Findings\n- [xss] src/app.py:1,2 high: x\n"), "finding-multi-cite")
        self.bad(report(extra="\n## Findings\n- [xss] src/app.py:1 high: x via src/app.py:2\n"), "finding-multi-cite")
        ok = ("\n## Findings\nTwo findings.\n- [XSS] src/app.py:1 medium-high: reaches 127.0.0.1:8080 and example.com:443\n"
              "  evidence: src/app.py:2\n### Attack paths\n- src/app.py:1 -> src/app.py:2\n## Finding 3: notes\n- prose\n")
        self.assertEqual(lint(report(extra=ok))[0], 0)
        split = runpy.run_path(str(LINT))["FILES_SPLIT"]
        self.assertEqual(re.split(split, "a.py,2fa.py src/app.py:1,2"), ["a.py", "2fa.py", "src/app.py:1,2"])

    def test_line_lists_and_stdin(self):
        self.assertEqual(lint(report(rows=ROWS["tool"].replace("src/app.py:2", "src/app.py:1,2,3") + ROWS["guided"] + ROWS["nc"]))[0], 0)
        self.assertEqual(lint(report(extra="See `src/app.py:1,3`.\n"))[0], 0)
        self.bad(report(extra="See `src/app.py:1,99`.\n"), "bad-citation")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
            run = lambda t: subprocess.run([sys.executable, str(LINT), "-", "--root", d], input=t, capture_output=True, text=True)
            self.assertEqual(run(report(extra="\n## Findings\n- [other] src/app.py:1 low: y\n")).returncode, 0)
            self.assertEqual(run(report(extra="\n## Findings\n- y\n")).returncode, 1)


class RouteInventory(unittest.TestCase):
    def rc(self, tail):
        return lint(report().replace("\n## Route inventory\n- GET /a src/app.py:1 auth=none rate-limit=no\n", tail))

    def test_inventory_rules(self):
        self.assertEqual(self.rc("")[1].count("missing-route-inventory"), 1)
        for line in ("- GET /a auth=none rate-limit=no", "- POST /a, /b src/app.py:1 src/app.py:2", "- GET /a app.py:1 auth=none", "- GET /a src/gone.py:1 auth=none"):
            with self.subTest(line=line):
                self.assertIn("inventory-no-cite", self.rc("\n## Route inventory\n" + line + "\n")[1])
        self.assertEqual(self.rc("\n## Route inventory\n- GET /a `src/app.py:2` auth=none rate-limit=yes\n")[0], 0)

    def test_empty_inventory_needs_none(self):
        inv = "\n## Route inventory\n"
        self.assertIn("missing-route-inventory", self.rc(inv + "\n")[1])
        self.assertEqual(self.rc(inv + "- none\n")[0], 0)

    def test_inventory_prose_line_fails(self):
        self.assertIn("inventory-not-list", self.rc("\n## Route inventory\n- GET /a src/app.py:1 auth=none\nprose line\n")[1])

    def test_inventory_host_port_is_not_a_cite(self):
        self.assertEqual(self.rc("\n## Route inventory\n- GET /a src/app.py:1 calls host:8080\n")[0], 0)

    def test_bare_basename_prose_cite(self):
        self.assertIn("bad-citation", lint(report(extra="Path: a reaches fetch (app.py:2) on.\n"))[1])
        self.assertEqual(lint(report(extra="It calls example.com:443 only.\n"))[0], 0)


class HeredocContract(unittest.TestCase):
    def test_prose_and_heredoc(self):
        skill = LINT.parent.parent
        sec = (skill / "references/security-review-mode.md").read_text()
        self.assertIn("report_contract_lint.py - --root . <<'EOF'", sec)
        self.assertIn("Never write the draft to a file", sec)
        self.assertIn("final answer is that linted draft verbatim", sec)
        self.assertIn("never re-word, re-section, drop `[class]` labels", sec)
        self.assertIn("alone, with no `;`, `&&`, `for` loop, `cd X &&` chain or `VAR=` prefix", sec)
        self.assertIn("never a reason to skip the tool pass", sec)
        self.assertIn("the single-command rule of step 1 applies", sec)
        skill_md = (skill / "SKILL.md").read_text()
        self.assertIn("Paths are in this skill's base dir, not the repo.", skill_md)
        wp = (skill / "references/whole-project-report.md").read_text()
        for k in ("route_auth_map.py --all", "commit-line anchor is `csrf` only", "`missing-attempt-limit`", "`rate-limit` finding"):
            self.assertIn(k, wp)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
            draft = report(extra="\n## Findings\n- [other] src/app.py:1 low: y\n")
            cmd = f"python3 -I {LINT} - --root . <<'EOF'\n{draft}EOF\n"
            r = subprocess.run(["bash", "-c", cmd], cwd=d, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (0, PLAIN), r.stderr)


class ChunkedAndVocab(unittest.TestCase):
    def test_vocab_matches_classes(self):
        wp = (LINT.parent.parent / "references/whole-project-report.md").read_text()
        labels = re.search(r"Fixed class vocabulary: (.*?)\. Pick", wp, re.S).group(1)
        self.assertEqual(set(re.findall(r"`([a-z-]+)`(?=,|$| \()", labels)), runpy.run_path(str(LINT))["CLASSES"])

    def test_prose_slash_token_not_citation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
            r = subprocess.run([sys.executable, "-I", str(LINT), "-", "--root", d], input=report(extra="\nUses `net/http` and `text/html`, `gone/x.py:3` too.\n"), capture_output=True, text=True)
            self.assertIn("gone/x.py", r.stdout)
            self.assertNotIn("net/http", r.stdout)
            self.assertNotIn("text/html", r.stdout)
            r = subprocess.run([sys.executable, "-I", str(LINT), "-", "--root", d], input=report(extra="\nSee `net/http.Client` and `src/app.py#L3`.\n"), capture_output=True, text=True)
            self.assertNotIn("net/http", r.stdout)  # prose
            self.assertIn("src/app.py#L3", r.stdout)  # still parsed as a citation (flagged: #L form is not valid)

    def test_part_done(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
            run = lambda *a, i="": subprocess.run([sys.executable, "-I", str(LINT), *a, "--root", d], input=i, capture_output=True, text=True)
            draft = report(extra="\n## Findings\n- [other] src/app.py:1 low: y\n")
            cut = draft.index("## NOT CHECKED")
            a, b = run("--part", "1", i=draft[:cut]), run("--part", "2", i=draft[cut:])
            self.assertEqual((a.returncode, b.returncode), (0, 0))
            self.assertEqual(int(b.stdout), draft.count("\n"))
            r = run("--done")
            self.assertEqual((r.returncode, r.stdout), (0, OK), r.stderr)
            self.assertEqual(run("--done").returncode, 2)  # draft deleted
            run("--part", "1", i="junk stale\n")  # stale draft, then part 1 truncates it
            self.assertEqual(run("--part", "1", i=draft[:cut]).stdout.strip(), str(draft[:cut].count("\n")))
            run("--part", "2", i="## Bogus\nsafe to deploy\n")  # failing --done deletes; resend from part 1
            self.assertEqual(run("--done").returncode, 1)
            run("--part", "1", i=draft[:cut]), run("--part", "2", i=draft[cut:])
            self.assertEqual(run("--done").returncode, 0)

    def test_symlink_draft_refused(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as t:
            import hashlib
            draft = Path(tempfile.gettempdir()) / ("rcl-" + hashlib.sha256(str(Path(d).resolve()).encode()).hexdigest()[:16] + ".md")
            victim = Path(t) / "victim"
            victim.write_text("keep")
            draft.symlink_to(victim)
            try:
                r = subprocess.run([sys.executable, "-I", str(LINT), "--part", "1", "--root", d], input="x\n", capture_output=True, text=True)
                self.assertEqual((r.returncode, victim.read_text()), (2, "keep"))
            finally:
                draft.unlink()

    def test_extensionless_citation_rule(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/app.py").write_text("a\n")
            run = lambda t: subprocess.run([sys.executable, "-I", str(LINT), "-", "--root", d], input=report(extra=f"\nSee {t}.\n"), capture_output=True, text=True).stdout
            self.assertIn("src/Makefile", run("`src/Makefile`"))  # top dir exists, file missing
            self.assertNotIn("net/http", run("`net/http`"))
            self.assertNotIn("passwd", run("`../../etc/passwd`"))
            self.assertIn("escapes", run("`../x.py:3`"))

    def test_part_order_and_draft_safety(self):
        with tempfile.TemporaryDirectory() as d:
            import hashlib
            draft = Path(tempfile.gettempdir()) / ("rcl-" + hashlib.sha256(str(Path(d).resolve()).encode()).hexdigest()[:16] + ".md")
            run = lambda *a, i="x\n": subprocess.run([sys.executable, "-I", str(LINT), *a, "--root", d], input=i, capture_output=True, text=True)
            try:
                self.assertEqual(run("--part", "2").returncode, 2)  # N>1, no draft
                self.assertIn("--part 1", run("--part", "2").stderr)
                self.assertEqual(run("--part", "1").returncode, 0)
                self.assertEqual(run("--part", "3").returncode, 2)  # skipped
                self.assertEqual(run("--part", "2").returncode, 0)
                self.assertEqual(run("--part", "2").returncode, 2)  # duplicate
                draft.chmod(0o644)
                self.assertEqual(run("--part", "3").returncode, 2)  # not private
                self.assertEqual(run("--done").returncode, 2)
            finally:
                for f in (draft, Path(str(draft) + ".part")):
                    f.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
