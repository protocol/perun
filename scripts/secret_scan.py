#!/usr/bin/env python3
"""Secret scanner shared by the privacy gate (scripts/ci-gates.sh) and the rival bench (score_rivals.py).

Python port of the gitleaks default rules, scanning text for live-format secrets. One copy: the gate unions it
with .banlist.txt, the bench scores it as the gitleaks rival, so the two can never drift apart.

Rules are data in gitleaks-v8.30.1.toml next to this file (upstream gitleaks v8.30.1, MIT licence, Copyright (c)
2019 Zachary Rice; pin and sha256 in docs/bench/security-gates-1024/rivals/SOURCES.md). The vendored copy carries `@@`
markers inside public sample Google keys so the privacy gate never fires on it; deleting them restores upstream bytes.

Ported: keyword prefilter, regex, secret group, entropy, rule and global allowlists, `gitleaks:allow` lines.
Not ported: decode-and-rescan of base64/hex/percent, git history; lines are cut to 4 KB before matching. Go RE2 syntax is translated to Python `re`.

CLI (the gate's entry point, fanned out with xargs -P): file paths as arguments (or `--refilter ERE file...`, the banlist half's second pass: prints files with a non-placeholder match (judged on the matched span, not the line)); prints each path that hits (rule id only, never the
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


# Lines that mark a match as a non-secret: documentation words, filler runs, Stripe test-mode and publishable keys, browser-exposed
# env vars (NEXT_PUBLIC_), Mapbox public tokens, CSRF nonces. Applied to the matched text only (never the rest of the line), only by the gate (precise=True), never to the rival bench.
PLACEHOLDER = re.compile(r"(?<![A-Za-z])(?:[Ee]xample|EXAMPLE)(?![a-z]|\.[a-z])|[A-Z0-9]EXAMPLE(?:KEY)?(?![A-Za-z0-9])|(?i:dummy|fake|placeholder|redacted|revoked|replace[_-]?me|changeme|x{8,}|0{10,}|[sp]k_test_|pk_live_|next_public_|\bpk\.eyJ|[cx]srf)|(?<![A-Za-z])your[_-]|dXNlcm5hbWU6cGFzc3dvcmQ|dXNlcjpwYXNz|QWxhZGRpbjpvcGVuIHNlc2FtZQ")


# A Google API key whose own line says it is a referrer-restricted public (browser) key is public by design; an unsigned JWT (empty signature) is not a credential.
PUBKEY = re.compile(r"(?i)(?:#|//|--)[^\n]*?(?:\bpublic\b[^\n]*\b(?:restricted|referr?er)\b|referr?er[- ]restricted)")


def pubkey_ok(tail):
    """True when the text after one match on its line is a comment calling that key public/referrer-restricted and holds no second key."""
    return "AIza" not in tail and bool(PUBKEY.match(tail.lstrip()))


# Perun's own recall rules (gate only: precise=True; the rival bench scores plain gitleaks). (id, regex, secret group, min entropy).
# Added after held-out-4 misses; each passes its decoy twins in scripts/test_secrets_heldout4_blind.py.
_Q = r"""['"](?![$<{%*])"""  # opening quote, not followed by a template/placeholder sigil
# Identifier-shaped values are code references, not secrets: dotted paths and env refs (os.environ[X], config.secret_key_value), snake_case or
# SCREAMING_CASE names, and camelCase words (passwordRequired). Random secrets have no such word structure.
IDENT = re.compile(r"\w+(?:\.\w+)+|[\w.]*[\[\](){}][\w.\[\](){}]*|[a-z]+(?:_[a-z0-9]+)+|[A-Z]+(?:_[A-Z0-9]+)+|[a-z]+(?:[A-Z][a-z]{2,})+\d*", re.A)
EXTRA = [(i, re.compile(r), g, e) for i, r, g, e in [
    ("discord-webhook", r"discord(?:app)?\.com/api/webhooks/\d{17,20}/([\w-]{50,})", 1, 3.5),
    ("url-password", r"\b[a-z][a-z0-9+.-]*://[^\s:/]*:([^\s@/$<>{}*%]{8,})@[\w.-]+", 1, 3.0),
    ("secret-key-literal", rf"(?i)secret_key\W{{0,4}}[=:]\s*{_Q}([^'\"\s]{{16,}})['\"]", 1, 3.5),
    ("jwt-literal-secret", rf"\bjwt\.(?:sign|verify)\([^,()]+,\s*{_Q}([^'\"\s]{{16,}})['\"]", 1, 3.0),
    ("google-client-secret", r"\bGOCSPX-[\w-]{20,}", 0, 0),
    ("uuid-credential", r"(?i)\b\w*(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?key|access[_-]?token|auth[_-]?token)\w*=([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\b", 1, 0),
    ("auth-header-token", r"(?i)\bauthorization\W{1,3}(?:bearer|token)\s+([\w.~+/=-]{24,})", 1, 3.5),
    ("password-literal", rf"(?i)\bpassword['\"]?\s*[=:]\s*{_Q}([^'\"\s]{{8,}})['\"]", 1, 3.0),
    ("cli-password", rf"(?i)\b(?:mysql(?:dump)?|psql|sshpass|redis-cli|mongo(?:sh)?)\b[^\n]*?\s-p\s*{_Q}([^'\"\s]{{6,}})['\"]", 1, 3.0),
    ("telegram-bot-token", r"\b\d{8,10}:(?:AA[\w-]{30,}|[\w-]{35}\b)", 0, 3.0),
    ("sentry-dsn", r"\bhttps://\w{16,}:(\w{16,})@[\w.-]*ingest[\w.-]*/\d+", 1, 3.0),  # legacy key:secret form only; a key-only DSN is public by design
    ("cli-token-flag", r"""(?i)\s--(?:token|api[_-]?key|password|secret)(?:=|\s+)['"]?(?![$<{%*])(?![^\s'"]*/)(?![^\s'"]*\.(?:ya?ml|json|txt|pem|key|env|conf|cfg|ini|toml|crt|p12)(?:[\s'"]|$))([^\s'"]{16,})""", 1, 3.5),
    ("password-assign", r"""(?i)\b(?!test_)\w*passw(?:or)?d(?!\w*(?:length|min|max|policy)\b)\w*['"]?\s*[=:]\s*['"]?(?=[a-z\d])(?!(?:\w*passw(?:or)?d|secret|admin|qwerty|letmein)[\d!]{0,6}(?![^\s'",;]))(?=\S*\d)(?=\S*[a-z])([^\s'",;]{8,})""", 1, 3.0),
    # whitespace-separated forms only where the syntax is fixed: Dockerfile ENV/ARG and netrc `login X password Y`
    ("password-env-netrc", r"""(?i)(?:\b(?:env|arg)\s+\w*passw(?:or)?d\w*|\blogin\s+\S+\s+password)\s+(?=[a-z\d])(?!(?:\w*passw(?:or)?d|secret|admin|qwerty|letmein)[\d!]{0,6}(?![^\s'",;]))(?=\S*\d)(?=\S*[a-z])([^\s'",;]{8,})""", 1, 3.0),
    ("conn-string-password", r"""(?i)[;?&](?:password|pwd)=(?![$<{%*])([^;&\s'"]{8,})""", 1, 3.0),
    ("auth-basic", r"(?i)\bauthorization\W{1,3}basic\s+([A-Za-z0-9+/]{16,}={0,2})", 1, 3.5),
    ("vault-token", r"\bhv[sbr]\.([\w-]{24,})", 1, 3.5),
]]


def gitleaks_rule(text, path="input.txt", precise=False):
    """Return the ids of every rule that flags text (scanned as a file body at `path`); empty means clean.

    precise=True also drops matches whose own text looks like a placeholder or public-by-design value (PLACEHOLDER); the gate sets it, the bench does not."""
    glob, rules, _ = GL
    frag = "\n".join(l[:LINE_MAX] for l in text.split("\n")) + "\n"; low = frag.lower(); out = []  # long lines make the regexes quadratic
    for rid, rx, kw, sg, ent, als, pr in rules:
        if (kw and not any(k in low for k in kw)) or (pr and not pr.search(path)): continue
        for m in rx.finditer(frag):
            line = frag[frag.rfind("\n", 0, m.start()) + 1:frag.find("\n", m.end())]
            gs = [g for g in m.groups() if g]
            sec = m.group(sg) or "" if sg else (gs[0] if gs else m.group(0))
            if "gitleaks:allow" in line or (precise and (PLACEHOLDER.search(m.group(0)) or (rid == "gcp-api-key" and pubkey_ok(frag[m.end():frag.find("\n", m.end())])) or (rid == "jwt" and sec.endswith(".")))): continue
            if ent and entropy(sec) <= ent: continue
            if any(a.hit(sec, m.group(0), line, path) for a in glob + als): continue
            out.append(rid); break
    xf = frag.replace("\\n", "\n")  # a literal backslash-n (JSON, logs, one-line fixtures) is a line break for the extra rules
    for rid, rx, g, ent in EXTRA if precise else ():
        for m in rx.finditer(xf):
            if not PLACEHOLDER.search(m.group(0)) and entropy(m.group(g)) > ent and not (g and IDENT.fullmatch(m.group(g))) and "gitleaks:allow" not in xf[xf.rfind("\n", 0, m.start()) + 1:xf.find("\n", m.end())]:
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


def refilter(pat, files):
    """Print each file where ERE `pat` matches a line that is not a placeholder; unverifiable files (bad regex, no Python match, unreadable) are kept (fail closed)."""
    try: rx = re.compile(go2py(pat))
    except re.error: rx = None
    for f in files:
        try: lines = pathlib.Path(f).read_text("utf-8", "replace").split("\n")
        except OSError: lines = None
        if rx is None or lines is None or not any(rx.search(l) for l in lines) or any(not PLACEHOLDER.search(m.group(0)) and not (m.group(0).startswith("AIza") and pubkey_ok(l[m.end():])) for l in lines for m in rx.finditer(l)): print(f)


def main(argv):
    """Scan the files named in argv; exit 1 on any hit, 2 on an unreadable file or a bad rule (fail closed)."""
    if argv[:1] == ["--refilter"]: refilter(argv[1], argv[2:]); return 0
    if GL[2]: print(f"secret_scan: {GL[2]} gitleaks regexes failed to compile", file=sys.stderr); return 2
    allow = {l.split(None, 1)[1]: l.split()[0] for l in (R / "secret-scan-allow.txt").read_text().splitlines() if l and not l.startswith("#")}
    names = {posixpath.basename(a) for a in allow}
    hit = 0
    for f in argv:
        if posixpath.basename(f) in names and _allowed(f, allow): continue
        try: b = pathlib.Path(f).read_bytes()
        except OSError as e: print(f"secret_scan: cannot read {f}: {e.strerror}", file=sys.stderr); return 2
        if b"\0" in b[:8192]: continue
        ids = gitleaks_rule(b.decode("utf-8", "replace"), f, True)
        if ids: print(f"  {f} ({', '.join(ids)})"); hit = 1
    return hit


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
