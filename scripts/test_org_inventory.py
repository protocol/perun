#!/usr/bin/env python3
"""Tests: org_inventory.py against a fake in-process GitHub API (no network, fictional acme-org data): pagination, Link header paging, TSV columns, --previous reconcile and malformed-previous exit 2, --results-dir NOT CHECKED (missing, stale, empty, wrong-name files), count mismatch, empty listing, HTTP and unexpected errors all exit 2 with no TSV, https-only --api-url, page cap, off-host Link, and redirect auth stripping."""
import contextlib
import http.client
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "org_inventory.py")
REPOS = [{"name": f"repo-{i:03d}", "visibility": "public", "archived": i == 1, "fork": i == 2, "has_wiki": True,
          "pushed_at": "2026-01-01T00:00:00Z"} for i in range(103)]


class Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def resp(obj, link=""):
    r = Resp(json.dumps(obj).encode())
    r.headers = {"Link": link} if link else {}
    return r


def fake_open(req, timeout=None):
    """Stands in for the GitHub API: no socket is ever opened."""
    url = req.full_url
    org, listing = url.split("/")[4].split("?")[0], "/repos" in url
    if org == "denied-org":
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    if org == "boom-org":
        raise http.client.IncompleteRead(b"x")
    totals = {"public_repos": {"empty-org": 0, "mismatch-org": 105}.get(org, 103)}
    if org == "priv-org":
        totals["total_private_repos"] = 2  # visible to the token, but none listed
    if not listing:
        return resp(totals)
    if org == "weird-org":
        return resp({"message": "nope"})
    if org == "empty-org":
        return resp([])
    if org == "keyerr-org":
        return resp([{"nope": 1}])
    if org == "link-org":  # Link header drives paging: page 1 is short (60) yet has a next link
        if url.endswith("&page=1"):
            return resp(REPOS[:60], '<https://api.github.com/orgs/link-org/repos?type=all&per_page=100&page=2>; rel="next"')
        return resp(REPOS[60:])
    if org == "offhost-org":
        return resp(REPOS[:100], '<https://evil.example.com/x?page=2>; rel="next"')
    if org == "loop-org":
        return resp(REPOS[:100], '<https://api.github.com/orgs/loop-org/repos?page=2>; rel="next"')
    return resp(REPOS[:100] if url.endswith("&page=1") else REPOS[100:])


def run(*args, token="tok"):
    """Run org_inventory.main() in-process with the fake API; returns (exit code, stdout, stderr)."""
    spec = importlib.util.spec_from_file_location("org_inventory", S)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.OPEN = fake_open
    m.MAX_PAGES = 5
    m.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout="")  # `gh auth token` yields nothing
    os.environ.pop("GITHUB_TOKEN", None)
    if token:
        os.environ["GITHUB_TOKEN"] = token
    out, err, code = io.StringIO(), io.StringIO(), 0
    sys.argv = ["org_inventory.py", *args]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = m.main()
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def main():
    n = 0

    def check(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            sys.exit(f"FAIL: {msg}")

    with tempfile.TemporaryDirectory() as t:
        out, res = os.path.join(t, "out"), os.path.join(t, "res")
        os.makedirs(res)
        c, so, se = run("--org", "acme-org", "--out", out)
        check(c == 0 and "103 repos" in so, f"listing: {c} {so} {se}")
        tsv = os.path.join(out, os.listdir(out)[0])
        lines = open(tsv).read().splitlines()
        check(lines[0].split("\t") == ["org", "repo", "visibility", "archived", "fork", "has_wiki", "pushed_at"], "header")
        check(len(lines) == 104 and lines[2].split("\t")[3] == "true" and lines[3].split("\t")[4] == "true", "rows/pagination")
        prev = os.path.join(t, "prev.tsv")
        with open(prev, "w") as fh:
            fh.write("\n".join(lines[:-1] + ["org\trepo", "acme-org\tgone-repo"][1:]) + "\n")
        c, so, se = run("--org", "acme-org", "--out", out, "--previous", prev)
        check("added 1, removed 1" in so and "added: acme-org/repo-102" in so
              and "removed: acme-org/gone-repo" in so, f"reconcile: {so}")
        for i in range(102):
            with open(os.path.join(res, f"acme-org__repo-{i:03d}.json"), "w") as fh:
                fh.write("{}")
        old = os.path.join(res, "acme-org__repo-005.json")
        os.utime(old, (time.time() - 40 * 86400,) * 2)
        c, so, se = run("--org", "acme-org", "--out", out, "--results-dir", res)
        check(c == 1 and so.count("NOT CHECKED") == 2 and "NOT CHECKED: acme-org/repo-005" in so
              and "NOT CHECKED: acme-org/repo-102" in so, f"not checked: {so}")
        c, so, se = run("--org", "acme-org", "--out", out, "--results-dir", res, "--max-age-days", "60")
        check(so.count("NOT CHECKED") == 1, "max-age-days")
        for org in ("denied-org", "weird-org", "empty-org", "mismatch-org", "priv-org", "keyerr-org", "boom-org", "offhost-org", "loop-org"):
            o2 = os.path.join(t, org)
            c, so, se = run("--org", org, "--out", o2)
            check(c == 2 and not os.path.exists(o2), f"{org} must exit 2, no TSV: {c}")
        c, so, se = run("--org", "acme-org", "--org", "denied-org", "--out", os.path.join(t, "o3"))
        check(c == 2 and not os.path.exists(os.path.join(t, "o3")), "partial org failure")
        o4 = os.path.join(t, "o4")
        c, so, se = run("--org", "link-org", "--out", o4)
        check(c == 0 and "103 repos" in so, f"Link header paging: {c} {so} {se}")
        for bad in ("http://api.github.com", "ftp://x.example.com"):
            c, so, se = run("--org", "acme-org", "--out", o4, "--api-url", bad)
            check(c == 2 and "https" in se, f"--api-url {bad} must exit 2")
        c, so, se = run("--org", "acme-org", "--out", o4, "--api-url", "http://localhost:1")
        check(c == 0, "http localhost allowed")
        for name, body in (("hdr", "org\trepo\n"), ("junk", "hello\n"), ("empty", "")):
            p = os.path.join(t, name + ".tsv")
            with open(p, "w") as fh:
                fh.write(body if name != "hdr" else "\t".join(["org", "repo", "visibility", "archived", "fork", "has_wiki", "pushed_at"]) + "\n")
            c, so, se = run("--org", "acme-org", "--out", o4, "--previous", p)
            check(c == 2 and "malformed" in se, f"--previous {name} must exit 2: {c} {se}")
        with open(os.path.join(res, "acme-org__repo-102.json"), "w"):
            pass  # zero-byte result is not a result
        c, so, se = run("--org", "acme-org", "--out", o4, "--results-dir", res)
        check("NOT CHECKED: acme-org/repo-102" in so, "empty result file must not count")
        with open(os.path.join(res, "repo-102.json"), "w") as fh:
            fh.write("{}")  # bare repo name (old naming) must not match either
        c, so, se = run("--org", "acme-org", "--out", o4, "--results-dir", res)
        check("NOT CHECKED: acme-org/repo-102" in so, "only org__repo.* matches")
        spec = importlib.util.spec_from_file_location("oi", S)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        req = urllib.request.Request("https://api.github.com/x", headers={"Authorization": "Bearer t"})
        h = m.NoAuthRedirect()
        off = h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/y")
        same = h.redirect_request(req, None, 302, "Found", {}, "https://api.github.com/z")
        check(not any(k.lower() == "authorization" for k in off.headers) and not off.unredirected_hdrs.get("Authorization"), "token must not follow an off-host redirect")
        check(any(k.lower() == "authorization" for k in same.headers), "same-host redirect keeps auth")
        c, so, se = run("--org", "acme-org", "--out", out, token="")
        check(c == 2 and "no token" in se, "missing token")
    print(f"Tests: {n}/{n}")


if __name__ == "__main__":
    main()
