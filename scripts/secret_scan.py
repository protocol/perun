#!/usr/bin/env python3
"""Secret scanner shared by the privacy gate (scripts/ci-gates.sh) and the rival bench (score_rivals.py).

Python port of the gitleaks default rules, scanning text for live-format secrets. One copy: the gate unions it
with .banlist.txt, the bench scores it as the gitleaks rival, so the two can never drift apart.

Rules are data in gitleaks-v8.30.1.toml next to this file (upstream gitleaks v8.30.1, MIT licence, Copyright (c)
2019 Zachary Rice; pin and sha256 in docs/bench/security-gates-1024/rivals/SOURCES.md). The vendored copy carries `@@`
markers inside public sample Google keys so the privacy gate never fires on it; deleting them restores upstream bytes.

Ported: keyword prefilter, regex, secret group, entropy, rule and global allowlists, `gitleaks:allow` lines.
Not ported: decode-and-rescan of base64/hex/percent, git history; lines are cut to 4 KB before matching. Go RE2 syntax is translated to Python `re`.

CLI (the gate's entry point, fanned out with xargs -P): file paths as arguments; prints each path that hits (rule id only, never the
secret) and exits 1 on any hit. Files pinned in secret-scan-allow.txt (exact repo-relative path and unchanged sha256) are skipped. Binary files (a NUL byte in the first 8 KB) are skipped, like `grep -I`.
"""
import hashlib, math, pathlib, posixpath, re, subprocess, sys, tomllib

R = pathlib.Path(__file__).resolve().parent

POSIX = {"alnum": "0-9A-Za-z", "alpha": "A-Za-z", "digit": "0-9", "lower": "a-z", "upper": "A-Z", "space": r"\t\n\v\f\r ",
         "punct": r"!-/:-@\[-`{-~", "xdigit": "0-9A-Fa-f", "word": r"0-9A-Za-z_"}


def go2py(p):
    """Translate a Go RE2 pattern to Python re: scoped inline flags, `$`/`\\z` as end-of-text, POSIX classes."""
    out, i, cls, stack = [], 0, False, [0]
    while i < len(p):
        c = p[i]
        if c == "\\":
            out.append(r"\Z" if p[i + 1:i + 2] == "z" else p[i:i + 2]); i += 2; continue
        if cls:
            if p.startswith("[:", i):
                j = p.index(":]", i); out.append(POSIX[p[i + 2:j]]); i = j + 2; continue
            cls = c != "]"; out.append(c); i += 1; continue
        if c == "[":
            cls = True; out.append(c); i += 1
            if p[i:i + 1] == "^": out.append("^"); i += 1
            if p[i:i + 1] == "]": out.append(r"\]"); i += 1
            continue
        if c == "(":
            m = re.match(r"\(\?([imsU]+)\)", p[i:])
            if m: out.append(f"(?{m.group(1)}:"); stack[-1] += 1; i += m.end(); continue
            stack.append(0)
        elif c == ")" and len(stack) > 1:
            out.append(")" * stack.pop())
        elif c == "$":
            out.append(r"\Z"); i += 1; continue
        out.append(c); i += 1
    return "".join(out) + ")" * stack[0]


def entropy(s):
    return -sum(s.count(c) / len(s) * math.log2(s.count(c) / len(s)) for c in set(s)) if s else 0.0


class AL:
    def __init__(s, d):
        c = lambda xs: [re.compile(go2py(x)) for x in xs]
        s.rx, s.paths = c(d.get("regexes", [])), c(d.get("paths", []))
        s.stop, s.rt, s.cond = [w.lower() for w in d.get("stopwords", [])], d.get("regexTarget", ""), d.get("condition", "OR")

    def hit(s, secret, match, line, path):
        t = {"": secret, "secret": secret, "match": match, "line": line}[s.rt]
        ch = ([any(r.search(t) for r in s.rx)] if s.rx else []) + ([any(w in secret.lower() for w in s.stop)] if s.stop else []) \
            + ([any(r.search(path) for r in s.paths)] if s.paths else [])
        return bool(ch) and (all(ch) if s.cond == "AND" else any(ch))


def load_gitleaks():
    cfg = tomllib.loads((R / "gitleaks-v8.30.1.toml").read_text().replace("@@", ""))
    glob = [AL(a) for a in cfg.get("allowlists", [])] + ([AL(cfg["allowlist"])] if "allowlist" in cfg else [])
    rules, fail = [], 0
    for r in cfg["rules"]:
        if "regex" not in r: continue  # path-only rules (file-type rules) do not apply to text strings
        try: rx = re.compile(go2py(r["regex"]))
        except re.error: fail += 1; continue
        pr = re.compile(go2py(r["path"])) if "path" in r else None
        als = [AL(a) for a in r.get("allowlists", [])] + ([AL(r["allowlist"])] if "allowlist" in r else [])
        rules.append((r["id"], rx, [k.lower() for k in r.get("keywords", [])], r.get("secretGroup", 0), r.get("entropy", 0.0), als, pr))
    return glob, rules, fail


GL = load_gitleaks()
LINE_MAX = 4096  # a secret starting past 4 KB of one line (minified bundles) is not seen; the cost of bounded time


def gitleaks_rule(text, path="input.txt"):
    """Return the ids of every rule that flags text (scanned as a file body at `path`); empty means clean."""
    glob, rules, _ = GL
    frag = "\n".join(l[:LINE_MAX] for l in text.split("\n")) + "\n"; low = frag.lower(); out = []  # long lines make the regexes quadratic
    for rid, rx, kw, sg, ent, als, pr in rules:
        if (kw and not any(k in low for k in kw)) or (pr and not pr.search(path)): continue
        for m in rx.finditer(frag):
            line = frag[frag.rfind("\n", 0, m.start()) + 1:frag.find("\n", m.end())]
            if "gitleaks:allow" in line: continue
            gs = [g for g in m.groups() if g]
            sec = m.group(sg) or "" if sg else (gs[0] if gs else m.group(0))
            if ent and entropy(sec) <= ent: continue
            if any(a.hit(sec, m.group(0), line, path) for a in glob + als): continue
            out.append(rid); break
    return out


def _allowed(f, allow):
    """True if f's path relative to its git top-level equals an allow-list entry exactly and its sha256 still matches the pin."""
    try:
        d = pathlib.Path(f).resolve().parent
        top = pathlib.Path(subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()).resolve()
        rel = pathlib.Path(f).resolve().relative_to(top).as_posix()
        return allow.get(rel) == hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def main(argv):
    """Scan the files named in argv; exit 1 on any hit, 2 on an unreadable file or a bad rule (fail closed)."""
    if GL[2]: print(f"secret_scan: {GL[2]} gitleaks regexes failed to compile", file=sys.stderr); return 2
    allow = {l.split(None, 1)[1]: l.split()[0] for l in (R / "secret-scan-allow.txt").read_text().splitlines() if l and not l.startswith("#")}
    names = {posixpath.basename(a) for a in allow}
    hit = 0
    for f in argv:
        if posixpath.basename(f) in names and _allowed(f, allow): continue
        try: b = pathlib.Path(f).read_bytes()
        except OSError as e: print(f"secret_scan: cannot read {f}: {e.strerror}", file=sys.stderr); return 2
        if b"\0" in b[:8192]: continue
        ids = gitleaks_rule(b.decode("utf-8", "replace"), f)
        if ids: print(f"  {f} ({', '.join(ids)})"); hit = 1
    return hit


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
