#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=deny destructive host commands before they run (best effort; the OS sandbox is the boundary), review=2027-01-30
"""PreToolUse(Bash) hook entry: runs `destructive_guard_core.py`, which holds all of the guard logic and its documentation.

Python never caches bytecode for the script it is started on, so a 2000-line hook script was recompiled on every tool
call. This stub is tiny, and it runs the core's code object from the `__pycache__` bytecode cache next to it (compiled
on the first call, reused after). The code is executed in this module's own namespace, so `import destructive_guard`,
`check`, `main`, and patching a name such as `TIMEOUT` behave exactly as before. Limit: when the skills directory is
read-only, or `PYTHONDONTWRITEBYTECODE` is set, no cache file is written and each call compiles the core again (as before).
Fail closed, because any exit code but 2 lets the command run: a core that is missing or does not compile exits 2
("could not load"), and a crash inside the core's `main()` exits 2 ("guard crashed").
"""
import os
import sys

_script = __name__ == "__main__"
try:
    from importlib.machinery import SourceFileLoader
    _code = SourceFileLoader("destructive_guard_core", os.path.join(os.path.dirname(os.path.abspath(__file__)), "destructive_guard_core.py")).get_code("destructive_guard_core")
    if _script:
        __name__ = "destructive_guard_core"  # the core's own `__main__` block must not run here: this stub runs main() below
    try:
        exec(_code, globals())
    finally:
        if _script:
            __name__ = "__main__"
except BaseException as e:
    if not _script:
        raise
    print(f"Blocked: destructive guard could not load ({type(e).__name__}), so the command was not vetted.", file=sys.stderr)
    sys.exit(2)

if _script:
    try:
        _rc = main()
    except SystemExit as e:
        _rc = e.code
    except BaseException as e:
        print(f"Blocked: destructive guard crashed ({type(e).__name__}), so the command was not vetted.", file=sys.stderr)
        _rc = 2
    sys.exit(_rc if _rc in (0, 2) else 2)  # Claude Code allows on any exit but 2, so every failure blocks
