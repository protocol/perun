#!/usr/bin/env python3
"""preflight.py CONFIG.json [--all] [--cache FILE] — run cheap gates first, report every failure together.

WHY: a 20-37 minute commit/push hook cycle failed late on two cheap gates (lint, privacy grep) that take seconds,
costing ~3 wasted cycles. Run this before the hook: all cheap gates run (never stopping at the first failure) and
every failure prints together; expensive gates run only when every cheap gate passed, or always with --all.
CONFIG is JSON, gates in order:
  {"gates": [{"name": "lint", "command": "ruff check .", "cheap": true, "timeout": 60},
             {"name": "tests", "command": "pytest -q", "timeout": 1800}]}
`command` is split with shlex and run WITHOUT a shell (no pipes, globs, `&&`; wrap those in a script file).
Optional top-level `"require_files": [".env.production"]`: each missing path prints `WARN preflight: required file missing` on stderr (warn only, no exit effect).
`cheap` defaults false; `timeout` seconds defaults to 600. Per-gate wall time is merged into --cache (default
.preflight-times.json, keep it gitignored) and the 3 slowest gates of this run print last, to show what to make cheap.
Output, one line per gate: PASS | FAIL (exit N) | TIMEOUT | COULD_NOT_RUN (command not startable) | SKIPPED.
Exit: 0 all ran and passed; 1 any FAIL/TIMEOUT; 3 any COULD_NOT_RUN or SKIPPED with no FAIL; 2 bad config.
After the gates, `clock_lint.py` and `env_lint.py` (`--base origin/main`) run as advisory steps (`WARN clock_lint ...` / `WARN env_lint ...` lines; no exit effect; silently skipped when origin/main or a repo is absent).
A gate that cannot start is never a pass. Timeouts use subprocess timeout only: the direct child is killed, but
grandchildren it spawned are NOT (no process-group kill); keep gate commands single-process or self-limiting.
"""
import argparse, json, os, shlex, subprocess, sys, tempfile, time


def run_gate(g):
    """(status, seconds, detail) for one gate."""
    t = time.monotonic()
    try:
        p = subprocess.run(shlex.split(g["command"]), capture_output=True, text=True, timeout=g.get("timeout", 600))
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.monotonic() - t, f"over {g.get('timeout', 600)}s"
    except (OSError, ValueError, IndexError) as e:  # missing binary, not executable, bad quoting, empty command
        return "COULD_NOT_RUN", time.monotonic() - t, str(e)
    out = (p.stdout + p.stderr).strip().splitlines()
    return ("PASS" if p.returncode == 0 else "FAIL"), time.monotonic() - t, \
        "" if p.returncode == 0 else f"exit {p.returncode}: " + " | ".join(out[-3:])


def preflight(gates, run_all=False):
    """Return [(name, status, seconds, detail)] in config order."""
    res, cheap_ok = [], True
    for cheap in (True, False):
        for g in gates:
            if bool(g.get("cheap")) != cheap:
                continue
            if not cheap and not cheap_ok and not run_all:
                res.append((g["name"], "SKIPPED", 0.0, "cheap gate(s) failed"))
            else:
                s, sec, d = run_gate(g)
                res.append((g["name"], s, sec, d))
                cheap_ok = cheap_ok and (s == "PASS" or not cheap)
    return res


def selftest():
    py = lambda c, **k: {"name": c[:6], "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(c)}", **k}
    gates = [py("import sys;sys.exit(1)", cheap=True), py("pass", cheap=True), {"name": "nope", "command": "/no/such/bin x", "cheap": True},
             py("import time;time.sleep(5)", cheap=True, timeout=0.3), py("pass")]
    r = preflight(gates)
    assert [x[1] for x in r] == ["FAIL", "PASS", "COULD_NOT_RUN", "TIMEOUT", "SKIPPED"], r  # all cheap ran; expensive skipped
    assert preflight(gates, run_all=True)[-1][1] == "PASS"
    assert preflight([{"name": "e", "command": ""}])[0][1] == "COULD_NOT_RUN"
    with tempfile.TemporaryDirectory() as t:
        cfg, cache = os.path.join(t, "c.json"), os.path.join(t, "times.json")
        json.dump({"gates": [py("pass", cheap=True)]}, open(cfg, "w"))
        me = [sys.executable, os.path.abspath(__file__), cfg, "--cache", cache]
        o = subprocess.run(me, capture_output=True, text=True)
        assert o.returncode == 0 and "PASS" in o.stdout and "slowest" in o.stdout, o
        assert "pass" in json.load(open(cache)), "wall time cached"
        json.dump({"gates": [py("import sys;sys.exit(2)", cheap=True), py("pass")]}, open(cfg, "w"))
        assert subprocess.run(me, capture_output=True).returncode == 1
        json.dump({"gates": [{"name": "x", "command": "/no/such/bin"}]}, open(cfg, "w"))
        assert subprocess.run(me, capture_output=True).returncode == 3
        open(cfg, "w").write("{")
        assert subprocess.run(me, capture_output=True).returncode == 2
        for bad in ({"timeout": "5"}, {"timeout": 0}, {"timeout": True}, {"cheap": "yes"}):
            json.dump({"gates": [py("pass", **bad)]}, open(cfg, "w"))
            assert subprocess.run(me, capture_output=True).returncode == 2, bad
        json.dump({"gates": [py("pass", cheap=True)]}, open(cfg, "w"))
        for junk in ("[1, 2]", "\xff not json"):  # non-object / unreadable cache is ignored, not a traceback
            open(cache, "w", errors="surrogateescape").write(junk)
            o = subprocess.run(me, capture_output=True, text=True)
            assert o.returncode == 0 and "Traceback" not in o.stderr, o
            assert isinstance(json.load(open(cache)), dict)
        o = subprocess.run(me[:-1] + [os.path.join(t, "no", "dir", "c.json")], capture_output=True, text=True)
        assert o.returncode == 0 and "WARN" in o.stderr and "Traceback" not in o.stderr, o
    print("selftest ok")


def clock_advisory(base="origin/main", tool="clock_lint.py"):
    """Advisory lines from clock_lint.py (real-clock reads, date-literal time bombs; or env_lint.py via `tool`) on files changed vs `base`.
    [] (silently) when not in a repo, `base` is missing, or clock_lint cannot start/finishes late; never raises."""
    try:
        if subprocess.run(["git", "rev-parse", "--verify", "-q", base], capture_output=True).returncode:
            return []
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), tool),
                            "--base", base, "--deadline", "5"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [l for l in p.stdout.splitlines() if l and not l.startswith("COULD_NOT_CHECK")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config", nargs="?")
    ap.add_argument("--all", action="store_true", help="run expensive gates even if a cheap gate failed")
    ap.add_argument("--cache", default=".preflight-times.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest() or 0
    try:
        cfg = json.load(open(a.config))
        gates = cfg["gates"]
        need = cfg.get("require_files", [])
        assert isinstance(need, list) and all(isinstance(x, str) for x in need), "require_files must be a list of paths"
        assert gates and all(g["name"] and g["command"] for g in gates), "empty name/command"
        for g in gates:
            t = g.get("timeout", 600)
            assert isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0, "timeout must be a positive number"
            assert isinstance(g.get("cheap", False), bool), "cheap must be true or false"
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as e:
        print(f"preflight: bad config: {e!r}", file=sys.stderr)
        return 2
    for f in need:  # never removes or copies anything: a missing env template the build needs is named, not silently absent
        if not os.path.exists(f):
            print(f"WARN preflight: required file missing: {f} (env templates such as .env.production must survive gate prep)", file=sys.stderr)
    res = preflight(gates, a.all)
    for n, s, sec, d in res:
        print(f"{s} {n} ({sec:.1f}s){': ' + d if d else ''}")
    try:
        times = json.load(open(a.cache))
        times = times if isinstance(times, dict) else {}
    except (OSError, ValueError):
        times = {}
    times.update({n: round(sec, 2) for n, s, sec, _ in res if s != "SKIPPED"})
    try:
        tmp = f"{a.cache}.{os.getpid()}.tmp"
        with open(tmp, "w") as fh:
            json.dump(times, fh, indent=1)
        os.replace(tmp, a.cache)
    except (OSError, TypeError, ValueError) as e:
        print(f"WARN: preflight cache not written: {e}", file=sys.stderr)
    sys.stdout.flush()
    for tool in ("clock_lint", "env_lint"):
        for line in clock_advisory(tool=tool + ".py"):
            print(f"WARN {tool} {line}")
    top = sorted((r for r in res if r[1] != "SKIPPED"), key=lambda r: -r[2])[:3]
    print("slowest: " + ", ".join(f"{n} {sec:.1f}s" for n, _, sec, _ in top))
    st = {s for _, s, _, _ in res}
    return 1 if st & {"FAIL", "TIMEOUT"} else 3 if st & {"COULD_NOT_RUN", "SKIPPED"} else 0


if __name__ == "__main__":
    sys.exit(main())
