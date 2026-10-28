#!/usr/bin/env python3
"""freeze_gate.py BASE HEAD — while a freeze is on, allow only deletions and red-trunk fixes.

WHY: a freeze (release stabilisation, incident) that lives in a chat message is broken by the next lane. This makes it a
file the push/merge preflight reads, like DCR_HOLD but selective: removing code and fixing a red trunk stay possible.

Freeze is ON while `$PERUN_FREEZE` (a path) or `<git-common-dir>/PERUN_FREEZE` or a repo-root `.perun-freeze` exists; its first
line is the reason. Off -> exit 0 silently. On, BASE..HEAD is allowed when EITHER every changed file is a deletion
(`git diff --name-status BASE...HEAD` shows only `D`), OR a commit message in BASE..HEAD carries the line `Red-Trunk-Fix: <what
was red>` with a non-empty value. Otherwise prints `FROZEN: <reason>; only deletions and red-trunk fixes land` and exits 1.
An empty diff is allowed. Exit 2 on usage or git error (fail closed: a freeze that cannot be checked blocks). The trailer is
self-reported; the trunk's red state is the control (`red_main.py`). Side effects: none (read-only).
"""
import os
import re
import subprocess
import sys


def git(*a):
    p = subprocess.run(["git", *a], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"freeze_gate: git {a[0]} failed: {p.stderr.strip()}")
    return p.stdout


def freeze_file():
    env = os.environ.get("PERUN_FREEZE")
    cands = [env] if env else [os.path.join(git("rev-parse", "--git-common-dir").strip(), "PERUN_FREEZE"),
                               os.path.join(git("rev-parse", "--show-toplevel").strip(), ".perun-freeze")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def main(argv):
    if len(argv) != 2:
        print("usage: freeze_gate.py BASE HEAD", file=sys.stderr)
        return 2
    base, head = argv
    f = freeze_file()
    if not f:
        return 0
    reason = (open(f, errors="replace").readline().strip() if os.path.isfile(f) else "") or "(no reason given)"
    status = [ln.split("\t")[0][:1] for ln in git("diff", "--name-status", f"{base}...{head}").splitlines() if ln]
    if all(s == "D" for s in status):
        return 0
    if re.search(r"^Red-Trunk-Fix:[ \t]*\S", git("log", "--format=%B", f"{base}..{head}"), re.M):
        return 0
    print(f"FROZEN: {reason}; only deletions and red-trunk fixes land (a commit line `Red-Trunk-Fix: <what was red>`)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
