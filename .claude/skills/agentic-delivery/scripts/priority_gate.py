#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=no presentation-only PR while an aged P0 or mechanism issue has no PR, review=2027-01-30
"""priority_gate.py — no presentation-only PR while an aged P0/mechanism issue has no PR citing it.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
One private delivery audit (generalized; no identifiers kept) found the
presentation-layer share of work rising to 48% while feature work fell to 9%,
and the mechanism/P0 issues stayed open with zero PRs citing them. Every
cosmetic PR was individually cheap and reviewable; together they were a
priority inversion nobody decided on. This gate makes the inversion a visible,
blocking fact at review time instead of a retrospective finding.

THE RULE
--------
FAIL the PR under review when BOTH hold:
  1. it is presentation work: it carries a presentation label, or every one
     of its changed paths matches a presentation glob (a PR that also touches
     a non-presentation path is not presentation-only); and
  2. some OPEN issue (no `state` field, or `state: "open"`) carries a
     priority label, is at least `--min-age-hours` old, and has no open or
     merged PR citing it. A PR cites issue N when its
     title/body contains `#N`, or the issue's own `citing_prs` list names it
     (in `--repo` mode, from the issue timeline's cross-referenced events).
     A closed-unmerged PR does not count: abandoned work is not work. The PR
     under review never counts as its own citation (neither its own
     title/body, nor its entry in `prs` or `citing_prs`): a presentation PR
     that merely mentions `#N` would otherwise clear the gate by itself.
Optional `--budget F` (0..1): also FAIL a presentation PR when presentation
PRs already exceed fraction F of the PRs merged in the 24 hours before `now`.

HONESTY
-------
The gate checks that SOME PR cites each aged priority issue. It cannot judge
whether the citing PR actually advances the issue, whether a label is
accurate, or whether the priority is right. Labels and globs are the
operator's configuration; a mislabeled issue defeats the gate silently.

INPUT (pure function over one JSON document, so it is testable offline)
------------------------------------------------------------------------
  {"now": "2026-09-23T12:00:00Z",            # optional; else --now, else UTC now
   "pr":  {"number": 7, "title": "", "body": "", "labels": ["ui"],
           "paths": ["web/app.css"]},        # paths required and non-empty
   "issues": [{"number": 3, "labels": ["P0"], "created_at": "...Z",
               "citing_prs": [{"number": 9, "state": "merged"}]}],
   "prs": [{"number": 9, "title": "", "body": "Refs #3", "labels": [],
            "paths": ["src/x.py"], "state": "open|merged|closed",
            "merged_at": "...Z|null"}]}
Labels may be strings or `{"name": ...}` objects; matching is
case-insensitive. Timestamps must carry a timezone. `--repo O/R --pr N`
builds this document through `gh api` (paginated) and evaluates the same way.

EXIT CODES (fail closed)
------------------------
  0  not presentation work, or no aged uncited priority issue (and budget ok)
  1  a BLOCKING line per aged uncited priority issue, and/or a BUDGET line
  2  unresolvable input: unreadable/malformed JSON, a missing or mistyped
     field, an unparseable or timezone-less timestamp, an empty path list, a
     budget outside 0..1, a `gh` failure, or the sibling fix_class_gate.py
     (glob grammar) missing.

USAGE
-----
  priority_gate.py --labels-json FILE [options]
  priority_gate.py --repo OWNER/REPO --pr N [options]
  priority_gate.py --selftest
options: --presentation-label L ... --presentation-glob G ... --priority-label L ...
         --min-age-hours H (24) --budget F --now ISO
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable

sys.dont_write_bytecode = True
from refix_gate import load_fix_class_gate  # noqa: E402  (sibling script; one loader)

OK, FAIL, ERROR = 0, 1, 2
DEFAULT_PRESENTATION_LABELS = ("presentation", "cosmetic", "ui", "styling")
DEFAULT_PRESENTATION_GLOBS = ("**/*.css", "**/*.scss", "**/*.sass", "**/*.less",
                              "**/*.styl", "**/*.svg", "**/styles/**")
DEFAULT_PRIORITY_LABELS = ("P0", "mechanism")
DEFAULT_MIN_AGE_HOURS = 24.0
BUDGET_WINDOW = timedelta(hours=24)
MAX_PAGES = 50

GhRunner = Callable[[list], str]


class InputError(ValueError):
    """The input cannot be evaluated; the caller must exit 2."""


class GhError(RuntimeError):
    """A `gh` invocation failed; the caller must exit 2."""


def parse_ts(value, what: str) -> datetime:
    """Parse an ISO-8601 timestamp that carries a timezone; raise InputError otherwise."""
    if not isinstance(value, str):
        raise InputError(f"{what}: timestamp missing or not a string ({value!r})")
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError(f"{what}: unparseable timestamp {value!r}") from None
    if ts.tzinfo is None:
        raise InputError(f"{what}: timestamp {value!r} has no timezone")
    return ts


def _labels(obj: dict, what: str) -> set:
    """Lower-cased label names from a list of strings or {name} objects."""
    raw = obj.get("labels")
    if not isinstance(raw, list):
        raise InputError(f"{what}: 'labels' must be a list")
    names = set()
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else item
        if not isinstance(name, str):
            raise InputError(f"{what}: label {item!r} is not a string or {{name}} object")
        names.add(name.lower())
    return names


def _number(obj, what: str) -> int:
    if not isinstance(obj, dict) or not isinstance(obj.get("number"), int):
        raise InputError(f"{what}: must be an object with an integer 'number'")
    return obj["number"]


def _paths(obj: dict, what: str) -> list:
    paths = obj.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise InputError(f"{what}: 'paths' must be a non-empty list of strings")
    return paths


def _cites(text: str, n: int) -> bool:
    return re.search(rf"(?<![\w/&])#{n}(?!\d)", text or "") is not None


def evaluate(doc, *, presentation_labels=DEFAULT_PRESENTATION_LABELS,
             presentation_globs=DEFAULT_PRESENTATION_GLOBS, priority_labels=DEFAULT_PRIORITY_LABELS,
             min_age_hours=DEFAULT_MIN_AGE_HOURS, budget=None, now=None, fcg=None) -> tuple[int, list[str]]:
    """Pure verdict over one input document; return (exit_code, printable lines). No I/O.

    `now` (a tz-aware datetime) overrides doc["now"]; with neither, the
    current UTC time is used. `fcg` is the loaded fix_class_gate module
    (glob grammar); None fails closed.
    """
    if fcg is None:
        return ERROR, ["error: sibling deep-code-review/scripts/fix_class_gate.py not found (fail closed)"]
    try:
        if budget is not None and not 0 <= budget <= 1:
            raise InputError(f"--budget must be within 0..1 (got {budget})")
        if not min_age_hours >= 0:
            raise InputError(f"--min-age-hours must be >= 0 (got {min_age_hours})")
        if not isinstance(doc, dict):
            raise InputError("top level must be a JSON object")
        if now is None:
            now = parse_ts(doc["now"], "now") if "now" in doc else datetime.now(timezone.utc)
        pr = doc.get("pr")
        pr_n = _number(pr, "pr")
        pr_labels, pr_paths = _labels(pr, "pr"), _paths(pr, "pr")
        issues, prs = doc.get("issues"), doc.get("prs", [])
        if not isinstance(issues, list) or not isinstance(prs, list):
            raise InputError("'issues' must be a list and 'prs' (optional) a list")
        globs = fcg._compile_globs(tuple(presentation_globs))
        pres_set = {x.lower() for x in presentation_labels}
        prio_set = {x.lower() for x in priority_labels}

        def is_presentation(labels: set, paths: list) -> bool:
            return bool(labels & pres_set) or all(fcg._matches_any(p, globs) for p in paths)

        # The PR under review is excluded from every citation source: its
        # own title/body, its entry in `prs` (in --repo mode the open-PR list
        # includes it), and its entry in any issue's `citing_prs`.
        live_texts = []
        merged_recent = []
        for i, other in enumerate(prs):
            what = f"prs[{i}]"
            other_n = _number(other, what)
            state = other.get("state")
            if state not in ("open", "merged", "closed"):
                raise InputError(f"{what}: 'state' must be open|merged|closed")
            if state in ("open", "merged") and other_n != pr_n:
                live_texts.append(f"{other.get('title', '')}\n{other.get('body', '')}")
            if budget is not None and state == "merged":
                merged_at = parse_ts(other.get("merged_at"), f"{what}.merged_at")
                if now - BUDGET_WINDOW <= merged_at <= now:
                    merged_recent.append(is_presentation(_labels(other, what), _paths(other, what)))

        blocking = []
        for i, issue in enumerate(issues):
            what = f"issues[{i}]"
            n = _number(issue, what)
            labels = _labels(issue, what)
            created = parse_ts(issue.get("created_at"), f"{what}.created_at")
            citing = issue.get("citing_prs", [])
            if not isinstance(citing, list):
                raise InputError(f"{what}: 'citing_prs' must be a list")
            hit = labels & prio_set if issue.get("state", "open") == "open" else set()
            age = max(0.0, (now - created).total_seconds() / 3600)
            if not hit or age < min_age_hours:
                continue
            cited = any(isinstance(c, dict) and c.get("state") in ("open", "merged")
                        and c.get("number") != pr_n for c in citing) \
                or any(_cites(t, n) for t in live_texts)
            if not cited:
                blocking.append(f"BLOCKING #{n} [{','.join(sorted(hit))}] age={age:.1f}h has no open or merged PR citing it")
    except InputError as exc:
        return ERROR, [f"error: {exc}"]

    if not is_presentation(pr_labels, pr_paths):
        return OK, [f"priority_gate: ok (PR #{pr_n} is not presentation-only work)"]
    lines = list(blocking)
    if budget is not None and merged_recent:
        share = sum(merged_recent) / len(merged_recent)
        if share > budget:
            lines.append(f"BUDGET presentation share of PRs merged in the last 24h is "
                         f"{sum(merged_recent)}/{len(merged_recent)} = {share:.0%}, above the {budget:.0%} budget")
    if lines:
        lines.append(f"priority_gate: FAILED (PR #{pr_n} is presentation work; land or cite the priority work first)")
        return FAIL, lines
    return OK, [f"priority_gate: ok (PR #{pr_n} is presentation work; no aged uncited priority issue)"]


# --------------------------------------------------------------------------
# --repo mode: build the same document through `gh api` (injectable runner).
# --------------------------------------------------------------------------

def real_gh(args: list) -> str:
    """Run `gh api <args>`; return stdout or raise GhError."""
    try:
        proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    except OSError as exc:
        raise GhError(f"cannot run gh: {exc}") from None
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip() or f"gh api {' '.join(args)} failed (rc={proc.returncode})")
    return proc.stdout


def _jsonl(text: str) -> list:
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise GhError(f"gh returned non-JSON output: {exc}") from None


def fetch_doc(gh: GhRunner, repo: str, pr_number: int, priority_labels, want_budget: bool,
              now: datetime) -> dict:
    """Assemble the evaluate() input for `repo`/`pr_number` via paginated `gh api` calls.

    Reads only; raises GhError on any failed or malformed call (the caller
    exits 2). Timelines are fetched only for open issues carrying a priority
    label; merged PRs only when a budget is set, walking closed PRs sorted by
    last update until one predates the window (merging updates a PR, so no
    PR merged inside the window can sort below that point).
    """
    base = f"repos/{repo}"
    pr = _jsonl(gh([f"{base}/pulls/{pr_number}", "--jq",
                    "{number, title, body, labels: [.labels[].name]}"]))
    if len(pr) != 1:
        raise GhError(f"expected one PR object for #{pr_number}")
    pr = pr[0]
    pr["paths"] = [p for p in gh(["--paginate", f"{base}/pulls/{pr_number}/files?per_page=100",
                                  "--jq", ".[].filename"]).splitlines() if p]
    issues = _jsonl(gh(["--paginate", f"{base}/issues?state=open&per_page=100", "--jq",
                        ".[] | select(.pull_request == null) | {number, created_at, labels: [.labels[].name]}"]))
    prio = {x.lower() for x in priority_labels}
    for issue in issues:
        if prio & {str(x).lower() for x in issue.get("labels", [])}:
            refs = _jsonl(gh(["--paginate", f"{base}/issues/{issue['number']}/timeline?per_page=100", "--jq",
                              '.[] | select(.event == "cross-referenced") | .source.issue '
                              "| select(.pull_request != null) "
                              "| {number, state, merged_at: .pull_request.merged_at}"]))
            issue["citing_prs"] = [{"number": r.get("number"),
                                    "state": "merged" if r.get("merged_at") else r.get("state")} for r in refs]
    prs = _jsonl(gh(["--paginate", f"{base}/pulls?state=open&per_page=100", "--jq",
                     '.[] | {number, title, body, labels: [.labels[].name], state: "open"}']))
    if want_budget:
        cutoff = now - BUDGET_WINDOW
        for page in range(1, MAX_PAGES + 1):
            rows = _jsonl(gh([f"{base}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}",
                              "--jq", ".[] | {number, title, body, labels: [.labels[].name], "
                              "merged_at, updated_at}"]))
            for row in rows:
                if row.get("merged_at") and parse_ts(row["merged_at"], "merged_at") >= cutoff:
                    row["state"] = "merged"
                    row["paths"] = [p for p in gh(["--paginate", f"{base}/pulls/{row['number']}/files?per_page=100",
                                                   "--jq", ".[].filename"]).splitlines() if p]
                    prs.append(row)
            if not rows or parse_ts(rows[-1].get("updated_at"), "updated_at") < cutoff:
                break
        else:
            raise GhError(f"more than {MAX_PAGES} pages of recently-updated closed PRs; cannot bound the budget window")
    return {"pr": pr, "issues": issues, "prs": prs}


# --------------------------------------------------------------------------
# Selftest (offline fixtures only; the gh runner is faked).
# --------------------------------------------------------------------------

NOW = "2026-01-10T12:00:00Z"


def _doc(pr_labels=("ui",), pr_paths=("web/app.css",), issue_labels=("P0",), created="2026-01-08T12:00:00Z",
         citing=(), prs=(), pr_body=""):
    return {"now": NOW,
            "pr": {"number": 7, "title": "polish", "body": pr_body, "labels": list(pr_labels), "paths": list(pr_paths)},
            "issues": [{"number": 3, "labels": list(issue_labels), "created_at": created, "citing_prs": list(citing)}],
            "prs": list(prs)}


def _selftest() -> int:
    """Assert every verdict branch, the fail-closed inputs, and --repo assembly on fake gh output."""
    fcg = load_fix_class_gate()
    if fcg is None:
        print("SELFTEST FAILED: sibling fix_class_gate.py not found")
        return 1
    failures: list[str] = []
    ran = [0]

    def case(label, doc, want, must=(), **kw):
        ran[0] += 1
        kw.setdefault("fcg", fcg)
        rc, lines = evaluate(doc, **kw)
        out = "\n".join(lines)
        if rc != want:
            failures.append(f"{label}: rc={rc} want {want}: {out}")
        failures.extend(f"{label}: missing {m!r}: {out}" for m in must if m not in out)

    merged = lambda n, labels, paths, at="2026-01-10T06:00:00Z": {  # noqa: E731
        "number": n, "labels": labels, "paths": paths, "state": "merged", "merged_at": at}
    # Planted violation: presentation PR while a 48h-old P0 has no citing PR -> FIRES.
    case("inversion-fires", _doc(), FAIL, must=("BLOCKING #3", "age=48.0h"))
    case("path-classified-fires", _doc(pr_labels=()), FAIL, must=("BLOCKING #3",))
    case("mixed-paths-not-presentation", _doc(pr_labels=(), pr_paths=("web/app.css", "src/core.py")), OK)
    case("label-case-insensitive", _doc(pr_labels=("UI",), pr_paths=("src/core.py",)), FAIL)
    case("young-issue-passes", _doc(created="2026-01-10T00:00:00Z"), OK)
    case("non-priority-issue-passes", _doc(issue_labels=("bug",)), OK)
    closed_doc = _doc()
    closed_doc["issues"][0]["state"] = "closed"
    case("closed-issue-ignored", closed_doc, OK)
    case("cited-by-open-pr-body", _doc(prs=[{"number": 9, "body": "Refs #3", "state": "open"}]), OK)
    # The PR under review never cites for itself: not its own body, not its
    # own entry in `prs`, not its own entry in `citing_prs`.
    case("cited-by-own-body", _doc(pr_body="also advances #3"), FAIL, must=("BLOCKING #3",))
    case("own-entry-in-prs-does-not-cite", _doc(prs=[{"number": 7, "body": "Refs #3", "state": "open"}]), FAIL)
    case("own-timeline-ref-does-not-cite", _doc(citing=[{"number": 7, "state": "open"}]), FAIL)
    case("cited-by-timeline-merged", _doc(citing=[{"number": 9, "state": "merged"}]), OK)
    case("closed-unmerged-does-not-cite", _doc(citing=[{"number": 9, "state": "closed"}],
                                               prs=[{"number": 9, "body": "Fixes #3", "state": "closed"}]), FAIL)
    case("longer-number-is-not-a-cite", _doc(prs=[{"number": 9, "body": "see #31", "state": "open"}]), FAIL)
    case("custom-priority-label", _doc(issue_labels=("sev1",)), FAIL, priority_labels=("sev1",))
    case("custom-presentation-label", _doc(pr_labels=("theme",), pr_paths=("src/x.py",)), FAIL,
         presentation_labels=("theme",))
    over = [merged(1, ["ui"], ["a.css"]), merged(2, ["ui"], ["b.css"]), merged(3, [], ["src/c.py"])]
    case("budget-fires", _doc(issue_labels=("bug",), prs=over), FAIL, must=("BUDGET", "2/3"), budget=0.5)
    case("budget-within", _doc(issue_labels=("bug",), prs=over), OK, budget=0.7)
    case("budget-ignores-old-merges", _doc(issue_labels=("bug",), prs=[merged(1, ["ui"], ["a.css"], "2026-01-01T00:00:00Z")]),
         OK, budget=0.1)
    case("budget-not-applied-to-mechanism-pr", _doc(pr_labels=(), pr_paths=("src/core.py",), issue_labels=("bug",),
                                                    prs=over), OK, budget=0.1)
    case("budget-counts-window", _doc(issue_labels=("bug",), prs=over + [merged(8, [], ["src/d.py"], "2026-01-01T00:00:00Z")]), FAIL, must=("2/3",), budget=0.5)
    # Fail-closed inputs.
    case("missing-created-at", {"now": NOW, "pr": _doc()["pr"], "issues": [{"number": 3, "labels": ["P0"]}]}, ERROR)
    case("naive-timestamp", _doc(created="2026-01-08T12:00:00"), ERROR)
    case("empty-paths", _doc(pr_paths=()), ERROR)
    case("labels-not-list", {"now": NOW, "pr": {"number": 7, "labels": "ui", "paths": ["a.css"]}, "issues": []}, ERROR)
    case("missing-pr", {"now": NOW, "issues": []}, ERROR)
    case("bad-budget", _doc(), ERROR, budget=1.5)
    case("bad-state", _doc(prs=[{"number": 9, "state": "draft"}]), ERROR)
    case("budget-merged-missing-paths", _doc(prs=[{"number": 1, "labels": [], "state": "merged",
                                                   "merged_at": "2026-01-10T06:00:00Z"}]), ERROR, budget=0.5)
    case("missing-glob-module", _doc(), ERROR, fcg=None)

    # --repo assembly on canned gh output, then the same verdict.
    def fake_gh(fail_on: str = "", self_cite: bool = False) -> GhRunner:
        def run(args: list) -> str:
            path = next(a for a in args if a.startswith("repos/"))
            if fail_on and fail_on in path:
                raise GhError("HTTP 502")
            if path.endswith("/pulls/7"):
                body = "touches #3" if self_cite else ""
                return json.dumps({"number": 7, "title": "polish", "body": body, "labels": ["ui"]}) + "\n"
            if path.endswith("/files?per_page=100"):
                return "web/app.css\n" if "/pulls/7/" in path else "src/c.py\n"
            if "/issues?state=open" in path:
                return json.dumps({"number": 3, "created_at": "2026-01-08T12:00:00Z", "labels": ["P0"]}) + "\n"
            if "/timeline" in path:
                if self_cite:
                    return json.dumps({"number": 7, "state": "open", "merged_at": None}) + "\n"
                return json.dumps({"number": 9, "state": "closed", "merged_at": None}) + "\n"
            if "state=open" in path:
                if self_cite:
                    return json.dumps({"number": 7, "title": "polish", "body": "touches #3",
                                       "labels": ["ui"], "state": "open"}) + "\n"
                return ""
            if "state=closed" in path and path.endswith("page=1"):
                return (json.dumps({"number": 5, "labels": [], "merged_at": "2026-01-10T01:00:00Z",
                                    "updated_at": "2026-01-10T01:00:00Z"}) + "\n"
                        + json.dumps({"number": 4, "labels": [], "merged_at": None,
                                      "updated_at": "2026-01-01T00:00:00Z"}) + "\n")
            raise GhError(f"unexpected gh call {args}")
        return run

    now = parse_ts(NOW, "now")
    ran[0] += 4
    try:
        doc = fetch_doc(fake_gh(), "acme/widgets", 7, DEFAULT_PRIORITY_LABELS, True, now)
        rc, lines = evaluate(doc, now=now, fcg=fcg, budget=0.9)
        if rc != FAIL or "BLOCKING #3" not in "\n".join(lines) or len(doc["prs"]) != 1:
            failures.append(f"repo-mode-fires: rc={rc} prs={doc['prs']} lines={lines}")
        doc["issues"][0]["citing_prs"] = [{"number": 9, "state": "open"}]
        if evaluate(doc, now=now, fcg=fcg)[0] != OK:
            failures.append("repo-mode-open-citation-passes")
    except GhError as exc:
        failures.append(f"repo-mode: unexpected GhError {exc}")
    # --repo mode: the PR under review appears in the open-PR list and in the
    # issue timeline citing #3; neither may count as a citation.
    try:
        doc = fetch_doc(fake_gh(self_cite=True), "acme/widgets", 7, DEFAULT_PRIORITY_LABELS, False, now)
        rc, lines = evaluate(doc, now=now, fcg=fcg)
        if rc != FAIL or "BLOCKING #3" not in "\n".join(lines):
            failures.append(f"repo-mode-self-cite-excluded: rc={rc} lines={lines}")
    except GhError as exc:
        failures.append(f"repo-mode-self-cite-excluded: unexpected GhError {exc}")
    try:
        fetch_doc(fake_gh(fail_on="/timeline"), "acme/widgets", 7, DEFAULT_PRIORITY_LABELS, False, now)
        failures.append("repo-mode-gh-failure: no GhError raised")
    except GhError:
        pass

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST OK: priority_gate {ran[0]}/{ran[0]} cases passed")
    return 0


def main(argv: list | None = None) -> int:
    """CLI entry point; see the module docstring for modes, options, and exit codes."""
    ap = argparse.ArgumentParser(description="Fail a presentation-only PR while an aged priority issue "
                                 "has no PR citing it.")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--labels-json", metavar="FILE", help="evaluate this JSON document (offline)")
    src.add_argument("--repo", metavar="OWNER/REPO", help="fetch the document via gh api (needs --pr)")
    ap.add_argument("--pr", type=int, help="PR number under review (--repo mode)")
    ap.add_argument("--presentation-label", action="append", metavar="L", help="repeatable; replaces defaults")
    ap.add_argument("--presentation-glob", action="append", metavar="G", help="repeatable; replaces defaults")
    ap.add_argument("--priority-label", action="append", metavar="L", help="repeatable; replaces defaults")
    ap.add_argument("--min-age-hours", type=float, default=DEFAULT_MIN_AGE_HOURS)
    ap.add_argument("--budget", type=float, help="max presentation share (0..1) of PRs merged in the last 24h")
    ap.add_argument("--now", help="ISO timestamp overriding the evaluation clock")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    fcg = load_fix_class_gate()
    kw = {"presentation_labels": tuple(args.presentation_label or DEFAULT_PRESENTATION_LABELS),
          "presentation_globs": tuple(args.presentation_glob or DEFAULT_PRESENTATION_GLOBS),
          "priority_labels": tuple(args.priority_label or DEFAULT_PRIORITY_LABELS),
          "min_age_hours": args.min_age_hours, "budget": args.budget, "fcg": fcg}
    try:
        now = parse_ts(args.now, "--now") if args.now else None
        if args.labels_json:
            try:
                with open(args.labels_json, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                raise InputError(f"cannot read {args.labels_json}: {exc}") from None
        elif args.repo:
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or args.pr is None:
                raise InputError("--repo needs OWNER/REPO and --pr N")
            now = now or datetime.now(timezone.utc)
            doc = fetch_doc(real_gh, args.repo, args.pr, kw["priority_labels"], args.budget is not None, now)
        else:
            raise InputError("one of --labels-json FILE or --repo OWNER/REPO is required")
    except (InputError, GhError) as exc:
        print(f"error: {exc}")
        return ERROR
    code, lines = evaluate(doc, now=now, **kw)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
