#!/usr/bin/env python3
"""handback.py — one command for a lane's last mile; composes the existing scripts, adds no gate logic of its own.

  handback.py --sha SHA --base REF --branch BRANCH --gate-cmd CMD [--gate-cmd CMD ...]
              [--cite PATH ...] [--artifact-root DIR] [--fragment-dir DIR] [--worktree DIR]
              [--repo OWNER/NAME [--tracker-issue N --agent NAME --to NAME --body-file FILE [--send]]] [--timeout S]

Gates run in --worktree and every git step runs there too (default: the current directory).
Runs in order and stops at the first red step, printing `handback RED: <step>` and exiting 1:
  gate      each --gate-cmd through `gate_cache.py run --stage handback` (a tree that already passed is not rerun;
            plain `bash -c` when deep-code-review is not installed).
  guard     `lane_guard.py handback` (orphan, unrelated history, unmoved head, branch tip, cites).
  ff        BASE is an ancestor of SHA, so BASE can fast-forward to it; otherwise rebase first.
  diff      `git diff --check BASE...SHA` is clean.
  fragment  the range adds a file under --fragment-dir (default changelog.d; pass '' to skip).
With --repo (the only network use) it also prints the base branch's required check names and the exact-SHA
verdict of the latest check runs (`surface_check.check_checks`); a failing check is red, pending, NO-RUN or unreadable
is UNVERIFIED: it prints `handback UNVERIFIED: <n> checks could not run` instead of GREEN and exits 3. With --tracker-issue it composes a HANDOFF post through `board_post.py`: a dry run that
prints the command unless --send is given.
It PRINTS the teardown commands (`clean_finished.sh`, `reap_own.sh --report`) and never runs them, and never
pushes or moves any branch: the human push grant stays. Exit 0 green, 1 red, 2 bad arguments, 3 unverified (the checks have not finished; re-run).
Side effects: whatever the gate commands do; --send posts one issue comment.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE_CACHE = os.path.join(HERE, "..", "..", "deep-code-review", "scripts", "gate_cache.py")


def run(argv, **kw):
    """(returncode, stdout) of argv; stderr passes through. Never raises on a nonzero exit."""
    p = subprocess.run(argv, stdout=subprocess.PIPE, text=True, **kw)
    return p.returncode, p.stdout


def required_checks(slug, base, sha, timeout):
    """Print the base branch's required check names and the latest-run verdict at sha.
    Returns (failed, unverified): unverified counts PENDING + NO-RUN runs, or 1 when the verdict is unreadable."""
    sys.path.insert(0, HERE)
    import surface_check as sc  # noqa: E402  (lazy: offline runs never import the forge code)
    branch = base.split("/", 1)[1] if base.startswith("origin/") else base
    rc, out, _ = sc._gh(["gh", "api", f"repos/{slug}/branches/{branch}/protection/required_status_checks"], timeout)
    names = []
    if rc == 0:
        try:
            d = json.loads(out)
            names = [c["context"] for c in d.get("checks") or []] or list(d.get("contexts") or [])
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    print("required checks: " + (", ".join(names) if names else "unreadable or none (judging every latest check run)"))
    code, summary, why = sc.check_checks(slug, sha, names, timeout)
    print(f"checks {sha[:12]}: {why}")
    if code != sc.COULD_NOT_CHECK:
        return code == sc.FAIL, 0
    return False, sum(int(n) for n in re.findall(r"(\d+) (?:PENDING|NO-RUN)", summary or "")) or 1


def main(argv):
    """CLI entry point; returns 0 green, 1 red, 2 bad arguments."""
    ap = argparse.ArgumentParser(prog="handback.py", description="One-command lane handback; prints cleanup, never runs it.")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--base", required=True, help="the integration ref the lane lands on")
    ap.add_argument("--branch", required=True)
    ap.add_argument("--gate-cmd", action="append", required=True, help="a gate command line (repeatable)")
    ap.add_argument("--cite", action="append", default=[])
    ap.add_argument("--artifact-root")
    ap.add_argument("--fragment-dir", default="changelog.d", help="'' skips the changelog-fragment check")
    ap.add_argument("--worktree", default=os.getcwd(), help="the lane worktree: gates and git steps run here; named in the printed cleanup")
    ap.add_argument("--repo", default="", help="OWNER/NAME: enables the network steps")
    ap.add_argument("--tracker-issue", type=int)
    ap.add_argument("--agent", default="")
    ap.add_argument("--to", default="", help="HANDOFF recipient (board_post.py requires it)")
    ap.add_argument("--body-file")
    ap.add_argument("--send", action="store_true", help="really post to the tracker (default: dry run)")
    ap.add_argument("--timeout", type=float, default=60.0)
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if a.tracker_issue and not (a.repo and a.agent and a.to and a.body_file):
        print("handback: --tracker-issue needs --repo, --agent, --to and --body-file", file=sys.stderr)
        return 2
    if not os.path.isdir(a.worktree):
        print(f"handback: --worktree {a.worktree} is not a directory", file=sys.stderr)
        return 2

    def red(step):
        print(f"handback RED: {step}")
        return 1

    for cmd in a.gate_cmd:
        argv_ = ([sys.executable, GATE_CACHE, "run", "--stage", "handback", "--tree", a.sha, "-c", cmd]
                 if os.path.exists(GATE_CACHE) else ["bash", "-c", cmd])
        rc, out = run(argv_, cwd=a.worktree)
        if rc:
            print(out.rstrip())
            return red(f"gate: {cmd}")
    guard = [sys.executable, os.path.join(HERE, "lane_guard.py"), "handback", "--sha", a.sha, "--base", a.base, "--branch", a.branch]
    for c in a.cite:
        guard += ["--cite", c]
    if a.artifact_root:
        guard += ["--artifact-root", a.artifact_root]
    rc, out = run(guard, cwd=a.worktree)
    print(out.strip())
    if rc:
        return red("guard: lane_guard.py handback")
    if run(["git", "merge-base", "--is-ancestor", a.base, a.sha], cwd=a.worktree)[0]:
        return red(f"ff: {a.base} is not an ancestor of {a.sha[:12]}; rebase onto it")
    if run(["git", "diff", "--check", f"{a.base}...{a.sha}"], cwd=a.worktree)[0]:
        return red("diff: git diff --check reports whitespace errors")
    if a.fragment_dir:
        rc, out = run(["git", "diff", "--name-only", "--diff-filter=A", f"{a.base}...{a.sha}", "--", a.fragment_dir], cwd=a.worktree)
        if rc or not out.strip():
            return red(f"fragment: the range adds no file under {a.fragment_dir}/")
    print(f"ok: gates, guard, fast-forward of {a.base}, diff --check" + (", fragment" if a.fragment_dir else ""))
    unverified = 0
    if a.repo:
        failed, unverified = required_checks(a.repo, a.base, a.sha, a.timeout)
        if failed:
            return red("checks: a required check run failed")
    if unverified:
        print(f"handback UNVERIFIED: {unverified} checks could not run")
        return 3
    if a.tracker_issue:
        post = [sys.executable, os.path.join(HERE, "board_post.py"), "--repo", a.repo, "--issue", str(a.tracker_issue),
                "--agent", a.agent, "--type", "HANDOFF", "--refs", f"#{a.tracker_issue}", "--to", a.to, "--body-file", a.body_file] + (["--post"] if a.send else [])
        rc, out = run(post)
        print(out.strip())
        if rc:
            return red("tracker: board_post.py refused the post")
    print("handback GREEN " + a.sha[:12])
    print("cleanup (printed, not run; run after the push grant):")
    print(f"  ROOT={a.worktree} bash {os.path.join(HERE, 'clean_finished.sh')}")
    print(f"  ROOT={a.worktree} bash {os.path.join(HERE, 'reap_own.sh')} --report   # must print orphans=0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
