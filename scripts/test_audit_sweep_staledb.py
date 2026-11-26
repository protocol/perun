#!/usr/bin/env python3
"""Tests: the review_checks.sh stale-advisory-DB not-checked row (an offline osv-scanner or trivy DB older than REVIEW_ADVISORY_MAX_AGE_DAYS)
is an ENVGAP row in audit_sweep.py (a provisioning gap that names its cause class, "not-provisioned"), never a blocking GAP, for both tools;
the same text with a stray suffix, or the same tool's "exit N" row, still blocks. Synthetic data only; no network."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
FAKE = 'import os, sys\na = sys.argv[1:]\nprint(open(os.path.dirname(a[a.index("--repo") + 1]) + "/rows.json").read())\n'
MSG = ("NOT CHECKED: no local advisory DB newer than 7 days (21 days old, REVIEW_ADVISORY_MAX_AGE_DAYS=7); "
       "refresh: trivy --cache-dir /x/trivy image --download-db-only")
ok = 0


def check(c, m):
    global ok
    if not c:
        raise AssertionError(m)
    ok += 1


def nc(tool, m, file=""):
    return {"file": file, "line": 0, "rule": "not-checked", "text": "not-checked: " + m, "message": m, "tool": tool}


def sweep(rows):
    """One `audit_sweep.py --local` run on a one-commit repo whose fake scanner prints `rows`: (rc, TSV rows)."""
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        for n, body in (("fake.py", FAKE), ("rows.json", json.dumps(rows)), ("checks.sh", f'exec {sys.executable} {t}/fake.py "$@"\n')):
            with open(os.path.join(t, n), "w") as fh:
                fh.write(body)
        repo = os.path.join(t, "acme")
        os.makedirs(repo)
        for c in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "a"]):
            subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(t, "checks.sh"))
        r = subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", repo, "--state", os.path.join(t, "s.json")],
                           capture_output=True, text=True, env=env)
        return r.returncode, [l.split("\t") for l in r.stdout.splitlines()[1:]]
    finally:
        shutil.rmtree(t, ignore_errors=True)


def test_stale_db_row_is_envgap_for_both_tools():
    rc, rows = sweep([nc("trivy", MSG), nc("osv-scanner", MSG.replace("trivy --cache-dir /x/trivy image --download-db-only", "osv-scanner --download-offline-databases ."))])
    kinds = sorted((x[1], x[4], x[3]) for x in rows if x[1] != "COVERAGE")
    check(kinds == [("ENVGAP", "osv-scanner", "1 not-checked: not-provisioned 1"), ("ENVGAP", "trivy", "1 not-checked: not-provisioned 1")], f"rows: {rows}")
    check(rc == 0, f"a provisioning gap does not fail the sweep: rc={rc}")


def test_unknown_age_row_is_envgap_too():
    unk = "NOT CHECKED: no local advisory DB of known age (REVIEW_ADVISORY_MAX_AGE_DAYS=7); refresh: trivy --cache-dir /x/trivy fs --download-db-only"
    rc, rows = sweep([nc("trivy", unk), nc("osv-scanner", unk)])
    check(sorted((x[1], x[4], x[3]) for x in rows if x[1] != "COVERAGE") ==
          [("ENVGAP", "osv-scanner", "1 not-checked: not-provisioned 1"), ("ENVGAP", "trivy", "1 not-checked: not-provisioned 1")], f"rows: {rows}")
    check(rc == 0, f"rc={rc}")


def test_other_rows_for_the_same_tools_still_block():
    rc, rows = sweep([nc("trivy", MSG + "\nextra"), nc("osv-scanner", "exit 2")])
    check(sorted((x[1], x[4]) for x in rows if x[1] != "COVERAGE") == [("GAP", "osv-scanner"), ("GAP", "trivy")], f"rows: {rows}")
    check(rc == 1, f"blocking rows exit 1: rc={rc}")


bad = 0
for f in (test_stale_db_row_is_envgap_for_both_tools, test_unknown_age_row_is_envgap_too, test_other_rows_for_the_same_tools_still_block):
    try:
        f()
    except AssertionError as e:
        bad += 1
        print("FAIL", f.__name__, e)
print(f"Tests: {ok}/{ok + bad}")
sys.exit(1 if bad else 0)
