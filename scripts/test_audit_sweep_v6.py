#!/usr/bin/env python3
"""Tests: a fixed finding that is re-added is reported again; a tool missing at first appears later and its full rescan reports findings
from the skipped range; summary-row line shifts and corroboration suffixes do not re-alert; a tab or newline in a file name cannot break the TSV."""
import atexit, json, os, shutil, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

FAKE = '''import json, os, sys
av = sys.argv
repo = av[av.index("--repo") + 1]
t = os.path.dirname(repo)
open(t + "/calls.log", "a").write(" ".join(av[1:]) + "\\n")
diff = "--base" in av and "--history" not in av
rows = []
for f in sorted(os.listdir(repo)):
    if f == ".git":
        continue
    for i, l in enumerate(open(os.path.join(repo, f)).read().splitlines(), 1):
        if "BAD" in l:
            rows.append({"file": f, "line": i, "rule": "r", "text": "BAD thing", "tool": "fake", **({"new": True} if diff else {})})
        if "LATE" in l and os.path.exists(t + "/bin/latetool"):
            rows.append({"file": f, "line": i, "rule": "r", "text": "LATE thing", "tool": "latetool"})
if not os.path.exists(t + "/bin/latetool"):
    rows.append({"file": "", "line": 0, "rule": "not-checked", "message": "install: brew install latetool", "text": "not-checked: install: brew install latetool", "tool": "latetool"})
print(json.dumps(rows))
'''


def env():
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    atexit.register(shutil.rmtree, t, True)
    open(t + "/fake.py", "w").write(FAKE)
    open(t + "/checks.sh", "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
    os.makedirs(t + "/bin"); os.makedirs(t + "/acme")
    repo, state = t + "/acme", t + "/s.json"
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("init", "-q")
    def commit(files):
        for n, body in files.items():
            open(os.path.join(repo, n), "w").write(body)
        g("add", "-A"); g("commit", "-qm", "c")
    e = dict(os.environ, AUDIT_SWEEP_CHECKS=t + "/checks.sh", PATH=t + "/bin" + os.pathsep + os.environ["PATH"])
    run = lambda: subprocess.run([sys.executable, D + "/audit_sweep.py", "--local", repo, "--state", state], capture_output=True, text=True, env=e)
    rows = lambda r: [l.split("\t") for l in r.stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l and "\tENVGAP\t" not in l]
    return t, commit, run, rows


def test_fix_then_readd_reports_again():
    t, commit, run, rows = env()
    open(t + "/bin/latetool", "w").write("")  # no missing-tool noise
    commit({"f.py": "BAD\n"})
    assert [r[1] for r in rows(run())] == ["first"]
    commit({"f.py": "ok\n"})
    assert rows(run()) == [], "fix: nothing to report"
    commit({"f.py": "ok\nBAD\n"})
    r3 = rows(run())
    assert [x[1] for x in r3] == ["delta"], f"identical BAD re-added must be reported again: {r3}"


def test_missing_tool_appears_full_rescan_reports_old_range():
    t, commit, run, rows = env()
    commit({"a.txt": "LATE\n"})
    r1 = run()
    assert rows(r1) == [], "tool missing: nothing from latetool"
    commit({"b.txt": "x\n"})
    run()
    n = len(open(t + "/calls.log").read().splitlines())
    open(t + "/bin/latetool", "w").write(""); os.chmod(t + "/bin/latetool", 0o755)
    r3 = run()
    calls = open(t + "/calls.log").read().splitlines()[n:]
    assert calls and all("--full" in c for c in calls), calls
    got = rows(r3)
    assert [(x[1], x[2], x[4]) for x in got] == [("rescan", "a.txt", "latetool")], f"finding from the skipped range must surface as NEW: {got}"


def test_summary_line_shift_and_corroboration_are_stable():
    f = lambda t: a.fingerprint("r", {"tool": "ruff", "rule": "F821-summary", "file": "x.py", "text": t})
    assert f("12 F821 hits in this file (showing 3 of 12; REVIEW_FIXTURE_ROWS=all for every row): 4, 9, 30") == f("13 F821 hits in this file (showing 3 of 13; REVIEW_FIXTURE_ROWS=all for every row): 5, 10, 31")
    g = lambda t: a.fingerprint("r", {"tool": "semgrep", "rule": "r", "file": "x.py", "text": t})
    assert g("bad call") == g("bad call [corroborated by: semgrep, bandit]") == g("bad call; added: 3, 4")
    assert g("port 80 open") != g("port 81 open")


def test_tab_newline_in_file_name_keeps_tsv_columns():
    t, commit, run, rows = env()
    open(t + "/bin/latetool", "w").write("")
    commit({"bad\tname.py": "BAD\n"})
    lines = [l for l in run().stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l]  # a host without a CORE scanner adds a COVERAGE row
    assert len(lines) == 1 and len(lines[0].split("\t")) == 6, lines


bad = 0
for f in (test_fix_then_readd_reports_again, test_missing_tool_appears_full_rescan_reports_old_range, test_summary_line_shift_and_corroboration_are_stable, test_tab_newline_in_file_name_keeps_tsv_columns):
    try:
        f(); print("ok", f.__name__)
    except AssertionError as e:
        bad += 1; print("FAIL", f.__name__, e)
print(f"Tests: {4 - bad}/4")
sys.exit(bad)
