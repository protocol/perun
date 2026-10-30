#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=fail-closed test selection plus a cross-lane serial run lock, review=2027-01-30
"""serial_gate.py — fail-closed test selection + a cross-lane serial run lock.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
N parallel agent lanes share one repo. If each lane runs the FULL test suite
on every push, the lanes self-DoS the host (CPU/RAM contention, flaky timeouts
that look like real failures). The fix — path-scoped test selection ("only
run the tests near what changed") — introduces a worse failure if it is
wrong: a bad glob silently SKIPS the tests that would have caught a
regression, and the change ships untested with a green check mark. So the
selector itself must be fail-closed (any input it cannot classify with
confidence runs the FULL suite, never "nothing to run, pass") and it must be
testable (`--selftest` pins every fail-closed branch with a real assertion).

Serializing the shared-state parts of a multi-lane push (a migration, a
generated file, the integration branch) needs a real cross-process lock. This
uses `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on a lock file — a KERNEL advisory
lock, not a hand-rolled one: the `flock(2)` syscall exists on both macOS and
Linux (the common "macOS has no flock" claim is about the `flock(1)` CLI
binary used to wrap a shell command, which macOS indeed lacks — the Python
`fcntl.flock()` syscall binding is unaffected and has always worked on both).
A kernel lock has one property no user-space "stale lock" scheme can fully
replicate: the kernel releases it the instant the holding process's last file
descriptor closes, for ANY reason the process ends — clean exit, uncaught
exception, or `SIGKILL`. There is nothing to reclaim and nothing to age out.

TWO SUBCOMMANDS
----------------
select --map <map.tsv> [--base REF --head REF | --changed-file PATH ...]
    Print selected test targets, one per line, OR the single line `FULL`
    meaning "run the whole suite." Exit 0 on a resolved selection (mapped
    or FULL). Exit 2 — plus a reason on stderr — when the input itself could
    not be resolved (a bad ref, a malformed or missing map): FULL is still
    printed to stdout (a caller that only checks stdout still runs the full
    suite), but the caller's script SHOULD treat exit 2 as "investigate,"
    not silently continue.

    MAP FILE FORMAT (tab-separated; one row per line):
      <glob>\t<test target>       — changed path matching <glob> selects <test target>
      !full\t<glob>                — changed path matching <glob> forces FULL
      # comment or blank line      — ignored
    The map file's OWN path is always FULL-forcing, whether or not it also
    appears as a `!full` row — a change to the routing table itself is by
    definition a change no fixed row can vouch for. "Own path" is compared
    both as given and relative to the repository top level (`git rev-parse
    --show-toplevel`, run in --repo or the cwd), so an absolute or
    cwd-relative --map still matches the repo-relative path git reports.

    The diff is read with `git diff --name-only --no-renames`: a rename is
    reported as its deleted OLD path plus its added NEW path, so moving a
    file out of a `!full` or mapped area can never hide the old path.

    GLOB SEMANTICS (exactly what is implemented, not "glob-like"): each
    changed path is normalized to a repo-root-relative POSIX path (backslashes
    turned to `/`, no leading `./`), then matched against each pattern with
    `fnmatch.fnmatchcase`. `fnmatch` has no path-separator concept: a bare
    `*` already matches across `/` the same way `**` conventionally does, `?`
    matches exactly one character, and `[seq]`/`[!seq]` match a character
    class — literally, per Python's `fnmatch` module. `**` is accepted and
    behaves identically to a single `*` (both translate through the same
    "match anything" rule); there is no directory-scoped single-`*`.

    FAIL-CLOSED RULES, in order:
      (a) map missing / unreadable / malformed (bad row shape)   -> FULL, exit 2
      (b) unresolvable ref / git error resolving the diff        -> FULL, exit 2
      (c) empty diff (nothing changed)                           -> FULL, exit 0
      (d) any changed path matches NO row                        -> FULL, exit 0
      (e) any changed path matches a `!full` glob, or IS the map -> FULL, exit 0
      (f) otherwise: union of every matched row's target(s), deduped, sorted

run --lock-dir DIR [--timeout SECONDS] [--slots N] [--retry K --backoff S --retry-on REGEX] -- <cmd...>
    Serialize <cmd...> across lanes with a kernel advisory lock:
    `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on the file `DIR/lock` (DIR is
    created if missing). A waiter polls with bounded exponential backoff
    (capped, jittered) until it acquires the lock or --timeout elapses
    (default 120s) — on timeout, exits 124 and NEVER runs <cmd...> unlocked.
    Once acquired, the SAME fd is truncated and rewritten with an
    informational owner record (pid, host, UTC acquire time) for a human
    inspecting the lock file; this record is never read back by the tool and
    never consulted for correctness — only the flock decides who holds the
    lock. The lock is released (and the fd closed) in `finally` and on
    SIGTERM/SIGINT; the OS additionally guarantees release on any other
    process death, including SIGKILL, because a dead process cannot hold an
    open file descriptor. The child's own exit code is propagated. There is
    no staleness window, no age-based reclaim, and no lock file to "clean up
    by hand": a lock that looks held IS held, for as long as its holder's
    process is alive, however long that is — NO STALE-LOCK TAKEOVER, here or
    at any slot below: nothing ages out, nothing is adopted from a plain
    `run` (only `--singleton`, above, ever adopts, and only its own kind).

    --slots N: an N-slot semaphore instead of one lock — N independent flock
    files (`DIR/lock.0` .. `DIR/lock.N-1`; N=1, the default, is exactly the
    single `DIR/lock` file above, unchanged). A caller takes whichever slot
    is free first, so up to N callers run at once and caller N+1 queues with
    the same bounded, jittered backoff and --timeout/124 semantics as a
    single lock (#1127: cap the heavy tier at N concurrent instead of
    serializing it to 1 or leaving it uncapped). Each slot is released the
    same way a single lock is — its holder exiting, including SIGKILL — so
    there is nothing to age out per slot either.
    ONE LOCK GUARDS ONE RESOURCE: --slots/--lock-dir here guards only the
    resource its caller names (e.g. a push-queue slot). A "finish" step that
    also needs a second, unrelated resource (e.g. a fixed local port for an
    evidence-capture tool) must NOT run that second thing inside this lock's
    critical section — that couples two independent resources onto one
    semaphore and serializes every caller of either (#1159). Give evidence
    capture its own pool (a rotating port range or a second, separately
    sized `--lock-dir`/`--slots`), not this one.

    --retry K --backoff S --retry-on REGEX: retry the WHOLE acquire+run+
    release cycle up to K more times (bounded: at most K+1 attempts, ever)
    when an attempt exits nonzero AND its captured stdout+stderr matches
    REGEX — never on a plain nonzero exit that doesn't match, so a lane's
    real test/lint failure is reported at once instead of retried into a
    fresh resource-exhaustion storm (#1127's failure mode: N lanes each
    retrying a transient error amplify the very shortage that caused it).
    Each retry waits an exponentially growing, jittered backoff (`S * 2^n`,
    capped) before the next attempt. `--retry-on` is required whenever
    `--retry` > 0 — an unconditional retry-on-any-failure is refused
    (exit 2), since that is exactly the amplifying loop this closes.

run --singleton --lock-dir DIR [--build-id ID] -- <helper cmd...>
    Make a long-lived helper (a watchdog, a static server) a singleton across
    sessions, so "start the helper" is idempotent however many sessions call
    it (#1078). One non-blocking try of the same flock: if it is free, fork
    a small SUPERVISOR process that keeps the only lock fd and starts the
    helper WITHOUT it (the fd is close-on-exec and never passed), then
    propagate the helper's exit code. So the lock lives exactly as long as
    the helper: it survives SIGKILL of this wrapper (the supervisor lives on),
    and it is released the moment the helper exits even if the helper left a
    backgrounded grandchild behind (a grandchild that inherited the fd would
    otherwise hold the lock with no recorded process alive). Accepted gap:
    SIGKILL of the supervisor itself releases the lock while the helper may
    still run; nothing portable can tie a lock to an arbitrary program's
    lifetime without handing that program the fd.
    If it is held, never wait and never start a twin: read the holder's
    record, then exit 0 with `adopted`, or refuse with exit 75
    (NOT_ADOPTED, EX_TEMPFAIL from sysexits.h) and one marker line on stdout:
      `SERIAL_GATE: STALE_HOLDER`  --build-id is given and the live holder's
                                   recorded build id differs (it can still be
                                   serving stale code);
      `SERIAL_GATE: ORPHAN_HOLDER` the lock is held but the record names no
                                   live process: its `pid` is dead, or alive
                                   with a different start time than recorded
                                   (pid reuse), or the record is unreadable or
                                   has no start time. Some process outside
                                   the record holds the lock ("orphan holds
                                   lock"); it is never adopted.
    The marker, not the number alone, identifies a refusal: a helper may
    itself exit 75. A holder is reported, never killed: stop it only if it is
    yours. --timeout is ignored. No pidfile check-then-write (a race) and no
    `pgrep -f <name>` match (it can match the caller's own shell and exit
    with zero instances running): only the kernel lock decides who holds it;
    the record's pid plus start time decide only whether to trust the record.

    PLATFORM SCOPE: POSIX advisory locks (`flock`) apply per open-file-table
    entry on a single host's local filesystem. This is not a distributed
    lock: it does not work over NFS or other network filesystems, and it says
    nothing about processes on a different host. Use it only for lanes on one
    shared host talking to one shared local disk. `fcntl` does not exist on
    Windows; `run` on a platform without it fails closed (exit 2, <cmd...>
    never runs) rather than silently running unlocked.

USAGE
-----
  serial_gate.py select --map map.tsv --base origin/main --head HEAD
  serial_gate.py select --map map.tsv --changed-file src/foo.py
  serial_gate.py run --lock-dir /tmp/x.lock -- pytest -k foo
  serial_gate.py run --singleton --lock-dir /tmp/watchdog.lock --build-id "$(git rev-parse HEAD)" -- ./watchdog.sh
  serial_gate.py --selftest
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import posixpath
import random
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

try:
    import fcntl  # POSIX only — absent on Windows.
except ImportError:  # pragma: no cover — exercised only on non-POSIX hosts
    fcntl = None  # type: ignore[assignment]

OK = 0
USAGE_ERROR = 2
LOCK_TIMEOUT = 124
LOCK_ERROR = 1
# --singleton refusal (stale build or orphan holder): EX_TEMPFAIL from
# sysexits.h, so it cannot be mistaken for a small helper exit code. A
# helper can still exit 75 itself; the marker line on stdout disambiguates.
STALE_HOLDER = 75
STALE_MARKER = "SERIAL_GATE: STALE_HOLDER"
ORPHAN_MARKER = "SERIAL_GATE: ORPHAN_HOLDER"

FULL = "FULL"

DEFAULT_LOCK_TIMEOUT = 120.0
_POLL_START = 0.05
_POLL_CAP = 1.0
_POLL_BACKOFF = 1.6
_ADOPT_READ_TRIES = 20  # x 0.1s: time for a just-started holder to write its record
_LOCK_FREED = -1  # internal: the record never verified, but the lock is free again; retry the start once
try:  # a waiter prints a queue line this often (seconds); PERUN_QUEUE_NOTE_SECS overrides it
    QUEUE_NOTE_SECS = float(os.environ.get("PERUN_QUEUE_NOTE_SECS", "120"))
except ValueError:
    QUEUE_NOTE_SECS = 120.0
if not 0 < QUEUE_NOTE_SECS < float("inf"):  # 0, negative, nan, inf: fall back
    QUEUE_NOTE_SECS = 120.0
_RETRY_BACKOFF_CAP = 30.0  # ceiling on --retry's per-attempt backoff (#1127: bounded, never unbounded)


# --------------------------------------------------------------------------
# select
# --------------------------------------------------------------------------


class MapError(Exception):
    """Map file missing, unreadable, or malformed. Always forces FULL."""


def _normalize_path(path: str) -> str:
    """Repo-root-relative POSIX form used for every glob comparison.

    Backslashes become `/`, a leading `./` is stripped, and the result is
    NOT resolved against the filesystem (a changed path from `git diff` may
    no longer exist at HEAD, e.g. a deletion — this must still match).
    """
    p = path.replace("\\", "/")
    p = posixpath.normpath(p)
    if p.startswith("./"):
        p = p[2:]
    return p


def parse_map(map_path: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse the TSV map. Returns (rows, full_globs).

    `rows` is `[(glob, target), ...]` in file order. `full_globs` is every
    glob from a `!full` row. Raises `MapError` — never returns a partial or
    best-effort result — on: missing file, unreadable file, or any
    non-comment/non-blank line that is not exactly two tab-separated,
    non-empty fields. A malformed map is a routing-table failure, and a
    routing-table failure must be loud, not silently partially applied.
    """
    if not map_path or not os.path.isfile(map_path):
        raise MapError(f"map file not found: {map_path!r}")
    try:
        with open(map_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        raise MapError(f"map file unreadable: {map_path!r} ({exc})") from exc

    rows: list[tuple[str, str]] = []
    full_globs: list[str] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n").rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
            raise MapError(
                f"malformed map row at {map_path}:{lineno}: expected "
                f"'<glob>\\t<target>', got {line!r}"
            )
        left, right = fields[0].strip(), fields[1].strip()
        if left == "!full":
            full_globs.append(right)
        else:
            rows.append((left, right))
    return rows, full_globs


def _git_diff_paths(base: str, head: str, repo_dir: str | None) -> list[str]:
    """Return changed paths between two refs. Raises `MapError` on any git
    failure (bad ref, not a repo, etc.) so the caller forces FULL + exit 2.
    """
    cmd = ["git"]
    if repo_dir:
        cmd += ["-C", repo_dir]
    # --no-renames: a rename must surface BOTH its old and new path. With
    # rename detection on (git's porcelain default), only the new path is
    # printed, so moving a file out of a `!full`/mapped area would silently
    # drop the old path from selection — a fail-open.
    cmd += ["diff", "--name-only", "--no-renames", base, head]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        raise MapError(f"git invocation failed: {exc}") from exc
    if proc.returncode != 0:
        raise MapError(
            f"git diff --name-only --no-renames {base} {head} failed (exit "
            f"{proc.returncode}): {proc.stderr.strip()}"
        )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _map_self_paths(map_path: str, repo_dir: str | None) -> set[str]:
    """Every normalized form under which the map file itself may appear in
    the changed-path list.

    Always includes the --map argument as given. Additionally includes the
    map's path relative to the repository top level (resolved via
    `git rev-parse --show-toplevel` in `repo_dir`, or the cwd), because git
    and `--changed-file` report repo-relative paths while --map may be
    absolute or relative to a different cwd. Both sides are `realpath`-ed so
    symlinked temp dirs (e.g. macOS /var -> /private/var) compare equal. If
    the top level cannot be resolved, or the map lies outside it, only the
    as-given form is used (no guess).
    """
    selves = {_normalize_path(map_path)}
    cmd = ["git"]
    if repo_dir:
        cmd += ["-C", repo_dir]
    cmd += ["rev-parse", "--show-toplevel"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return selves
    top = proc.stdout.strip()
    if proc.returncode != 0 or not top:
        return selves
    try:
        rel = os.path.relpath(os.path.realpath(map_path), os.path.realpath(top))
    except ValueError:  # e.g. different drives on Windows: not inside the repo
        return selves
    rel = _normalize_path(rel)
    if rel != ".." and not rel.startswith("../"):
        selves.add(rel)
    return selves


def select_targets(
    map_path: str,
    changed_files: list[str] | None = None,
    base: str | None = None,
    head: str | None = None,
    repo_dir: str | None = None,
) -> tuple[int, list[str]]:
    """Resolve one selection. Returns `(exit_code, lines_to_print)`.

    `lines_to_print` is either `["FULL"]` or the sorted, deduped target
    list. Every fail-closed rule in the module docstring is implemented
    here, in the documented order, so a caller reading this function top to
    bottom sees the exact precedence.
    """
    try:
        rows, full_globs = parse_map(map_path)
    except MapError as exc:
        print(f"serial_gate: {exc}", file=sys.stderr)
        return USAGE_ERROR, [FULL]

    if changed_files is not None:
        changed = [_normalize_path(p) for p in changed_files]
    else:
        if not base or not head:
            print(
                "serial_gate: select requires --changed-file or both --base and --head",
                file=sys.stderr,
            )
            return USAGE_ERROR, [FULL]
        try:
            changed = [_normalize_path(p) for p in _git_diff_paths(base, head, repo_dir)]
        except MapError as exc:
            print(f"serial_gate: {exc}", file=sys.stderr)
            return USAGE_ERROR, [FULL]

    if not changed:
        return OK, [FULL]

    map_selves = _map_self_paths(map_path, repo_dir)
    force_full_globs = list(full_globs)

    for path in changed:
        if path in map_selves:
            return OK, [FULL]
        if any(fnmatch.fnmatchcase(path, g) for g in force_full_globs):
            return OK, [FULL]

    targets: set[str] = set()
    for path in changed:
        matched_any = False
        for glob, target in rows:
            if fnmatch.fnmatchcase(path, glob):
                matched_any = True
                targets.add(target)
        if not matched_any:
            return OK, [FULL]

    return OK, sorted(targets)


# --------------------------------------------------------------------------
# run — cross-lane serial lock (kernel advisory lock via flock)
# --------------------------------------------------------------------------


class LockTimeout(Exception):
    """Raised internally when acquisition exceeds --timeout."""


def _lock_file_path(lock_dir: str) -> str:
    return os.path.join(lock_dir, "lock")


def _holder(fd: int) -> str:
    """The lock file's informational owner record ("" when unreadable); never decides who holds the lock."""
    try:
        return os.pread(fd, 300, 0).decode(errors="replace")
    except OSError:
        return ""


def _queue_note(label: str, start: float, last: float, holder: str = "") -> float:
    """Print one stderr line ("queued Ns on <label>; holder <owner record>") once QUEUE_NOTE_SECS have passed since `last`;
    return the new `last`. A waiter on a long job is never silent. The poll sleeps up to ~1.1s past the check, so the
    threshold is lowered by that slack (at most half the interval) to keep the gap between lines <= QUEUE_NOTE_SECS."""
    now = time.monotonic()
    if now - last < QUEUE_NOTE_SECS - min(1.2, QUEUE_NOTE_SECS / 2):
        return last
    print(f"serial_gate: queued {int(now - start)}s on {label}; holder {holder or 'unknown'}", file=sys.stderr, flush=True)
    return now


def _slot_lock_path(lock_dir: str, index: int, slots: int) -> str:
    """Lock-file path for one semaphore slot. `slots<=1` is exactly
    `_lock_file_path` (the single `lock` file) — no behavior or filename
    change for the pre-existing single-lock case; `slots>1` uses
    `lock.<index>`.
    """
    if slots <= 1:
        return _lock_file_path(lock_dir)
    return os.path.join(lock_dir, f"lock.{index}")


def acquire_slot(lock_dir: str, slots: int, timeout: float) -> tuple[int, int]:
    """Block until this process holds an exclusive kernel advisory lock on
    ANY ONE of `slots` independent lock files — an N-slot semaphore built
    from N `flock`s, not one lock reused: whichever slot is free first is
    taken, so up to `slots` callers hold a slot at once and caller N+1
    queues. `slots<=1` uses the same single `lock` file as `acquire_lock`
    (identical behavior, not a special case). Same bounded, jittered
    exponential backoff and `timeout`/`LockTimeout` semantics as
    `acquire_lock`. Returns `(fd, index)`; release with `release_lock(fd)`
    exactly as for the single-lock case. No stale-lock takeover: a slot is
    freed only by its holder's fd closing (normal exit, SIGTERM/SIGINT via
    `run_locked`, or the kernel on SIGKILL) — nothing here ages a slot out
    or adopts one from another process.
    """
    assert fcntl is not None, "acquire_slot requires fcntl (POSIX only)"
    os.makedirs(lock_dir, exist_ok=True)
    slots = max(1, slots)
    start = last = time.monotonic()
    deadline = start + timeout
    delay = _POLL_START
    holder = ""
    while True:
        for index in range(slots):
            fd = os.open(_slot_lock_path(lock_dir, index, slots), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd, index
            except BlockingIOError:
                holder = _holder(fd)  # the last busy slot's owner, for the queue line
                os.close(fd)
                continue
            except OSError:
                os.close(fd)
                raise
        if time.monotonic() >= deadline:
            raise LockTimeout(f"timed out after {timeout}s waiting for a free slot (0..{slots - 1}): {lock_dir}")
        last = _queue_note(lock_dir, start, last, holder)
        time.sleep(min(delay, _POLL_CAP) + random.uniform(0, delay * 0.1))
        delay = min(delay * _POLL_BACKOFF, _POLL_CAP)


def _slots_all_free(lock_dir: str, slots: int) -> bool:
    """True iff every one of `slots` slot lock files is acquirable (and is
    immediately released again) right now — proof all slots are free.
    """
    for index in range(slots):
        try:
            fd = os.open(_slot_lock_path(lock_dir, index, slots), os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        finally:
            os.close(fd)
    return True


def acquire_lock(lock_dir: str, timeout: float) -> int:
    """Block until this process holds an exclusive kernel advisory lock.

    Opens (creating if needed) `<lock_dir>/lock` and polls
    `fcntl.flock(fd, LOCK_EX | LOCK_NB)` with bounded, jittered exponential
    backoff until it succeeds or `timeout` elapses. Returns the open file
    descriptor: that fd IS the lock. The caller must keep it open for
    exactly as long as it wants to hold the lock, and release it (see
    `release_lock`) to let a waiter through — or simply let the process die,
    which the kernel treats identically.

    Raises `LockTimeout` once `timeout` elapses without acquiring, closing
    the fd first; the caller must not run its command in that case. Raises
    `OSError` on any other failure opening or locking the file (e.g. a
    permissions error) — a fatal condition distinct from "someone else holds
    it," which callers should treat as an error, not a normal contention
    path.
    """
    assert fcntl is not None, "acquire_lock requires fcntl (POSIX only)"
    os.makedirs(lock_dir, exist_ok=True)
    fd = os.open(_lock_file_path(lock_dir), os.O_RDWR | os.O_CREAT, 0o644)
    start = last = time.monotonic()
    deadline = start + timeout
    delay = _POLL_START
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            pass  # held by another process right now — keep polling
        except OSError:
            os.close(fd)
            raise

        if time.monotonic() >= deadline:
            os.close(fd)
            raise LockTimeout(f"timed out after {timeout}s waiting for lock: {lock_dir}")
        last = _queue_note(lock_dir, start, last, _holder(fd))

        time.sleep(min(delay, _POLL_CAP) + random.uniform(0, delay * 0.1))
        delay = min(delay * _POLL_BACKOFF, _POLL_CAP)


def _write_owner_info(fd: int, extra: dict | None = None) -> None:
    """Best-effort, human-readable record of who holds the lock right now.

    Truncates and rewrites the SAME fd that holds the flock with this
    process's pid, host, and UTC acquire time (plus `extra`, which
    `--singleton` uses for `pid_start`, `child_pid`, and `build_id`), so a
    human looking at the lock file mid-run can see who has it. Plain `run`
    never reads it back; `--singleton` reads it only to decide whether the
    record can be trusted (pid alive with the recorded start time) and to
    compare the holder's build id when adopting — never to decide who holds
    the lock, which only the flock decides. A failure to write is swallowed:
    it cannot affect whether the lock is held (an unwritten record makes a
    peer report an orphan holder, never adopt).
    """
    owner = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_utc": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps(owner).encode("utf-8"))
    except OSError:
        pass


def release_lock(fd: int) -> None:
    """Release the flock on `fd` and close it. Never raises."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _run_locked_once(lock_dir: str, timeout: float, cmd: list[str], slots: int, capture: bool) -> tuple[int, str]:
    """One acquire(-a-slot)+run+release cycle. Returns `(exit_code, output)`;
    `output` is `cmd`'s combined stdout+stderr when `capture` is true (also
    echoed to this process's real stdout/stderr so nothing is silently
    swallowed), else `""` (the normal, streaming, non-retry path). Shared
    body behind both `run_locked` and `run_locked_with_retry` — one lock/
    release/signal implementation, not two.
    """
    if fcntl is None:
        print(
            "serial_gate: fcntl is unavailable on this platform (e.g. "
            "Windows) — this lock is POSIX-only; refusing to run unlocked",
            file=sys.stderr,
        )
        return USAGE_ERROR, ""

    held: dict[str, int | None] = {"fd": None}

    def _on_signal(signum, _frame):
        raise SystemExit(128 + signum)

    old_term = signal.signal(signal.SIGTERM, _on_signal)
    old_int = signal.signal(signal.SIGINT, _on_signal)
    try:
        try:
            if slots <= 1:
                held["fd"] = acquire_lock(lock_dir, timeout)
            else:
                held["fd"], _ = acquire_slot(lock_dir, slots, timeout)
        except LockTimeout as exc:
            print(f"serial_gate: {exc}", file=sys.stderr)
            return LOCK_TIMEOUT, ""
        except OSError as exc:
            print(f"serial_gate: lock acquisition failed: {exc}", file=sys.stderr)
            return LOCK_ERROR, ""
        _write_owner_info(held["fd"])
        if not capture:
            return subprocess.run(cmd).returncode, ""
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        if held["fd"] is not None:
            release_lock(held["fd"])
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def run_locked(lock_dir: str, timeout: float, cmd: list[str], slots: int = 1) -> int:
    """Acquire the lock (or, with `slots` > 1, any free semaphore slot), run
    `cmd`, release, and return `cmd`'s exit code.

    Fails closed with `LOCK_ERROR`/2-family behavior and never runs `cmd` if
    `fcntl` is unavailable (Windows has no `fcntl` module — this lock is
    POSIX-only) or if the lock file itself cannot be opened/locked for a
    reason other than contention. A SIGTERM/SIGINT while waiting or while
    the child runs still releases the lock: the handler raises `SystemExit`,
    which unwinds through the `finally` in `_run_locked_once` exactly like
    any other exception. Any OTHER process death (including SIGKILL)
    releases the lock without any handler running at all, because the
    kernel closes the dead process's file descriptors.
    """
    rc, _ = _run_locked_once(lock_dir, timeout, cmd, slots, capture=False)
    return rc


def run_locked_with_retry(
    lock_dir: str, timeout: float, cmd: list[str], slots: int, retry: int, backoff: float, retry_on: str
) -> int:
    """Like `run_locked`, but retries the WHOLE acquire+run+release cycle up
    to `retry` more times (bounded: at most `retry + 1` attempts, ever) when
    an attempt exits nonzero AND its captured stdout+stderr matches the
    `retry_on` regex — never on a plain nonzero exit that doesn't match, so
    a lane's real test/lint failure is returned at once instead of retried
    into a fresh resource-exhaustion storm (#1127). Each retry waits an
    exponentially growing, jittered backoff (`backoff * 2**attempt`, capped
    at `_RETRY_BACKOFF_CAP`, +10% jitter) before the next attempt — the same
    shape as the lock's own poll backoff, applied at the whole-command grain.
    """
    pattern = re.compile(retry_on)
    attempt = 0
    while True:
        rc, output = _run_locked_once(lock_dir, timeout, cmd, slots, capture=True)
        if rc == 0 or attempt >= retry or not pattern.search(output):
            return rc
        delay = min(backoff * (2**attempt), _RETRY_BACKOFF_CAP)
        time.sleep(delay + random.uniform(0, delay * 0.1))
        attempt += 1


def _pid_alive(pid: int) -> bool:
    """True iff `pid` names a live process (another user's counts as live)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _proc_start(pid: int) -> str | None:
    """An opaque start-time token for `pid`, or None when it cannot be read.

    Two readings of the same live process compare equal; a different process
    that later reuses the pid gets a different token. Linux: field 22
    (`starttime`, clock ticks since boot) of `/proc/<pid>/stat`, read after
    the last `)` so a command name holding spaces or parentheses cannot shift
    the fields. Elsewhere (macOS has no /proc): `ps -o lstart= -p <pid>` under
    the C locale, one-second resolution — a pid reused within the same second
    is the residual risk. Side-effects: reads /proc or runs `ps`.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        return "proc:" + fields[19]  # fields[0] is field 3 (state), so field 22 is index 19
    except (OSError, IndexError):
        pass
    try:
        proc = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=5, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = " ".join(proc.stdout.split())
    return f"ps:{stamp}" if proc.returncode == 0 and stamp else None


def _read_holder(lock_dir: str) -> dict | None:
    """The holder's record, or None unless it names the process holding the lock.

    Trusted only when its `pid` is a live process whose start time equals the
    recorded `pid_start`: a dead pid is a previous holder's leftover (the file
    outlives the lock), a live pid with another start time is an unrelated
    process that reused the number, and a record without a start time cannot
    be verified. Side-effects: reads the lock file, may run `ps`.
    """
    try:
        with open(_lock_file_path(lock_dir), encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    pid, start = rec.get("pid"), rec.get("pid_start")
    if not (isinstance(pid, int) and pid > 0 and isinstance(start, str) and start and _pid_alive(pid)):
        return None
    return rec if _proc_start(pid) == start else None


def _lock_is_free(lock_dir: str) -> bool:
    """One non-blocking probe: True iff nobody holds the lock right now (released again at once)."""
    try:
        fd = os.open(_lock_file_path(lock_dir), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    finally:
        os.close(fd)  # closing the only fd on this open file description drops a lock just taken
    return True


def _refuse(marker: str, message: str) -> int:
    """Print the machine-readable marker line (stdout) and the reason (stderr); return STALE_HOLDER."""
    print(marker, flush=True)
    print(f"serial_gate: {message}", file=sys.stderr)
    return STALE_HOLDER


def _adopt(lock_dir: str, build_id: str | None) -> int:
    """Report on the live holder of a --singleton lock; never start a twin.

    Returns OK (adopted), STALE_HOLDER with the STALE marker (--build-id
    given and the verified holder recorded another build), STALE_HOLDER with
    the ORPHAN marker (the lock stays held but no record ever verifies), or
    the internal `_LOCK_FREED` when the lock turned free while the record was
    being read (the holder just exited; the caller retries the start once).
    """
    rec = None
    for _ in range(_ADOPT_READ_TRIES):
        rec = _read_holder(lock_dir)
        if rec is not None:
            break
        time.sleep(0.1)
    if rec is None:
        if _lock_is_free(lock_dir):
            return _LOCK_FREED
        return _refuse(ORPHAN_MARKER, f"orphan holds lock: {lock_dir} is locked, but its record names no live "
                       "process with the recorded start time (dead pid, reused pid, or no record); not adopted "
                       "and nothing started. Find the holder with `lsof` on the lock file and stop it only if it "
                       "is yours")
    who = f"pid {rec.get('child_pid') or rec.get('pid')}, build {rec.get('build_id')}"
    if build_id is not None and rec.get("build_id") != build_id:
        return _refuse(STALE_MARKER, f"singleton held by {who}, not build {build_id}: not adopted. The holder may "
                       "serve stale code; stop it only if it is yours, then re-run")
    print(f"serial_gate: singleton already running ({who}); adopted, not starting a second instance: {lock_dir}")
    return OK


def _exit_code(status: int) -> int:
    """A shell-style exit code from a returncode or `os.waitstatus_to_exitcode` value (-N -> 128+N)."""
    return status if status >= 0 else 128 - status


def _supervise(fd: int, lock_dir: str, build_id: str | None, cmd: list[str]) -> int:
    """Body of the forked supervisor: hold `fd`, run the helper without it, return its exit code.

    The helper is started with `close_fds=True` (the default) and `fd` is
    non-inheritable, so neither the helper nor anything it spawns receives
    the lock; this process keeps the only reference, so the lock is released
    exactly when this process exits after the helper does. SIGTERM/SIGINT
    kill the helper, then exit 128+signal. Side-effects: rewrites the lock
    record, starts the helper, prints one `started` line.
    """
    os.set_inheritable(fd, False)

    def _on_signal(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    record = {"pid_start": _proc_start(os.getpid()), "child_pid": None, "build_id": build_id}
    _write_owner_info(fd, record)
    proc = None
    try:
        try:
            proc = subprocess.Popen(cmd)
        except OSError as exc:
            print(f"serial_gate: cannot start the helper: {exc}", file=sys.stderr)
            return LOCK_ERROR
        _write_owner_info(fd, {**record, "child_pid": proc.pid})
        print(f"serial_gate: singleton started (pid {proc.pid}, build {build_id}): {lock_dir}", flush=True)
        return _exit_code(proc.wait())
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()


def run_singleton(lock_dir: str, build_id: str | None, cmd: list[str]) -> int:
    """Start `cmd` as the lock-holding singleton, or adopt the live holder.

    Side effects: creates `lock_dir`, takes a non-blocking flock, and either
    forks a supervisor that holds the lock and runs `cmd` without the fd
    (returning `cmd`'s exit code), or starts nothing and returns `_adopt`'s
    code (0 adopted, 75 refused with a marker line). This wrapper closes its
    own copy of the fd right after the fork and never LOCK_UNs (unlocking
    would release the supervisor's lock too). SIGTERM/SIGINT to this wrapper
    is forwarded to the supervisor, which kills the helper; SIGKILL of this
    wrapper leaves the supervisor, and so the lock, alive while the helper
    runs. Fails closed (exit 2, nothing started) without `fcntl`.
    """
    if fcntl is None:
        print("serial_gate: fcntl is unavailable on this platform; refusing to start an unguarded helper",
              file=sys.stderr)
        return USAGE_ERROR
    for attempt in range(2):
        try:
            os.makedirs(lock_dir, exist_ok=True)
            fd = os.open(_lock_file_path(lock_dir), os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as exc:
            print(f"serial_gate: cannot open the singleton lock: {exc}", file=sys.stderr)
            return LOCK_ERROR
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            code = _adopt(lock_dir, build_id)
            if code != _LOCK_FREED:
                return code
            if attempt == 0:
                continue  # the holder exited while we read its record: try the start again, once
            return _refuse(ORPHAN_MARKER, f"orphan holds lock: {lock_dir} kept changing hands; not adopted")
        except OSError as exc:
            os.close(fd)
            print(f"serial_gate: singleton lock failed: {exc}", file=sys.stderr)
            return LOCK_ERROR
        return _fork_supervisor(fd, lock_dir, build_id, cmd)
    return LOCK_ERROR  # pragma: no cover — the loop always returns


def _fork_supervisor(fd: int, lock_dir: str, build_id: str | None, cmd: list[str]) -> int:
    """Fork the lock-holding supervisor, drop this process's fd, and wait for it.

    Why a fork and not `pass_fds` to the helper: a helper cannot be made to
    mark an inherited fd close-on-exec before it spawns children, so any
    grandchild it backgrounds would keep the lock after the helper exits.
    Returns the supervisor's exit code (the helper's code), or 128+signal
    when this wrapper was told to stop.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid == 0:  # supervisor: never return into the caller's stack
        code = LOCK_ERROR
        try:
            code = _supervise(fd, lock_dir, build_id, cmd)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else LOCK_ERROR
        except BaseException as exc:  # noqa: BLE001 — any failure must still end this forked process
            print(f"serial_gate: supervisor failed: {exc}", file=sys.stderr)
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)
    os.close(fd)  # the supervisor now holds the only reference to the locked open file description
    stopped: dict[str, int] = {}

    def _forward(signum, _frame):
        stopped["sig"] = signum
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    old_term = signal.signal(signal.SIGTERM, _forward)
    old_int = signal.signal(signal.SIGINT, _forward)
    try:
        _, status = os.waitpid(pid, 0)  # PEP 475: retried after _forward runs
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    if "sig" in stopped:
        return 128 + stopped["sig"]
    return _exit_code(os.waitstatus_to_exitcode(status))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_select(args: argparse.Namespace) -> int:
    code, lines = select_targets(
        map_path=args.map,
        changed_files=args.changed_file or None,
        base=args.base,
        head=args.head,
        repo_dir=args.repo,
    )
    for line in lines:
        print(line)
    return code


def _cmd_run(args: argparse.Namespace, cmd: list[str]) -> int:
    if not cmd:
        print("serial_gate: run requires a command after '--'", file=sys.stderr)
        return USAGE_ERROR
    if args.build_id is not None and (not args.singleton or not args.build_id.strip()
                                      or any(c.isspace() for c in args.build_id) or len(args.build_id) > 200):
        print("serial_gate: --build-id needs --singleton and a non-empty id without whitespace (<= 200 chars)",
              file=sys.stderr)
        return USAGE_ERROR
    if args.singleton:
        if args.slots != 1 or args.retry or args.retry_on:
            print("serial_gate: --slots/--retry/--retry-on are not supported with --singleton",
                  file=sys.stderr)
            return USAGE_ERROR
        return run_singleton(args.lock_dir, args.build_id, cmd)
    if args.slots < 1:
        print("serial_gate: --slots must be >= 1", file=sys.stderr)
        return USAGE_ERROR
    if args.retry < 0:
        print("serial_gate: --retry must be >= 0", file=sys.stderr)
        return USAGE_ERROR
    if args.retry > 0:
        if not args.retry_on:
            print("serial_gate: --retry > 0 requires --retry-on <regex>", file=sys.stderr)
            return USAGE_ERROR
        try:
            re.compile(args.retry_on)
        except re.error as exc:
            print(f"serial_gate: --retry-on is not a valid regex: {exc}", file=sys.stderr)
            return USAGE_ERROR
        return run_locked_with_retry(args.lock_dir, args.timeout, cmd, args.slots, args.retry, args.backoff,
                                      args.retry_on)
    return run_locked(args.lock_dir, args.timeout, cmd, args.slots)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: `select`, `run -- <cmd>`, or `--selftest`."""
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] == "--selftest":
        return _selftest()

    parser = argparse.ArgumentParser(
        description="Fail-closed path-scoped test selection + a cross-lane serial run lock."
    )
    parser.add_argument("--selftest", action="store_true", help="run the built-in self-test suite")
    sub = parser.add_subparsers(dest="subcommand")

    p_select = sub.add_parser("select", help="pick test targets for a diff, or FULL")
    p_select.add_argument("--map", required=True, help="path to the <glob>\\t<target> TSV map")
    p_select.add_argument("--base", help="base git ref")
    p_select.add_argument("--head", help="head git ref")
    p_select.add_argument("--repo", help="run git in this directory (default: cwd); also locates the repo top level for the map self-check")
    p_select.add_argument(
        "--changed-file", action="append", default=[],
        help="a changed path (repeatable); bypasses git entirely",
    )

    p_run = sub.add_parser("run", help="serialize a command across lanes with a flock-based lock")
    p_run.add_argument("--lock-dir", required=True, help="lock directory path (holds a file named 'lock')")
    p_run.add_argument("--timeout", type=float, default=DEFAULT_LOCK_TIMEOUT,
                        help=f"seconds to wait for the lock before giving up (default {DEFAULT_LOCK_TIMEOUT})")
    p_run.add_argument("--singleton", action="store_true",
                       help="start a long-lived helper once across sessions; adopt a live holder instead of waiting")
    p_run.add_argument("--build-id", help="with --singleton: adopt only a holder recorded with this build id")
    p_run.add_argument("--slots", type=int, default=1,
                       help="N-slot semaphore across N lock files; any free slot may be taken (default 1 = the "
                            "single lock, unchanged behavior); not supported with --singleton")
    p_run.add_argument("--retry", type=int, default=0,
                       help="retry the whole acquire+run+release cycle up to N more times, bounded, only when the "
                            "exit is nonzero AND output matches --retry-on (default 0 = no retry)")
    p_run.add_argument("--backoff", type=float, default=1.0,
                       help="base seconds for --retry's exponential, jittered, capped backoff")
    p_run.add_argument("--retry-on", help="regex matched against the failed attempt's combined stdout+stderr; "
                                          "required when --retry > 0")

    cmd: list[str] = []
    if "run" in argv:
        run_idx = argv.index("run")
        if "--" in argv[run_idx:]:
            sep = argv.index("--", run_idx)
            cmd = argv[sep + 1:]
            argv = argv[:sep]

    if not argv:
        parser.error("a subcommand is required (select, run) or --selftest")
        return USAGE_ERROR  # pragma: no cover — parser.error() already exits(2)

    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.subcommand == "select":
        return _cmd_select(args)
    if args.subcommand == "run":
        return _cmd_run(args, cmd)
    parser.error("a subcommand is required (select, run) or --selftest")
    return USAGE_ERROR  # pragma: no cover


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------


def _selftest() -> int:
    """Run every planted case and assert it behaves. Any failure prints a
    labeled reason and the function returns non-zero — this is the tool's
    own proof that fail-closed selection and the flock lock actually fire on
    real input, not just that they parse.
    """
    import shutil

    failures: list[str] = []
    total = {"n": 0}

    def check(label: str, cond: bool, detail: str = "") -> None:
        total["n"] += 1
        if not cond:
            failures.append(f"{label}: {detail}" if detail else label)

    tmp = tempfile.mkdtemp(prefix="serial_gate_selftest_")
    try:
        _selftest_select(tmp, check)
        _selftest_lock(tmp, check)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = total["n"] - len(failures)
    if failures:
        print(f"SELFTEST FAILED ({passed}/{total['n']}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST OK: {passed}/{total['n']}")
    return 0


def _write_map(path: str, rows: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")


def _selftest_select(tmp: str, check) -> None:
    map_path = os.path.join(tmp, "map.tsv")
    _write_map(map_path, [
        "# comment line, ignored",
        "",
        "src/alpha/**\ttest_alpha",
        "src/beta/**\ttest_beta",
        "!full\tconfig/critical.*",
    ])

    # 1) mapped path -> exactly its target, and NOT FULL.
    code, lines = select_targets(map_path, changed_files=["src/alpha/x.py"])
    check("mapped-path", code == OK and lines == ["test_alpha"], f"got {code} {lines}")

    # 2) two mapped paths -> union deduped, sorted.
    code, lines = select_targets(
        map_path, changed_files=["src/alpha/x.py", "src/alpha/y.py", "src/beta/z.py"]
    )
    check("two-mapped-union", code == OK and lines == ["test_alpha", "test_beta"], f"got {code} {lines}")

    # 3) unmapped path -> FULL.
    code, lines = select_targets(map_path, changed_files=["docs/readme.md"])
    check("unmapped-full", code == OK and lines == [FULL], f"got {code} {lines}")

    # 4) !full path -> FULL.
    code, lines = select_targets(map_path, changed_files=["config/critical.yaml"])
    check("bang-full", code == OK and lines == [FULL], f"got {code} {lines}")

    # 5) map-file change -> FULL (even though map.tsv matches no listed row).
    code, lines = select_targets(map_path, changed_files=[_normalize_path(map_path)])
    check("map-file-forces-full", code == OK and lines == [FULL], f"got {code} {lines}")

    # 6) empty diff -> FULL.
    code, lines = select_targets(map_path, changed_files=[])
    check("empty-diff-full", code == OK and lines == [FULL], f"got {code} {lines}")

    # 7) malformed map -> rc 2 (+ FULL printed).
    bad_map = os.path.join(tmp, "bad_map.tsv")
    _write_map(bad_map, ["only-one-field-no-tab"])
    code, lines = select_targets(bad_map, changed_files=["src/alpha/x.py"])
    check("malformed-map-rc2", code == USAGE_ERROR and lines == [FULL], f"got {code} {lines}")

    # 8) missing map -> rc 2 (+ FULL printed) — same fail-closed family as malformed.
    code, lines = select_targets(os.path.join(tmp, "does-not-exist.tsv"), changed_files=["x"])
    check("missing-map-rc2", code == USAGE_ERROR and lines == [FULL], f"got {code} {lines}")

    # 9 & 10) real git repo: unresolvable ref -> FULL + rc2; empty diff -> FULL + rc0;
    # plus one real mapped-diff exercise of the --base/--head code path.
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    _git(repo, ["init", "-q"])
    _git(repo, ["config", "user.email", "jane@example.com"])
    _git(repo, ["config", "user.name", "Jane Smith"])
    os.makedirs(os.path.join(repo, "src", "alpha"))
    with open(os.path.join(repo, "src", "alpha", "x.py"), "w") as fh:
        fh.write("1\n")
    _git(repo, ["add", "."])
    _git(repo, ["commit", "-q", "-m", "base"])
    base_sha = _git(repo, ["rev-parse", "HEAD"]).strip()

    with open(os.path.join(repo, "src", "alpha", "x.py"), "w") as fh:
        fh.write("2\n")
    _git(repo, ["commit", "-q", "-am", "change alpha"])
    head_sha = _git(repo, ["rev-parse", "HEAD"]).strip()

    repo_map = os.path.join(repo, "map.tsv")
    _write_map(repo_map, ["src/alpha/**\ttest_alpha"])

    code, lines = select_targets(repo_map, base=base_sha, head=head_sha, repo_dir=repo)
    check("git-diff-mapped", code == OK and lines == ["test_alpha"], f"got {code} {lines}")

    code, lines = select_targets(repo_map, base=head_sha, head=head_sha, repo_dir=repo)
    check("git-empty-diff-full", code == OK and lines == [FULL], f"got {code} {lines}")

    code, lines = select_targets(repo_map, base="does-not-exist-ref", head=head_sha, repo_dir=repo)
    check("git-unresolvable-rc2", code == USAGE_ERROR and lines == [FULL], f"got {code} {lines}")

    # Rename out of a !full area into a mapped one. With git's default rename
    # detection only the NEW (mapped) path is reported and selection would be
    # just `test_alpha` — a fail-open. --no-renames surfaces the old !full
    # path too, so the result must be FULL. Content is long enough for git to
    # detect the rename with detection on (the pre-fix behaviour).
    os.makedirs(os.path.join(repo, "config"))
    with open(os.path.join(repo, "config", "critical.yaml"), "w") as fh:
        fh.write("".join(f"line {i}\n" for i in range(20)))
    _git(repo, ["add", "."])
    _git(repo, ["commit", "-q", "-m", "add critical config"])
    pre_mv = _git(repo, ["rev-parse", "HEAD"]).strip()
    _git(repo, ["mv", "config/critical.yaml", "src/alpha/moved.yaml"])
    _git(repo, ["commit", "-q", "-m", "move critical config"])
    post_mv = _git(repo, ["rev-parse", "HEAD"]).strip()
    renamed_seen = _git(repo, ["diff", "-M", "--name-only", pre_mv, post_mv]).split()
    check("rename-precondition-git-detects-rename", renamed_seen == ["src/alpha/moved.yaml"],
          f"git default diff reported {renamed_seen} — test no longer exercises rename detection")
    rename_map = os.path.join(repo, "rename_map.tsv")
    _write_map(rename_map, ["src/alpha/**\ttest_alpha", "!full\tconfig/critical.*"])
    code, lines = select_targets(rename_map, base=pre_mv, head=post_mv, repo_dir=repo)
    check("rename-old-path-not-dropped", code == OK and lines == [FULL], f"got {code} {lines}")

    # Map self-check against the repo top level: the map lives at ci/map.tsv
    # and a row maps ci/** to a target, so without the top-level comparison
    # an absolute --map would select `test_ci` instead of forcing FULL.
    os.makedirs(os.path.join(repo, "ci"))
    ci_map = os.path.join(repo, "ci", "map.tsv")
    _write_map(ci_map, ["ci/**\ttest_ci", "src/**\ttest_src"])
    code, lines = select_targets(os.path.abspath(ci_map), changed_files=["ci/map.tsv"], repo_dir=repo)
    check("abs-map-vs-repo-relative-changed-file", code == OK and lines == [FULL], f"got {code} {lines}")
    code, lines = select_targets(os.path.abspath(ci_map), changed_files=["ci/other.txt"], repo_dir=repo)
    check("abs-map-sibling-still-mapped", code == OK and lines == ["test_ci"], f"got {code} {lines}")
    _git(repo, ["add", "ci/map.tsv"])
    _git(repo, ["commit", "-q", "-m", "add ci map"])
    pre_ci = _git(repo, ["rev-parse", "HEAD"]).strip()
    with open(ci_map, "a") as fh:
        fh.write("docs/**\ttest_docs\n")
    _git(repo, ["commit", "-q", "-am", "edit ci map"])
    post_ci = _git(repo, ["rev-parse", "HEAD"]).strip()
    code, lines = select_targets(os.path.abspath(ci_map), base=pre_ci, head=post_ci, repo_dir=repo)
    check("abs-map-git-diff-forces-full", code == OK and lines == [FULL], f"got {code} {lines}")


def _git(cwd: str, args: list[str]) -> str:
    proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0 and args and args[0] not in ("rev-parse",):
        raise RuntimeError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


def _wait_for(path: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.02)
    return os.path.exists(path)


def _lock_free(lock_dir: str, timeout: float = 2.0) -> bool:
    """True iff `lock_dir`'s lock can be acquired (and is immediately
    released again) within `timeout` — proof that nothing else holds it.
    """
    try:
        fd = acquire_lock(lock_dir, timeout)
    except LockTimeout:
        return False
    release_lock(fd)
    return True


def _selftest_lock(tmp: str, check) -> None:
    """Cross-lane flock lock: exclusivity, promptness on SIGKILL, timeout,
    exit-code propagation, no age-based release, release on normal exit, and
    the fail-closed path when `fcntl` is unavailable.
    """
    script_path = os.path.abspath(__file__)

    _selftest_lock_many_racers(tmp, check, script_path)
    _selftest_lock_release_on_exit(tmp, check, script_path)
    _selftest_lock_sigkill(tmp, check, script_path)
    _selftest_lock_timeout(tmp, check, script_path)
    _selftest_lock_exit_code(tmp, check, script_path)
    _selftest_lock_no_age_reclaim(tmp, check, script_path)
    _selftest_lock_no_fcntl(tmp, check)
    _selftest_lock_slots(tmp, check, script_path)
    _selftest_lock_retry(tmp, check, script_path)
    _selftest_singleton(tmp, check, script_path)


def _selftest_lock_many_racers(tmp: str, check, script_path: str) -> None:
    """>= 4 concurrent `run`s, repeated over several rounds: at most one
    child is ever inside the lock.

    Each child appends `enter <id>` then `exit <id>` to one O_APPEND log and
    also keeps a per-holder marker in an `active/` dir while inside; entering
    with any other marker present is written as `overlap`. Exclusivity holds
    iff the log is a strict enter/exit alternation with matching ids, no
    `overlap` line, and one enter per racer. After every racer exits, the
    lock must be immediately acquirable again (release-on-exit, not just
    exclusivity).
    """
    racers = 5
    for rnd in range(3):
        base = os.path.join(tmp, f"race_{rnd}")
        os.makedirs(base)
        lock_dir = os.path.join(base, "lock")
        log = os.path.join(base, "log")
        active = os.path.join(base, "active")
        os.mkdir(active)
        child_tmpl = (
            "import os,sys,time\n"
            "rid=sys.argv[1]; log={log!r}; active={active!r}\n"
            "def w(s):\n"
            "    fd=os.open(log, os.O_WRONLY|os.O_APPEND|os.O_CREAT, 0o644); os.write(fd, s.encode()); os.close(fd)\n"
            "if os.listdir(active): w('overlap '+rid+'\\n')\n"
            "open(os.path.join(active, rid), 'w').close()\n"
            "w('enter '+rid+'\\n')\n"
            "time.sleep(0.1)\n"
            "w('exit '+rid+'\\n')\n"
            "os.remove(os.path.join(active, rid))\n"
        )
        child = child_tmpl.format(log=log, active=active)
        procs = [
            subprocess.Popen([
                sys.executable, script_path, "run", "--lock-dir", lock_dir,
                "--timeout", "60",
                "--", sys.executable, "-c", child, str(i),
            ])
            for i in range(racers)
        ]
        rcs = [p.wait(timeout=90) for p in procs]
        try:
            with open(log, encoding="utf-8") as fh:
                events = [ln.split() for ln in fh.read().splitlines() if ln.strip()]
        except OSError:
            events = []
        ok = all(len(e) == 2 for e in events) and len(events) == 2 * racers
        if ok:
            for i in range(0, len(events), 2):
                if events[i][0] != "enter" or events[i + 1] != ["exit", events[i][1]]:
                    ok = False
                    break
        entered = sorted(e[1] for e in events if e and e[0] == "enter")
        check(f"racers-{rnd}-exclusive",
              ok and not any(e and e[0] == "overlap" for e in events),
              f"log={events}")
        check(f"racers-{rnd}-all-ran",
              rcs == [0] * racers and entered == sorted(str(i) for i in range(racers)),
              f"rcs={rcs} entered={entered}")
        check(f"racers-{rnd}-lock-released-after", _lock_free(lock_dir))


def _selftest_lock_release_on_exit(tmp: str, check, script_path: str) -> None:
    """A holder that exits normally releases the lock immediately."""
    lock_dir = os.path.join(tmp, "lock_release")
    rc = subprocess.run([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "10", "--", sys.executable, "-c", "pass",
    ]).returncode
    check("release-normal-exit-rc0", rc == 0, f"got {rc}")
    check("release-normal-exit-unlocked", _lock_free(lock_dir))


def _selftest_lock_sigkill(tmp: str, check, script_path: str) -> None:
    """SIGKILLing the holder releases the lock immediately (kernel-owned):
    a waiter acquires promptly, with no stale-wait window to cross — because
    none exists.
    """
    lock_dir = os.path.join(tmp, "lock_sigkill")
    started = os.path.join(tmp, "sigkill_started")
    # Short-lived so the orphaned child (SIGKILL only hits the `run` parent,
    # not this grandchild) does not linger past the test.
    holder_child = f"import pathlib,time; pathlib.Path({started!r}).touch(); time.sleep(5)"
    holder = subprocess.Popen([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "30", "--", sys.executable, "-c", holder_child,
    ])
    started_ok = _wait_for(started, timeout=10)
    check("sigkill-holder-started", started_ok)

    holder.kill()  # SIGKILL the process holding the fd/flock
    holder.wait(timeout=10)

    t0 = time.monotonic()
    waiter_rc = subprocess.run([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "10", "--", sys.executable, "-c", "pass",
    ]).returncode
    elapsed = time.monotonic() - t0
    check("sigkill-waiter-acquired", waiter_rc == 0, f"rc={waiter_rc}")
    # Bound generous enough for N copies of this selftest to share one CPU
    # (contended host / concurrent test-ci-gates.sh runs) yet still well
    # short of the 10s --timeout above, so a real stale-wait regression still
    # fails this check instead of merely the outer timeout.
    check("sigkill-waiter-prompt", elapsed < 8.0, f"elapsed={elapsed:.2f}s")


def _selftest_lock_timeout(tmp: str, check, script_path: str) -> None:
    """A held lock that never releases within --timeout -> 124, and the
    command is NEVER executed.
    """
    lock_dir = os.path.join(tmp, "lock_timeout")
    started = os.path.join(tmp, "timeout_started")
    release = os.path.join(tmp, "timeout_release")
    holder_child = (
        f"import pathlib,time; pathlib.Path({started!r}).touch(); "
        f"r=pathlib.Path({release!r})\n"
        f"while not r.exists(): time.sleep(0.02)\n"
    )
    holder = subprocess.Popen([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "30", "--", sys.executable, "-c", holder_child,
    ])
    try:
        check("timeout-holder-started", _wait_for(started, timeout=10))
        marker = os.path.join(tmp, "timeout_marker_should_not_exist")
        rc = subprocess.run([
            sys.executable, script_path, "run", "--lock-dir", lock_dir,
            "--timeout", "1",
            "--", sys.executable, "-c", f"open({marker!r}, 'w').close()",
        ]).returncode
        check("timeout-rc-124", rc == LOCK_TIMEOUT, f"got {rc}")
        check("timeout-command-not-run", not os.path.exists(marker),
              "command ran despite the lock never being acquired")
    finally:
        open(release, "w").close()
        holder.wait(timeout=15)


def _selftest_lock_exit_code(tmp: str, check, script_path: str) -> None:
    """The child's own exit code is propagated through `run`."""
    lock_dir = os.path.join(tmp, "lock_exit")
    rc = subprocess.run([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "10", "--", sys.executable, "-c", "import sys; sys.exit(7)",
    ]).returncode
    check("child-exit-propagated", rc == 7, f"got {rc}")


def _selftest_lock_no_age_reclaim(tmp: str, check, script_path: str) -> None:
    """A held lock survives past any age: there is no --stale-after and no
    reclaim logic left to trip. Back-dating the lock file's mtime far past
    any historical staleness window must have no effect.
    """
    lock_dir = os.path.join(tmp, "lock_no_age")
    started = os.path.join(tmp, "no_age_started")
    release = os.path.join(tmp, "no_age_release")
    holder_child = (
        f"import pathlib,time; pathlib.Path({started!r}).touch(); "
        f"r=pathlib.Path({release!r})\n"
        f"while not r.exists(): time.sleep(0.02)\n"
    )
    holder = subprocess.Popen([
        sys.executable, script_path, "run", "--lock-dir", lock_dir,
        "--timeout", "60", "--", sys.executable, "-c", holder_child,
    ])
    try:
        check("no-age-holder-started", _wait_for(started, timeout=10))
        past = time.time() - 10_000
        os.utime(_lock_file_path(lock_dir), (past, past))
        marker = os.path.join(tmp, "no_age_intruder_ran")
        rc = subprocess.run([
            sys.executable, script_path, "run", "--lock-dir", lock_dir,
            "--timeout", "1",
            "--", sys.executable, "-c", f"open({marker!r}, 'w').close()",
        ]).returncode
        check("no-age-intruder-times-out", rc == LOCK_TIMEOUT, f"rc={rc}")
        check("no-age-intruder-never-ran", not os.path.exists(marker))
    finally:
        open(release, "w").close()
        holder.wait(timeout=15)


def _selftest_lock_no_fcntl(tmp: str, check) -> None:
    """`fcntl` unavailable (e.g. Windows) -> exit 2, fail closed, command
    never runs. Exercised in-process by monkeypatching the module-level
    `fcntl` name rather than by faking a whole platform.
    """
    marker = os.path.join(tmp, "no_fcntl_marker")
    saved = globals()["fcntl"]
    globals()["fcntl"] = None
    try:
        rc = run_locked(
            os.path.join(tmp, "lock_no_fcntl"), 5.0,
            [sys.executable, "-c", f"open({marker!r}, 'w').close()"],
        )
    finally:
        globals()["fcntl"] = saved
    check("no-fcntl-exit-2", rc == USAGE_ERROR, f"rc={rc}")
    check("no-fcntl-command-not-run", not os.path.exists(marker))


def _selftest_lock_slots(tmp: str, check, script_path: str) -> None:
    """`--slots N` is an N-slot semaphore, not N independent copies of the
    single lock: with slots=2 and 5 concurrent racers, never more than 2 are
    ever inside at once (deterministic proof, not a timing sample: each
    racer marks itself in a shared `active/` dir before recording how many
    markers — including its own — are present, so a real >N-holder
    violation always leaves a >N count in the log), every racer runs exactly
    once, and afterward every slot is free again (release-on-exit, per slot,
    same as the single-lock case above).
    """
    racers = 5
    slots = 2
    lock_dir = os.path.join(tmp, "lock_slots")
    active = os.path.join(tmp, "lock_slots_active")
    log = os.path.join(tmp, "lock_slots_log")
    os.makedirs(active)
    child = (
        "import os,sys,time\n"
        f"rid=sys.argv[1]; active={active!r}; log={log!r}\n"
        "open(os.path.join(active, rid), 'w').close()\n"
        "n = len(os.listdir(active))\n"
        "fd=os.open(log, os.O_WRONLY|os.O_APPEND|os.O_CREAT, 0o644)\n"
        "os.write(fd, (str(n)+'\\n').encode()); os.close(fd)\n"
        "time.sleep(0.3)\n"
        "os.remove(os.path.join(active, rid))\n"
    )
    procs = [
        subprocess.Popen([
            sys.executable, script_path, "run", "--lock-dir", lock_dir, "--slots", str(slots),
            "--timeout", "60", "--", sys.executable, "-c", child, str(i),
        ])
        for i in range(racers)
    ]
    rcs = [p.wait(timeout=90) for p in procs]
    with open(log, encoding="utf-8") as fh:
        counts = [int(x) for x in fh.read().split()]
    check("slots-all-ran", rcs == [0] * racers and len(counts) == racers, f"rcs={rcs} counts={counts}")
    check("slots-never-exceeds-cap", bool(counts) and max(counts) <= slots, f"counts={counts}")
    check("slots-cap-actually-used", bool(counts) and max(counts) >= 1, f"counts={counts}")
    check("slots-all-free-after", _slots_all_free(lock_dir, slots))


def _selftest_lock_retry(tmp: str, check, script_path: str) -> None:
    """`--retry K --retry-on REGEX`: retried only when a failed attempt's
    combined output matches REGEX (recovers within the budget -> final rc 0
    with exactly the attempts needed); a failure that does NOT match is
    returned at once with zero retries (never amplifies a genuine, unrelated
    failure, per #1127); and a helper that always fails matching output
    still runs EXACTLY `retry + 1` total attempts, proving the loop is
    bounded, not unbounded. `--retry` without `--retry-on` is a usage error.
    """

    def _counter(counter: str) -> str:
        return (
            "import os\n"
            f"c={counter!r}\n"
            "n = int(open(c).read()) if os.path.exists(c) else 0\n"
            "open(c, 'w').write(str(n + 1))\n"
        )

    def _run(lock_dir: str, retry: int, retry_on: str | None, helper: str) -> int:
        args = [sys.executable, script_path, "run", "--lock-dir", lock_dir, "--retry", str(retry)]
        if retry_on is not None:
            args += ["--retry-on", retry_on]
        args += ["--backoff", "0.02", "--", sys.executable, "-c", helper]
        return subprocess.run(args, capture_output=True, text=True, timeout=60).returncode

    counter = os.path.join(tmp, "retry_recovers_count")
    helper = _counter(counter) + "import sys\nif n < 2:\n    sys.stderr.write('RETRYME transient\\n'); sys.exit(1)\n"
    rc = _run(os.path.join(tmp, "retry_recovers"), 5, "RETRYME", helper)
    attempts = int(open(counter, encoding="utf-8").read())
    check("retry-recovers-rc0", rc == 0, f"rc={rc}")
    check("retry-recovers-attempts-3", attempts == 3, f"attempts={attempts}")

    counter2 = os.path.join(tmp, "retry_no_match_count")
    helper2 = _counter(counter2) + "import sys\nsys.stderr.write('unrelated real failure\\n'); sys.exit(9)\n"
    rc2 = _run(os.path.join(tmp, "retry_no_match"), 5, "RETRYME", helper2)
    attempts2 = int(open(counter2, encoding="utf-8").read())
    check("retry-no-match-not-retried", rc2 == 9 and attempts2 == 1, f"rc={rc2} attempts={attempts2}")

    counter3 = os.path.join(tmp, "retry_bounded_count")
    helper3 = _counter(counter3) + "import sys\nsys.stderr.write('RETRYME always\\n'); sys.exit(1)\n"
    rc3 = _run(os.path.join(tmp, "retry_bounded"), 2, "RETRYME", helper3)
    attempts3 = int(open(counter3, encoding="utf-8").read())
    check("retry-bounded-final-rc-propagated", rc3 == 1, f"rc={rc3}")
    check("retry-bounded-exact-attempts", attempts3 == 3, f"attempts={attempts3} (expected retry+1=3)")

    rc4 = _run(os.path.join(tmp, "retry_needs_pattern"), 1, None, "pass")
    check("retry-without-pattern-usage-error", rc4 == USAGE_ERROR, f"rc={rc4}")


def _selftest_singleton(tmp: str, check, script_path: str) -> None:
    """`run --singleton`: a second start adopts the live holder instead of
    spawning a twin (#1078), a different --build-id is refused rather than
    adopted, the lock survives SIGKILL of the wrapper while the helper child
    lives (the forked supervisor keeps the lock fd), and a start after the helper
    exits runs normally.
    """
    lock_dir = os.path.join(tmp, "singleton")
    started = os.path.join(tmp, "singleton_started")
    release = os.path.join(tmp, "singleton_release")
    twin = os.path.join(tmp, "singleton_twin_ran")
    holder_child = (
        f"import pathlib,time; pathlib.Path({started!r}).touch(); "
        f"r=pathlib.Path({release!r})\n"
        f"while not r.exists(): time.sleep(0.02)\n"
    )
    holder = subprocess.Popen([
        sys.executable, script_path, "run", "--singleton", "--lock-dir", lock_dir,
        "--build-id", "abc1234", "--", sys.executable, "-c", holder_child,
    ], stdout=subprocess.DEVNULL)

    def start(*extra: str) -> tuple[int, str, float]:
        t0 = time.monotonic()
        proc = subprocess.run([
            sys.executable, script_path, "run", "--singleton", "--lock-dir", lock_dir, *extra,
            "--", sys.executable, "-c", f"open({twin!r}, 'w').close()",
        ], capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr, time.monotonic() - t0

    try:
        check("singleton-holder-started", _wait_for(started, timeout=10))
        rc, out, took = start("--build-id", "abc1234")
        check("singleton-second-start-adopts", rc == OK and "adopted" in out and took < 10
              and not os.path.exists(twin), f"rc={rc} took={took:.2f}s out={out!r}")
        rc, out, _ = start()
        check("singleton-adopts-without-build-id", rc == OK and "adopted" in out
              and not os.path.exists(twin), f"rc={rc} out={out!r}")
        rc, out, _ = start("--build-id", "def5678")
        check("singleton-stale-build-not-adopted", rc == STALE_HOLDER and "not adopted" in out
              and "abc1234" in out and not os.path.exists(twin), f"rc={rc} out={out!r}")
        holder.kill()  # SIGKILL the wrapper only; the supervisor keeps the lock while the helper lives
        holder.wait(timeout=10)
        rc, out, _ = start("--build-id", "abc1234")
        check("singleton-survives-wrapper-sigkill", rc == OK and "adopted" in out
              and not os.path.exists(twin), f"rc={rc} out={out!r}")
    finally:
        open(release, "w").close()
        if holder.poll() is None:
            holder.wait(timeout=15)
    check("singleton-free-after-helper-exits", _lock_free(lock_dir, timeout=10))
    rc, out, _ = start()
    check("singleton-starts-when-free", rc == OK and os.path.exists(twin), f"rc={rc} out={out!r}")
    rc = subprocess.run([
        sys.executable, script_path, "run", "--lock-dir", lock_dir, "--build-id", "abc1234",
        "--", sys.executable, "-c", "pass",
    ], capture_output=True).returncode
    check("build-id-needs-singleton", rc == USAGE_ERROR, f"rc={rc}")

    _selftest_singleton_codes(tmp, check, script_path)
    _selftest_singleton_grandchild(tmp, check, script_path)
    _selftest_singleton_orphan(tmp, check, script_path)


def _singleton_start(script_path: str, lock_dir: str, helper: str, *extra: str) -> tuple[int, str]:
    """One `run --singleton` whose helper is `python -c helper`; returns (rc, stdout + stderr)."""
    proc = subprocess.run([
        sys.executable, script_path, "run", "--singleton", "--lock-dir", lock_dir, *extra,
        "--", sys.executable, "-c", helper,
    ], capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def _selftest_singleton_codes(tmp: str, check, script_path: str) -> None:
    """A not-adopted exit is distinguishable from any helper exit code: the
    stale-build refusal exits 75 (EX_TEMPFAIL) with a `SERIAL_GATE:
    STALE_HOLDER` marker line, while a helper that exits 3 propagates 3 with
    no marker. Before the fix both exited 3, so a caller could not tell "the
    helper failed" from "nothing was started".
    """
    lock_dir = os.path.join(tmp, "singleton_codes")
    rc_helper, out_helper = _singleton_start(script_path, lock_dir, "import sys; sys.exit(3)", "--build-id", "abc1234")
    check("singleton-helper-exit-3-propagated", rc_helper == 3 and STALE_MARKER not in out_helper
          and ORPHAN_MARKER not in out_helper, f"rc={rc_helper} out={out_helper!r}")
    started = os.path.join(tmp, "codes_started")
    release = os.path.join(tmp, "codes_release")
    holder = subprocess.Popen([
        sys.executable, script_path, "run", "--singleton", "--lock-dir", lock_dir, "--build-id", "abc1234",
        "--", sys.executable, "-c",
        f"import pathlib,time; pathlib.Path({started!r}).touch(); r=pathlib.Path({release!r})\n"
        f"while not r.exists(): time.sleep(0.02)\n",
    ], stdout=subprocess.DEVNULL)
    try:
        check("singleton-codes-holder-started", _wait_for(started, timeout=10))
        rc_stale, out_stale = _singleton_start(script_path, lock_dir, "pass", "--build-id", "def5678")
        check("singleton-stale-exit-75-with-marker", rc_stale == 75 and STALE_MARKER in out_stale.splitlines()
              and rc_stale != rc_helper, f"rc={rc_stale} out={out_stale!r}")
    finally:
        open(release, "w").close()
        holder.wait(timeout=15)


def _selftest_singleton_grandchild(tmp: str, check, script_path: str) -> None:
    """A helper that backgrounds a grandchild and exits must not leave that
    grandchild holding the lock (#1078 follow-up). Before the fix the helper
    inherited the lock fd, so `sh -c 'sleep 8 & exit 0'` left `sleep` holding
    the lock for 8s with no recorded process alive; the supervisor now keeps
    the only lock fd and the helper tree never receives it.
    """
    lock_dir = os.path.join(tmp, "singleton_grandchild")
    pidfile = os.path.join(tmp, "grandchild.pid")
    # stdout/stderr go to DEVNULL: a pipe would stay open in `sleep` and make
    # the wrapper's caller wait the full 8s for EOF.
    rc = subprocess.run([
        sys.executable, script_path, "run", "--singleton", "--lock-dir", lock_dir,
        "--", "sh", "-c", f"sleep 8 & echo $! > {pidfile}; exit 0",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode
    try:
        check("singleton-grandchild-helper-exit-0", rc == 0, f"rc={rc}")
        check("singleton-grandchild-does-not-keep-lock", _lock_free(lock_dir, timeout=1.0),
              "a backgrounded grandchild of the helper still holds the singleton lock")
    finally:
        try:
            with open(pidfile, encoding="utf-8") as fh:
                os.kill(int(fh.read().strip()), signal.SIGKILL)
        except (OSError, ValueError):
            pass


def _selftest_singleton_orphan(tmp: str, check, script_path: str) -> None:
    """The lock is held but the holder record names no live process, or names
    a live pid whose start time does not match (pid reuse): exit 75 with a
    `SERIAL_GATE: ORPHAN_HOLDER` marker, never adopt, never start a twin.
    Before the fix, both cases were adopted (exit 0) without --build-id.
    """
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=10)
    records = {
        "dead-pid": {"pid": dead.pid, "pid_start": "ps:never"},
        "reused-pid": {"pid": os.getpid(), "pid_start": "ps:not-this-process"},
        "no-start-time": {"pid": os.getpid()},
    }
    for label, rec in records.items():
        lock_dir = os.path.join(tmp, f"singleton_orphan_{label}")
        os.makedirs(lock_dir)
        started = os.path.join(tmp, f"orphan_{label}_started")
        release = os.path.join(tmp, f"orphan_{label}_release")
        twin = os.path.join(tmp, f"orphan_{label}_twin")
        planter = (
            "import fcntl,json,os,pathlib,time\n"
            f"fd=os.open({_lock_file_path(lock_dir)!r}, os.O_RDWR|os.O_CREAT, 0o644)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            f"os.write(fd, json.dumps({rec!r}).encode())\n"
            f"pathlib.Path({started!r}).touch(); r=pathlib.Path({release!r})\n"
            "while not r.exists(): time.sleep(0.02)\n"
        )
        holder = subprocess.Popen([sys.executable, "-c", planter])
        try:
            check(f"orphan-{label}-planted", _wait_for(started, timeout=10))
            rc, out = _singleton_start(script_path, lock_dir, f"open({twin!r}, 'w').close()")
            check(f"orphan-{label}-refused", rc == 75 and ORPHAN_MARKER in out.splitlines()
                  and "orphan holds lock" in out and "adopted" not in out.replace("not adopted", "")
                  and not os.path.exists(twin), f"rc={rc} out={out!r}")
        finally:
            open(release, "w").close()
            holder.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
