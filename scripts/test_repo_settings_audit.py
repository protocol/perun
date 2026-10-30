#!/usr/bin/env python3
"""Offline tests for repo_settings_audit.py: every check (default-branch protection from classic rules and rulesets,
Actions, collaborators, deploy keys, webhooks, environments, secret scanning), the not-checked rows (a 403 or 404, a
missing field, an unreadable item and a list of 1000 or more are never a clean result; `Branch not protected` is a
finding only for a token shown to have admin), pagination, odd API replies, the privacy rule (counts only: no login,
email, key title, hook URL or API message text in any output), the CLI (slugs, --repos-file, --json, exit 2) and the
default getter end to end through `gh api`. Synthetic data only: fictional acme/widgets, no network, no real names."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SCRIPTS))
import pipeline_hub as hub  # noqa: E402
import repo_settings_audit as rsa  # noqa: E402

SLUG = "acme/widgets"
B = "/repos/" + SLUG
PROT, RULES = B + "/branches/main/protection", B + "/rules/branches/main"
WF, AP = B + "/actions/permissions/workflow", B + "/actions/permissions"
COLLAB, KEYS, HOOKS, ENVS = B + "/collaborators", B + "/keys", B + "/hooks", B + "/environments"
NOT_PROTECTED = OSError("Branch not protected (HTTP 404)")
NOT_FOUND = OSError("Not Found (HTTP 404)")
FORBIDDEN = OSError("Resource not accessible by personal access token (HTTP 403)")
STRONG = {"required_pull_request_reviews": {"required_approving_review_count": 2}, "allow_force_pushes": {"enabled": False},
          "enforce_admins": {"enabled": True}, "required_status_checks": {"contexts": ["ci"], "checks": [{"context": "ci"}]}}
FORCE = {"allow_force_pushes": {"enabled": True}, "enforce_admins": {"enabled": True}}  # classic protection that allows force pushes
RULESET_FULL = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}, {"type": "non_fast_forward"},
                {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci"}]}}]


def pages(items, key=None):
    """A list endpoint that honours per_page and page, as the API does."""
    def f(params):
        n, p = params["per_page"], params["page"]
        chunk = items[(p - 1) * n:p * n]
        return {"total_count": len(items), key: chunk} if key else chunk
    return f


def collab(admins=0, outside=0):
    """/collaborators: the admin filter and the outside filter each return their own list (logins and emails included)."""
    def f(params):
        n = outside if params.get("affiliation") == "outside" else admins
        return pages([{"login": "jane-smith-%d" % i, "email": "jane@example.com"} for i in range(n)])(params)
    return f


def many(n, key=None):
    """A list endpoint of n items that every list check can read (a collaborator, a read-only key, a safe hook, a
    protected environment, a rule), paged as the API pages it."""
    item = {"login": "jane-smith", "read_only": True, "config": {"url": "https://hooks.example.com/a", "insecure_ssl": "0"},
            "name": "prod", "protection_rules": [{"type": "wait_timer"}], "type": "creation"}
    return pages([item] * n, key)


def healthy():
    """Replies for a repository that passes every check (fresh dicts each call)."""
    return {
        B: {"default_branch": "main", "permissions": {"admin": True},
            "security_and_analysis": {"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}},
        PROT: dict(STRONG), RULES: [],
        WF: {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False},
        AP: {"enabled": True, "allowed_actions": "selected"},
        COLLAB: collab(1, 0),
        KEYS: [{"title": "ci read key", "read_only": True}],
        HOOKS: [{"config": {"url": "https://hooks.example.com/a", "insecure_ssl": "0"}}],
        ENVS: {"total_count": 1, "environments": [{"name": "prod", "protection_rules": [{"type": "required_reviewers"}]}]},
    }


class Fake:
    """The injected getter: replies keyed by path (data, an Exception to raise, or a callable of the params). A path
    the test did not provide raises KeyError, so an unexpected call fails loudly."""

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def __call__(self, path, params=None):
        self.calls.append((path, params))
        v = self.replies[path]
        if isinstance(v, Exception):
            raise v
        return v(params) if callable(v) else v


def run(over=None):
    return rsa.audit(SLUG, Fake({**healthy(), **(over or {})}))


def summary(rows, skip=("info",)):
    """[(severity, check)] without the always-present collaborator count row."""
    return [(r["severity"], r["check"]) for r in rows if r["severity"] not in skip]


def cli(*argv, get=None):
    """(exit code, stdout, stderr) of main(); `get=None` leaves the default getter (`gh api`) in place."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = rsa.main(list(argv), **({"get": get} if get else {}))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Helpers(unittest.TestCase):
    def test_dig_walks_dicts_and_returns_none_on_any_miss(self):
        self.assertEqual(rsa.dig({"a": {"b": 1}}, "a", "b"), 1)
        for d in ({"a": 1}, {"a": None}, {}, None, [1], "a"):
            self.assertIsNone(rsa.dig(d, "a", "b"))

    def test_read_returns_reply_or_error_never_raises_on_odd_replies(self):
        self.assertEqual(rsa.read(lambda p: {"a": 1}, "/x", dict), ({"a": 1}, None))
        for bad in (OSError("Server Error (HTTP 502)"), ValueError("not json")):
            def get(path, bad=bad):
                raise bad
            self.assertEqual(rsa.read(get, "/x", dict), (None, bad))
        for reply in ([], "x", None, 5):  # a list where a dict is expected, and the reverse
            d, e = rsa.read(lambda p, r=reply: r, "/x", dict)
            self.assertEqual((d, str(e)), (None, "unexpected reply"))
        d, e = rsa.read(lambda p: {}, "/x", list)
        self.assertEqual((d, str(e)), (None, "unexpected reply"))

    def test_read_needs_every_key_path_present_and_not_null(self):
        need = (("a", "b"), ("c",))
        self.assertEqual(rsa.read(lambda p: {"a": {"b": False}, "c": 0}, "/x", dict, need=need)[1], None)  # false and 0 are values
        for reply in ({}, {"a": {"b": 1}}, {"c": 1}, {"a": {}, "c": 1}, {"a": {"b": None}, "c": 1}, {"a": 1, "c": 1}):
            d, e = rsa.read(lambda p, r=reply: r, "/x", dict, need=need)
            self.assertEqual((d, str(e)), (None, "unexpected reply"), reply)

    def test_why_gives_a_fixed_label_from_the_status_never_the_message(self):
        for msg, label in (("Not Found (HTTP 404)", "needs admin"),
                           ("Resource not accessible by integration (HTTP 403)", "needs admin"),
                           ("API rate limit exceeded for user ID 1 (HTTP 403)", "rate limited"),
                           ("You have exceeded a secondary rate limit (HTTP 429)", "rate limited"),
                           ("Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)",
                            "not available on this plan"),
                           ("Server Error (HTTP 502)", "HTTP 502"), ("Bad credentials (HTTP 401)", "HTTP 401"),
                           ("gh api failed", "API error"), ("unexpected reply", "not reported by the API"),
                           ("too many items", "1000 or more items")):
            got_label, fix = rsa.why(OSError(msg))
            self.assertEqual(got_label, label, msg)
            self.assertTrue(fix and "\n" not in fix, msg)
        self.assertEqual(rsa.why(NOT_FOUND, rsa.NOT_FOUND)[0], "not found or no access")
        self.assertEqual(rsa.why(OSError("Server Error (HTTP 502)"), rsa.NOT_FOUND)[0], "HTTP 502")  # only 403/404 use `miss`

    def test_nc_row_shape(self):
        self.assertEqual(rsa.nc("x", ("needs admin", "fix it")), ("x: not checked (needs admin)", "not-checked", "fix it"))

    def test_slug_accepts_owner_name_and_refuses_anything_that_could_leave_the_path(self):
        for ok in ("acme/widgets", "Acme-Co/widgets.v2", "a1/.github", "a/b_c"):
            self.assertTrue(rsa.SLUG.fullmatch(ok), ok)
        for bad in ("acme", "acme/", "/widgets", "acme/widgets/x", "acme/..", "acme/.", "../widgets", "-acme/widgets", "acme/wid gets",
                    "acme/widgets?x=1", "acme/wid%2Fgets", "acme/widgets\n", "jane@example.com"):
            self.assertFalse(rsa.SLUG.fullmatch(bad), repr(bad))

    def test_listing_pages_through_the_list_and_stops_at_a_short_page(self):
        f = Fake({"/x": pages([{"i": i} for i in range(250)])})
        items, e = rsa.listing(f, "/x", {"permission": "admin"})
        self.assertEqual((len(items), e), (250, None))
        self.assertEqual([c[1] for c in f.calls], [{"permission": "admin", "per_page": 100, "page": p} for p in (1, 2, 3)])
        f = Fake({"/x": pages([{}] * 100)})  # a full last page costs one more call and ends on the empty one
        self.assertEqual((len(rsa.listing(f, "/x")[0]), len(f.calls)), (100, 2))
        f = Fake({"/x": pages([{}] * 130, key="environments")})  # the array inside an object reply
        self.assertEqual((len(rsa.listing(f, "/x", key="environments")[0]), len(f.calls)), (130, 2))

    def test_listing_that_fills_every_page_is_an_error_not_a_truncated_list(self):
        endless = Fake({"/x": lambda p: [{}] * 100})
        items, e = rsa.listing(endless, "/x")
        self.assertEqual((items, str(e), len(endless.calls)), (None, "too many items", 10))  # 10 pages of 100: stop, do not guess
        f = Fake({"/x": many(1000)})  # exactly 1000 cannot be told from more, so it is an error too, without an 11th call
        self.assertEqual((rsa.listing(f, "/x")[0], len(f.calls)), (None, 10))
        f = Fake({"/x": many(999)})  # one short of a full last page is read in full
        items, e = rsa.listing(f, "/x")
        self.assertEqual((len(items), e, len(f.calls)), (999, None, 10))
        f = Fake({"/x": many(1000, key="environments")})  # the same rule inside an object reply
        self.assertEqual(str(rsa.listing(f, "/x", key="environments")[1]), "too many items")

    def test_listing_refuses_an_item_it_cannot_read(self):
        need = (("read_only",),)
        for items in ([{"read_only": True}, {}], [{"read_only": None}], [{"read_only": True}, None], [5], ["x"], [[]], [{"a": 1}]):
            items_, e = rsa.listing(Fake({"/x": items}), "/x", need=need)
            self.assertEqual((items_, str(e)), (None, "unexpected reply"), items)
        self.assertEqual(rsa.listing(Fake({"/x": [{"read_only": False}, {"read_only": True}]}), "/x", need=need)[1], None)
        for items in ([None], [5]):  # without `need` an item must still be an object
            self.assertIsNone(rsa.listing(Fake({"/x": items}), "/x")[0], items)
        self.assertIsNone(rsa.listing(Fake({"/x": {"environments": [None]}}), "/x", key="environments")[0])

    def test_listing_reports_a_failed_page(self):
        def flaky(params):
            if params["page"] > 1:
                raise OSError("Server Error (HTTP 502)")
            return [{}] * 100
        items, e = rsa.listing(Fake({"/x": flaky}), "/x")  # one failed page loses the whole list: a count would be wrong
        self.assertEqual((items, str(e)), (None, "Server Error (HTTP 502)"))
        for reply in ({}, [], {"environments": "x"}):
            self.assertIsNone(rsa.listing(Fake({"/x": reply}), "/x", key="environments")[0])

    def test_render_counts_findings_and_not_checked(self):
        rows = [{"repo": "a/b", "check": c, "severity": s, "fix": "f"} for c, s in
                (("c1", "high"), ("c2", "low"), ("c3", "info"), ("c4", "not-checked"), ("c5", "not-checked"))]
        text, counts = rsa.render(rows, 2)
        self.assertEqual(counts, {"repos": 2, "findings": 2, "not_checked": 2})
        lines = text.splitlines()
        self.assertEqual((lines[0], lines[-1]), ("| repo | severity | check | fix |", "2 repos, 2 findings, 2 not checked"))
        self.assertIn("| a/b | high | c1 | f |", lines)


class Protection(unittest.TestCase):
    def test_a_healthy_repository_has_no_finding_and_no_not_checked_row(self):
        rows = run()
        self.assertEqual([(r["severity"], r["check"]) for r in rows], [("info", "collaborators: 1 admin, 0 outside")])
        self.assertTrue(all(set(r) == {"repo", "check", "severity", "fix"} and r["repo"] == SLUG for r in rows))

    def test_no_protection_at_all_is_one_high_finding_not_four(self):
        rows = run({PROT: NOT_PROTECTED})
        self.assertEqual(summary(rows), [("high", "default branch has no protection (no classic rule, no ruleset)")])

    def test_weak_classic_protection_gives_each_finding_worst_first(self):
        rows = run({PROT: {"allow_force_pushes": {"enabled": True}, "enforce_admins": {"enabled": False}}})
        self.assertEqual(summary(rows), [
            ("high", "force pushes allowed on the default branch"),
            ("medium", "fewer than 1 required approving review on the default branch"),
            ("medium", "no required status checks on the default branch"),
            ("low", "admins exempt from the default branch protection (enforce_admins off)")])

    def test_zero_required_reviews_and_empty_check_lists_count_as_missing(self):
        rows = run({PROT: {**STRONG, "required_pull_request_reviews": {"required_approving_review_count": 0},
                           "required_status_checks": {"contexts": [], "checks": []}}})
        self.assertEqual([c for _, c in summary(rows)],
                         ["fewer than 1 required approving review on the default branch", "no required status checks on the default branch"])

    def test_a_classic_reply_without_its_force_push_or_admin_setting_is_not_checked_never_clean(self):
        gone = "default branch protection: not checked (not reported by the API)"
        for reply in ({k: v for k, v in STRONG.items() if k != "allow_force_pushes"},  # the REST page marks neither setting required
                      {k: v for k, v in STRONG.items() if k != "enforce_admins"},
                      {**STRONG, "allow_force_pushes": {}}, {**STRONG, "enforce_admins": {"enabled": None}}, {}):
            self.assertEqual(summary(run({PROT: reply})), [("not-checked", gone)], reply)  # no guessed finding either

    def test_a_ruleset_alone_can_protect_the_branch(self):
        rows = run({PROT: NOT_PROTECTED, RULES: RULESET_FULL})
        self.assertEqual(summary(rows), [("not-checked", "admins exempt from the rulesets: not checked (ruleset bypass lists are not read)")])

    def test_ruleset_and_classic_rules_fill_each_others_gaps(self):
        weak = {"allow_force_pushes": {"enabled": True}, "enforce_admins": {"enabled": True}}  # no reviews, no checks, force allowed
        rows = run({PROT: weak, RULES: RULESET_FULL})
        self.assertEqual([s for s, _ in summary(rows)], ["not-checked"])  # nothing weak is left; only the bypass-list note

    def test_a_weak_ruleset_is_still_weak(self):
        rows = run({PROT: NOT_PROTECTED, RULES: [{"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
                                                 {"type": "required_status_checks", "parameters": {"required_status_checks": []}}]})
        self.assertEqual([c for s, c in summary(rows) if s != "not-checked"],
                         ["force pushes allowed on the default branch", "fewer than 1 required approving review on the default branch",
                          "no required status checks on the default branch"])

    def test_the_strictest_review_count_across_sources_wins(self):
        weak_rule = [{"type": "pull_request", "parameters": {"required_approving_review_count": 0}}]
        self.assertNotIn("fewer than 1 required approving review on the default branch",
                         [c for _, c in summary(run({RULES: weak_rule}))])  # classic requires 2
        strong_rule = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}]
        weak = {**STRONG, "required_pull_request_reviews": {"required_approving_review_count": 0}}
        self.assertNotIn("fewer than 1 required approving review on the default branch",
                         [c for _, c in summary(run({PROT: weak, RULES: strong_rule}))])

    def test_a_404_that_is_not_branch_not_protected_is_not_checked_not_a_finding(self):
        for err in (NOT_FOUND, FORBIDDEN):
            rows = run({PROT: err})
            self.assertEqual(summary(rows), [("not-checked", "default branch protection: not checked (needs admin)")])

    def test_branch_not_protected_is_a_finding_only_when_the_reply_shows_admin_true(self):
        no_field = {k: v for k, v in healthy()[B].items() if k != "permissions"}
        for repo in ({**healthy()[B], "permissions": {"admin": False, "push": True}}, no_field,  # not admin, or unknown
                     {**healthy()[B], "permissions": None}, {**healthy()[B], "permissions": {}},
                     {**healthy()[B], "permissions": {"push": True}}, {**healthy()[B], "permissions": {"admin": None}},
                     {**healthy()[B], "permissions": {"admin": 1}}, {**healthy()[B], "permissions": {"admin": "true"}}):
            rows = run({B: repo, PROT: NOT_PROTECTED})
            self.assertEqual(summary(rows), [("not-checked", "default branch protection: not checked (needs admin)")],
                             repo.get("permissions", "no permissions field"))
        rows = run({B: {**healthy()[B], "permissions": {"admin": True}}, PROT: NOT_PROTECTED})  # a conclusive 404
        self.assertEqual(summary(rows), [("high", "default branch has no protection (no classic rule, no ruleset)")])

    def test_unreadable_rulesets_hide_weaknesses_but_not_a_missing_classic_rule(self):
        rows = run({RULES: FORBIDDEN, PROT: FORCE})
        self.assertEqual(summary(rows), [("not-checked", "default branch rulesets: not checked (needs admin)")])  # a ruleset might block force
        rows = run({RULES: FORBIDDEN, PROT: NOT_PROTECTED})
        self.assertEqual(summary(rows), [("high", "default branch has no classic protection rule (rulesets not checked)"),
                                         ("not-checked", "default branch rulesets: not checked (needs admin)")])

    def test_rulesets_are_read_page_by_page(self):
        rules = [{"type": "creation"}] * 100 + RULESET_FULL  # the rules that block force pushes and require review sit on page 2
        f = Fake({**healthy(), PROT: NOT_PROTECTED, RULES: pages(rules)})
        rows = rsa.audit(SLUG, f)
        self.assertEqual(summary(rows), [("not-checked", "admins exempt from the rulesets: not checked (ruleset bypass lists are not read)")])
        self.assertEqual([c[1] for c in f.calls if c[0] == RULES], [{"per_page": 100, "page": 1}, {"per_page": 100, "page": 2}])

    def test_a_rule_list_that_fills_every_page_is_not_checked_not_judged_on_its_first_1000(self):
        rows = run({PROT: NOT_PROTECTED, RULES: many(1000)})
        self.assertEqual(summary(rows), [("high", "default branch has no classic protection rule (rulesets not checked)"),
                                         ("not-checked", "default branch rulesets: not checked (1000 or more items)")])
        rows = run({PROT: FORCE, RULES: many(1000)})  # a weakness is not reported from half of the evidence
        self.assertEqual(summary(rows), [("not-checked", "default branch rulesets: not checked (1000 or more items)")])

    def test_both_sources_unreadable_gives_two_not_checked_rows(self):
        rows = run({PROT: FORBIDDEN, RULES: FORBIDDEN})
        self.assertEqual([s for s, _ in summary(rows)], ["not-checked", "not-checked"])

    def test_the_branch_name_is_url_encoded_but_keeps_its_slashes(self):
        for branch, enc in (("release/1.x", "release/1.x"), ("odd #1", "odd%20%231")):
            replies = healthy()
            replies[B]["default_branch"] = branch
            replies[B + "/branches/%s/protection" % enc], replies[B + "/rules/branches/%s" % enc] = replies.pop(PROT), replies.pop(RULES)
            self.assertEqual(summary(rsa.audit(SLUG, Fake(replies))), [], branch)  # a wrong path would be a KeyError

    def test_a_missing_default_branch_is_not_checked(self):
        replies = healthy()
        replies[B] = {"permissions": {"admin": True}}
        rows = rsa.audit(SLUG, Fake(replies))
        self.assertIn("default branch protection: not checked (default branch not reported)", [r["check"] for r in rows])


class OtherChecks(unittest.TestCase):
    def test_actions_token_write_review_approval_and_all_actions_allowed(self):
        rows = run({WF: {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True},
                    AP: {"enabled": True, "allowed_actions": "all"}})
        self.assertEqual(summary(rows), [("medium", "default workflow token has write permission"),
                                         ("medium", "workflows can approve pull request reviews"),
                                         ("low", "all actions and reusable workflows are allowed")])

    def test_actions_checks_fail_independently(self):
        rows = run({WF: FORBIDDEN, AP: {"enabled": True, "allowed_actions": "all"}})
        self.assertEqual(summary(rows), [("low", "all actions and reusable workflows are allowed"),
                                         ("not-checked", "Actions workflow token: not checked (needs admin)")])
        rows = run({AP: OSError("Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)")})
        self.assertEqual(summary(rows), [("not-checked", "allowed actions: not checked (not available on this plan)")])

    def test_collaborator_counts(self):
        f = Fake({**healthy(), COLLAB: collab(3, 2)})
        rows = rsa.audit(SLUG, f)
        self.assertEqual([(r["severity"], r["check"]) for r in rows], [("low", "collaborators: 3 admin, 2 outside")])
        self.assertEqual({tuple(c[1].items())[0] for c in f.calls if c[0] == COLLAB},
                         {("permission", "admin"), ("affiliation", "outside")})  # one filtered list per count
        self.assertEqual(run({COLLAB: collab(2, 0)})[0]["severity"], "info")  # no outside collaborator: a count, not a finding

    def test_collaborators_unreadable(self):
        self.assertEqual(summary(run({COLLAB: FORBIDDEN}), skip=()), [("not-checked", "collaborators: not checked (needs admin)")])
        self.assertEqual(summary(run({COLLAB: lambda p: pages([])(p) if "permission" in p else (_ for _ in ()).throw(NOT_FOUND)}),
                                 skip=()), [("not-checked", "collaborators: not checked (needs admin)")])  # the second call fails

    def test_deploy_keys_with_write_are_counted_read_only_ones_are_not(self):
        keys = [{"title": "a", "read_only": False}, {"title": "b", "read_only": True}, {"title": "c", "read_only": False}]
        self.assertEqual(summary(run({KEYS: keys})), [("medium", "2 deploy key(s) with write access")])
        self.assertEqual(summary(run({KEYS: [{"read_only": True}]})), [])
        self.assertEqual(summary(run({KEYS: FORBIDDEN})), [("not-checked", "deploy keys: not checked (needs admin)")])

    def test_a_deploy_key_without_a_read_only_flag_makes_the_list_not_checked_never_clean(self):
        gone = [("not-checked", "deploy keys: not checked (not reported by the API)")]
        for keys in ([{"read_only": False}, {"title": "d"}], [{"read_only": None}], [{}], [None], [5], ["x"], [[]]):
            self.assertEqual(summary(run({KEYS: keys})), gone, keys)  # not even a count of the keys it could read

    def test_webhooks_with_tls_verification_off_or_plain_http(self):
        hooks = [{"config": {"url": "http://hooks.example.com/a", "insecure_ssl": "1"}},  # both problems
                 {"config": {"url": "https://hooks.example.com/b", "insecure_ssl": 1}},  # the API may send a number
                 {"config": {"url": "https://hooks.example.com/c", "insecure_ssl": "0"}}]
        self.assertEqual(summary(run({HOOKS: hooks})), [("medium", "2 webhook(s) with TLS verification off (insecure_ssl)"),
                                                        ("medium", "1 webhook(s) delivering over plain http")])
        self.assertEqual(summary(run({HOOKS: FORBIDDEN})), [("not-checked", "webhooks: not checked (needs admin)")])

    def test_a_webhook_without_a_url_or_insecure_ssl_makes_the_list_not_checked_never_clean(self):
        ok = {"config": {"url": "http://hooks.example.com/a", "insecure_ssl": "1"}}
        gone = [("not-checked", "webhooks: not checked (not reported by the API)")]
        for bad in ({"config": {"url": "https://hooks.example.com/b"}}, {"config": {"insecure_ssl": "0"}}, {"config": {}},
                    {"config": None}, {}, None, 5):
            self.assertEqual(summary(run({HOOKS: [ok, bad]})), gone, bad)  # the readable hook is not counted either

    def test_an_actions_reply_missing_a_field_is_not_checked_never_clean(self):
        wf_gone = [("not-checked", "Actions workflow token: not checked (not reported by the API)")]
        for wf in ({}, {"default_workflow_permissions": "write"}, {"can_approve_pull_request_reviews": True},
                   {"default_workflow_permissions": None, "can_approve_pull_request_reviews": False}):
            self.assertEqual(summary(run({WF: wf})), wf_gone, wf)  # a lone field is not reported as a finding
        ap_gone = [("not-checked", "allowed actions: not checked (not reported by the API)")]
        for ap in ({}, {"allowed_actions": "selected"}, {"enabled": None}, {"enabled": True}, {"enabled": True, "allowed_actions": "other"}):
            self.assertEqual(summary(run({AP: ap})), ap_gone, ap)  # Actions on and no policy named: not a clean answer
        for ap in ({"enabled": False}, {"enabled": True, "allowed_actions": "local_only"}, {"enabled": True, "allowed_actions": "selected"}):
            self.assertEqual(summary(run({AP: ap})), [], ap)  # Actions off needs no policy row; allowed_actions is optional in the schema

    def test_a_list_with_an_item_that_is_not_an_object_is_not_checked_never_clean(self):
        def envs(items):
            return {"total_count": len(items), "environments": items}
        for path, name, wrap in ((COLLAB, "collaborators", list), (HOOKS, "webhooks", list), (ENVS, "environments", envs)):
            for items in ([None], [5], ["x"], [[]]):
                rows = run({path: wrap(items)})
                self.assertEqual(summary(rows), [("not-checked", "%s: not checked (not reported by the API)" % name)], (name, items))
        self.assertEqual(summary(run({ENVS: envs([{}])})), [("low", "1 environment(s) without protection rules")])  # an object with no rules is unprotected

    def test_environments_without_a_protection_rule(self):
        envs = {"total_count": 3, "environments": [{"protection_rules": []}, {"protection_rules": [{"type": "wait_timer"}]}, {}]}
        self.assertEqual(summary(run({ENVS: envs})), [("low", "2 environment(s) without protection rules")])
        self.assertEqual(summary(run({ENVS: {"total_count": 0, "environments": []}})), [])
        self.assertEqual(summary(run({ENVS: NOT_FOUND})), [("not-checked", "environments: not checked (needs admin)")])

    def test_secret_scanning_and_push_protection(self):
        sa = {"secret_scanning": {"status": "disabled"}, "secret_scanning_push_protection": {"status": "disabled"}}
        repo = {**healthy()[B], "security_and_analysis": sa}
        self.assertEqual(summary(run({B: repo})), [("medium", "secret scanning not enabled"), ("low", "push protection not enabled")])
        repo["security_and_analysis"] = {"secret_scanning": {"status": "enabled"}}  # a key the API did not report
        self.assertEqual(summary(run({B: repo})), [("not-checked", "push protection: not checked (not reported by the API)")])
        for none in (None, {}):  # admin-only field: absent or null without admin
            repo["security_and_analysis"] = none
            self.assertEqual(summary(run({B: repo})), [("not-checked", "secret scanning and push protection: not checked (needs admin)")])

    def test_the_secret_scanning_fixes_name_github_secret_protection_for_private_organization_repositories(self):
        sa = {"secret_scanning": {"status": "disabled"}, "secret_scanning_push_protection": {"status": "disabled"}}
        rows = run({B: {**healthy()[B], "security_and_analysis": sa}})
        fixes = [r["fix"] for r in rows if r["severity"] in rsa.FINDING]
        self.assertEqual(len(fixes), 2)  # secret scanning and push protection
        for fix in fixes:
            self.assertIn("private or internal organization repository needs GitHub Secret Protection", fix)

    def test_a_list_of_1000_is_not_checked_on_every_list_check_and_999_are_read_in_full(self):
        for path, name in ((COLLAB, "collaborators"), (KEYS, "deploy keys"), (HOOKS, "webhooks")):
            self.assertEqual(summary(run({path: many(1000)})), [("not-checked", "%s: not checked (1000 or more items)" % name)], name)
        envs = run({ENVS: many(1000, key="environments")})
        self.assertEqual(summary(envs), [("not-checked", "environments: not checked (1000 or more items)")])
        read_in_full = run({COLLAB: many(999), KEYS: many(999), HOOKS: many(999), ENVS: many(999, key="environments")})
        self.assertEqual([(r["severity"], r["check"]) for r in read_in_full], [("low", "collaborators: 999 admin, 999 outside")])

    def test_an_unreadable_repository_is_one_row_and_its_other_calls_are_skipped(self):
        for err, label in ((NOT_FOUND, "not found or no access"), (FORBIDDEN, "not found or no access"), (OSError("Server Error (HTTP 502)"), "HTTP 502"),
                           (OSError("Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)"), "not available on this plan")):
            f = Fake({B: err})
            rows = rsa.audit(SLUG, f)
            self.assertEqual([(r["severity"], r["check"]) for r in rows], [("not-checked", "repository: not checked (%s)" % label)])
            self.assertEqual(f.calls, [(B, None)])

    def test_rows_are_sorted_worst_first_within_a_repository(self):
        rows = run({PROT: FORCE, WF: FORBIDDEN, KEYS: [{"read_only": False}],
                    COLLAB: collab(1, 1), B: {**healthy()[B], "security_and_analysis": None}})
        order = [rsa.SEVERITY.index(r["severity"]) for r in rows]
        self.assertEqual(order, sorted(order))
        self.assertEqual((rows[0]["severity"], rows[-1]["severity"]), ("high", "not-checked"))

    def test_every_odd_reply_is_a_not_checked_row_never_a_clean_one(self):
        """For each endpoint and each wrong-shaped reply the owning check says `not checked`; the one reply that stays
        clean is a valid empty list from a list endpoint."""
        owner = {B: ("repository", "default branch protection", "secret scanning and push protection"), PROT: ("default branch protection",),
                 RULES: ("default branch rulesets",), WF: ("Actions workflow token",), AP: ("allowed actions",),
                 COLLAB: ("collaborators",), KEYS: ("deploy keys",), HOOKS: ("webhooks",), ENVS: ("environments",)}
        self.assertEqual(set(owner), set(healthy()))  # a new endpoint must be added here
        for path, names in owner.items():
            for value in (None, "text", 7, [], {}, [None, 5, "x"], [[], {}]):
                rows = rsa.audit(SLUG, Fake({**healthy(), path: value}))
                self.assertTrue(all(r["severity"] in rsa.SEVERITY and r["check"] and r["fix"] for r in rows), (path, value))
                said = [r["check"] for r in rows if r["severity"] == "not-checked" and r["check"].startswith(names)]
                valid_empty_list = value == [] and path in (RULES, COLLAB, KEYS, HOOKS)
                self.assertEqual(bool(said), not valid_empty_list, (path, value, rows))


class Cli(unittest.TestCase):
    def fleet(self, *slugs):
        replies = {}
        for s in slugs:
            replies.update({k.replace(SLUG, s): v for k, v in healthy().items()})
        return Fake(replies)

    def test_text_table_and_summary_line(self):
        rc, out, err = cli(SLUG, get=Fake({**healthy(), PROT: NOT_PROTECTED, KEYS: FORBIDDEN}))
        lines = out.splitlines()
        self.assertEqual((rc, err, lines[0]), (0, "", "| repo | severity | check | fix |"))
        self.assertEqual(lines[2].split(" | ")[:3], ["| acme/widgets", "high", "default branch has no protection (no classic rule, no ruleset)"])
        self.assertEqual(lines[-1], "1 repos, 1 findings, 1 not checked")

    def test_json_rows_and_summary(self):
        rc, out, _ = cli(SLUG, "--json", get=Fake({**healthy(), PROT: NOT_PROTECTED, KEYS: FORBIDDEN}))
        rep = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(rep["summary"], {"repos": 1, "findings": 1, "not_checked": 1})
        self.assertEqual([r["severity"] for r in rep["rows"]], ["high", "info", "not-checked"])
        self.assertTrue(all(set(r) == {"repo", "check", "severity", "fix"} for r in rep["rows"]))

    def test_a_failing_repository_does_not_stop_the_sweep(self):
        f = self.fleet("acme/gadgets")
        f.replies[B] = NOT_FOUND  # acme/widgets is unreadable, acme/gadgets is fine
        rc, out, _ = cli(SLUG, "acme/gadgets", "--json", get=f)
        rep = json.loads(out)
        self.assertEqual((rc, rep["summary"]), (0, {"repos": 2, "findings": 0, "not_checked": 1}))
        self.assertEqual([(r["repo"], r["severity"]) for r in rep["rows"]], [(SLUG, "not-checked"), ("acme/gadgets", "info")])

    def test_repos_file_skips_blanks_and_comments_and_audits_each_repository_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "repos.txt"
            p.write_text("# fleet\nacme/widgets\nAcme/Widgets   # same repository, other case\n\n  acme/gadgets  # second\n", encoding="utf-8")
            f = self.fleet("acme/gadgets", SLUG)
            rc, out, _ = cli("acme/gadgets", "--repos-file", str(p), "--json", get=f)  # an argument repeats a file line
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["summary"]["repos"], 2)
        self.assertEqual([c[0] for c in f.calls if c[0].count("/") == 3], ["/repos/acme/gadgets", "/repos/acme/widgets"])  # argv order, no repeat

    def test_a_bad_slug_exits_2_before_any_api_call(self):
        for bad in ("acme", "acme/..", "../widgets", "acme/widgets/x", " acme/widgets", "jane@example.com"):
            f = Fake({})
            rc, out, err = cli(SLUG, bad, get=f)  # one good slug first: still nothing is audited
            self.assertEqual((rc, out, f.calls), (2, "", []), bad)
            self.assertIn("not an OWNER/NAME slug", err)

    def test_no_repository_exits_2(self):
        rc, _, err = cli(get=Fake({}))
        self.assertEqual(rc, 2)
        self.assertIn("no repositories", err)

    def test_an_unreadable_repos_file_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err = cli("--repos-file", str(Path(d) / "missing.txt"), get=Fake({}))
            self.assertEqual(rc, 2)
            self.assertIn("cannot read --repos-file", err)
            (Path(d) / "binary.txt").write_bytes(b"\xff\xfe\x00acme/widgets")
            rc, _, err = cli("--repos-file", str(Path(d) / "binary.txt"), get=Fake({}))
            self.assertEqual(rc, 2)
            self.assertIn("cannot read --repos-file: not UTF-8 text", err)

    def test_missing_gh_exits_2_with_the_default_getter_only(self):
        with mock.patch.object(rsa.shutil, "which", return_value=None), mock.patch.object(hub.subprocess, "run") as r:
            rc, out, err = cli(SLUG)
            self.assertEqual((rc, out, r.call_count), (2, "", 0))
            self.assertIn("gh not found on PATH", err)
            self.assertEqual(cli(SLUG, get=Fake(healthy()))[0], 0)  # an injected getter does not need gh

    def test_output_never_carries_logins_emails_key_titles_hook_urls_or_api_text(self):
        private = ["jane-smith", "jane@example.com", "Jane laptop key", "ssh-ed25519 AAAA-fixture", "hooks.example.com/secret-path-123",
                   "hook-fixture-value", "tok-fixture-9z", "Resource not accessible"]
        over = {PROT: FORCE, COLLAB: collab(2, 1),
                KEYS: [{"title": "Jane laptop key", "key": "ssh-ed25519 AAAA-fixture", "read_only": False}],
                HOOKS: [{"name": "web", "config": {"url": "http://hooks.example.com/secret-path-123", "insecure_ssl": "1", "secret": "hook-fixture-value"}}],
                WF: OSError("Resource not accessible by token tok-fixture-9z (HTTP 403)"),
                ENVS: {"total_count": 1, "environments": [{"name": "jane-smith-env", "protection_rules": []}]}}
        for argv in ((SLUG,), (SLUG, "--json")):
            f = Fake({**healthy(), **over})
            rc, out, err = cli(*argv, get=f)
            self.assertEqual(rc, 0)
            for word in ("1 deploy key(s) with write access", "1 webhook(s) with TLS verification off", "1 webhook(s) delivering over plain http",
                         "collaborators: 2 admin, 1 outside", "Actions workflow token: not checked (needs admin)",
                         "1 environment(s) without protection rules"):
                self.assertIn(word, out)  # the output is not vacuous
            for secret in private:
                self.assertNotIn(secret, out + err, secret)

    def test_default_getter_makes_only_plain_gh_api_gets(self):
        replies = {**healthy(), COLLAB: []}  # PROT is answered by the 404 below
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            path = args[2].split("?")[0]
            if path == PROT:
                return subprocess.CompletedProcess(args, 1, "", "gh: Branch not protected (HTTP 404)\n")
            return subprocess.CompletedProcess(args, 0, json.dumps(replies[path]), "")
        with mock.patch.object(hub.subprocess, "run", side_effect=fake_run), mock.patch.object(rsa.shutil, "which", return_value="/usr/bin/gh"):
            rc, out, _ = cli(SLUG, "--json")
        rep = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual([r["check"] for r in rep["rows"] if r["severity"] == "high"],
                         ["default branch has no protection (no classic rule, no ruleset)"])
        self.assertTrue(calls and all(len(a) == 3 and a[:2] == ["gh", "api"] and a[2].startswith(B) for a in calls), calls)  # no -X, -f or --input
        self.assertIn(COLLAB + "?permission=admin&per_page=100&page=1", [a[2] for a in calls])


if __name__ == "__main__":
    unittest.main()
