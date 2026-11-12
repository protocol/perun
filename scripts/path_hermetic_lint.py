#!/usr/bin/env python3
"""path_hermetic_lint.py - a negative grep for a path-segment word is not hermetic: the checkout path is part of every absolute path in a log.

WHY: `! grep -E 'worktrees' "$LOG"` passes in CI (checkout /home/runner/work/...) but fails in a lane worktree
(/repo/.claude/worktrees/lane/...), because the scanner argv/log holds absolute paths that contain the word.
Flags, in scripts/test-*.sh, every `! grep` command segment (a line is split on ; && || | outside quotes) whose literal,
non-$var text holds a bare path-segment word (worktrees, Desktop, Users, home, tmp, var, ...) as a whole word, unless the
grep's input (its last arg) is written, on that line or the one before, by a sed/`${x//...}`/replace that uses $ROOT/$PWD.
Existing offenders are frozen in scripts/path-hermetic-baseline.tsv (`path<TAB>stripped line text`; a row whose line no longer
flags also fails, so the baseline only shrinks). Usage: path_hermetic_lint.py [root]. Exit 0 clean, 1 on a violation.
Side effects: none. Edge case: a pattern built from a variable is not seen (false negative, accepted).
"""
import glob
import os
import re
import sys
from pathlib import Path

WORDS = {"worktree", "worktrees", "desktop", "users", "home", "tmp", "private", "var", "checkout", "deep-code-review", "documents"}
STRIP = re.compile(r"(\bsed\b|\$\{[^}]*//|\breplace\b)")
ROOTS = re.compile(r"\$\{?(ROOT|PWD|REPO\w*|CHECKOUT\w*|SRC)\b|\$\(pwd\)|\$\(git rev-parse --show-toplevel\)")


def segments(line):
    """Split a shell line on ; && || | outside quotes."""
    out, cur, q, i = [], "", "", 0
    while i < len(line):
        c = line[i]
        if q:
            q = "" if c == q else q
        elif c in "\"'":
            q = c
        elif (c == "|" and cur.endswith(">")) is False and c in ";|" or (c == "&" and line[i:i + 2] == "&&"):
            out.append(cur)
            cur = ""
            i += 2 if line[i:i + 2] in ("&&", "||") else 1
            continue
        cur += c
        i += 1
    return out + [cur]


def hit_words(seg):
    """Return the WORDS found as whole words in the literal (non-$var) text of a `! grep` segment, else []."""
    seg = seg.strip()
    if not re.match(r"!\s+grep\b", seg):
        return []
    lit = re.sub(r"\$\{[^}]*\}|\$\([^)]*\)|\$\w+", " ", seg).lower()
    lit = re.sub(r"(?<=\s)-[a-z]*?e(?=\w)", r"\g<0> ", lit)  # -ePATTERN / -qePATTERN glue
    return [w for w in WORDS if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", lit)]


def exempt(seg, lines):
    """True if a non-grep segment on this or the previous line has STRIP and ROOTS and redirects (> f, >f, >| f) exactly into the grep's input file (last arg, quotes stripped)."""
    f = seg.split()[-1].strip("\"'")
    for l in lines:
        for s in segments(l):
            if s.strip().startswith("! grep") or not (STRIP.search(s) and ROOTS.search(s)):
                continue
            if any(t.strip("\"'") == f for t in re.findall(r"(?<![>&\d])>\|?\s*(\"[^\"]*\"|'[^']*'|[^\s;&|]+)", s)):
                return True
    return False


def lint(root="."):
    """Return (new, stale): new = `path:line` of unexempt hits whose `path<TAB>text` key is not in the baseline, stale = baseline keys that no longer hit."""
    with open(os.path.join(root, "scripts/path-hermetic-baseline.tsv"), encoding="utf-8") as f:  # missing = fail closed
        base = {l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")}
    hits = {}
    for p in sorted(glob.glob(os.path.join(root, "scripts/test-*.sh"))):
        rel = os.path.relpath(p, root)
        ls = Path(p).read_text(encoding="utf-8").splitlines()
        for n, l in enumerate(ls):
            if l.lstrip().startswith("#"):
                continue
            for seg in segments(l):
                if hit_words(seg) and not exempt(seg, [l] + ls[n - 1:n]):
                    hits[f"{rel}\t{l.strip()}"] = f"{rel}:{n + 1}"
    return sorted(v for k, v in hits.items() if k not in base), sorted(base - set(hits))


def main(argv):
    new, stale = lint(argv[1] if len(argv) > 1 else ".")
    for k in new:
        print(f"path_hermetic_lint: {k} has a `! grep` for a path-segment word that is also in the checkout path; strip $ROOT/$PWD first (sed \"s|$ROOT||g\")", file=sys.stderr)
    for k in stale:
        print(f"path_hermetic_lint: baseline row no longer flags (delete it from scripts/path-hermetic-baseline.tsv): {k.replace(chr(9), ' :: ')}", file=sys.stderr)
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
