#!/usr/bin/env python3
"""Score three rival tools on the frozen security-gates corpus, using their rules ported to Python.

Usage: python3 -I docs/bench/security-gates-1024/rivals/score_rivals.py   (offline, deterministic, nothing executed)

These are ports of the rivals' published rules, NOT the rival binaries: ported-rule fidelity is the main threat
to every number printed here (see README.md next to this file's parent and SOURCES.md for pins and gaps).
  gitleaks        full port of the pinned default config (keywords prefilter, regex, secret group, entropy,
                  rule and global allowlists; shared with the privacy gate as scripts/secret_scan.py). Not ported: decode-and-rescan of base64/hex/percent, path rules.
  hooks-mastery   exact port of the rm and .env regexes of the pinned pre_tool_use.py.
  safety-net      a documented SUBSET port of a large shell-AST analyzer, scored three-state: block / allow /
                  unported. "unported" rows are counted in neither the lower bound nor as a rival miss.
"""
import importlib.util, pathlib, posixpath, re, shlex, sys

R = pathlib.Path(__file__).resolve().parent
D = R.parent
spec = importlib.util.spec_from_file_location("score", D / "score.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)
spec = importlib.util.spec_from_file_location("secret_scan", D.parents[2] / "scripts" / "secret_scan.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)
go2py, gitleaks_rule, GL = ss.go2py, ss.gitleaks_rule, ss.GL  # the one shared gitleaks port; its rules are the data file next to it

# ---------------------------------------------------------------- hooks-mastery (exact port of pre_tool_use.py)
HM_RM = [r'\brm\s+.*-[a-z]*r[a-z]*f', r'\brm\s+.*-[a-z]*f[a-z]*r', r'\brm\s+--recursive\s+--force',
         r'\brm\s+--force\s+--recursive', r'\brm\s+-r\s+.*-f', r'\brm\s+-f\s+.*-r']
HM_PATHS = [r'/', r'/\*', r'~', r'~/', r'\$HOME', r'\.\.', r'\*', r'\.', r'\.\s*$']
HM_ENV = [r'\b\.env\b(?!\.sample)', r'cat\s+.*\.env\b(?!\.sample)', r'echo\s+.*>\s*\.env\b(?!\.sample)',
          r'touch\s+.*\.env\b(?!\.sample)', r'cp\s+.*\.env\b(?!\.sample)', r'mv\s+.*\.env\b(?!\.sample)']


def hooks_mastery(cmd):
    if any(re.search(p, cmd) for p in HM_ENV): return True
    n = " ".join(cmd.lower().split())
    return any(re.search(p, n) for p in HM_RM) or (
        bool(re.search(r'\brm\s+.*-[a-z]*r', n)) and any(re.search(p, n) for p in HM_PATHS))


# ---------------------------------------------------------------- safety-net (subset port, 3-state)
B, A, U = "block", "allow", "unported"
SHELLS = {"bash", "sh", "zsh", "ksh", "dash", "fish", "csh", "tcsh"}
GIT_VAL = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
TEMP = ("/tmp", "/var/tmp", "/private/tmp", "$TMPDIR", "${TMPDIR}")


def split_segments(cmd):
    """Split on ; & && || | newline outside quotes and $(...); yields (text, piped_from_previous)."""
    segs, cur, q, depth, i, piped = [], [], "", 0, 0, False
    while i < len(cmd):
        c = cmd[i]
        if q:
            if c == "\\" and q == '"': cur.append(cmd[i:i + 2]); i += 2; continue
            q = "" if c == q else q
        elif c in "'\"": q = c
        elif c == "`": depth = 0 if depth == -1 else -1
        elif c == "(" and cur and cur[-1] == "$": depth += 1 if depth >= 0 else 0
        elif c == ")" and depth > 0: depth -= 1
        elif depth == 0 and c in ";&|\n" and not (c == "&" and (cmd[i - 1:i] == ">" or cmd[i + 1:i + 2] == ">")):
            segs.append(("".join(cur), piped)); cur = []; piped = c == "|"
            if cmd[i + 1:i + 2] == c and c in "&|": i += 1
            i += 1; continue
        cur.append(c); i += 1
    segs.append(("".join(cur), piped))
    return [(t, p) for t, p in segs if t.strip()]


def flags(args):
    """(recursive, force) over option tokens, stopping at `--`; long options may be abbreviated."""
    rec = frc = False
    for a in args:
        if a == "--": break
        if a.startswith("--"):
            rec |= len(a) > 2 and "recursive".startswith(a[2:]); frc |= len(a) > 2 and "force".startswith(a[2:])
        elif a.startswith("-") and len(a) > 1:
            rec |= bool(set("rR") & set(a)); frc |= bool(set("fF") & set(a))
    return rec, frc


def dyn(t): return bool(re.search(r"[$`*?\[]|\{[^}]*(,|\.\.)", t))
def temp(t): return t.startswith(TEMP) and ".." not in t.split("/")
def scoped(t): return temp(t) or (not dyn(t) and not t.startswith(("/", "~")) and ".." not in t.split("/") and posixpath.normpath(t) != ".")


def rm_target_bad(t):
    if re.fullmatch(r"(/+\*?|~/*\*?|\$\{?HOME\}?/*\*?)", t) or ".git" in t.split("/"): return True
    if temp(t) or dyn(t): return False  # dynamic targets are blocked only in strict mode
    return posixpath.normpath(t) == "." or t.startswith("/") or ".." in t.split("/")


def git_check(a):
    i = 0
    while i < len(a) and a[i].startswith("-"): i += 2 if a[i] in GIT_VAL else 1
    if i >= len(a): return A
    sub, rest = a[i], a[i + 1:]
    head = rest[:rest.index("--")] if "--" in rest else rest
    longs = [x.split("=")[0] for x in head if x.startswith("--")]
    has = lambda o: any(len(n) >= 4 and o.startswith(n) for n in longs)
    sh = {ch for x in head if re.fullmatch(r"-[A-Za-z]+", x) for ch in x[1:]}
    pos = [x for x in head if not x.startswith("-")]
    force = "f" in sh or has("--force")
    if sub == "checkout":
        if force: return B
        if sh & {"b", "B"} or has("--orphan"): return A
        if "--" in rest: return B
        if len(pos) >= 2: return B
        return B if pos and re.search(r"^(\.\.?/?|/.*|:.*)$|/$|[*?\[]", pos[0]) else A
    if sub == "switch": return B if has("--discard-changes") or force else A
    if sub == "restore":
        if not (pos or has("--patch") or "p" in sh): return A
        return A if ("S" in sh or has("--staged")) and not ("W" in sh or has("--worktree")) else B
    if sub == "reset": return B if has("--hard") or has("--merge") else A
    if sub == "clean": return A if "n" in sh or has("--dry-run") else B if force else A
    if sub == "stash": return B if pos[:1] and pos[0] in ("drop", "clear") else A
    if sub == "worktree": return B if pos[:1] == ["remove"] and force else A
    if sub == "tag": return B if "d" in sh or has("--delete") else A
    if sub == "branch": return B if "D" in sh or (("d" in sh or has("--delete")) and force) else A
    if sub == "push":
        refs = pos[1:]
        bad = has("--mirror") or force or has("--delete") or "d" in sh or any(r.startswith("+") or ":+" in r or (r.startswith(":") and len(r) > 1) for r in refs)
        return B if bad else A
    return A


def analyze_tokens(t, piped=False, prev="", depth=0):
    while t and re.fullmatch(r"[A-Za-z_]\w*=.*", t[0]): t = t[1:]
    while t and posixpath.basename(t[0]).lower() in ("sudo", "env", "command", "builtin"):
        t = t[1:]
        while t and (t[0].startswith("-") or re.fullmatch(r"[A-Za-z_]\w*=.*", t[0])): t = t[1:]
    if not t: return A
    if t[0][0] in "${" or "${" in t[0] or "`" in t[0]: return U  # dynamic-executable / dynamic-structure: strict-only rules
    h, a = posixpath.basename(t[0]).lower(), t[1:]
    if h == "rm":
        rec, _ = flags(a)
        return B if rec and any(rm_target_bad(x) for x in a if x == "--" or not x.startswith("-")) else A
    if h == "git": return git_check(a)
    if h == "shred": return B if a else A
    if h == "dd": return B if any(re.fullmatch(r"of=/dev/.+", x) and x not in ("of=/dev/null", "of=/dev/zero", "of=/dev/full") for x in a) else A
    if re.fullmatch(r"mkfs(\..+)?|mke2fs|newfs(_.+)?", h): return B if any(x.startswith("/dev/") for x in a) else A
    if h == "find":
        starts = []
        for x in a:
            if x.startswith("-") or x in ("(", "!"): break
            starts.append(x)
        if "-delete" in a and not all(scoped(s) for s in starts): return B
        for k, x in enumerate(a):
            if x in ("-exec", "-execdir", "-ok", "-okdir"):
                kid = []
                for y in a[k + 1:]:
                    if y in (";", "+", "\\;"): break
                    kid.append(y)
                if kid and posixpath.basename(kid[0]) == "rm" and all(flags(kid[1:])): return B
                if analyze_tokens(kid, depth=depth + 1) == B: return B
        return A
    if h == "xargs":
        k = 0
        while k < len(a) and a[k].startswith("-"): k += 2 if a[k] in ("-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a", "-J") else 1
        kid = a[k:]
        if kid and posixpath.basename(kid[0]) == "rm" and all(flags(kid[1:])): return B
        return analyze_tokens(kid, True, depth=depth + 1) if kid else A
    if h == "rsync":
        dl = any(len(x) >= 5 and "--delete".startswith(x) or x.startswith("--delete-") for x in a if x.startswith("--"))
        ops = [x for x in a if not x.startswith("-")]
        return B if dl and any(not scoped(d) for d in ops[1:] if not re.match(r"^[^/]*:", d)) else A
    if h in SHELLS:
        for k, x in enumerate(a):
            if re.fullmatch(r"-[a-z]*c[a-z]*", x) and k + 1 < len(a):
                code = a[k + 1]
                if re.search(r"[$`].*\b(curl|wget)\b", code) and code.lstrip().startswith(("$(", "`")): return B
                return analyze(code, depth + 1) if depth < 4 else U
        return (U if prev.lstrip().startswith("printf") else B) if piped else A
    if h == "eval":
        j = " ".join(a)
        return B if re.search(r"[$`]", j) else analyze(j, depth + 1)
    if re.fullmatch(r"python[0-9.]*|node|ruby|perl", h):
        for k, x in enumerate(a):
            if x in ("-c", "-e", "-E", "-p", "--eval") and k + 1 < len(a): return interp_check(a[k + 1], depth)
    return A


def interp_check(code, depth):
    """Interpreter -c/-e code: native recursive delete of root/home, raw rm with -r and -f, nested shell text."""
    if re.search(r"\b(rmtree|rm_rf|rmSync|rimraf|remove_tree)\s*\(\s*['\"](/|~|\$HOME)['\"]", code): return B
    for m in re.finditer(r"(?<![A-Za-z0-9_])rm\s+([^\n;&|]*)", code):
        if all(flags(m.group(1).split())): return B
    return B if depth < 4 and analyze(code, depth + 1) == B else A


def analyze(cmd, depth=0):
    res, prev = A, ""
    for text, piped in split_segments(cmd):
        if re.search(r">>?\s*/dev/(r?disk\d|sd[a-z]|hd[a-z]|vd[a-z]|xvd[a-z]|nvme\d|mmcblk\d|md\d|dm-\d|loop\d)", text): return B
        try: t = shlex.split(text)
        except ValueError: r = U
        else: r = analyze_tokens(t, piped, prev, depth)
        if r == B: return B
        res, prev = (U if U in (res, r) else A), text
    return res


# ---------------------------------------------------------------- scoring
def scores():
    """Compute every rival number on the frozen corpus; raises on hash drift or ported-regex compile failure."""
    if sc.sha_ok(): raise SystemExit(f"HASH DRIFT: {sc.sha_ok()}")
    if GL[2]: raise SystemExit(f"{GL[2]} gitleaks regexes failed to compile")
    pick = lambda n: [(l.split("\t")[0], l.split("\t", 1)[1].replace("@@", "")) for l in sc.rows(n)]
    leaks, decoys = pick("secret-leaks.txt"), pick("secret-decoys.txt")
    dang, ben = sc.cmds("destructive-dangerous.txt"), sc.cmds("destructive-benign.txt")
    s = {"gitleaks": dict(n_leaks=len(leaks), n_decoys=len(decoys), rules=len(GL[1]),
                          missed=[n for n, t in leaks if not gitleaks_rule(t)], fp=[n for n, t in decoys if gitleaks_rule(t)])}
    s["hooks-mastery"] = dict(n=len(dang), n_ben=len(ben), missed=[c for c in dang if not hooks_mastery(c)], fp=[c for c in ben if hooks_mastery(c)])
    sn = {c: analyze(c) for c in dang}
    sb = {c: analyze(c) for c in ben}
    s["safety-net"] = dict(n=len(dang), n_ben=len(ben), missed=[c for c, r in sn.items() if r == A], unported=[c for c, r in sn.items() if r == U],
                           fp=[c for c, r in sb.items() if r == B], fp_unported=[c for c, r in sb.items() if r == U])
    return s


def main():
    s = scores(); g, h, n = s["gitleaks"], s["hooks-mastery"], s["safety-net"]
    print(f"gitleaks v8.30.1 (ported, {g['rules']} rules): recall {g['n_leaks'] - len(g['missed'])}/{g['n_leaks']}  FP {len(g['fp'])}/{g['n_decoys']}")
    print("  missed:", g["missed"]); print("  false positives:", g["fp"])
    print(f"hooks-mastery (ported): blocked {h['n'] - len(h['missed'])}/{h['n']}  FP {len(h['fp'])}/{h['n_ben']}")
    print("  missed:", h["missed"]); print("  false positives:", h["fp"])
    lo = n["n"] - len(n["missed"]) - len(n["unported"])
    print(f"safety-net (ported subset): blocked {lo}/{n['n']} ({len(n['unported'])} unported)  FP {len(n['fp'])}/{n['n_ben']} (unported benign {len(n['fp_unported'])})")
    print("  missed:", n["missed"]); print("  unported:", n["unported"]); print("  false positives:", n["fp"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
