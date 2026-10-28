#!/usr/bin/env python3
"""wired_check.py BASE HEAD [--root DIR] — warn when a NEW script has no caller.

WHY: tooling was built (train scripts, a reaper, browser-worker settings) and nothing called it, so it
never ran. For every file ADDED between BASE and HEAD directly under `scripts/` or `*/scripts/` (test
files `test_*` / `test-*` excluded), require at least one caller at HEAD: a JSON config (hook/settings
template, package.json), CI workflow (.yml/.yaml), Makefile, command .md, another non-test script, or a
SKILL.md / references .md line in a run context (python3, bash, sh, `./`, "run"). The script itself, its own
tests, generated indexes, changelogs, checksums and evals do not count; a script referenced only from its own
test is unwired.
Prints `WARN: <path> has no caller` per unwired script. WARN-ONLY unless --strict: exits 0 (exit 2 on usage/git error).
`--strict --runs FILE [--runs FILE...]` (hand-back/CI mode): exit 1 when any new script is unwired OR its exact basename token appears in none of
the observed-run record FILEs (CI passes the registered test files, which run the script every build); a missing FILE exits non-zero even with no new script. Limits: matches on the file's basename; a caller built by string concatenation is missed (false WARN).
"""
import os
import re
import subprocess
import sys

NEW_RE = re.compile(r"(^|/)scripts/[^/]+\.(py|sh)$")
TEST_RE = re.compile(r"(^|/)(test[_-][^/]*|[^/]*_test\.py)$")
CODE_EXT = (".json", ".yml", ".yaml", ".sh", ".py")
RUN_RE = re.compile(r"python3?\b|\bbash\b|\bsh\b|\./|\brun\b", re.I)
SKIP = ("INDEX.md", "CHANGELOG.md", "SHA256SUMS")


def git(root, *a, ok=(0,)):
    p = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)
    if p.returncode not in ok:
        sys.exit("wired_check: git %s failed: %s" % (a[0], p.stderr.strip()))
    return p.stdout


def counts(path, hits):
    """True when `path` is a caller kind that counts and `hits` (its lines naming the script) qualify."""
    base, low = os.path.basename(path), path.lower()
    if TEST_RE.search(path) or "/evals/" in path or base in SKIP or low.startswith("changelog.d/"):
        return False
    if base == "Makefile" or low.endswith(CODE_EXT):
        return True
    if low.endswith(".md") and (base == "SKILL.md" or low.startswith("commands/") or "/references/" in low):
        return any(RUN_RE.search(h) for h in hits)
    return False


def main(argv):
    root = "."
    if "--root" in argv:
        i = argv.index("--root")
        root = argv[i + 1]
        del argv[i:i + 2]
    strict = "--strict" in argv
    argv = [x for x in argv if x != "--strict"]
    runs = []
    while "--runs" in argv:
        i = argv.index("--runs")
        runs.append(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) != 2 or (strict and not runs):
        sys.exit("usage: wired_check.py BASE HEAD [--root DIR] [--strict --runs FILE ...]")
    ran = ""
    for r in runs if strict else ():
        try:
            ran += open(r, errors="replace").read() + "\n"
        except OSError as e:  # fail closed even when no script was added: a missing record is not "nothing ran"
            sys.exit("wired_check: run record %s unreadable: %s" % (r, e))
    base, head = argv
    added = [f for f in git(root, "diff", "--name-only", "--diff-filter=A", "%s...%s" % (base, head)).split("\n")
             if NEW_RE.search(f) and not TEST_RE.search(f)]
    unwired = unrun = 0
    for s in added:
        name = os.path.basename(s)
        # -I skips binaries; exit 1 = no match
        out = git(root, "grep", "-I", "-F", "-n", "-e", name, head, "--", ok=(0, 1))
        by_file = {}
        for line in out.split("\n"):
            parts = line.split(":", 3)  # head:path:lineno:text
            if len(parts) == 4 and parts[1] != s:
                by_file.setdefault(parts[1], []).append(parts[3])
        if not any(counts(f, h) for f, h in by_file.items()):
            unwired += 1
            print("WARN: %s has no caller (hook/settings, CI, command, package.json, Makefile, script, "
                  "or a run line in SKILL.md/references)" % s)
        if strict and not re.search(r"(?<![\w.-])%s(?![\w.-])" % re.escape(name), ran):
            unrun += 1
            print("FAIL: %s has no observed run record in %s" % (s, ", ".join(runs)))
    print("wired_check: %d new script(s), %d unwired%s" % (len(added), unwired, ", %d never run" % unrun if strict else " (warn-only)"))
    return 1 if strict and (unwired or unrun) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
