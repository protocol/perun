#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=flag a merge pipeline that landed nothing while green PRs wait, review=2027-01-30
"""landing_watchdog.py — UserPromptSubmit + PreToolUse(Agent|Task) hook (+ `check` CLI): flag a merge pipeline that has landed nothing while green PRs wait.

WHY: a merge pipeline landed nothing for 40 minutes to about 4 hours while green PRs waited and the coordinator kept
spawning new work, unnoticed. Output (new lanes, new PRs) kept growing; the one number that says work is reaching the
default branch was never looked at. This hook looks at it for the model, once per prompt, cheaply.

Signal: zero first-parent commits on the default branch in the last N minutes (policy `landing_stall_min`, default
60) AND at least one open, non-draft PR into that branch whose checks all passed (one `gh pr list` call). When both
hold, UserPromptSubmit emits hookSpecificOutput.additionalContext, one line:
"Landing stalled: 0 merged to <branch> in N min, K green PRs waiting. Fix landing before starting new work."
A PR with no checks, a pending or failing check, or a draft is not green. Squash-merge and merge-commit workflows both
land on the first-parent chain; a direct push counts as landing too.

Autonomous runs that spawn lanes without a user prompt never reach UserPromptSubmit, so the same line is also emitted on
PreToolUse for tool_name Agent or Task (hookEventName PreToolUse), main session only: an input with agent_id (a
subagent's own spawn) stays silent. It only warns, never denies, and shares the verdict cache and throttle below.

WIP cap: the same `gh pr list` call also counts open non-draft PRs into the branch (a draft cannot be drained by review or
landing). Ceiling: the call asks for `--base <branch> --limit 100`, so PRs into other branches are not counted and above 100
the count stops at 100. When that count exceeds policy `wip_cap` (integer >= 0; opt-in, default 0 = off), a second line is added:
"WIP: N open PRs > cap M. Drain (review, land) before spawning." It is independent of the stall line, warn-only, and
shares the same throttle, cache and CLI (`check` exits 1 for either line).

WIP exemption: one open, non-draft PR labelled `p0-recurrence` with a `Fixes: #N` trailer (the reopened P0 issue) whose issue gh shows reopened (and not closed again) less than 24 h ago is not
counted, so a recurrence fix is never queued behind the cap; at most one PR is exempt (so one per issue), the 24 h runs from the reopen, and any gh failure or an unverified issue exempts nothing.

Installer alarm (opt-in, policy `installer_unapplied_h`, hours >= 0, default 0 = off): "Installer unapplied: <name> merged H h ago ..." for a
host installer recorded by host_installer.py and not marked applied; warn-only, the owner runs the printed `! ` command.

Flow alarms (opt-in, policy `merges_per_hour_target` and `train_yield_floor`, integer >= 0, default 0 = off): when something merged in
the window, "Landing slow: R merged/h to <branch> < target T, K green PRs waiting." fires if merges per hour fall below the target while
green PRs wait, and "Train yield low: Y PRs per landed train < floor F. Rerun the failing checks alone before bisecting." fires if the
average PRs per landed train falls below the floor. A train is a run of first-parent commits less than TRAIN_GAP_S apart (a heuristic:
land_train.sh merges back-to-back, a lone merge counts as a train of one). Both are warn-only and share the throttle, cache and CLI.

Ready-PR age (opt-in, policy `ready_age_p50_h` and `ready_age_p90_h`, integer hours >= 0, default 0 = off): the p50 / p90 of the
hours the green PRs waiting have been green (since their last check finished, else since creation; an unparseable time is skipped); "Ready PRs aging: p50 X h (limit T), p90 Y h (limit U), K green PRs waiting." when
either percentile (nearest rank) exceeds its nonzero limit. Warn-only; shares the throttle, cache and CLI.

Lane stall (opt-in, policy `lane_idle_h` hours >= 0 plus `lane_globs` {lane: [fnmatch globs]}, default off): a PR's lane is the first
lane whose glob matches a changed file; "Lane stalled: <lane> has K ready PRs, last merge H h ago (limit L h)." when a lane has green PRs and its
last merge (last 100 merged PRs) is older than the limit, so one busy lane cannot hide an idle one. Two extra `gh pr list` calls; warn-only.

Train landing yield (always on, no policy key): train_land.sh records each started train in a ledger (train_yield.py); "Train landing
yield: L of S trains landed ..." fires when fewer than half the recent trains landed a PR or one PR re-rode 5+ trains, and says it points
at infra (timebox or load), not the PR. No ledger or zero trains = silent. Warn-only; shares the throttle, cache and CLI.

Train liveness and decision effect (always on, no policy key): the train's progress marker is the `perun/train-stage` status on each open PR (merge_train.py `stage`).
`gh pr list` shows that status but not its description, so while it shows one, one `gh api graphql` call reads the markers of the open PRs into the branch: stage = first
word of the description, time = its `at=<epoch>` unless that is more than 5 min ahead of the clock, else the status `createdAt`, eta = `eta<=Ns` (at most 24 h); a marker with
no stage word or no time is skipped, and no marker means no extra call. green() ignores that marker (it is not a check), so a PR left in a dead run or skipped once still
counts as waiting. The last train activity is the newest of every marker, whatever its run (a run id is minted per `merge_train.py stage` call, not per train, so it groups
nothing), and the newest first-parent commit on the branch (one local `git log -1`; a failure, or a time more than 5 min ahead of the clock, reads as none); an outcome beats a marker on a tie.
"Train run stuck: run R posted <stage> on K PRs X min ago (expected <= Y min), no outcome since. ..." fires only when that last activity is itself a queued, gating or
landing marker older than 1.5 x its eta (default 60 min), K counting the PRs that carry that run and stage. Any newer marker or any landing supersedes a live marker, so a
dead run's marker on a PR no later train touched stays quiet. When the stall line fires and the last activity is not a live marker but older than max(1.5 x expected, the check
window), the stall line gains " No train run in X min: start the train or check its runner."; a stuck run gets the stuck line and no clause, and fresh outcome markers
(trains that run but fail) get none. No markers at all = silent, so a repo without trains never alarms. `landing_watchdog.py expect 'train_size>=N' [--hours H]` (quote the
first argument, an unquoted `>=` is a shell redirect; N and H integers >= 1, H default 24; anything else exits 2) appends a decision to <git-common-dir>/perun-decisions.jsonl
(env PERUN_DECISIONS overrides), and "Decision not in effect: train_size>=N set X h ago; the K trains since carried a median of M PRs. ..." fires while the newest
unexpired decision is unmet by the median PR count of the >= 2 ledger trains started since it (train_yield.py stamps each train with its start time, else its end time; a
record with neither never counts), so a decision the runner never applied does not read as a slow train. Residuals: any landing supersedes a live marker, so a hand merge,
or a landing stage that hangs after its first merge, silences the stuck line (the stall line still fires once nothing merges for the window); markers come only from the
current heads of open PRs, so a re-push or a close mid-run drops one, and a failed second call reads as no markers; the `createdAt` fallback is the post time, not the run
start; train_size reads the local ledger only, so another host's trains are not seen. Warn-only; shares the throttle, cache and CLI; fails open.

Throttle: the remote is asked (one `git fetch` of the default branch, one `gh pr list`, and one `gh api graphql` while an open PR carries a train marker) at most once per 15 minutes
per repo; the verdict is cached between probes, so a standing stall costs no network call; a prompt's line is emitted once per
session and again when it changes or after 15 minutes; a spawn always gets it, and a payload without session_id is not deduped. The cache is one small JSON file per repo under $PERUN_LANDING_DIR, else <cache>/perun/landing-watchdog
(<cache> = $XDG_CACHE_HOME or ~/.cache, beside the other Perun hook state). The stamp is written before the calls, so a
hanging or failing remote is not retried on every prompt.

CLI: `landing_watchdog.py check [--minutes N]` ignores the throttle and the mode, prints the stall line or
`landing ok: ...` or `landing unknown: <why>`; exit 0 ok, 1 stalled, 2 unknown.
Mode: env PERUN_LANDING_WATCHDOG=off|warn, else policy `landing_watchdog` (`perun_policy.py set landing_watchdog off`),
default `warn`. Only `warn` exists: the hook advises and never blocks a prompt.
Fail open: no git repo, no origin, no gh, no auth, a failed fetch (a stale remote ref would fake a stall), bad stdin,
an unreadable policy or cache and any other error print nothing and exit 0. gh_rest.py's macOS-sandbox TLS retry
covers `gh api` only, not `gh pr list`, so under that sandbox this hook stays silent rather than guess.
Side effects: `git fetch origin <default branch>` (updates that remote-tracking ref only) and the cache file.
"""
import calendar
import fnmatch
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time

THROTTLE_S = 15 * 60
STAMP_TTL_S = 15 * 60  # re-show a standing line after this long: a compaction may have dropped it
PRUNE_S = 7 * 24 * 3600
DEFAULT_MIN = 60
TRAIN_GAP_S = 300  # ponytail: a time gap stands in for a train marker; a recorded train id would be exact
DEFAULT_MODE = "warn"
MODES = ("off", "warn")
WIP = "WIP: {n} open PRs > cap {c}. Drain (review, land) before spawning."
SLOW = "Landing slow: {r:.1f} merged/h to {b} < target {t}, {k} green PRs waiting."
YIELD = "Train yield low: {y:.1f} PRs per landed train < floor {f}. Rerun the failing checks alone before bisecting."
AGE = "Ready PRs aging: p50 {a:.1f} h (limit {t}), p90 {b:.1f} h (limit {u}), {k} green PRs waiting. Land or review them before new work."
LANE = "Lane stalled: {l} has {k} ready PRs, last merge {h} (limit {t} h). Land that lane before new work."
LKG = "Last-known-good is {h:.1f} h old (limit {t} h): no full ci-tests pass recorded since. Check the merge gate."
LINE = "Landing stalled: 0 merged to {b} in {n} min, {k} green PRs waiting. Fix landing before starting new work."
TRAIN_STAGE = "perun/train-stage"  # the train's progress marker; same string as merge_train's STAGE_CONTEXT (merge_train imports this module, so not imported here)
LIVE = ("queued", "gating", "landing")  # stages with no outcome yet
ETA_S = 3600  # expected run time when a marker carries no eta
STUCK = "Train run stuck: run {r} posted {s} on {k} PRs {x:.0f} min ago (expected <= {y:.0f} min), no outcome since. Check the train runner, not the PRs."
IDLE = " No train run in {x:.0f} min: start the train or check its runner."  # appended to the stall line
DECISION = "Decision not in effect: train_size>={n} set {h:.1f} h ago; the {k} trains since carried a median of {m:g} PRs. Check that the runner reads it."
STAGES_Q = ("query($owner:String!,$repo:String!,$base:String!){repository(owner:$owner,name:$repo){pullRequests(states:OPEN,baseRefName:$base,first:100,"
            "orderBy:{field:CREATED_AT,direction:DESC}){nodes{commits(last:1){nodes{commit{statusCheckRollup{contexts(first:100){nodes{__typename "
            "...on StatusContext{context,description,createdAt}}}}}}}}}}}")
EXPECT_USAGE = "usage: landing_watchdog.py expect 'train_size>=N' [--hours H]  (quote the first argument; N and H integers >= 1, H default 24)"


def _run(args, cwd, timeout=15):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {p.stderr.strip()[:200]}")
    return p.stdout.strip()


def _check_ok(r):
    if r.get("__typename") == "StatusContext":
        return r.get("state") == "SUCCESS"
    return r.get("status") == "COMPLETED" and r.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED")


def blocker(pr, allow_forks=False):
    """The one merge-queue eligibility rule on a PR's current facts: '' when it may join a train, else why not.

    Shared by merge_train (which adds hold, parked and check-run rules) and green(), so a PR the train would skip
    is never counted as waiting. Fails closed: isDraft or isCrossRepository that is not exactly False counts as
    draft / fork, and a missing `mergeable` is not MERGEABLE.
    """
    if pr.get("isDraft") is not False:
        return "draft"
    if pr.get("isCrossRepository") is not False and not allow_forks:
        return "fork (verify would run its code here; --allow-forks)"
    if pr.get("mergeable") != "MERGEABLE":
        return f"mergeable={str(pr.get('mergeable'))[:80]}"
    return ""


def _stage(r):
    """True for the train's own progress marker (a StatusContext named TRAIN_STAGE), which is not a check."""
    return r.get("__typename") == "StatusContext" and r.get("context") == TRAIN_STAGE


def green(pr, allow_forks=False):
    """True when the PR is queue-eligible (see blocker) with at least one check, all finished successfully.

    mergeable=UNKNOWN is GitHub still computing: counted as eligible here so stall signals do not flicker, while the
    train itself still blocks it. The train's progress marker is ignored (pending while a run is live, failure after a
    skip), as merge_train judges check runs only; any other pending status still blocks.
    """
    rolls = [r for r in pr.get("statusCheckRollup") or [] if not _stage(r)]
    return blocker(pr, allow_forks) in ("", "mergeable=UNKNOWN") and bool(rolls) and all(_check_ok(r) for r in rolls)


def default_branch(cwd):
    """origin's default branch: origin/HEAD, else main, else master. Raises when none exists."""
    try:
        return _run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd).split("/", 1)[1]
    except RuntimeError:
        pass
    for b in ("main", "master"):
        try:
            _run(["git", "rev-parse", "--verify", "-q", "origin/" + b], cwd)
            return b
        except RuntimeError:
            pass
    raise RuntimeError("no default branch on origin")


def _ts(iso):
    return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))


def _age_h(p, now):
    """Hours a green PR has been waiting: since its last check finished (when green), else since creation; None if unparseable."""
    try:
        done = [_ts(r["completedAt"]) for r in p.get("statusCheckRollup") or [] if r.get("completedAt", "").startswith("20")]
        return (now - (max(done) if done else _ts(p["createdAt"]))) / 3600
    except (KeyError, ValueError, TypeError):
        return None


def age_limits():
    """(ready_age_p50_h, ready_age_p90_h) from policy; 0 = off. An unreadable policy reads as off."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        pol = perun_policy.load()
        return pol.get("ready_age_p50_h") or 0, pol.get("ready_age_p90_h") or 0
    except Exception as e:  # fail open, but say so: a silent (0, 0) hides a broken policy
        sys.stderr.write(f"landing_watchdog: age policy unreadable, ready-PR age alarm off: {e}\n")
        return 0, 0


def pct(xs, q):
    """Nearest-rank percentile q (0-100) of a non-empty list."""
    s = sorted(xs)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


def _age(ages, limits):
    """The ready-PR age line, or None. `ages` is hours each green PR has waited."""
    t50, t90 = limits
    if not ages or not (t50 or t90):
        return None
    p50, p90 = pct(ages, 50), pct(ages, 90)
    if (t50 and p50 > t50) or (t90 and p90 > t90):
        return AGE.format(a=p50, t=t50, b=p90, u=t90, k=len(ages))
    return None


P0_LABEL, P0_TTL_H = "p0-recurrence", 24


def p0_issue(pr):
    """Issue number from a `Fixes: #N` trailer (digits only) on a non-draft PR labelled `p0-recurrence`, else None."""
    names = {l.get("name") for l in pr.get("labels") or [] if isinstance(l, dict)}
    for x in (pr.get("body") or "").splitlines():
        x = x.strip()
        if x.lower().startswith("fixes: #") and x[8:].isdigit() and P0_LABEL in names and not pr.get("isDraft"):
            return int(x[8:])
    return None


def reopened_at(cwd, n):
    """Epoch of issue n's latest `reopened` event when it is still open after it (no later `closed`), else None. Raises when gh fails (caller fails closed)."""
    ev = json.loads(_run(["gh", "api", f"repos/{{owner}}/{{repo}}/issues/{n}/events?per_page=100"], cwd, timeout=30))
    last = [e for e in ev if e.get("event") in ("reopened", "closed")]
    return _ts(last[-1]["created_at"]) if last and last[-1]["event"] == "reopened" else None


def p0_exempt(prs, cwd, now):
    """1 when one PR fixes an issue verified reopened less than P0_TTL_H ago, else 0. At most one exemption in total (so one per issue); any gh problem exempts nothing."""
    for p in prs:
        n = p0_issue(p)
        try:
            t = reopened_at(cwd, n) if n else None
        except Exception:
            t = None
        if t and now - t < P0_TTL_H * 3600:
            return 1
    return 0


def _stages(prs, branch, cwd):
    """The train's progress markers on the open PRs into `branch` (their current heads), as statuses with a `description` and `createdAt`; [] when there are none.

    `gh pr list --json statusCheckRollup` exports a status's context, state and start time but not its description (checked on gh 2.99), and the stage, run id and
    time live there. So when its output shows a marker, one `gh api graphql` call reads them; no marker, no extra call. Fails open: any gh or shape problem gives []."""
    if not any(_stage(s) for p in prs for s in p.get("statusCheckRollup") or []):
        return []
    try:
        out = json.loads(_run(["gh", "api", "graphql", "-f", "query=" + STAGES_Q, "-f", "base=" + branch, "-F", "owner={owner}", "-F", "repo={repo}"], cwd, timeout=30))
        return [s for p in out["data"]["repository"]["pullRequests"]["nodes"] for c in p["commits"]["nodes"]
                for s in (c["commit"]["statusCheckRollup"] or {}).get("contexts", {}).get("nodes", []) if _stage(s)]
    except Exception:  # no marker is read, no line is added
        return []


def _marks(stages, now=None):
    """[(run, stage, at, eta_s)] for the train progress markers in `stages` (see _stages): stage = first word of the status description, at = its `at=<epoch>` unless that
    is more than 300 s ahead of the clock, else the status createdAt, eta_s = `eta<=Ns` capped at 86400 else 0, run = `run=<id>` else "?". A marker with no stage word or no
    time is skipped, never guessed. The patterns are bounded, so a hand-made status cannot overflow a number or grow a line, and a made-up eta or future time cannot
    keep a dead run from ever reading as stuck."""
    now, out = now or time.time(), []
    for r in stages:
        d = str(r.get("description") or "")
        at, eta, run = (re.search(x, d) for x in (r"\bat=(\d{1,10})\b", r"\beta<=(\d{1,9})s\b", r"\brun=([\w.-]{1,16})"))
        try:
            t = int(at[1]) if at and int(at[1]) <= now + 300 else _ts(r["createdAt"])
        except (KeyError, ValueError, TypeError):
            continue
        if d.split():
            out.append((run[1] if run else "?", d.split()[0], t, min(int(eta[1]), 86400) if eta else 0))
    return out


def probe(cwd, minutes, allow_forks=False):
    """(branch, merged_count, green_count, open_non_draft_count, green_ages_hours, train_markers, landed_at). `landed_at` is the epoch second of the newest first-parent
    commit on origin/<branch>, None when that local `git log` fails. Raises on any other git/gh problem; callers fail open."""
    branch = default_branch(cwd)
    _run(["git", "fetch", "-q", "origin", branch], cwd, timeout=20)
    merged = _run(["git", "log", "--first-parent", f"--since={minutes} minutes ago", "--format=%H", "origin/" + branch], cwd)
    prs = json.loads(_run(["gh", "pr", "list", "--state", "open", "--base", branch, "--limit", "100",
                           "--json", "isDraft,mergeable,isCrossRepository,statusCheckRollup,createdAt,body,labels"], cwd, timeout=30))
    now = time.time()
    ages = [a for a in (_age_h(p, now) for p in prs if green(p, allow_forks)) if a is not None]
    try:
        landed = int(_run(["git", "log", "-1", "--first-parent", "--format=%ct", "origin/" + branch], cwd))
    except Exception:  # fail open: no landing time, the markers alone judge
        landed = None
    return branch, len(merged.split()), sum(green(p, allow_forks) for p in prs), sum(not p.get("isDraft") for p in prs) - p0_exempt(prs, cwd, now), ages, _marks(_stages(prs, branch, cwd), now), landed


def settings():
    """(mode, minutes): env PERUN_LANDING_WATCHDOG, else policy, else defaults. An unreadable policy reads as defaults."""
    mode, minutes = None, DEFAULT_MIN
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        pol = perun_policy.load()
        mode, minutes = pol.get("landing_watchdog"), pol.get("landing_stall_min") or DEFAULT_MIN
    except Exception:  # fail open
        pass
    env = (os.environ.get("PERUN_LANDING_WATCHDOG") or "").strip().lower()
    return (env if env in MODES else mode if mode in MODES else DEFAULT_MODE), minutes


def wip_cap():
    """Policy `wip_cap` (0 = off, the default). An unreadable policy reads as off."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        return perun_policy.load().get("wip_cap") or 0
    except Exception:  # fail open
        return 0


def flow_limits():
    """(merges_per_hour_target, train_yield_floor) from policy; 0 = off. An unreadable policy reads as off."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        pol = perun_policy.load()
        return pol.get("merges_per_hour_target") or 0, pol.get("train_yield_floor") or 0
    except Exception:  # fail open
        return 0, 0


def lane_cfg():
    """(lane_idle_h, lane_globs) from policy; (0, {}) = off. An unreadable policy reads as off."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        pol = perun_policy.load()
        return pol.get("lane_idle_h") or 0, pol.get("lane_globs") or {}
    except Exception:  # fail open
        return 0, {}


def _lane(pr, globs):
    """Every lane in `globs` ({lane: [fnmatch globs]}) matching any changed file of the PR (a cross-lane PR counts for each)."""
    paths = [f.get("path", "") for f in pr.get("files") or []]
    return [l for l, gs in globs.items() if any(fnmatch.fnmatch(x, g) for x in paths for g in gs)]


def _lanes(cwd, branch, cfg, now=None, allow_forks=False):
    """Per-lane stall lines, newline-joined, or None: a lane with ready (green) PRs whose last merge is older than lane_idle_h.
    A total-merges alarm hides this when one busy lane keeps the total up. Looks at the last 100 merged PRs only."""
    limit, globs = cfg
    if not limit or not globs:
        return None
    now = now or time.time()
    gh = lambda st, fields, n: json.loads(_run(["gh", "pr", "list", "--state", st, "--base", branch, "--limit", str(n), "--json", fields], cwd, timeout=60))
    last, ready = {}, {}
    for pr in gh("merged", "mergedAt,files", 100):
        for l in _lane(pr, globs) if pr.get("mergedAt") else []:
            last[l] = max(last.get(l, 0), _ts(pr["mergedAt"]))
    for pr in gh("open", "isDraft,mergeable,isCrossRepository,statusCheckRollup,files", 1000):  # high cap: a truncated list would hide a stalled lane's ready PRs
        for l in _lane(pr, globs) if green(pr, allow_forks) else []:
            ready[l] = ready.get(l, 0) + 1
    out = []
    for l, k in ready.items():
        age = (now - last[l]) / 3600 if l in last else None
        if age is None or age > limit:  # age == limit is not yet stalled
            out.append(LANE.format(l=l, k=k, h="none in the last 100 merged" if age is None else f"{age:.1f} h ago", t=limit))
    return "\n".join(out) or None


def trains(times):
    """Number of trains in a list of commit unix times: runs with gaps under TRAIN_GAP_S."""
    t = sorted(times)
    return len(t) and 1 + sum(b - a >= TRAIN_GAP_S for a, b in zip(t, t[1:]))


def _flow(branch, merged, k, minutes, limits, times):
    """Rate and yield lines, newline-joined, or None. `times` is a callable (git is asked only when a floor is set)."""
    target, floor = limits
    lines = []
    if merged and target and k and merged * 60 / minutes < target:
        lines.append(SLOW.format(r=merged * 60 / minutes, b=branch, t=target, k=k))
    y = merged / max(1, trains(times())) if merged and floor else floor
    if y < floor:
        lines.append(YIELD.format(y=y, f=floor))
    return "\n".join(lines) or None


def cache_file(cwd):
    base = os.environ.get("PERUN_LANDING_DIR")
    if not base:
        cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        if not os.path.isabs(cache):
            raise OSError("no absolute cache dir: set HOME, XDG_CACHE_HOME or PERUN_LANDING_DIR")
        base = os.path.join(cache, "perun", "landing-watchdog")
    os.makedirs(base, exist_ok=True)
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd)
    return os.path.join(base, hashlib.sha1(top.encode()).hexdigest()[:16] + ".json")


def _stall(branch, merged, k, n_open, minutes, cap, idle=None):
    """The stall line and/or the WIP line, newline-joined, or None when neither applies. `idle` (minutes since the last train activity, from _runs) is appended to the stall line."""
    lines = [LINE.format(b=branch, n=minutes, k=k) + (IDLE.format(x=idle) if idle else "")] if merged == 0 and k else []
    if cap and n_open > cap:
        lines.append(WIP.format(n=n_open, c=cap))
    return "\n".join(lines) or None


def _train_yield(cwd):
    """Train landing-yield / re-ride alarm line (train_yield.py), or None. Fails open: a ledger problem never drops the other lines."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import train_yield
        return train_yield.alarm(train_yield.ledger_path(cwd))
    except Exception:
        return None


def _runs(marks, landed, minutes, now=None):
    """(stuck line or None, idle minutes or None). `marks` is [(run, stage, at, eta_s)] (see _marks), `landed` the epoch second of the newest first-parent commit on the branch
    or None; no markers = (None, None), so a repo without trains never alarms.

    The last activity is the newest of every marker and, when known and not more than 300 s ahead of the clock, a landing counted as an outcome at `landed`; on a tie in time an
    outcome is the newer. Run ids do not
    group markers: a run id is minted per `merge_train.py stage` call, not per train, so one train posts several.
    Stuck: the last activity is itself a queued, gating or landing marker older than 1.5 x its expected time (eta, else ETA_S); the line names its run and stage and counts the
    PRs carrying both. Any newer marker or any landing supersedes a live marker, so a dead run's marker on a PR no later train touched stays quiet. Residual: a hand merge, or a
    landing stage that hangs after its first merge, therefore silences it (the stall line still fires once nothing merges for the window).
    Idle: the last activity is not a live marker and is older than max(1.5 x expected, the check window); its age in minutes, which _stall appends to the stall line. A repo
    that merges has no stall line, so a skipped marker from days ago never alarms there."""
    if not marks:
        return None, None
    now = now or time.time()
    last = max(marks + ([("", "landed", landed, 0)] if landed and landed <= now + 300 else []), key=lambda m: (m[2], m[1] not in LIVE))
    age, eta = now - last[2], last[3] or ETA_S
    if last[1] in LIVE:
        return (STUCK.format(r=last[0], s=last[1], k=sum(m[:2] == last[:2] for m in marks), x=age / 60, y=eta / 60) if age > 1.5 * eta else None), None
    return None, age / 60 if age > max(1.5 * eta, minutes * 60) else None


def decisions_path(cwd=None):
    """Decision file: env PERUN_DECISIONS, else perun-decisions.jsonl under the git common dir of cwd (as train_yield.ledger_path). Raises RuntimeError outside a repo."""
    return os.environ.get("PERUN_DECISIONS") or os.path.join(_run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd), "perun-decisions.jsonl")


def expect(argv, now=None):
    """Record `'train_size>=N' [--hours H]` (H default 24) in the decision file and return a one-line receipt (main prints it); quote the first argument, an unquoted `>=` is a shell redirect.

    Only the metric train_size with `>=`, N >= 1 and a whole-number H >= 1 are accepted; anything else raises ValueError(EXPECT_USAGE) and writes nothing.
    Side effect: appends {"metric","op","value","at","until"} (epoch seconds) to decisions_path(). Raises OSError or RuntimeError when it cannot write."""
    m = re.fullmatch(r"train_size>=([0-9]{1,9})", argv[0]) if argv else None
    hours = "24" if len(argv) == 1 else argv[2] if len(argv) == 3 and argv[1] == "--hours" else ""
    if not (m and re.fullmatch(r"[0-9]{1,9}", hours) and int(m[1]) >= 1 and int(hours) >= 1):
        raise ValueError(EXPECT_USAGE)
    at = int(now or time.time())
    with open(decisions_path(os.getcwd()), "a") as f:
        f.write(json.dumps({"metric": "train_size", "op": ">=", "value": int(m[1]), "at": at, "until": at + int(hours) * 3600}) + "\n")
    return f"decision recorded: train_size>={int(m[1])} for {int(hours)} h"


def _decision(cwd, now=None):
    """Decision-effect line, or None: the newest unexpired `train_size>=N` decision (see expect) while the >= 2 ledger trains started since it (train_yield.sizes_since) carried a median
    of fewer than N PRs, i.e. the decision is not in effect. Met, expired, fewer than 2 trains, a record without a time, a missing or unreadable file = silent.
    Fails open: never drops the other lines."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import train_yield
        now, ds = now or time.time(), []
        with open(decisions_path(cwd)) as f:
            for ln in f.read().splitlines():
                try:
                    d = json.loads(ln)
                    if d["metric"] == "train_size" and d["op"] == ">=" and d["value"] >= 1 and d["at"] <= now < d["until"]:
                        ds.append(d)
                except (ValueError, KeyError, TypeError):
                    continue
        d = max(ds, key=lambda x: x["at"], default=None)
        sizes = train_yield.sizes_since(train_yield.ledger_path(cwd), d["at"]) if d else []
        if len(sizes) > 1 and (m := statistics.median(sizes)) < d["value"]:
            return DECISION.format(n=d["value"], h=(now - d["at"]) / 3600, k=len(sizes), m=m)
    except Exception:  # no file, no repo, no ledger: silent
        pass
    return None


def _lkg(cwd):
    """Stale last-known-good alarm line (lkg.py), or None. Off unless policy `lkg_stale_h` > 0. Fails open: never drops the other lines."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lkg
        import perun_policy
        lim = perun_policy.load().get("lkg_stale_h") or 0
        a = lkg.age_h(cwd) if lim else None
        return LKG.format(h=a, t=lim) if a is not None and a > lim else None
    except Exception:
        return None


def _red(cwd):
    """Red-main alarm line (red_main.py), or None. Off unless policy `red_uncovered_max` or `red_oldest_h` is set. With a threshold set, an unreadable or missing
    .claude/red-main.json (red_main rc 2) and a red_main that cannot load are alarms too, never silent green; only the render path fails open."""
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        import perun_policy
        pol = perun_policy.load()
        if not (pol.get("red_uncovered_max") or pol.get("red_oldest_h")):
            return None
        import io
        import contextlib
        import red_main
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = red_main.main(["--file", os.path.join(cwd, ".claude", "red-main.json")])
    except Exception as e:  # policy on but the check itself cannot run: say so
        return f"Red-main check could not run ({type(e).__name__}); green is unknown."
    if rc == 1:
        return "Red main needs an owner: " + " | ".join(buf.getvalue().split("\n")[:3])
    return f"Red-main check failed (rc {rc}): {err.getvalue().strip()[:160]}; green is unknown." if rc else None


def _installer(cwd):
    """Merged-but-unapplied host installer alarm (host_installer.py), or None. Off unless policy `installer_unapplied_h` > 0. Fails open."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import host_installer
        import perun_policy
        return host_installer.alarm(perun_policy.load().get("installer_unapplied_h") or 0)
    except Exception:
        return None


def _all(cwd, probed, minutes, cap, ages_lim=None, lanes=None):
    """Stall + WIP + flow lines for one probe result, newline-joined, or None."""
    b, merged, k, n_open, *rest = probed
    def times():
        out = _run(["git", "log", "--first-parent", f"--since={minutes} minutes ago", "--format=%ct", "origin/" + b], cwd)
        return [int(x) for x in out.split()]
    try:
        extra = _flow(b, merged, k, minutes, flow_limits(), times)
    except Exception:  # the flow alarms must never drop the stall and WIP lines
        extra = None
    try:
        lane = _lanes(cwd, b, lanes if lanes is not None else lane_cfg())
    except Exception:  # fail open: lane lines never drop the others
        lane = None
    stuck, idle = _runs(rest[1] if len(rest) > 1 else [], rest[2] if len(rest) > 2 else None, minutes)
    return "\n".join(x for x in (_stall(b, merged, k, n_open, minutes, cap, idle), extra, lane, _train_yield(cwd), stuck, _decision(cwd), _lkg(cwd), _red(cwd), _installer(cwd), _age(rest[0] if rest else [], ages_lim if ages_lim is not None else age_limits())) if x) or None


def _event(data):
    """The hook event to answer, or None: a user prompt, or a main-session Agent/Task spawn (a subagent's has agent_id)."""
    ev = data.get("hook_event_name", "UserPromptSubmit")
    if ev == "UserPromptSubmit" or (ev == "PreToolUse" and data.get("tool_name") in ("Agent", "Task") and not data.get("agent_id")):
        return ev
    return None


def hook(data, now=None):
    """The additionalContext line for this event, or None. Network at most once per THROTTLE_S per repo.
    A UserPromptSubmit with a session_id gets the line once and again only when it changes or after STAMP_TTL_S (so a
    compaction that dropped it re-shows it); stamp `<cache>.<session>`, context_nudge's pattern; a cleared line resets
    it so a recurrence shows. A spawn (PreToolUse) always gets the line: its "drain before spawning" is for that spawn."""
    line = _line(data, now)
    sid = str(data.get("session_id") or "").replace("/", "_")
    if not sid or _event(data) != "UserPromptSubmit":
        return line
    try:
        stamp = cache_file(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) + "." + sid
        try:
            with open(stamp) as f:
                seen = f.read()
            fresh = (now or time.time()) - os.path.getmtime(stamp) < STAMP_TTL_S
        except (OSError, ValueError):
            seen, fresh = "", False
        if (line or "") == seen and fresh:
            return None
        with open(stamp, "w") as f:
            f.write(line or "")
        d = os.path.dirname(stamp)
        for n in os.listdir(d):  # prune stamps of long-gone sessions
            q = os.path.join(d, n)
            if ".json." in n and time.time() - os.path.getmtime(q) > PRUNE_S:
                os.remove(q)
    except (OSError, ValueError):  # fail open (ValueError: NUL in session_id): a stamp problem must not drop the warning
        pass
    return line


def _line(data, now=None):
    mode, minutes = settings()
    if mode == "off" or not _event(data):
        return None
    cap, alim, lcfg = wip_cap(), age_limits(), list(lane_cfg())
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path, now = cache_file(cwd), now or time.time()
    try:
        with open(path) as f:
            c = json.load(f)
        if now - c["ts"] < THROTTLE_S and c.get("minutes") == minutes and c.get("cap") == cap and c.get("flow", [0, 0]) == list(flow_limits()) and c.get("age", [0, 0]) == list(alim) and c.get("lane", [0, {}]) == lcfg:
            return c.get("line")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with open(path, "w") as f:  # stamp first: a failing or hanging remote is not retried on every prompt
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "flow": list(flow_limits()), "age": list(alim), "lane": lcfg, "line": None}, f)
    line = _all(cwd, probe(cwd, minutes), minutes, cap, alim, tuple(lcfg))
    with open(path, "w") as f:
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "flow": list(flow_limits()), "age": list(alim), "lane": lcfg, "line": line}, f)
    return line


def check(argv):
    minutes = int(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else settings()[1]
    try:
        probed = probe(os.getcwd(), minutes)
        b, merged, k = probed[:3]
        line = _all(os.getcwd(), probed, minutes, wip_cap())
    except Exception as e:
        print(f"landing unknown: {e}")
        return 2
    print(line or f"landing ok: {merged} merged to {b} in {minutes} min, {k} green PRs waiting")
    return 1 if line else 0


def main():
    if sys.argv[1:2] == ["check"]:
        return check(sys.argv[2:])
    if sys.argv[1:2] == ["expect"]:
        try:
            print(expect(sys.argv[2:]))
            return 0
        except (ValueError, OSError, RuntimeError) as e:
            sys.stderr.write(f"landing_watchdog: {e}\n")
            return 2
    try:
        data = json.load(sys.stdin)
        line = hook(data)
        if line:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": _event(data), "additionalContext": line}}))
    except Exception:  # fail open: a broken watchdog must never block a prompt
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
