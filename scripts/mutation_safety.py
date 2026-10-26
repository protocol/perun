#!/usr/bin/env python3
"""Opt-in mutation pass over Perun's safety-critical scripts. Local only, never run by CI, never installs anything.

Usage: python3 scripts/mutation_safety.py [heavy_gate|perun_policy|secret_scan ...] [--python PY] [--max-children N]

PY must be an interpreter that can import mutmut 3.x (default: this one), e.g. a venv from `uv venv "$TMPDIR/mm" &&
uv pip install --python "$TMPDIR/mm/bin/python" mutmut pytest`. For each target it builds a scratch tree under $TMPDIR (the
repo is never modified), runs the existing in-process pins against every mutant of the listed functions, and prints
`<target>: killed/total = score` plus each survivor. Score = killed (timeouts count as killed) over all generated mutants;
"no tests" mutants are not covered and count against the score. Subprocess and CLI pins cannot see a mutant, so the score is
a floor. Side effects: writes only under the scratch tree (kept, path printed). A survivor is a lead, not proof of a missing
test: some are equivalent mutants.
"""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
SC = ROOT / "scripts"
POLICY_TESTS = ["test_lane_weight.py", "test_resource_policy.py", "test_mutation_kills_policy.py"]
SECRET_PINS = sorted(p.name for p in SC.glob("test_secret_extra_rules*.py"))
TARGETS = {  # module -> (source dir, functions to mutate or None for all, native pytest files, script pins)
    "heavy_gate": (AD, None, POLICY_TESTS + ["test_mutation_kills_heavy_gate.py"], []),
    "perun_policy": (AD, "token_cap free_cores lanes heavy_slots lease_dir _alive _leases active_leases tree_cpu lane_weight lease_load "
                         "heavy_acquire heavy_release exclusive_holder exclusive_acquire exclusive_renew exclusive_release holder_pid".split(),
                     POLICY_TESTS, []),
    "secret_scan": (SC, None, ["test_mutation_kills_secret_scan.py"], SECRET_PINS),
}


def run(target, py, children):
    mod_dir, fns, native, scripts = TARGETS[target]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"mut-{target}-", dir=os.environ.get("TMPDIR")))
    (tmp / "tests/pins").mkdir(parents=True)
    src = tmp / "src"
    shutil.copytree(AD, src, ignore=shutil.ignore_patterns("__pycache__", "*.sh", "test_*"))
    if fns:  # mutmut skips a def marked no-mutate; mutating the other functions only costs generation time
        t = src / f"{target}.py"
        t.write_text(re.sub(r"^(def (\w+)\(.*\):)[ \t]*$", lambda m: m.group(1) if m.group(2) in fns else m.group(1) + "  # pragma: no mutate", t.read_text(), flags=re.M))
    for f in ["secret_scan.py", "gitleaks-v8.30.1.toml", "secret-scan-allow.txt"]:
        shutil.copy(SC / f, src / f)
    for f in native:
        if (SC / f).exists():
            shutil.copy(SC / f, tmp / "tests" / f)
    for f in scripts:
        shutil.copy(SC / f, tmp / "tests/pins" / (f + ".pin"))  # not test_*.py: pytest must not collect them
    shutil.copy(SC / "mutation_harness.py", tmp / "tests/test_harness.py")
    cfg = {"stems": ["secret_scan", "destructive_guard", "heavy_gate", "perun_policy"], "scripts": scripts, "corpus": [], "freeze_clock": target == "secret_scan"}
    (tmp / "tests/harness.json").write_text(json.dumps(cfg))
    cfg_py = lambda deselect: (f'[tool.mutmut]\nsource_paths = ["src/{target}.py"]\nalso_copy = {json.dumps(sorted("src/" + p.name for p in src.iterdir() if p.name != target + ".py"))}\n'
                               f'pytest_add_cli_args = {json.dumps(deselect)}\npytest_add_cli_args_test_selection = ["tests/"]\nuse_git_change_detection = false\n')
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONDONTWRITEBYTECODE": "1"}
    base = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider", "tests"], cwd=tmp, env=env, capture_output=True, text=True)
    bad = sorted(set(re.findall(r"^(?:FAILED|ERROR) (\S+?)(?: - .*)?$", base.stdout, re.M)))
    deselect = [a for b in bad for a in ("--deselect", b)]  # pins that cannot run in a scratch tree (subprocess, CLI paths)
    (tmp / "pyproject.toml").write_text(cfg_py(deselect))
    pats = [f"{target}.x_{f}__mutmut_*" for f in fns] if fns else [f"{target}.*"]
    r = subprocess.run([py, "-m", "mutmut", "run", "--max-children", str(children), *pats], cwd=tmp, capture_output=True, text=True)
    res = subprocess.run([py, "-m", "mutmut", "results", "--all", "true"], cwd=tmp, capture_output=True, text=True).stdout
    rows = re.findall(r"^\s*(\S+): (\w[\w ]*?)\s*$", res, re.M)
    if fns:
        rows = [r for r in rows if re.fullmatch(rf"{target}\.x_({'|'.join(fns)})__mutmut_\d+", r[0])]
    killed = sum(s in ("killed", "timeout") for _, s in rows)
    surv = [n for n, s in rows if s == "survived"]
    print(f"{target}: {killed}/{len(rows)} = {killed / max(len(rows), 1):.3f}  (survived {len(surv)}, other {len(rows) - killed - len(surv)}; "
          f"{len(bad)} pins skipped; scratch {tmp})")
    for n in surv:
        print("  SURVIVED", n)
    if not rows:
        print((r.stdout + r.stderr)[-1500:])
    return len(rows) and killed / len(rows)


def main(argv):
    py, children, names = sys.executable, 4, []
    while argv:
        a = argv.pop(0)
        if a == "--python":
            py = argv.pop(0)
        elif a == "--max-children":
            children = int(argv.pop(0))
        else:
            names.append(a)
    if subprocess.run([py, "-c", "import mutmut, pytest"], capture_output=True).returncode:
        print(f"mutation_safety: {py} cannot import mutmut and pytest; install them in a venv (see --help text) and pass --python", file=sys.stderr)
        return 2
    for t in names or TARGETS:
        if t not in TARGETS:
            print(f"unknown target {t}; choose from {', '.join(TARGETS)}", file=sys.stderr)
            return 2
        run(t, py, children)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
