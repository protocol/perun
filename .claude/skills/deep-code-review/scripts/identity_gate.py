#!/usr/bin/env python3
# rail: owner=deep-code-review, why=refuse a push whose commits publish a non-noreply git email, review=2027-01-30
"""identity_gate.py -- refuse a push whose commits publish a non-noreply git email.

WHY THIS EXISTS
---------------
Every commit stores an author and a committer email, and a push publishes both
for good. A machine whose global `user.email` is a personal address therefore
leaks it through every branch it pushes, even when the default branch only
carries the host's noreply address. Nothing else on the push path looked at
identity.

THE ONE IMPLEMENTATION. templates/pre-push-verify.sh calls this CLI and
scripts/perun_doctor.py imports `doctor_warn`, so the predicate lives here only.

WHAT COUNTS
-----------
For every commit in the pushed range, the author email and the committer email
must each be a noreply form (`<local>@users.noreply.github.com` or
`noreply@<domain>`, any case) or match a line of the gitignored
`<repo root>/.identity-allow.local.txt`: one email or fnmatch glob per line,
whole-line `#` comments and blank lines ignored, case-insensitive; a lone `*`
allows everything (a host with no noreply form). Like `.banlist.local.txt`
it is per checkout, and it must be gitignored or the hook sees a dirty tree.

Range: every commit of HEAD that neither `--base B` nor any `refs/remotes/<--remote>/*`
ref already has, i.e. only what the push adds: the whole history on a first push,
the new commits otherwise. `B` is left out when it is not a commit in this clone
(the remote tip was never fetched) or is not given (a new branch). Because the
remote-tracking refs are excluded too, a branch rebased onto a newer main is not
blamed for the main commits it now carries (`B..HEAD` would list them).

Not checked (known ceiling): `Co-authored-by:` trailers and other message text.

OUTPUT
------
Never prints an address: `jane@example.com` shows as `j***@***.com`. Names the
commit (short sha) and the role, then the fix. Silent on success. Read-only:
runs `git log`, `git rev-list`, `git cat-file` and `git config`, writes nothing.

EXIT CODES (fail closed)
------------------------
  0  every author and committer email in the range is allowed.
  1  at least one is not (listed on stderr, masked).
  2  the range could not be listed (not a repo, unknown --head): never a silent
     pass.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ALLOW_FILE = ".identity-allow.local.txt"
NOREPLY = "<id>+<username>@users.noreply.github.com"
MAX_LISTED = 10


def noreply(email: str) -> bool:
    """True for `<local>@users.noreply.github.com` (non-empty local part) or `noreply@<domain>`, any case.

    Edge cases: a lookalike such as `x@users.noreply.github.com.example.com` or
    `x@fake-users.noreply.github.com` is False; an empty or `@`-less string is False.
    """
    local, _, domain = email.strip().lower().rpartition("@")
    return bool(local) and (domain == "users.noreply.github.com" or (local == "noreply" and bool(domain)))


def mask(email: str) -> str:
    """`jane@example.com` -> `j***@***.com`: first local char and last domain label only; `***` when unparsable."""
    local, _, domain = email.strip().rpartition("@")
    if not local:
        return "***"
    return f"{local[0]}***@***" + (f".{domain.rpartition('.')[2]}" if "." in domain else "")


def allow_patterns(root: str | Path) -> list[str]:
    """Lower-cased lines of `<root>/.identity-allow.local.txt`; [] when it is missing or unreadable (stricter, never looser)."""
    try:
        lines = (Path(root) / ALLOW_FILE).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [s.lower() for s in (ln.strip() for ln in lines) if s and not s.startswith("#")]


def allowed(email: str, patterns: list[str]) -> bool:
    """True when `email` is a noreply form or matches an allowlist pattern (fnmatch glob, case-insensitive)."""
    return noreply(email) or any(fnmatch.fnmatchcase(email.strip().lower(), p) for p in patterns)


def git(*args: str, cwd: str | Path | None = None) -> str:
    """stdout of `git <args>`; RuntimeError (git's own message) on a non-zero exit."""
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"git {args[0]} exited {r.returncode}")
    return r.stdout


def known(commit: str, root: str | Path) -> bool:
    """True when `commit` names a commit present in this clone (False for an unfetched remote tip or a malformed sha)."""
    return subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root, capture_output=True).returncode == 0


def pushed(head: str, base: str | None, remote: str) -> list[str]:
    """`git log`/`rev-list` arguments for the commits a push of `head` adds: those neither `base` (when given) nor a `remote` tracking ref has."""
    return [head, "--not", *([base] if base else []), f"--remotes={remote}"]


def fork_point(head: str, base: str | None, remote: str, root: str | Path) -> str:
    """Short sha of the first commit below the pushed range (one `base` or a `remote` tracking ref has); "" when none does (a first push)."""
    for ln in git("rev-list", "--boundary", *pushed(head, base, remote), cwd=root).splitlines():
        if ln.startswith("-"):
            return ln[1:13]
    return ""


def violations(head: str, base: str | None, remote: str, root: str | Path) -> tuple[list[tuple[str, str, str]], int]:
    """((short sha, role, email) for each disallowed identity, commits scanned) over the range described in the module docstring."""
    pats = allow_patterns(root)
    rows = [ln.split("\t") for ln in git("log", "--format=%h%x09%ae%x09%ce", *pushed(head, base, remote), cwd=root).splitlines()]
    bad = [(sha, role, e) for sha, ae, ce in rows for role, e in (("author", ae), ("committer", ce)) if not allowed(e, pats)]
    return bad, len(rows)


def doctor_warn(repo: str | Path) -> str | None:
    """WARN text when `repo`'s effective user.email is not allowed but the default branch's last 10 authors all are noreply.

    None when the dir is not a repo, user.email is unset, the address is allowed, no default branch resolves, or that
    branch has any non-noreply author (then a personal address is the project's norm, not a slip). The effective value
    is read (global config included): that is what a commit made here would publish.
    """
    try:
        email = git("config", "user.email", cwd=repo).strip()
        root = git("rev-parse", "--show-toplevel", cwd=repo).strip()
    except RuntimeError:
        return None
    if not email or allowed(email, allow_patterns(root)):
        return None
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        try:
            authors = git("log", "-10", "--format=%ae", ref, cwd=repo).split()
        except RuntimeError:
            continue
        if authors and all(noreply(a) for a in authors):
            return (f"user.email ({mask(email)}) is not a noreply form, but all {len(authors)} most recent commit(s) on {ref} are, so "
                    f"commits made here publish it. Fix: git config user.email {NOREPLY}")
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fail when a pushed commit's author or committer email is not a noreply form.")
    ap.add_argument("--head", required=True, help="tip commit being pushed")
    ap.add_argument("--base", help="the remote's current tip of the branch, excluded with its history; omit (or an unknown commit) for a new branch")
    ap.add_argument("--remote", default="origin", help="remote whose tracking refs are excluded (default origin)")
    a = ap.parse_args(argv)
    try:
        root = git("rev-parse", "--show-toplevel").strip()
        base = a.base if a.base and known(a.base, root) else None  # an unfetched remote tip is not in HEAD's history
        bad, n = violations(a.head, base, a.remote, root)
        anchor = fork_point(a.head, base, a.remote, root) if bad else ""  # replay only the pushed commits, never published ones
    except RuntimeError as e:
        print(f"identity_gate: cannot list the pushed commits ({e}). Fix: check that the pushed ref names a commit in this clone.",
              file=sys.stderr)
        return 2
    if not bad:
        return 0
    print(f"identity_gate: {len(bad)} non-noreply email(s) in {n} pushed commit(s); a push publishes them for good (masked):", file=sys.stderr)
    for sha, role, e in bad[:MAX_LISTED]:
        print(f"  {sha} {role:<9} {mask(e)}", file=sys.stderr)
    if len(bad) > MAX_LISTED:
        print(f"  ... and {len(bad) - MAX_LISTED} more", file=sys.stderr)
    redo = f"git rebase {anchor} --exec" if anchor else "git rebase --root --exec"
    print(f"Fix: git config user.email {NOREPLY}, then rewrite the commit(s):\n"
          f"  tip only:  git commit --amend --reset-author\n"
          f"  all:       {redo} 'git commit --amend --reset-author --no-edit'\n"
          f"A deliberate personal address: list it (one per line, globs ok) in {ALLOW_FILE}, which must be gitignored.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
