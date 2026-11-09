"""review_checks.sh node-check: a .js file with JSX or markup (node --check: "Unexpected token '<'") is one not-checked row per run, never a SyntaxError; a plain syntax error in a .js file stays a SyntaxError row. Fictional fixtures; runs review_checks.sh on a throwaway git repo."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RC = ROOT / ".claude/skills/deep-code-review/scripts/review_checks.sh"
ENV = dict(os.environ)
JSX = "const Card = () => <div className=\"card\">hi</div>;\nexport default Card;\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@example.com", "-c", "user.name=Acme", *args],
                   check=True, capture_output=True, env=ENV)


def node_rows(files):
    with tempfile.TemporaryDirectory() as t:
        repo = Path(t) / "r"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        git(repo, "branch", "base")
        for name, text in files.items():
            Path(repo, name).write_text(text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "files")
        r = subprocess.run(["bash", str(RC), "--base", "base"], cwd=repo, capture_output=True, text=True, env=ENV)
    return [x for x in json.loads(r.stdout) if x["tool"] == "node-check"]


class T(unittest.TestCase):
    def test_jsx_js_files_become_one_not_checked_row(self):
        rows = node_rows({"a.js": JSX, "b.js": JSX, "c.js": JSX, "d.js": JSX})
        self.assertEqual([(x["file"], x["line"], x["rule"]) for x in rows], [("a.js", 1, "not-checked")])
        self.assertEqual(rows[0]["message"], "4 .js files hold JSX or markup that node --check cannot parse (first 3: a.js, b.js, c.js); a JSX-aware linter or the project build judges them")

    def test_single_jsx_file_row_names_it(self):
        rows = node_rows({"view.js": JSX})
        self.assertEqual([(x["file"], x["rule"]) for x in rows], [("view.js", "not-checked")])
        self.assertTrue(rows[0]["message"].startswith("1 .js files hold JSX"), rows[0]["message"])
        self.assertIn("(first 3: view.js)", rows[0]["message"])

    def test_plain_syntax_error_in_js_is_still_syntax_error(self):
        rows = node_rows({"bad.js": "let = = 1;\n", "view.js": JSX})
        self.assertEqual(sorted((x["file"], x["rule"]) for x in rows), [("bad.js", "SyntaxError"), ("view.js", "not-checked")])

    def test_plain_bad_js_alone_has_no_not_checked_row(self):
        rows = node_rows({"bad.js": "let = = 1;\n"})
        self.assertEqual([(x["file"], x["rule"]) for x in rows], [("bad.js", "SyntaxError")])

    def test_angle_bracket_cast_without_closing_tag_is_syntax_error(self):
        rows = node_rows({"cast.js": "const x = <T>y;\n"})
        self.assertEqual([(x["file"], x["rule"]) for x in rows], [("cast.js", "SyntaxError")])

    def test_jsx_then_later_error_is_not_checked_only(self):
        rows = node_rows({"mixed.js": JSX + "let = = 1;\n"})
        self.assertEqual([(x["file"], x["rule"]) for x in rows], [("mixed.js", "not-checked")])


if __name__ == "__main__":
    unittest.main()
