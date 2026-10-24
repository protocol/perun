#!/usr/bin/env python3
"""Score Perun's secret gate and destructive guard on the frozen synthetic corpora in this directory.

Offline and deterministic: no network, no model calls, nothing is executed (commands are only classified).
Usage: python3 docs/bench/security-gates-1024/score.py [--corpus-dir DIR]   (DIR holds the corpora and a README.md with SHA256 lines; run from the repo root; exit 1 on any hash drift)
Corpus files: tab-separated `name<TAB>text` (secrets) or one command per line; `#` lines are comments; `@@`
inside a secret line is a marker deleted before scoring so the files never trip the repo privacy gate.
"""
import hashlib, importlib.util, pathlib, subprocess, sys, tempfile

D = pathlib.Path(sys.argv[sys.argv.index("--corpus-dir") + 1]).resolve() if "--corpus-dir" in sys.argv else pathlib.Path(__file__).resolve().parent
ROOT = D.parents[2]
GATES = ROOT / "scripts" / "ci-gates.sh"
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"


def rows(name):
    return [l for l in (D / name).read_text().splitlines() if l and not l.startswith("#")]


def sha_ok():
    """Compare corpus hashes with SHA256 lines in README.md; returns the list of drifted files."""
    want = {}
    for l in (D / "README.md").read_text().splitlines():
        p = l.split()
        if len(p) == 2 and len(p[0]) == 64 and p[1].endswith(".txt"):
            want[p[1]] = p[0]
    return [f for f, h in want.items() if hashlib.sha256((D / f).read_bytes()).hexdigest() != h] or (
        [] if want else ["README.md has no sha256 lines"])


def secret_flagged(tmp, text):
    f = pathlib.Path(tmp) / "x.txt"
    f.write_text(text + "\n")
    r = subprocess.run(["bash", str(GATES), "privacy", "--banlist", str(pathlib.Path(tmp) / ".banlist.txt"), str(f)],
                       capture_output=True, text=True)
    return r.returncode != 0


def main():
    bad = sha_ok()
    if bad:
        print("HASH DRIFT:", bad); return 1
    spec = importlib.util.spec_from_file_location("dg", GUARD); dg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dg)
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / ".banlist.txt").write_text((ROOT / ".banlist.txt").read_text())
        pick = lambda n: [(l.split("\t")[0], l.split("\t", 1)[1].replace("@@", "")) for l in rows(n)]
        leaks, decoys = pick("secret-leaks.txt"), pick("secret-decoys.txt")
        miss = [n for n, t in leaks if not secret_flagged(tmp, t)]
        fp = [n for n, t in decoys if secret_flagged(tmp, t)]
    print(f"secret gate: recall {len(leaks) - len(miss)}/{len(leaks)}  FP {len(fp)}/{len(decoys)}")
    print("  missed:", miss); print("  false positives:", fp)
    dang, ben = rows("destructive-dangerous.txt"), rows("destructive-benign.txt")
    dmiss = [c for c in dang if not dg.check(c)]
    dfp = [c for c in ben if dg.check(c)]
    print(f"destructive guard: blocked {len(dang) - len(dmiss)}/{len(dang)}  FP {len(dfp)}/{len(ben)}")
    print("  missed:", dmiss); print("  false positives:", dfp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
