#!/usr/bin/env python3
"""In-process pins for .claude/skills/agentic-delivery/scripts/heavy_gate.py, written to kill the mutants that scripts/mutation_safety.py
found alive: command classification (is_heavy, strip_wrappers, scoped_pytest, tokens, segments), the load/lease verdict, the
deny-bypass ledger and the hook's stdin/stdout contract. Run: python3 scripts/test_mutation_kills_heavy_gate.py (or pytest). Offline;
leases are real files owned by this process or short-lived children (own PIDs only)."""
import contextlib, io, json, os, pathlib, subprocess, sys, tempfile, time

SC = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import heavy_gate as hg  # noqa: E402
import perun_policy as pp  # noqa: E402

PAT = hg.DEFAULT_PATTERNS
HEAVY = [
    "pytest", "pytest -q", "pytest tests/", "pytest -k foo", "pytest a.py b.py c.py", "pytest --ignore x a.py", "python -m pytest", "python3 -m pytest tests",
    "python3.11 -m pytest", "uv run pytest", "uv run --with x pytest", "poetry run pytest", "pipx run pytest", "command pytest", "cd x && pytest", "ls; pytest", "ls | pytest",
    "npm test", "npm run test", "yarn test", "pnpm test", "bun test", "bun run test", "cargo test", "cargo nextest run", "go test ./...", "npx jest", "jest", "vitest",
    "pnpm exec vitest", "playwright test", "npx playwright test", "next build", "npx next build", "npm run build", "pnpm run build", "tsc -b", "npx tsc -b",
    "bash -c 'pytest'", "bash -lc 'npm test'", "sh -c \"cargo test\"", "zsh -c pytest", "bash -o pipefail -c 'pytest'", "bash -c 'echo \"x'", "time pytest",
    "env FOO=1 pytest", "FOO=1 pytest", "/usr/bin/env pytest", "nice -n 5 pytest", "nice pytest", "timeout 60 pytest", "timeout -s KILL 5 pytest", "sudo -u bob pytest",
    "sudo pytest", "nohup pytest", "stdbuf -oL pytest", "xargs -I{} pytest {}", "xargs -n 1 pytest", "xargs pytest", "env -u X pytest", "env -- pytest",
    "env -C /tmp pytest", "caffeinate -t 5 pytest", "pytest tests/test_a.py::T::t tests/b.py tests/c.py", "pytest 'a b.py'", "pytest $F", "pytest *.py", "pytest a.txt",
    "pytest -p x a.py b.py c.py", "pytest --lf", "pytest --cache-dir x a.py", "bash -c 'a; pytest'", "cat <<EOF\nx\nEOF\npytest",
]
LIGHT = [
    "", "ls", "echo pytest", "git commit -m 'fix; pytest'", "grep -rn pytest .", "pytest --version", "pytest --help", "pytest -h", "pytest --collect-only", "pytest --co tests/",
    "pytest a.py", "pytest a.py::test_x", "pytest a.py::test_x[p1]", "pytest tests/a.py -k 'x y'", "pytest -q a.py b.py", "pytest -x a.py", "pytest -vv a.py", "pytest -n4 a.py",
    "pytest -rA a.py", "pytest --tb=short a.py", "pytest --tb short a.py", "pytest --lf a.py", "pytest --maxfail=2 a.py", "pytest -k foo a.py", "pytest -kfoo a.py",
    "pytest -m slow a.py", "pytest -p no:cacheprovider a.py", "pytest --cov=x a.py", "python -m pytest a.py", "uv run pytest a.py", "cd x && pytest a.py",
    "playwright install", "playwright install chromium", "npm run lint", "cargo build", "cat <<EOF\npytest\nEOF", "pytest 'unclosed", "bash -c 'echo hi'",
    "bash -c 'git commit -m pytest'", "bash script.sh", "bash -c 'pytest --version'", "time ls", "FOO=pytest ls", "vitest --help", "go test --help",
    "npm test --help", "tsc --version", "pytest a.py b.py", "pytest tests/a.py::T::t", "pytest --durations 5 a.py", "pytest --rootdir . a.py", "pytest -o x=1 a.py", "pytest -W ignore a.py",
]


def test_is_heavy_table():
    for c in HEAVY:
        assert hg.is_heavy(c, PAT), f"should be heavy: {c!r}"
    for c in LIGHT:
        assert not hg.is_heavy(c, PAT), f"should be light: {c!r}"
    assert not hg.is_heavy(None, PAT)


def test_custom_patterns_replace_the_defaults():
    assert hg.is_heavy("make check", [r"make check\b"]) and not hg.is_heavy("pytest", [r"make check\b"])
    assert hg.is_heavy("cd d && make check", [r"make check\b"])
    assert not hg.is_heavy("echo make check", [r"make check\b"])


def test_heavy_patterns_env():
    old = os.environ.pop("PERUN_HEAVY_PATTERNS", None)
    try:
        assert hg.heavy_patterns() == hg.DEFAULT_PATTERNS
        os.environ["PERUN_HEAVY_PATTERNS"] = "make a\n\n  \nmake b\n"
        assert hg.heavy_patterns() == ["make a", "make b"]
        os.environ["PERUN_HEAVY_PATTERNS"] = ""
        assert hg.heavy_patterns() == hg.DEFAULT_PATTERNS
    finally:
        os.environ.pop("PERUN_HEAVY_PATTERNS", None)
        if old is not None:
            os.environ["PERUN_HEAVY_PATTERNS"] = old


def test_tokens_and_segments():
    assert hg.tokens("a;b") == ["a", ";", "b"]
    assert hg.tokens("a && b | c") == ["a", "&&", "b", "|", "c"]
    assert hg.tokens("a 'b c' \"d;e\"") == ["a", "b c", "d;e"]
    assert hg.tokens("a\tb\r") == ["a", "b"]
    assert hg.tokens("cat <<EOF\nrm -rf x\nEOF\nls") == ["cat", "<<", "EOF", "\n", "ls"]
    assert hg.tokens("cat <<EOF\nx\n EOF\nEOF\nls") == ["cat", "<<", "EOF", "\n", "EOF", "\n", "ls"]
    assert hg.tokens("cat <<EOF\nEOF \nls") == ["cat", "<<", "EOF", "\n", "ls"]
    assert hg.tokens("x:y[1]") == ["x", ":", "y", "[", "1", "]"] and hg.tokens("a > f") == ["a", ">", "f"]
    assert hg.segments("a b; c | d && e") == [["a", "b"], ["c"], ["d"], ["e"]]
    assert hg.segments("a b") == [["a", "b"]]
    assert hg.segments("sed -i '' x") == [["sed", "-i", "", "x"]]
    assert hg.segments("a\nb") == [["a"], ["b"]]
    assert hg.segments("a > f") == [["a"], ["f"]]
    for bad in ("echo 'x", 'echo "x'):
        try:
            hg.segments(bad)
        except ValueError:
            continue
        raise AssertionError(f"no ValueError for {bad!r}")


def test_strip_wrappers_exact():
    s = hg.strip_wrappers
    assert s([]) == []
    assert s(["pytest", "-q"]) == ["pytest", "-q"]
    assert s(["/usr/bin/env", "FOO=1", "pytest"]) == ["pytest"]
    assert s(["env", "-u", "X", "pytest"]) == ["pytest"]
    assert s(["env", "-i", "pytest"]) == ["pytest"]
    assert s(["env", "--", "pytest"]) == ["pytest"]
    assert s(["env", "-", "pytest"]) == ["-", "pytest"]
    assert s(["nice", "-n", "5", "pytest", "x"]) == ["pytest", "x"]
    assert s(["nice", "-n5", "pytest"]) == ["pytest"]
    assert s(["timeout", "60", "pytest"]) == ["pytest"]
    assert s(["timeout", "-s", "KILL", "60", "pytest"]) == ["pytest"]
    assert s(["timeout", "-k", "1", "--foreground", "60", "pytest"]) == ["pytest"]
    assert s(["sudo", "-u", "bob", "pytest"]) == ["pytest"]
    assert s(["time", "-f", "%e", "pytest"]) == ["pytest"]
    assert s(["xargs", "-I", "{}", "pytest", "{}"]) == ["pytest", "{}"]
    assert s(["nohup", "setsid", "pytest"]) == ["pytest"]
    assert s(["uv", "run", "--with", "x", "pytest"]) == ["pytest"]
    assert s(["uv", "run", "-q", "pytest"]) == ["pytest"]
    assert s(["npx", "-p", "pkg", "jest"]) == ["jest"]
    assert s(["npx", "jest"]) == ["jest"]
    assert s(["python", "-m", "pytest"]) == ["pytest"]
    assert s(["python3.12", "-m", "pytest", "a.py"]) == ["pytest", "a.py"]
    assert s(["/usr/bin/python3", "-m", "pytest"]) == ["pytest"]
    assert s(["poetry", "run", "pytest"]) == ["pytest"]
    assert s(["pnpm", "exec", "vitest"]) == ["vitest"]
    assert s(["command", "pytest"]) == ["pytest"]
    assert s(["command", "-v", "grype"]) == [] and s(["command", "-V", "grype"]) == [] and s(["nice", "command", "-v", "x"]) == []  # presence check
    assert s(["uvx", "--from", "x", "pytest"]) == ["pytest"] and s(["bunx", "jest"]) == ["jest"] and s(["pnpm", "dlx", "vitest"]) == ["vitest"]
    assert s(["python", "x.py"]) == ["python", "x.py"]
    assert s(["uv"]) == ["uv"]
    assert s(["FOO=1"]) == []
    assert s(["env"]) == []
    assert s(["git", "status"]) == ["git", "status"]


def test_scoped_pytest_exact():
    f = hg.scoped_pytest
    assert f(["a.py"]) and f(["a.py", "b.py"]) and f(["a/b_c-d.py::T::t[x-1]"])
    assert not f([]) and not f(["a.py", "b.py", "c.py"]) and not f(["tests"]) and not f(["a.py", "dir/"])
    assert f(["-k", "x", "a.py"]) and f(["-kx", "a.py"]) and f(["--tb=short", "a.py"]) and f(["--tb", "short", "a.py"])
    assert f(["-n4", "a.py"]) and f(["-rA", "a.py"]) and f(["-qq", "a.py"]) and f(["-x", "a.py"]) and f(["--lf", "a.py"])
    assert not f(["--ignore", "x", "a.py"]) and not f(["--cache-dir=x", "a.py"]) and not f(["-z", "a.py"]) and not f(["--kfoo", "a.py"])
    assert not f(["-k"]) and not f(["-k", "a.py"])  # the value consumes the file
    assert not f(["a.py;b"]) and not f(["a.py\n"]) and not f(["a.pyc"]) and not f(["x.py::"]) and not f(["$F"])


def test_float_env():
    k = "PERUN_TEST_FLOAT_ENV"
    os.environ.pop(k, None)
    assert hg._float_env(k) is None
    os.environ[k] = ""
    assert hg._float_env(k) is None
    os.environ[k] = "2.5"
    assert hg._float_env(k) == 2.5
    os.environ[k] = "0"
    assert hg._float_env(k) == 0.0
    del os.environ[k]


class Env:
    """Set env vars for a with-block and restore them after."""

    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


@contextlib.contextmanager
def fleet(n=0):
    """A lease dir with `n` live leases owned by sleeping children, plus a fresh empty policy."""
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t) / "heavy"
        kids = [subprocess.Popen(["sleep", "60"]) for _ in range(n)]
        try:
            d.mkdir()
            for k in kids:
                (d / str(k.pid)).write_text(f"{k.pid} {int(time.time())}")
            pol = pathlib.Path(t) / "policy.json"
            pol.write_text("{}")
            with Env(PERUN_HEAVY_DIR=d, PERUN_POLICY=pol, PERUN_HEAVY_PATTERNS=None, PERUN_GATE_LOAD1=1, PERUN_GATE_CORES=4, PERUN_GATE_FREE_RAM_PCT=60):
                yield d
        finally:
            for k in kids:
                k.kill()
                k.wait()


def test_verdict_readings_and_holds():
    with fleet():
        assert hg.verdict() == (None, 1.0, 4, 60.0)
        with Env(PERUN_GATE_LOAD1=9):
            r = hg.verdict()
            assert r[0] == "HOLD load-high" and r[1:] == (9.0, 4, 60.0)
        with Env(PERUN_GATE_LOAD1=4):
            assert hg.verdict()[0] is None  # load1 == cores is not above
        with Env(PERUN_GATE_FREE_RAM_PCT=3):
            r = hg.verdict()
            assert r[0] == "HOLD low-ram" and r[3] == 3.0
        with Env(PERUN_GATE_CORES=0):
            assert hg.verdict()[2] >= 1  # 0 falls back to the host core count
        with Env(PERUN_GATE_LOAD1=0):
            assert hg.verdict()[1] == 0.0
        assert pp.exclusive_acquire(pathlib.Path(os.environ["PERUN_HEAVY_DIR"]), os.getpid())
        assert hg.verdict() == ("HOLD gate running: wait", 1.0, 4, 60.0)


def test_verdict_lease_slots():
    with fleet(2) as d:
        with Env(PERUN_GATE_LOAD1=7, PERUN_GATE_CORES=8):
            r = hg.verdict()
            assert r[0] == "HOLD heavy-lease-full 2/2", r
            assert hg.verdict("maximize")[0] is None  # every core is a slot
            assert hg.verdict("efficient")[0] == r[0]
        with Env(PERUN_GATE_LOAD1=1, PERUN_GATE_CORES=4):
            assert hg.verdict()[0] is None  # 3 slots, 2 held
    with fleet(3):
        with Env(PERUN_GATE_LOAD1=1, PERUN_GATE_CORES=4):
            assert hg.verdict()[0] == "HOLD heavy-lease-full 3/3"
            assert hg.verdict("maximize")[0] == "HOLD heavy-lease-full 3/4" or hg.verdict("maximize")[0] is None


def test_bypass_ledger():
    with fleet() as d:
        led = d.parent / "heavy-denies.json"
        b = hg._bypass
        assert b("pytest", "/w", False, now=100) is False and not led.exists() or json.loads(led.read_text()) == {}
        for i in range(3):
            assert b("pytest  -q", "/w", True, now=100 + i) is False
        assert len(json.loads(led.read_text())) == 1
        assert b("pytest -q", "/other", False, now=105) is False  # another cwd
        assert b("pytest -x", "/w", False, now=105) is False  # another command
        assert b("pytest   -q", "/w", False, now=105) is True  # whitespace-normalized, third deny reached
        assert json.loads(led.read_text()) == {}  # the entry reset
        assert b("pytest -q", "/w", False, now=106) is False
        for i in range(2):
            b("pytest -q", "/w", True, now=200 + i)
        assert b("pytest -q", "/w", False, now=201) is False  # only two denies
        b("pytest -q", "/w", True, now=202)
        assert b("pytest -q", "/w", False, now=200 + hg.WINDOW - 1) is True
        for i in range(3):
            b("pytest -q", "/w", True, now=300 + i)
        assert b("pytest -q", "/w", False, now=302 + hg.WINDOW) is False  # the denies aged out
        assert b("pytest -q", "/w", False, now=300 + hg.WINDOW - 1) is False  # (and were pruned)
        led.write_text("not json")
        assert b("pytest -q", "/w", True, now=1) is False  # unreadable ledger keeps the deny
        led.write_text("[1]")
        assert b("pytest -q", "/w", False, now=1) is False
        led.unlink()
        led.mkdir()  # a directory where the ledger should be: I/O error, still False
        assert b("pytest -q", "/w", True, now=1) is False


def hook(cmd, cwd="/w", raw=None):
    """Run heavy_gate.main() on a PreToolUse payload; -> (exit code, stdout)."""
    old, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(raw if raw is not None else json.dumps({"tool_input": {"command": cmd}, "cwd": cwd}))
    try:
        with contextlib.redirect_stdout(out):
            rc = hg.main()
    finally:
        sys.stdin = old
    return rc, out.getvalue()


def test_main_contract():
    with fleet() as d:
        assert hook("ls") == (0, "") and hook("pytest")[1] == ""  # idle host: allowed, silent
        assert hook("", raw="not json") == (0, "") and hook("", raw="[]") == (0, "") and hook("", raw='{"tool_input": null}') == (0, "")
        assert hook("pytest a.py") == (0, "")
        with Env(PERUN_GATE_LOAD1=99, PERUN_GATE_CORES=2):
            assert hook("ls") == (0, "")
            rc, out = hook("pytest -q")
            assert rc == 0
            o = json.loads(out)["hookSpecificOutput"]
            assert o["hookEventName"] == "PreToolUse" and o["permissionDecision"] == "deny"
            assert o["permissionDecisionReason"] == ("machine busy (load 99.0/2 cores, RAM 60% free; HOLD load-high): "
                                                     "wait and retry, or narrow the command (one test file, a -k filter, a smaller scan path)")
            assert hook("pytest -q")[1] and hook("pytest -q")[1]  # denies 2 and 3
            rc, out = hook("pytest -q")  # the 4th attempt is allowed with a WARN
            o = json.loads(out)["hookSpecificOutput"]
            assert rc == 0 and "permissionDecision" not in o and o["hookEventName"] == "PreToolUse"
            assert o["additionalContext"].startswith("WARN: machine busy (HOLD load-high) but this command was denied 3 times in 30 min;")
            assert json.loads(hook("pytest -q")[1])["hookSpecificOutput"]["permissionDecision"] == "deny"  # the entry reset
            assert json.loads(hook("pytest -q", cwd="/elsewhere")[1])["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert hook("pytest -q", cwd=None)[1]
        assert pp.exclusive_acquire(d, os.getpid())
        for _ in range(6):  # a train gate's deny is never counted or bypassed
            o = json.loads(hook("pytest -q")[1])["hookSpecificOutput"]
            assert o["permissionDecision"] == "deny" and "HOLD gate running: wait" in o["permissionDecisionReason"]
        assert not (d.parent / "heavy-denies.json").exists() or "pytest" not in (d.parent / "heavy-denies.json").read_text()
        pp.exclusive_release(d, os.getpid())
        assert hook("pytest -q")[1] == ""


def test_main_policy_errors_fall_back_to_efficient():
    with fleet() as d:
        (d.parent / "policy.json").write_text("{bad")
        with Env(PERUN_GATE_LOAD1=99, PERUN_GATE_CORES=2):
            assert "deny" in hook("pytest")[1]
        (d.parent / "policy.json").write_text('{"local_cpu": "maximize"}')
        with Env(PERUN_GATE_LOAD1=7, PERUN_GATE_CORES=8):
            assert hook("pytest")[1] == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
