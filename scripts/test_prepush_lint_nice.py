#!/usr/bin/env python3
"""pre-push-verify.sh: (1) a denied/broken `nice` degrades to an un-niced run with one notice, never a failed gate;
(3) with DCR_PREPUSH_CMD unset the project's own lint command (package.json/Makefile/pyproject) is run, and an
unreadable config fails closed."""
import os, subprocess, tempfile, textwrap
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, ".claude/skills/deep-code-review/templates/pre-push-verify.sh")
ENV0 = {k: v for k, v in os.environ.items() if not k.startswith(("DCR_", "GIT_"))}
ENV0.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")


def repo(files):
    d = tempfile.mkdtemp(prefix="dcr-prepush-lint.")
    g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@users.noreply.github.com", "-c", "user.name=T", *a],
                                  check=True, capture_output=True, text=True, env=ENV0).stdout.strip()
    g("init", "-q", "-b", "main")
    g("commit", "-q", "--allow-empty", "-m", "base")
    g("update-ref", "refs/remotes/origin/main", "HEAD")
    for n, t in files.items():
        open(os.path.join(d, n), "w").write(t)
    g("add", "-A")
    g("commit", "-q", "-m", "work")
    return d, g("rev-parse", "HEAD")


def run(d, sha, env=None, path=None):
    e = dict(ENV0, DCR_PREPUSH_DEFAULT_BRANCH="main", **(env or {}))
    if path:
        e["PATH"] = path + os.pathsep + e["PATH"]
    line = f"refs/heads/b {sha} refs/heads/b {'0' * 40}\n"
    return subprocess.run(["bash", HOOK, "origin"], cwd=d, input=line, env=e, capture_output=True, text=True)


# (1) nice present but denied (exits 126 like a sandbox exec denial): gate still runs, one notice
d, sha = repo({"a.txt": "x\n"})
fake = tempfile.mkdtemp(prefix="dcr-fake-nice.")
open(os.path.join(fake, "nice"), "w").write("#!/bin/sh\nexit 126\n")
os.chmod(os.path.join(fake, "nice"), 0o755)
r = run(d, sha, {"DCR_PREPUSH_CMD": "echo gate-ran > gate.out"}, path=fake)
assert r.returncode == 0, r.stderr
assert open(os.path.join(d, "gate.out")).read().strip() == "gate-ran"
assert r.stderr.count("nice unavailable or denied") == 1, r.stderr

# (3) unset command: package.json lint script is reused, not a second config
d, sha = repo({"package.json": '{"scripts":{"lint":"echo linted > lint.out"}}'})
fake = tempfile.mkdtemp(prefix="dcr-fake-npm.")
open(os.path.join(fake, "npm"), "w").write("#!/bin/sh\n[ \"$1 $2\" = 'run lint' ] && echo npm-lint > npm.out\n")
os.chmod(os.path.join(fake, "npm"), 0o755)
r = run(d, sha, path=fake)
assert r.returncode == 0 and "inferred lint: npm run lint" in r.stderr, r.stderr
assert open(os.path.join(d, "npm.out")).read().strip() == "npm-lint"

# Makefile target and pyproject ruff are recognised; nothing recognisable keeps the old fail-closed refusal
d, sha = repo({"Makefile": "lint:\n\techo ok\n"})
assert "make lint" in run(d, sha).stderr
d, sha = repo({"pyproject.toml": "[tool.ruff]\nline-length = 100\n"})
assert "ruff check ." in run(d, sha).stderr
d, sha = repo({"a.txt": "x\n"})
r = run(d, sha)
assert r.returncode != 0 and "DCR_PREPUSH_CMD" in r.stderr

# unreadable lint config fails closed (gate never runs)
d, sha = repo({"package.json": "{not json"})
r = run(d, sha)
assert r.returncode != 0 and "fail closed" in r.stderr, r.stderr
# blank lint value counts as absent; a Makefile `lint :=` variable is not a target; a planted json.py is never imported (-I)
d, sha = repo({"package.json": '{"scripts":{"lint":"  "}}'})
r = run(d, sha); assert r.returncode != 0 and "inferred lint" not in r.stderr, r.stderr
d, sha = repo({"Makefile": "lint := x\n"})
r = run(d, sha); assert r.returncode != 0 and "inferred lint" not in r.stderr, r.stderr
d, sha = repo({"json.py": "open('pwned', 'w').write('x')\n", "Makefile": "lint:\n\ttrue\n"})
r = run(d, sha); assert "make lint" in r.stderr and not os.path.exists(os.path.join(d, "pwned")), r.stderr
assert "pre-push: inferred lint: make lint (set DCR_PREPUSH_CMD for full verify)" in r.stderr
print("ok: nice degrades with one notice; project lint reused; unreadable config fails closed")
