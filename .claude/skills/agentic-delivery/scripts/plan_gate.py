#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=record which actions one plan approval grants for a whole ticket, review=2027-01-30
"""plan_gate.py: one plan approval covers a whole ticket (build, test, review, PR).

This is the agent's policy record, not a sandbox: host permissions stay the enforcement boundary.

The plan file carries a line `Grants: push, pr` (add `merge` only if the user is approving it).
The user approves that plan once, quoted verbatim. `grant` binds the approval to the plan's
sha256 and to the grantable actions the plan names (push, pr, merge); merge is also dropped
unless the user's whole reply is exactly "approve merge" (any case, trailing . or ! allowed);
any other wording parks merge. `check` answers each later gated action: exit 0 = covered,
proceed; exit 3 = park that action for the end-of-run batch and keep going; exit 2 = missing
or malformed or forged ledger, or unreadable plan (any `grant` failure too): HALT and ask the
user (fail closed).
Never grantable, even if the plan or ledger lists them: force_push, deploy, secrets, spend,
delete, external_send, history_rewrite, settings_edit. A plan with more than one `Grants:` line is
ambiguous: exit 2. An action not listed here is unrouted and
parks. Editing the plan after approval voids the grant. `parked` prints the parked actions and
exits 2 if they disagree with the append-only park-event log; the agent can still rewrite both
(advisory, the ledger is agent-writable; host permissions are the boundary). Side effects:
reads/writes only the --ledger JSON file.

Commands: grant (--ledger L --plan P --quote Q [--scope SUBSET]), check ACTION (--ledger L
--plan P), parked (--ledger L), simulate (offline prompt count per ticket, with vs without a
grant).
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

GRANTABLE = {"push", "pr", "merge"}
NEVER = {"force_push", "deploy", "secrets", "spend", "delete", "external_send",
         "history_rewrite", "settings_edit"}
_GRANTS = re.compile(r"^\s*grants?\s*:\s*(.+)$", re.I | re.M)


def _sha(plan):
    return hashlib.sha256(Path(plan).read_bytes()).hexdigest()


def _named(plan):
    """Actions the plan text names on its `Grants:` line (first match, lowercased)."""
    m = _GRANTS.findall(Path(plan).read_text())
    if len(m) > 1:
        raise ValueError(f"plan {plan} has {len(m)} Grants lines; keep exactly one")
    return set(re.split(r"[\s,]+", m[0].strip().lower())) - {""} if m else set()


def _approves_merge(quote):
    """Allowlist, fail closed: the whole quote is exactly "approve merge" (any case, trailing . or !)."""
    return quote.strip(" \t\r\n").lower().rstrip(".!") == "approve merge"  # ASCII only: nbsp/ZWSP/lookalikes fail


def _load(ledger):
    """The ledger dict, {} if absent; ValueError if malformed or its scope exceeds GRANTABLE."""
    p = Path(ledger)
    if not p.is_file():
        return {}
    r = json.loads(p.read_text())
    strs = lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)
    if not (isinstance(r, dict) and isinstance(r.get("plan_sha256"), str) and isinstance(r.get("quote"), str)
            and r["quote"].strip() and strs(r.get("scope")) and strs(r.get("parked")) and strs(r.get("log"))
            and set(r["scope"]) <= GRANTABLE):
        raise ValueError(f"malformed ledger {ledger}")
    return r


def grant(ledger, plan, quote, scope=None):
    """Record the approval. Scope defaults to the grantable actions the plan names and may only
    narrow that; merge needs the quote to be exactly "approve merge" (default scope drops it, an
    explicit merge scope without it is refused); re-granting keeps already-parked actions."""
    named = _named(plan) & GRANTABLE
    if not _approves_merge(quote):
        named.discard("merge")
    scope = set(scope) if scope else named
    if not quote.strip() or not scope or scope - named:
        raise ValueError(f"need a verbatim quote and a scope the plan's Grants line names, merge only if the "
                         f"quote is exactly \"approve merge\" (grantable: {sorted(GRANTABLE)}); plan names {sorted(named)}, "
                         f"asked {sorted(scope)}")
    try:
        old = _load(ledger)
    except ValueError:
        old = {}
    rec = {"plan_sha256": _sha(plan), "quote": quote, "scope": sorted(scope),
           "date": datetime.date.today().isoformat(), "parked": old.get("parked", []), "log": old.get("log", [])}
    Path(ledger).write_text(json.dumps(rec))
    return rec


def check(ledger, plan, action):
    """0 = covered; 3 = park (no grant, not grantable, plan does not name it, plan changed, or an
    unrouted action, or merge without a clean "approve merge" quote). Raises ValueError on a
    missing or malformed ledger. Every park is appended to the event log; `parked` holds the
    distinct ones."""
    rec = _load(ledger)
    if not rec:
        raise ValueError(f"no ledger {ledger}; run grant first")
    if (action in GRANTABLE and action in rec["scope"] and action in _named(plan)
            and rec["plan_sha256"] == _sha(plan) and (action != "merge" or _approves_merge(rec["quote"]))):
        return 0
    rec["log"].append(action)
    if action not in rec["parked"]:
        rec["parked"].append(action)
    Path(ledger).write_text(json.dumps(rec))
    return 3


def parked(ledger):
    """Distinct parked actions in first-park order. ValueError if the `parked` list disagrees with
    the park-event log (an entry added or removed by hand)."""
    rec = _load(ledger)
    if not rec:
        raise ValueError(f"no ledger {ledger}; run grant first")
    if rec["parked"] != list(dict.fromkeys(rec["log"])):
        raise ValueError("parked list disagrees with the park-event log; ledger was edited, ask the user")
    return rec["parked"]


def simulate(tmp):
    """Prompts a user sees per ticket as (name, before, after, after_with_merge_named). Without a
    grant the plan and every gated action each prompt; with one, the plan prompt plus one batched
    end-of-run prompt if anything was parked. Runs the real grant/check, no network."""
    seqs = {"clean": ["push", "pr", "merge"],
            "one review round": ["push", "push", "pr", "merge"],
            "review round + deploy": ["push", "push", "pr", "merge", "deploy"]}
    plans = {}
    for tag, grants in (("default", "push, pr"), ("merge", "push, pr, merge")):
        plans[tag] = Path(tmp, f"plan-{tag}.md")
        plans[tag].write_text(f"add a feature\nGrants: {grants}\n")
    rows = []
    for name, seq in seqs.items():
        after = []
        for tag, plan in plans.items():
            led = str(Path(tmp, f"{name.replace(' ', '_')}-{tag}.json"))
            grant(led, plan, "approve merge" if tag == "merge" else "approve the plan")
            n_parked = sum(1 for a in seq if check(led, plan, a) == 3)
            after.append(1 + (1 if n_parked else 0))
        rows.append((name, 1 + len(seq), *after))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["grant", "check", "parked", "simulate"])
    ap.add_argument("action", nargs="?")
    ap.add_argument("--ledger")
    ap.add_argument("--plan")
    ap.add_argument("--quote", default="")
    ap.add_argument("--scope")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "grant":
            print(json.dumps(grant(a.ledger, a.plan, a.quote, a.scope.split(",") if a.scope else None)))
        elif a.cmd == "check":
            rc = check(a.ledger, a.plan, a.action)
            print("covered (advisory: ledger is agent-writable)" if rc == 0 else f"park {a.action}")
            return rc
        elif a.cmd == "parked":
            print("\n".join(parked(a.ledger)))
        else:
            with tempfile.TemporaryDirectory() as t:
                print("ticket\tprompts_before\tprompts_after\tprompts_after_merge_named")
                for r in simulate(t):
                    print("\t".join(map(str, r)))
    except (ValueError, OSError, TypeError) as e:
        print(f"plan_gate: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
