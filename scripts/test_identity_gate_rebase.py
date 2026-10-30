#!/usr/bin/env python3
"""identity_gate: a branch rebased over a newer main is checked for the commits it adds, not for commits main already
published. With --base (the remote's old tip of the branch) the range is HEAD's commits that neither the base nor any
remote-tracking ref has; the rebase hint starts at the published fork point so it never replays public commits.
Hermetic: temp repo, fictional identities only."""
import os, pathlib, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, ".claude/skills/deep-code-review/scripts/identity_gate.py")
NR, ME = "1+jane@users.noreply.github.com", "jane@example.com"
_TD = tempfile.TemporaryDirectory(prefix="dcr-identity-rebase.")  # the stdlib removes it at exit
TMP = os.path.realpath(_TD.name)
# no host identity, and a plain temp dir never resolves to some parent repo
ENV0 = {k: v for k, v in os.environ.items() if not k.startswith(("DCR_", "GIT_"))}
ENV0.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_CEILING_DIRECTORIES=TMP)
D = tempfile.mkdtemp(dir=TMP)


def git(*a, ae=NR):
    env = dict(ENV0, GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL=ae, GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL=ae)
    return subprocess.run(["git", "-C", D, *a], check=True, capture_output=True, text=True, env=env).stdout.strip()


def commit(name, ae=NR):
    pathlib.Path(D, name).write_text(name)
    git("add", "-A"); git("commit", "-q", "-m", name, ae=ae)


def gate(base):
    return subprocess.run([sys.executable, "-I", GATE, "--head", "HEAD", "--base", base], cwd=D, env=ENV0, capture_output=True, text=True, check=False)


git("init", "-q", "-b", "main"); commit("base"); git("update-ref", "refs/remotes/origin/main", "HEAD")
git("checkout", "-q", "-b", "topic"); commit("work")
old = git("rev-parse", "HEAD"); git("update-ref", "refs/remotes/origin/topic", old)  # the branch as the remote has it
# main moves on with a commit from a personal address (the project's norm) and the clone fetches it
git("checkout", "-q", "main"); commit("news", ae=ME); git("update-ref", "refs/remotes/origin/main", "HEAD")
news = git("rev-parse", "HEAD")
git("checkout", "-q", "topic"); git("rebase", "-q", "main")

# force-push of the rebased branch: nothing the push adds is personal, so main's commit must not block it
r = gate(old)
assert r.returncode == 0 and not r.stderr, r

# a new personal commit on top blocks, names only that commit, and the rebase hint starts at main's tip, not at the old branch tip
commit("more", ae=ME)
r = gate(old)
assert r.returncode == 1 and "in 2 pushed commit(s)" in r.stderr, r
assert f"  {git('rev-parse', '--short', 'HEAD')} author" in r.stderr and news[:7] not in r.stderr.split("Fix:")[0], r.stderr
assert f"git rebase {news[:12]} --exec" in r.stderr and old[:12] not in r.stderr, r.stderr

print("ok: identity gate ignores commits a rebased branch took from an already-published main")
