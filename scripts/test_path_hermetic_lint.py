#!/usr/bin/env python3
"""Tests for path_hermetic_lint.py: a bare path-word negative grep fails, a $ROOT-stripped or non-path one passes, a baselined one is exempt; the repo is clean."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import path_hermetic_lint as p  # noqa: E402

BAD = '! grep -Eq "node_modules|worktrees|vendor" "$LOG"\n'
GOOD = 'sed "s|$ROOT||g" "$LOG" >"$LOG.rel"\n! grep -Eq "worktrees" "$LOG.rel"\n'


def tree(body, baseline=""):
    d = Path(tempfile.mkdtemp())
    (d / "scripts").mkdir()
    (d / "scripts/path-hermetic-baseline.tsv").write_text(baseline)
    (d / "scripts/test-x.sh").write_text(body)
    return str(d)


class Lint(unittest.TestCase):
    def test_bad_fixture_fails(self):
        self.assertEqual(p.lint(tree(BAD)), (["scripts/test-x.sh:1"], []))

    def test_reviewer_cases_fail(self):
        for body in (
            '! grep -q fatal "$L"; ! grep -q worktrees "$L"\n',  # 2nd grep on a line
            '! grep -q "unterminated worktrees "$L\n',  # unbalanced quote
            '! grep -qE -e worktrees "$L"\n',  # -e not last
            '! grep -m 1 -A 2 worktrees "$L"\n',  # -m N / -A N
            '! grep --regexp=worktrees "$L"\n',
            '! grep -eworktrees "$L"\n',
            '! grep -qeworktrees "$L"\n',  # glued combined flags
            'sed "s|$ROOT||g" "$LOG" >"$LOG2"\n! grep -q worktrees "$LOG"\n',  # sed writes $LOG2, not $LOG
            'sed "s|$ROOT||g" "$LOG" | tee x\n! grep -q worktrees "$LOG"\n',  # read-only sed
            'sed "s|$ROOT||g" "$A" >"$A.rel"\n! grep -q worktrees "$L"\n',  # sed unrelated to the input
            'sed "s|$ROOT||g" "$A" >"$A.rel"; cat "$B" >"$L"\n! grep -q worktrees "$L"\n',  # strip into another file, raw copy into the input
        ):
            self.assertEqual(p.lint(tree(body))[0], ["scripts/test-x.sh:%d" % (body.count("\n"))], body)

    def test_good_fixture_passes(self):
        self.assertEqual(p.lint(tree(GOOD)), ([], []))
        loop = 'cat "$A" | while IFS= read -r l; do printf "%s\\n" "${l//"$ROOT"/}"; done >"$L"\n! grep -q worktrees "$L"\n'
        self.assertEqual(p.lint(tree(loop)), ([], []))  # strip in a loop body, redirect after done
        self.assertEqual(p.lint(tree('! grep -q "$ROOT" "$L"; ! grep -q fatal "$L"\n# ! grep -q worktrees "$L"\n')), ([], []))

    def test_baseline_exempts_then_goes_stale(self):
        k = "scripts/test-x.sh\t" + BAD.strip() + "\n"
        self.assertEqual(p.lint(tree(BAD, k)), ([], []))
        self.assertEqual(p.lint(tree(GOOD, k)), ([], [k.strip()]))
        # a new offender in a baselined file is not covered by the row
        self.assertEqual(p.lint(tree(BAD + '! grep -q home "$L"\n', k)), (["scripts/test-x.sh:2"], []))

    def test_missing_baseline_fails_closed(self):
        r = tree(GOOD)
        os.remove(os.path.join(r, "scripts/path-hermetic-baseline.tsv"))
        with self.assertRaises(OSError):
            p.lint(r)

    def test_repo_is_clean(self):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/path_hermetic_lint.py"), str(ROOT)], capture_output=True, text=True,
                           env={"PATH": os.environ["PATH"]})
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
