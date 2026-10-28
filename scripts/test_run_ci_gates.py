#!/usr/bin/env python3
"""run-ci-tests.sh runs the privacy gate and the trigger lint too: a planted banned token and a trigger-path commit with no
mechanism each fail the runner before any test; a clean tree passes; an unresolvable trigger base fails closed."""
import os, shutil, subprocess, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RUN_CI"))}
ENV.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
d = tempfile.mkdtemp(prefix="dcr-runci.")
g = lambda *a, **k: subprocess.run(["git", "-C", d, "-c", "user.email=t@example.com", "-c", "user.name=T", *a], check=True, capture_output=True, env=ENV)
for rel in ("scripts/run-ci-tests.sh", "scripts/ci-gates.sh", "scripts/secret_scan.py", "scripts/secret-scan-allow.txt", "scripts/gitleaks-v8.30.1.toml", ".claude/skills/deep-code-review/scripts/fix_class_gate.py", ".claude/skills/agentic-delivery/scripts/scrub_env.sh"):
    os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
    shutil.copy(os.path.join(ROOT, rel), os.path.join(d, rel))
os.makedirs(os.path.join(d, "scripts/ci-tests.d"))
open(os.path.join(d, "scripts/ci-tests.d/ok.sh"), "w").write("[ \"$GH_TOKEN\" = invalid ] && [ -z \"${SSH_AUTH_SOCK:-}\" ]\n")
open(os.path.join(d, ".banlist.txt"), "w").write("# banlist\nPLANTED-BANNED-TOKEN\n")
g("init", "-q", "-b", "main"); g("add", "-A"); g("commit", "-q", "-m", "base"); g("update-ref", "refs/remotes/origin/main", "HEAD")


def run(env=None):
    return subprocess.run(["bash", "scripts/run-ci-tests.sh"], cwd=d, capture_output=True, text=True, env=dict(ENV, **(env or {})))


r = run(); assert r.returncode == 0, r.stderr
open(os.path.join(d, "leak.txt"), "w").write("see PLANTED-BANNED-TOKEN\n")
r = run(); assert r.returncode != 0 and "FAIL privacy" in r.stderr, r.stderr
os.remove(os.path.join(d, "leak.txt"))
os.rename(os.path.join(d, ".banlist.txt"), os.path.join(d, "ban.off"))
r = run(); assert r.returncode != 0 and "fail closed" in r.stderr, r.stderr  # missing banlist must not skip the privacy scan
os.rename(os.path.join(d, "ban.off"), os.path.join(d, ".banlist.txt"))
os.makedirs(os.path.join(d, ".claude/skills/x/references"))
open(os.path.join(d, ".claude/skills/x/references/a.md"), "w").write("lesson\n")
g("add", "-A"); g("commit", "-q", "-m", "prose lesson, no mechanism")
r = run(); assert r.returncode != 0 and "FAIL trigger lint" in r.stderr, r.stderr
g("update-ref", "-d", "refs/remotes/origin/main")
r = run(); assert r.returncode != 0 and "no base" in r.stderr, r.stderr
print("ok: run-ci-tests.sh runs privacy and trigger lint, fails closed")
