#!/usr/bin/env python3
"""In-process pins for the lease and lane arithmetic in .claude/skills/agentic-delivery/scripts/perun_policy.py (token_cap, free_cores,
lanes, heavy_slots, lease_dir, _alive, _leases, active_leases, tree_cpu, lane_weight, lease_load, heavy_acquire/release, the
exclusive lease and holder_pid), written to kill the mutants scripts/mutation_safety.py found alive. Run: python3
scripts/test_mutation_kills_policy.py (or pytest). Offline; only creates temp dirs and short-lived children of this process."""
import contextlib, io, os, pathlib, subprocess, sys, tempfile, time

SC = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import perun_policy as pp  # noqa: E402

NOW = 1_000_000.0
ME = os.getpid()


def dead_pid():
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def tdir():
    return pathlib.Path(tempfile.mkdtemp(prefix="pol-", dir=os.environ.get("TMPDIR"))) / "heavy"


def test_token_cap():
    assert pp.token_cap(9, "maximize") == 9
    assert pp.token_cap(9, "efficient") == 2 and pp.token_cap(1, "efficient") == 1
    assert pp.token_cap(9, "off") == 1
    assert pp.token_cap(9, 4) == 4 and pp.token_cap(3, 4) == 3 and pp.token_cap(9, 0) == 1 and pp.token_cap(9, -3) == 1 and pp.token_cap(9, 2.9) == 2
    assert pp.token_cap(9, None) == 2 and pp.token_cap(9, "anything") == 2


def test_free_cores_lanes_slots():
    assert pp.free_cores(8, 3.0) == 5 and pp.free_cores(8, None) == 8 and pp.free_cores(8, 3.5) == 4
    assert pp.free_cores(8, 3.0, 50.0) == 4 and pp.free_cores(8, 3.0, 0.0) == 0 and pp.free_cores(10, None, 33.0) == 3
    assert pp.lanes("maximize", 8, 3.0) == 5 and pp.lanes("maximize", 8, 99.0) == 1 and pp.lanes("maximize", 8, 3.0, idle_pct=25.0) == 2
    assert pp.lanes("maximize", 8, 3.0, tokens="efficient") == 2 and pp.lanes("maximize", 8, 3.0, tokens="off") == 1
    assert pp.lanes("efficient", 8) == 4 and pp.lanes("efficient", 1) == 1 and pp.lanes("efficient", 9, tokens="maximize") == 4
    assert pp.lanes("off", 8) == 1 and pp.lanes("garbage", 8) == 4 and pp.lanes(3, 8) == 3 and pp.lanes(0, 8) == 1 and pp.lanes(2.7, 8) == 2
    assert pp.lanes(6, 8, tokens="efficient") == 2 and pp.lanes(1, 8) == 1
    assert pp.heavy_slots(8, 3.0) == 5 and pp.heavy_slots(8, 7.9) == 2 and pp.heavy_slots(8, 99.0) == 2 and pp.heavy_slots(1, None) == 2
    assert pp.heavy_slots(8, 3.0, tokens="efficient") == 2 and pp.heavy_slots(8, 0.0, tokens=3) == 3 and pp.heavy_slots(8, 3.0, idle_pct=75.0) == 6


def test_lease_dir_and_alive():
    old = {k: os.environ.pop(k, None) for k in ("PERUN_HEAVY_DIR", "XDG_CACHE_HOME")}
    try:
        os.environ["PERUN_HEAVY_DIR"] = "/x/y"
        assert pp.lease_dir() == pathlib.Path("/x/y")
        del os.environ["PERUN_HEAVY_DIR"]
        os.environ["XDG_CACHE_HOME"] = "/c"
        assert pp.lease_dir() == pathlib.Path("/c/perun/heavy")
        del os.environ["XDG_CACHE_HOME"]
        assert pp.lease_dir() == pathlib.Path.home() / ".cache/perun/heavy"
        os.environ["PERUN_HEAVY_DIR"] = ""
        assert pp.lease_dir() == pathlib.Path.home() / ".cache/perun/heavy"
    finally:
        for k, v in old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    assert pp._alive(ME) and pp._alive(os.getppid())
    assert not pp._alive(0) and not pp._alive(-1) and not pp._alive(-ME) and not pp._alive(dead_pid())


def put(d, name, body):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_leases_parse():
    d = tdir()
    assert pp._leases(d, NOW) == [] and pp.active_leases(d, NOW) == []  # missing dir
    put(d, "a", f"{ME} {int(NOW) - 10}")
    assert pp._leases(d, NOW) == [(ME, int(NOW) - 10, None)]
    put(d, "a", f"{ME} {int(NOW) - 10} light")
    assert pp._leases(d, NOW) == [(ME, int(NOW) - 10, "light")] and pp.active_leases(d, NOW) == [ME]
    assert pp._leases(d, NOW, exclude=ME) == [] and pp._leases(d, NOW, exclude=ME + 1) != []
    put(d, "a", f"{ME} {int(NOW) - pp.LEASE_TTL + 1}")
    assert len(pp._leases(d, NOW)) == 1
    put(d, "a", f"{ME} {int(NOW) - pp.LEASE_TTL}")  # exactly the TTL: expired
    assert pp._leases(d, NOW) == []
    for body in (f"{dead_pid()} {int(NOW)}", "", f"{ME}", "x y", f"{ME} y", f"{ME} {int(NOW)} a b", f"{ME} {int(NOW)} a b c", "0 1"):
        put(d, "a", body)
        assert pp._leases(d, NOW) == [], body
    (d / "sub").mkdir()  # a directory entry: unreadable, ignored
    assert pp._leases(d, NOW) == []
    put(d, "a", f"{ME} {int(NOW) + 5}")  # start in the future still counts
    assert len(pp._leases(d, NOW)) == 1
    assert pp.active_leases(d) == []  # real clock: NOW-based start is long expired


def test_tree_cpu():
    t = {1: (0, 1.0), 2: (1, 2.0), 3: (2, 4.0), 4: (1, 8.0), 9: (9, 100.0)}
    assert pp.tree_cpu(t, 1) == 15.0 and pp.tree_cpu(t, 2) == 6.0 and pp.tree_cpu(t, 3) == 4.0
    assert pp.tree_cpu(t, 5) is None and pp.tree_cpu(None, 1) is None and pp.tree_cpu({}, 1) is None
    assert pp.tree_cpu(t, 9) == 100.0  # a self-parented node is counted once
    assert pp.tree_cpu({1: (2, 1.0), 2: (1, 2.0)}, 1) == 3.0  # a cycle terminates


def test_lane_weight():
    w = pp.lane_weight
    assert w("light", 0, None) == pp.LIGHT_WEIGHT == 0.25 and w("LIGHT", 0, None) == 0.25 and w("docs", 0, 99.0) == 0.25
    for k in pp.LIGHT_KINDS:
        assert w(k, 0, 99.0) == 0.25
    assert w("heavy", 9999, 0.0) == 1.0 and w("build", 0, None) == 1.0
    assert w(None, 60, 14.9) == 0.25 and w(None, 60, 15.0) == 1.0 and w(None, 59.9, 0.0) == 1.0 and w(None, 60, None) == 1.0 and w(None, 600, 0.0) == 0.25


def test_lease_load():
    d = tdir()
    assert pp.lease_load(d, NOW) == 0
    put(d, "h", f"{ME} {int(NOW) - 5}")
    assert pp.lease_load(d, NOW, table={}) == 1.0  # young, unmeasured
    put(d, "h", f"{ME} {int(NOW) - 100}")
    assert pp.lease_load(d, NOW, table={ME: (1, 3.0)}) == 0.25  # old and idle -> light
    assert pp.lease_load(d, NOW, table={ME: (1, 30.0)}) == 1.0
    assert pp.lease_load(d, NOW, table={ME: (1, 3.0), os.getppid(): (1, 0.0)}) == 0.25
    assert pp.lease_load(d, NOW, exclude=ME, table={}) == 0
    put(d, "h", f"{ME} {int(NOW) - 100} build")
    assert pp.lease_load(d, NOW, table={ME: (1, 0.0)}) == 1.0  # declared kind ignores cpu
    put(d, "h", f"{ME} {int(NOW) - 100} doc")
    assert pp.lease_load(d, NOW, table={}) == 0.25
    other = subprocess.Popen(["sleep", "30"])
    try:
        put(d, "o", f"{other.pid} {int(NOW) - 100}")
        assert pp.lease_load(d, NOW, table={}) == 0.25 + 1.0  # unmeasured undeclared old lease -> fail closed
        assert pp.lease_load(d, NOW, table={other.pid: (1, 0.0)}) == 0.5
    finally:
        other.kill()
        other.wait()


def test_acquire_release():
    d = tdir()
    kids = [subprocess.Popen(["sleep", "30"]) for _ in range(3)]
    try:
        a, b, c = (k.pid for k in kids)
        assert pp.heavy_acquire(d, 2, a) and pp.heavy_acquire(d, 2, b)
        assert (d / str(a)).read_text().split()[0] == str(a) and abs(int((d / str(a)).read_text().split()[1]) - time.time()) < 60
        assert not pp.heavy_acquire(d, 2, c) and not (d / str(c)).exists()
        assert pp.heavy_acquire(d, 2, a)  # re-acquire refreshes, own lease excluded
        assert not pp.heavy_acquire(d, 1, b)  # 1 other lease >= 1 slot
        pp.heavy_release(d, a)
        pp.heavy_release(d, a)  # idempotent
        assert not (d / str(a)).exists() and pp.heavy_acquire(d, 2, c)
        assert sorted(pp.active_leases(d)) == sorted([b, c])
        pp.heavy_release(d, b)
        pp.heavy_release(d, c)
        assert pp.heavy_acquire(d, 1, a, kind="light") and (d / str(a)).read_text().split()[2] == "light"
        assert pp.heavy_acquire(d, 1, b, kind="light") and pp.heavy_acquire(d, 1, c, kind="Doc-x")  # 0.25 + 0.25 < 1
        for bad in ("", "1x", "-a", "a" * 17, "a b", "a_b"):
            try:
                pp.heavy_acquire(d, 9, a, kind=bad)
            except ValueError as e:
                assert repr(bad) in str(e)
            else:
                raise AssertionError(f"kind {bad!r} accepted")
        assert pp.heavy_acquire(d, 9, a, kind="a" * 16)
    finally:
        for k in kids:
            k.kill()
            k.wait()


def test_exclusive_lease():
    d = tdir()
    f = d.parent / "heavy.exclusive"
    other = subprocess.Popen(["sleep", "30"])
    try:
        assert pp.exclusive_holder(d) is None
        assert pp.exclusive_acquire(d, ME) and pp.exclusive_holder(d) == ME
        assert f.read_text().split()[0] == str(ME) and abs(int(f.read_text().split()[1]) - time.time()) < 60
        assert not list(d.parent.glob("*.tmp"))
        assert not pp.exclusive_acquire(d, other.pid) and pp.exclusive_holder(d) == ME  # held by a live pid
        assert not list(d.parent.glob("*.tmp"))
        assert pp.exclusive_acquire(d, ME)  # own lease replaced
        pp.exclusive_release(d, other.pid)  # not the holder: no-op
        assert pp.exclusive_holder(d) == ME
        old = time.time() - pp.LEASE_TTL - 5
        os.utime(f, (old, old))
        assert pp.exclusive_holder(d) is None  # stale mtime expires a live pid
        assert pp.exclusive_acquire(d, other.pid) and pp.exclusive_holder(d) == other.pid  # stale lease taken over
        old = time.time() - pp.LEASE_TTL + 60
        os.utime(f, (old, old))
        assert pp.exclusive_holder(d) == other.pid  # still fresh just inside the TTL
        pp.exclusive_renew(d, ME)  # not the holder: no-op
        assert abs(f.stat().st_mtime - old) < 5
        pp.exclusive_renew(d, other.pid)
        assert time.time() - f.stat().st_mtime < 30
        pp.exclusive_release(d, other.pid)
        pp.exclusive_release(d, other.pid)
        assert not f.exists() and pp.exclusive_holder(d) is None
        f.write_text(f"{dead_pid()} 1")
        assert pp.exclusive_holder(d) is None and pp.exclusive_acquire(d, ME) and pp.exclusive_holder(d) == ME  # dead holder replaced
        for body in ("", "x", f"{ME}", f"{ME} 1 2", "a b"):
            f.write_text(body)
            assert pp.exclusive_holder(d) is None, body
        assert pp.exclusive_acquire(d, ME)  # malformed lease replaced
        pp.exclusive_release(d, ME)
        assert not f.exists()
    finally:
        other.kill()
        other.wait()


def test_ppid_and_holder_pid():
    assert pp._ppid(ME) == os.getppid() and pp._ppid(os.getppid()) > 0
    assert pp._ppid(dead_pid()) in (-1, 0) or pp._ppid(dead_pid()) > 0
    pp_ = os.getppid()
    old = os.environ.pop("PERUN_HOLDER_PID", None)
    try:
        def call(v):
            if v is None:
                os.environ.pop("PERUN_HOLDER_PID", None)
            else:
                os.environ["PERUN_HOLDER_PID"] = v
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                r = pp.holder_pid()
            return r, err.getvalue()
        assert call(None) == (pp_, "") and call("") == (pp_, "") and call(str(pp_)) == (pp_, "")
        for bad in ("0", "1", "-1", "abc", "2.5", str(ME), "999999999"):
            r, e = call(bad)
            assert r == pp_ and f"ignoring PERUN_HOLDER_PID={bad!r}" in e and f"holder is pid {pp_}" in e and e.endswith("\n"), bad
        code = ("import sys; sys.path.insert(0, %r); import perun_policy as p; print(p.holder_pid())" % os.path.dirname(pp.__file__))
        out = subprocess.run(["sh", "-c", f'"{sys.executable}" -c "{code}"; true'], env={**os.environ, "PERUN_HOLDER_PID": str(ME)},
                             capture_output=True, text=True)
        assert out.stdout.strip() == str(ME) and out.stderr == "", out  # the grandparent is honored
        out = subprocess.run(["sh", "-c", f'"{sys.executable}" -c "{code}"; true'], env={**os.environ, "PERUN_HOLDER_PID": str(ME + 1)},
                             capture_output=True, text=True)
        assert out.stdout.strip() != str(ME + 1) and "ignoring" in out.stderr
    finally:
        os.environ.pop("PERUN_HOLDER_PID", None)
        if old is not None:
            os.environ["PERUN_HOLDER_PID"] = old


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
