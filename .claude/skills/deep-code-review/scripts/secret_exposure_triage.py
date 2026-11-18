#!/usr/bin/env python3
"""secret_exposure_triage.py: rank gitleaks findings by exposure so the rotate-first order is known. Offline, git only, stdlib only.

Usage: python3 -I secret_exposure_triage.py REPORT.json [REPO] [--json|--tsv] [--keep ROWS.tsv] [--visibility public|private|unknown]
REPORT.json is a gitleaks JSON report (`-f json -r`, the shape review_checks.sh scans with); REPO defaults to ".".

Per finding (one per file + rule + secret, so a secret added in several commits is one row):
  first-seen commit and date, whether that commit is reachable from the default branch / a tag / another branch,
  whether the secret is still in the tree at HEAD and at the default-branch tip (anywhere in the tree, so a renamed or moved file
  still counts), and commits since it was introduced.
Priority: 0 = assume compromised (repo is public or visibility unknown, and the secret is reachable from the default branch):
  revoke/rotate first, then purge history; forks and CI logs may hold copies. 1 = present at the default-branch tip,
  2 = in default-branch history only, 3 = only in a tag or side branch, 4 = not assessable (no Secret and no Commit in the
  report, or a commit no ref contains). --visibility defaults to unknown (fail closed); review_checks.sh passes it from `gh repo view`.

Safety: the secret value is never printed (rows show rule, fingerprint, file:line) and never passed as a process argument: it is
searched for in-process over a streamed `git log --all -p`, and in trees via `git grep -F -f` on a 0600 temp file. No liveness
check, no provider or network call. An empty or "REDACTED" Secret (gitleaks --redact) counts as no secret.
Wired into review_checks.sh under the history scan (tool `secret-exposure`, rules `exposure-p0`..`exposure-p4`); --tsv prints the
`file line rule message` rows it adds. A missing git or a bad REPO exits 2 with one stderr line.
--keep ROWS.tsv limits triage to findings listed there (file, line, rule per line): review_checks.sh passes the rows it kept after
its own .gitleaks-allow / .gitleaksignore filter, so a suppressed finding is never triaged. Without it every finding is triaged.
Edge cases: a secret changed or rewrapped after its first commit is tracked by exact value only; a multi-line secret is not tree-searched
(unknown); a shallow clone cuts "first seen" at the clone boundary; non-UTF-8 blobs and subjects are searched as bytes.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile


def die(msg):
    print(f"secret_exposure_triage: {msg}", file=sys.stderr)
    sys.exit(2)


def gitb(repo, *a):
    p = subprocess.run(["git", "-C", repo, *a], capture_output=True, check=False)
    return p.stdout if p.returncode == 0 else None


def git(repo, *a):
    b = gitb(repo, *a)
    return None if b is None else b.decode("utf-8", errors="replace")


def first_seen(repo, secrets):
    """{secret: (commit, date)}: the oldest commit whose patch text holds each secret, from one streamed pass."""
    todo = {s.encode() for s in secrets}
    found = {}
    if not todo:
        return found
    # ponytail: one commit's patch is held whole in memory; cap per commit if a huge one bites
    p = subprocess.Popen(["git", "-C", repo, "log", "--all", "--reverse", "-p", "--format=%x00%H %cI"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    head, buf = None, []

    def flush():
        blob = b"".join(buf)
        for s in [s for s in todo if head and s in blob]:
            found[s.decode("utf-8", errors="replace")] = tuple(head.split(" ", 1))
            todo.discard(s)

    for line in p.stdout:
        if line.startswith(b"\0"):
            flush()
            head, buf = line[1:].decode("ascii", errors="replace").strip(), []
            if not todo:
                break
        else:
            buf.append(line)
    else:
        flush()
    p.stdout.close()
    p.kill()
    p.wait()
    return found


def default_branch(repo):
    h = git(repo, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if h:
        return h.strip()
    for b in ("main", "master"):
        if git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{b}") is not None:
            return f"refs/heads/{b}"
    return (git(repo, "symbolic-ref", "-q", "HEAD") or "HEAD").strip()


def holds(repo, ref, secret):
    """Is the secret anywhere in ref's tree? True/False, None when unknown. Never on argv: a 0600 pattern file."""
    if not secret or "\n" in secret or "\r" in secret:
        return None
    fd, tmp = tempfile.mkstemp(prefix="exposure-")  # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(secret.encode())
        rc = subprocess.run(["git", "-C", repo, "grep", "-aqF", "-f", tmp, ref], capture_output=True, check=False).returncode
    finally:
        os.unlink(tmp)
    return True if rc == 0 else False if rc == 1 else None


def triage(report, repo=".", keep=None, visibility="unknown"):
    if keep is not None:
        report = [f for f in report if ((f.get("File") or "").removeprefix("./"), str(f.get("StartLine")), f.get("RuleID")) in keep]
    dflt = default_branch(repo)
    secs = {f["Secret"] for f in report if f.get("Secret") not in (None, "", "REDACTED")}
    firsts = first_seen(repo, secs)
    seen, rows = set(), []
    for f in report:
        sec, path = (f.get("Secret") if f.get("Secret") in secs else ""), f.get("File") or ""
        key = (path, f.get("RuleID"), hashlib.sha256(sec.encode()).hexdigest() if sec else f.get("Fingerprint"))
        if key in seen:
            continue
        seen.add(key)
        commit = date = None
        if sec in firsts:  # earliest commit on any ref whose patch holds the exact value
            commit, date = firsts[sec]
        elif f.get("Commit"):
            commit, date = f["Commit"], f.get("Date")
        r = {"rule": f.get("RuleID"), "fingerprint": f.get("Fingerprint"), "file": path, "line": f.get("StartLine"),
             "first_commit": commit, "first_date": date, "in_default": None, "in_tag": None, "in_branch": None,
             "at_head": holds(repo, "HEAD", sec), "at_default": holds(repo, dflt, sec), "commits_since": None}
        if commit:
            refs = (git(repo, "for-each-ref", "--contains", commit, "--format=%(refname)", "refs/heads", "refs/remotes", "refs/tags") or "").split()
            if refs:  # a commit no ref contains (dangling) stays unranked
                r["in_default"] = dflt in refs or git(repo, "merge-base", "--is-ancestor", commit, dflt) is not None
                r["in_tag"] = any(x.startswith("refs/tags/") for x in refs)
                r["in_branch"] = any(x != dflt and not x.startswith("refs/tags/") and not x.endswith("/HEAD") for x in refs)
            n = git(repo, "rev-list", "--count", f"{commit}..HEAD")
            r["commits_since"] = int(n) if n else None
        reach = r["at_default"] or r["in_default"]
        r["priority"] = 0 if reach and visibility != "private" else 1 if r["at_default"] else 2 if r["in_default"] else 3 if (r["in_tag"] or r["in_branch"]) else 4
        rows.append(r)
    return sorted(rows, key=lambda r: (r["priority"], r["file"], r["line"] or 0))


NAMES = {0: "assume compromised: revoke/rotate first, then purge history; forks and CI logs may hold copies",
         1: "rotate first: present at default-branch tip", 2: "rotate next: in default-branch history", 3: "rotate last: only in a tag or side branch", 4: "not assessable"}


def summary(r):
    where = ",".join(k for k, v in (("default", r["in_default"]), ("tag", r["in_tag"]), ("branch", r["in_branch"])) if v) or "-"
    return f"{NAMES[r['priority']]}; first {(r['first_commit'] or '?')[:10]} {r['first_date'] or '?'}; in {where}; at HEAD {r['at_head']}; {r['commits_since']} commits since"


def main(argv):
    args, keep, vis = [a for a in argv[1:] if a not in ("--json", "--tsv")], None, "unknown"
    if "--visibility" in args:
        i = args.index("--visibility")
        vis = args[i + 1] if i + 1 < len(args) else ""
        if vis not in ("public", "private", "unknown"):
            die("--visibility must be public, private or unknown")
        del args[i : i + 2]
    if "--keep" in args:
        i = args.index("--keep")
        try:
            with open(args[i + 1]) as fh:
                keep = {(a[0].removeprefix("./"), a[1], a[2]) for a in (ln.rstrip("\n").split("\t") for ln in fh) if len(a) >= 3}
        except (OSError, IndexError) as e:
            die(f"unreadable --keep file ({type(e).__name__}); nothing triaged")
        del args[i : i + 2]
    if not args:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        sys.exit(2)
    repo = args[1] if len(args) > 1 else "."
    try:
        ok = subprocess.run(["git", "-C", repo, "rev-parse", "--git-dir"], capture_output=True, check=False).returncode == 0
    except OSError:
        die("git not found; nothing triaged")
    if not ok:
        die(f"not a git repository: {repo}; nothing triaged")
    try:
        with open(args[0]) as fh:
            report = json.load(fh)
        if not isinstance(report, list):
            raise ValueError("not a list")
    except (OSError, ValueError) as e:
        die(f"unreadable gitleaks report ({type(e).__name__}); nothing triaged")
    rows = triage(report, repo, keep, vis)
    if "--json" in argv:
        print(json.dumps(rows, indent=1))
    elif "--tsv" in argv:  # file, line, rule, message: the rows review_checks.sh adds
        for r in rows:
            print(f"{r['file']}\t{r['line']}\texposure-p{r['priority']}\t{r['fingerprint']}: {summary(r)}")
    else:
        for r in rows:
            print(f"P{r['priority']} | {r['rule']} {r['fingerprint']} | {r['file']}:{r['line']} | {summary(r)}")
        if not rows:
            print("no findings")


if __name__ == "__main__":
    main(sys.argv)
