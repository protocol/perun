#!/usr/bin/env python3
"""Bench-integrity gate for docs/bench/<dir> (stdlib only).

Usage: bench_check.py [--changed [BASE]] [--against REF] [--allow FILE] [--max-overlap F] DIR...

Fails (exit 1, one line per problem) when a bench dir:
  a. has a scenario file (scenarios*.json, tickets*.json, or the file a PREREGISTERED*.md
     names as "Scenarios file: NAME.json") that is not a non-empty list of {"id": ...}
     objects (or {"scenarios": [...]}), repeats an id inside one file, scores the same
     id in tune and held (a driver that skips existing outputs then serves tune outputs
     as held), or ships a non-empty outputs/ file byte-identical to the same relative
     path in another docs/bench dir (stale reuse). A scenario is tune or held by its
     file name, else its "split" field, else its id containing "tune" or "held";
  b. has no ledger.jsonl line {"event": "preregistered", "sha256": H} where H (>= 12 hex)
     is a prefix of sha256 of the first k lines of SHA256-frozen.txt for some k (k = all
     lines is the plain file hash), that line precedes the first non-preregistered line,
     and its timestamp is not later than that line's. Each line after k (appended later)
     must have its file hash appear as a value in a later ledger event, else it is
     uncovered and fails. The canonical event is "preregistered" and the canonical key
     "sha256"; event "prereg_frozen" and keys "sha", "preregistered_sha256",
     "frozen_list_sha256" and "sha256_of_SHA256-frozen.txt" are accepted. Timestamps are
     "ts" or "iso" (epoch number or ISO-8601); an unparseable one fails, a missing one
     leaves line order as the only check;
  c. has a PREREGISTERED*.md naming a SHA256*.txt hash file that does not exist;
  d. has a scenario whose 10-word shingles overlap all other docs/bench dirs, or (held
     scenarios) the bench's own tune scenarios, by more than --max-overlap (default 0.2). --allow FILE (default DIR/overlap-allow.txt) lists
     template phrases, one per line, whose shingles are ignored;
  e. lists in SHA256-frozen.txt a file that is missing, or whose sha256 differs from its line's
     hash, or a line that is not "<sha256>  <path>". A path resolves from the repo root first
     (the sha256sum -c convention in the bench READMEs), then from the bench dir. Enforced by
     main(), not check(), so check() reports rules a-d only.
DIR/reuse-allow.txt (optional) lists outputs/ paths whose byte-identical reuse is
deliberate (e.g. a rival arm generated once and shared): an exact file path or a
directory (matches everything beneath it). Document why in PREREGISTERED.md.

Old benches lack ledgers, so only dirs named on the command line are checked; --changed
names the docs/bench dirs absent from BASE (default origin/main), so CI gates only new
benches; a missing BASE is an error. For a dir that BASE already holds, --changed fails only
when the diff since the merge base touches (edits, deletes or renames) SHA256-frozen.txt or a
listed file inside that dir. The list is read from BASE, so dropping it does not unfreeze its
inputs, and paths follow BASE's symlinks with every link counted, so a post-freeze driver edit
cannot ride into an old bench while notes, ledger appends and results still can. Listed files outside the dir
(shared scripts, SKILL.md) keep evolving; snapshot them into the bench dir to freeze them.

The disjointness corpus (rules a, d) is every other docs/bench dir in the working tree plus
every dir at --against REF (default origin/main when it exists) that the tree lacks, so a
bench that landed on REF after the branch point is still compared. A missing REF is an
error only when --against names it. REF dirs are read with git archive, no checkout.

Trust limits (this catches accidents, not a lane forging records): hashes are compared as
strings, so a frozen line rewritten to a hash that some later ledger event also contains
passes, and committed file bytes are not re-hashed against SHA256-frozen.txt. A single
scenario file with no tune/held file name, "split" field or tune/held id is treated as
unsplit, so no tune/held check runs on it. In a bench dir that already exists on BASE,
--changed gates only the frozen list and the frozen in-dir inputs (see above). Files a SHA256-frozen.txt line lists are re-hashed (rule e); files it never
lists are not.
"""
import argparse, collections, hashlib, io, json, os, re, subprocess, sys, tarfile, tempfile
from datetime import datetime, timezone
from pathlib import Path

N = 10
KEYS = ("sha256", "sha", "preregistered_sha256", "frozen_list_sha256", "sha256_of_SHA256-frozen.txt")
PREREG = ("preregistered", "prereg_frozen")
REPO = Path(__file__).resolve().parent.parent


def load(f):
    """Scenario list of f, or None when f is not a non-empty list of {"id"} objects."""
    try:
        data = json.loads(f.read_text())
    except ValueError:
        return None
    if isinstance(data, dict):
        data = data.get("scenarios")
    ok = isinstance(data, list) and data and all(isinstance(s, dict) and "id" in s for s in data)
    return data if ok else None


def scenario_files(d):
    """scenarios*.json, tickets*.json and the file a PREREGISTERED*.md names as "Scenarios file: X.json"."""
    named = {m for p in d.glob("PREREGISTERED*.md")
             for m in re.findall(r"scenarios? file\W*([\w.-]+\.json)", p.read_text(), re.I)}
    return sorted(f for f in d.glob("*.json") if f.name in named or re.match("scenarios|tickets", f.name))


def split(f, s):
    """'tune' or 'held' from the file name, the item's split field, or its id; else ''."""
    for t in (f, str(s.get("split", "")), str(s["id"])):
        for w in ("tune", "held"):
            if w in t.lower():
                return w
    return ""


def scenarios(d):
    """[(file, id, text, split)] for every scenario list in d."""
    return [(f.name, str(s["id"]), " ".join(str(v) for k, v in s.items() if k != "id"), split(f.name, s))
            for f in scenario_files(d) for s in load(f) or []]


def shingles(text):
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + N]) for i in range(len(w) - N + 1)}


def when(e):
    """Epoch seconds of an event's ts/iso; None when absent; ValueError when unparseable."""
    for k in ("ts", "iso"):
        v = e.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))  # ValueError/AttributeError on junk
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()
    return None


def strings(x):
    """Every string value nested in x."""
    if isinstance(x, str):
        yield x
    for v in x.values() if isinstance(x, dict) else x if isinstance(x, list) else ():
        yield from strings(v)


def ledger_errs(d):
    frozen, led = d / "SHA256-frozen.txt", d / "ledger.jsonl"
    if not frozen.is_file() or not led.is_file():
        return [f"{d}: SHA256-frozen.txt and ledger.jsonl are both required"]
    lines = frozen.read_bytes().splitlines(keepends=True)
    hs = [hashlib.sha256(b"".join(lines[:k])).hexdigest() for k in range(1, len(lines) + 1)]
    ev = []
    for n, l in enumerate(led.read_text().splitlines(), 1):
        if not l.strip():
            continue
        try:
            e = json.loads(l)
            assert isinstance(e, dict)
            e["_t"] = when(e)
        except (ValueError, AttributeError, AssertionError):
            return [f"{d}: ledger.jsonl line {n} is not a JSON object with a comparable ts/iso"]
        ev.append(e)

    def hit(e):  # k = number of frozen lines the event's hash covers; 0 = no match
        if e.get("event") not in PREREG:
            return 0
        return next((k for k, h in enumerate(hs, 1) for key in KEYS
                     if isinstance(e.get(key), str) and len(e[key]) >= 12 and h.startswith(e[key].lower())), 0)
    ks = {n: hit(e) for n, e in enumerate(ev)}
    pre = [n for n, k in ks.items() if k]
    gen = next((n for n, e in enumerate(ev) if e.get("event") not in PREREG), len(ev))
    if not pre:
        return [f"{d}: ledger.jsonl has no preregistered event matching a line-prefix hash of SHA256-frozen.txt"]
    p, g = ev[pre[0]], ev[gen:gen + 1]
    if pre[0] > gen or (g and p["_t"] is not None and g[0]["_t"] is not None and p["_t"] > g[0]["_t"]):
        return [f"{d}: preregistered event is not earlier than the first generation event"]
    later = [v.lower() for e in ev[pre[0] + 1:] for v in strings(e)]
    out = []
    for l in lines[ks[pre[0]]:]:  # lines appended after the prereg hash must be covered by a later event
        h = (l.decode(errors="replace").split() or [""])[0].lower()
        if h and not any(len(v) >= 12 and h.startswith(v) for v in later):
            out.append(f"{d}: SHA256-frozen.txt line {l.decode(errors='replace').strip()!r} is after the preregistered hash and not in any later ledger event")
    return out


def frozen_errs(d):
    """Rule e: every "<sha256>  <path>" line of SHA256-frozen.txt names a file that exists and still hashes to it.

    The path resolves from REPO first, then from d (sha256sum -c run from the repo root or the bench dir;
    a "../" path resolves from d only, so it never reaches outside the repo by way of REPO/..);
    the first base that holds the file is the one hashed. Reads only. No SHA256-frozen.txt gives no errors
    here (ledger_errs reports it). A line that is not "<64 hex>  <path>" is an error (fails closed).
    """
    f = d / "SHA256-frozen.txt"
    if not f.is_file():
        return []
    out = []
    for n, l in enumerate(f.read_text(errors="replace").splitlines(), 1):
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", l)
        if not m:
            out.append(f"{f}: line {n} is not '<sha256>  <path>'")
            continue
        p = m.group(2)
        hit = None if p.startswith("/") else next((c for c in in_repo(REPO / p, d / p) if c.is_file()), None)
        if hit is None:
            out.append(f"{f}: {p} is missing (tried the repo root and the bench dir)")
        elif hashlib.sha256(hit.read_bytes()).hexdigest() != m.group(1).lower():
            out.append(f"{f}: {p} changed after the freeze (sha256 differs)")
    return out


def check(d, others, allow=None, max_overlap=0.2):
    d, errs = Path(d), []
    # a. scenario files fail closed; tune/held id collision; cross-bench byte-identical outputs
    for f in scenario_files(d):
        data = load(f)
        if data is None:
            errs.append(f"{d}: {f.name} is not a non-empty list of scenarios with ids")
            continue
        all_ids = [str(s["id"]) for s in data]
        errs += [f"{d}: {f.name} repeats scenario id {i}" for i in sorted({i for i in all_ids if all_ids.count(i) > 1})]
    sc = scenarios(d)
    ids = {w: {i for _, i, _, sp in sc if sp == w} for w in ("tune", "held")}
    for i in sorted(ids["tune"] & ids["held"]):
        errs.append(f"{d}: scenario id {i} is in both tune and held")
    ra = d / "reuse-allow.txt"
    keep = [l.strip().rstrip("/") for l in ra.read_text().splitlines() if l.strip()] if ra.is_file() else []
    for o in sorted((d / "outputs").rglob("*")) if (d / "outputs").is_dir() else []:
        rel = o.relative_to(d).as_posix()
        if not o.is_file() or o.stat().st_size == 0 or any(rel == k or rel.startswith(k + "/") for k in keep):
            continue
        for x in others:
            p = x / rel
            if p.is_file() and p.read_bytes() == o.read_bytes():
                errs.append(f"{d}: {rel} is byte-identical to {p}")
    errs += ledger_errs(d)
    # c. hash files named by the prereg docs
    for p in d.glob("PREREGISTERED*.md"):
        for n in sorted(set(re.findall(r"SHA256[\w.-]*\.txt", p.read_text()))):
            if not (d / n).is_file():
                errs.append(f"{p}: names hash file {n}, which does not exist")
    # d. 10-word shingle overlap vs all other benches
    ok = set()
    a = Path(allow) if allow else d / "overlap-allow.txt"
    if a.is_file():
        for l in a.read_text().splitlines():
            ok |= shingles(l)
    seen = set()
    for x in others:
        for *_, t, _sp in scenarios(x):
            seen |= shingles(t)
    tune = set().union(*[shingles(t) - ok for _, _, t, sp in sc if sp == "tune"])
    for f, i, t, sp in sc:
        s = shingles(t) - ok
        for pool, name in ((seen, "other benches"), (tune if sp == "held" else set(), "its own tune set")):
            r = len(s & pool) / len(s) if s else 0
            if r > max_overlap:
                errs.append(f"{d}: {f} id {i} shares {r:.0%} of its {N}-word shingles with {name} (max {max_overlap:.0%})")
    return errs


def disk_link(p):
    """The target of repo path P if it is a symlink in the working tree, else None."""
    q = REPO / p
    return os.readlink(q) if q.is_symlink() else None


def in_repo(*cands):
    """The candidates whose every symlink hop stays inside REPO, as the real path each one names.

    Uses the same component walk as frozen_touched, so a link with an absolute target or one that
    leaves the checkout (even to re-enter it) counts as missing: no frozen line reaches outside the
    checkout, and none freezes a file the landed-bench guard would not see.
    """
    out, root = [], str(REPO)
    for c in cands:
        s = str(c.absolute())
        if not s.startswith(root + "/"):
            continue
        try:
            final = aliases(s[len(root) + 1:], disk_link)[1]
        except (ValueError, OSError):  # NUL byte or unreadable link: counts as missing
            continue
        if final not in ("", "/"):
            out.append(REPO / final)
    return out


def base_links(base):
    """{repo path: target} for every symlink in the tree at BASE (one ls-tree; targets read only for links)."""
    out = {}
    for e in filter(None, git("ls-tree", "-r", "-z", base).stdout.split("\0")):
        meta, path = e.split("\t", 1)
        if meta.startswith("120000"):
            out[path] = git("cat-file", "blob", meta.split()[2]).stdout
    return out


def aliases(path, link):
    """(every symlink PATH passes through plus PATH itself, the repo path it finally names).

    LINK(path) gives a symlink's target or None. Walks components the way the OS does, so "link/.."
    leaves the link's target, not the link's parent. Leaving the repo (an absolute target, or ".."
    above the root), an absolute PATH, a NUL byte, more than 40 hops or more than 1024 components ends the walk with final "/", which no
bench dir matches.
    """
    seen, stack, rest, hops, n = {path}, [], collections.deque(path.split("/")), 0, 0
    if path.startswith("/") or "\0" in path:
        return seen | {"/"}, "/"
    while rest:
        c, n = rest.popleft(), n + 1
        if n > 1024:  # bounds the walk (each step joins the stack); no real frozen path is this deep
            return seen | {"/"}, "/"
        if c in ("", "."):
            continue
        if c == "..":
            if not stack:
                return seen | {"/"}, "/"
            stack.pop()
            continue
        stack.append(c)
        cur = "/".join(stack)
        t = link(cur)
        if t is not None:
            hops += 1
            if hops > 40:  # a cycle or an over-long chain cannot be followed, so it fails closed
                return seen | {"/"}, "/"
            seen.add(cur)
            if t.startswith("/") or "\0" in t:
                return seen | {"/"}, "/"
            stack = stack[:-1]
            rest.extendleft(reversed(t.split("/")))
    final = "/".join(stack)
    return seen | {final}, final


def frozen_touched(base, touched):
    """Errors for benches landed at BASE whose frozen list or listed in-dir inputs the diff (repo-relative paths) touches.

    Reads each list from BASE, so a deleted or renamed list still guards what it froze. Listed paths
    (repo-root or bench-dir relative) are followed through BASE's symlinks, and every link on the way
    counts too, so neither editing an aliased file nor retargeting a link slips past. Files outside the
    bench dir (shared tools, SKILL.md) may evolve. A list line that is not "<sha256>  <path>" fails closed
    once the diff touches that dir, since what it froze cannot be told.
    """
    out, links = [], base_links(base)
    for p in filter(None, git("ls-tree", "--name-only", "-z", base, "docs/bench/").stdout.split("\0")):
        rel = f"{p}/SHA256-frozen.txt"
        names, final = aliases(rel, links.get)
        lst = git("show", f"{base}:{final}")
        if lst.returncode:
            continue
        if names & touched:
            out.append(f"{rel}: touched after the freeze (a landed bench's frozen list is immutable)")
        hit = any(t.startswith(p + "/") for t in touched)
        for n, l in enumerate(lst.stdout.splitlines(), 1):
            m = re.fullmatch(r"[0-9a-fA-F]{64} [ *](.+)", l)
            if not m:
                if hit:
                    out.append(f"{rel}: line {n} is not '<sha256>  <path>', so this landed bench cannot be checked")
                continue
            hits = False
            for c in (m.group(1), f"{p}/{m.group(1)}"):
                names, final = aliases(c, links.get)
                # an in-dir link or file, or any link on a path that lands in the dir
                hits |= any(n in touched and (n.startswith(p + "/") or final.startswith(p + "/")) for n in names)
            if hits:
                out.append(f"{rel}: {m.group(1)} touched after the freeze (a landed bench's inputs are immutable)")
    return out


def git(*a):
    """Run git in REPO; stdout/stderr decoded byte-exact (surrogateescape, no newline translation)."""
    r = subprocess.run(["git", "-C", str(REPO), *a], capture_output=True)
    r.stdout, r.stderr = (x.decode("utf-8", "surrogateescape") for x in (r.stdout, r.stderr))
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--changed", nargs="?", const="origin/main")
    ap.add_argument("--against")
    ap.add_argument("--allow")
    ap.add_argument("--max-overlap", type=float, default=0.2)
    a = ap.parse_args(argv)
    dirs = [Path(x) for x in a.dirs]
    root = REPO / "docs/bench"
    if a.changed:
        if git("rev-parse", "--verify", "-q", a.changed).returncode:
            sys.exit(f"bench_check: --changed base {a.changed} not found (fetch it)")
        new = [d for d in sorted(root.iterdir()) if d.is_dir()
               and not git("ls-tree", a.changed, f"docs/bench/{d.name}/").stdout.strip()]
        dirs += new
        diff = git("diff", "--name-only", "--no-renames", "-z", "--merge-base", a.changed)
        if diff.returncode:
            sys.exit(f"bench_check: no merge base with {a.changed} (fetch full history)")
        touched = set(filter(None, diff.stdout.split("\0")))
        errs = frozen_touched(a.changed, touched)
    else:
        errs = []
    ref = a.against or ("origin/main" if not git("rev-parse", "--verify", "-q", "origin/main").returncode else None)
    if a.against and git("rev-parse", "--verify", "-q", a.against).returncode:
        sys.exit(f"bench_check: --against ref {a.against} not found (fetch it)")
    with tempfile.TemporaryDirectory() as tmp:
        if ref:  # benches that landed on REF after the branch point
            tar = subprocess.run(["git", "-C", str(REPO), "archive", ref, "docs/bench"], capture_output=True)
            if not tar.returncode:
                tarfile.open(fileobj=io.BytesIO(tar.stdout)).extractall(tmp)
        extra = [x for x in sorted((Path(tmp) / "docs/bench").glob("*")) if x.is_dir() and not (root / x.name).exists()]
        for d in dirs:
            others = [x for x in sorted(root.iterdir()) if x.is_dir() and x.resolve() != d.resolve()] + extra
            errs += check(d, others, a.allow, a.max_overlap) + frozen_errs(d)
    print("\n".join(errs) or f"bench_check: {len(dirs)} dir(s) clean")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")  # git paths keep non-UTF-8 bytes (surrogateescape)
    sys.exit(main())
