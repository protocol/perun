#!/usr/bin/env python3
"""hermetic_env_lint.py - a test that exercises a host-reading script must pin or scrub the host env it does not own.

WHY: scripts that read the machine (core count, load average, idle CPU) give a test different answers on a 4-core laptop,
an 88-vCPU runner and a sandbox; a test that shells out to or imports one without pinning (PERUN_GATE_CORES / PERUN_GATE_LOAD1,
an explicit `env=`, `env -i`, `unset`, `export`, or `scrub_env.sh`) passes on the author's host and fails elsewhere.
A script is host-reading when its source calls os.cpu_count / getloadavg / read_load1 / nproc. A test file naming one must carry
a pin marker. Existing offenders are frozen in scripts/hermetic-env-baseline.tsv (ratchet: a new unpinned test fails; fixing
one means deleting its row, and a row whose file now passes also fails so the baseline only shrinks).
Usage: hermetic_env_lint.py [root]. Exit 0 clean, 1 on a violation. Side effects: none.
"""
import glob
import os
import re
import sys
from pathlib import Path

HOST = re.compile(r"os\.cpu_count|getloadavg|read_load1|\bnproc\b")
PIN = re.compile(r"PERUN_GATE_CORES|PERUN_GATE_LOAD1|\benv\s*=|env -i|\bunset\b|\bexport\b|scrub_env|os\.environ\[")


def lint(root="."):
    """Return (new_violations, stale_baseline_rows) as sorted lists of repo-relative paths."""
    j = lambda *a: os.path.join(root, *a)  # noqa: E731
    prod = [p for p in glob.glob(j(".claude/skills/*/scripts/*.py")) + glob.glob(j("scripts/*.py"))
            if not os.path.basename(p).startswith("test_")]
    host = [os.path.basename(p) for p in prod if HOST.search(Path(p).read_text(encoding="utf-8"))]
    tests = glob.glob(j("scripts/test_*.py")) + glob.glob(j("scripts/test-*.sh")) + glob.glob(j(".claude/skills/*/scripts/test_*.py"))
    base = set()
    with open(j("scripts/hermetic-env-baseline.tsv"), encoding="utf-8") as f:  # missing baseline = fail closed (raises)
        base = {l.strip() for l in f if l.strip() and not l.startswith("#")}
    bad = set()
    for t in tests:
        s = Path(t).read_text(encoding="utf-8")
        code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))  # a comment is not a pin
        if any(h in s or h[:-3] in s for h in host) and not PIN.search(code):
            bad.add(os.path.relpath(t, root))
    return sorted(bad - base), sorted(base - bad)


def main(argv):
    new, stale = lint(argv[1] if len(argv) > 1 else ".")
    for p in new:
        print(f"hermetic_env_lint: {p} uses a host-reading script without pinning host env (PERUN_GATE_CORES/LOAD1, env=, scrub_env.sh)", file=sys.stderr)
    for p in stale:
        print(f"hermetic_env_lint: {p} is now pinned (or gone): delete its row from scripts/hermetic-env-baseline.tsv", file=sys.stderr)
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
