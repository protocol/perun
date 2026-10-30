#!/usr/bin/env python3
"""sibling_sweep.py --repo DIR --base REF [--head REF] - leads for an incomplete fix: a call changed here, its unchanged siblings there.

Purpose: a fix that changes the arguments of a call to a function F at some call sites (a rate-limit key, a new required option,
a wrapper around an argument) often leaves the same call on its old form elsewhere: the sibling route, the twin handler. The
hunks never show it. This lists the call sites of F that the diff did not touch, in non-test code. They are LEADS, never
findings: open each site and decide whether the same change belongs there.

How: `git diff -U0 BASE...HEAD` (BASE taken at the merge base) gives the changed lines. For each changed source file both blobs are
read and every call-shaped `name(...)` is found; the calls a hunk touches are compared across the two sides by their own
arguments (a nested call's arguments and a callback body are blanked first, so editing inside a callback is not editing the
outer call; whitespace, quote style and a trailing comma are ignored). A name whose touched calls lose one argument text and gain
another is "changed". `git grep` at HEAD then finds the calls to those names in the same language family; the ones the diff
did not touch, and whose arguments are not already a new form, are the leads.

Output (stdout, TSV, flushed at the end): `file<TAB>line<TAB>rule<TAB>message`, rule `unchanged-sibling-call` (message starts
`lead:`, names the changed site and its old and new arguments; the sites nearest an old form sort first, and one with the very same
arguments says so) or `not-checked` (surface this scan did not cover: leads beyond 5 per function or 30 in all, over 300 changed
source files, over 40 changed names, names with over 25 call sites: the first 5 are named; one row, path `.`). stderr: one summary
line. Exit 0, also with leads; 2 on usage, an unresolvable ref or no merge base.

Skipped: definitions; test, fixture, mock, vendored and build paths (as changed code and as call sites); names under 3 characters
and keywords; a name with more than 25 call sites (too common to sweep; named in the `not-checked` row and on stderr); calls in files of another language
family than a changed call; a call longer than 3000 characters; files over 400 KB; added and deleted files (no old and new side to compare; an added file's calls are changed, not unchanged sites).

Ceilings (a lead generator, not a call graph): regex based, no types or scopes, so two unrelated functions with one name merge;
calls without parentheses (shell, Ruby, Elixir), dynamic dispatch and names built from strings are invisible; an interface
declaration `f(x: T): U;` can read as a call and a call with a trailing block `f(x) { ... }` as a definition; a comment is
recognised only when it starts its line. A changed definition (a new parameter, a changed
return contract) is not swept here: `impact_map.py` lists the out-of-diff references to such a symbol, capped per symbol (`--cap`, default 8, then `truncated`).
Side effects: none (read-only git subprocesses against commits, no checkout, no writes).
"""
import argparse
import bisect
import collections
import difflib
import os
import re
import subprocess
import sys

MAX_SITES = 25  # a name called from more places than this is too common to sweep
MAX_LEADS = 30  # rows printed; the rest are counted in the not-checked row
MAX_PER_NAME = 5  # rows per changed name, so one noisy name cannot fill the output
MAX_FILES = 300  # changed source files read
MAX_FNS = 40  # changed names swept
SPAN = 3000  # characters scanned for a call's closing parenthesis
MAX_BLOB = 400_000  # bytes; a larger file is generated or minified
FAM = {e: f for f, es in {  # file extension -> language family: a name only matches within one family
    "js": ".js .jsx .mjs .cjs .ts .tsx .mts .cts .vue .svelte", "py": ".py .pyi", "go": ".go", "rb": ".rb", "jvm": ".java .kt .kts .scala",
    "c": ".c .h .cc .cpp .cxx .hpp .hh", "cs": ".cs", "rs": ".rs", "php": ".php", "swift": ".swift"}.items() for e in es.split()}
SKIP = re.compile(  # vendored and build paths, test and fixture dirs, test file names
    r"(^|/)(node_modules|vendor|dist|build|\.git|\.venv|venv|target|__pycache__|third_party|Pods|bower_components|\.claude/worktrees)/|\.min\.js$"
    r"|(^|/)(tests?|__tests__|__mocks__|__fixtures__|specs?|e2e|testdata|fixtures?|mocks?|cypress)/"
    r"|(^|/)(test_[^/]*|conftest\.py)$|(^|[/._-])(tests?|specs?|e2e|mocks?)\.[^/.]+$|(?-i:[a-z0-9](?:Test|Tests|Spec)\.(?:java|kt|cs|scala|swift))$", re.IGNORECASE)
KW = frozenset("""if for while switch catch return function def class with elif else except await not and or in is new typeof sizeof delete throw
assert yield match case print super this self cls async lambda defer range require import export""".split())
CALL = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)[ \t]*(?:<[^<>()\n]*>[ \t]*)?\(")
TOK = re.compile(r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`|[(){}\[\]]""")  # a string literal, or one bracket
NEST = {"(": re.compile(r"[\w$)\]>]\s*$"), "{": re.compile(r"(?:=>|\))\s*$")}  # a call's parenthesis; a function body's brace
DEFKW = re.compile(r"(?<![.\w$])(?:def|function|func|fn|fun|sub|proc|class|interface|struct|enum|trait|impl|protocol)(?![.\w$])\*?\s*(?:\([^()]*\)\s*)?[\w$.:<>,\s*&]*$")
TYPEPFX = re.compile(r"[\s\w$<>\[\],.*&:@]*$")  # only modifiers and a return type before the name: a method definition, not a call in an expression
KWX = re.compile(r"\b(?:if|for|while|switch|match|else|elif|catch|case|return|await|yield|new|throw|do)\b")
BRACE = re.compile(r"\s*(?::[^;{}=]*|->[^;{}=]*|throws\s[\w.,\s]+)?\{")  # what follows a method definition's parameter list
COMMENT = re.compile(r"\s*(?://|#|\*|/\*|--)")
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def fam(path):
    return FAM.get(os.path.splitext(path)[1].lower())


def git(repo, *args, ok=(0,)):
    """stdout of `git -C repo ARGS` as text, or None when the exit code is not in `ok`."""
    r = subprocess.run(["git", "-C", repo, "-c", "core.quotePath=false", *args], capture_output=True, check=False)
    return r.stdout.decode("utf-8", "replace") if r.returncode in ok else None


def blob(repo, rev, path):
    """File text at a commit (never the working tree), or None when absent or over MAX_BLOB."""
    r = subprocess.run(["git", "-C", repo, "cat-file", "blob", f"{rev}:{path}"], capture_output=True, check=False)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 and len(r.stdout) <= MAX_BLOB else None


def close(t, i):
    """Index of the bracket that closes the one opened just before t[i], or -1 when there is none within SPAN characters."""
    d = 1
    for m in TOK.finditer(t, i, i + SPAN):
        g = m.group()
        if len(g) == 1:
            d += 1 if g in "([{" else -1
            if d == 0:
                return m.start()
    return -1


def own(a):
    """`a` with the inside of every nested call's parentheses and of every function body blanked: an edit inside a callback or a
    nested call is not an edit of this call's own arguments."""
    out, i = [], 0
    while m := TOK.search(a, i):
        if m.group() in NEST and NEST[m.group()].search(a[max(0, m.start() - 40):m.start()]):
            j = close(a, m.end())
            if j >= 0:
                out += [a[i:m.end()], a[j]]
                i = j + 1
                continue
        out.append(a[i:m.end()])
        i = m.end()
    return "".join(out) + a[i:]


def norm(s):
    """Whitespace, quote style and a trailing comma do not make an argument list different."""
    s = re.sub(r"\s+", " ", s).replace("'", '"').strip()
    return s[:-1].rstrip() if s.endswith(",") else s


def calls(text):
    """[(name, own_args, first_line, last_line, is_definition)] for each call-shaped `name(...)` in text. Pure; no I/O."""
    nl = [m.start() for m in re.finditer("\n", text)]
    out = []
    for m in CALL.finditer(text):
        n, b = m.group(1), m.start(1)
        j = close(text, m.end()) if len(n) >= 3 and n not in KW else -1
        ls = text.rfind("\n", 0, b) + 1  # start of the call's line
        pre = text[max(ls, b - 300):b]  # what precedes the name on its line; 300 characters decide a definition (a one-line bundle is not quadratic)
        if j < 0 or COMMENT.match(text, ls):
            continue
        d = DEFKW.search(pre) or (TYPEPFX.match(pre) and not KWX.search(pre) and BRACE.match(text, j + 1))
        out.append((n, norm(own(text[m.end():j])), bisect.bisect_left(nl, b) + 1, bisect.bisect_left(nl, j) + 1, bool(d)))
    return out


def hunks(diff):
    """{(old_path, new_path): (old_intervals, new_intervals)} for each file with hunks in a `git diff -U0`; a path is None on the side
    that does not exist (added, deleted). An interval is (first, last) changed line, or (n + .5, n + .5) for the point between lines n
    and n + 1 where a pure insertion or deletion sits."""
    out, hdr, op, cur = {}, False, "", None
    for ln in diff.split("\n"):
        if ln.startswith("diff --git "):
            hdr, cur = True, None
        elif hdr and ln.startswith("--- "):  # headers count only before the first "@@": a removed "-- x" line also starts with "--- "
            op = ln[4:].split("\t")[0]
        elif hdr and ln.startswith("+++ "):  # a quoted (odd) path starts with a quote, not "a/": skipped
            np_ = ln[4:].split("\t")[0]
            pa = tuple(None if x == "/dev/null" else x[2:] if x[:2] in ("a/", "b/") else "" for x in (op, np_))
            cur = out.setdefault(pa, ([], [])) if "" not in pa else None
        elif ln.startswith("@@"):
            hdr = False
            m = HUNK.match(ln)
            for iv, (s, n) in zip(cur or (), ((m[1], m[2]), (m[3], m[4])) if m else ()):
                s, n = int(s), 1 if n is None else int(n)
                iv.append((s + .5, s + .5) if n == 0 else (s, s + n - 1))
    return out


def hit(c, ivs):
    """True when the call (tuple from calls()) overlaps a changed interval."""
    return any(c[2] <= hi and c[3] >= lo for lo, hi in ivs)


def short(s, k=48):
    return s if len(s) <= k else s[:k - 3] + "..."


def sweep(repo, base, head):
    """([(file, line, rule, message)], summary line) for the diff base...head of the repository at `repo`. Raises SystemExit(2) on an
    unresolvable ref or no merge base."""
    rv = lambda r: (git(repo, "rev-parse", "--verify", "-q", r + "^{commit}") or "").strip()
    bs, hd = rv(base), rv(head)
    mb = (git(repo, "merge-base", bs, hd, ok=(0,)) or "").strip() if bs and hd else ""
    if not mb:
        sys.exit(f"sibling_sweep: unresolvable ref or no merge base: {base} {head}")
    diff = git(repo, "diff", "-U0", "-M", "--no-color", "--no-ext-diff", "--no-textconv", "--diff-filter=AMR", "--src-prefix=a/", "--dst-prefix=b/", mb, hd)
    if diff is None:
        sys.exit("sibling_sweep: git diff failed")
    newiv, chg, seen, head = {}, {}, 0, {}  # head: path -> calls() at the head commit, shared by both passes
    for (op, np_), (oiv, niv) in hunks(diff).items():
        if np_:
            newiv[np_] = niv  # an added file is all changed lines: its calls are not "unchanged"
        if not (op and np_) or fam(np_) is None or SKIP.search(np_) or SKIP.search(op):
            continue
        seen += 1
        ot, nt = (blob(repo, mb, op), blob(repo, hd, np_)) if seen <= MAX_FILES else (None, None)
        if ot is None or nt is None:
            continue
        nc = head[np_] = calls(nt)
        tn = [c for c in nc if not c[4] and hit(c, niv)]
        co = collections.Counter((c[0], c[1]) for c in calls(ot) if not c[4] and hit(c, oiv))
        cn = collections.Counter((c[0], c[1]) for c in tn)
        rem, add = co - cn, cn - co  # argument texts only the old side has, only the new side has
        for n in {k[0] for k in rem} & {k[0] for k in add}:  # a name that lost one argument text and gained another
            o, w = {k[1] for k in rem if k[0] == n}, {k[1] for k in add if k[0] == n}
            c = chg.setdefault(n, {"old": set(), "new": set(), "fam": set(), "at": (np_, next(c[2] for c in tn if c[0] == n and (n, c[1]) in add)), "ex": (min(o), min(w))})
            c["old"] |= o
            c["new"] |= w
            c["fam"].add(fam(np_))
    names = sorted(chg)
    notes = [f"read {MAX_FILES} of {seen} changed source files"] * (seen > MAX_FILES) + [f"swept {MAX_FNS} of {len(names)} changed names"] * (len(names) > MAX_FNS)
    names, big, leads = names[:MAX_FNS], [], []
    if names:
        pat = r"(^|[^[:alnum:]_$])(" + "|".join(n.replace("$", r"\$") for n in names) + r")[[:space:]]*[(<]"
        exts = sorted(e for e, f in FAM.items() if f in set().union(*(chg[n]["fam"] for n in names)))
        found = git(repo, "grep", "-nIz", "--no-color", "-E", "-e", pat, hd, "--", *("*" + e for e in exts), ok=(0, 1)) or ""
        line = re.compile(r"(?<![\w$])(" + "|".join(re.escape(n) for n in names) + r")[ \t]*[(<]")
        cnt, cand = collections.Counter(), collections.defaultdict(set)
        for rec in found.split("\n"):
            p = rec.split("\0", 2)
            if len(p) == 3 and not SKIP.search(p[0][len(hd) + 1:]):
                for n in set(line.findall(p[2])):
                    if fam(p[0]) in chg[n]["fam"]:
                        cnt[n] += 1
                        cand[n].add(p[0][len(hd) + 1:])
        big = [n for n in names if cnt[n] > 2 * MAX_SITES]  # cheap line count first, so a very common name never costs a blob read
        names = [n for n in names if n not in big]
        sites = collections.defaultdict(list)
        for path in sorted(set().union(*(cand[n] for n in names))):
            if path not in head:
                t = blob(repo, hd, path)
                head[path] = calls(t) if t else []
            for n, a, s, e, d in head[path]:
                if n in names and not d and fam(path) in chg[n]["fam"]:
                    sites[n].append((path, s, e, a))
        for n in names:
            if len(sites[n]) > MAX_SITES:
                big.append(n)
                continue
            for path, s, e, a in sites[n]:
                if not hit((n, a, s, e), newiv.get(path, ())) and a not in chg[n]["new"]:
                    sim = max(difflib.SequenceMatcher(None, a[:200], o[:200]).ratio() for o in chg[n]["old"])  # 1.0 = the old form itself
                    leads.append((-sim, n, path, s, a))
    leads.sort()  # nearest to an old form first
    per, kept = collections.Counter(), []
    for lead in leads:
        per[lead[1]] += 1
        if per[lead[1]] <= MAX_PER_NAME:
            kept.append(lead)
    rows = []
    for _, n, path, s, a in kept[:MAX_LEADS]:
        c = chg[n]
        rows.append((path, s, "unchanged-sibling-call", f"lead: {n}({short(a)}) is unchanged, but this diff changed the arguments of {n} at "
                     f"{c['at'][0]}:{c['at'][1]} ({short(c['ex'][0])} -> {short(c['ex'][1])})" + ("; same arguments as the old form" if a in c["old"] else "")))
    if len(leads) > len(rows):
        notes.append(f"{len(leads) - len(rows)} more sibling lead(s) not listed (cap {MAX_PER_NAME} per function, {MAX_LEADS} in all)")
    over = (f"not swept, over {MAX_SITES} call sites: {', '.join(sorted(big)[:5])}" + (f" (+{len(big) - 5} more)" if len(big) > 5 else "")) if big else ""
    if over:  # a row, not only the stderr summary: review_checks.sh keeps rows and drops that line
        notes.append(over)
    if notes:
        rows.append((".", 0, "not-checked", "sibling sweep partial: " + "; ".join(notes)))
    summary = f"sibling_sweep: {len(chg)} name(s) with changed call arguments; {len(leads)} lead(s), not findings: open each site" + (f"; {over}" if over else "")
    return rows, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".", help="git repository (default .)")
    ap.add_argument("--base", required=True, help="base ref; the diff is taken from its merge base with --head")
    ap.add_argument("--head", default="HEAD", help="head ref (default HEAD)")
    a = ap.parse_args(argv)
    if a.base.startswith("-") or a.head.startswith("-"):
        sys.exit("sibling_sweep: a ref must not start with '-'")
    rows, summary = sweep(a.repo, a.base, a.head)
    sys.stdout.write("".join("\t".join(re.sub(r"[\t\r\n]", " ", str(x)) for x in r) + "\n" for r in rows))
    print(summary, file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:  # sys.exit("msg") exits 1 by default; every failure here is "bad input": 2
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise
