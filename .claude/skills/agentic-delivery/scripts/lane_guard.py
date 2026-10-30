#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=refuse to start a write lane that is not isolated, review=2027-01-30
"""Lane-start isolation guard: refuse unless this lane really is isolated.

Run as the FIRST step of every write-lane, from the lane's working directory:

    python3 .claude/skills/agentic-delivery/scripts/lane_guard.py --expect-branch NAME

Exit 0 (one `LANE_GUARD OK:` line) only when ALL hold:
  1. --expect-branch was given. Without it the guard could only prove "some
     linked worktree on some non-default branch", not "this lane's worktree",
     so it refuses. --allow-any-branch waives this for a non-lane probe and
     then makes only that weaker claim; a lane brief never uses it.
  2. git answers a plain read in the cwd (a PATH shim or sandbox that blocks
     git fails it). A tool-call hook never sees this subprocess, so chain the
     lane's own direct read first: `git rev-parse HEAD && python3 lane_guard.py`.
  3. The cwd is a LINKED worktree: `git rev-parse --git-dir` differs from
     `--git-common-dir`. Equal means the main checkout (a shared tree), which
     is exactly the escape this guard exists to catch.
  4. HEAD is on a named branch (not detached) that is not a default branch.
  5. HEAD's branch equals --expect-branch exactly.
  6. No OTHER live process — excluding this process and its own ancestor
     chain (the calling shell/orchestrator, which can itself have its cwd
     inside the worktree) — has its cwd inside the worktree. Reuses
     `lane_liveness.py`'s cwd-occupancy scan by import
     (`lane_liveness.foreign_cwd_pids`), never a second implementation. When
     that scan itself is blind (no lsof, no /proc, or a scan that can't see
     its own process), this refuses as UNVERIFIED — a blind scan is never
     read as "no foreign process" — unless --allow-unverified is passed
     (owner-only escape hatch, documented here, never a default: it trades a
     confirmed absence of a live writer for an explicit human call).

Otherwise exit 1 with exactly one `LANE_GUARD REFUSE: <reason>` line on stdout,
written to be quoted verbatim in the lane's handback. The lane stops at that
point; it never retries the refused step through another path.

DEFAULT BRANCHES. A union, never a single guess: `main` and `master`, the
remote HEAD's target (`git symbolic-ref refs/remotes/origin/HEAD`) when set,
the main checkout's current branch (first entry of `git worktree list
--porcelain`) when it is on one, and --default-branch when given (it adds to
the set, never replaces it). A stale origin/HEAD therefore cannot make `main`
pass. Fails closed: when the worktree list cannot be read, or when neither
origin/HEAD, the main checkout's branch, nor --default-branch names a branch
(so the repository's real default is unknown), the guard refuses.

ENVIRONMENT. GIT_DIR, GIT_WORK_TREE, GIT_COMMON_DIR and GIT_INDEX_FILE are
removed from every git call's environment, so an inherited variable (for
example from a git hook) cannot point the check at a different repository than
the cwd. Read-only except for the one copy under BANLIST SEED: the guard never
writes to a tracked file, the index, refs or any other path.

BANLIST SEED. After an OK result only, when the main checkout has a
`.banlist.local.txt` (the gitignored file holding private identifiers for the
privacy gate) and this worktree has nothing at that path, the guard copies it in
with a plain byte copy, so the lane's privacy gate sees the same private
patterns as the main checkout instead of silently skipping them. Never a
symlink; never an overwrite (the file is created exclusively, so an existing
file, symlink or dangling symlink is left alone); skipped unless git ignores the
path in this worktree (otherwise `git add -A` could commit a private file); any
failure copies nothing and is not a refusal. The OK line then ends with
`; copied .banlist.local.txt from the main checkout <path>`. Claude Code can also
copy gitignored files at worktree creation through a `.worktreeinclude` file
(https://code.claude.com/docs/en/worktrees); this copy covers every other host
and a worktree made by hand or with `lane_worktree.sh`.

    lane_guard.py --selftest    builds throwaway repos and proves every
                                refusal fires (and that the OK case passes).

HANDBACK MODE. Run as the LAST step before the orchestrator relays a lane's PR
onward (merges it, or hands it to a human/reviewer), from a checkout that can
resolve both refs:

    python3 .claude/skills/agentic-delivery/scripts/lane_guard.py handback \
        --sha <lane-head-sha> --base <dispatch-base> --branch <lane-branch> \
        [--cite <path> ...] [--artifact-root <dir>]

<dispatch-base> is the integration ref the lane was dispatched from (and
will land on).

Catches a root/orphan commit: a lane that committed in an unusual state (an
orphan or unborn HEAD, or plumbing commands) can produce a head whose tree is
the whole repository, yet a tree-diff PR view and CI both look normal — the
defect surfaces only on rebase, as a full-tree conflict. Exit 0 (one
`LANE_GUARD OK:` line) only when ALL hold:
  0. `git rev-parse --is-shallow-repository` is not `true` (a shallow clone's
     truncated history cannot prove ancestry either way, so this refuses
     before attempting any of the diagnosis below), and neither a graft
     (`$(git rev-parse --git-common-dir)/info/grafts` does not exist) nor a
     replace ref can rewrite parentage — every git call in this mode runs
     with `GIT_NO_REPLACE_OBJECTS=1`.
  1. `git log -1 --format=%P <sha>` succeeds and is non-empty (the head has at
     least one parent — a root/orphan commit's is empty).
  2. `git merge-base <sha> <base>` succeeds (the head shares history with the
     integration ref; an unresolvable ref or an unrelated history both fail
     this).
  3. `git rev-list --max-parents=0 <base>..<sha>` succeeds and is empty (no
     root commit is reachable at all in `<base>..<head>` — catches an
     unrelated-history merge that pulls in a second root even though the
     merge commit itself has parents and a merge-base with `<base>`).
  4. `git rev-list --count <base>..<sha>` is non-zero: a head already reachable
     from the base the lane was dispatched from parked nothing (a lane that
     reports "parked <head>" while HEAD never moved).
  5. --sha is a 7-40 character lowercase hex id and the resolved commit
     starts with it (a ref name would always match its own tip), and the tip
     of --branch (`refs/heads/<branch>`, or a full `refs/...` name) is
     exactly that commit, so a sha from another branch, or a tip that moved
     after the claim, is refused.
  6. Every relative --cite is a file committed at the cited sha (`git
     cat-file -t <sha>:<path>` is `blob`, repo-root relative; empty and `..`
     paths refused; a file only on disk does not count). An absolute --cite
     (an artifact such as a composite image) counts only when it is an
     existing file inside the explicit --artifact-root.
Otherwise exit 1 with exactly one `LANE_GUARD REFUSE:` line. Fails closed:
any nonzero = refuse; pass only when exit 0 AND an OK line is printed — a
git failure at any step is a refusal, never a pass. Recovery: check out a
fresh branch from `<base>`, take the lane's files from the bad commit
(`git checkout <bad-sha> -- <paths>`), commit normally, and force-push with an
explicit lease on the old head (force-push stays owner/standing-grant gated,
same as any other force-push in this repo).

WAIT MODE. A lane that ends its turn with background work still running (a
browser test, a dev server, a build) hands back "waiting on background work"
instead of a verified result. Before the handback, wait for that work,
bounded, then verify:

    python3 .claude/skills/agentic-delivery/scripts/lane_guard.py wait \
        [--pid N ...] [--port N ...] [--file PATH ...] [--timeout S] \
        && python3 .claude/skills/agentic-delivery/scripts/lane_guard.py handback ...

Exit 0 (one `LANE_GUARD OK:` line) once every target is finished:
  - --pid: must already be running when the wait *starts* (a stale or
    mistyped pid is never silently "finished" — see below); once confirmed
    alive, finished means it no longer runs (gone, or a zombie nobody reaped
    yet — per `ps -o stat=`, falling back to a signal-0 probe).
  - --port: must be observed accepting a connection on `localhost:<port>` at
    least once within the `--settle` window (default 30s, capped at
    --timeout — a target that only ever starts up slowly is a REFUSE-worthy
    brief, not a longer wait); once confirmed listening, finished means
    nothing accepts a connection there any more. A port that never once
    listens is exactly as unverifiable as a pid that was never alive — never
    read as "already done".
  - --file: exists, is non-empty, and keeps the same size on two consecutive
    polls. No alive-at-start check (a file plausibly pre-exists from a prior
    run and is still the right target); point --file at a result written
    once at the end (a JUnit report, a status file), not a streaming log
    whose pauses look finished — for a log, wait on the writer's --pid.

Exit 2 with one `LANE_GUARD COULD_NOT_CHECK:` line naming the target when: a
--pid is not observed running at wait start; a --port is never observed
listening within the settle window; or --timeout seconds (default 300) pass
with something still running. A timeout is never a pass, and the handback
does not run. Exit 1 (`LANE_GUARD REFUSE:`) on no target, a pid below 1, a
port outside 1-65535, or a non-positive --timeout/--settle. Read-only: it
signals nothing and kills nothing.
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_liveness  # noqa: E402  (sibling module, path set above)

OK = 0
REFUSED = 1
COULD_NOT_CHECK = 2
_STRIPPED_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
_ALWAYS_DEFAULTS = ("main", "master")
_UI_RE = re.compile(r"\.(tsx|jsx|vue|svelte|html?|css|scss|sass|less)$", re.I)
_JOURNEY_RE = re.compile(r"^\s*journey:\s+\S+\s+.+\s+PASS\s*$", re.M)
_POSTDEPLOY_RE = re.compile(r"^\s*postdeploy-logs:\s*(\S.*?)\s*$", re.M)


def _receipt_problem(cwd, base, full, receipt, deployed, git):
    """Why the delivery receipt cannot back a DONE claim, or None. A diff that touches UI files needs a
    `journey: <page> <steps> PASS` line; --deployed needs `postdeploy-logs: clean` (absent = deployed,
    unverified; anything else = errors listed, not done). Missing/unreadable receipt = refuse."""
    code, names = _git_handback(["diff", "--name-only", f"{base}...{full}"], cwd, git)
    if code != 0:
        return f"cannot list files changed in {base}...{full}"
    ui = any(_UI_RE.search(n) for n in names.splitlines())
    if not (ui or deployed):
        return None
    try:
        with open(receipt, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeError, TypeError):
        return f"UI/deploy claim needs --receipt FILE; {receipt!r} is not readable"
    if ui and not _JOURNEY_RE.search(text):
        return ("UI change has no `journey: <page> <steps> PASS` line in the receipt: click the control, "
                "assert the effect persisted after a reload, on the page the request came from")
    if deployed:
        m = _POSTDEPLOY_RE.search(text)
        if not m:
            return "deployed, unverified: receipt has no `postdeploy-logs: clean | <errors>` line"
        if m.group(1).lower() != "clean":
            return f"postdeploy-logs reports errors: {m.group(1)}"
    return None


def _git(args, cwd, git="git", extra_env=None):
    """Run one read-only git command; return (returncode, stripped stdout).

    A missing binary or an OS-level refusal returns code 127 instead of raising,
    so the caller turns it into a refusal line rather than a traceback. `extra_env`
    is applied after the strip below, so a caller can force a variable (handback
    mode forces GIT_NO_REPLACE_OBJECTS=1) that plain environment inheritance can't
    guarantee.
    """
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            [git, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout.strip()


def _git_handback(args, cwd, git="git"):
    """Like `_git`, but forces GIT_NO_REPLACE_OBJECTS=1 on every call.

    Handback's ancestry checks (parent, merge-base, reachable-root) all reason
    about true commit parentage; a replace ref can swap in a different parent
    at read time and make a bad head look clean. Every git call `check_handback`
    makes goes through this wrapper, never bare `_git`.
    """
    return _git(args, cwd, git, extra_env={"GIT_NO_REPLACE_OBJECTS": "1"})


def _main_checkout_branch(cwd, git):
    """Return (readable, branch) for the main checkout.

    The main checkout is the first entry of `git worktree list --porcelain`.
    `readable` is False when that list cannot be read or parsed; `branch` is
    None when the main checkout is detached or bare (no branch to add).
    """
    code, out = _git(["worktree", "list", "--porcelain"], cwd, git)
    if code != 0 or not out.startswith("worktree "):
        return False, None
    prefix = "branch refs/heads/"
    for line in out.split("\n\n", 1)[0].splitlines():
        if line.startswith(prefix) and len(line) > len(prefix):
            return True, line[len(prefix):]
    return True, None


def _default_branches(cwd, explicit, git):
    """Return (set of default branch names, refusal reason or None).

    See the module docstring: the union of main/master, origin/HEAD's target,
    the main checkout's branch, and `explicit`. The reason is set (fail
    closed) when the worktree list is unreadable or no source names a branch.
    """
    defaults = set(_ALWAYS_DEFAULTS)
    named = False
    if explicit:
        defaults.add(explicit)
        named = True
    code, ref = _git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd, git)
    prefix = "refs/remotes/origin/"
    if code == 0 and ref.startswith(prefix) and len(ref) > len(prefix):
        defaults.add(ref[len(prefix):])
        named = True
    readable, main_branch = _main_checkout_branch(cwd, git)
    if not readable:
        return defaults, "cannot read the worktree list to find the main checkout's branch"
    if main_branch:
        defaults.add(main_branch)
        named = True
    if not named:
        return defaults, (
            "default branch unknown (no origin/HEAD, main checkout not on a branch); "
            "pass --default-branch"
        )
    return defaults, None


def check(cwd, expect_branch=None, default_branch=None, git="git", allow_any_branch=False,
          allow_unverified=False, occupancy_scanner=None):
    """Evaluate the lane at `cwd`; return (exit_code, one-line message).

    Refuses when `expect_branch` is None unless `allow_any_branch` is True
    (then the OK line proves only a non-default linked worktree, not which
    lane). Side-effect free: runs read-only git commands only.

    `occupancy_scanner` defaults to `lane_liveness.foreign_cwd_pids` (a root
    -> (pids_or_None, detail) callable, same contract as that function); a
    test injects a stub here instead of depending on the host's real lsof/proc
    availability. `allow_unverified` waives a blind occupancy scan (see item 6
    of the module docstring) — owner-only, never a default.
    """
    if expect_branch is None and not allow_any_branch:
        return REFUSED, (
            "LANE_GUARD REFUSE: no --expect-branch given; a write-lane must name its own "
            "branch (--allow-any-branch is for non-lane probes only)"
        )
    code, top = _git(["rev-parse", "--show-toplevel"], cwd, git)
    if code != 0 or not top:
        return REFUSED, (
            f"LANE_GUARD REFUSE: git read failed in {cwd} (exit {code}); "
            "stop and hand back, do not retry git another way"
        )
    code_d, git_dir = _git(["rev-parse", "--git-dir"], top, git)
    code_c, common_dir = _git(["rev-parse", "--git-common-dir"], top, git)
    if code_d != 0 or code_c != 0 or not git_dir or not common_dir:
        return REFUSED, f"LANE_GUARD REFUSE: cannot resolve git dirs in {top}"
    real_git_dir = os.path.realpath(os.path.join(top, git_dir))
    real_common = os.path.realpath(os.path.join(top, common_dir))
    if real_git_dir == real_common:
        return REFUSED, (
            f"LANE_GUARD REFUSE: {top} is the main checkout, not a linked worktree "
            "(git-dir == git-common-dir)"
        )
    code, branch = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], top, git)
    if code != 0 or not branch:
        return REFUSED, f"LANE_GUARD REFUSE: HEAD is detached in {top}; a write-lane needs its own branch"
    defaults, unknown = _default_branches(top, default_branch, git)
    if unknown:
        return REFUSED, f"LANE_GUARD REFUSE: {unknown} in {top}"
    if branch in defaults:
        return REFUSED, f"LANE_GUARD REFUSE: HEAD is on default branch '{branch}' in {top}"
    if expect_branch is not None and branch != expect_branch:
        return REFUSED, f"LANE_GUARD REFUSE: HEAD is on '{branch}', expected '{expect_branch}' in {top}"
    scanner = occupancy_scanner or lane_liveness.foreign_cwd_pids
    occ_pids, occ_detail = scanner(top)
    if occ_pids is None:
        if not allow_unverified:
            return REFUSED, (
                f"LANE_GUARD REFUSE: UNVERIFIED — cannot confirm previous agent terminated in {top} "
                f"({occ_detail}); pass --allow-unverified (owner-only) to proceed anyway"
            )
        return OK, (
            f"LANE_GUARD OK: linked worktree {top} on branch '{branch}' "
            "(occupancy UNVERIFIED, proceeding on --allow-unverified)"
        )
    if occ_pids:
        return REFUSED, (
            f"LANE_GUARD REFUSE: live process(es) {sorted(occ_pids)} have cwd inside {top}; "
            "confirm the previous agent terminated before reusing this worktree"
        )
    return OK, f"LANE_GUARD OK: linked worktree {top} on branch '{branch}'"


BANLIST = ".banlist.local.txt"


def seed_banlist(cwd, git="git"):
    """Copy the main checkout's gitignored `.banlist.local.txt` into the worktree at `cwd` when it has none.

    Returns the text to append to the OK line ("" when nothing was copied). Plain byte copy, never a symlink;
    the destination is created exclusively, so any existing path (file, symlink, dangling symlink) is never
    overwritten. Copies only when git ignores the path in this worktree, so `git add -A` cannot stage it. Writes
    only that one path; never raises: any failure copies nothing, except a write that dies midway, which is
    named in the returned text so the lane's owner can fix it (the guard never deletes).
    """
    code, top = _git(["rev-parse", "--show-toplevel"], cwd, git)
    code_w, listing = _git(["worktree", "list", "--porcelain"], cwd, git)
    if code != 0 or code_w != 0 or not listing.startswith("worktree "):
        return ""
    main = listing.split("\n\n", 1)[0].splitlines()[0][len("worktree "):]
    src, dst = os.path.join(main, BANLIST), os.path.join(top, BANLIST)
    if os.path.realpath(main) == os.path.realpath(top) or not os.path.isfile(src) or os.path.lexists(dst):
        return ""
    if _git(["check-ignore", "-q", BANLIST], top, git)[0] != 0:
        return ""
    try:
        with open(src, "rb") as s:
            data = s.read()
        with open(dst, "xb") as d:
            d.write(data)
        shutil.copymode(src, dst)
    except FileExistsError:  # lost a race with another writer: theirs stays
        return ""
    except OSError:
        return f"; WARNING: copying {BANLIST} may be incomplete, check {dst} by hand" if os.path.lexists(dst) else ""
    return f"; copied {BANLIST} from the main checkout {main}"


def _cite_problem(cwd, full, path, artifact_root, git):
    """'' when one cited path is backed by evidence (rule 6 of HANDBACK MODE), else why not."""
    if os.path.isabs(path):
        if not artifact_root:
            return f"absolute cited path {path!r} needs --artifact-root"
        root, real = os.path.realpath(artifact_root), os.path.realpath(path)
        if os.path.commonpath([root, real]) != root:
            return f"cited path {path!r} is outside --artifact-root {artifact_root!r}"
        return "" if os.path.isfile(real) else f"cited path {path!r} is not an existing file"
    if not path or ".." in path.replace("\\", "/").split("/"):
        return f"cited path {path!r} is empty or '..'"
    code, kind = _git_handback(["cat-file", "-t", f"{full}:{path}"], cwd, git)
    return "" if code == 0 and kind == "blob" else f"cited path {path!r} is not a file committed at {full[:12]}"


def check_handback(cwd, sha, base, branch=None, cites=(), git="git", artifact_root=None,
                   receipt=None, deployed=False):
    """Evaluate a lane's head commit right before it is relayed onward (merged,
    or handed to a human/reviewer); return (exit_code, one-line message).

    Refuses when:
      - the repository is shallow (`git rev-parse --is-shallow-repository` ==
        `true`) — truncated history cannot prove ancestry either way, so this
        fires before any of the diagnosis below runs, never as a mislabeled
        orphan/unrelated-history result;
      - `$(git rev-parse --git-common-dir)/info/grafts` exists — a graft
        rewrites parentage in a way these checks can't see through;
      - `sha` has no parent (a root/orphan commit — its tree replays as a
        full-repo diff on rebase even though a tree-diff PR view and CI both
        look normal);
      - `sha` shares no `git merge-base` with `base` (an unresolvable ref, or
        a history unrelated to the integration branch — both would explode
        the same way on rebase/merge);
      - `git rev-list --max-parents=0 <base>..<sha>` finds any root commit
        reachable in `<base>..<head>` — an unrelated-history merge can pull a
        second root in through a merge commit that itself has parents and
        does share a merge-base with `base`, so the merge-base check alone
        would pass it;
      - `<base>..<sha>` holds no commit (the head parked nothing new);
      - `sha` is not a 7-40 character lowercase hex id that the resolved
        commit starts with;
      - the tip of `branch` does not resolve or is not exactly `sha`;
      - a relative path in `cites` is not a blob committed at `sha`, or an
        absolute one is not an existing file inside `artifact_root`;
      - the diff touches UI files (tsx/jsx/vue/svelte/html/css/...) or `deployed` is set and the
        `receipt` file lacks `journey: <page> <steps> PASS` / `postdeploy-logs: clean`
        (`_receipt_problem`).
    Every git call above runs with GIT_NO_REPLACE_OBJECTS=1 (`_git_handback`),
    so a replace ref cannot mask true parentage. Fails closed: any nonzero =
    refuse; pass only when exit 0 AND an OK line is printed — a git failure
    (including a nonzero from the rev-list check itself) is a refusal, never
    a pass. Side-effect free: runs read-only git commands only.
    """
    if not sha or not base or not branch:
        return REFUSED, "LANE_GUARD REFUSE: handback needs --sha, --base and --branch"
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return REFUSED, f"LANE_GUARD REFUSE: --sha {sha!r} must be a 7-40 character lowercase hex sha"

    code, is_shallow = _git_handback(["rev-parse", "--is-shallow-repository"], cwd, git)
    if code != 0:
        return REFUSED, f"LANE_GUARD REFUSE: cannot determine shallow-ness in {cwd}"
    if is_shallow == "true":
        return REFUSED, "LANE_GUARD REFUSE: shallow clone — git fetch --unshallow, then rerun"

    code, common_dir = _git_handback(["rev-parse", "--git-common-dir"], cwd, git)
    if code != 0 or not common_dir:
        return REFUSED, f"LANE_GUARD REFUSE: cannot resolve git-common-dir in {cwd}"
    grafts_path = os.path.join(os.path.realpath(os.path.join(cwd, common_dir)), "info", "grafts")
    if os.path.exists(grafts_path):
        return REFUSED, (
            f"LANE_GUARD REFUSE: grafts file present at {grafts_path}; parentage cannot be trusted"
        )

    code, parents = _git_handback(["log", "-1", "--format=%P", sha, "--"], cwd, git)
    if code != 0:
        return REFUSED, f"LANE_GUARD REFUSE: cannot resolve head {sha!r} in {cwd}"
    if not parents:
        return REFUSED, (
            f"LANE_GUARD REFUSE: head {sha} has no parent (root/orphan commit); "
            "recover via a fresh branch from the integration ref, not a rebase in place"
        )

    code, merge_base = _git_handback(["merge-base", sha, base], cwd, git)
    if code != 0 or not merge_base:
        return REFUSED, (
            f"LANE_GUARD REFUSE: no merge-base between {sha} and {base!r} "
            "(unrelated history, or base does not resolve)"
        )

    code, roots = _git_handback(["rev-list", "--max-parents=0", f"{base}..{sha}"], cwd, git)
    if code != 0:
        return REFUSED, (
            f"LANE_GUARD REFUSE: cannot check for reachable root commits in {base}..{sha}"
        )
    if roots:
        return REFUSED, (
            f"LANE_GUARD REFUSE: root commit reachable in {base}..{sha} ({roots.splitlines()[0]}); "
            "an unrelated-history merge pulled in a second root"
        )

    code, full = _git_handback(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"], cwd, git)
    code2, ahead = _git_handback(["rev-list", "--count", f"{base}..{sha}"], cwd, git)
    if code != 0 or code2 != 0 or not full.startswith(sha):
        return REFUSED, f"LANE_GUARD REFUSE: cannot resolve {sha} or count commits in {base}..{sha}"
    if ahead == "0":
        return REFUSED, (
            f"LANE_GUARD REFUSE: head {sha} adds no commits over {base}; "
            "nothing was parked (HEAD never moved from the dispatch base)"
        )

    ref = branch if branch.startswith("refs/") else f"refs/heads/{branch}"
    code, tip = _git_handback(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd, git)
    if code != 0 or not tip:
        return REFUSED, f"LANE_GUARD REFUSE: branch {branch!r} does not resolve in {cwd}"
    if tip != full:
        return REFUSED, f"LANE_GUARD REFUSE: tip of {branch!r} is {tip}, which is not the cited sha {full}"

    for path in cites:
        why = _cite_problem(cwd, full, path, artifact_root, git)
        if why:
            return REFUSED, f"LANE_GUARD REFUSE: {why}"

    why = _receipt_problem(cwd, base, full, receipt, deployed, git)
    if why:
        return REFUSED, f"LANE_GUARD REFUSE: {why}"

    return OK, (
        f"LANE_GUARD OK: head {sha} has parent(s) {parents}, "
        f"merge-base with {base} is {merge_base}, no reachable root commits in {base}..{sha}, "
        f"{ahead} new commit(s), tip of {branch} matches, {len(cites)} cited path(s) exist"
    )


def _pid_running(pid):
    """True while `pid` is a live, non-zombie process. Read-only: signal 0 sends nothing."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):  # gone, or a pid no process can have
        return False
    except PermissionError:
        pass  # exists, owned by another user
    try:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True  # no ps: signal 0 said it exists, so it still counts as running
    return bool(stat) and not stat.startswith("Z")


def _port_listening(port):
    """True while something on localhost accepts a TCP connection on `port`."""
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
    except OSError:
        return False
    return True


def _write_progress(path, elapsed, pending):
    """Overwrite `path` with one liveness line: UTC time, elapsed seconds, what is still pending.

    Lets a parent read a long lane's state from a known file instead of waiting on interim notices.
    Write errors are swallowed: progress is advisory and must never fail the wait itself.
    """
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{stamp} waiting {elapsed:.0f}s; pending: {', '.join(pending) or 'none'}\n")
    except OSError:
        pass


def check_wait(pids, ports, files, timeout=300.0, interval=1.0, settle=30.0, progress=None,
               progress_every=900.0):
    """Wait, bounded by `timeout` seconds, until every pid/port/file target is finished (see WAIT MODE).

    A --pid must already be running when this is called, else it is never trusted as "will finish" —
    an unreachable pid (typo, already exited before the wait started) returns COULD_NOT_CHECK naming it
    instead of an instant, wrong OK. A --port must be observed listening at least once within `settle`
    seconds (capped at `timeout`) before "not listening" is trusted as done, for the same reason: a port
    that never once accepted a connection was never confirmed to be the background work at all. --file
    keeps its existing exists/non-empty/stable-size semantics with no alive-at-start check.

    Returns (code, one line): OK when all finished, COULD_NOT_CHECK naming what still runs (or was never
    confirmed alive/listening), REFUSED on bad input. Side-effects: none beyond reading process, socket,
    and file state, plus, when `progress` names a file, overwriting it with one line (`_write_progress`) at
    the first check and then every `progress_every` seconds while anything is pending.
    """
    if not (pids or ports or files):
        return REFUSED, "LANE_GUARD REFUSE: wait needs targets; name at least one --pid, --port, or --file"
    if any(p < 1 for p in pids):
        return REFUSED, "LANE_GUARD REFUSE: --pid must be a positive pid (0 and negatives address process groups)"
    if any(not 1 <= p <= 65535 for p in ports):
        return REFUSED, "LANE_GUARD REFUSE: --port must be 1-65535"
    if not timeout > 0:
        return REFUSED, "LANE_GUARD REFUSE: --timeout must be a positive number of seconds"
    if not settle > 0:
        return REFUSED, "LANE_GUARD REFUSE: --settle must be a positive number of seconds"

    never_alive = [p for p in pids if not _pid_running(p)]
    if never_alive:
        named = ", ".join(f"pid {p}" for p in never_alive)
        return COULD_NOT_CHECK, (f"LANE_GUARD COULD_NOT_CHECK: {named} not observed running at wait start; "
                                  f"a pid that never lived cannot be trusted as 'finished'")

    now = time.monotonic()
    settle_bound = min(settle, timeout)
    settle_deadline = now + settle_bound
    deadline = now + timeout
    sizes = {}
    seen_listening = {p: False for p in ports}
    start, next_progress = now, now
    while True:
        now = time.monotonic()
        pending = [f"pid {p} running" for p in pids if _pid_running(p)]
        for p in ports:
            if _port_listening(p):
                seen_listening[p] = True
                pending.append(f"port {p} listening")
            elif not seen_listening[p] and now < settle_deadline:
                pending.append(f"port {p} not yet observed listening (settle window)")
        for path in files:
            size = os.path.getsize(path) if os.path.isfile(path) else None
            if size is None:
                pending.append(f"file {path} absent")
            elif size == 0:
                pending.append(f"file {path} empty")
            elif sizes.get(path) != size:
                pending.append(f"file {path} still growing")
            sizes[path] = size
        never_listened = [p for p in ports if not seen_listening[p] and now >= settle_deadline]
        if never_listened:
            named = ", ".join(f"port {p}" for p in never_listened)
            return COULD_NOT_CHECK, (f"LANE_GUARD COULD_NOT_CHECK: {named} never observed listening within "
                                      f"{settle_bound:g}s settle window; a port that never once listened cannot "
                                      f"be trusted as 'finished'")
        if progress and pending and now >= next_progress:
            _write_progress(progress, now - start, pending)
            next_progress = now + progress_every
        if not pending:
            done =[f"pid {p}" for p in pids] + [f"port {p}" for p in ports] + [f"file {f}" for f in files]
            return OK, f"LANE_GUARD OK: background work finished ({', '.join(done)})"
        if now >= deadline:
            return COULD_NOT_CHECK, (f"LANE_GUARD COULD_NOT_CHECK: still running after {timeout:g}s: "
                                     f"{', '.join(pending)}; do not hand back until it finishes")
        time.sleep(interval)


def _main_wait(argv):
    parser = argparse.ArgumentParser(
        prog="lane_guard.py wait",
        description="Wait (bounded) for a lane's background work to finish before its handback.",
    )
    parser.add_argument("--pid", type=int, action="append", default=[], help="a process that must exit (repeatable)")
    parser.add_argument("--port", type=int, action="append", default=[],
                        help="a localhost port that must stop listening (repeatable)")
    parser.add_argument("--file", action="append", default=[],
                        help="a result file that must exist, be non-empty, and stop growing (repeatable)")
    parser.add_argument("--timeout", type=float, default=300.0, help="total seconds to wait (default 300)")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between checks (default 1)")
    parser.add_argument("--settle", type=float, default=30.0,
                        help="seconds a --port gets to start listening at least once before 'not listening' "
                             "counts as done, capped at --timeout (default 30)")
    parser.add_argument("--progress", help="file to overwrite with one liveness line while waiting")
    parser.add_argument("--progress-every", type=float, default=900.0,
                        help="seconds between --progress writes (default 900)")
    args = parser.parse_args(argv)
    code, line = check_wait(args.pid, args.port, args.file, args.timeout, max(args.interval, 0.05), args.settle,
                            args.progress, max(args.progress_every, 0.05))
    print(line)
    return code


def _main_handback(argv):
    parser = argparse.ArgumentParser(
        prog="lane_guard.py handback",
        description="Refuse a parentless, unrelated, or unmoved head, a branch tip that is not "
                    "the cited sha, or a cited path that does not exist.",
    )
    parser.add_argument("--sha", required=True, help="the lane's head commit to check")
    parser.add_argument("--base", required=True,
                        help="the integration ref the lane was dispatched from and will land on")
    parser.add_argument("--branch", required=True, help="the lane branch whose tip must equal --sha")
    parser.add_argument("--cite", action="append", default=[],
                        help="a path the handback cites as evidence (repeatable): a file committed at --sha, "
                             "or an absolute path inside --artifact-root")
    parser.add_argument("--artifact-root", help="directory that absolute --cite paths must sit inside")
    parser.add_argument("--receipt", help="delivery receipt file; required when the diff touches UI files "
                        "(needs a `journey: <page> <steps> PASS` line) or with --deployed")
    parser.add_argument("--deployed", action="store_true",
                        help="claim includes a deploy: receipt needs `postdeploy-logs: clean`")
    args = parser.parse_args(argv)
    code, line = check_handback(os.getcwd(), args.sha, args.base, args.branch, args.cite,
                                artifact_root=args.artifact_root, receipt=args.receipt, deployed=args.deployed)
    print(line)
    return code


def hot_files(mine, open_prs, limit=5):
    """Files in `mine` that more than `limit` OTHER open PRs also touch -> {file: count}.

    `open_prs` maps PR id -> iterable of touched paths (stubbed offline; the caller lists open PRs).
    A shared append-only file edited by every PR makes a train conflict after the first lands; use one
    fragment file per entry instead (see changelog.d/). Pure function: no network, no VCS calls.
    """
    counts = {f: sum(f in set(files) for files in open_prs.values()) for f in set(mine)}
    return {f: n for f, n in sorted(counts.items()) if n > limit}


def _main_hotfiles(argv):
    parser = argparse.ArgumentParser(prog="lane_guard.py hotfiles",
                                     description="Warn when this PR touches a file >N other open PRs also touch.")
    parser.add_argument("--prs", required=True, help="JSON file: {pr_id: [paths]} for the other open PRs")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("files", nargs="+", help="paths this PR touches")
    args = parser.parse_args(argv)
    with open(args.prs) as fh:
        hot = hot_files(args.files, json.load(fh), args.limit)
    for f, n in hot.items():
        print(f"LANE_GUARD HOT: {f} also touched by {n} other open PRs; split into one fragment file per entry")
    return 0


_CLOSER_RE = re.compile(r"(?i)\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s*:?\s+(?:(?:[\w.-]+/[\w.-]+)?#\d+|https?://[\w.-]+/[\w.-]+/[\w.-]+/issues/\d+\b)")
_OFF_DEFAULT_RE = re.compile(
    r"(?i):-(?:0|false|off|no)\}|(?:getenv|environ\.get|env\.get)\(\s*[\"']\w+[\"']\s*,\s*[\"']?(?:0|false|off|no)\b"
    r"|\b\w*(?:SHADOW|ENFORCE|ENABLE\w*|FLAG)\w*\s*[:=]\s*[\"']?(?:0|false|off|no)\b[\"']?\s*[,;]?\s*(?:#.*)?$")


_PIPELINE_RE = re.compile(r"^(?:\.github/|\.githooks/|\.claude/hooks/|.*(?:train|hook|ci-gates)[^/]*$)", re.I)
_PROD_LOG_RE = re.compile(r"(?im)^.*\bprod(?:uction)?[- ]run\b.*https?://\S+")


def check_shadow_fix(cwd, base, head, body, git="git"):
    """Refuse a closing keyword (Fixes/Closes/Resolves #N) when the diff adds a flag or env default of 0/false/off,
    or touches pipeline/CI/train/hook paths without 2 `production run: <url>` lines in the body."""
    if not _CLOSER_RE.search(body):
        return OK, "LANE_GUARD OK: shadow-fix: no closing keyword in the PR body"
    rc, out = _git(["diff", "-U0", f"{base}...{head}"], cwd, git)
    if rc:
        return COULD_NOT_CHECK, "LANE_GUARD UNVERIFIED: shadow-fix: git diff failed"
    rc, names = _git(["diff", "--name-only", f"{base}...{head}"], cwd, git)
    if rc:
        return COULD_NOT_CHECK, "LANE_GUARD UNVERIFIED: shadow-fix: git diff --name-only failed"
    hits = [ln[1:].strip() for ln in out.splitlines()
            if ln.startswith("+") and not ln.startswith("+++") and _OFF_DEFAULT_RE.search(ln)]
    pipeline = any(_PIPELINE_RE.match(n) for n in names.splitlines())
    urls = {re.search(r"https?://\S+", m).group(0) for m in _PROD_LOG_RE.findall(body)}
    if (hits or pipeline) and len(urls) < 2:
        why = ("adds a default-off flag (" + hits[0][:80] + ")") if hits else "touches pipeline/CI/train/hook paths"
        return REFUSED, ("LANE_GUARD REFUSE: shadow-fix: the diff " + why + " and the body closes an issue without 2 distinct "
                         "`production run: <log url>` lines; label the issue verify:prod, use `Refs #N` (with an enforce-flip checklist "
                         "for a flag), close after 2 production runs")
    return OK, "LANE_GUARD OK: shadow-fix: no default-off flag added or 2 production runs cited"


def _main_shadow_fix(argv):
    parser = argparse.ArgumentParser(prog="lane_guard.py shadow-fix",
                                     description="Refuse Fixes/Closes/Resolves #N on a diff that adds a default-off flag.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--body-file", required=True, help="file holding the PR body")
    args = parser.parse_args(argv)
    with open(args.body_file, encoding="utf-8") as f:
        code, line = check_shadow_fix(os.getcwd(), args.base, args.head, f.read())
    print(line)
    return code


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw[:1] == ["hotfiles"]:
        return _main_hotfiles(raw[1:])
    if raw[:1] == ["shadow-fix"]:
        return _main_shadow_fix(raw[1:])
    if raw[:1] == ["handback"]:
        return _main_handback(raw[1:])
    if raw[:1] == ["wait"]:
        return _main_wait(raw[1:])
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     epilog="subcommands: {handback,wait,hotfiles,shadow-fix} ... (see: lane_guard.py <subcommand> --help)")
    parser.add_argument("--expect-branch", help="required: refuse unless HEAD is on exactly this branch")
    parser.add_argument("--allow-any-branch", action="store_true",
                        help="waive --expect-branch (non-lane probes only; proves less)")
    parser.add_argument("--default-branch",
                        help="add a default branch name (joins main, master, origin/HEAD, main checkout)")
    parser.add_argument("--allow-unverified", action="store_true",
                        help="owner-only: proceed when the occupancy scan cannot rule out a live foreign "
                             "process (no lsof, no /proc, or a blind scan); never pass this by default")
    parser.add_argument("--selftest", action="store_true", help="prove every refusal fires")
    args = parser.parse_args(raw)
    if args.selftest:
        return _selftest()
    code, line = check(os.getcwd(), args.expect_branch, args.default_branch,
                       allow_any_branch=args.allow_any_branch, allow_unverified=args.allow_unverified)
    if code == OK:
        line += seed_banlist(os.getcwd())
    print(line)
    return code


def _selftest():
    """Build throwaway repos and assert each planted case refuses (or passes)."""
    failures = []
    total = [0]

    def expect(label, result, want_code, want_text):
        total[0] += 1
        code, line = result
        if code != want_code or want_text not in line or "\n" in line:
            failures.append(f"{label}: got ({code}) {line!r}")

    tmp = os.path.realpath(tempfile.mkdtemp(prefix="lane_guard_selftest_"))
    # Stop repository discovery at tmp, so "not a repo" holds even when the
    # temp dir itself sits inside some checkout.
    saved_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
    os.environ["GIT_CEILING_DIRECTORIES"] = tmp
    # The structural cases below (branch/default-branch/git-dir plumbing) are
    # independent of occupancy; stub it to (empty set, "ok") so they do not
    # depend on the host actually having lsof or /proc. The dedicated
    # occupancy cases further down pass their own `occupancy_scanner` and so
    # bypass this stub entirely.
    saved_default_scanner = lane_liveness.foreign_cwd_pids
    lane_liveness.foreign_cwd_pids = lambda root: (set(), "selftest stub: occupancy check disabled")
    try:
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        for args in (
            ["init", "-q"],
            ["symbolic-ref", "HEAD", "refs/heads/main"],
            ["-c", "user.name=Test", "-c", "user.email=test@example.com",
             "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
             "commit", "-q", "--allow-empty", "-m", "seed"],
            ["branch", "lane-a"],
            ["branch", "trunk"],
            ["worktree", "add", "-q", os.path.join(tmp, "wt-lane"), "lane-a"],
            ["worktree", "add", "-q", "--detach", os.path.join(tmp, "wt-detached"), "main"],
        ):
            code, _ = _git(args, repo)
            if code != 0:
                print(f"SELFTEST FAILED: setup git {' '.join(args)} exited {code}")
                return 1
        wt_lane = os.path.join(tmp, "wt-lane")
        wt_detached = os.path.join(tmp, "wt-detached")
        plain = os.path.join(tmp, "not-a-repo")
        os.makedirs(plain)

        lane = "lane-a"
        # --expect-branch is required; only --allow-any-branch waives it.
        expect("no-expect-branch-refused", check(wt_lane), REFUSED, "no --expect-branch")
        expect("allow-any-branch-ok", check(wt_lane, allow_any_branch=True), OK, "LANE_GUARD OK")
        expect("main-checkout-refused", check(repo, expect_branch="main"),
               REFUSED, "not a linked worktree")
        expect("linked-lane-ok", check(wt_lane, expect_branch=lane), OK, "LANE_GUARD OK")
        expect("subdir-of-lane-ok", check(_mkdir(wt_lane, "sub"), expect_branch=lane),
               OK, "LANE_GUARD OK")
        expect("detached-refused", check(wt_detached, expect_branch=lane), REFUSED, "detached")
        expect("expect-branch-mismatch-refused", check(wt_lane, expect_branch="lane-b"),
               REFUSED, "expected 'lane-b'")
        expect("explicit-default-refused",
               check(wt_lane, expect_branch=lane, default_branch=lane),
               REFUSED, "default branch 'lane-a'")
        expect("not-a-repo-refused", check(plain, expect_branch=lane), REFUSED, "git read failed")
        expect("git-refused-refused",
               check(wt_lane, expect_branch=lane, git=os.path.join(tmp, "no-such-git")),
               REFUSED, "git read failed")
        # A git that answers everything except the worktree list: fail closed.
        real_git = shutil.which("git")
        shim = os.path.join(tmp, "git-no-worktree-list")
        with open(shim, "w", encoding="utf-8") as handle:
            handle.write(f'#!/bin/sh\n[ "$1" = worktree ] && exit 1\nexec "{real_git}" "$@"\n')
        os.chmod(shim, 0o755)
        expect("worktree-list-unreadable-refused", check(wt_lane, expect_branch=lane, git=shim),
               REFUSED, "cannot read the worktree list")

        # An inherited GIT_DIR must not redirect the check to another repo.
        saved = os.environ.get("GIT_DIR")
        os.environ["GIT_DIR"] = os.path.join(repo, ".git")
        try:
            expect("inherited-git-dir-ignored", check(wt_lane, expect_branch=lane),
                   OK, "LANE_GUARD OK")
        finally:
            if saved is None:
                os.environ.pop("GIT_DIR", None)
            else:
                os.environ["GIT_DIR"] = saved

        # --- occupancy check (#1116): lane-start refuses when another live
        # process (not this one or its ancestors) has cwd inside the
        # worktree; passes when none does; and refuses rather than silently
        # proceeding when the scan is blind, unless --allow-unverified.
        def _occ_found(_root):
            return {999999}, "stub: foreign pid 999999"

        def _occ_none(_root):
            return set(), "stub: no foreign process"

        def _occ_blind(_root):
            return None, "BLIND (stub: simulated blind occupancy scan)"

        expect("occupancy-foreign-process-refused",
               check(wt_lane, expect_branch=lane, occupancy_scanner=_occ_found),
               REFUSED, "live process(es)")
        expect("occupancy-none-ok",
               check(wt_lane, expect_branch=lane, occupancy_scanner=_occ_none),
               OK, "LANE_GUARD OK")
        expect("occupancy-blind-refused-unverified",
               check(wt_lane, expect_branch=lane, occupancy_scanner=_occ_blind),
               REFUSED, "UNVERIFIED")
        expect("occupancy-blind-allow-unverified-ok",
               check(wt_lane, expect_branch=lane, occupancy_scanner=_occ_blind, allow_unverified=True),
               OK, "UNVERIFIED")

        # Prove the WIRING, not just the parameter: with the real
        # lane_liveness.foreign_cwd_pids restored (no occupancy_scanner
        # override) and a genuine foreign process planted with its cwd inside
        # the worktree, lane-start refuses with no stub anywhere in the loop —
        # this is what closes #1116, not the injectable param alone.
        lane_liveness.foreign_cwd_pids = saved_default_scanner
        foreign = subprocess.Popen(["sleep", "5"], cwd=wt_lane)
        try:
            expect("occupancy-real-wiring-refused", check(wt_lane, expect_branch=lane),
                   REFUSED, "live process(es)")
        finally:
            foreign.terminate()
            foreign.wait(timeout=5)
        lane_liveness.foreign_cwd_pids = lambda root: (set(), "selftest stub: occupancy check disabled")

        # No origin/HEAD, main checkout moved to trunk: main stays default via
        # the always-default names, and a lane force-added onto the main
        # checkout's own branch is refused.
        _git(["checkout", "-q", "trunk"], repo)
        wt_main = os.path.join(tmp, "wt-main")
        wt_trunk = os.path.join(tmp, "wt-trunk")
        _git(["worktree", "add", "-q", wt_main, "main"], repo)
        _git(["worktree", "add", "-q", "--force", wt_trunk, "trunk"], repo)
        expect("always-default-main-refused", check(wt_main, expect_branch="main"),
               REFUSED, "default branch 'main'")
        expect("main-checkout-branch-refused", check(wt_trunk, expect_branch="trunk"),
               REFUSED, "default branch 'trunk'")
        # --default-branch adds to the set; it never un-defaults main.
        expect("explicit-default-adds-not-replaces",
               check(wt_main, expect_branch="main", default_branch="trunk"),
               REFUSED, "default branch 'main'")
        # origin/HEAD's target is default; a stale origin/HEAD (naming trunk)
        # does not make main pass.
        _git(["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/lane-a"], repo)
        expect("origin-head-target-refused", check(wt_lane, expect_branch=lane),
               REFUSED, "default branch 'lane-a'")
        _git(["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk"], repo)
        expect("stale-origin-head-main-refused", check(wt_main, expect_branch="main"),
               REFUSED, "default branch 'main'")
        expect("origin-head-other-lane-ok", check(wt_lane, expect_branch=lane),
               OK, "LANE_GUARD OK")
        # No origin/HEAD and a detached main checkout: the real default is
        # unknown, so refuse unless --default-branch names it.
        _git(["symbolic-ref", "--delete", "refs/remotes/origin/HEAD"], repo)
        _git(["checkout", "-q", "--detach"], repo)
        expect("default-unknown-refused", check(wt_lane, expect_branch=lane),
               REFUSED, "default branch unknown")
        expect("default-unknown-explicit-ok",
               check(wt_lane, expect_branch=lane, default_branch="trunk"),
               OK, "LANE_GUARD OK")

        # --- handback mode: a dedicated repo, independent of the lane-start
        # fixtures above (which end mid-test with a detached main checkout).
        repo2 = os.path.join(tmp, "repo2")
        os.makedirs(repo2)
        commit_args = ["-c", "user.name=Test", "-c", "user.email=test@example.com",
                       "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
                       "commit", "-q", "--allow-empty", "-m"]
        for setup_args in (
            ["init", "-q"],
            ["symbolic-ref", "HEAD", "refs/heads/main"],
            [*commit_args, "base"],
        ):
            code, _ = _git(setup_args, repo2)
            if code != 0:
                print(f"SELFTEST FAILED: setup git {' '.join(setup_args)} exited {code}")
                return 1

        # Normal commit: a real parent on a branch descended from main.
        _git(["checkout", "-q", "-b", "lane-normal"], repo2)
        _git([*commit_args, "lane work"], repo2)
        _, normal_sha = _git(["rev-parse", "HEAD"], repo2)
        expect("handback-normal-ok", check_handback(repo2, normal_sha, "main", branch="lane-normal"),
               OK, "LANE_GUARD OK")

        # Root/orphan commit: no parent at all.
        _git(["checkout", "-q", "--orphan", "lane-orphan"], repo2)
        _git([*commit_args, "orphan root"], repo2)
        _, orphan_sha = _git(["rev-parse", "HEAD"], repo2)
        expect("handback-orphan-refused", check_handback(repo2, orphan_sha, "main", "lane-x"),
               REFUSED, "no parent")

        # Unrelated history: a second independent orphan lineage, never
        # sharing an ancestor with main; its own commit has a parent, so only
        # the merge-base step (not the parent check) can catch this one.
        _git(["checkout", "-q", "--orphan", "lane-unrelated"], repo2)
        _git([*commit_args, "unrelated root"], repo2)
        _git([*commit_args, "unrelated child"], repo2)
        _, unrelated_sha = _git(["rev-parse", "HEAD"], repo2)
        expect("handback-unrelated-refused", check_handback(repo2, unrelated_sha, "main", "lane-x"),
               REFUSED, "no merge-base")

        # A merge that pulls in a second, unrelated root: the merge commit
        # itself has parents and does share a merge-base with main (via
        # lane-normal), so only the reachable-root scan (not the parent or
        # merge-base check) can catch this one.
        _git(["checkout", "-q", "-b", "lane-merged", "lane-normal"], repo2)
        code, _ = _git(
            ["-c", "user.name=Test", "-c", "user.email=test@example.com",
             "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
             "merge", "-q", "--no-edit", "--allow-unrelated-histories", "lane-unrelated"],
            repo2,
        )
        if code != 0:
            print(f"SELFTEST FAILED: setup unrelated-histories merge exited {code}")
            return 1
        _, merged_sha = _git(["rev-parse", "HEAD"], repo2)
        expect("handback-merged-root-refused", check_handback(repo2, merged_sha, "main", "lane-x"),
               REFUSED, "root commit reachable")

        # Shallow clone: truncated history can't prove ancestry either way, so
        # this refuses before any orphan/unrelated-history diagnosis runs —
        # even passing a sha/base pair that would otherwise pass clean.
        shallow = os.path.join(tmp, "repo2-shallow")
        code, _ = _git(["clone", "-q", "--depth", "1", f"file://{repo2}", shallow], tmp)
        if code != 0:
            print(f"SELFTEST FAILED: setup shallow clone exited {code}")
            return 1
        expect("handback-shallow-refused", check_handback(shallow, normal_sha, "main", "lane-x"),
               REFUSED, "shallow clone")

        # Grafts file: parentage can be rewritten underneath these checks, so
        # refuse rather than trust it. Clean the file up immediately after so
        # it doesn't leak into the tests below.
        _, common_dir = _git(["rev-parse", "--git-common-dir"], repo2)
        grafts_dir = os.path.join(os.path.realpath(os.path.join(repo2, common_dir)), "info")
        os.makedirs(grafts_dir, exist_ok=True)
        grafts_path = os.path.join(grafts_dir, "grafts")
        with open(grafts_path, "w", encoding="utf-8") as handle:
            handle.write(f"{normal_sha}\n")
        try:
            expect("handback-grafts-refused", check_handback(repo2, normal_sha, "main", "lane-x"),
                   REFUSED, "grafts")
        finally:
            os.remove(grafts_path)

        # rev-list itself failing (not just returning empty) must refuse too —
        # a command error is never read as "no roots found".
        real_git = shutil.which("git")
        revlist_shim = os.path.join(tmp, "git-no-revlist")
        with open(revlist_shim, "w", encoding="utf-8") as handle:
            handle.write(f'#!/bin/sh\n[ "$1" = rev-list ] && exit 1\nexec "{real_git}" "$@"\n')
        os.chmod(revlist_shim, 0o755)
        expect(
            "handback-revlist-error-refused",
            check_handback(repo2, normal_sha, "main", "lane-x", git=revlist_shim),
            REFUSED, "cannot check for reachable root commits",
        )

        # Unresolvable refs: neither a bad sha nor a bad base is allowed to
        # pass by falling through — fail closed on both.
        expect("handback-unresolvable-sha-refused",
               check_handback(repo2, "0" * 40, "main", "lane-x"), REFUSED, "cannot resolve head")
        expect("handback-unresolvable-base-refused",
               check_handback(repo2, normal_sha, "no-such-branch", "lane-x"), REFUSED, "no merge-base")
        expect("handback-missing-args-refused",
               check_handback(repo2, "", "main"), REFUSED, "needs --sha, --base and --branch")
        expect("handback-missing-branch-refused",
               check_handback(repo2, normal_sha, "main", branch=""), REFUSED,
               "needs --sha, --base and --branch")

        # Parked-claim verification (field failure: a lane reported "parked
        # <head>" while HEAD never moved, or cited evidence files that did not
        # exist). A sha already reachable from the dispatch base parked nothing.
        # Here the lane was dispatched from lane-normal's tip and never moved.
        expect("handback-unmoved-head-refused",
               check_handback(repo2, normal_sha, "lane-normal", branch="lane-normal"), REFUSED,
               "adds no commits")
        # The branch tip must be the cited sha: a lane that commits again after
        # citing, or cites a sha from another branch, is refused.
        _git(["checkout", "-q", "-b", "lane-moved", "lane-normal"], repo2)
        _git([*commit_args, "later work"], repo2)
        expect("handback-branch-tip-mismatch-refused",
               check_handback(repo2, normal_sha, "main", branch="lane-moved"), REFUSED,
               "is not the cited sha")
        expect("handback-branch-missing-refused",
               check_handback(repo2, normal_sha, "main", branch="no-such-lane"), REFUSED,
               "does not resolve")
        # Cited paths: a file in the tree at the cited sha passes; an on-disk
        # artifact passes; a path in neither is refused.
        _git(["checkout", "-q", "-b", "lane-cite", "main"], repo2)
        with open(os.path.join(repo2, "evidence.txt"), "w", encoding="utf-8") as handle:
            handle.write("proof\n")
        _git(["add", "evidence.txt"], repo2)
        _git([*commit_args, "add evidence"], repo2)
        _, cite_sha = _git(["rev-parse", "HEAD"], repo2)
        artifacts = _mkdir(tmp, "artifacts")
        artifact = os.path.join(artifacts, "composite.png")
        with open(artifact, "w", encoding="utf-8") as handle:
            handle.write("png\n")

        def cite(*paths, root=artifacts):
            return check_handback(repo2, cite_sha, "main", branch="lane-cite", cites=list(paths),
                                  artifact_root=root)
        expect("handback-cited-paths-ok", cite("evidence.txt", artifact), OK, "LANE_GUARD OK")
        expect("handback-cited-path-missing-refused",
               cite("evidence.txt", os.path.join(artifacts, "no-such-composite.png")), REFUSED, "cited path")
        # A relative cite must be a blob committed at the sha: an uncommitted
        # file that exists on disk, a directory (a tree), an empty path, and a
        # `..` escape are all refused.
        with open(os.path.join(repo2, "uncommitted.txt"), "w", encoding="utf-8") as handle:
            handle.write("not in the commit\n")
        expect("handback-cite-uncommitted-on-disk-refused", cite("uncommitted.txt"), REFUSED,
               "is not a file committed at")
        os.makedirs(os.path.join(repo2, "sub"), exist_ok=True)
        expect("handback-cite-tree-refused", cite("."), REFUSED, "is not a file committed at")
        expect("handback-cite-empty-refused", cite(""), REFUSED, "empty or '..'")
        expect("handback-cite-dotdot-refused", cite("sub/../evidence.txt"), REFUSED, "empty or '..'")
        # An absolute cite counts only under an explicit --artifact-root.
        expect("handback-cite-absolute-without-root-refused", cite(artifact, root=None), REFUSED,
               "needs --artifact-root")
        outside = os.path.join(tmp, "outside.png")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("png\n")
        expect("handback-cite-absolute-outside-root-refused", cite(outside), REFUSED,
               "outside --artifact-root")
        # --sha must be a hex commit id that the resolved sha starts with, not
        # a ref name that happens to resolve (a branch name would always match
        # its own tip).
        expect("handback-sha-ref-name-refused",
               check_handback(repo2, "lane-cite", "main", branch="lane-cite"), REFUSED,
               "must be a 7-40 character lowercase hex sha")
        expect("handback-sha-short-prefix-ok",
               check_handback(repo2, cite_sha[:12], "main", branch="lane-cite"), OK, "LANE_GUARD OK")
    finally:
        lane_liveness.foreign_cwd_pids = saved_default_scanner
        if saved_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = saved_ceiling
        shutil.rmtree(tmp, ignore_errors=True)

    _selftest_wait(expect)
    passed = total[0] - len(failures)
    if failures:
        print(f"SELFTEST FAILED ({passed}/{total[0]}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"SELFTEST OK: {passed}/{total[0]}")
    return 0


def _selftest_wait(expect):
    """`wait` cases on real processes, a real listening port, and real files (each well under a second)."""
    import socket
    import threading

    tmp = tempfile.mkdtemp(prefix="lane_guard_wait_")
    try:
        expect("wait-no-target-refused", check_wait([], [], [], timeout=1), REFUSED, "name at least one")
        expect("wait-pid-zero-refused", check_wait([0], [], [], timeout=1), REFUSED, "positive pid")
        expect("wait-bad-settle-refused", check_wait([], [], [os.path.join(tmp, "x")], timeout=1, settle=0),
               REFUSED, "--settle")
        dead = subprocess.Popen(["true"])
        dead.wait()  # exited and reaped before the wait ever starts: never trusted as "will finish"
        expect("wait-pid-never-alive-could-not-check", check_wait([dead.pid], [], [], timeout=1),
               COULD_NOT_CHECK, f"pid {dead.pid} not observed running at wait start")
        short = subprocess.Popen(["sleep", "0.2"])  # never reaped here: its zombie must still count as finished
        expect("wait-pid-exits-ok", check_wait([short.pid], [], [], timeout=5, interval=0.05), OK, "LANE_GUARD OK")
        longer = subprocess.Popen(["sleep", "30"])
        try:
            expect("wait-pid-timeout-names-it", check_wait([longer.pid], [], [], timeout=0.3, interval=0.05),
                   COULD_NOT_CHECK, f"pid {longer.pid} running")
        finally:
            longer.kill()
            longer.wait()
            short.wait()
        note = os.path.join(tmp, ".lane-progress")
        busy = subprocess.Popen(["sleep", "30"])
        try:
            check_wait([busy.pid], [], [], timeout=0.3, interval=0.05, progress=note, progress_every=0.1)
            with open(note, encoding="utf-8") as handle:
                text = handle.read()
            ok = text.count("\n") == 1 and f"pid {busy.pid} running" in text and "waiting" in text
            expect("wait-progress-file-one-line", (OK if ok else REFUSED, text.rstrip("\n")), OK, "")
        finally:
            busy.kill()
            busy.wait()
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        never_bound_port = free.getsockname()[1]
        free.close()  # port is free again; nothing ever listens on it during the wait below
        expect("wait-port-never-listens-could-not-check",
               check_wait([], [never_bound_port], [], timeout=0.3, interval=0.05, settle=0.1),
               COULD_NOT_CHECK, f"port {never_bound_port} never observed listening")

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        try:
            expect("wait-port-timeout-names-it", check_wait([], [port], [], timeout=0.3, interval=0.05),
                   COULD_NOT_CHECK, f"port {port} listening")
            threading.Timer(0.2, server.close).start()
            expect("wait-port-closes-ok", check_wait([], [port], [], timeout=5, interval=0.05), OK, "LANE_GUARD OK")
        finally:
            server.close()
        out = os.path.join(tmp, "results.xml")
        expect("wait-file-absent-timeout", check_wait([], [], [out], timeout=0.3, interval=0.05),
               COULD_NOT_CHECK, "absent")
        open(out, "w", encoding="utf-8").close()  # a shell redirect creates the file empty, long before the result
        expect("wait-file-empty-timeout", check_wait([], [], [out], timeout=0.3, interval=0.05),
               COULD_NOT_CHECK, "empty")
        os.remove(out)

        def write_result():
            with open(out, "w", encoding="utf-8") as handle:
                handle.write("<testsuite/>\n")

        threading.Timer(0.2, write_result).start()
        expect("wait-file-appears-ok", check_wait([], [], [out], timeout=5, interval=0.05), OK, "LANE_GUARD OK")
        expect("wait-bad-timeout-refused", check_wait([], [], [out], timeout=0), REFUSED, "--timeout")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _mkdir(parent, name):
    path = os.path.join(parent, name)
    os.makedirs(path, exist_ok=True)
    return path


if __name__ == "__main__":
    sys.exit(main())
