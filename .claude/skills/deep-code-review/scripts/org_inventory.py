#!/usr/bin/env python3
"""org_inventory.py: dated TSV inventory of every repo in one or more GitHub orgs, reconciled against a previous run and a results dir.

Usage: org_inventory.py --org ORG [--org ORG ...] [--out DIR] [--previous TSV] [--results-dir DIR] [--max-age-days N]
                        [--token-env VAR] [--api-url URL]

Writes `<out>/inventory-YYYYMMDD.tsv` with header `org<TAB>repo<TAB>visibility<TAB>archived<TAB>fork<TAB>has_wiki<TAB>pushed_at`
(columns: repo is the bare name; archived/fork/has_wiki are true|false). Read-only: GET /orgs/ORG/repos?type=all, paginated.
Token: env var named by --token-env (default GITHUB_TOKEN), else `gh auth token`; none = exit 2. Any HTTP error, bad JSON,
non-list reply (missing scope, 401/403/404, rate limit), unexpected exception, empty listing, more than 1000 pages, or a
listed count that differs from the org totals (GET /orgs/ORG: public_repos, plus total_private_repos when visible) is a
loud exit 2 and no TSV: a failed listing is never zero repos. Pagination follows the Link rel=next header when present,
else stops on the first short page. --api-url must be https (http only for localhost, for tests); the token is never sent
to another host (redirects drop it, a cross-host Link is an error).
--previous TSV (an earlier inventory; must have the exact header and at least one row, else exit 2) prints added and
removed repo counts and names. --results-dir DIR prints `NOT CHECKED: org/repo` for every repo with no non-empty file
`<org>__<repo>.*` in DIR modified within --max-age-days (default 30), and exits 1 if any exist (0 = every repo has a fresh
result). Exit codes: 0 ok, 1 unchecked repos, 2 usage/API error.
Side effects: network GETs to the API only; writes only the inventory TSV under --out (default $TMPDIR/org-inventory).
"""
import argparse, csv, datetime, glob, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

MAX_PAGES = 1000
COLS = ["org", "repo", "visibility", "archived", "fork", "has_wiki", "pushed_at"]


def fail(msg):
    print(f"org_inventory: {msg}", file=sys.stderr)
    raise SystemExit(2)


class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Drops the Authorization header when a redirect leaves the original host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.headers = {k: v for k, v in new.headers.items() if k.lower() != "authorization"}
            new.unredirected_hdrs.pop("Authorization", None)
        return new


OPEN = urllib.request.build_opener(NoAuthRedirect).open


def get_json(url, token):
    """GET url -> (parsed JSON, Link header). Every failure is a loud exit 2."""
    where = url.split("?")[0]
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"})
    try:
        with OPEN(req, timeout=30) as r:
            return json.load(r), r.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        fail(f"HTTP {e.code} on {where} (missing scope or access?); inventory NOT written")
    except Exception as e:  # URLError, IncompleteRead, bad JSON, timeout: never a traceback, never zero repos
        fail(f"{type(e).__name__} on {where}; inventory NOT written")


def next_link(link):
    m = re.search(r'<([^>]+)>\s*;\s*rel="next"', link)
    return m.group(1) if m else None


def list_org(api, org, token):
    info, _ = get_json(f"{api}/orgs/{org}", token)
    if not isinstance(info, dict) or not isinstance(info.get("public_repos"), int):
        fail(f"{org}: org totals missing in API reply; inventory NOT written")
    rows, url, host = [], f"{api}/orgs/{org}/repos?type=all&per_page=100&page=1", urllib.parse.urlsplit(api).netloc
    for page in range(1, MAX_PAGES + 1):
        batch, link = get_json(url, token)
        if not isinstance(batch, list):
            fail(f"unexpected reply from {url.split('?')[0]}; inventory NOT written")
        try:
            for x in batch:
                rows.append([org, x["name"], x.get("visibility") or ("private" if x.get("private") else "public"),
                             str(bool(x.get("archived"))).lower(), str(bool(x.get("fork"))).lower(),
                             str(bool(x.get("has_wiki"))).lower(), x.get("pushed_at") or ""])
        except (KeyError, TypeError, AttributeError):
            fail(f"malformed repo entry on {url.split('?')[0]}; inventory NOT written")
        nxt = next_link(link) if link else (None if len(batch) < 100 else f"{api}/orgs/{org}/repos?type=all&per_page=100&page={page + 1}")
        if nxt is None:
            break
        if urllib.parse.urlsplit(nxt).netloc != host:
            fail(f"Link header points off-host ({urllib.parse.urlsplit(nxt).netloc}); inventory NOT written")
        url = nxt
    else:
        fail(f"{org}: more than {MAX_PAGES} pages; inventory NOT written")
    pub = sum(r[2] == "public" for r in rows)
    bad = pub != info["public_repos"]
    if isinstance(info.get("total_private_repos"), int):
        bad = bad or len(rows) - pub != info["total_private_repos"]
    if not rows or bad:
        fail(f"{org}: listed {len(rows)} repos ({pub} public) but org totals say {info['public_repos']} public"
             f" + {info.get('total_private_repos', 'unknown')} private; token scope too narrow? inventory NOT written")
    return rows


def fresh(results_dir, org, repo, max_age_days):
    cutoff = time.time() - max_age_days * 86400
    pat = os.path.join(glob.escape(results_dir), glob.escape(f"{org}__{repo}") + ".*")
    return any(os.path.getsize(p) > 0 and os.path.getmtime(p) >= cutoff for p in glob.glob(pat))


def _main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--org", action="append", required=True)
    ap.add_argument("--out", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "org-inventory"))
    ap.add_argument("--previous")
    ap.add_argument("--results-dir")
    ap.add_argument("--max-age-days", type=float, default=30)
    ap.add_argument("--token-env", default="GITHUB_TOKEN")
    ap.add_argument("--api-url", default="https://api.github.com")
    a = ap.parse_args()
    token = os.environ.get(a.token_env, "")
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        except OSError:
            pass
    if not token:
        fail(f"no token: set {a.token_env} or run `gh auth login`")
    prev = None
    if a.previous:
        if not os.path.isfile(a.previous):
            fail(f"--previous {a.previous} not found")
        with open(a.previous, newline="") as fh:
            rd = csv.DictReader(fh, delimiter="\t")
            prev = {(r["org"], r["repo"]) for r in rd}
            cols = rd.fieldnames
        if cols != COLS or not prev or any(not o or not r for o, r in prev):
            fail(f"--previous {a.previous} is malformed or has no repos (want header {COLS} and at least one row)")
    if a.results_dir and not os.path.isdir(a.results_dir):
        fail(f"--results-dir {a.results_dir} not a directory")
    api = a.api_url.rstrip("/")
    u = urllib.parse.urlsplit(api)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1")):
        fail(f"--api-url must be https (http only for localhost): {api}")
    rows = []
    for org in a.org:
        rows += list_org(api, org, token)
    os.makedirs(a.out, mode=0o700, exist_ok=True)
    path = os.path.join(a.out, f"inventory-{datetime.date.today():%Y%m%d}.tsv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(COLS)
        w.writerows(rows)
    print(f"org_inventory: {len(rows)} repos, inventory {path}")
    if prev is not None:
        now = {(r[0], r[1]) for r in rows}
        added, removed = sorted(now - prev), sorted(prev - now)
        print(f"reconcile: previous {len(prev)}, now {len(now)}, added {len(added)}, removed {len(removed)}")
        for tag, items in (("added", added), ("removed", removed)):
            for o, r in items:
                print(f"{tag}: {o}/{r}")
    bad = 0
    if a.results_dir:
        for r in rows:
            if not fresh(a.results_dir, r[0], r[1], a.max_age_days):
                print(f"NOT CHECKED: {r[0]}/{r[1]}")
                bad += 1
    return 1 if bad else 0


def main():
    try:
        return _main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:  # fail closed: any unexpected error is exit 2, never a traceback or a partial TSV
        fail(f"unexpected {type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
