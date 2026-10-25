#!/usr/bin/env python3
"""Score the secret gate on held-out-3: Perun-union (the real privacy gate), Perun-banlist-only, and gitleaks alone.

Usage: python3 -I docs/bench/security-gates-heldout3-1024/score.py   (run from anywhere; offline, deterministic; exit 1 on hash drift)
Rows are `id<TAB>text`; `@@` markers are deleted before scoring. Union is the actual `ci-gates.sh privacy` run; it may only drop
hits of banlist OR gitleaks (the placeholder pass), which this script asserts; banlist and gitleaks columns are the raw rules.
"""
import hashlib, importlib.util, pathlib, subprocess, sys, tempfile

D = pathlib.Path(__file__).resolve().parent
ROOT = D.parents[2]
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
BAN = ROOT / ".banlist.txt"


def rows(name):
    return [(l.split("\t")[0], l.split("\t", 1)[1].replace("@@", "")) for l in (D / name).read_text().splitlines() if l and not l.startswith("#")]


def drift():
    """Files whose sha256 differs from the LAST line naming them in SHA256-frozen.txt (earlier lines are disclosed amendments)."""
    want = {p[1]: p[0] for p in (l.split() for l in (D / "SHA256-frozen.txt").read_text().splitlines() if not l.startswith("#"))}
    return [f for f, h in want.items() if hashlib.sha256((D / f).read_bytes()).hexdigest() != h]


def scores():
    pats = [l.lstrip() for l in BAN.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    out = {}
    with tempfile.TemporaryDirectory() as t:
        tp = pathlib.Path(t); (tp / ".banlist.txt").write_text(BAN.read_text())
        for name in ("secret-leaks.txt", "secret-decoys.txt"):
            res = {"union": [], "banlist": [], "gitleaks": []}
            for i, text in rows(name):
                f = tp / "x.txt"; f.write_text(text + "\n")
                u = subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(tp / ".banlist.txt"), str(f)],
                                   capture_output=True, text=True).returncode != 0
                b = any(subprocess.run(["grep", "-qE", "-e", p, str(f)]).returncode == 0 for p in pats)
                g = bool(ss.gitleaks_rule(text + "\n"))
                assert u <= (b or g or bool(set(ss.gitleaks_rule(text + "\n", precise=True)) & {r[0] for r in ss.EXTRA})), (i, u, b, g)  # the gate may drop raw hits (placeholder pass) or add only its EXTRA rules (secret_scan.py)
                for k, v in (("union", u), ("banlist", b), ("gitleaks", g)):
                    if v: res[k].append(i)
            out[name] = res
    return out


def main():
    if drift(): print("HASH DRIFT:", drift()); return 1
    s = scores(); n = {k: len(rows(k)) for k in s}
    for k in ("union", "banlist", "gitleaks"):
        lk, dc = s["secret-leaks.txt"][k], s["secret-decoys.txt"][k]
        print(f"{k}: recall {len(lk)}/{n['secret-leaks.txt']}  FP {len(dc)}/{n['secret-decoys.txt']}")
        print("  missed:", [i for i, _ in rows("secret-leaks.txt") if i not in lk]); print("  false positives:", dc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
