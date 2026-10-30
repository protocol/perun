#!/usr/bin/env python3
"""repo_settings_audit.py: read-only audit of the GitHub settings that decide who can change a repository and what its CI may do.

WHY: a clean code review says nothing about a default branch anyone can force-push, a workflow token that can write,
a deploy key that can push, or a webhook that skips TLS verification. Those live in repository settings, not in the
diff, and they decide whether a review gate is worth anything. This lists them per repository, one row each: repo,
check, severity, one-line fix. It reuses `pipeline_hub.gh_get` (bare `gh api` GET, with `gh_rest.fallback` for the
macOS-sandbox TLS failure) and adds no analysis engine.

Checks, per repository:
  default branch    classic branch protection and rulesets (`/rules/branches/{branch}`) together: no protection,
                    force pushes allowed, fewer than 1 required approving review, no required status checks, admins
                    exempt (classic `enforce_admins`)
  Actions           default workflow token has write, workflows can approve pull request reviews, allowed actions = all
  people            collaborator counts: admins, outside collaborators
  deploy keys       keys with write access (count)
  webhooks          TLS verification off (`insecure_ssl`), plain http delivery (counts)
  environments      environments with no protection rule (count)
  security          secret scanning and push protection, from `security_and_analysis` (a private or internal
                    organization repository needs GitHub Secret Protection for either; the fix text says so)

A call the token cannot make (HTTP 403 or 404) is a `not checked (needs admin)` row, never a clean result. So is a
reply that lacks a field the check reads, and a list of 1000 items or more (see Limits). A list holding one item the
audit cannot read is `not checked` as a whole, since a count of it would be wrong. One reading is a finding on its
own: a 404 `Branch not protected` on a branch no ruleset covers means the branch has no protection, but only when
the repository reply shows admin for the token (`permissions.admin` true). The branch-protection REST page does not
say what a token without admin gets for a protected branch, so with any other token (admin false, or the field
missing) that 404 is `not checked`. A weakness inside the protection (force pushes, reviews, checks) is reported
only when classic protection and rulesets were both readable, since either can fill what the other lacks. Not read:
ruleset bypass lists (a `not checked` row says so whenever rulesets apply).

USAGE: repo_settings_audit.py OWNER/NAME [OWNER/NAME ...] [--repos-file FILE] [--json]
`--repos-file` holds one OWNER/NAME per line (blank lines and `#` comments ignored). A repository twice, in any case,
is audited once. `--json` prints `{"rows": [{repo, check, severity, fix}], "summary": {repos, findings, not_checked}}`.
Severity is high, medium, low, info (a count with nothing to fix) or not-checked.

Exit codes: 0 the audit ran (findings do not change it), 2 usage: a bad slug, no repository, an unreadable
--repos-file, or `gh` not on PATH.
Side effects: `gh api` GET calls only (about a dozen per repository); nothing is written or changed.
Limits: counts and booleans only. No login, email, key title or hook URL is printed, and no API message text, only
fixed phrases. A list is read 100 items a page for up to 10 pages; one that fills all ten (1000 items or more) is
`not checked`, not a truncated count. An archived repository is audited like any other. The full set needs an admin
token (admin on the repository, plus an org owner or security manager for `security_and_analysis`); with less, the
rows that need it say so.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_profile as pp  # noqa: E402
from pipeline_hub import gh_get  # noqa: E402

SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/(?!\.{1,2}$)[A-Za-z0-9_.-]+")  # no `..` or `.`: the slug goes into a URL path
SEVERITY = ("high", "medium", "low", "info", "not-checked")
FINDING = SEVERITY[:3]
MAX_PAGES = 10  # ponytail: 1000 items per list; a list that fills every page is `not checked`, raise if one ever matters
NEEDS_ADMIN = ("needs admin", "re-run with a token that has admin access to the repository")
NOT_FOUND = ("not found or no access", "check the OWNER/NAME slug and that the token can see the repository")
NOT_REPORTED = ("not reported by the API", "check it in the repository settings, or re-run with a token that has admin access to the repository")
UNEXPECTED, TOO_MANY = "unexpected reply", "too many items"  # error texts `why` turns into fixed `not checked` rows


def dig(d, *keys):
    """d[k1][k2]... or None as soon as a step is missing or not a dict (a surprising reply never raises)."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def has(d, need=()):
    """True when d is an object carrying every key path in `need` with a non-null value (a missing field is never
    read as a clean one)."""
    return isinstance(d, dict) and all(dig(d, *p) is not None for p in need)


def read(get, path, kind, params=None, need=()):
    """(reply, None) or (None, error): one GET through `get`. A reply that is not a `kind` (dict or list), a dict
    missing a key path of `need`, a non-JSON reply and an API failure (OSError from `gh_get`) are all errors, so a
    caller never has to type-check."""
    try:
        d = get(path, params) if params else get(path)
        if not isinstance(d, kind) or (kind is dict and not has(d, need)):
            raise ValueError(UNEXPECTED)
        return d, None
    except (OSError, ValueError) as e:
        return None, e


def listing(get, path, params=None, key=None, need=()):
    """(items, None) or (None, error): every item of a list endpoint, 100 per page, at most MAX_PAGES pages. `key`
    names the array inside an object reply (the environments list); without it the reply is the array. Every item
    must be an object carrying the key paths in `need`, and a list that fills all MAX_PAGES pages is an error too (it
    may be longer than what was read): a count of a list the audit could not read in full would be wrong."""
    items = []
    for page in range(1, MAX_PAGES + 1):
        d, e = read(get, path, dict if key else list, dict(params or {}, per_page=100, page=page))
        chunk = d.get(key) if key and d is not None else d
        if e or not isinstance(chunk, list) or not all(has(i, need) for i in chunk):
            return None, e or ValueError(UNEXPECTED)
        items += chunk
        if len(chunk) < 100:
            return items, None
    return None, ValueError(TOO_MANY)


def why(e, miss=NEEDS_ADMIN):
    """(label, fix) for a failed read, from the HTTP status only. 403 or 404 is `miss`; a rate limit and a plan limit
    are told apart by their message (matched, never printed); an odd reply and a list too long to read in full have
    their own labels; anything else is the status or `API error`."""
    if str(e) == UNEXPECTED:
        return NOT_REPORTED
    if str(e) == TOO_MANY:
        return "%d or more items" % (MAX_PAGES * 100), "review this list in the repository settings"
    m = re.search(r"\(HTTP (\d+)\)$", str(e))
    s, msg = int(m.group(1)) if m else None, str(e).lower()
    if s in (403, 429) and "rate limit" in msg:
        return "rate limited", "wait for the limit to reset, then re-run"
    if s == 403 and "upgrade to github" in msg:
        return "not available on this plan", "upgrade the plan or make the repository public, then re-run"
    if s in (403, 404):
        return miss
    return ("HTTP %d" % s if s else "API error"), "re-run; if it persists check `gh auth status` and the network"


def nc(check, reason):
    """The row for a check that could not run: `<check>: not checked (<label>)` with the fix that would let it."""
    label, fix = reason
    return ("%s: not checked (%s)" % (check, label), "not-checked", fix)


def protection(get, base, repo):
    """Default-branch rows from classic protection and rulesets. A 404 `Branch not protected` is the classic 'none'
    only when the repository reply shows admin for the token (`permissions.admin` true); with any other token it is
    `not checked`, since the REST page does not say what a token without admin gets for a protected branch."""
    b = dig(repo, "default_branch")
    if not isinstance(b, str) or not b:
        return [nc("default branch protection", ("default branch not reported", NEEDS_ADMIN[1]))]
    q = urllib.parse.quote(b, safe="/")
    classic, cerr = read(get, "%s/branches/%s/protection" % (base, q), dict,
                         need=(("allow_force_pushes", "enabled"), ("enforce_admins", "enabled")))
    rules, rerr = listing(get, "%s/rules/branches/%s" % (base, q))
    none = bool(cerr) and "branch not protected" in str(cerr).lower() and dig(repo, "permissions", "admin") is True
    fix = "protect the default branch: require a pull request and the CI checks, and block force pushes"
    out = []
    if cerr and not none:
        out.append(nc("default branch protection", why(cerr)))
    if rerr:
        out.append(nc("default branch rulesets", why(rerr)))
        if none:
            out.append(("default branch has no classic protection rule (rulesets not checked)", "high", fix))
    if (cerr and not none) or rerr:
        return out
    if none and not rules:
        return [("default branch has no protection (no classic rule, no ruleset)", "high", fix)]
    classic = {} if none else classic
    force = none or dig(classic, "allow_force_pushes", "enabled") is True
    counts = [dig(classic, "required_pull_request_reviews", "required_approving_review_count")]
    checks = bool(dig(classic, "required_status_checks", "contexts") or dig(classic, "required_status_checks", "checks"))
    for r in rules:
        t = dig(r, "type")
        if t == "pull_request":
            counts.append(dig(r, "parameters", "required_approving_review_count"))
        elif t == "non_fast_forward":
            force = False
        elif t == "required_status_checks" and dig(r, "parameters", "required_status_checks"):
            checks = True
    reviews = max([c for c in counts if isinstance(c, int)] or [0])  # the strictest source wins; none given = 0
    if force:
        out.append(("force pushes allowed on the default branch", "high",
                    "block force pushes (allow_force_pushes off, or a non_fast_forward rule)"))
    if reviews < 1:
        out.append(("fewer than 1 required approving review on the default branch", "medium",
                    "require at least 1 approving review (required_approving_review_count)"))
    if not checks:
        out.append(("no required status checks on the default branch", "medium", "require the CI checks that must pass before merge"))
    if dig(classic, "enforce_admins", "enabled") is False:
        out.append(("admins exempt from the default branch protection (enforce_admins off)", "low", "turn on enforce_admins"))
    if rules:
        out.append(nc("admins exempt from the rulesets", ("ruleset bypass lists are not read", "review each ruleset's bypass_actors")))
    return out


def actions(get, base):
    """Rows from the repository's Actions permissions: token default, review approval, allowed actions."""
    out = []
    wf, e = read(get, base + "/actions/permissions/workflow", dict,
                 need=(("default_workflow_permissions",), ("can_approve_pull_request_reviews",)))  # both required in the schema
    if e:
        out.append(nc("Actions workflow token", why(e)))
    else:
        if wf.get("default_workflow_permissions") == "write":
            out.append(("default workflow token has write permission", "medium",
                        "set default_workflow_permissions to read and grant write per workflow with `permissions:`"))
        if wf.get("can_approve_pull_request_reviews") is True:
            out.append(("workflows can approve pull request reviews", "medium", "set can_approve_pull_request_reviews to false"))
    ap, e = read(get, base + "/actions/permissions", dict, need=(("enabled",),))  # `allowed_actions` is optional: see below
    if e:
        out.append(nc("allowed actions", why(e)))
    elif ap.get("allowed_actions") == "all":
        out.append(("all actions and reusable workflows are allowed", "low",
                    "set allowed_actions to selected or local_only and list the allowed actions"))
    elif ap["enabled"] is not False and ap.get("allowed_actions") not in ("selected", "local_only"):
        out.append(nc("allowed actions", NOT_REPORTED))  # Actions is on but the reply carries no policy; off needs none
    return out


def collaborators(get, base):
    """One row with the admin and outside-collaborator counts: low when any are outside, else info."""
    n = {}
    for k, params in (("admin", {"permission": "admin"}), ("outside", {"affiliation": "outside"})):
        items, e = listing(get, base + "/collaborators", params)
        if e:
            return [nc("collaborators", why(e))]
        n[k] = len(items)
    return [("collaborators: %d admin, %d outside" % (n["admin"], n["outside"]), "low" if n["outside"] else "info",
             "keep admin to the few who need it; remove outside collaborators who no longer need access")]


def deploy_keys(get, base):
    """A row when any deploy key can write (count only; titles and keys are never read out)."""
    keys, e = listing(get, base + "/keys", need=(("read_only",),))
    if e:
        return [nc("deploy keys", why(e))]
    n = sum(1 for k in keys if k["read_only"] is False)
    return [("%d deploy key(s) with write access" % n, "medium", "replace each with a read-only key unless it must push")] if n else []


def webhooks(get, base):
    """Rows for webhooks that skip TLS verification or deliver over plain http (counts only; URLs are never read out)."""
    hooks, e = listing(get, base + "/hooks", need=(("config", "url"), ("config", "insecure_ssl")))
    if e:
        return [nc("webhooks", why(e))]
    off = sum(1 for h in hooks if str(h["config"]["insecure_ssl"]) == "1")
    plain = sum(1 for h in hooks if str(h["config"]["url"]).startswith("http://"))
    return ([("%d webhook(s) with TLS verification off (insecure_ssl)" % off, "medium", "set insecure_ssl to 0")] if off else []) + \
           ([("%d webhook(s) delivering over plain http" % plain, "medium", "switch the payload URL to https")] if plain else [])


def environments(get, base):
    """A row when any deployment environment has no protection rule (reviewers, wait timer or branch policy)."""
    envs, e = listing(get, base + "/environments", key="environments")
    if e:
        return [nc("environments", why(e))]
    n = sum(1 for v in envs if not dig(v, "protection_rules"))
    return [("%d environment(s) without protection rules" % n, "low",
             "add required reviewers, a wait timer or a deployment branch policy to each")] if n else []


def analysis(repo):
    """Secret scanning and push protection from the repository object's `security_and_analysis` (admin-only field)."""
    sa = dig(repo, "security_and_analysis")
    if not sa or not isinstance(sa, dict):
        return [nc("secret scanning and push protection", NEEDS_ADMIN)]
    out = []
    for key, what, sev in (("secret_scanning", "secret scanning", "medium"), ("secret_scanning_push_protection", "push protection", "low")):
        st = dig(sa, key, "status")
        if st is None:
            out.append(nc(what, NOT_REPORTED))
        elif st != "enabled":
            out.append(("%s not enabled" % what, sev, "set security_and_analysis.%s.status to enabled (a private or internal "
                        "organization repository needs GitHub Secret Protection)" % key))
    return out


def audit(slug, get=gh_get):
    """Rows {repo, check, severity, fix} for one OWNER/NAME, worst first. `get(path, params=None)` -> parsed JSON or
    raises OSError (default `gh_get`; tests inject a fake). A repository the token cannot read gives one not-checked
    row; a failed check gives its own and never stops the others. Never raises on a failed or odd reply."""
    base = "/repos/" + slug
    repo, e = read(get, base, dict)
    if e:
        rows = [nc("repository", why(e, NOT_FOUND))]
    else:
        rows = [r for part in (protection(get, base, repo), actions(get, base), collaborators(get, base), deploy_keys(get, base),
                               webhooks(get, base), environments(get, base), analysis(repo)) for r in part]
    rows.sort(key=lambda r: SEVERITY.index(r[1]))  # stable: checks keep their order within a severity
    return [{"repo": slug, "check": c, "severity": s, "fix": f} for c, s, f in rows]


def render(rows, repos):
    """Table (repo | severity | check | fix) plus a summary line; `--json` prints the same rows and counts."""
    n_find = sum(1 for r in rows if r["severity"] in FINDING)
    n_nc = sum(1 for r in rows if r["severity"] == "not-checked")
    lines = ["| repo | severity | check | fix |", "|---|---|---|---|"]
    lines += ["| %(repo)s | %(severity)s | %(check)s | %(fix)s |" % r for r in rows]
    lines.append("\n%d repos, %d findings, %d not checked" % (repos, n_find, n_nc))
    return "\n".join(lines), {"repos": repos, "findings": n_find, "not_checked": n_nc}


def main(argv=None, get=gh_get):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repos", nargs="*", metavar="OWNER/NAME")
    ap.add_argument("--repos-file", help="file with one OWNER/NAME per line (blank lines and # comments ignored)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = ap.parse_args(argv)
    names = list(a.repos)
    if a.repos_file:
        try:
            with open(a.repos_file, encoding="utf-8") as f:
                names += [ln.split("#", 1)[0].strip() for ln in f]
        except (OSError, UnicodeDecodeError) as e:
            pp.die("cannot read --repos-file: %s" % (getattr(e, "strerror", None) or "not UTF-8 text"))
    slugs = {}  # lower-cased slug -> first spelling: a repository twice is audited once
    for s in filter(None, names):
        if not SLUG.fullmatch(s):
            pp.die("not an OWNER/NAME slug: %r" % s)
        slugs.setdefault(s.lower(), s)
    if not slugs:
        pp.die("no repositories: pass OWNER/NAME or --repos-file")
    if get is gh_get and not shutil.which("gh"):
        pp.die("gh not found on PATH")
    rows = [r for s in slugs.values() for r in audit(s, get)]
    text, summary = render(rows, len(slugs))
    print(json.dumps({"rows": rows, "summary": summary}, indent=2) if a.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
