#!/usr/bin/env python3
"""gh_rest.py — curl REST fallback for `gh api` when gh's Go TLS fails inside a macOS sandbox.

WHY: in a Claude Code macOS sandbox gh fails with `x509: OSStatus -26276` / `failed to verify certificate`
while curl works. Every shipped script that calls `gh api` routes through `fallback()` (Python) or uses this
file as its GH command (shell), so the fix lives in one place.

Python: `rc, out, err = fallback(args, rc, out, err)` returns its input unchanged unless `args` is a
`gh api` call whose result shows that TLS error; then it retries the same GET (or -X/--input write) with curl.
Shell: `gh_rest.py <gh args>` runs gh and does the same; stdout/stderr/exit code pass through.
Supported: `gh api [--paginate] [-X METHOD] [--input FILE] PATH` (`{owner}/{repo}` resolves from the origin
remote). Not supported (original failure returned, with a cause line): `gh pr ...`, -f/-F/-H/-q flags.
Token: GH_TOKEN, GITHUB_TOKEN, else `gh auth token`. Side effects: HTTPS calls to api.github.com only; never
changes any setting. Paginated output is back-to-back JSON arrays, as `gh api --paginate` prints them.
"""
import json, os, re, subprocess, sys

TLS = re.compile(r"OSStatus -26276|failed to verify certificate")
UNSUPPORTED = "gh_rest: TLS error and no curl fallback for this call (only plain `gh api PATH`, --paginate, -X, --input)"


def _slug():
    u = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?\s*$", u)
    return m.group(1) if m else None


def _token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return t or subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()


def _curl(url, token, method, body, timeout):
    cmd = ["curl", "-sS", "-i", "-X", method, "-K", "-", "-H", "Accept: application/vnd.github+json"]
    if body:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", f"@{body}"]
    p = subprocess.run(cmd + [url], capture_output=True, text=True, timeout=timeout,
                       input=f'header = "Authorization: Bearer {token}"\n')  # token via stdin, not argv
    head, _, text = p.stdout.partition("\n\n")  # text mode folds CRLF
    while text.startswith("HTTP/"):  # a proxy's CONNECT reply comes first: the real response is the next block
        head, _, text = text.partition("\n\n")
    m = re.match(r"HTTP/\S+ (\d+)", head)
    status = int(m.group(1)) if m else 0
    nxt = re.search(r'<([^>]+)>;\s*rel="next"', head)
    return p.returncode or (0 if 200 <= status < 300 else 1), text, p.stderr or f"HTTP {status}: {text[:200]}", nxt and nxt.group(1)


def fallback(args, rc, out, err, timeout=300):
    """See module doc. Returns (rc, out, err); the input tuple when no fallback applies."""
    if rc == 0 or not TLS.search(err or ""):
        return rc, out, err
    if args[:2] != ["gh", "api"]:
        return rc, out, err + "\n" + UNSUPPORTED
    method, body, pages, path, it = None, None, False, None, iter(args[2:])
    for a in it:
        if a == "--paginate":
            pages = True
        elif a in ("-X", "--method"):
            method = next(it, None)
        elif a == "--input":
            body = next(it, None)
        elif a.startswith("-") or path:
            return rc, out, err + "\n" + UNSUPPORTED
        else:
            path = a
    method = method or ("POST" if body else "GET")  # gh api: --input implies POST
    try:
        if "{owner}" in (path or ""):
            path = path.replace("{owner}/{repo}", _slug() or "{owner}")
        token = _token()
        if not path or not token or "{owner}" in path or "//" in path:
            return rc, out, err + "\ngh_rest: no token or repo for curl fallback"
        url, text = "https://api.github.com/" + path.lstrip("/"), ""
        while url:
            r, o, e, url = _curl(url, token, method, body, timeout)
            if r:
                return r, text, e
            text += o
            url = url if pages else None
        return 0, text, ""
    except (OSError, subprocess.SubprocessError) as e:
        return rc, out, f"{err}\ngh_rest: curl fallback failed: {e}"


def main(argv):
    try:
        p = subprocess.run(["gh", *argv], capture_output=True, text=True)
    except OSError as e:
        print(f"gh_rest: cannot run gh: {e}", file=sys.stderr)
        return 127
    rc, out, err = fallback(["gh", *argv], p.returncode, p.stdout, p.stderr)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
