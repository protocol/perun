#!/usr/bin/env python3
"""org_settings_audit.py: read-only audit of GitHub organization settings, then every repository's settings.

WHY: branch protection, required 2FA, Actions token defaults, installed apps and self-hosted runners are not visible in
code, yet they decide whether a review gate means anything (the CIS GitHub benchmark covers them). Per repository this
reuses `repo_settings_audit.audit` unchanged (branch protection and rulesets, Actions, collaborators, deploy keys,
webhooks, environments, secret scanning and push protection); this file adds the organization-level checks:
  2FA               `two_factor_requirement_enabled` on the organization (owner token only)
  Actions           organization default workflow token has write, workflows can approve reviews, allowed actions = all
  apps              installed GitHub Apps holding admin or write on repository administration or contents (count)
  outside people    outside collaborators (count)
  self-hosted       organization-level self-hosted runners (count)
A 403 or 404, a missing field or an odd reply is a `not checked` row that names the token scope or permission it needs,
never a pass.

USAGE: org_settings_audit.py ORG [--max-repos N] [--token-env VAR] [--json]
Token: the env var named by --token-env, else `gh auth token`; it reaches curl on stdin only (never argv), as in
org_leak_sweep.py. `GITHUB_API_URL` overrides https://api.github.com (tests point it at a stub).
Output: `{"org": rows, "repos": {"OWNER/NAME": rows}, "summary": {...}}` with `--json`, else one table.
Exit codes: 0 the audit ran (findings do not change it), 2 usage, no token, gh missing or a non-https GITHUB_API_URL.
Side effects: HTTP GET only; nothing is written or changed. Counts and booleans only: no login, app name or API text.
Limits: first --max-repos repositories (default 200); a longer org says so in a not-checked row.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_settings_audit as rsa  # noqa: E402

API = "https://api.github.com"
ORG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")


def curl_get(token):
    """get(path, params=None) -> parsed JSON over curl; failure raises OSError('... (HTTP n)') for `rsa.why`."""
    def get(path, params=None):
        url = os.environ.get("GITHUB_API_URL", API) + path + ("?" + urllib.parse.urlencode(params) if params else "")
        cfg = 'header = "Authorization: Bearer ' + token.replace("\\", "\\\\").replace('"', '\\"') + '"\n'
        r = subprocess.run(["curl", "-sS", "--max-time", "60", "--connect-timeout", "15", "-w", "\n%{http_code}", "-H", "Accept: application/vnd.github+json",
                            "--config", "-", url], input=cfg, capture_output=True, text=True, errors="replace")
        body, _, code = r.stdout.rpartition("\n")
        if r.returncode or not code.isdigit():
            raise OSError("API error")
        if int(code) >= 400:
            try:
                msg = str(json.loads(body).get("message", ""))
            except (ValueError, AttributeError):
                msg = ""
            raise OSError("%s (HTTP %s)" % (msg, code))
        return json.loads(body)
    return get


def need(scope):
    return ("needs " + scope, "re-run with a token that has " + scope)


def org_rows(get, org):
    """(check, severity, fix) tuples for the organization itself; any failed read is a not-checked row."""
    base, rows = "/orgs/" + org, []
    o, e = rsa.read(get, base, dict)
    if e:
        return [rsa.nc("organization", rsa.why(e, need("read access to the organization")))]
    tf = o.get("two_factor_requirement_enabled")  # absent unless the token is an org owner
    if tf is None:
        rows.append(rsa.nc("2FA requirement", need("owner access (admin:org)")))
    elif tf is not True:
        rows.append(("2FA requirement is off", "high", "enable 'Require two-factor authentication' in the organization security settings"))
    adm = "admin:org (fine-grained: Administration read)"
    w, e = rsa.read(get, base + "/actions/permissions/workflow", dict,
                    need=(("default_workflow_permissions",), ("can_approve_pull_request_reviews",)))
    if e:
        rows.append(rsa.nc("org Actions token", rsa.why(e, need(adm))))
    else:
        if w["default_workflow_permissions"] == "write":
            rows.append(("org default workflow token can write", "medium", "set the organization default workflow permissions to read"))
        if w["can_approve_pull_request_reviews"] is True:
            rows.append(("org workflows can approve pull request reviews", "medium", "turn off 'Allow GitHub Actions to create and approve pull requests'"))
    a, e = rsa.read(get, base + "/actions/permissions", dict, need=(("enabled_repositories",),))
    if e:
        rows.append(rsa.nc("org allowed actions", rsa.why(e, need(adm))))
    elif "allowed_actions" not in a and a["enabled_repositories"] != "none":
        rows.append(rsa.nc("org allowed actions", need(adm)))  # absent field is never a pass
    elif a.get("allowed_actions") == "all":
        rows.append(("org allows all actions", "medium", "restrict allowed actions to GitHub-owned and an allowlist"))
    ins, e = rsa.listing(get, base + "/installations", key="installations")
    if e:
        rows.append(rsa.nc("installed apps", rsa.why(e, need("admin:read (fine-grained: Administration read)"))))
    else:
        n = sum(1 for i in ins if isinstance(i, dict) and any(
            (i.get("permissions") or {}).get(k) in ("write", "admin") for k in ("administration", "contents")))
        rows.append(("%d installed app(s) hold write or admin on administration or contents" % n, "low" if n else "info",
                     "review each app's permissions in the organization installed apps settings"))
    oc, e = rsa.listing(get, base + "/outside_collaborators")
    rows.append(rsa.nc("outside collaborators", rsa.why(e, need("admin:org (owner)"))) if e else
                ("%d outside collaborator(s)" % len(oc), "low" if oc else "info", "confirm each still needs access"))
    rn, e = rsa.listing(get, base + "/actions/runners", key="runners")
    rows.append(rsa.nc("self-hosted runners", rsa.why(e, need("admin:org (fine-grained: Self-hosted runners read)"))) if e else
                ("%d org self-hosted runner(s)" % len(rn), "medium" if rn else "info",
                 "keep self-hosted runners off public repositories and use ephemeral runners"))
    return rows


def audit(org, get, max_repos=200):
    """(org rows, {slug: rows}); an unreadable or over-long repo list is a not-checked org row."""
    keys = ("check", "severity", "fix")
    rows = [dict(zip(keys, r)) for r in org_rows(get, org)]
    repos, e = rsa.listing(get, "/orgs/%s/repos" % org, {"type": "all"}, need=(("full_name",),))
    if e:
        rows.append(dict(zip(keys, rsa.nc("repository list", rsa.why(e, need("read access to the organization's repositories"))))))
        repos = []
    if len(repos) > max_repos:
        rows.append(dict(zip(keys, rsa.nc("repository list", ("capped at %d repos" % max_repos, "raise --max-repos")))))
    rows.sort(key=lambda r: rsa.SEVERITY.index(r["severity"]))
    return rows, {r["full_name"]: rsa.audit(r["full_name"], get) for r in repos[:max_repos]}


def main(argv=None, get=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("org")
    ap.add_argument("--max-repos", type=int, default=200)
    ap.add_argument("--token-env")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not ORG.fullmatch(a.org):
        print("org_settings_audit: not an organization name", file=sys.stderr)
        return 2
    if get is None:
        u = os.environ.get("GITHUB_API_URL", API)
        if not re.match(r"https://|http://(localhost|127\.0\.0\.1)([:/]|$)", u):
            print("org_settings_audit: GITHUB_API_URL must be https:// (or http://localhost)", file=sys.stderr)
            return 2
        try:
            tok = os.environ.get(a.token_env, "") if a.token_env else subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        except OSError:
            print("org_settings_audit: gh not runnable (set --token-env VAR)", file=sys.stderr)
            return 2
        if not tok:
            print("org_settings_audit: no token (set --token-env VAR or run `gh auth login`)", file=sys.stderr)
            return 2
        get = curl_get(tok)
    org, repos = audit(a.org, get, a.max_repos)
    flat = [r for v in repos.values() for r in v]
    summ = {"repos": len(repos), "findings": sum(r["severity"] in rsa.FINDING for r in org + flat),
            "not_checked": sum(r["severity"] == "not-checked" for r in org + flat)}
    if a.json:
        print(json.dumps({"org": org, "repos": repos, "summary": summ}, indent=2))
    else:
        print(rsa.render([dict(r, repo=a.org) for r in org] + flat, len(repos))[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
