#!/usr/bin/env python3
"""fitness_tick.py — run every fix's fitness check once per operating-loop tick; close a fix only on evidence.

WHY: a fix with no executable check regresses silently, and a fix closed on one lucky run was never observed holding.
Every fix ships ONE executable file in the fitness dir (default `.perun/fitness/`): exit 0 = healthy, exit 1 = broken,
its first output line is the reason. The operating loop calls `fitness_tick.py` each tick.

  fitness_tick.py [--dir D] [--state F]            run all executables in D (sorted); print `ALARM name: reason` per
                                                   failing check (one line each) and `ok name` per pass; exit 1 on any
                                                   ALARM. Records consecutive passes per check in F (default
                                                   `.perun/fitness-state.json`). Non-executable files are ignored; a check
                                                   that times out (60s) or cannot start is an ALARM.
  fitness_tick.py closable NAME [--dir D] [--state F] [--root R]
                                                   exit 0 only when NAME exists in D, has >= 2 consecutive passing
                                                   ticks (two real runs), AND a real caller exists under R (default `.`):
                                                   a hook/settings/package JSON, CI workflow, `.sh` or Makefile line that
                                                   runs it (`python3|bash|sh ...fitness_tick.py` or `./...`), or a loop
                                                   entry (`loop.md`, a `routines/` file) whose line starts with that command.
                                                   A prose mention or a comment does not count.
                                                   Otherwise exit 1 with the one missing reason.
Exit 2 on usage error. Side effects: the state file write. Never edits or deletes a check.
"""
import json
import os
import re
import subprocess
import sys

NEED = 2


def args(argv):
    o = {"--dir": ".perun/fitness", "--state": ".perun/fitness-state.json", "--root": "."}
    rest = []
    it = iter(argv)
    for a in it:
        if a in o:
            o[a] = next(it, "")
        else:
            rest.append(a)
    return o, rest


def load(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return {}


def tick(o):
    st, bad = load(o["--state"]), 0
    names = sorted(n for n in os.listdir(o["--dir"]) if os.access(os.path.join(o["--dir"], n), os.X_OK)) \
        if os.path.isdir(o["--dir"]) else []
    if not names:
        print(f"ALARM no executable fitness checks in {o['--dir']}: nothing is being verified")
        return 2
    for n in names:
        try:
            r = subprocess.run([os.path.join(o["--dir"], n)], capture_output=True, text=True, timeout=60)
            ok, why = r.returncode == 0, ((r.stdout + r.stderr).strip().splitlines() or [f"exit {r.returncode}"])[0]
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, why = False, f"did not run: {e}"
        st[n] = {"pass": st.get(n, {}).get("pass", 0) + 1 if ok else 0}
        print(f"ok {n}" if ok else f"ALARM {n}: {why}")
        bad += not ok
    os.makedirs(os.path.dirname(o["--state"]) or ".", exist_ok=True)
    json.dump(st, open(o["--state"], "w"), indent=1)
    return 1 if bad else 0


def has_caller(o):
    skip = {os.path.realpath(__file__), os.path.realpath(o["--state"])}
    r = subprocess.run(["grep", "-rIn", "--exclude-dir=.git", "--exclude=test*", "-F", "fitness_tick.py", o["--root"]],
                       capture_output=True, text=True)
    for ln in r.stdout.splitlines():
        f, _, txt = ln.split(":", 2)
        low, base = "/" + f.lower(), os.path.basename(f.lower())
        if os.path.realpath(f) in skip:
            continue
        # executable wiring only: an interpreter or ./path invocation, never a prose mention or a comment
        run = r"(?:(?:python3?|bash|sh)\s+\S*|\./\S*)fitness_tick\.py"
        if base == "loop.md" or "/routines/" in low:  # a loop entry: the line IS the command
            ok = re.match(r"\s*(?:[-*$>]\s*)*`?" + run, txt)
        elif base == "makefile" or low.endswith((".json", ".sh", ".yml", ".yaml")):
            ok = re.search(run, txt) and not txt.lstrip().startswith("#") and (
                not low.endswith((".yml", ".yaml")) or "/.github/workflows/" in low)
        else:
            ok = False
        if ok:
            return True
    return False


def closable(o, name):
    if not os.access(os.path.join(o["--dir"], name), os.X_OK):
        print(f"NOT CLOSABLE {name}: no executable check in {o['--dir']}")
    elif load(o["--state"]).get(name, {}).get("pass", 0) < NEED:
        print(f"NOT CLOSABLE {name}: needs {NEED} consecutive passing ticks")
    elif not has_caller(o):
        print(f"NOT CLOSABLE {name}: nothing calls fitness_tick.py, so the check never runs")
    else:
        print(f"CLOSABLE {name}")
        return 0
    return 1


def main(argv):
    o, rest = args(argv)
    if not rest:
        return tick(o)
    if rest[0] == "closable" and len(rest) == 2:
        return closable(o, rest[1])
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
