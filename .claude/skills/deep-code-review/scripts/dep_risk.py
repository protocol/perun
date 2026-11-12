#!/usr/bin/env python3
"""Offline dependency-risk leads for a diff: new or changed dependencies only.

Usage: dep_risk.py --base REF < files   (one changed manifest path per line, run from the repo root)
Output: TSV rows `file<TAB>line<TAB>rule<TAB>message` on stdout; exit 0 even with leads.

Rules (every row is a lead for a reviewer, never a verdict; no network, no registry, no paid API):
  typosquat-near  a new name one edit away from a bundled popular name (separators ignored)
  vcs-or-url-dep  a git, URL, file or owner/repo shorthand spec: it bypasses registry integrity checks
  unpinned-dep    npm "*", "latest" or empty; a requirements line with no == pin (requirements*.txt, package.json)
  dependency-confusion  a requirements --index-url / --extra-index-url / -i line
  npm-alias       an "npm:" alias spec (a different package under this name); workspace: specs are fine
  install-script  package.json preinstall/install/postinstall/prepare, or a setup.py cmdclass override, added or changed
  not-checked     a manifest that could not be read or parsed (never read as clean)
Manifests: package.json, requirements*.txt, pyproject.toml (typosquat + vcs only), setup.py (cmdclass only).
Maintenance signals (age, last release, owners) are not derivable offline, so they are out of scope here.
"""
import json, os, re, subprocess, sys

NPM = "react react-dom lodash express axios chalk commander debug moment request webpack typescript eslint prettier jquery vue next jest mocha underscore async bluebird colors uuid dotenv cors mongoose redux yargs semver glob rimraf minimist tslib babel-core core-js".split()
PYPI = "requests numpy pandas django flask urllib3 boto3 botocore setuptools pip wheel pytest scipy matplotlib pillow cryptography pyyaml jinja2 click certifi idna six python-dateutil sqlalchemy tensorflow beautifulsoup4 colorama jsonschema paramiko lxml selenium openpyxl psycopg2 aiohttp".split()
STRIP = re.compile(r"[-_.]+")


def lev1(a, b):
    """True when a and b differ by exactly one insert, delete, substitute or adjacent swap."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, l = sorted((a, b), key=len)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def squat(name, eco):
    """The popular name `name` imitates, or None. Exact (or, for PyPI, separator-normalized) matches are the real package."""
    n = name.lower()
    if n.startswith("@"):
        return None  # scoped npm names are owned by their scope
    for t in NPM if eco == "npm" else PYPI:
        if (STRIP.sub("-", n) if eco == "pypi" else n) == (STRIP.sub("-", t) if eco == "pypi" else t):
            return None
    for t in NPM if eco == "npm" else PYPI:
        a, b = STRIP.sub("", n), STRIP.sub("", t)
        sib = lambda x, y: len(x) == len(y) + 1 and x[-1] in "s0123456789" and x[:-1] == y  # plural or version sibling (color/colors, boto/boto3): a real package
        if len(b) >= 5 and not sib(a, b) and not sib(b, a) and (a == b or lev1(a, b)):
            return t
    return None


def spec_rules(name, spec, eco):
    """Rule names for one (name, spec) pair; spec is a version/range string."""
    s, out = spec.strip(), []
    if re.match(r"(git\+|git:|git@|ssh:|https?:|file:|github:|gitlab:|bitbucket:|link:|\.{0,2}/)", s) or (eco == "npm" and re.fullmatch(r"[\w.-]+/[\w.-]+(#.*)?", s)):
        out.append("vcs-or-url-dep")
    elif eco == "npm" and s.startswith("npm:"):
        out.append("npm-alias")
    elif eco == "npm" and s in ("", "*", "latest", "x"):
        out.append("unpinned-dep")
    return out


def git(*a):
    r = subprocess.run(["git", *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def lineof(text, needle):
    for i, ln in enumerate(text.split("\n"), 1):
        if needle in ln:
            return i
    return 0


def pkg_json(f, base, row):
    cur = json.loads(open(f, encoding="utf-8").read())
    old = {}
    prev = git("show", f"{base}:{f}")
    if prev:
        try:
            old = json.loads(prev)
        except ValueError:
            pass
    text = open(f, encoding="utf-8").read()
    for sec in ("dependencies", "devDependencies", "optionalDependencies"):
        for n, v in (cur.get(sec) or {}).items():
            if not isinstance(v, str) or v == (old.get(sec) or {}).get(n):
                continue
            ln = lineof(text, json.dumps(n))
            t = squat(n, "npm")
            if t:
                row(f, ln, "typosquat-near", f"{n} is one edit from the popular package {t}; confirm it is the intended name [heuristic]")
            for r in spec_rules(n, v, "npm"):
                row(f, ln, r, f"{n}@{v} ({sec}): " + ("fetched from a git/URL/path source, outside registry integrity checks" if r == "vcs-or-url-dep" else "floating spec: any published version installs" if r == "unpinned-dep" else "npm: alias installs a different package under this name"))
    for k in ("preinstall", "install", "postinstall", "prepare"):
        v = (cur.get("scripts") or {}).get(k)
        if isinstance(v, str) and v != (old.get("scripts") or {}).get(k):
            row(f, lineof(text, json.dumps(k)), "install-script", f"scripts.{k} runs on every consumer install: read it (`{v[:60]}`)")


REQ = re.compile(r"^\s*(?:-e\s+)?([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def pip_line(f, ln, line, row, strict):
    s = line.split("#")[0].strip()
    if re.match(r"(--(extra-)?index-url|-i)\b", s):
        row(f, ln, "dependency-confusion", f"`{s[:70]}`: a package index override; a same-named package on a public index can win over a private one")
        return
    if not s or s.startswith(("-r", "-c", "--")):
        return
    vcs = bool(re.match(r"(-e\s+)?(git\+|https?:|file:|\.{0,2}/)", s) or " @ " in s)
    if vcs:
        row(f, ln, "vcs-or-url-dep", f"`{s[:70]}`: fetched from a git/URL/path source, outside registry integrity checks")
    m = REQ.match(s)
    if not m:
        return
    t = squat(m.group(1), "pypi")
    if t:
        row(f, ln, "typosquat-near", f"{m.group(1)} is one edit from the popular package {t}; confirm it is the intended name [heuristic]")
    if strict and not vcs and not re.search(r"===?|--hash", m.group(3) + " " + line):
        row(f, ln, "unpinned-dep", f"{m.group(1)}: no == pin, any release installs")


def added(f, base):
    """(line number, text) for lines this diff adds to f; the whole file when base has none."""
    d = git("diff", "-U0", "--no-color", base, "--", f)
    if d is None:
        raise OSError("git diff failed")
    out, n = [], 0
    for ln in d.split("\n"):
        m = re.match(r"@@ -\S+ \+(\d+)", ln)
        if m:
            n = int(m.group(1))
        elif ln.startswith("+") and not ln.startswith("+++"):
            out.append((n, ln[1:]))
            n += 1
    return out


def main():
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "HEAD"
    rows = []
    row = lambda f, l, r, m: rows.append(f"{f}\t{l}\t{r}\t{m}")
    for f in filter(None, (x.strip() for x in sys.stdin)):
        b = os.path.basename(f)
        try:
            if b == "package.json":
                pkg_json(f, base, row)
            elif re.fullmatch(r"[^/]*requirements[^/]*\.txt", b):
                for n, t in added(f, base):
                    pip_line(f, n, t, row, True)
            elif b == "setup.py":
                for n, t in added(f, base):
                    if re.search(r"\bcmdclass\b", t):
                        row(f, n, "install-script", "setup.py cmdclass overrides an install/build command: it runs code on the consumer's machine at install")
            elif b == "pyproject.toml":
                import tomllib
                d = tomllib.load(open(f, "rb"))
                p = d.get("project", {})
                want = {STRIP.sub("-", m.group(1).lower()) for _, t in added(f, base) for q in re.findall(r'"([^"]+)"', t) if (m := REQ.match(q))}
                for dep in [*p.get("dependencies", []), *[x for v in p.get("optional-dependencies", {}).values() for x in v]]:
                    if (m := REQ.match(dep)) and STRIP.sub("-", m.group(1).lower()) in want:
                        pip_line(f, lineof(open(f, encoding="utf-8").read(), dep), dep, row, False)
        except Exception as e:  # unreadable, unparseable, or no tomllib: say so, never read as clean
            row(f, 0, "not-checked", f"dep-risk could not read {f}: {type(e).__name__}")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
