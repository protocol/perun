#!/usr/bin/env python3
"""Tests: org_audit_driver.py --noise-re hands the ERE to review_checks.sh as REVIEW_NOISE_RE; without the flag the child
sees the caller's value unchanged (the default noise paths stay), so an audited repo's own tree is never exempted by default.
A stub review_checks echoes the variable in a row; local file:// repo, no network, fictional names."""
import json, os, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "org_audit_driver.py")
STUB = """#!/usr/bin/env bash
printf '[{"tool":"stub","file":"x","line":0,"rule":"env","message":"%s","text":"x"}]' "${REVIEW_NOISE_RE-UNSET}"
"""
G = ["git", "-c", "user.name=Jane Smith", "-c", "user.email=jane@example.com"]


def sh(*c):
    assert subprocess.run(c, capture_output=True, text=True).returncode == 0, c


def seen(t, extra):
    out = os.path.join(t, "out" + str(len(extra)))
    env = {k: v for k, v in os.environ.items() if k != "REVIEW_NOISE_RE"}
    env.update(ORG_AUDIT_BASE_URL="file://" + t, ORG_AUDIT_REVIEW_CHECKS=os.path.join(t, "rc.sh"))
    subprocess.run([sys.executable, D, "--repos", os.path.join(t, "repos.txt"), "--out", out, *extra], capture_output=True, text=True, env=env, check=True)
    fn = next(f for f in os.listdir(out) if f.startswith("acme__widgets"))
    return next(x["message"] for x in json.load(open(os.path.join(out, fn))) if x["rule"] == "env")


with tempfile.TemporaryDirectory() as t:
    src, bare = os.path.join(t, "src"), os.path.join(t, "acme", "widgets.git")
    sh("git", "init", "-q", src)
    open(os.path.join(src, "a.txt"), "w").write("x")
    sh(*G, "-C", src, "add", "-A")
    sh(*G, "-C", src, "commit", "-qm", "c0")
    os.makedirs(os.path.dirname(bare))
    sh("git", "clone", "-q", "--bare", src, bare)
    open(os.path.join(t, "rc.sh"), "w").write(STUB)
    open(os.path.join(t, "repos.txt"), "w").write("acme/widgets\n")
    assert seen(t, []) == "UNSET", "no flag must leave REVIEW_NOISE_RE unset"
    assert seen(t, ["--noise-re", "(^|/)bench/"]) == "(^|/)bench/", "flag value must reach review_checks"
print("ok - 2 checks")
