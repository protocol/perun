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
import hashlib
import json
import os
import subprocess
import sys
import time

THROTTLE_S = 15 * 60
STAMP_TTL_S = 15 * 60  # re-show a standing line after this long: a compaction may have dropped it
PRUNE_S = 7 * 24 * 3600
DEFAULT_MIN = 60
DEFAULT_MODE = "warn"
MODES = ("off", "warn")
WIP = "WIP: {n} open PRs > cap {c}. Drain (review, land) before spawning."
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


def probe(cwd, minutes):
    """(branch, merged_count, green_count, open_non_draft_count). Raises on any git/gh problem; callers fail open."""
    branch = default_branch(cwd)
    _run(["git", "fetch", "-q", "origin", branch], cwd, timeout=20)
    merged = _run(["git", "log", "--first-parent", f"--since={minutes} minutes ago", "--format=%H", "origin/" + branch], cwd)
    prs = json.loads(_run(["gh", "pr", "list", "--state", "open", "--base", branch, "--limit", "100",
                           "--json", "isDraft,statusCheckRollup"], cwd, timeout=30))
    return branch, len(merged.split()), sum(green(p) for p in prs), sum(not p.get("isDraft") for p in prs)


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
    cap = wip_cap()
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path, now = cache_file(cwd), now or time.time()
    try:
        with open(path) as f:
            c = json.load(f)
        if now - c["ts"] < THROTTLE_S and c.get("minutes") == minutes and c.get("cap") == cap:
            return c.get("line")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with open(path, "w") as f:  # stamp first: a failing or hanging remote is not retried on every prompt
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "line": None}, f)
    line = _stall(*probe(cwd, minutes), minutes, cap)
    with open(path, "w") as f:
        json.dump({"ts": now, "minutes": minutes, "cap": cap, "line": line}, f)
    return line


def check(argv):
    minutes = int(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else settings()[1]
    try:
        b, merged, k, n_open = probe(os.getcwd(), minutes)
    except Exception as e:
        print(f"landing unknown: {e}")
        return 2
    line = _stall(b, merged, k, n_open, minutes, wip_cap())
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
