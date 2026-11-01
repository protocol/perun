#!/usr/bin/env python3
"""handback.py — lane handback, gates to merge; composes the existing scripts, adds no gate logic of its own.

  handback.py --sha SHA --base REF --branch BRANCH --gate-cmd CMD [--gate-cmd CMD ...]
              [--cite PATH ...] [--spec PATH ...] [--artifact-root DIR] [--fragment-dir DIR] [--worktree DIR]
              [--repo OWNER/NAME [--tracker-issue N --agent NAME --to NAME --body-file FILE [--send]] [--merge-pr N [--apply]]] [--timeout S]

Gates run in --worktree and every git step runs there too (default: the current directory).
Runs in order and stops at the first red step, printing `handback RED: <step>` and exiting 1:
  gate      each --gate-cmd through `gate_cache.py run --stage handback` (a tree that already passed is not rerun;
            plain `bash -c` when deep-code-review is not installed).
  guard     `lane_guard.py handback` (orphan, unrelated history, unmoved head, branch tip, cites).
  ff        BASE is an ancestor of SHA, so BASE can fast-forward to it; otherwise rebase first.
  diff      `git diff --check BASE...SHA` is clean.
  fragment  the range adds a file under --fragment-dir (default changelog.d; pass '' to skip).
  tests     the commits' `Tests:` lines (BASE..SHA) must all be X/X with total X>0 or `none (<where the suites run>)`, or carry a `No-Tests-Reason:` trailer (a BLOCKED/WIP head
            subject is exempt). Run last, before any merge. HANDBACK_TESTS_COUNT=enforce exits 4 `UNVERIFIED: no passing test count`;
            default shadow only warns; off skips.
  mode      each findings claim in --body-file for a review mode (security, perf, ...) has a `mode: ran (N files)` or `mode: NOT RUN (reason)`
            entry (validate_status_claims.mode_gaps), so a skipped mode never reads as 0 findings; skipped without --body-file or deep-code-review.
  claims    a --body-file line that claims a full test pass (`run-ci-tests` / `--affected` / `Tests:` / "N tests", beside pass/passing/green/ok/X/X; "not passed" and "2 of 3 passed" are not claims)
            needs a lkg.py receipt for SHA's tree with rc 0 whose runner blob and re-derived selection (against merge-base BASE) check out (`run-ci-tests.sh --affected` writes one per run) or SHA being
            the last-known-good; else `unverified test claim (no receipt for this tree)` (red). No writable receipt location, an unresolvable tree or merge-base: `could not verify` is yellow (exit 3, UNVERIFIED), never red.
  spec      each --spec PATH (a .py run with python3, anything else with bash) runs 3 times in --worktree, each under --timeout; one
            failure or timeout is red (`handback RED: spec PATH`), and so is a worktree that is not clean at SHA. --spec is REQUIRED
            when any BASE..SHA commit subject matches `^fix.*flak(e|y|iness)` (case-insensitive) or the diff changes a file named by
            an id on the flake_ledger.py quarantine list (`path` or `path::name`). The list is read from BASE at
            $FLAKE_LEDGER_DIR (default `.claude/flake-ledger`) when that is relative, else from that absolute directory.
With --repo (the only network use) it also prints the base branch's required check names and the exact-SHA
verdict of the latest check runs (`surface_check.check_checks`); a failing check is red, pending, NO-RUN or unreadable
is UNVERIFIED: it prints `handback UNVERIFIED: <n> checks could not run` instead of GREEN and exits 3. With --tracker-issue it composes a HANDOFF post through `board_post.py`: a dry run that
prints the command unless --send is given.
With --merge-pr N (needs --repo and --sha as 40 hex digits; readable required-check names, else UNVERIFIED) it first
checks that PR N targets --base at exactly SHA and that review_gate.py has an independent review receipt for it, then prints `gh pr merge N --merge --match-head-commit SHA` (GitHub
refuses a head that moved past SHA; `[skip ci]` is added when policy github_actions=off, an unreadable policy is red,
as in land_train.sh). --apply runs it, only after every step above is GREEN; a refused or failed merge is `handback RED: merge`,
and the --tracker-issue post runs only after the merge. A train of several PRs is `train_land.sh`.
It PRINTS the teardown commands (`clean_finished.sh`, `reap_own.sh --report`) and a branch-prune command and never
runs them, and never pushes: the only forge write besides --send is the --apply merge. Exit 0 green, 1 red, 2 bad arguments, 3 unverified (the checks have not finished; re-run), 4 unverified test count (HANDBACK_TESTS_COUNT=enforce).
Side effects: whatever the gate commands do; --send posts one issue comment; --apply merges one PR.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE_CACHE = os.path.join(HERE, "..", "..", "deep-code-review", "scripts", "gate_cache.py")
STATUS_CHECK = os.path.join(HERE, "..", "..", "deep-code-review", "scripts", "validate_status_claims.py")


def run(argv, **kw):
    """(returncode, stdout) of argv; stderr passes through. Never raises on a nonzero exit."""
    p = subprocess.run(argv, stdout=subprocess.PIPE, text=True, **kw)
    return p.returncode, p.stdout


def mode_gaps(path):
    """Findings claims in the hand-back body PATH for a review mode with no coverage entry; [] when deep-code-review is not installed or PATH is unreadable."""
    if not os.path.exists(STATUS_CHECK):
        return []
    sys.path.insert(0, os.path.dirname(STATUS_CHECK))
    import validate_status_claims as v  # noqa: E402
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return v.mode_gaps(f.read())
    except OSError:
        return []


_STRONG = re.compile(r"run-ci-tests|--affected|\baffected:|\baffected (?:tests|suites?)\b|\btests?\s*:|\btests?\s+\d+\s*(?:/|of)\s*\d+", re.I)
_PASS = r"\b(?:pass(?:ed|es|ing)?|green|ok)\b"
_WEAK = re.compile(r"\b(?:all|\d+)\s+(?:\w+\s+)?(?:tests?|suites?)\b[\s:,(-]*(?:all\s+)?(?:" + _PASS + "|\u2705)", re.I)  # "12 tests passing", but not "added 2 tests; lint ok"
_NEG = re.compile(r"(?:\bnot|\bnever|\bno|n['\u2019]t)\s+(?:\w+\s+)?" + _PASS, re.I)  # "not passed", "didn't pass", "did not yet pass"
_RATIO = re.compile(r"(\d+)\s*(?:/|of)\s*(\d+)")


def _is_claim(line):
    """True when `line` names a test run and claims it fully passed: a pass word that no negation cancels ("pass", "passing", "green", "ok", a tick), or any X/X (or "X of X") counts like "Tests: 12/12 pass"
    ("44/45 pass; rerun 45/45 pass" claims the rerun). A bare "N tests" names a run only when the pass word follows it ("added 2 tests; lint ok" does not).
    A partial ratio ("2 of 3 passed") or a negated pass ("not passed") is honest prose, not a claim."""
    line = _NEG.sub("", line)
    if not (_STRONG.search(line) or _WEAK.search(line)):
        return False
    ratios = _RATIO.findall(line)
    if ratios:
        return any(a == b for a, b in ratios)
    return bool(re.search(_PASS + "|\u2705", line, re.I))


def test_claim_gaps(path, sha, cwd, base=None):
    """(red, yellow) message lists, one message per --body-file line (path) claiming a run-ci-tests / affected / "Tests: N/N" pass that no receipt backs.
    Backed = a passing lkg.py affected receipt for sha's tree (its runner and re-derived selection checked against merge-base(base, sha)), or sha is the last-known-good (full suite).
    red = `unverified test claim (why)`: refused or no receipt. yellow = could not verify (no receipt location is writable here, the tree or merge-base does not resolve, or the check itself failed): never a false claim.
    ([], []) without claims; unreadable PATH -> ([], [])."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            hits = [n for n, line in enumerate(f.read().splitlines(), 1) if _is_claim(line)]
    except OSError:
        return [], []
    if not hits:
        return [], []
    sys.path.insert(0, HERE)
    import lkg  # noqa: E402
    rc, tree = run(["git", "rev-parse", f"{sha}^{{tree}}"], cwd=cwd)
    tree = tree.strip()
    mbrc, mb = run(["git", "merge-base", base, sha], cwd=cwd) if base else (1, "")
    if rc or mbrc or not mb.strip():  # never fall back to the receipt's own base: a forger picks it
        ok, why = None, "could not verify: cannot resolve the " + ("tree" if rc else f"merge-base of {base} and the head")
    else:
        try:
            ok, why = lkg.affected_check(tree, cwd, mb.strip())
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            ok, why = None, f"could not verify: {lkg.tilde(e)}"
    try:
        ok = lkg.check(sha, cwd)[0] or ok  # the full suite at this exact head backs it too
    except (OSError, RuntimeError):  # no readable pointer (e.g. ~/.cache denied in the sandbox) just means it does not back the claim
        pass
    if ok:
        return [], []
    if ok is None:
        return [], [f"L{n}: test claim could not be verified ({why})" for n in hits]
    return [f"L{n}: unverified test claim ({why}) tree {tree[:12]}; rerun scripts/run-ci-tests.sh --affected on this tree or drop the claim" for n in hits], []


def merge_command(a):
    """(argv, '') for `gh pr merge`, or (None, why) when PR --merge-pr is not --base at --sha or the policy is unreadable."""
    rc, out = run(["gh", "pr", "view", str(a.merge_pr), "--repo", a.repo, "--json", "baseRefName,headRefOid"], cwd=a.worktree)
    try:
        pr = json.loads(out)
    except ValueError:
        pr = {}
    if rc or not isinstance(pr, dict):
        return None, f"PR #{a.merge_pr} is unreadable"
    if pr.get("baseRefName") != a.base.removeprefix("origin/") or pr.get("headRefOid") != a.sha:
        return None, f"PR #{a.merge_pr} is {pr.get('baseRefName')}@{str(pr.get('headRefOid'))[:12]}, not {a.base}@{a.sha[:12]}"
    # review_gate (.perun/policy.json): an independent review receipt for this exact head, as in land_train.sh.
    if run([sys.executable, os.path.join(HERE, "review_gate.py"), "check", str(a.merge_pr), "--head", a.sha, "--repo", a.repo],
           cwd=a.worktree, stdin=subprocess.DEVNULL)[0]:
        return None, f"PR #{a.merge_pr} has no independent review receipt for {a.sha[:12]} (review_gate)"
    rc, gha = run([sys.executable, os.path.join(HERE, "perun_policy.py"), "get", "github_actions"], cwd=a.worktree)
    if rc:
        return None, "bad .perun/policy.json"
    gha = os.environ.get("PERUN_GITHUB_ACTIONS", gha.strip())  # the env overrides, as in skip-ci
    cmd = ["gh", "pr", "merge", str(a.merge_pr), "--repo", a.repo, "--merge", "--match-head-commit", a.sha]
    return cmd + (["--body", "[skip ci]"] if gha == "off" else []), ""


def required_checks(slug, base, sha, timeout, strict=False):
    """Print the base branch's required check names and the latest-run verdict at sha.
    Returns (failed, unverified): unverified counts PENDING + NO-RUN runs, or 1 when the verdict is unreadable.
    strict (a merge): no readable required-check names is itself unverified, so an unreadable protection never merges."""
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
    if strict and not names:
        return False, 1
    code, summary, why = sc.check_checks(slug, sha, names, timeout)
    print(f"checks {sha[:12]}: {why}")
    if code != sc.COULD_NOT_CHECK:
        return code == sc.FAIL, 0
    return False, sum(int(n) for n in re.findall(r"(\d+) (?:PENDING|NO-RUN)", summary or "")) or 1


def tests_claim(msgs):
    """Why the lane's commit messages (base..sha, newest first) prove no passing test run, or '' when they do.
    Each `Tests: ...` line (leading space, `>`, `*`, `-` allowed) needs every X/Y on it with X==Y and total Y>0; one bad line fails
    the lot. A non-empty `No-Tests-Reason:` trailer or a BLOCKED/WIP head subject (not a done claim) waives it. A `none (<where the suites run>)`
    line with a non-empty parenthetical is a stated no-run that counts as a good line (digits inside it are no count; a bare `none` or `none ()` fails)."""
    if re.search(r"^No-Tests-Reason:[ \t]*\S", msgs, re.M) or re.match(r"\s*(blocked|wip)\b", msgs, re.I):
        return ""
    lines = re.findall(r"^[ \t>*-]*Tests?\b[^:\n]*:(.*)$", msgs, re.M | re.I)
    if not lines:
        return "no `Tests: X/X` line"
    for t in lines:
        if re.fullmatch(r"\s*none\s*\(\s*[^\s)].*\)\s*", t, re.I):
            continue
        c = re.findall(r"(\d+)/(\d+)", t)
        if not c or any(x != y for x, y in c) or sum(int(y) for _, y in c) == 0:
            return f"`Tests:{t}` is not X/X with X>0"
    return ""


def main(argv):
    """CLI entry point; returns 0 green, 1 red, 2 bad arguments."""
    ap = argparse.ArgumentParser(prog="handback.py", description="One-command lane handback; prints cleanup, never runs it.")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--base", required=True, help="the integration ref the lane lands on")
    ap.add_argument("--branch", required=True)
    ap.add_argument("--gate-cmd", action="append", required=True, help="a gate command line (repeatable)")
    ap.add_argument("--cite", action="append", default=[])
    ap.add_argument("--spec", action="append", default=[], help="a spec to run 3x at --sha; required for a flake fix (repeatable)")
    ap.add_argument("--artifact-root")
    ap.add_argument("--fragment-dir", default="changelog.d", help="'' skips the changelog-fragment check")
    ap.add_argument("--worktree", default=os.getcwd(), help="the lane worktree: gates and git steps run here; named in the printed cleanup")
    ap.add_argument("--repo", default="", help="OWNER/NAME: enables the network steps")
    ap.add_argument("--tracker-issue", type=int)
    ap.add_argument("--agent", default="")
    ap.add_argument("--to", default="", help="HANDOFF recipient (board_post.py requires it)")
    ap.add_argument("--body-file")
    ap.add_argument("--merge-pr", type=int, help="PR number to merge once GREEN (needs --repo); a dry run unless --apply")
    ap.add_argument("--apply", action="store_true", help="really run the merge (default: print it)")
    ap.add_argument("--send", action="store_true", help="really post to the tracker (default: dry run)")
    ap.add_argument("--timeout", type=float, default=60.0)
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if a.tracker_issue and not (a.repo and a.agent and a.to and a.body_file):
        print("handback: --tracker-issue needs --repo, --agent, --to and --body-file", file=sys.stderr)
        return 2
    if a.apply and not a.merge_pr:
        print("handback: --apply needs --merge-pr (it only applies the merge)", file=sys.stderr)
        return 2
    if a.merge_pr and not a.repo:
        print("handback: --merge-pr needs --repo (a merge needs the checks verdict)", file=sys.stderr)
        return 2
    if a.merge_pr and not re.fullmatch(r"[0-9a-f]{40}", a.sha):
        print("handback: --merge-pr needs --sha as a full 40-hex commit id", file=sys.stderr)
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
    gaps = mode_gaps(a.body_file) if a.body_file else []
    if gaps:
        print("\n".join(gaps))
        return red("mode coverage: --body-file claims findings for a mode with no ran/NOT RUN entry")
    gaps, unknown = test_claim_gaps(a.body_file, a.sha, a.worktree, a.base) if a.body_file else ([], [])
    if gaps:
        print("\n".join(gaps))
        return red("test claim: --body-file claims a run-ci-tests/affected pass with no passing receipt for this tree")
    if unknown:
        print("\n".join(unknown))
    if not a.spec:
        sys.path.insert(0, HERE)
        import flake_ledger as fl  # noqa: E402
        d = os.environ.get("FLAKE_LEDGER_DIR", fl.DEFAULT_DIR)
        try:  # the list comes from BASE (or an absolute dir outside the tree), so a PR cannot delete its own entry
            if os.path.isabs(d):
                q = fl.load_q(os.path.join(d, "quarantine.json"))
            else:
                rc, out = run(["git", "show", f"{a.base}:{d}/quarantine.json"], cwd=a.worktree, stderr=subprocess.DEVNULL)
                q = json.loads(out) if rc == 0 else {}
        except ValueError:
            return red("spec: quarantine list is not valid JSON")
        (rc1, changed), (rc2, log) = (run(["git", *c], cwd=a.worktree) for c in (
            ["diff", "--name-only", f"{a.base}...{a.sha}"], ["log", "--format=%s", f"{a.base}..{a.sha}"]))
        if rc1 or rc2:
            return red("spec: git diff/log failed")
        if re.search(r"^fix.*flak(e|y|iness)", log, re.I | re.M) or any(i.split("::")[0] in changed.split("\n") for i in q):
            return red("spec: --spec PATH is required for a flake fix or a change to a quarantined test")
    if a.spec and (run(["git", "rev-parse", "HEAD"], cwd=a.worktree)[1].strip() != a.sha
                   or run(["git", "status", "--porcelain"], cwd=a.worktree)[1].strip()):
        return red("spec: worktree not clean at SHA")
    for s in a.spec:
        for _ in range(3):
            try:
                rc, out = run([sys.executable if s.endswith(".py") else "bash", "--", s], cwd=a.worktree, timeout=a.timeout)
            except subprocess.TimeoutExpired:
                return red(f"spec {s}: timeout")
            if rc:
                print(out.rstrip())
                return red(f"spec {s}")
    print(f"ok: gates, guard, fast-forward of {a.base}, diff --check" + (", fragment" if a.fragment_dir else "") + (f", {len(a.spec)} spec x3" if a.spec else ""))
    unverified = 0
    if a.repo:
        failed, unverified = required_checks(a.repo, a.base, a.sha, a.timeout, strict=bool(a.merge_pr))
        if failed:
            return red("checks: a required check run failed")
    unverified += len(unknown)  # a test claim that could not be verified is yellow, never red
    mode = os.environ.get("HANDBACK_TESTS_COUNT", "shadow")  # shadow (default) warns, enforce => exit 4, off skips
    rc, msgs = (0, "") if mode == "off" else run(["git", "log", "--format=%B", f"{a.base}..{a.sha}"], cwd=a.worktree)
    why = "cannot read commit message" if rc else tests_claim(msgs) if mode != "off" else ""
    if why:
        print(f"handback tests-count {'UNVERIFIED: no passing test count' if mode == 'enforce' else 'shadow'}: {why}; add a real count, a Tests: none (<where they run>) line or a No-Tests-Reason: trailer")
        if unverified:
            print(f"handback UNVERIFIED: {unverified} checks could not run")
        if mode == "enforce":
            return 4
    if unverified:
        print(f"handback UNVERIFIED: {unverified} checks could not run")
        return 3
    merge = None
    if a.merge_pr:
        merge, why = merge_command(a)
        if not merge:
            return red(f"merge: {why}")
    if merge:
        print(("merging: " if a.apply else "dry run (add --apply to merge): ") + " ".join(merge))
        if a.apply and run(merge, cwd=a.worktree)[0]:
            return red(f"merge: gh pr merge {a.merge_pr} failed (head moved past {a.sha[:12]}?)")
    if a.tracker_issue:  # after the merge, so a refused merge never posts a HANDOFF
        post = [sys.executable, os.path.join(HERE, "board_post.py"), "--repo", a.repo, "--issue", str(a.tracker_issue),
                "--agent", a.agent, "--type", "HANDOFF", "--refs", f"#{a.tracker_issue}", "--to", a.to, "--body-file", a.body_file] + (["--post"] if a.send else [])
        rc, out = run(post)
        print(out.strip())
        if rc:
            return red("tracker: board_post.py refused the post" + (" (the PR is already merged)" if merge and a.apply else ""))
    print("handback GREEN " + a.sha[:12])
    print("cleanup (printed, not run; run after the push grant):")
    print(f"  ROOT={a.worktree} bash {os.path.join(HERE, 'clean_finished.sh')}")
    print(f"  ROOT={a.worktree} bash {os.path.join(HERE, 'reap_own.sh')} --report   # must print orphans=0")
    print(f"  git push origin --delete {a.branch}   # branch prune, after the merge")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
