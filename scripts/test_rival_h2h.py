#!/usr/bin/env python3
"""Regression for docs/bench/security-gates-1024/rivals/score_rivals.py (rival rules ported to Python).

Pins the head-to-head scores so a port edit that moves a number fails loudly, pins the vendored rival files by
sha256, proves the hooks-mastery regexes equal the vendored source, and checks that each port can both fire and
stay quiet on held-out inputs (a port that flags nothing would also pass a pure score pin). Secret values are
fake and assembled from fragments so this file never trips the privacy gate. Commands are only classified.
"""
import hashlib, importlib.util, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RIV = ROOT / "docs/bench/security-gates-1024/rivals"
spec = importlib.util.spec_from_file_location("rivals", RIV / "score_rivals.py")
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)

PINS = {"gitleaks-v8.30.1.toml": "e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf",
        "hooks-mastery-pre_tool_use.py.txt": "78006866f793ccd394bc52011582ce48707ceef9d3496e474ab7bcb63365a5da"}
for f, h in PINS.items():  # the gitleaks copy carries `@@` privacy markers; removing them must give the upstream bytes
    assert hashlib.sha256(((ROOT / "scripts" if f.endswith(".toml") else RIV) / f).read_bytes().replace(b"@@", b"")).hexdigest() == h, f"rival source drifted: {f}"

s = sr.scores()
g, h, n = s["gitleaks"], s["hooks-mastery"], s["safety-net"]
assert (g["rules"], len(g["missed"]), len(g["fp"])) == (221, 9, 0), g
assert (len(h["missed"]), len(h["fp"])) == (33, 5), h
assert (len(n["missed"]), len(n["unported"]), len(n["fp"]), len(n["fp_unported"])) == (15, 4, 0, 0), n

# hooks-mastery: every regex literal in the vendored file is in the port, and vice versa.
src = (RIV / "hooks-mastery-pre_tool_use.py.txt").read_text()
lits = set(re.findall(r"^\s+r'(.*?)',?\s*(?:#.*)?$", src, re.M))
assert lits == set(sr.HM_RM + sr.HM_PATHS + sr.HM_ENV), lits ^ set(sr.HM_RM + sr.HM_PATHS + sr.HM_ENV)
assert sr.hooks_mastery("rm -rf build") and not sr.hooks_mastery("git status") and not sr.hooks_mastery("cat .env.sample")

# gitleaks: fires on well-formed fake tokens, stays quiet on placeholders and on the documented EXAMPLE key.
M = "Mq7Zt2Vb9Nx4Lk8RcD3HfJw5Rs1Yp6GuAe3B"
assert "github-pat" in sr.gitleaks_rule("GITHUB_TOKEN=gh" "p_" + M)
assert "aws-access-token" in sr.gitleaks_rule("x=AK" "IAQZXMLP2RTW2NBV47")
assert not sr.gitleaks_rule("GITHUB_TOKEN=gh" "p_" + "x" * 36)
assert not sr.gitleaks_rule("aws_access_key_id = AK" "IAIOSFODNN7EXAMPLE")
assert sr.go2py(r"a(?i)b$") == r"a(?i:b\Z)"

# safety-net subset: known allow/block edges from the pinned source.
for c, want in [("rm -rf /", "block"), ("rm -rf build", "allow"), ("rm -rf ../x", "block"), ("rm -rf /tmp/x", "allow"),
                ("git push --force origin main", "block"), ("git push --force-with-lease origin main", "allow"),
                ("git reset --hard", "block"), ("git reset --soft HEAD~1", "allow"), ("git checkout main", "allow"),
                ("find . -delete", "block"), ("find build -delete", "allow"), ("ls | sh", "block"),
                ("sh -c 'rm -rf /'", "block"), ("echo hi && git clean -fd", "block"), ("$x reset --hard", "unported")]:
    assert sr.analyze(c) == want, (c, sr.analyze(c), want)
print("rival head-to-head port tests: ok")
