#!/usr/bin/env python3
"""ci_cost_advisor.py — estimate a repo's GitHub Actions minutes and dollars, and print a local-first plan with a ready patch.

WHY THIS EXISTS
---------------
Many owners want the gates to run on their own machine, not on paid Actions minutes. `ci_cost_lint.py` flags the
structural levers; this prices them. It reads `.github/workflows/*`, the repository's visibility and its git
history, estimates runs, minutes and dollars per push/PR and per month, and recommends a "local-first" plan: run
the full gate locally before the push (the cached pre-push gate, `pre-push-verify.sh`), keep only a cheap required
check in Actions, trim the rest. It prints before/after numbers and a unified diff. It NEVER edits a workflow: the
patch goes to stdout for the owner to review and `git apply`.

WHAT IT KNOWS (docs.github.com, fetched 2026-10-16; URLs in docs/standards-index.md)
------------------------------------------------------------------------------------
- Standard GitHub-hosted runners in PUBLIC repositories are free (so are self-hosted runners); larger runners are
  always billed. A public repo on standard runners therefore gets a one-line "free" verdict and no plan.
- Private repos get a monthly quota of included minutes per plan (Free 2,000, Pro 3,000, Team 3,000, Enterprise
  Cloud 50,000), then pay per minute: Linux 2-core $0.006, Linux arm64 $0.005, Linux 1-core `ubuntu-slim` $0.002,
  Windows $0.010, macOS $0.062. GitHub rounds every JOB up to a whole minute, so ten 10-second jobs bill 10 minutes.
- A workflow skipped by a path filter, branch filter or `[skip ci]` leaves its checks "Pending", which blocks a PR
  that requires them; a job skipped by an `if:` reports "Success". So a REQUIRED workflow never gets a path filter.

THE MODEL (every number is computed; inputs you do not give are labelled "assumed")
-----------------------------------------------------------------------------------
runs/month per workflow = sum over its triggers of
  pull_request   merged PRs x (share of PRs whose files pass the filters) x pushes per PR (`types:` respected)
  push           default branch: one run per merged PR; unfiltered branches add one run per PR-branch push
                 (the push + pull_request double trigger); tag pushes count the matching tags in the window
  schedule       fires per month computed from the cron fields
billed minutes per run = sum over jobs of ceil(job minutes) x matrix legs, each leg at its `runs-on` rate (a
`${{ matrix.os }}` label is priced per axis value). Merged PRs, their changed files and the release tags come
from `git log --first-parent` over the last 30 days (`--prs` overrides the count); job minutes default to 5 (an
assumption: pass measured numbers with `--job-minutes`). Not modelled: job-level `if:`, reusable-workflow calls,
cancel-in-progress savings (they depend on push timing), `fail-fast`. Included minutes are valued at the Linux
2-core rate (the fetched pages do not say how Windows/macOS minutes draw the quota down) and are shared by every
private repo on the account, so "billed" is a lower bound.

THE PLAN AND THE PATCH (only edits that cannot strand a required check; unknown means "possibly required")
------------------------------------------------------------------------------------------------------
  PR workflow without cancel-in-progress   add `concurrency`, grouped per PR number (run id otherwise), so only a
                                           superseded PR run is cancelled and a push or schedule run never is
  push + pull_request, strict protection   drop `push` (--strict-protection or `--repo` lookup)
  push + pull_request, not strict          limit `push` to the default branch (stops the PR-branch double trigger)
  `--required` names the required files    for any other workflow: a gate-like one (test command) moves to
                                           `workflow_dispatch` once a local pre-push gate exists (hook or
                                           scripts/dcr-gates.sh); a path filter for docs goes in only when it
                                           would have skipped 0 < x <= 50% of the last 30 days of PRs (a filter that
                                           skips most PRs is filtering the product, e.g. a repo whose skills are .md)
Everything else is advice with its measured cost: shrink each required check to one cheap job (the owner knows
which gates are cheap), `[skip ci]` on doc-only commits only where no required check applies, schedules to a local
cron, big matrices to weekly or local. The after-numbers re-price the PATCHED workflow text (one model, no second
formula), then add "push each PR once" and "required checks cost `--cheap-minutes`".

USAGE
-----
  ci_cost_advisor.py [ROOT] [--visibility auto|public|private] [--plan free|pro|team|enterprise]
      [--required FILE[,FILE]|none] [--strict-protection | --repo OWNER/REPO] [--default-branch NAME]
      [--prs N] [--pushes-per-pr N] [--job-minutes [FILE[:JOB]=]MIN ...] [--cheap-minutes N] [--doc-glob GLOB ...]
  ci_cost_advisor.py ROOT --patch | git apply     only the diff on stdout (nothing is written by this tool)
  ci_cost_advisor.py ROOT --decide                prints `local-first` or `cloud` (reason on stderr); the
                                                  `auto` mode of policy key `ci` (perun_policy.py ci)
  ci_cost_lint.py --advise ROOT                   the lint's findings, then this report

Visibility `auto` reads the `origin` remote and sends one unauthenticated HEAD to github.com (200 public, 404
private or missing; cached 24h under the git dir). Anything unresolved is treated as private: the billable case.
Exit 0; 2 when ROOT does not exist.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_cost_lint as lint  # noqa: E402  (one YAML-subset parser and trigger model; never a second copy)

# USD per minute (standard runners) and included minutes per plan: docs.github.com, fetched 2026-10-16.
RATES = {"linux": 0.006, "linux-arm": 0.005, "linux-slim": 0.002, "windows": 0.010, "macos": 0.062}
PLANS = {"free": 2000, "pro": 3000, "team": 3000, "enterprise": 50000}
# `runs-on` label -> rate class: the standard-runner label table of the GitHub-hosted runners reference.
_RUNNERS = (
    (r"ubuntu-slim", "linux-slim"),
    (r"ubuntu-\d\d\.\d\d-arm", "linux-arm"),
    (r"ubuntu-(latest|\d\d\.\d\d)", "linux"),
    (r"windows-(latest|\d{4}|11-arm|11-vs2026-arm)", "windows"),
    (r"(macos-(latest|\d+|\d+-intel)|xcode-\d+)", "macos"),
)
DAYS = 30
MONTH_DAYS = 365 / 12
ASSUMED_PRS = 20  # used only when git has no history and --prs is absent; always printed as assumed
AUTO_LOCAL_FRACTION = 0.5  # `ci: auto` goes local-first at >= this share of the plan's included minutes
MAX_SKIP_SHARE = 0.5  # never propose a path filter that would have skipped more than this share of recent PRs
DOC_GLOBS = ("**.md", "docs/**", "LICENSE")
# Grouped per PR number and per run id otherwise: only a superseded PR run is cancelled; push and schedule runs
# never share a group, so none is replaced while pending (a shared group would drop intermediate main runs).
CONCURRENCY = "concurrency:\n  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}\n  cancel-in-progress: true\n"


@dataclass
class Ctx:
    """Everything the model needs besides the workflow text."""
    private: bool = True  # billable: private, internal or unknown
    allowance: int = PLANS["free"]
    prs: float = ASSUMED_PRS
    pushes: float = 3
    files: list = field(default_factory=list)  # changed-file set per merged PR in the window (empty = no history)
    tags: list = field(default_factory=list)
    default_branch: str = "main"
    strict: bool | None = None
    required: frozenset | None = None  # basenames of required workflows; None = unknown
    mins: dict = field(default_factory=lambda: {"*": 5.0})
    cheap: float = 1
    docs: tuple = DOC_GLOBS
    local_gate: bool = True  # a pre-push gate exists, so a non-required workflow may leave Actions


# ---- GitHub filter patterns ------------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _tokens(pat: str) -> tuple:
    """A filter pattern as ((char predicate, repeat), ...), repeat one of "", "?", "+", "*"."""
    toks, i = [], 0
    while i < len(pat):
        c = pat[i]
        if c == "*":
            two = pat.startswith("**", i)
            toks.append(((lambda ch: True) if two else (lambda ch: ch != "/"), "*"))
            i += 2 if two else 1
        elif c in "?+" and toks and toks[-1][1] == "":
            toks[-1] = (toks[-1][0], c)
            i += 1
        else:
            j = pat.find("]", i + 1) if c == "[" else -1
            try:
                rx = re.compile(pat[i:j + 1]) if j > i + 1 else None
            except re.error:
                rx = None
            toks.append(((lambda ch, rx=rx: rx.fullmatch(ch) is not None) if rx else (lambda ch, c=c: ch == c), ""))
            i = j + 1 if rx else i + 1
    return tuple(toks)


@lru_cache(maxsize=1 << 16)
def _glob(pat: str, s: str) -> bool:
    """GitHub filter-pattern match of the whole string (the "Filter pattern cheat sheet": `*` no slash, `**` anything,
    `?`/`+` quantify the previous character, `[..]` a class). An NFA walk, O(pattern x string): a hostile pattern in a
    scanned repo cannot cause regex backtracking."""
    toks = _tokens(pat)

    def close(states):  # skip over optional tokens
        out = set(states)
        for i in states:
            while i < len(toks) and toks[i][1] in ("?", "*"):
                i += 1
                out.add(i)
        return out

    cur = close({0})
    for ch in s:
        nxt = set()
        for i in cur:
            if i < len(toks) and toks[i][0](ch):
                nxt.add(i + 1)
                if toks[i][1] in ("+", "*"):
                    nxt.add(i)
        cur = close(nxt)
        if not cur:
            return False
    return len(toks) in cur


def _select(patterns, name: str) -> bool:
    """Ordered include/`!`exclude evaluation: a later match flips the earlier verdict."""
    hit = False
    for p in patterns:
        p = str(p)
        if p.startswith("!"):
            hit = hit and not _glob(p[1:], name)
        elif _glob(p, name):
            hit = True
    return hit


def _path_triggers(filt, files) -> bool:
    """Would a push/PR touching `files` start a workflow with this trigger's path filters?"""
    d = filt if isinstance(filt, dict) else {}
    if d.get("paths"):
        return any(_select(d["paths"], f) for f in files)
    if d.get("paths-ignore"):
        return not all(any(_glob(p, f) for p in d["paths-ignore"]) for f in files)
    return True


def _branch_ok(filt, branch: str) -> bool:
    d = filt if isinstance(filt, dict) else {}
    if isinstance(d.get("branches"), list):
        return _select(d["branches"], branch)
    if isinstance(d.get("branches-ignore"), list):
        return not any(_glob(p, branch) for p in d["branches-ignore"])
    return True


def _share(filt, ctx: Ctx) -> float:
    """Share of recent PRs whose changed files trigger this event; 1.0 without history."""
    if not ctx.files:
        return 1.0
    return sum(_path_triggers(filt, f) for f in ctx.files) / len(ctx.files)


def _tags_only(push) -> bool:
    d = push if isinstance(push, dict) else {}
    return ("tags" in d or "tags-ignore" in d) and "branches" not in d and "branches-ignore" not in d


# ---- the cost model --------------------------------------------------------------------------------------


def runner_class(label) -> str | None:
    """A RATES key for a standard `runs-on` label, "self-hosted" (free), or None for anything else (a larger or
    custom runner is never priced from a guess)."""
    label = str(label).strip().lower()
    if label == "self-hosted":
        return "self-hosted"
    return next((c for pat, c in _RUNNERS if re.fullmatch(pat, label)), None)


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _legs(job: dict) -> list:
    """[(rate class, legs)] for one job: the matrix size spread over `runs-on` (`${{ matrix.<axis> }}` is priced
    per axis value, including values that only appear in `include:` rows)."""
    strat = job.get("strategy")
    matrix = strat.get("matrix") if isinstance(strat, dict) else None
    matrix = matrix if isinstance(matrix, dict) else None
    ro = job.get("runs-on")
    label = ro.get("labels") if isinstance(ro, dict) else ro
    if isinstance(label, list):
        label = "self-hosted" if "self-hosted" in label else (label[0] if label else None)
    m = re.fullmatch(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", label) if isinstance(label, str) else None
    if matrix is None or not m:
        size = (lint._matrix_size(matrix) if matrix else 1) or 1
        return [(runner_class(label) if isinstance(label, str) else None, size)]
    axis = m.group(1)
    inc = [r for r in (matrix.get("include") or []) if isinstance(r, dict)]
    vals = matrix.get(axis) if isinstance(matrix.get(axis), list) and matrix[axis] else []
    core = lint._matrix_size({k: v for k, v in matrix.items() if k != "include"}) if vals else 0
    legs = [(runner_class(v), core / len(vals)) for v in vals]
    legs += [(runner_class(r.get(axis, vals[0] if vals else "")), 1) for r in inc]
    return legs or [(None, 1)]


def run_cost(wf: dict, base: str, mins: dict) -> tuple[dict, list]:
    """({rate class: billed minutes per run}, notes). A job is billed ceil(minutes) per matrix leg."""
    out: dict = {}
    notes: list = []
    for jid, job in (wf.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        if "uses" in job:
            notes.append(f"job '{jid}' calls a reusable workflow: billed where it is defined, not priced here")
            continue
        if isinstance(job.get("strategy"), dict) and isinstance(job["strategy"].get("matrix"), str):
            notes.append(f"job '{jid}' has a dynamic matrix: counted as one leg")
        m = mins.get(f"{base}:{jid}", mins.get(base, mins["*"]))
        t = _num(job.get("timeout-minutes"))
        m = math.ceil(min(m, t) if t else m)
        for cls, n in _legs(job):
            out[cls] = out.get(cls, 0) + n * m
    return out, notes


def _field_n(x: str, lo: int, hi: int) -> int:
    """How many values one cron field matches (ValueError on names, `L`, `?`)."""
    n = 0
    for part in x.split(","):
        rng, slash, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(v) for v in rng.split("-", 1))
        else:
            a = int(rng)
            b = hi if slash else a
        n += len(range(a, b + 1, int(step) if slash else 1))
    return n


def cron_runs(cron: str) -> float | None:
    """Fires per month for a 5-field cron; None when a field is not plain numbers. Day-of-month and day-of-week
    both set is cron's OR: counted as the sum (an upper bound)."""
    f = cron.split()
    if len(f) != 5:
        return None
    try:
        mi, ho, dom, mon, dow = (_field_n(x, lo, hi) for x, (lo, hi) in zip(f, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))))
    except ValueError:
        return None
    days = (
        MONTH_DAYS if f[2] == "*" and f[4] == "*" else min(dom, MONTH_DAYS) if f[4] == "*"
        else dow * MONTH_DAYS / 7 if f[2] == "*" else min(dom, MONTH_DAYS) + dow * MONTH_DAYS / 7
    )
    return mi * ho * days * mon / 12


def monthly_runs(on: dict, ctx: Ctx, pushes: float) -> tuple[dict, list]:
    """({event label: runs per month}, events this model does not count) for one workflow's normalized `on:`."""
    runs: dict = {}
    skipped: list = []
    for ev, v in on.items():
        d = v if isinstance(v, dict) else {}
        if ev in ("pull_request", "pull_request_target"):
            if _branch_ok(d, ctx.default_branch):
                types = set(d.get("types") or [])
                first = 1 if not types or types & {"opened", "reopened", "ready_for_review"} else 0
                more = pushes - 1 if not types or "synchronize" in types else 0
                runs[ev] = ctx.prs * _share(d, ctx) * (first + more)
        elif ev == "push":
            if _tags_only(v):
                pats, ign = d.get("tags"), d.get("tags-ignore") or []
                runs["push (tags)"] = sum(1 for t in ctx.tags if (_select(pats, t) if pats else not any(_glob(p, t) for p in ign)))
            else:
                share = _share(d, ctx)
                if _branch_ok(d, ctx.default_branch):
                    runs["push (default branch)"] = ctx.prs * share
                if _branch_ok(d, "feature/x"):
                    runs["push (PR branches)"] = ctx.prs * pushes * share
        elif ev == "schedule":
            runs["schedule"] = sum(x for x in (cron_runs(str(e.get("cron", ""))) for e in v if isinstance(e, dict)) if x) if isinstance(v, list) else 0
        elif ev not in ("workflow_dispatch", "workflow_call"):
            skipped.append(ev)
    return runs, skipped


@dataclass
class Row:
    path: str
    req: bool | None = None
    runs: dict = field(default_factory=dict)
    per_run: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def estimate(texts: dict, ctx: Ctx, *, pushes: float | None = None, shrink: frozenset = frozenset()) -> tuple[list, dict]:
    """(rows, {rate class: minutes per month}) for {path: workflow text}. `shrink` names workflow basenames priced
    as one cheap Linux job (`ctx.cheap` minutes). A workflow the lint cannot parse is a note, never a guess."""
    rows, total = [], {}
    for path, text in texts.items():
        base = os.path.basename(path)
        row = Row(path, None if ctx.required is None else base in ctx.required)
        rows.append(row)
        try:
            wf = lint.parse_workflow_yaml(text)
        except Exception as exc:  # fail closed like the lint: report, never crash or guess
            row.notes.append(f"not priced: {exc}")
            continue
        row.runs, skipped = monthly_runs(lint._normalize_on(wf.get("on")), ctx, ctx.pushes if pushes is None else pushes)
        row.per_run, row.notes = ({"linux": math.ceil(ctx.cheap)}, []) if base in shrink else run_cost(wf, base, ctx.mins)
        if skipped:
            row.notes.append(f"not counted (no model for the trigger): {', '.join(skipped)}")
        n = sum(row.runs.values())
        for cls, m in row.per_run.items():
            total[cls] = total.get(cls, 0) + m * n
    return rows, total


def list_price(minutes: dict) -> float:
    return sum(m * RATES.get(c, 0.0) for c, m in minutes.items())


def billed(minutes: dict, ctx: Ctx) -> float:
    """Dollars actually charged: nothing on a public repo's standard runners; else list price minus the plan's
    included minutes (valued at the Linux 2-core rate)."""
    if not ctx.private:
        return 0.0
    return max(0.0, list_price(minutes) - ctx.allowance * RATES["linux"])


def decide(minutes: dict, ctx: Ctx) -> tuple[str, str]:
    """The `auto` verdict: ("cloud"|"local-first", reason). Public repos stay on `cloud` (standard runners are
    free); a private one goes `local-first` once its estimated minutes reach AUTO_LOCAL_FRACTION of the plan's
    included minutes, because that quota is shared by every private repo on the account."""
    unpriced = f"; ~{_n(minutes[None])} min/mo on labels this tool cannot price: check them" if minutes.get(None) else ""
    if not ctx.private:
        return "cloud", "public repo on standard runners: Actions minutes are free" + unpriced
    eq = list_price(minutes) / RATES["linux"]
    pct = eq / ctx.allowance
    if eq and pct >= AUTO_LOCAL_FRACTION:
        return "local-first", f"~{_n(eq)} Linux-equivalent min/mo is {pct:.0%} of the {ctx.allowance:,} included (shared by every private repo on the account)" + unpriced
    return "cloud", f"~{_n(eq)} Linux-equivalent min/mo is {pct:.0%} of the {ctx.allowance:,} included: inside the free allowance" + unpriced


# ---- the patch (text edits, each verified by re-parsing) ---------------------------------------------------


def _scalar(x) -> str:
    """A bare word stays bare (a small diff); anything else, or a word YAML 1.1 reads as a bool/null, is quoted."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, str):
        return x if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_./-]*", x) and x.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "y", "n") else json.dumps(x)
    return "null" if x is None else str(x)


def _yaml(v, ind: int) -> list:
    """Block-YAML lines for a parsed dict/list tree, strings double-quoted (the `on:` shapes the lint parses)."""
    pad, out = " " * ind, []
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                out += [f"{pad}{k}:"] + _yaml(x, ind + 2)
            else:
                out.append(f"{pad}{k}:" if x is None else f"{pad}{k}: {'[]' if x == [] else '{}' if x == {} else _scalar(x)}")
        return out
    for x in v:
        if isinstance(x, dict) and x:
            sub = _yaml(x, ind + 2)
            out += [f"{pad}- {sub[0].lstrip()}"] + sub[1:]
        elif isinstance(x, (dict, list)):
            raise ValueError("nested empty/list item")
        else:
            out.append(f"{pad}- {_scalar(x)}")
    return out


def _splice(text: str, new_on: dict | None, conc: str | None) -> str | None:
    """`text` with its top-level `on:` block rewritten from `new_on` and/or a `concurrency:` block inserted before
    `jobs:`; None when the layout is not one this can edit safely (no `on:`/`jobs:` line, a block scalar inside `on:`)."""
    lines = text.split("\n")
    if new_on is not None:
        i = next((k for k, ln in enumerate(lines) if re.match(r"""^["']?on["']?\s*:""", ln)), None)
        if i is None:
            return None
        j = i + 1
        if not lines[i].split(":", 1)[1].split("#")[0].strip():
            while j < len(lines) and (not lines[j].strip() or lines[j][0] in " \t#"):
                j += 1
            while j > i + 1 and (not lines[j - 1].strip() or lines[j - 1][0] == "#"):
                j -= 1  # comments and blanks above the next key belong to it
        region = "\n".join(lines[i:j])
        if re.search(r":\s*[|>]", region) or re.search(r"(?m)[:-]\s+[-+]?[0-9][0-9._-]*\s*(#.*)?$", region):
            return None  # a block scalar would be lost and a bare number would turn into a string
        lines[i:j] = ["on:"] + _yaml(new_on, 2)
    if conc:
        k = next((k for k, ln in enumerate(lines) if re.match(r"^jobs\s*:", ln)), None)
        if k is None:
            return None
        lines[k:k] = ([""] if k and lines[k - 1].strip() else []) + conc.split("\n")
    return "\n".join(lines)


def _concurrency_missing(wf: dict) -> bool:
    c = wf.get("concurrency")
    civ = c.get("cancel-in-progress") if isinstance(c, dict) else None
    return not (civ is True or (isinstance(civ, str) and civ.strip().lower() not in ("", "false")))


def edit_workflow(path: str, text: str, ctx: Ctx) -> tuple[str | None, list]:
    """(patched text or None, one human line per edit). The patched text is re-parsed: jobs and every other
    top-level key must be unchanged and `on:` must equal the intended trigger set, else no edit is offered."""
    try:
        wf = lint.parse_workflow_yaml(text)
    except Exception:
        return None, []
    if "\r" in text or not text.endswith("\n"):
        return None, [f"{path}: not patched (CRLF or no final newline): edit by hand"]
    on = lint._normalize_on(wf.get("on"))
    new, steps = copy.deepcopy(on), []
    req = None if ctx.required is None else os.path.basename(path) in ctx.required
    push = on.get("push")
    pushd = push if isinstance(push, dict) else {}
    branch_push = "push" in on and not _tags_only(push)
    if req is False and ctx.local_gate and lint.TEST_SIGNAL_RE.search(text) and ("pull_request" in on or branch_push):
        for k in ("pull_request", "push"):
            if k in new and (k == "pull_request" or branch_push):
                del new[k]
        new.setdefault("workflow_dispatch", None)
        steps.append("move to `workflow_dispatch`: not a required check and the full gate runs locally before the push")
    else:
        if "pull_request" in on and branch_push:
            if ctx.strict is True:
                del new["push"]
                steps.append("drop `push`: strict protection means the PR run already tested what merges")
            elif "branches" not in pushd and "branches-ignore" not in pushd:
                new["push"] = {**pushd, "branches": [ctx.default_branch]}
                steps.append(f"limit `push` to {ctx.default_branch}: PR-branch pushes were running the workflow twice (push + pull_request)")
        skip = 1 - _share({"paths-ignore": list(ctx.docs)}, ctx) if ctx.files else 0
        for k in ("pull_request", "push"):
            d = new.get(k, False)  # False: the event is absent
            if req is False and 0 < skip <= MAX_SKIP_SHARE and d is not False and (k == "pull_request" or branch_push) \
                    and not ((d or {}).get("paths") or (d or {}).get("paths-ignore")):
                new[k] = {**(d or {}), "paths-ignore": list(ctx.docs)}
                steps.append(f"`paths-ignore` docs on `{k}`: would have skipped {skip:.0%} of the last {DAYS} days' PRs")
    conc = None
    if ("pull_request" in new or "pull_request_target" in new) and _concurrency_missing(wf):
        if "concurrency" in wf:
            steps.append("by hand: `concurrency` exists without cancel-in-progress: add `cancel-in-progress: true` and a per-PR group")
        else:
            conc = CONCURRENCY
            steps.append("add `concurrency` cancel-in-progress: a superseded push stops burning minutes (savings not counted below)")
    if new == on and not conc:
        return None, steps
    out = _splice(text, new if new != on else None, conc)
    try:
        chk = lint.parse_workflow_yaml(out) if out else None
    except Exception:
        chk = None
    keep = lambda w: {k: v for k, v in w.items() if k not in ("on", "concurrency")}  # noqa: E731
    if (
        chk is None or keep(chk) != keep(wf) or lint._normalize_on(chk.get("on")) != new
        or (conc is not None and _concurrency_missing(chk)) or (conc is None and chk.get("concurrency") != wf.get("concurrency"))
    ):
        return None, [f"{path}: not patched (could not edit its triggers safely): edit by hand"]
    return out, steps


def build_patch(texts: dict, ctx: Ctx) -> tuple[dict, dict, str]:
    """({path: patched text}, {path: [step lines]}, unified diff). Never writes a file."""
    patched, steps, diff = dict(texts), {}, []
    for path, text in texts.items():
        new, st = edit_workflow(path, text, ctx)
        if st:
            steps[path] = st
        if new is not None:
            patched[path] = new
            diff += difflib.unified_diff(text.splitlines(True), new.splitlines(True), f"a/{path}", f"b/{path}")
    return patched, steps, "".join(diff)


# ---- inputs: git history, visibility ---------------------------------------------------------------------


def _git(root: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def hist_from_git(root: str, branch: str, days: int = DAYS) -> tuple[list, list]:
    """([changed-file set per merged PR], [tag names]) from the last `days` days of first-parent history of
    origin/<branch> (else <branch>, else HEAD): a merge commit or a squash commit is one PR. ([], []) without git."""
    ref = next((r for r in (f"origin/{branch}", branch, "HEAD") if _git(root, "rev-parse", "--verify", "-q", r)), None)
    prs: list = []
    if ref:
        cur = None
        for ln in (_git(root, "-c", "core.quotepath=off", "log", ref, "--first-parent", "-m", "--name-only", f"--since={days}.days.ago", "--format=@@%H") or "").splitlines():
            if ln.startswith("@@"):
                cur = set()
                prs.append(cur)
            elif ln and cur is not None:
                cur.add(ln)
    tags = []
    for ln in (_git(root, "tag", "--list", "--format=%(refname:short) %(creatordate:unix)") or "").splitlines():
        name, _, ts = ln.rpartition(" ")
        if name and ts.isdigit() and time.time() - int(ts) <= days * 86400:
            tags.append(name)
    return prs, tags


def local_gate(root: str) -> bool:
    """True when the repo already has a pre-push gate (a pre-push hook in .githooks, .husky or the git hooks dir,
    or scripts/dcr-gates.sh): the precondition for moving a non-required workflow out of Actions."""
    hook = (_git(root, "rev-parse", "--git-path", "hooks/pre-push") or "").strip()
    return any(os.path.isfile(os.path.join(root, c)) for c in (".githooks/pre-push", ".husky/pre-push", "scripts/dcr-gates.sh", hook) if c)


def _http_status(url: str) -> int | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=8) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def visibility(root: str, repo: str | None, choice: str) -> tuple[str, str]:
    """("public"|"private"|"unknown", evidence). `auto` = one unauthenticated HEAD to github.com/<owner>/<repo>
    (200 public; 404 private or missing), cached 24h in the git dir; any other answer is "unknown"."""
    if choice != "auto":
        return choice, "--visibility"
    if not repo:
        m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?\s*$", _git(root, "remote", "get-url", "origin") or "")
        repo = f"{m.group(1)}/{m.group(2)}" if m else None
    if not repo:
        return "unknown", "no github.com origin remote"
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return "unknown", f"{repo!r} is not OWNER/REPO"
    common = (_git(root, "rev-parse", "--git-common-dir") or "").strip()
    cache = os.path.join(root, common, "perun-ci-visibility.json") if common else None
    try:
        with open(cache or os.devnull) as fh:
            c = json.load(fh)
        if c.get("repo") == repo and c.get("vis") in ("public", "private") and time.time() - c.get("ts", 0) < 86400:
            return c["vis"], f"{repo} (cached)"
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    code = _http_status(f"https://github.com/{repo}")
    vis = {200: "public", 404: "private"}.get(code, "unknown")
    if vis != "unknown" and cache:
        try:
            with open(cache, "w") as fh:
                json.dump({"repo": repo, "vis": vis, "ts": time.time()}, fh)
        except OSError:
            pass
    return vis, f"{repo}: github.com answered {code} to an unauthenticated HEAD" + (" (private or missing)" if code == 404 else "")


# ---- report ------------------------------------------------------------------------------------------------


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _d(x: float) -> str:
    return f"${x:,.2f}"


def per_event(rows: list, ctx: Ctx, pushes: float) -> tuple[float, float, float, float]:
    """(minutes, list price) of one push to a PR branch, then of one merged PR (its pushes plus the run on the merge);
    schedule and tag runs are not part of a PR."""
    mp = dp = mr = dr = 0.0
    for r in rows:
        m, d = sum(r.per_run.values()), list_price(r.per_run)
        n_push = sum(r.runs.get(k, 0) for k in ("pull_request", "pull_request_target", "push (PR branches)"))
        n_pr = n_push + r.runs.get("push (default branch)", 0)
        mp, dp, mr, dr = mp + m * n_push, dp + d * n_push, mr + m * n_pr, dr + d * n_pr
    k, kp = max(ctx.prs, 1e-9), max(ctx.prs * pushes, 1e-9)
    return mp / kp, dp / kp, mr / k, dr / k


def _line(label: str, rows: list, minutes: dict, ctx: Ctx, pushes: float) -> str:
    extra = f", +{_n(minutes[None])} min on runners this tool cannot price" if minutes.get(None) else ""
    mp, dp, mr, dr = per_event(rows, ctx, pushes)
    return (f"  {label:<38}{_n(sum(minutes.values())):>9} min/mo  list {_d(list_price(minutes)):>9}  billed {_d(billed(minutes, ctx)):>9}{extra}\n"
            f"      one push to a PR branch: {mp:,.1f} min {_d(dp)}; one merged PR: {mr:,.1f} min {_d(dr)} (list price)")


def report(root: str, texts: dict, ctx: Ctx, vis: tuple, notes: list) -> int:
    """Print the BLUF verdict, the context, the before/after estimate, the plan and the patch."""
    print(f"ci_cost_advisor: {root}")
    if not texts:
        print("VERDICT: no workflows under .github/workflows: nothing to price.")
        return 0
    rows, before = estimate(texts, ctx)
    mode = decide(before, ctx)[0]
    patched, steps, patch = build_patch(texts, ctx)
    r1, a1 = estimate(patched, ctx)
    r2, a2 = estimate(patched, ctx, pushes=1)
    shrink = frozenset(os.path.basename(r.path) for r in rows if r.req)
    r3, a3 = estimate(patched, ctx, pushes=1, shrink=shrink) if shrink else (r2, a2)
    unpriced = f" ~{_n(before[None])} min/mo run on labels this tool cannot price (larger runners are always billed, self-hosted are free): check them." if before.get(None) else ""
    mins = f"~{_n(sum(before.values()))} min/mo (list {_d(list_price(before))})"
    if not ctx.private:
        print(f"VERDICT: FREE. Public repo on standard runners: {mins} costs $0. No spend to cut; local-first is optional.{unpriced}")
    elif billed(before, ctx) == 0:
        print(f"VERDICT: INSIDE THE FREE QUOTA. {mins} fits the {ctx.allowance:,} included minutes, which every private repo on the account shares. `ci: auto` would choose {mode}.{unpriced}")
    else:
        print(f"VERDICT: COSTS MONEY. {mins}, billed ~{_d(billed(before, ctx))} -> local-first ~{_d(billed(a3, ctx))}"
              f" (saves ~{_d(billed(before, ctx) - billed(a3, ctx))}/mo). `ci: auto` would choose {mode}.{unpriced}")
    print(f"\nContext\n  visibility: {vis[0]} ({vis[1]})" + (": treated as private, the billable case; pass --visibility public if it is" if vis[0] == "unknown" else ""))
    print(f"  plan: {ctx.allowance:,} included min/mo for private repos (--plan), shared by every private repo on the account" if ctx.private
          else "  plan: public repo, standard runners: free (docs.github.com); larger runners are always billed")
    for n in notes:
        print(f"  {n}")
    print("\nBefore (each job is billed rounded up to a whole minute)")
    for r in rows:
        ev = ", ".join(f"{k} {_n(v)}" for k, v in r.runs.items() if v) or "no automatic trigger"
        pm = sum(r.per_run.values())
        print(f"  {r.path}{' [required]' if r.req else ''}: {ev} runs/mo x {_n(pm)} min/run = {_n(pm * sum(r.runs.values()))} min")
        for note in r.notes:
            print(f"    note: {note}")
    print(_line("TOTAL before", rows, before, ctx, ctx.pushes))
    if not ctx.private:
        return 0
    print("\nAfter (same assumptions; re-priced from the patched workflow text)")
    print(_line("apply the patch", r1, a1, ctx, ctx.pushes))
    print(_line("+ push each PR once (local gate)", r2, a2, ctx, 1))
    if shrink:
        print(_line(f"+ required check(s) shrunk to {ctx.cheap:g} min", r3, a3, ctx, 1))
    plan = ["Run the full gate locally before every push: set DCR_PREPUSH_CMD to it (`install.sh --with-gates` wires .githooks/pre-push, which caches the verdict per commit so an unchanged commit never re-runs) and push each PR once. Policy: `perun_policy.py set ci local-first`."]
    if steps:
        edits = "\n".join(f"       {os.path.basename(p)}: {s}" for p, st in steps.items() for s in st)
        plan.append((f"Review the patch below, then `ci_cost_advisor.py {root} --patch | git apply` (this tool never edits a workflow):\n" if patch else "Edit by hand:\n") + edits)
    if ctx.required is None:
        plan.append("Pass `--required <workflow files that branch protection requires>` (or `none`): until then every workflow is treated as possibly required, so only edits that cannot strand a required check are offered.")
    elif not ctx.local_gate:
        plan.append("Moving non-required gate workflows to `workflow_dispatch` is withheld: no local gate found (.githooks/pre-push, .husky/pre-push, .git/hooks/pre-push or scripts/dcr-gates.sh). Add one first (`install.sh --with-gates`), then re-run.")
    if ctx.required:
        plan.append(f"Shrink the required check(s) {', '.join(sorted(ctx.required))} to one cheap job ({ctx.cheap:g} min) running a fast subset of the gate; the full gate runs locally. Only you know which gates are cheap, so this is not in the patch. A required workflow must never get a path filter or `[skip ci]`: a skipped required check stays Pending and blocks the merge.")
    if ctx.files:
        doc = 1 - _share({"paths-ignore": list(ctx.docs)}, ctx)
        plan.append(f"Doc-only commits ({doc:.0%} of the last {DAYS} days' PRs match {', '.join(ctx.docs)}): `[skip ci]` in the head commit message skips push/pull_request runs, but use it only where no required check applies.")
    for r in rows:
        hot = r.per_run.get("windows", 0) * RATES["windows"] + r.per_run.get("macos", 0) * RATES["macos"]
        if hot and hot / list_price(r.per_run) >= 0.5:
            plan.append(f"{r.path}: Windows/macOS legs are {hot / list_price(r.per_run):.0%} of its list price per run ({_d(hot)} of {_d(list_price(r.per_run))}): keep one Linux leg on PRs and run the rest locally or weekly.")
        if r.runs.get("schedule", 0) > 4.5:
            plan.append(f"{r.path} runs ~{_n(r.runs['schedule'])}/mo on a schedule: move monitoring to a local cron at the same cadence and keep a weekly Actions heartbeat; cutting its cadence loses detection time.")
    print("\nPlan (local-first)")
    for i, item in enumerate(plan, 1):
        print(f"  {i}. {item}")
    if patch:
        print(f"\nPatch (not applied)\n{patch}", end="")
    return 0


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Estimate GitHub Actions minutes and dollars and print a local-first plan with a ready patch. Never edits a workflow.")
    p.add_argument("root", nargs="?", default=".", help="repository root (expects .github/workflows/)")
    p.add_argument("--visibility", choices=("auto", "public", "private"), default="auto")
    p.add_argument("--repo", metavar="OWNER/REPO", help="repo for the visibility probe and the live strict-protection lookup (default: origin)")
    p.add_argument("--plan", choices=sorted(PLANS), default="free", help="GitHub plan for the included minutes (default: free)")
    p.add_argument("--required", metavar="FILE[,FILE...]|none", help="workflow basenames branch protection requires; `none` = no required checks")
    p.add_argument("--strict-protection", action="store_true", help="required checks are strict (up to date before merge)")
    p.add_argument("--default-branch", default="main", metavar="NAME")
    p.add_argument("--prs", type=float, metavar="N", help="merged PRs per month (default: counted from git history)")
    p.add_argument("--pushes-per-pr", type=float, default=3, metavar="N", help="pushes per PR today (default: 3, assumed)")
    p.add_argument("--job-minutes", action="append", default=[], metavar="[FILE[:JOB]=]MIN", help="minutes per job (default 5, assumed); repeatable")
    p.add_argument("--cheap-minutes", type=float, default=1, metavar="N", help="minutes of the cheap required check (default 1)")
    p.add_argument("--doc-glob", action="append", metavar="GLOB", help="doc-only path pattern (default: **.md, docs/**, LICENSE); repeatable")
    p.add_argument("--decide", action="store_true", help="print local-first or cloud (reason on stderr) for policy `ci: auto`")
    p.add_argument("--patch", action="store_true", help="print only the unified diff")
    a = p.parse_args(argv)
    try:
        texts = lint.load_workflows(a.root)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return lint.ERROR
    if not texts and not os.path.isdir(os.path.join(a.root, ".github", "workflows")):
        top = (_git(a.root, "rev-parse", "--show-toplevel") or "").strip()
        if top and os.path.isdir(os.path.join(top, ".github", "workflows")):
            a.root, texts = top, lint.load_workflows(top)
    mins = {"*": 5.0}
    for it in a.job_minutes:
        key, sep, val = it.rpartition("=")
        if not _num(val):
            p.error(f"--job-minutes {it!r}: minutes must be a positive number")
        mins[key if sep else "*"] = float(val)
    vis = ("unknown", "not probed") if a.patch else visibility(a.root, a.repo, a.visibility)  # the diff needs no network
    files, tags = hist_from_git(a.root, a.default_branch)
    jm = ", ".join(f"{'default' if k == '*' else k}={v:g}" for k, v in mins.items())
    notes = [f"merged PRs/mo: {_n(a.prs)} (--prs)" if a.prs is not None else
             f"merged PRs/mo: {_n(len(files))} counted from git first-parent history, last {DAYS} days" if files else
             f"merged PRs/mo: {ASSUMED_PRS} ASSUMED (no git history; pass --prs)",
             f"pushes per PR today: {a.pushes_per_pr:g} (assumed; --pushes-per-pr). Local-first assumes 1.",
             f"job minutes: {jm} (assumed unless you passed measured numbers with --job-minutes)"]
    required = None if a.required is None else frozenset() if a.required.strip() == "none" else frozenset(x.strip() for x in a.required.split(",") if x.strip())
    strict = True if a.strict_protection else (lint._lookup_strict(a.repo, a.default_branch) if a.repo else None)
    ctx = Ctx(private=vis[0] != "public", allowance=PLANS[a.plan], prs=a.prs if a.prs is not None else (len(files) or ASSUMED_PRS),
              pushes=a.pushes_per_pr, files=files, tags=tags, default_branch=a.default_branch, strict=strict, required=required,
              mins=mins, cheap=a.cheap_minutes, docs=tuple(a.doc_glob or DOC_GLOBS), local_gate=local_gate(a.root))
    if a.decide:
        mode, why = decide(estimate(texts, ctx)[1], ctx) if texts else ("cloud", "no workflows")
        print(mode)
        print(why + (f" [visibility {vis[0]}: {vis[1]}]" if ctx.private else ""), file=sys.stderr)
        return 0
    if a.patch:
        patch = build_patch(texts, ctx)[2]
        if not patch:
            print("ci_cost_advisor: nothing to patch", file=sys.stderr)
        print(patch, end="")
        return 0
    return report(a.root, texts, ctx, vis, notes)


if __name__ == "__main__":
    sys.exit(main())
