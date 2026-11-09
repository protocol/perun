#!/usr/bin/env python3
"""org_leak_sweep.py: sweep every public repo of a GitHub org (or one local repo) for secrets and banned terms across full history.

Usage: org_leak_sweep.py --org ORG [--banlist FILE] [--out DIR] [--token-env VAR]
       org_leak_sweep.py --local REPO [--banlist FILE] [--out DIR]    (no network; used by the test)

Per repo: `git clone --mirror`, then `gitleaks detect --redact` over all history, then a banlist regex grep over every
added line of `git log --all -p`. The banlist is one case-insensitive regex per line ('#' and blank lines skipped); it
is NEVER committed, default `.banlist.local.txt`. A missing or empty banlist fails closed (exit 2) unless --no-banlist.
Output: `<out>/leaks.tsv` with header `repo<TAB>file<TAB>commit<TAB>rule` (rule = gitleaks RuleID or `banlist:<line no>`;
no secret value, no matched term, no message text ever written). `--out` must not be inside a git work tree (private dir,
created 0700; default $TMPDIR/org-leak-sweep). Org listing uses curl + `gh auth token` (or the env var named by
--token-env) against api.github.com, public repos only; mirrors live under <out>/mirrors and are deleted after scanning.
Edge cases: empty org = header-only TSV; gitleaks missing = exit 3 (never a clean result); a repo that fails to clone or
scan is an `ERROR` row and exit 1 at the end. Exit 0 = swept, no hits; 1 = hits or errors; 2 = usage; 3 = tool missing.
Side effects: network (listing and clones) only in --org mode; writes only under --out.
"""
import argparse, csv, json, os, re, shutil, subprocess, sys, tempfile


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def list_repos(org, token):
    names, page = [], 1
    while True:
        url = f"https://api.github.com/orgs/{org}/repos?type=public&per_page=100&page={page}"
        cfg = ""
        if token:  # via stdin config so the token never shows in argv
            cfg = 'header = "Authorization: Bearer ' + token.replace("\\", "\\\\").replace('"', '\\"') + '"\n'
        r = run(["curl", "-fsS", "-H", "Accept: application/vnd.github+json", "--config", "-", url], input=cfg)
        if r.returncode:
            sys.exit(f"org_leak_sweep: listing failed (curl exit {r.returncode}); not clean")
        batch = json.loads(r.stdout)
        names += [(x["name"], x["clone_url"]) for x in batch]
        if len(batch) < 100:
            return names
        page += 1


def gitleaks_rows(mirror, tmp):
    rep = os.path.join(tmp, "gl.json")
    r = run(["gitleaks", "detect", "--source", mirror, "--redact", "--no-banner", "--report-format", "json",
             "--report-path", rep, "--exit-code", "0"])
    if r.returncode:
        raise RuntimeError("gitleaks failed")
    with open(rep) as fh:
        rows = json.load(fh) or []
    os.remove(rep)
    return [(x["File"], x["Commit"][:12], x["RuleID"]) for x in rows]


SECRET_RX = re.compile(r"(ghp_|gho_|ghs_|ghu_|ghr_|github_pat_|AKIA|ASIA|xox[baprs]-|[sr]k_live_)[A-Za-z0-9_-]{8,}")
ESC = {"n": 10, "t": 9, "\\": 92, '"': 34, "a": 7, "b": 8, "f": 12, "r": 13, "v": 11}


def unquote(path):
    """Undo git's C-style path quoting; None if it cannot be parsed (caller scans anyway)."""
    path = path.rstrip("\n")
    if not path.startswith('"'):
        return path.rstrip("\t")
    if len(path) < 2 or not path.endswith('"'):
        return None
    raw, i, body = bytearray(), 0, path[1:-1]
    while i < len(body):
        c = body[i]
        if c != "\\":
            raw += c.encode()
            i += 1
        elif i + 1 < len(body) and body[i + 1] in ESC:
            raw.append(ESC[body[i + 1]])
            i += 2
        elif re.fullmatch(r"[0-7]{3}", body[i + 1:i + 4]):
            raw.append(int(body[i + 1:i + 4], 8))
            i += 4
        else:
            return None
    return raw.decode("utf-8", "replace")


def redact_name(f, pats):
    return "<redacted>" if SECRET_RX.search(f) or any(rx.search(f) for _, rx in pats) else f


def banlist_rows(mirror, pats):
    p = subprocess.Popen(["git", "-C", mirror, "-c", "core.quotepath=off", "log", "--all", "-p", "--no-color",
                          "--format=\x01%H"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace")
    commit, f, header = "", "?unparsed", False
    seen, rows = set(), []
    for line in p.stdout:
        if line.startswith("\x01"):
            commit, header = line[1:].strip()[:12], False
        elif line.startswith("diff --git "):
            f, header = "?unparsed", True  # file headers count only from here to the first hunk
        elif header and (line.startswith("--- ") or line.startswith("+++ ")):
            if line[4:].startswith("/dev/null"):
                continue
            name = unquote(line[4:])
            if name is not None and name[:2] in ("a/", "b/"):
                f = name[2:]
        elif line.startswith("@@"):
            header = False
        elif not header and line.startswith("+"):
            for n, rx in pats:
                if rx.search(line[1:]) and (f, commit, n) not in seen:
                    seen.add((f, commit, n))
                    rows.append((f, commit, f"banlist:{n}"))
    if p.wait():
        raise RuntimeError("git log failed")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--org")
    g.add_argument("--local", help="scan this one local repo, no network")
    ap.add_argument("--banlist", default=".banlist.local.txt")
    ap.add_argument("--no-banlist", action="store_true")
    ap.add_argument("--out", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "org-leak-sweep"))
    ap.add_argument("--token-env", help="env var holding a token; default `gh auth token`")
    a = ap.parse_args()
    if not shutil.which("gitleaks"):
        print("NOT CHECKED: gitleaks (install: brew install gitleaks)", file=sys.stderr)
        return 3
    pats = []
    if not a.no_banlist:
        if not os.path.isfile(a.banlist):
            print(f"org_leak_sweep: banlist {a.banlist} missing (fail closed; --no-banlist to skip)", file=sys.stderr)
            return 2
        with open(a.banlist, errors="replace") as fh:
            for n, l in enumerate(fh, 1):
                l = l.strip()
                if l and not l.startswith("#"):
                    try:
                        pats.append((n, re.compile(l, re.I)))
                    except re.error:
                        print(f"org_leak_sweep: banlist line {n} is not a valid regex", file=sys.stderr)
                        return 2
        if not pats:
            print("org_leak_sweep: banlist has no patterns (fail closed)", file=sys.stderr)
            return 2
    out = os.path.abspath(a.out)
    top = out
    while not os.path.isdir(top):
        top = os.path.dirname(top)
    if run(["git", "-C", top, "rev-parse", "--is-inside-work-tree"]).returncode == 0:
        print("org_leak_sweep: --out is inside a git work tree; pick a private dir", file=sys.stderr)
        return 2
    os.makedirs(out, mode=0o700, exist_ok=True)
    if a.org:
        token = os.environ.get(a.token_env, "") if a.token_env else run(["gh", "auth", "token"]).stdout.strip()
        repos = list_repos(a.org, token)
    else:
        repos = [(os.path.basename(os.path.abspath(a.local)), os.path.abspath(a.local))]
    bad = False
    with open(os.path.join(out, "leaks.tsv"), "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["repo", "file", "commit", "rule"])
        for name, url in repos:
            mirror = os.path.join(out, "mirrors", name + ".git")
            try:
                shutil.rmtree(mirror, ignore_errors=True)
                os.makedirs(os.path.dirname(mirror), exist_ok=True)
                if run(["git", "clone", "--mirror", "-q", "--", url, mirror]).returncode:
                    raise RuntimeError("clone failed")
                with tempfile.TemporaryDirectory(dir=out) as tmp:
                    rows = gitleaks_rows(mirror, tmp) + banlist_rows(mirror, pats)
                for f, c, rule in rows:
                    w.writerow([name, redact_name(f, pats), c, rule])
                    bad = True
            except Exception as e:
                w.writerow([name, "", "", f"ERROR:{type(e).__name__}"])
                bad = True
            finally:
                shutil.rmtree(mirror, ignore_errors=True)
    print(f"org_leak_sweep: {len(repos)} repos, report {os.path.join(out, 'leaks.tsv')}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
