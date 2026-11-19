#!/usr/bin/env python3
"""Seeded regression cases (vuln, clean twin, mutant) for classes that had a mapped detector but no seed.

Fixtures live in bench/class-seeds/{vuln,clean,mutant}/. CASES records, per class, what the mapped detector
actually did when the seeds were first run: True = fires, False = honest expected miss (a known gap, not a pass).
The clean twin must never fire. A missing tool is an explicit SKIP with its reason, never a silent pass. If a
detector starts catching an expected miss, this test fails so the entry gets flipped to True on purpose.
Fictional data only. No rule or detector is edited here."""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = os.path.join(ROOT, "bench", "class-seeds")
SKILL = os.path.join(ROOT, ".claude", "skills")
SEMGREP_CFG = [os.path.join(SKILL, "deep-code-review", "templates", "semgrep-taint", f) for f in ("js.yml", "py.yml", "defaults.yml")]
OSC = os.path.join(SKILL, "product-output-safety", "scripts", "output_safety_check.py")


def semgrep(path):
    """True when any bundled perun rule fires on the file. HOME is redirected because semgrep writes ~/.semgrep."""
    with tempfile.TemporaryDirectory() as home:
        cmd = ["semgrep", "--metrics=off", "--disable-version-check", "--json", "--quiet"]
        for c in SEMGREP_CFG:
            cmd += ["--config", c]
        r = subprocess.run(cmd + ["--", os.path.basename(path)], cwd=os.path.dirname(path), capture_output=True, text=True, env={**os.environ, "HOME": home})
    return bool(json.loads(r.stdout)["results"])


def osc(path):
    """True when output_safety_check.py exits 1 (a FAIL); exit 0 is clean, anything else is a broken run."""
    rc = subprocess.run([sys.executable, "-I", OSC, path], capture_output=True, text=True).returncode
    assert rc in (0, 1), (path, rc)
    return rc == 1


def cppcheck(path):
    """True on any cppcheck finding (warning checks on, template prints ids to stderr). Only reached when installed."""
    return bool(subprocess.run(["cppcheck", "--quiet", "--enable=warning", "--template={id}", path], capture_output=True, text=True).stderr.strip())


def flawfinder(path):
    """True on any flawfinder hit (data rows only). Only reached when installed."""
    return bool(subprocess.run(["flawfinder", "--quiet", "--dataonly", path], capture_output=True, text=True).stdout.strip())


NOTE_C = "tool not installed here; vuln and mutant are expected to fire once it is, unverified"
# (class, seed file, tool, runner, expected (vuln, mutant) hit, reason for an expected miss or skip)
CASES = [
    ("CWE-416", "cwe416.c", "cppcheck", cppcheck, (True, True), NOTE_C),
    ("CWE-125", "cwe125.c", "cppcheck", cppcheck, (True, True), NOTE_C),
    ("CWE-476", "cwe476.c", "cppcheck", cppcheck, (True, True), NOTE_C),
    ("CWE-121", "cwe121.c", "flawfinder", flawfinder, (True, True), NOTE_C),
    ("CWE-122", "cwe122.c", "flawfinder", flawfinder, (True, True), NOTE_C),
    ("CWE-20", "cwe20.js", "semgrep", semgrep, (False, False),
     "only the narrow Prisma where-filter and mass-assignment shapes are modelled; a missing type or range check is not"),
    ("CWE-200", "cwe200.py", "semgrep", semgrep, (False, False),
     "only DEBUG = True and app.run(debug=True) are modelled; a traceback or secret field returned in a response is not"),
    ("LLM05", "llm05.js", "semgrep", semgrep, (True, False),
     "vuln fires only because request-body taint flows through the model call (eval and xss sinks), not because the completion is a source; the mutant routes the completion into new Function via a helper and is missed"),
    ("LLM09", "llm09.json", "output_safety_check", osc, (True, True), ""),
    ("safety-unsafe-ai-output", "safety-unsafe-ai-output.json", "output_safety_check", osc, (True, True), ""),
]


def main():
    ok = fail = skip = 0
    for cls, fname, tool, runner, (ev, em), why in CASES:
        if tool != "output_safety_check" and not shutil.which(tool):
            print(f"SKIP {cls} ({tool} not installed): {why}")
            skip += 1
            continue
        for kind, want in (("vuln", ev), ("clean", False), ("mutant", em)):
            got = runner(os.path.join(SEEDS, kind, fname))
            note = "" if want or kind == "clean" else f" (expected miss: {why})"
            print(f"{'ok' if got == want else 'FAIL'} {cls} {kind}: {'hit' if got else 'miss'}{note}")
            ok, fail = ok + (got == want), fail + (got != want)
    print(f"class seeds: {ok} ok, {fail} fail, {skip} skipped classes")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
