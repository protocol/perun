#!/usr/bin/env python3
"""bg_admit.py - admission for background and shadow jobs, plus a lint for mktemp without a cleanup trap.

WHY: one unattended job filled /tmp with 56 GB because nothing bounded it. A background or shadow job is admitted only when
its script declares (1) `# disk-cap: <N>[K|M|G|T]` (N >= 1; a declared budget, not enforced at runtime), (2) a `trap ... EXIT` that removes what it made, and
(3) `# disk-stop: <rule>` with a free-space check (`df`, `disk_usage` or `statvfs`) compared against a threshold on one code line, so it stops under disk pressure.

  bg_admit.py admit SCRIPT...   exit 1 and one `bg_admit: REFUSE <file>: <missing>` line per script that lacks a declaration.
  bg_admit.py untrapped [ROOT] exit 1 on a shipped shell script that calls mktemp with no `trap` (new offender) or a row in
                                scripts/mktemp-trap-baseline.tsv whose file is now clean or gone (the baseline only shrinks).
  job_lease.py run --admit -- CMD   admits the script CMD actually runs (CMD[0], or CMD[1] after bash/sh/python3) before the lease is taken.
Side effects: none (read-only). A missing or unreadable file is a refusal (fail closed).
"""
import glob
import os
import re
import sys
from pathlib import Path

CAP = re.compile(r"#\s*disk-cap:\s*[1-9]\d*\s*[KMGT]?B?\b", re.I)
STOP_DECL = re.compile(r"#\s*disk-stop:\s*\S")
STOP_CODE = re.compile(r"(?:\bdf\s|disk_usage|statvfs).*(?:-lt|-le|-gt|-ge|<|>)|(?:-lt|-le|-gt|-ge|<|>).*(?:\bdf\s|disk_usage|statvfs)")
TRAP = re.compile(r"(?:^|[;&]\s*)\s*trap\s+[^\n]*\bEXIT\b", re.M)  # one regex for admit and the mktemp lint
TRAILING = re.compile(r"\s#[^'\"]*$")  # a trailing comment with no quote after it


def _code(s):
    return "\n".join(TRAILING.sub("", l) for l in s.splitlines() if not l.lstrip().startswith("#"))


def missing(path):
    """List of what the script at `path` fails to declare (empty = admitted)."""
    try:
        s = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return [f"unreadable ({e.strerror})"]
    out = []
    if not CAP.search(s):
        out.append("`# disk-cap: <N>[K|M|G|T]`")
    if not TRAP.search(_code(s)):
        out.append("`trap ... EXIT` cleanup")
    if not (STOP_DECL.search(s) and STOP_CODE.search(_code(s))):
        out.append("`# disk-stop: <rule>` plus a df/disk_usage check")
    return out


def shipped_shell(root="."):
    pats = [".claude/skills/*/scripts/**/*.sh", ".claude/skills/*/scripts/**/*.bash", "scripts/**/*.sh", "scripts/**/*.bash", ".githooks/**/*", "install.sh"]
    return sorted({os.path.relpath(p, root) for g in pats for p in glob.glob(os.path.join(root, g), recursive=True) if os.path.isfile(p)})


def mktemp_untrapped(root="."):
    """(new_offenders, stale_baseline_rows): shell files with a mktemp call but no `trap`."""
    bad = set()
    for rel in shipped_shell(root):
        try:
            code = _code(Path(root, rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bmktemp\b", code) and not TRAP.search(code):
            bad.add(rel)
    base = {l.strip() for l in Path(root, "scripts/mktemp-trap-baseline.tsv").read_text(encoding="utf-8").splitlines()  # missing = fail closed
            if l.strip() and not l.startswith("#")}
    return sorted(bad - base), sorted(base - bad)


def main(argv):
    if argv[:1] == ["admit"] and len(argv) > 1:
        rc = 0
        for p in argv[1:]:
            m = missing(p)
            if m:
                rc = 1
                print(f"bg_admit: REFUSE {p}: missing {', '.join(m)}", file=sys.stderr)
        return rc
    if argv[:1] == ["untrapped"]:
        new, stale = mktemp_untrapped(argv[1] if len(argv) > 1 else ".")
        for p in new:
            print(f"bg_admit: {p} calls mktemp without a `trap ... EXIT` cleanup", file=sys.stderr)
        for p in stale:
            print(f"bg_admit: {p} is now clean (or gone): delete its row from scripts/mktemp-trap-baseline.tsv", file=sys.stderr)
        return 1 if new or stale else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
