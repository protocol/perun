#!/usr/bin/env python3
"""perun_doctor.review_scanners: the "review scanners" row is red (WARN) when the last review_checks.sh run had wired scanners that
did not run, or ran without their offline cache, and a provision fixes it; INFO when nothing is recorded, the record is unreadable
or the cause is not fixable by provisioning, or a scanner ran with a partial scope (trivy secret-only, semgrep with errors); OK when
everything wired ran in full. An osv-scanner fix names this repo as DIR on the command. The record lives in the git common dir, so a
linked worktree sees the same one. Read-only."""
import atexit, json, os, pathlib, shlex, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perun_doctor

os.environ["DCR_NO_PROBE"] = "1"  # check() below: no sandbox probe, no ps
mk = lambda prefix: pathlib.Path(tempfile.mkdtemp(prefix=prefix))
T, wt, nongit = mk("dcr-doctor-scan."), mk("dcr-doctor-wt."), mk("dcr-doctor-nogit.")
for d in (T, wt, nongit):
    atexit.register(shutil.rmtree, str(d), True)
git = lambda *a, cwd=T: subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *a], cwd=cwd, check=True, capture_output=True)
git("init", "-q", ".")
git("commit", "-q", "--allow-empty", "-m", "base")
rec = T / ".git/review-checks-last.json"


def row(repo=T):
    return perun_doctor.review_scanners(repo)


def write(**d):
    rec.write_text(json.dumps({"ts": int(time.time()), "wired": [], "not_run": [], "fixable": [], **d}))


st, msg = row()  # no record yet: not checked, never a guess
assert st == "INFO" and "not checked" in msg, (st, msg)

write(wired=["gitleaks", "osv-scanner", "zizmor"], not_run=["osv-scanner", "zizmor"], fixable=["osv-scanner", "zizmor"])
st, msg = row()  # red: names the tools, the counts and the one command to run yourself
assert st == "WARN" and "ran 1 / wired 3" in msg and "fixable: osv-scanner, zizmor" in msg, (st, msg)
assert "provision_tools.sh --print" in msg and "yourself outside the sandbox" in msg, msg
assert f"--print {shlex.quote(str(T))}`" in msg, msg  # osv fix: this repo is DIR, else a warm any-ecosystem cache makes --print emit nothing and the row loops

write(wired=["gitleaks", "zizmor", "semgrep"], not_run=["zizmor"], fixable=["zizmor", "semgrep"])
st, msg = row()  # no osv-scanner in the fix: the bare command, no DIR
assert st == "WARN" and "provision_tools.sh --print`" in msg and shlex.quote(str(T)) not in msg, (st, msg)

write(wired=["gitleaks", "semgrep"], fixable=["semgrep"])  # semgrep ran, but without the p/default pack: still red
st, msg = row()
assert st == "WARN" and "ran 2 / wired 2" in msg and "fixable: semgrep" in msg, (st, msg)

write(wired=["gitleaks", "bandit"], not_run=["bandit"])  # crashed or timed out: nothing to provision, so not red
st, msg = row()
assert st == "INFO" and "not run: bandit" in msg and "provision_tools" not in msg, (st, msg)

write(wired=["gitleaks", "trivy"])
st, msg = row()
assert st == "OK" and "ran 2 / wired 2" in msg, (st, msg)

write(wired=["gitleaks", "trivy"], partial=["trivy(secret-only)"])  # ran, but secret-only: not OK, and nothing to provision
st, msg = row()
assert st == "INFO" and "partial scope: trivy(secret-only)" in msg and "ran 2 / wired 2" in msg and "provision_tools" not in msg, (st, msg)

write(wired=["gitleaks", "semgrep", "bandit"], not_run=["bandit"], partial=["semgrep(errors)"])  # both causes are named
st, msg = row()
assert st == "INFO" and "not run: bandit" in msg and "partial scope: semgrep(errors)" in msg, (st, msg)

write(wired=["gitleaks", "trivy", "zizmor"], not_run=["zizmor"], fixable=["zizmor"], partial=["trivy(secret-only)"])  # a fix still wins
st, msg = row()
assert st == "WARN" and "fixable: zizmor" in msg, (st, msg)

write(wired=["gitleaks"], partial=[])  # an empty partial list is a full run
assert row()[0] == "OK", row()

for bad in ("{not json", "[]", "null", '{"wired": 5, "not_run": [], "fixable": [], "ts": 1}', '{"wired": [], "not_run": [], "fixable": []}',
            '{"wired": [], "not_run": [], "fixable": [], "ts": "x"}'):  # unreadable or malformed record: INFO, never a crash
    rec.write_text(bad)
    st, msg = row()
    assert st == "INFO" and "not checked" in msg, (bad, st, msg)

write(wired=["trivy"], not_run=["trivy"], fixable=["trivy"])
wt.rmdir()  # git creates it
git("worktree", "add", "-q", str(wt))
st, msg = row(wt)  # the record is shared through the git common dir
assert st == "WARN" and "fixable: trivy" in msg, (st, msg)
rows = [r for r in perun_doctor.check(T, T) if r[1] == "review scanners"]
assert len(rows) == 1 and rows[0][0] == "WARN", rows  # check() carries the row (the record read needs no probe)
assert "Healthy" not in perun_doctor.verdict(rows, T), "a red row must count as needing attention"
assert row(nongit)[0] == "INFO"  # not a git repo: not checked
print("ok: review scanners row is red only for a fixable NOT RUN, INFO without a record, worktrees share it")
