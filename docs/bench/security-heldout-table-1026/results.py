#!/usr/bin/env python3
"""Regenerate docs/bench/security-heldout-table-1026/table.md: every blind held-out security corpus scored against ported rivals.

Usage: python3 -I docs/bench/security-heldout-table-1026/results.py > docs/bench/security-heldout-table-1026/table.md
Offline, deterministic, nothing executed (guard commands are only classified), $0. Needs the git history of this repo
(`git archive` of the pinned commits below); exits 2 if a pinned commit is missing (shallow clone).

Perun at authoring = the secret gate (`ci-gates.sh privacy`, the real union gate) and the destructive guard exactly as
extracted from the parent of the commit that added the corpus. Perun now = the same two tools at NOW (in-sample: later waves
were written against these rows, so only the authoring column is evidence). Rivals are the ported rules of
security-gates-1024/rivals/score_rivals.py (gitleaks v8.30.1; hooks-mastery; a SUBSET port of claude-code-safety-net, whose
unported rows count as neither block nor miss, so its recall is a lower bound).
"""
import concurrent.futures as cf, hashlib, importlib.util, math, pathlib, subprocess, sys, tempfile

D = pathlib.Path(__file__).resolve().parent
BENCH = D.parent
ROOT = BENCH.parents[1]
ONLY = sys.argv[1:]  # optional corpus dirs: print only those table rows (the test's fast sample)
NOW = "1db5ddf06"  # origin/main when this table was built
GUARD = ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
# corpus dir -> parent of the commit that added it (the rules the blind author's corpus met)
BASE = {
    "security-gates-heldout-1024": "de6635006", "security-gates-heldout2-1024": "c3f14095a", "security-gates-heldout3-1024": "9e22d2ae2",
    "security-gates-heldout4-1025": "e42fed4a7", "security-gates-heldout5-1025": "e42fed4a7", "security-gates-heldout6-1025": "352be0329",
    "security-gates-heldout7-1025": "352be0329", "security-gates-heldout8-1025": "352be0329", "security-gates-heldout9-1025": "49162c7b0",
    "security-gates-heldout10-1025": "d83e8f53a", "security-gates-heldout11-1025": "8eb9fc0d5", "security-gates-heldout12-1025": "7453990b1",
    "security-gates-heldout13-1025": "7453990b1", "security-gates-heldout14-1025": "27b57d18d", "security-gates-heldout15-1025": "27b57d18d",
    "security-gates-heldout17-1025": "cda0f9105", "security-gates-heldout18-1025": "cda0f9105", "security-gates-heldout19-1025": "12b481ebd",
    "security-gates-heldout20-1025": "12b481ebd", "security-gates-heldout21-1025": "7cfb7c263", "security-gates-heldout22-1025": "82d79503a",
    "security-gates-heldout24-1026": "ea5734712",
    "secrets-heldout4-1025": "576f9915d", "secrets-heldout5-1025": "576f9915d", "secrets-heldout6-1025": "576f9915d",
    "secrets-heldout7-1025": "6c5701e8f", "secrets-heldout8-1025": "6c5701e8f", "secrets-heldout9-1025": "12b481ebd",
    "secrets-heldout10-1025": "7cfb7c263", "secrets-heldout11-1025": "7cfb7c263", "secrets-heldout12-1025": "82d79503a",
    "secrets-heldout14-1026": "82d79503a", "secrets-heldout15-1026": "ea5734712", "secrets-heldout16-1026": "4aeb11c05",
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def tree(sha, tmp):
    """Extract the gate, the guard and the banlist at `sha` into tmp/sha; returns the path."""
    t = pathlib.Path(tmp) / sha; t.mkdir()
    a = subprocess.run(["git", "-C", str(ROOT), "archive", sha, "scripts", ".banlist.txt", GUARD], capture_output=True)
    if a.returncode: sys.exit(f"missing commit {sha} (shallow clone?): {a.stderr.decode()[:200]}")
    subprocess.run(["tar", "-x", "-C", str(t)], input=a.stdout, check=True)
    return t


def rows(d, name):
    f = BENCH / d / name
    return [l for l in f.read_text().splitlines() if l and not l.startswith("#")] if f.exists() else []


def secrets(d):
    p = lambda n: [l.split("\t", 1)[1].replace("@@", "") for l in rows(d, n)]
    return p("secret-leaks.txt"), p("secret-decoys.txt")


def drifted(d):
    """True when a frozen file's sha256 differs from the last line naming it in SHA256-frozen.txt (disclosed post-freeze amendment)."""
    want = {}
    for l in (BENCH / d / "SHA256-frozen.txt").read_text().splitlines():
        p = l.split()
        if len(p) == 2 and len(p[0]) == 64 and p[1].endswith(".txt"): want[p[1]] = p[0]
    return any(hashlib.sha256((BENCH / d / f).read_bytes()).hexdigest() != h for f, h in want.items() if (BENCH / d / f).exists())


def gate(t, texts):
    """Real union gate (ci-gates.sh privacy) at tree t: True per text if flagged."""
    def one(i):
        f = pathlib.Path(tempfile.mkdtemp(dir=t)) / "x.txt"; f.write_text(texts[i] + "\n")
        return subprocess.run(["bash", str(t / "scripts/ci-gates.sh"), "privacy", "--banlist", str(t / ".banlist.txt"), str(f)],
                              cwd=t, capture_output=True).returncode != 0
    with cf.ThreadPoolExecutor(8) as ex: return list(ex.map(one, range(len(texts))))


def cp(k, n, a=0.05):
    """Exact Clopper-Pearson (1-a) interval for k of n, by bisection on binomial tails."""
    pmf = lambda i, p: math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + (i * math.log(p) if i else 0) + ((n - i) * math.log1p(-p) if n - i else 0))
    cdf = lambda x, p: sum(pmf(i, p) for i in range(x + 1))
    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if f(m) else (lo, m)
        return lo
    return (0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) < a / 2), 1.0 if k == n else solve(lambda p: cdf(k, p) > a / 2))


def sign_p(b, c):
    """Exact two-sided sign-test p over the b+c discordant rows."""
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def fmt_p(p): return "<0.0001" if p < 1e-4 else f"{p:.4f}"


def pct(k, n): return f"{100 * k / n:.1f}%"
def ci(k, n): lo, hi = cp(k, n); return f"{pct(k, n)} [{100 * lo:.1f}, {100 * hi:.1f}]"


def main():
    sr = load(BENCH / "security-gates-1024/rivals/score_rivals.py", "sr")
    with tempfile.TemporaryDirectory() as tmp:
        trees = {}
        T = lambda s: trees[s] if s in trees else trees.setdefault(s, tree(s, tmp))
        guard = {}
        def dg(s):
            if s not in guard: guard[s] = load(T(s) / GUARD, "dg" + s)
            return guard[s]
        out, amended = [], []
        # per-kind accumulators: hits over blind-at-authoring rows
        acc = {k: dict(n=0, nb=0, a=0, fa=0, r=0, fr=0, r2=0, fr2=0, b=0, c=0, bf=0, cf=0) for k in ("secrets", "guard")}
        for d in (d for d in sorted(BASE, key=lambda d: (d.startswith("security-gates"), int("".join(c for c in d.split("-")[-2] if c.isdigit()) or 1), d)) if not ONLY or d in ONLY):
            base = BASE[d]
            if drifted(d): amended.append(d)
            if rows(d, "secret-leaks.txt"):
                lk, dc = secrets(d)
                ga, gn = gate(T(base), lk + dc), gate(T(NOW), lk + dc)
                ra = [bool(sr.gitleaks_rule(t)) for t in lk + dc]
                n, nb = len(lk), len(dc)
                A, N, R = ga, gn, ra
                a, an, r = sum(A[:n]), sum(N[:n]), sum(R[:n])
                fa, fn, fr = sum(A[n:]), sum(N[n:]), sum(R[n:])
                out.append((d, "secrets", base, f"{a}/{n}", f"{an}/{n}", f"gitleaks {r}/{n}", f"{fa} / {fn} / {fr} of {nb}"))
                x = acc["secrets"]
                x["n"] += n; x["nb"] += nb; x["a"] += a; x["fa"] += fa; x["r"] += r; x["fr"] += fr
                x["b"] += sum(A[i] and not R[i] for i in range(n)); x["c"] += sum(R[i] and not A[i] for i in range(n))
            if rows(d, "destructive-dangerous.txt"):
                dang = [l.split("\t", 1)[-1] for l in rows(d, "destructive-dangerous.txt")]
                ben = [l.split("\t", 1)[-1] for l in rows(d, "destructive-benign.txt")]
                n, nb = len(dang), len(ben)
                ga, gn = dg(base), dg(NOW)
                A = [bool(ga.check(c)) for c in dang + ben]; N = [bool(gn.check(c)) for c in dang + ben]
                sn = [sr.analyze(c) for c in dang + ben]
                S = [s == sr.B for s in sn]; H = [bool(sr.hooks_mastery(c)) for c in dang + ben]
                un = sum(s == sr.U for s in sn[:n])
                a, an, r, r2 = sum(A[:n]), sum(N[:n]), sum(S[:n]), sum(H[:n])
                fa, fn, fr, fr2 = sum(A[n:]), sum(N[n:]), sum(S[n:]), sum(H[n:])
                u = f", {un} unported" if un else ""
                out.append((d, "guard", base, f"{a}/{n}", f"{an}/{n}", f"safety-net {r}/{n}{u}; hooks-mastery {r2}/{n}",
                            f"{fa} / {fn} / {fr}; {fr2} of {nb}"))
                x = acc["guard"]
                x["n"] += n; x["nb"] += nb; x["a"] += a; x["fa"] += fa; x["r"] += r; x["fr"] += fr; x["r2"] += r2; x["fr2"] += fr2
                ok = [sn[i] != sr.U for i in range(n)]  # unported rows are neither block nor miss: out of the paired test
                x["b"] += sum(A[i] and not S[i] and ok[i] for i in range(n)); x["c"] += sum(S[i] and not A[i] for i in range(n))
    if ONLY: print("\n".join(f"| {d} | {k} | `{b}` | {a} | {n} | {r} | {f} |" for d, k, b, a, n, r, f in out)); return
    L = ["# Security held-out table, 2026-10-26", "",
         "Generated by `results.py` (offline, $0, byte-identical on rerun). Corpus rows are read from this tree; Perun at authoring and Perun now are the real secret gate (`ci-gates.sh privacy`) and destructive guard extracted from git at the pinned commits.", "",
         f"Perun now = commit `{NOW}`, and its rules were written against these rows, so that column is in-sample and is NOT evidence. The authoring column is the only evidence: the rules as they stood at the parent of the commit that added the corpus, which a blind author did not read. Rivals are ported rules, not binaries (see `../security-gates-1024/rivals/SOURCES.md`); the safety-net port is a subset, so its recall is a lower bound.", "",
         "| Corpus | Kind | Authoring base | Perun at authoring | Perun now (in-sample) | Rival | FP (authoring / now / rival) |", "|---|---|---|---|---|---|---|"]
    L += [f"| {d} | {k} | `{b}` | {a} | {n} | {r} | {f} |" for d, k, b, a, n, r, f in out]
    L += ["", "## Pooled, blind at authoring (the evidence)", "",
          "Recall with exact 95% Clopper-Pearson intervals; the paired p is an exact two-sided sign test on rows where exactly one of Perun and the rival hit (safety-net rows it left unported are excluded from the pairs). Rows are treated as independent, which they are not (corpora share an author and style), so the intervals are optimistic.", "",
          "| Kind | Rows | Perun recall at authoring | Rival recall | Perun-only / rival-only hits | Paired p | Perun FP | Rival FP |", "|---|---|---|---|---|---|---|---|"]
    for k, rival in (("secrets", "gitleaks"), ("guard", "safety-net (lower bound)")):
        x = acc[k]
        L.append(f"| {k} | {x['n']} leaks/dangerous, {x['nb']} decoys/benign | {x['a']}/{x['n']} = {ci(x['a'], x['n'])} | {rival} {x['r']}/{x['n']} = {ci(x['r'], x['n'])} | {x['b']} / {x['c']} | {fmt_p(sign_p(x['b'], x['c']))} | {x['fa']}/{x['nb']} = {ci(x['fa'], x['nb'])} | {x['fr']}/{x['nb']} = {ci(x['fr'], x['nb'])} |")
    x = acc["guard"]
    L += ["", f"Guard rival hooks-mastery (ported exactly): {x['r2']}/{x['n']} = {ci(x['r2'], x['n'])}, FP {x['fr2']}/{x['nb']}."]
    if amended: L += ["", "Corpus files amended after freezing (hash differs from the last SHA256-frozen.txt line; disclosed in each ledger): " + ", ".join(amended) + "."]
    L += ["", "Caveats: (1) Authoring base is the parent of the squashed commit that added the corpus, so corpora added in one commit share a base, and a corpus may have been authored a little earlier than its base. (2) Every README declares its corpus blind (authored without reading the scanner or guard); that is the author's own statement and was not re-verified. (3) Perun's rules changed between corpora, so the pool is a sequence of different rule sets, each blind to its own corpus but not to earlier ones; later corpora benefit from fixes made on earlier ones. Read per corpus: Perun trailed gitleaks on the first three secrets corpora and led on every later one. (4) Rival ports are not the rival binaries. (5) No corpus directory exists in this tree for secrets held-out 13, or guard held-out 16 and 23, so they are not scored here (CHANGELOG.md names a secrets held-out-13, but its files are not committed); no reason beyond that is claimed."]
    print("\n".join(L))


if __name__ == "__main__":
    main()
