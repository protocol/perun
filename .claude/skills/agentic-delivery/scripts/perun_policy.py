#!/usr/bin/env python3
"""perun_policy.py — read the one resource-policy file, `.perun/policy.json`.

WHY JSON AT `.perun/policy.json`: stdlib-only (no YAML dependency), readable by bash via this CLI, and
`.perun/` is a single repo-local dir other Perun state can share. Found by walking up from the cwd, or
`$PERUN_POLICY` (an explicit path; if set, a missing or unparseable file is an error, never defaults).
No file found by the walk means every default; a malformed file or bad value
fails closed (exit 2), never silently falls back.

Each dimension in DIMS takes `efficient` (default), `maximize`, `off`, or a non-negative number (a cap).
`share_learnings` takes `auto|ask|off` (default `ask`). `auto_update` takes `on|off` (default `on`):
whether perun_auto_update.py may re-apply a newer release tag in the background. `auto_update_pr` takes `on|off`
(default `on`): whether it then opens a `perun/update-v<ver>` PR so the copy committed on the default branch catches
up (never auto-merged); `auto_update_pr_base` (default empty = `origin/HEAD`) names the branch that PR targets and
that the committed-version WARN compares against (a base missing on origin skips the PR). `review_gate` takes
`warn|enforce|off` (default `warn`): whether review_gate.py blocks a merge with no independent review receipt.
`auto_compact` takes `on|off` (default `on`): whether `install.sh --apply-operating-layer` may set `autoCompactWindow: 200000`
(`off` skips it; a value the user already set is never overridden either way). `release_every` takes an integer >= 1 (default 1): `land-release.sh publish` releases only when the minor is a multiple of it.
`role` takes `off|ceo|ceo-strict` (default `off`; `ceo strict` is read as `ceo-strict`): whether ceo_altitude_guard.py warns (`ceo`) or
blocks (`ceo-strict`) when the MAIN session hand-edits source or tests; a subagent is never touched. Env `PERUN_ROLE` overrides it for one process.

  perun_policy.py get <dim>      print the value (a number prints as a number)
  perun_policy.py show           print the whole effective policy as JSON
  perun_policy.py set <dim> <value>  validate, write `.perun/policy.json` (created if absent), print the policy
  perun_policy.py check <dim> <value>  validate one pair, write nothing
  perun_policy.py skip-ci        print `[skip ci]` when github_actions is off, else nothing
  perun_policy.py lanes          parallel-lane count from local_cpu (see lanes())
  perun_policy.py heavy-slots    heavy-command concurrency = max(2, free cores) (see heavy_slots())
  perun_policy.py heavy-acquire [--kind light]  take a machine-wide heavy lease (exit 0 + prints pid) or exit 1 when full;
                                 `--kind light` (a read-only or doc lane) holds a quarter slot, see lane_weight()
  perun_policy.py heavy-load     print the weighted live-lease count (heavy = 1, light = 0.25), e.g. for host_probe.py --live-lanes
  perun_policy.py heavy-exclusive[-release|-renew]  take/drop/renew the EXCLUSIVE lease (train gate); heavy_gate denies heavy commands while held
  perun_policy.py heavy-release  drop this shell's lease (idempotent)
  perun_policy.py --selftest

Exit 0 ok, 2 usage / malformed policy / unknown dimension.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DIMS = ("tokens", "local_cpu", "local_ram", "github_actions", "paid_api_calls", "network")
MODES = ("efficient", "maximize", "off")
SHARE = ("auto", "ask", "off")
ON_OFF = ("on", "off")
REVIEW = ("warn", "enforce", "off")
ROLES = ("off", "ceo", "ceo-strict")


def norm_role(v):
    """Canonical role spelling: `Ceo  Strict` and `ceo-strict` are one role. Pure; a non-string is returned unchanged."""
    return "-".join(v.lower().split()) if isinstance(v, str) else v


def find_policy(start: str = ".") -> Path | None:
    """`$PERUN_POLICY`, else the nearest `.perun/policy.json` at or above `start`; None when absent."""
    if os.environ.get("PERUN_POLICY"):
        return Path(os.environ["PERUN_POLICY"])
    for d in [Path(start).resolve(), *Path(start).resolve().parents]:
        if (d / ".perun" / "policy.json").is_file():
            return d / ".perun" / "policy.json"
    return None


def load(path: Path | None = None) -> dict:
    """The validated policy with defaults filled. Raises ValueError on malformed JSON or a bad value."""
    explicit = path is None and os.environ.get("PERUN_POLICY")
    path = path or find_policy()
    if explicit and not path.is_file():  # an explicit $PERUN_POLICY that is absent never means "defaults"
        raise ValueError(f"$PERUN_POLICY set but {path} is missing")
    raw: dict = {}
    if path is not None and path.is_file():
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"unreadable policy {path}: {e}") from e
        if not isinstance(raw, dict):
            raise ValueError(f"policy {path} must be a JSON object")
    return validate(raw)


def validate(raw: dict) -> dict:
    """Defaults overlaid with `raw`; ValueError on an unknown key or a bad value."""
    pol: dict = {d: "efficient" for d in DIMS} | {"share_learnings": "ask", "auto_update": "on", "auto_update_pr": "on", "auto_update_pr_base": "", "review_gate": "warn", "release_every": 1, "auto_compact": "on", "role": "off"}
    for k, v in raw.items():
        if k == "share_learnings":
            ok = v in SHARE
        elif k == "role":  # canonicalised below: pol[k] stores the normalised spelling
            v = norm_role(v)
            ok = v in ROLES
        elif k == "review_gate":
            ok = v in REVIEW
        elif k == "release_every":  # publish a GitHub release every Nth minor version (land-release.sh publish)
            ok = isinstance(v, int) and not isinstance(v, bool) and v >= 1
        elif k == "auto_update_pr_base":  # '' = origin/HEAD; else a plain branch name (no option-like or `..` names)
            ok = isinstance(v, str) and (v == "" or (re.fullmatch(r"[A-Za-z0-9._/-]+", v) is not None and v[0] not in "-/" and v[-1] != "/" and ".." not in v and "//" not in v and v != "HEAD"))
        elif k in ("auto_update", "auto_update_pr", "auto_compact"):
            ok = v in ON_OFF
        elif k in DIMS:
            ok = v in MODES or (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0)
        else:
            raise ValueError(f"unknown policy key {k!r}")
        if not ok:
            raise ValueError(f"bad value for {k}: {v!r}")
        pol[k] = v
    return pol


def parse_value(value: str):
    """ASCII-digit strings become numbers; everything else stays a string (validate() then rejects it)."""
    return float(value) if re.fullmatch(r"[0-9]+\.[0-9]+", value) else int(value) if re.fullmatch(r"[0-9]+", value) else value


def set_value(dim: str, value: str) -> dict:
    """Set one dimension (a number string becomes a number) in the policy file: `$PERUN_POLICY`, the nearest
    `.perun/policy.json`, else `./.perun/policy.json` (created). Validated through load() before the atomic
    replace, so a bad dim/value raises (an existing bad key is overwritten, so `set` repairs it) and an unparseable file raises ValueError and leaves the file untouched."""
    path = find_policy() or Path(".perun/policy.json")
    try:
        raw = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"unreadable policy {path}: {e}") from e
    v = parse_value(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({**raw, dim: v}, indent=2) + "\n")
    try:
        pol = load(tmp)
    except ValueError:
        tmp.unlink()
        raise
    os.replace(tmp, path)
    return pol


def token_cap(n: int, tokens) -> int:
    """Cap a lane/slot count `n` by the `tokens` dim: efficient -> at most 2; off -> 1; a number -> at most
    that many (never below 1; it is a lane cap only, not a token budget); maximize -> no cap."""
    if tokens == "maximize":
        return n
    cap = 1 if tokens == "off" else max(1, int(tokens)) if isinstance(tokens, (int, float)) else 2
    return min(n, cap)


def free_cores(cores: int, load1: float | None, idle_pct: float | None = None) -> int:
    """Idle cores: `cores * idle%` when a CPU-idle reading exists (disk-IO wait inflates load1 while CPUs sit
    idle, which stalled admission), else the load1 fallback `cores - load1`."""
    if idle_pct is not None:
        return int(cores * idle_pct / 100.0)
    return int(cores - (load1 or 0))


def lanes(mode, cores: int, load1: float | None = None, tokens="maximize", idle_pct: float | None = None) -> int:
    """Parallel heavy-lane count for a `local_cpu` value. efficient: half the cores; maximize: every idle
    core (cores minus current load1), never below 1 and never past the host's own load ceiling; off: 1
    (serial); a number: that many; then capped by `tokens` (token_cap). `tokens` defaults to `maximize`
    (no cap) for direct callers; the CLI and host_probe pass the policy's value. host_probe.py's
    RAM/swap/load vetoes still apply on top."""
    if isinstance(mode, (int, float)):
        n = max(1, int(mode))
    elif mode == "maximize":
        n = max(1, free_cores(cores, load1, idle_pct))
    elif mode == "off":
        n = 1
    else:
        n = max(1, cores // 2)
    return token_cap(n, tokens)


def heavy_slots(cores: int, load1: float | None = None, tokens="maximize", idle_pct: float | None = None) -> int:
    """Concurrent heavy local commands (full test suite, build, browser run) a gate admits: free cores
    (cores x CPU idle%, else cores minus load1) but never below 2, so a busy host still makes progress. A primitive: callers opt in.
    Pair with `host_probe.py --lane-type heavy`, which defers the job when load1 > cores or RAM is low.
    `tokens` caps the result (token_cap). Kill criterion: if the median pre-push time rises after adopting this, revert to the flat cap."""
    return token_cap(max(2, free_cores(cores, load1, idle_pct)), tokens)


LEASE_TTL = 2 * 3600


def lease_dir() -> Path:
    """Machine-wide lease dir: `$PERUN_HEAVY_DIR` (tests), else `$XDG_CACHE_HOME` or `~/.cache`, /perun/heavy."""
    d = os.environ.get("PERUN_HEAVY_DIR")
    return Path(d) if d else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun" / "heavy"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # signal 0 only probes existence; nothing is signalled
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # exists, owned by another user
    return True


LIGHT_WEIGHT = 0.25  # a light lane (read-only, docs) holds this fraction of a heavy lane's slot
LIGHT_KINDS = ("light", "doc", "docs", "read-only", "readonly")
LIGHT_CPU_PCT = 15.0  # an undeclared lane whose process tree burns less than this % of one core counts as light...
WARMUP = 60  # ...once its lease is this many seconds old: a heavy job's CPU takes a moment to ramp up


def _leases(d: Path, now: float, exclude: int | None = None) -> list:
    """`(pid, start, kind)` for every live lease. One file per heavy job named `<pid>`, content `<pid> <start epoch>`
    plus an optional declared kind word (`light`, ...). A lease with a dead pid, a start older than LEASE_TTL (2h)
    or unreadable/malformed content is ignored, never deleted."""
    out = []
    for f in d.glob("*") if d.is_dir() else []:
        try:
            t = f.read_text().split()
            pid, start = int(t[0]), int(t[1])
        except (OSError, ValueError, IndexError):
            continue
        if len(t) in (2, 3) and pid != exclude and now - start < LEASE_TTL and _alive(pid):
            out.append((pid, start, t[2] if len(t) == 3 else None))
    return out


def active_leases(d: Path, now: float | None = None) -> list:
    """Pids holding a live lease (see `_leases` for the file format and what is ignored)."""
    return [pid for pid, _, _ in _leases(d, time.time() if now is None else now)]


def _proc_table() -> dict | None:
    """`{pid: (ppid, %cpu)}` from one `ps` read; None when ps is unavailable or unparseable (callers then fail closed)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pcpu="], capture_output=True, text=True, timeout=5).stdout
        return {int(r[0]): (int(r[1]), float(r[2])) for r in (ln.split() for ln in out.splitlines() if ln.strip())} or None
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def tree_cpu(table: dict | None, root: int) -> float | None:
    """Summed %CPU of `root` and every descendant in a `_proc_table()`; None when the table or `root` is missing."""
    if not table or root not in table:
        return None
    kids: dict = {}
    for pid, (ppid, _) in table.items():
        kids.setdefault(ppid, []).append(pid)
    total, todo, seen = 0.0, [root], set()
    while todo:
        p = todo.pop()
        if p not in seen:
            seen.add(p)
            total += table[p][1]
            todo += kids.get(p, [])
    return total


def lane_weight(kind: str | None, age: float, cpu: float | None) -> float:
    """What one live lease counts toward the slot cap. A declared light kind is LIGHT_WEIGHT; any other declared kind
    is 1. Undeclared: LIGHT_WEIGHT only when its measured CPU is known, below LIGHT_CPU_PCT and the lease is past
    WARMUP; every unknown counts 1, so a lane that cannot be measured is assumed heavy (fail closed)."""
    if kind is not None:
        return LIGHT_WEIGHT if kind.lower() in LIGHT_KINDS else 1.0
    return LIGHT_WEIGHT if cpu is not None and age >= WARMUP and cpu < LIGHT_CPU_PCT else 1.0


def lease_load(d: Path, now: float | None = None, exclude: int | None = None, table: dict | None = None) -> float:
    """Weighted count of live leases (heavy = 1, light = LIGHT_WEIGHT), the number a slot cap is compared with.
    `ps` is read once, only when an undeclared lease is old enough to be measured; `table` injects it for tests."""
    now = time.time() if now is None else now
    rows = _leases(d, now, exclude)
    if table is None and any(k is None and now - s >= WARMUP for _, s, k in rows):
        table = _proc_table()
    return sum(lane_weight(k, now - s, tree_cpu(table, p) if k is None else None) for p, s, k in rows)


def heavy_acquire(d: Path, slots: int, pid: int, kind: str | None = None) -> bool:
    """Take a lease for `pid` unless other live leases already weigh `slots` or more (see lease_load). Declare
    `kind="light"` for a read-only or doc lane so it counts LIGHT_WEIGHT. Re-acquire by the same pid refreshes it.
    Side effect: creates `d`. ponytail: check-then-write is racy across simultaneous starts; the host_probe HOLD
    retry absorbs it, add O_EXCL slot files if overshoot is measured."""
    if kind is not None and not re.fullmatch(r"[A-Za-z][A-Za-z-]{0,15}", kind):
        raise ValueError(f"bad lane kind {kind!r}")
    if lease_load(d, exclude=pid) >= slots:
        return False
    d.mkdir(parents=True, exist_ok=True)
    (d / str(pid)).write_text(f"{pid} {int(time.time())}" + (f" {kind}" if kind else ""))
    return True


def heavy_release(d: Path, pid: int) -> None:
    """Drop `pid`'s lease; a missing lease is fine."""
    (d / str(pid)).unlink(missing_ok=True)


def exclusive_holder(d: Path):
    """Pid of the live EXCLUSIVE lease (a train gate running), else None. Stored beside the lease dir
    (`heavy.exclusive`, content `<pid> <start epoch>`) so it never fills a slot. Valid only while the pid is alive AND the
    file's mtime is younger than LEASE_TTL: the holder renews it (exclusive_renew) at each step, so a long gate keeps it
    and a pid reused after a reboot (live pid, old mtime) expires. Dead pid, expired, unreadable or malformed = None
    (heavy_gate stays fail-open); nothing is deleted here."""
    f = d.parent / "heavy.exclusive"
    try:
        pid, _ = (int(x) for x in f.read_text().split())
        fresh = time.time() - f.stat().st_mtime < LEASE_TTL
    except (OSError, ValueError):
        return None
    return pid if fresh and _alive(pid) else None


def exclusive_acquire(d: Path, pid: int) -> bool:
    """Take the machine-wide exclusive lease for `pid`; False while another valid holder has it. The content (`pid ts`)
    is written whole to a temp file and hard-linked into place (atomic and exclusive: nobody sees an empty file, two
    gates cannot both win). A lease is unlinked only after two expiry checks; our own is replaced by rename. While held,
    heavy_gate.py denies every heavy command ("gate running: wait"). Side effect: creates `d.parent`."""
    f = d.parent / "heavy.exclusive"
    d.parent.mkdir(parents=True, exist_ok=True)
    tmp = d.parent / f"heavy.exclusive.{pid}.tmp"
    tmp.write_text(f"{pid} {int(time.time())}")
    try:
        for _ in range(2):
            try:
                os.link(tmp, f)
                return True
            except FileExistsError:
                h = exclusive_holder(d)
                if h == pid:
                    os.replace(tmp, f)
                    return True
                if h is not None:
                    return False
                if exclusive_holder(d) is None:  # re-check right before unlink
                    f.unlink(missing_ok=True)
        return False
    finally:
        tmp.unlink(missing_ok=True)


def exclusive_renew(d: Path, pid: int) -> None:
    """Refresh the lease mtime while `pid` still holds it (called by the train at each step); no-op otherwise."""
    if exclusive_holder(d) == pid:
        os.utime(d.parent / "heavy.exclusive")


def exclusive_release(d: Path, pid: int) -> None:
    """Drop the exclusive lease only if `pid` holds it; a missing one is fine."""
    if exclusive_holder(d) == pid:
        (d.parent / "heavy.exclusive").unlink(missing_ok=True)


def main(argv: list) -> int:
    if argv[:1] == ["--selftest"]:
        return _selftest()
    try:
        if argv[:1] == ["check"] and len(argv) == 3:  # validate one pair, write nothing
            validate({argv[1]: parse_value(argv[2])})
            return 0
        if argv[:1] == ["set"] and len(argv) == 3:
            print(json.dumps(set_value(argv[1], argv[2])))
            return 0
        pol = load()
        if argv[:1] == ["get"] and len(argv) == 2 and argv[1] in pol:
            print(pol[argv[1]])
            return 0
        if argv == ["show"]:
            print(json.dumps(pol))
            return 0
        if argv == ["skip-ci"]:
            print("[skip ci]" if os.environ.get("PERUN_GITHUB_ACTIONS", pol["github_actions"]) == "off" else "")
            return 0
        if argv == ["lanes"]:
            import host_probe  # lazy: host_probe imports this module
            load1, cores = host_probe.read_load1_and_cores()
            print(lanes(pol["local_cpu"], cores or os.cpu_count() or 1, load1, pol["tokens"], host_probe.read_cpu_idle_pct()))
            return 0
        if argv == ["heavy-slots"]:
            import host_probe
            load1, cores = host_probe.read_load1_and_cores()
            print(heavy_slots(cores or os.cpu_count() or 1, load1, pol["tokens"], host_probe.read_cpu_idle_pct()))
            return 0
        if argv in (["heavy-exclusive"], ["heavy-exclusive-release"], ["heavy-exclusive-renew"]):  # caller shell = holder
            if argv != ["heavy-exclusive"]:
                (exclusive_release if argv[0].endswith("release") else exclusive_renew)(lease_dir(), os.getppid())
                return 0
            ok = exclusive_acquire(lease_dir(), os.getppid())
            print(os.getppid() if ok else "HELD")
            return 0 if ok else 1
        if argv == ["heavy-load"]:
            print(f"{lease_load(lease_dir()):g}")
            return 0
        if argv == ["heavy-release"] or argv[:1] == ["heavy-acquire"] and (len(argv) == 1 or len(argv) == 3 and argv[1] == "--kind"):
            pid = os.getppid()  # the calling shell outlives this CLI; its death frees the lease
            if argv == ["heavy-release"]:
                heavy_release(lease_dir(), pid)
                return 0
            import host_probe
            load1, cores = host_probe.read_load1_and_cores()
            ok = heavy_acquire(lease_dir(), heavy_slots(cores or os.cpu_count() or 1, load1, pol["tokens"], host_probe.read_cpu_idle_pct()),
                               pid, argv[2] if len(argv) == 3 else None)
            print(pid if ok else "FULL")
            return 0 if ok else 1
    except (ValueError, OSError) as e:
        print(f"perun_policy: {e}", file=sys.stderr)
        return 2
    print(__doc__, file=sys.stderr)
    return 2


def _selftest() -> int:
    import tempfile
    d = Path(tempfile.mkdtemp())
    p = d / "policy.json"
    assert load(d / "none.json")["github_actions"] == "efficient"
    os.environ["PERUN_POLICY"] = str(d / "absent.json")
    try:
        load()
        raise AssertionError("explicit missing policy must fail closed")
    except ValueError:
        pass
    del os.environ["PERUN_POLICY"]
    p.write_text('{"local_cpu": "maximize", "github_actions": "off", "tokens": 5000, "share_learnings": "auto"}')
    pol = load(p)
    assert (pol["local_cpu"], pol["github_actions"], pol["tokens"], pol["share_learnings"]) == ("maximize", "off", 5000, "auto")
    assert pol["network"] == "efficient" and pol["auto_update"] == "on" and pol["auto_update_pr"] == "on"
    p.write_text('{"auto_update": "off"}')
    assert load(p)["auto_update"] == "off"
    for bad in ('{"tokens": "lots"}', '{"nope": 1}', '{"tokens": -1}', '{"share_learnings": "yes"}', '{"auto_update": true}', "[1]", "{"):
        p.write_text(bad)
        try:
            load(p)
        except ValueError:
            continue
        raise AssertionError(bad)
    os.environ["PERUN_POLICY"] = str(d / "set" / "p.json")
    assert set_value("tokens", "3000")["tokens"] == 3000 and set_value("local_cpu", "maximize")["local_cpu"] == "maximize"
    assert json.loads((d / "set" / "p.json").read_text()) == {"tokens": 3000, "local_cpu": "maximize"}
    for bad in (("tokens", "lots"), ("nope", "1"), ("share_learnings", "yes")):
        try:
            set_value(*bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    del os.environ["PERUN_POLICY"]
    assert [lanes(m, 8, 3) for m in ("efficient", "maximize", "off", 3)] == [4, 5, 1, 3]
    assert lanes("maximize", 8, 99) == 1
    assert [lanes("maximize", 16, 0, t) for t in ("efficient", "maximize", "off", 3, 0)] == [2, 16, 1, 3, 1]
    assert [heavy_slots(16, 0, t) for t in ("efficient", "maximize", "off", 5)] == [2, 16, 1, 5]
    assert [heavy_slots(8, 3), heavy_slots(8, 7.5), heavy_slots(8, 99), heavy_slots(1), heavy_slots(8)] == [5, 2, 2, 2, 8]
    ld = d / "leases"
    assert heavy_acquire(ld, 1, os.getpid()) and active_leases(ld) == [os.getpid()]
    assert not heavy_acquire(ld, 1, 4194301) and heavy_acquire(ld, 1, os.getpid())
    heavy_release(ld, os.getpid())
    heavy_release(ld, os.getpid())
    assert active_leases(ld) == []
    assert exclusive_holder(ld) is None and exclusive_acquire(ld, os.getpid()) and exclusive_holder(ld) == os.getpid()
    assert not exclusive_acquire(ld, os.getppid()) and exclusive_acquire(ld, os.getpid())
    exclusive_release(ld, os.getpid())
    assert exclusive_holder(ld) is None and exclusive_acquire(ld, os.getppid())
    exclusive_release(ld, os.getppid())
    print("perun_policy selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
