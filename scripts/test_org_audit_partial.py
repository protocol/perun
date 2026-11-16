#!/usr/bin/env python3
"""Tests: org_audit_driver.py clone filter and timeout handling. (1) The clone uses --filter=blob:limit=5m: a
history-only blob over 5m (never checked out) becomes a git-clone not-checked row in the repo JSON and one aggregated
entry in the summary. (2) A review_checks run that outlives --timeout is a PARTIAL row (exit 0), not FAILED: its raw findings so far
are kept, the tool that started but never finished and the never-started checks are "timed out" not-checked rows, and a
finished tool is not. A fake slow script stands in for review_checks.sh; local file:// repos only, no network, fictional names."""
import json, os, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "org_audit_driver.py")
FAST = "#!/usr/bin/env bash\necho '[]'\n"
NOPROG = """#!/usr/bin/env bash
[ "$1" = --list-tools ] && { printf 'semgrep\\ngitleaks\\nbandit\\n'; exit 0; }
td=$(mktemp -d "$TMPDIR/review.XXXXXX")
printf 'semgrep\\ta.py\\t3\\tr1\\tmsg\\n' >"$td/raw"
sleep 60
"""
SLOW = """#!/usr/bin/env bash
td=$(mktemp -d "$TMPDIR/review.XXXXXX")
printf 'semgrep\\ta.py\\t3\\tr1\\tmsg\\n' >"$td/raw"
printf 'start semgrep 100\\ndone semgrep 105\\nstart bandit 106\\n' >"$td/progress"
sleep 60
echo '[]'
"""
G = ["git", "-c", "user.name=Jane Smith", "-c", "user.email=jane@example.com"]


def sh(*c):
    r = subprocess.run(c, capture_output=True, text=True)
    assert r.returncode == 0, (c, r.stderr)


def drive(t, stub, extra=()):
    open(os.path.join(t, "rc.sh"), "w").write(stub)
    open(os.path.join(t, "repos.txt"), "w").write("acme/widgets\n")
    env = dict(os.environ, ORG_AUDIT_BASE_URL="file://" + t, ORG_AUDIT_REVIEW_CHECKS=os.path.join(t, "rc.sh"))
    r = subprocess.run([sys.executable, D, "--repos", os.path.join(t, "repos.txt"), "--out", os.path.join(t, "out"), *extra], capture_output=True, text=True, env=env)
    fn = next(f for f in os.listdir(os.path.join(t, "out")) if f.startswith("acme__widgets"))
    return r, json.load(open(os.path.join(t, "out", fn))), r.stdout.splitlines()[1].split("\t")


def main():
    with tempfile.TemporaryDirectory() as t:
        src, bare = os.path.join(t, "src"), os.path.join(t, "acme", "widgets.git")
        sh("git", "init", "-q", src)
        open(os.path.join(src, "big.bin"), "wb").write(b"\0" * (6 * 1024 * 1024))
        sh(*G, "-C", src, "add", "-A")
        sh(*G, "-C", src, "commit", "-qm", "c0")
        sh(*G, "-C", src, "rm", "-q", "big.bin")
        open(os.path.join(src, "a.txt"), "w").write("x")
        sh(*G, "-C", src, "add", "-A")
        sh(*G, "-C", src, "commit", "-qm", "c1")
        os.makedirs(os.path.dirname(bare))
        sh("git", "clone", "-q", "--bare", src, bare)
        sh("git", "-C", bare, "config", "uploadpack.allowFilter", "true")

        r, js, row = drive(t, FAST)
        miss = [x for x in js if x["tool"] == "git-clone" and x["rule"] == "not-checked"]
        assert r.returncode == 0 and row[1] == "OK", r.stdout + r.stderr
        assert len(miss) == 1 and "5m" in miss[0]["message"], js
        assert "git-clone (1 blobs over 5m skipped)" in row[3], row

        r, js, row = drive(t, SLOW, ("--timeout", "5"))
        assert r.returncode == 3 and row[1] == "PARTIAL", r.stdout + r.stderr  # distinct from FAILED (1)
        r2, _, _ = drive(t, SLOW, ("--timeout", "5", "--allow-partial"))
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert any(x["tool"] == "semgrep" and x["rule"] == "r1" for x in js), js
        nc = {x["tool"] for x in js if x["rule"] == "not-checked" and "timed out" in x["message"]}
        assert nc == {"bandit", "review_checks"}, nc

        r, js, row = drive(t, NOPROG, ("--timeout", "5"))  # progress file missing: fail closed, the finished-looking tool counts as timed out
        nc = {x["tool"] for x in js if x["rule"] == "not-checked" and "timed out" in x["message"]}
        assert row[1] == "PARTIAL" and nc == {"semgrep", "gitleaks", "bandit", "review_checks"}, (row, nc)  # gitleaks and bandit come from --list-tools only
    real = os.path.join(os.path.dirname(D), "review_checks.sh")  # the real script names its own tools, hub= array included
    names = subprocess.run(["bash", real, "--list-tools"], capture_output=True, text=True).stdout.split()
    assert {"semgrep", "gitleaks", "trivy", "bash-n", "ruff", "zizmor", "actionlint"} <= set(names) and not {"exit", "tests"} & set(names), names
    print("ok - 14 checks")


main()
