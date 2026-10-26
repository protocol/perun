"""pytest adapter that scripts/mutation_safety.py copies into its scratch tree as tests/test_harness.py. Not a CI test.

mutmut mutates module functions and needs pytest tests that import them under their plain module name. Perun's existing
pins are plain scripts that load the guard or scanner by file path, so this adapter (1) points that loading at the scratch
`src/` copy, (2) replays each existing script in-process, and (3) replays the BAD/GOOD command lists of the guard pins
through `destructive_guard.check`. It reads `harness.json` next to it. Offline.
"""
import ast, importlib.util, json, pathlib, runpy, sys, time

import pytest

HERE = pathlib.Path(__file__).resolve().parent
CFG = json.loads((HERE / "harness.json").read_text())
sys.path.insert(0, str(HERE.parent / "src"))
_orig = importlib.util.spec_from_file_location


def _spec(name, location=None, *a, **k):
    """Load a target module from src/ under its plain name, so mutmut's trampoline keys match."""
    if location and pathlib.Path(str(location)).stem in CFG["stems"]:
        return importlib.util.find_spec(pathlib.Path(str(location)).stem)
    return _orig(name, location, *a, **k)


importlib.util.spec_from_file_location = _spec


@pytest.mark.parametrize("f", CFG["scripts"])
def test_script(f, monkeypatch):
    if CFG["freeze_clock"]:  # the pins assert wall-clock bounds; a loaded host must not fail them
        monkeypatch.setattr(time, "time", lambda: 0.0)
        monkeypatch.setattr(time, "perf_counter", lambda: 0.0)
    try:
        runpy.run_path(str(HERE / "pins" / (f + ".pin")), run_name="__main__")
    except SystemExit as e:
        assert not e.code


def _rows(names):
    """Every string in the module-level lists called `names` in the guard pins (lists that need helpers to build are skipped)."""
    out = []
    for f in CFG["corpus"]:
        for n in ast.parse((HERE / "pins" / (f + ".pin")).read_text()).body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names:
                try:
                    v = eval(compile(ast.Expression(n.value), f, "eval"), {})
                except Exception:
                    continue
                stack = [v]
                while stack:
                    x = stack.pop()
                    if isinstance(x, str) and len(x) < 3000:
                        out.append(x)
                    elif isinstance(x, (list, tuple, set, frozenset)):
                        stack.extend(x)
    return out


def test_guard_corpus():
    import destructive_guard as dg
    for c in _rows({"BAD", "DANGEROUS", "BLOCK"}):
        assert dg.check(c), f"missed: {c[:80]!r}"
    for c in _rows({"GOOD", "BENIGN", "SAFE", "ALLOW", "KEPT_FP"}):
        assert not dg.check(c), f"false positive: {c[:80]!r}"
