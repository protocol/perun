#!/usr/bin/env python3
"""identity_gate: the pre-push hook refuses a push whose commits carry a non-noreply author or committer email, masks the
address, prints the fix, honours the gitignored allowlist, checks only the pushed range, and cannot be skipped through
DCR_PREPUSH_ALLOW_UNSET; perun_doctor WARNs when user.email is personal but the default branch is all noreply.
Hermetic: temp repos, fictional identities only."""
import os, pathlib, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude/skills/deep-code-review")
HOOK, GATE = os.path.join(SKILL, "templates/pre-push-verify.sh"), os.path.join(SKILL, "scripts/identity_gate.py")
ENV0 = {k: v for k, v in os.environ.items() if not k.startswith(("DCR_", "GIT_"))}
NR, ME, ZERO = "1+jane@users.noreply.github.com", "jane@example.com", "0" * 40
_TD = tempfile.TemporaryDirectory(prefix="dcr-identity.")  # the stdlib removes it at exit
TMP = os.path.realpath(_TD.name)
# no host identity, and a plain temp dir never resolves to some parent repo
ENV0.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_CEILING_DIRECTORIES=TMP)
os.environ.clear(); os.environ.update(ENV0, DCR_NO_PROBE="1")  # in-process git calls (doctor) are hermetic too


def git(d, *a, ae=NR, ce=None):
    env = dict(ENV0, GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL=ae, GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL=ce or ae)
    return subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True, env=env).stdout.strip()


def repo(*idents, root_ident=NR):
    """Temp repo: base commit (+ .gitignore for the allowlist) at refs/remotes/origin/main, then one commit per (author, committer)."""
    d = tempfile.mkdtemp(dir=TMP)
    git(d, "init", "-q", "-b", "main")
    pathlib.Path(d, ".gitignore").write_text(".identity-allow.local.txt\n")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base", ae=root_ident)
    git(d, "update-ref", "refs/remotes/origin/main", "HEAD")
    for i, (ae, ce) in enumerate(idents):
        pathlib.Path(d, f"f{i}.txt").write_text(f"{i}\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", f"work {i}", ae=ae, ce=ce)
    return d


def push(d, remote_sha=ZERO, hook=HOOK, **env):
    """(rc, combined output) of the pre-push hook for HEAD of d pushed over remote_sha (ZERO = a new branch)."""
    e = {**ENV0, "DCR_PREPUSH_DEFAULT_BRANCH": "main", "DCR_PREPUSH_CMD": "true", **env}
    line = f"refs/heads/b {git(d, 'rev-parse', 'HEAD')} refs/heads/b {remote_sha}\n"
    r = subprocess.run(["bash", hook, "origin"], cwd=d, input=line, env=e, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def blocked(d, *must, **kw):
    rc, out = push(d, **kw)
    assert rc != 0 and "FAIL -- commit identity" in out, (rc, out)
    assert ME not in out and "jane@" not in out.lower(), "raw address leaked: " + out
    for m in must:
        assert m in out, (m, out)
    return out


def passes(d, **kw):
    rc, out = push(d, **kw)
    assert rc == 0 and "commit identity" not in out, (rc, out)


# --- hook: personal author AND committer blocked; address masked; both fixes named
out = blocked(repo((ME, ME)), "j***@***.com", "git config user.email", "--reset-author", "author", "committer", ".identity-allow.local.txt")
# --- either role alone blocks and names only that role
out = blocked(repo((ME, NR)), "author"); assert "committer" not in out.split("Fix:")[0], out
out = blocked(repo((NR, ME)), "committer"); assert "author " not in out.split("Fix:")[0], out
# --- noreply forms pass (GitHub squash-merge committer, id-less form, upper case, a non-GitHub noreply@)
for ae, ce in [(NR, "noreply@github.com"), ("jane@users.noreply.github.com", NR), ("JANE@Users.NoReply.GitHub.com", "NoReply@Example.com")]:
    passes(repo((ae, ce)))
# --- lookalikes of the noreply form are personal addresses
for bad in ("jane@users.noreply.github.com.example.com", "jane@fake-users.noreply.github.com", "@users.noreply.github.com"):
    blocked(repo((bad, NR)))
# --- allowlist (gitignored, so the tree stays clean): exact, glob, comment/blank lines ignored, `*`; non-matching entry still blocks
for body, ok in [("# mine\n\nJane@Example.com\n", True), ("*@example.com\n", True), ("*\n", True), ("bob@example.com\n# jane@example.com\n", False)]:
    d = repo((ME, ME)); pathlib.Path(d, ".identity-allow.local.txt").write_text(body)
    passes(d) if ok else blocked(d)
# --- range scoping: an already-published personal commit never blocks; a new personal commit on top of it does
d = repo((ME, ME), (NR, NR)); a = git(d, "rev-parse", "HEAD~1")
passes(d, remote_sha=a)
d = repo((NR, NR), (ME, ME)); a = git(d, "rev-parse", "HEAD~1")
out = blocked(d, remote_sha=a)  # only the new commit is listed (the rebase hint may still name the base)
assert f"  {git(d, 'rev-parse', '--short', 'HEAD')} author" in out and f"  {git(d, 'rev-parse', '--short', a)} " not in out, out
# --- new branch: commits another remote-tracking ref already has (a stacked branch) are not re-checked; unpublished ones are
d = repo((ME, ME), (NR, NR)); git(d, "update-ref", "refs/remotes/origin/master", "HEAD~1")
passes(d)
d = repo((ME, ME), (NR, NR)); blocked(d, f"git rebase {git(d, 'rev-parse', 'origin/main')[:12]} --exec")  # hint rebases onto the published fork point
# --- first push: no remote-tracking ref at all, so the whole history (here only a personal root commit) is checked
d = tempfile.mkdtemp(dir=TMP); git(d, "init", "-q", "-b", "main"); pathlib.Path(d, ".gitignore").write_text(".identity-allow.local.txt\n")
git(d, "add", "-A"); git(d, "commit", "-q", "-m", "root", ae=ME)
blocked(d, "j***@***.com", "git rebase --root --exec")
git(d, "commit", "-q", "--amend", "--reset-author", "--no-edit", ae=NR); passes(d)
# --- long lists are capped
blocked(repo(*[(ME, ME)] * 6), "and 2 more")
# --- DCR_PREPUSH_ALLOW_UNSET and a prior PASS do not skip it (the control with a noreply identity passes in the same setup)
unset = {"DCR_PREPUSH_CMD": "", "DCR_PREPUSH_ALLOW_UNSET": "1"}
d = repo((NR, NR)); passes(d, **unset)
d = repo((ME, ME)); blocked(d, **unset)
d = repo((NR, NR)); passes(d); git(d, "commit", "-q", "--amend", "--reset-author", "--no-edit", ae=ME); blocked(d)
# --- a remote sha this clone never fetched (or a malformed one) falls back to the commits no remote-tracking ref has: still checked, no false block
for rs in ("1" * 40, "1" * 38 + "e"):
    passes(repo((NR, NR)), remote_sha=rs)
    blocked(repo((ME, ME)), remote_sha=rs)
# --- fail closed when the range cannot be listed (unknown head, not a repo): exit 2, a message, no traceback
for cwd, head in [(repo((NR, NR)), "1" * 40), (tempfile.mkdtemp(dir=TMP), "HEAD")]:
    r = subprocess.run([sys.executable, "-I", GATE, "--head", head], cwd=cwd, env=ENV0, capture_output=True, text=True)
    assert r.returncode == 2 and "cannot list the pushed commits" in r.stderr and "Traceback" not in r.stderr, r
# --- no python3 script next to the hook or in the repo: one notice, push goes on (documented trade-off)
bare = pathlib.Path(TMP, "bare/templates"); bare.mkdir(parents=True); (bare / "pre-push-verify.sh").write_text(pathlib.Path(HOOK).read_text())
rc, out = push(repo((ME, ME)), hook=str(bare / "pre-push-verify.sh"))
assert rc == 0 and "commit identity not checked" in out, (rc, out)

# --- units
sys.path.insert(0, os.path.join(SKILL, "scripts")); sys.path.insert(0, os.path.join(ROOT, "scripts"))
import identity_gate as ig, perun_doctor
for e in (NR, "jane@users.noreply.github.com", "JANE@Users.NoReply.GitHub.com", "noreply@github.com", "NoReply@Example.com"):
    assert ig.noreply(e), e
for e in (ME, "x@users.noreply.github.com.example.com", "x@fake-users.noreply.github.com", "@users.noreply.github.com",
          "users.noreply.github.com", "noreply@", "no-noreply@example.com", ""):
    assert not ig.noreply(e), e
for e, m in [(ME, "j***@***.com"), ("Jane.Smith@mail.example.co.uk", "J***@***.uk"), ("jane@localhost", "j***@***"), ("nope", "***"), ("", "***")]:
    assert ig.mask(e) == m, (e, ig.mask(e))
assert ig.allowed("Jane@Example.com", ["jane@example.com"]) and ig.allowed("x@y", ["*"]) and not ig.allowed("bob@example.com", ["*@example.org"])
assert ig.allow_patterns(TMP) == []  # missing file: no patterns

# --- doctor: WARN only when the effective user.email is personal AND the default branch's recent authors are all noreply
warn = ig.doctor_warn
d = repo((NR, NR)); git(d, "config", "user.email", ME)
w = warn(d); assert w and "j***@***.com" in w and "git config user.email" in w and ME not in w, w
rows = [r for r in perun_doctor.check(pathlib.Path(d), pathlib.Path(tempfile.mkdtemp(dir=TMP))) if r[1] == "commit identity"]
assert len(rows) == 1 and rows[0][0] == "WARN" and rows[0][2] == w, rows
git(d, "config", "user.email", NR); assert warn(d) is None  # already noreply
git(d, "config", "--unset", "user.email"); assert warn(d) is None  # no identity configured
git(d, "config", "user.email", ME); pathlib.Path(d, ".identity-allow.local.txt").write_text(ME + "\n"); assert warn(d) is None  # allowlisted
d = repo((NR, NR), root_ident=ME); git(d, "config", "user.email", ME); assert warn(d) is None  # main's author is personal: that is its norm
d = repo((ME, ME), (NR, NR)); git(d, "update-ref", "refs/remotes/origin/main", "HEAD"); git(d, "config", "user.email", ME)
assert warn(d) is None  # one personal author among main's recent commits is enough to stay quiet
assert warn(tempfile.mkdtemp(dir=TMP)) is None  # not a repo
d = repo((NR, NR)); git(d, "config", "user.email", ME)
assert not [r for r in perun_doctor.check(pathlib.Path(tempfile.mkdtemp(dir=TMP)), pathlib.Path(d)) if r[1] == "commit identity"]
print("ok: commit identity gate blocks, masks, scopes to the pushed range, cannot be skipped; doctor warns")
