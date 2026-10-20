#!/usr/bin/env python3
"""lane_liveness.py — report a background lane's liveness by positive evidence, never a kill verdict.

WHY THIS EXISTS (the failure it closes, #1070)
-----------------------------------------------
Under heavy multi-agent load, a commit can take minutes and a gate run longer
still: a lane that has produced nothing new in an hour is routinely SLOW, not
STUCK. An orchestrator that reads "elapsed time, no PR yet" as evidence of a
hang kills the lane, discovers near the end that it was almost done, and pays
for the stop, the resume, and the re-work — repeatedly, on the same false
inference. This script replaces that inference with a report built only from
POSITIVE, checkable signals, so "no PR yet" is never mistaken for "dead."

THE RULE
--------
Report exactly one of four states for a worktree `P`, each backed by the
evidence lines that produced it:

  ALIVE       a process is running for this lane (an explicit --pid that
              answers, or a process whose current working directory resolves
              inside `P`) AND that lane shows recent product activity: a file
              under `P` (excluding `.git`) modified within `--quiet-minutes`,
              the git index/refs modified within that window, or measured CPU
              time moving on the lane's process(es) across a short sample.

  QUIET       a live process with no recent product signal (long silent work:
              compiling, a slow test suite, a network wait), or recent product
              activity with no process currently found (a lane that just
              finished a step and is between processes). QUIET is a prompt to
              look closer, never a kill signal.

  UNVERIFIED  no process and no recent activity were found, BUT a detector
              was blind: the cwd-scan could not run or did not succeed (no
              `lsof` and no `/proc`, an lsof error or timeout, or a scan that
              could not see this script's own process), or the file walk hit
              an unreadable directory. Absence of evidence from a blind
              detector is not evidence of absence, so this is never DEAD.

  DEAD        the cwd-scan RAN AND SUCCEEDED and found no process with its cwd
              in `P` (and --pid, if given, does not answer) AND the file walk
              completed without error AND no product activity (file mtime, or
              git index/refs mtime) is younger than `--quiet-minutes`.

DEAD is the only state that can justify reaping a lane, and even then it is
evidence, not a mandate: killing a lane is a destructive, shared-state action
(`verification-handback.md`: closing or deleting shared state needs evidence,
not presumption), so the orchestrator confirms before it acts. This script
NEVER prints a kill recommendation — DEAD is a report, not an instruction.

EVIDENCE SOURCES
-----------------
1. Process alive: `--pid` answers `os.kill(pid, 0)` (exists, any state,
   including a zombie the OS hasn't reaped — a known limitation, noted below),
   OR a process whose cwd resolves inside `P` — found via `lsof -a -d cwd -F
   pn` when the `lsof` binary is available, else (Linux only) by reading
   `/proc/<pid>/cwd` for every numeric entry in `/proc`. A scan counts as
   SUCCEEDED only if it ran without error or timeout AND it saw this script's
   own process (a scan that cannot see its own caller cannot be trusted to
   have seen the lane's). Otherwise the scan is BLIND, which rules out DEAD.
2. Newest file mtime under `P`, walking the tree and excluding any `.git`
   directory (a lane's own git operations must not look like "no activity").
3. git index/refs mtime: resolves the real git-dir for `P` (`git rev-parse
   --git-dir`, so a linked worktree's per-worktree gitdir is used, not the
   common one) and takes the newest mtime among `HEAD`, `index`, `refs/`
   (recursively) and `packed-refs`, whichever exist. A `git` failure (not a
   repository, binary missing) just drops this signal; it does not error the
   whole run.
4. Child CPU time delta: for every pid found in (1), reads cumulative CPU
   time via `ps -o time= -p <pid>` twice, `--sample-seconds` apart (default
   0.5s), and reports whether it moved. Both `ps` TIME shapes parse: procps
   `[dd-]hh:mm:ss` and macOS `mm:ss.cc` (minutes unbounded). A pid that
   exits between samples, or that `ps` cannot see, contributes no delta
   (never misread as "moved").

LIMITATIONS (stated, not hidden)
---------------------------------
- A zombie process still answers `os.kill(pid, 0)`: this script does not
  distinguish "running" from "exited but unreaped" for an explicit --pid. The
  cwd-scan and CPU-delta checks are unaffected (a zombie has no cwd entry and
  no moving CPU time), so a zombie alone does not produce a false ALIVE.
- The cwd-scan needs `lsof` or `/proc` (Linux); on a host with neither, an
  explicit `--pid` is the only process evidence available, and a lane with no
  answering --pid and no recent activity reports UNVERIFIED, never DEAD.
- The own-process canary proves the scan can see this user's processes, not
  another user's; a lane running as a different user may be invisible.
- This tool answers "is this lane alive," never "is this lane's OUTPUT
  correct" — a live, busy process can still be building the wrong thing.

USAGE
-----
  lane_liveness.py --worktree PATH [--pid N] [--quiet-minutes M] [--sample-seconds S]
  lane_liveness.py --selftest

EXIT CODES
----------
  0  ALIVE
  1  QUIET
  2  error: a usage error (unknown flag, missing --worktree) or a --worktree
     that is not a directory — never a verdict
  3  UNVERIFIED
  4  DEAD (a caller may branch on it, but it is not authorization to kill;
     see THE RULE above)
`--help` exits 0 and prints no LANE_LIVENESS line; parse the verdict line,
not the exit code alone, when a flag could be malformed.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

ALIVE, QUIET, ERROR, UNVERIFIED, DEAD = 0, 1, 2, 3, 4
_VERDICT_NAME = {ALIVE: "ALIVE", QUIET: "QUIET", UNVERIFIED: "UNVERIFIED", DEAD: "DEAD"}
_TRAILER = {
    ALIVE: "positive signal found; no action implied.",
    QUIET: "no recent product signal — look closer, this is not a kill signal.",
    UNVERIFIED: "a detector was blind — liveness unknown, never a kill signal.",
    DEAD: "no process and no recent activity — evidence only, not a kill verdict.",
}
DEFAULT_QUIET_MINUTES = 20.0
DEFAULT_SAMPLE_SECONDS = 0.5


def _pid_alive(pid: int) -> bool:
    """True iff a process with this pid exists (see the zombie caveat above)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal
    except OSError:
        return False
    return True


def _cwd_pids_via_lsof(root: str):
    """pids whose cwd resolves inside `root`, via `lsof -a -d cwd -F pn`.

    Returns (pids, None) on a scan that succeeded, or (None, reason) when the
    scan is blind: lsof erroring, timing out, or not seeing this process's own
    pid (the canary that the scan saw this user's processes at all).
    """
    try:
        # cwd="/" so lsof never lists itself as a process inside the lane.
        proc = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "-F", "pn"],
            capture_output=True, text=True, timeout=10, cwd="/",
        )
    except subprocess.TimeoutExpired:
        return None, "lsof timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"lsof failed to run ({exc.__class__.__name__})"
    if proc.returncode not in (0, 1):  # lsof exits 1 when some processes are unreadable
        return None, f"lsof exited {proc.returncode}"
    pids = set()
    seen = set()
    pid = None
    for line in proc.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            try:
                pid = int(value)
            except ValueError:
                pid = None
                continue
            seen.add(pid)
        elif tag == "n" and pid is not None and same_tree(value, root):
            pids.add(pid)
    if os.getpid() not in seen:
        return None, "lsof ran but did not see this script's own process"
    return pids, None


def _cwd_pids_via_proc(root: str):
    """Linux fallback: read /proc/<pid>/cwd. Same (pids, None) / (None, reason) contract as lsof."""
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None, "/proc unavailable"
    pids = set()
    saw_self = False
    for name in entries:
        if not name.isdigit():
            continue
        try:
            cwd = os.readlink(f"/proc/{name}/cwd")
        except OSError:
            continue
        if int(name) == os.getpid():
            saw_self = True
        if same_tree(cwd, root):
            pids.add(int(name))
    if not saw_self:
        return None, "/proc listed but this script's own cwd was unreadable"
    return pids, None


def _inside(candidate: str, root: str) -> bool:
    try:
        c = os.path.realpath(candidate)
        r = os.path.realpath(root)
    except OSError:
        return False
    return c == r or c.startswith(r + os.sep)


def _top(p: str):
    """Nearest ancestor of `p` with a `.git` (dir or worktree file), or None. A submodule's `.git` file
    (gitdir under `/modules/`) belongs to its parent checkout, so the walk continues past it."""
    p = os.path.realpath(p)
    while True:
        g = os.path.join(p, ".git")
        if os.path.isdir(g):
            return p
        if os.path.isfile(g):
            try:
                gd = open(g).read()
            except OSError:
                gd = ""
            if "/modules/" not in gd or "/worktrees/" in gd:
                return p
        if p == os.path.dirname(p):
            return None
        p = os.path.dirname(p)


def same_tree(candidate: str, root: str) -> bool:
    """`candidate` is inside `root` and in the same git worktree, so a lane worktree nested under the main
    checkout does not count as the main checkout's. Outside any git tree: plain containment."""
    if not _inside(candidate, root):
        return False
    top = _top(root)
    return top is None or _top(candidate) == top


def cwd_pids(root: str):
    """Processes whose cwd is inside `root`; lsof first, /proc as the fallback.

    Returns (pids, detail): `pids` is a set when a scan succeeded (possibly
    empty — a real "none found"), or None when every available scan was blind;
    `detail` names the backend used, or why each one was blind. This script's
    own process is never counted as the lane's, even when run from inside it.
    """
    import shutil

    reasons = []
    if shutil.which("lsof"):
        found, why = _cwd_pids_via_lsof(root)
        if found is not None:
            return found - {os.getpid()}, "lsof ok"
        reasons.append(why)
    else:
        reasons.append("lsof not installed")
    found, why = _cwd_pids_via_proc(root)
    if found is not None:
        return found - {os.getpid()}, "/proc ok"
    reasons.append(why)
    return None, "BLIND (" + "; ".join(reasons) + ")"


def process_ancestors(pid=None, ps_bin="ps"):
    """Return `{pid}` plus every ancestor pid reachable by climbing `ps -o ppid=`.

    Used to exclude the CALLING agent's own process tree — not just its own
    pid — from an occupancy scan: the shell/orchestrator that invoked the scan
    can itself have its cwd inside the worktree being checked, and only the
    ancestor chain (never a child) is that caller. `ps_bin` is injectable so a
    test can supply a broken binary and prove the walk fails closed rather than
    hangs or fabricates a parent. Bounded to 10_000 hops as a cycle guard; any
    `ps` failure, a blank/unparseable ppid, or reaching pid <= 1 stops the walk
    and returns whatever ancestors were already found — it never invents one.
    """
    if pid is None:
        pid = os.getpid()
    seen = {pid}
    current = pid
    for _ in range(10_000):
        try:
            proc = subprocess.run([ps_bin, "-o", "ppid=", "-p", str(current)],
                                   capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            break
        if proc.returncode != 0:
            break
        text = proc.stdout.strip()
        if not text:
            break
        try:
            ppid = int(text)
        except ValueError:
            break
        if ppid <= 1 or ppid in seen:
            break
        seen.add(ppid)
        current = ppid
    return seen


def foreign_cwd_pids(root: str, exclude=None):
    """Like `cwd_pids`, but also drops this process's own ancestor chain.

    `lane_guard.py`'s lane-start occupancy check calls this instead of
    `cwd_pids` directly: the calling agent's own shell/orchestrator can have
    its cwd inside the worktree being checked, and without this exclusion
    every lane-start would find itself and refuse. `exclude` adds pids beyond
    the ancestor chain (a test's own planted pid); both sets are removed from
    a real scan. Same (pids_or_None, detail) contract as `cwd_pids` — a blind
    scan returns None and must never be read as "no foreign process found."
    """
    pids, detail = cwd_pids(root)
    if pids is None:
        return None, detail
    drop = process_ancestors() | (set(exclude) if exclude else set())
    return pids - drop, detail


def newest_mtime_excluding_git(root: str):
    """Newest mtime under `root`, skipping any `.git` directory.

    Returns (newest_or_None, walk_errors): `walk_errors` counts directories the
    walk could not read; non-zero means a recent file may be hidden, so the
    caller must not treat "nothing recent" as proven.
    """
    newest = None
    errors = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=errors.append):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                mtime = os.lstat(path).st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest, len(errors)


def git_state_mtime(root: str):
    """Newest mtime among HEAD/index/refs/packed-refs in `root`'s real git-dir; None on any git failure."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=root,
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    git_dir = proc.stdout.strip()
    if not git_dir:
        return None
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(root, git_dir)
    newest = None
    for rel in ("HEAD", "index", "packed-refs"):
        path = os.path.join(git_dir, rel)
        try:
            mtime = os.lstat(path).st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    refs_dir = os.path.join(git_dir, "refs")
    for dirpath, _dirnames, filenames in os.walk(refs_dir):
        for name in filenames:
            try:
                mtime = os.lstat(os.path.join(dirpath, name)).st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


_PS_TIME_RE = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$")


def _parse_ps_time(value: str):
    """Parse ps's `-o time=` into seconds (float); None if unparseable.

    Accepts procps `[dd-][hh:]mm:ss` and macOS `mm:ss.cc` (minutes may exceed
    59, e.g. `277:49.40`), plus `h:mm:ss.cc`.
    """
    value = value.strip()
    m = _PS_TIME_RE.match(value)
    if not m:
        return None
    days, hours, minutes, seconds = m.groups()
    total = int(minutes) * 60 + float(seconds)
    if hours:
        total += int(hours) * 3600
    if days:
        total += int(days) * 86400
    return total


def _ps_cpu_seconds(pid: int):
    try:
        proc = subprocess.run(
            ["ps", "-o", "time=", "-p", str(pid)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return _parse_ps_time(proc.stdout)


def cpu_delta(pids, sample_seconds: float) -> bool:
    """True iff cumulative CPU time moved for any of `pids` across `sample_seconds`."""
    if not pids:
        return False
    before = {pid: _ps_cpu_seconds(pid) for pid in pids}
    time.sleep(max(sample_seconds, 0.0))
    for pid, was in before.items():
        if was is None:
            continue
        now = _ps_cpu_seconds(pid)
        if now is not None and now > was:
            return True
    return False


def evaluate(worktree: str, pid=None, quiet_minutes: float = DEFAULT_QUIET_MINUTES,
             sample_seconds: float = DEFAULT_SAMPLE_SECONDS, scanner=None):
    """Return (verdict, [evidence lines]). Pure aside from the filesystem/process reads.

    `scanner` (default `cwd_pids`) maps a root to (pids_or_None, detail); None
    means the scan was blind, which can yield UNVERIFIED but never DEAD.
    """
    root = os.path.realpath(worktree)
    evidence = [f"worktree: {root}"]

    scanned, scan_detail = (scanner or cwd_pids)(root)
    scan_ok = scanned is not None
    found_pids = set(scanned or ())
    evidence.append(f"process detection: {scan_detail}")
    pid_note = "n/a"
    if pid is not None:
        alive = _pid_alive(pid)
        pid_note = "alive" if alive else "not found"
        if alive:
            found_pids.add(pid)
    evidence.append(f"--pid {pid}: {pid_note}" if pid is not None else "--pid: not given")
    if not scan_ok:
        evidence.append("cwd-scan: blind — cannot rule out a process with cwd inside worktree")
    elif scanned:
        evidence.append(f"cwd-scan: {sorted(scanned)} process(es) with cwd inside worktree")
    else:
        evidence.append("cwd-scan: no process found with cwd inside worktree")

    now = time.time()
    quiet_seconds = quiet_minutes * 60.0

    file_mtime, walk_errors = newest_mtime_excluding_git(root)
    file_age = (now - file_mtime) if file_mtime is not None else None
    evidence.append(
        f"newest file mtime (excl .git): {file_age:.0f}s ago" if file_age is not None
        else "newest file mtime (excl .git): no files found"
    )
    if walk_errors:
        evidence.append(f"file walk: {walk_errors} unreadable director(ies) — a recent file may be hidden")

    git_mtime = git_state_mtime(root)
    git_age = (now - git_mtime) if git_mtime is not None else None
    evidence.append(
        f"git index/refs mtime: {git_age:.0f}s ago" if git_age is not None
        else "git index/refs mtime: unavailable"
    )

    has_cpu_delta = cpu_delta(found_pids, sample_seconds) if found_pids else False
    if found_pids:
        evidence.append(f"CPU time delta over {sample_seconds}s sample: {'moved' if has_cpu_delta else 'no change'}")
    else:
        evidence.append(f"CPU time delta over {sample_seconds}s sample: skipped (no process found)")

    process_alive = bool(found_pids)
    recent_activity = (
        (file_age is not None and file_age <= quiet_seconds)
        or (git_age is not None and git_age <= quiet_seconds)
        or has_cpu_delta
    )

    if process_alive and recent_activity:
        verdict = ALIVE
    elif process_alive or recent_activity:
        verdict = QUIET
    elif scan_ok and not walk_errors:
        # DEAD only when every detector ran, succeeded, and found nothing.
        verdict = DEAD
    else:
        verdict = UNVERIFIED
    return verdict, evidence


def _format_report(verdict: int, evidence) -> str:
    lines = [f"LANE_LIVENESS {_VERDICT_NAME[verdict]}: {_TRAILER[verdict]}"]
    lines.extend(f"  - {line}" for line in evidence)
    return "\n".join(lines)


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors exit ERROR (2), never a verdict code."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"LANE_LIVENESS ERROR: {message}", file=sys.stderr)
        sys.exit(ERROR)


def main(argv=None) -> int:
    parser = _Parser(description=__doc__.splitlines()[0])
    parser.add_argument("--worktree", help="path to the lane's worktree")
    parser.add_argument("--pid", type=int, default=None, help="explicit pid to check, in addition to the cwd scan")
    parser.add_argument("--quiet-minutes", type=float, default=DEFAULT_QUIET_MINUTES,
                        help=f"activity window in minutes (default {DEFAULT_QUIET_MINUTES})")
    parser.add_argument("--sample-seconds", type=float, default=DEFAULT_SAMPLE_SECONDS,
                        help=f"CPU-delta sample window in seconds (default {DEFAULT_SAMPLE_SECONDS})")
    parser.add_argument("--selftest", action="store_true", help="prove each verdict and exit code fires, offline")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.worktree:
        parser.error("--worktree is required (or use --selftest)")
    if not os.path.isdir(args.worktree):
        print(f"LANE_LIVENESS ERROR: not a directory: {args.worktree}", file=sys.stderr)
        return ERROR

    verdict, evidence = evaluate(args.worktree, args.pid, args.quiet_minutes, args.sample_seconds)
    print(_format_report(verdict, evidence))
    return verdict


def _selftest() -> int:
    import shutil
    import tempfile

    failures = []
    total = [0]

    def expect(label, got, want):
        total[0] += 1
        if got != want:
            failures.append(f"{label}: got {_VERDICT_NAME.get(got, got)!r}, want {_VERDICT_NAME.get(want, want)!r}")

    tmp = tempfile.mkdtemp(prefix="lane_liveness_selftest_")
    old = time.time() - 3600

    def blind(_root):
        return None, "BLIND (selftest: simulated detector failure)"

    def stale_lane(name):
        lane_dir = os.path.join(tmp, name)
        os.makedirs(lane_dir)
        path = os.path.join(lane_dir, "output.txt")
        with open(path, "w") as fh:
            fh.write("stale\n")
        os.utime(path, (old, old))
        return lane_dir

    def run_main(*args, env=None, cwd=None):
        return subprocess.run([sys.executable, os.path.abspath(__file__), *args],
                              capture_output=True, text=True, env=env, cwd=cwd, timeout=60)

    try:
        # ALIVE: a live child process with cwd inside the worktree, plus a
        # just-written file inside the quiet window, found via --pid.
        lane = os.path.join(tmp, "lane-alive")
        os.makedirs(lane)
        with open(os.path.join(lane, "output.txt"), "w") as fh:
            fh.write("progress\n")
        child = subprocess.Popen(["sleep", "5"], cwd=lane)
        try:
            verdict, _ = evaluate(lane, pid=child.pid, quiet_minutes=5.0, sample_seconds=0.05)
            expect("alive-process-and-recent-file", verdict, ALIVE)
        finally:
            child.terminate()
            child.wait(timeout=5)

        # ALIVE via the cwd-scan alone (no --pid): the scan itself must find
        # the child whose cwd is inside the worktree, and say so.
        lane_scan = os.path.join(tmp, "lane-scan")
        os.makedirs(lane_scan)
        with open(os.path.join(lane_scan, "output.txt"), "w") as fh:
            fh.write("progress\n")
        child_scan = subprocess.Popen(["sleep", "5"], cwd=lane_scan)
        try:
            verdict, evidence = evaluate(lane_scan, pid=None, quiet_minutes=5.0, sample_seconds=0.05)
            expect("cwd-scan-without-pid-is-alive", verdict, ALIVE)
            scan_lines = [line for line in evidence if line.startswith("cwd-scan:")]
            total[0] += 1
            if not (scan_lines and str(child_scan.pid) in scan_lines[0]):
                failures.append(f"cwd-scan-names-child-pid: {child_scan.pid} not in {scan_lines!r}")
            total[0] += 1
            if not any(line.endswith(" ok") for line in evidence if line.startswith("process detection:")):
                failures.append(f"cwd-scan-reports-backend-ok: {evidence!r}")
        finally:
            child_scan.terminate()
            child_scan.wait(timeout=5)

        # foreign_cwd_pids: finds a genuinely unrelated process whose cwd is
        # inside the worktree, but the `exclude` param removes a planted pid
        # from the result — the same mechanism lane_guard.py relies on to drop
        # its caller's own ancestor chain (this selftest process's real
        # ancestors are not inside `lane_foreign`, so they cannot mask this
        # case; `exclude` isolates the removal logic on its own).
        lane_foreign = os.path.join(tmp, "lane-foreign")
        os.makedirs(lane_foreign)
        child_foreign = subprocess.Popen(["sleep", "5"], cwd=lane_foreign)
        try:
            found, detail = foreign_cwd_pids(lane_foreign)
            total[0] += 1
            if found is None or child_foreign.pid not in found:
                failures.append(f"foreign-cwd-pids-finds-unrelated-process: {found!r} ({detail})")
            found_excluded, _ = foreign_cwd_pids(lane_foreign, exclude={child_foreign.pid})
            total[0] += 1
            if found_excluded is None or child_foreign.pid in found_excluded:
                failures.append(f"foreign-cwd-pids-exclude-param-removes-pid: {found_excluded!r}")
        finally:
            child_foreign.terminate()
            child_foreign.wait(timeout=5)

        # foreign_cwd_pids stays blind (never "no foreign process") when the
        # underlying cwd_pids scan itself is blind — proven by swapping the
        # module-level cwd_pids for a stub that reports BLIND, then restoring it.
        lane_blind_occ = os.path.join(tmp, "lane-blind-occ")
        os.makedirs(lane_blind_occ)
        _module = sys.modules[__name__]
        _orig_cwd_pids = _module.cwd_pids
        _module.cwd_pids = lambda root: (None, "BLIND (selftest: simulated cwd_pids failure)")
        try:
            found_blind, detail_blind = foreign_cwd_pids(lane_blind_occ)
            total[0] += 1
            if found_blind is not None:
                failures.append(f"foreign-cwd-pids-blind-stays-blind: {found_blind!r} ({detail_blind})")
        finally:
            _module.cwd_pids = _orig_cwd_pids

        # process_ancestors: always includes the caller's own pid, and a
        # broken `ps_bin` fails closed (returns just the seed pid) instead of
        # hanging or fabricating a parent.
        me = process_ancestors()
        total[0] += 1
        if os.getpid() not in me:
            failures.append(f"process-ancestors-includes-self: {me!r}")
        broken = process_ancestors(ps_bin=os.path.join(tmp, "no-such-ps"))
        total[0] += 1
        if broken != {os.getpid()}:
            failures.append(f"process-ancestors-broken-ps-fails-closed: {broken!r}")

        # QUIET: a live process, but no recent product signal — quiet-minutes
        # set to 0 so even a just-written file does not count as "recent",
        # and the process (a plain sleep) never moves CPU time.
        lane_quiet = os.path.join(tmp, "lane-quiet")
        os.makedirs(lane_quiet)
        with open(os.path.join(lane_quiet, "output.txt"), "w") as fh:
            fh.write("old\n")
        child2 = subprocess.Popen(["sleep", "5"], cwd=lane_quiet)
        try:
            verdict, _ = evaluate(lane_quiet, pid=child2.pid, quiet_minutes=0.0, sample_seconds=0.05)
            expect("alive-process-no-recent-signal-is-quiet", verdict, QUIET)
        finally:
            child2.terminate()
            child2.wait(timeout=5)

        # DEAD: the scan ran and succeeded, no process (a pid that has
        # already exited and been reaped), and the only file is backdated
        # well past the quiet window.
        lane_dead = stale_lane("lane-dead")
        exited = subprocess.Popen(["true"])
        exited.wait()
        expect("no-process-no-recent-activity-is-dead",
               evaluate(lane_dead, pid=exited.pid, quiet_minutes=1.0, sample_seconds=0.05)[0], DEAD)

        # QUIET: recent file activity but no process found at all.
        lane_between = os.path.join(tmp, "lane-between")
        os.makedirs(lane_between)
        with open(os.path.join(lane_between, "output.txt"), "w") as fh:
            fh.write("just written\n")
        expect("recent-activity-no-process-is-quiet",
               evaluate(lane_between, pid=None, quiet_minutes=5.0, sample_seconds=0.05)[0], QUIET)

        # Nonexistent pid never mistaken for alive.
        lane_badpid = stale_lane("lane-badpid")
        huge_pid = 2**30  # astronomically unlikely to exist
        expect("nonexistent-pid-is-dead",
               evaluate(lane_badpid, pid=huge_pid, quiet_minutes=1.0, sample_seconds=0.05)[0], DEAD)

        # A blind process detector never yields DEAD, with or without --pid.
        lane_blind = stale_lane("lane-blind")
        verdict, evidence = evaluate(lane_blind, pid=None, quiet_minutes=1.0,
                                     sample_seconds=0.05, scanner=blind)
        expect("blind-scan-no-activity-is-unverified", verdict, UNVERIFIED)
        total[0] += 1
        if not any("BLIND" in line for line in evidence):
            failures.append(f"blind-scan-evidence-names-blind: {evidence!r}")
        expect("blind-scan-dead-pid-is-unverified",
               evaluate(lane_blind, pid=huge_pid, quiet_minutes=1.0,
                        sample_seconds=0.05, scanner=blind)[0], UNVERIFIED)

        # An unreadable directory hides possible activity: never DEAD.
        if os.geteuid() != 0:  # root reads mode-000 dirs, so the case cannot be staged
            lane_walk = stale_lane("lane-walk")
            locked = os.path.join(lane_walk, "locked")
            os.makedirs(locked)
            os.chmod(locked, 0)
            try:
                expect("walk-error-no-activity-is-unverified",
                       evaluate(lane_walk, pid=None, quiet_minutes=1.0, sample_seconds=0.05)[0],
                       UNVERIFIED)
            finally:
                os.chmod(locked, 0o700)

        # End to end with lsof off PATH: where /proc is also absent (macOS)
        # the scan is blind -> UNVERIFIED; where /proc exists the fallback
        # scan succeeds -> DEAD.
        lane_nolsof = stale_lane("lane-nolsof")
        proc = run_main("--worktree", lane_nolsof, "--quiet-minutes", "1", "--sample-seconds", "0.05",
                        env={"PATH": os.path.join(tmp, "empty-path")})
        want_code = DEAD if os.path.isdir("/proc/self") else UNVERIFIED
        total[0] += 1
        if proc.returncode != want_code:
            failures.append(f"no-lsof-end-to-end: exit {proc.returncode}, want {want_code}: {proc.stdout}{proc.stderr}")

        # Exit codes: verdicts and errors never collide.
        total[0] += 1
        if len({ALIVE, QUIET, ERROR, UNVERIFIED, DEAD}) != 5:
            failures.append("exit-codes-distinct: verdict/error codes collide")
        for label, args in (
            ("missing-worktree", ()),
            ("unknown-flag", ("--worktree", tmp, "--no-such-flag")),
            ("non-int-pid", ("--worktree", tmp, "--pid", "abc")),
            ("not-a-directory", ("--worktree", os.path.join(tmp, "missing"))),
        ):
            proc = run_main(*args)
            total[0] += 1
            if proc.returncode != ERROR or "LANE_LIVENESS ERROR" not in proc.stderr:
                failures.append(f"usage-error-{label}: exit {proc.returncode}, want {ERROR}: {proc.stderr!r}")
        # Run from INSIDE the lane: the script's own process must not count.
        proc = run_main("--worktree", ".", "--quiet-minutes", "1", "--sample-seconds", "0.05",
                        cwd=lane_dead)
        total[0] += 1
        if proc.returncode != DEAD or "LANE_LIVENESS DEAD" not in proc.stdout:
            failures.append(f"main-dead-exit-4-own-process-excluded: exit {proc.returncode}: "
                            f"{proc.stdout}{proc.stderr}")

        # _parse_ps_time covers procps and macOS shapes and rejects garbage.
        cases = [("01:02", 62), ("1:01:02", 3662), ("2-01:01:02", 176462),
                 ("0:00.03", 0.03), ("277:49.40", 16669.4), ("1:02:03.50", 3723.5),
                 ("garbage", None), ("1:2:3:4", None)]
        for text, want in cases:
            got = _parse_ps_time(text)
            total[0] += 1
            if (got is None) != (want is None) or (want is not None and abs(got - want) > 1e-6):
                failures.append(f"parse-ps-time({text!r}): got {got!r}, want {want!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = total[0] - len(failures)
    if failures:
        print(f"SELFTEST FAILED ({passed}/{total[0]}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"SELFTEST OK: {passed}/{total[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
