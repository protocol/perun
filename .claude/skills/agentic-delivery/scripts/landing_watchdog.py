#!/usr/bin/env python3
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

Flow alarms (opt-in, policy `merges_per_hour_target` and `train_yield_floor`, integer >= 0, default 0 = off): when something merged in
the window, "Landing slow: R merged/h to <branch> < target T, K green PRs waiting." fires if merges per hour fall below the target while
green PRs wait, and "Train yield low: Y PRs per landed train < floor F. Rerun the failing checks alone before bisecting." fires if the
average PRs per landed train falls below the floor. A train is a run of first-parent commits less than TRAIN_GAP_S apart (a heuristic:
land_train.sh merges back-to-back, a lone merge counts as a train of one). Both are warn-only and share the throttle, cache and CLI.

Ready-PR age (opt-in, policy `ready_age_p50_h` and `ready_age_p90_h`, integer hours >= 0, default 0 = off): the p50 / p90 of the
hours the green PRs waiting have been green (since their last check finished, else since creation; an unparseable time is skipped); "Ready PRs aging: p50 X h (limit T), p90 Y h (limit U), K green PRs waiting." when
either percentile (nearest rank) exceeds its nonzero limit. Warn-only; shares the throttle, cache and CLI.

Train landing yield (always on, no policy key): train_land.sh records each started train in a ledger (train_yield.py); "Train landing
yield: L of S trains landed ..." fires when fewer than half the recent trains landed a PR or one PR re-rode 5+ trains, and says it points
at infra (timebox or load), not the PR. No ledger or zero trains = silent. Warn-only; shares the throttle, cache and CLI.

Throttle: the remote is asked (one `git fetch` of the default branch, one `gh pr list`) at most once per 15 minutes
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
import hashlib
import json
import math
import os
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
LINE = "Landing stalled: 0 merged to {b} in {n} min, {k} green PRs waiting. Fix landing before starting new work."


def _run(args, cwd, timeout=15):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {p.stderr.strip()[:200]}")
    return p.stdout.strip()


def _check_ok(r):
    if r.get("__typename") == "StatusContext":
        return r.get("state") == "SUCCESS"
    return r.get("status") == "COMPLETED" and r.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED")


def green(pr):
    """True when the PR is non-draft with at least one check and every check finished successfully."""
    rolls = pr.get("statusCheckRollup") or []
    return not pr.get("isDraft") and bool(rolls) and all(_check_ok(r) for r in rolls)


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


def probe(cwd, minutes):
    """(branch, merged_count, green_count, open_non_draft_count, green_ages_hours). Raises on any git/gh problem; callers fail open."""
    branch = default_branch(cwd)
    _run(["git", "fetch", "-q", "origin", branch], cwd, timeout=20)
    merged = _run(["git", "log", "--first-parent", f"--since={minutes} minutes ago", "--format=%H", "origin/" + branch], cwd)
    prs = json.loads(_run(["gh", "pr", "list", "--state", "open", "--base", branch, "--limit", "100",
                           "--json", "isDraft,statusCheckRollup,createdAt"], cwd, timeout=30))
    now = time.time()
    ages = [a for a in (_age_h(p, now) for p in prs if green(p)) if a is not None]
    return branch, len(merged.split()), sum(green(p) for p in prs), sum(not p.get("isDraft") for p in prs), ages


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


def _stall(branch, merged, k, n_open, minutes, cap):
    """The stall line and/or the WIP line, newline-joined, or None when neither applies."""
    lines = [LINE.format(b=branch, n=minutes, k=k)] if merged == 0 and k else []
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


def _all(cwd, probed, minutes, cap, ages_lim=None):
    """Stall + WIP + flow lines for one probe result, newline-joined, or None."""
    b, merged, k, n_open, *rest = probed
    def times():
        out = _run(["git", "log", "--first-parent", f"--since={minutes} minutes ago", "--format=%ct", "origin/" + b], cwd)
        return [int(x) for x in out.split()]
    try:
        extra = _flow(b, merged, k, minutes, flow_limits(), times)
    except Exception:  # the flow alarms must never drop the stall and WIP lines
        extra = None
    return "\n".join(x for x in (_stall(b, merged, k, n_open, minutes, cap), extra, _train_yield(cwd), _age(rest[0] if rest else [], ages_lim if ages_lim is not None else age_limits())) if x) or None


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
    cap, alim = wip_cap(), age_limits()
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path, now = cache_file(cwd), now or time.time()
    try:
        with open(path) as f:
            c = json.load(f)
        if now - c["ts"] < THROTTLE_S and c.get("minutes") == minutes and c.get("cap") == cap and c.get("flow", [0, 0]) == list(flow_limits()) and c.get("age", [0, 0]) == list(alim):
            return c.get("line")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with open(path, "w") as f:  # stamp first: a failing or hanging remote is not retried on every prompt
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "flow": list(flow_limits()), "age": list(alim), "line": None}, f)
    line = _all(cwd, probe(cwd, minutes), minutes, cap, alim)
    with open(path, "w") as f:
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "flow": list(flow_limits()), "age": list(alim), "line": line}, f)
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
