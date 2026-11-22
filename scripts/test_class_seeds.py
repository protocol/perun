#!/usr/bin/env python3
"""Seeded regression cases (vuln, clean twin, mutant) for classes that had a mapped detector but no seed.

Cases come from CASES below plus every bench/class-seeds/cases.d/*.json (see its README.md), so a seed lane adds
a case without editing Python. Fixtures live in bench/class-seeds/{vuln,clean,mutant}/<seed> (a file or a directory)
or are assembled at test time by bench/class-seeds/builders/<name>.py (build(dst, kind)), so a fake secret never sits
in the repo as a literal. A case records what the mapped detector actually did when its seeds were first run:
expect = [vuln_hit, mutant_hit], True = fires, False = honest expected miss (a known gap, not a pass). The clean
twin must never fire. A missing tool, or a pin_only seed on a tool version CI does not pin, is an explicit SKIP,
counted and never a pass; a run where no seed ran fails, and
under REQUIRE_SEMGREP=1 (CI's real-hub job, every tool installed) any SKIP fails. If a detector starts catching
an expected miss, this test fails so the entry gets flipped on purpose. Fictional data only. No rule is edited here."""
import glob, importlib.util, json, os, re, shutil, subprocess, sys, tempfile

sys.dont_write_bytecode = True  # builders import from the repo: leave no __pycache__
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = os.path.join(ROOT, "bench", "class-seeds")
SKILL = os.path.join(ROOT, ".claude", "skills")
SEMGREP_DIR = os.path.join(SKILL, "deep-code-review", "templates", "semgrep-taint")
HUB = os.path.join(SKILL, "deep-code-review", "scripts", "review_checks.sh")
OSC = os.path.join(SKILL, "product-output-safety", "scripts", "output_safety_check.py")
GIT = ["git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", "-c", "commit.gpgsign=false"]
SKIPPED = None  # a runner returns this when its tool did not run: counted as skipped, never a pass


def semgrep(path, c):
    """True when a bundled perun rule whose check_id contains c["rule"] fires. Whole semgrep-taint/ dir, cwd = the
    seed's parent, target = its basename (file or dir) for every case. HOME is redirected: semgrep writes ~/.semgrep.
    A non-zero exit or any semgrep error raises, so an expect-False case cannot pass on a run that scanned nothing."""
    if not shutil.which("semgrep"):
        return SKIPPED
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "HOME": home, "SEMGREP_LOG_FILE": home + "/sg.log", "SEMGREP_SETTINGS_FILE": home + "/sg.yml"}
        cmd = ["semgrep", "--metrics=off", "--disable-version-check", "--json", "--quiet", "--config", SEMGREP_DIR, "--", os.path.basename(path)]
        r = subprocess.run(cmd, cwd=os.path.dirname(path), capture_output=True, text=True, env=env)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and not out["errors"], (path, r.returncode, out["errors"])  # a broken run is never a miss
    return any(c.get("rule", "") in x["check_id"] for x in out["results"])


def hub(path, c):
    """True when review_checks.sh, run on a fresh git repo holding only the seed at its root, emits a row from tool
    c["tool"][4:] (whose rule contains c["rule"]). diff mode against an empty base commit (a seed with its own .git runs --full); c["flags"]
    adds review_checks.sh flags (e.g. --history). SKIPPED when the tool's only rows are not-checked or stderr lists it,
    or the binary c["needs"] names (a tool such as gitleaks-history runs the gitleaks binary), under "skipped (not installed)". A seed with its own .git (a builder's history) is used as is."""
    name = c["tool"][4:]
    with tempfile.TemporaryDirectory() as t:
        repo, home = os.path.join(t, "repo"), os.path.join(t, "home")
        os.mkdir(home)
        if os.path.isdir(path):
            shutil.copytree(path, repo, symlinks=True)
        else:
            os.mkdir(repo)
            shutil.copy(path, repo)
        # a plain seed: empty base commit, then the seed, diff mode (fast). A builder's own repo: --full (its history may be the point).
        base = ["--full"]
        if not os.path.isdir(os.path.join(repo, ".git")):
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "base"], cwd=repo, check=True)
            base = ["--base", "HEAD~1"]
        if subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout.strip():
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(GIT + ["commit", "-qm", "seed"], cwd=repo, check=True)
        env = {**os.environ, "HOME": home, "REVIEW_SEMGREP_REGISTRY": "0", "CI": "true"}
        r = subprocess.run(["bash", HUB, *base, *c.get("flags", [])], cwd=repo, capture_output=True, text=True, env=env)
    rows = json.loads(r.stdout)  # a crash or non-JSON output raises: broken run, never a pass
    mine = [x for x in rows if x["tool"] == name]
    hits = [x for x in mine if x["rule"] != "not-checked" and c.get("rule", "") in x["rule"]]
    skipped = re.search(r"skipped \(not installed\): ([^\n]*)", r.stderr)
    absent = skipped.group(1).split(", ") if skipped else []
    if not hits and (any(x["rule"] == "not-checked" for x in mine) or name in absent or c.get("needs") in absent):
        return SKIPPED
    return bool(hits)


def osc(path, c):
    """True when output_safety_check.py exits 1 (a FAIL); exit 0 is clean, anything else is a broken run."""
    rc = subprocess.run([sys.executable, "-I", OSC, path], capture_output=True, text=True).returncode
    assert rc in (0, 1), (path, rc)
    return rc == 1


def cppcheck(path, c):
    """True when cppcheck (warning checks on, template prints ids to stderr) reports an id containing c["rule"], so a
    finding of another class in the same seed (2.22's nullPointerOutOfMemory, uninitdata) is not a hit. SKIPPED when
    not installed, or when the seed kind is in c["pin_only"] and the host cppcheck is not the version ci.yml pins;
    the SKIP note then names both versions."""
    if not shutil.which("cppcheck"):
        return SKIPPED
    kind = os.path.basename(os.path.dirname(path))
    if kind in c.get("pin_only", ()):
        pin = re.search(r"cppcheck_([\d.]+)-", open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()).group(1)
        host = subprocess.run(["cppcheck", "--version"], capture_output=True, text=True).stdout.split()[-1]
        if host != pin:
            c["why"] = f"the {kind} seed counts only on CI's pinned cppcheck {pin}; this host has cppcheck {host}"
            return SKIPPED
    ids = subprocess.run(["cppcheck", "--quiet", "--enable=warning", "--template={id}", path], capture_output=True, text=True).stderr
    return any(c["rule"] in i for i in ids.split())


GUARD = os.path.join(SKILL, "agentic-delivery", "scripts", "destructive_guard.py")


def guard(path, c):
    """True when destructive_guard.py (tool kind `hook:destructive_guard`) blocks the seed: the seed file is a JSON
    PreToolUse payload piped to its stdin, never run. Exit 2 = block, 0 = allow, anything else is a broken run."""
    rc = subprocess.run([sys.executable, "-I", GUARD], stdin=open(path), capture_output=True, text=True).returncode
    assert rc in (0, 2), (path, rc)
    return rc == 2


RUNNERS = {"semgrep": semgrep, "output_safety_check": osc, "cppcheck": cppcheck, "hook:destructive_guard": guard}


def build(name, dst, kind):
    """Run bench/class-seeds/builders/<name>.py build(dst, kind) so a fixture is assembled at test time."""
    spec = importlib.util.spec_from_file_location("seed_builder_" + name, os.path.join(SEEDS, "builders", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.build(dst, kind)


NOTE_C = "vuln and mutant fire on cppcheck 2.22.0, the CWE-416 mutant excepted (pin_only); the CI-pinned run is unverified here"


def case(cls, seed, tool, rule, expect, why=""):
    return {"class": cls, "seed": seed, "tool": tool, "rule": rule, "expect": expect, "why": why}


CASES = [
    dict(case("CWE-416", "cwe416.c", "cppcheck", "deallocuse", [True, True], NOTE_C), pin_only=["mutant"]),
    case("CWE-125", "cwe125.c", "cppcheck", "arrayIndexOutOfBounds", [True, True], NOTE_C),
    case("CWE-476", "cwe476.c", "cppcheck", "nullPointer", [True, True], NOTE_C),
    case("CWE-20", "cwe20.js", "semgrep", "perun.js.unvalidated-size-or-qty", [True, True], "observed with the whole semgrep-taint/ dir: the rule fires on vuln and mutant; the earlier miss came from loading only js/py/defaults.yml"),
    case("CWE-200", "cwe200.py", "semgrep", "perun.py.exception-in-response", [True, True], "observed with the whole semgrep-taint/ dir: exception-in-response fires on vuln and mutant (mutant also hits secret-field-in-response); earlier miss came from loading only js/py/defaults.yml"),
    case("LLM05", "llm05.js", "semgrep", "perun.js.llm-output-code-exec", [True, True], "observed with the whole semgrep-taint/ dir: llm-output-code-exec fires on vuln (plus deserialize-eval, xss) and on the mutant; earlier mutant miss came from loading only js/py/defaults.yml"),
    case("LLM09", "llm09.json", "output_safety_check", "", [True, True]),
    case("safety-unsafe-ai-output", "safety-unsafe-ai-output.json", "output_safety_check", "", [True, True]),
]


def run_kind(c, kind):
    """Hit (True/False) or SKIPPED for one kind (vuln|clean|mutant) of a case."""
    runner = hub if c["tool"].startswith("hub:") else RUNNERS[c["tool"]]
    if c.get("builder"):
        with tempfile.TemporaryDirectory() as t:
            dst = os.path.join(t, "seed")
            os.mkdir(dst)
            build(c["builder"], dst, kind)
            return runner(dst, c)
    return runner(os.path.join(SEEDS, kind, c["seed"]), c)


def main():
    if shutil.which("semgrep"):  # self-check: a broken semgrep run (missing target) must raise, never read as a miss
        try:
            semgrep(os.path.join(SEEDS, "vuln", "no-such-seed.py"), {"rule": "perun."})
            print("FAIL: a broken semgrep run read as a miss")
            return 1
        except AssertionError:
            pass
    cases = CASES + [x for f in sorted(glob.glob(os.path.join(SEEDS, "cases.d", "*.json"))) for x in json.load(open(f))]
    ok = fail = skip = 0
    for c in cases:
        res = [(k, w, run_kind(c, k)) for k, w in zip(("vuln", "clean", "mutant"), (c["expect"][0], False, c["expect"][1]))]
        label = c["class"] if isinstance(c["class"], str) else "/".join(c["class"])
        if any(g is SKIPPED for _, _, g in res):
            print(f"SKIP {label} ({c['tool']} not run): {c.get('why', '')}")
            skip += 1
            continue
        for kind, want, got in res:
            note = "" if want or kind == "clean" else f" (expected miss: {c.get('why', '')})"
            print(f"{'ok' if got == want else 'FAIL'} {label} {kind}: {'hit' if got else 'miss'}{note}")
            ok, fail = ok + (got == want), fail + (got != want)
    print(f"class seeds: {ok} ok, {fail} fail, {skip} skipped")
    if not ok:
        print("FAIL: no seed ran")
    if skip and os.environ.get("REQUIRE_SEMGREP") == "1":
        print("FAIL: seeds skipped under REQUIRE_SEMGREP=1")
    return 1 if fail or not ok or (skip and os.environ.get("REQUIRE_SEMGREP") == "1") else 0


if __name__ == "__main__":
    sys.exit(main())
