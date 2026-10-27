#!/usr/bin/env python3
"""union_overlap.py [--repo DIR] --base REF [--plan PATH...] --mine PR_OR_REF... --other PR_OR_REF... | --selftest

WHY: two machines each building a merge union raced into stale trains. Before merging, list the files the
candidate PRs and the other in-flight union both touch (`git diff --name-only --no-renames <merge-base> <ref>` (a rename counts both paths)).
A PR number N resolves to `refs/pull/N/head` (fetch it first); anything else is used as a ref.
Prints one overlapping path per line, exit 1; prints `no overlap` exit 0; prints `COULD_NOT_CHECK: <why>`
and exits 2 on ANY git error (unknown ref, no merge-base) - never 0 on an unchecked pair.
Lane start (before any build): `--plan PATH...` adds the paths a new lane declares it will touch to the --mine side,
so a lane planning the same files as an open PR or another lane is flagged before it builds.
Limit: path-level overlap only; two PRs editing different hunks of one file still report that file.
"""
import argparse
import os
import posixpath
import subprocess
import sys
import tempfile


class Fail(Exception):
    pass


def git(repo, *a):
    try:
        p = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, errors="surrogateescape")
    except (OSError, UnicodeError) as e:
        raise Fail("git %s: %s" % (" ".join(a[:2]), e))
    if p.returncode:
        raise Fail("git %s: %s" % (" ".join(a[:2]), p.stderr.strip() or "exit %d" % p.returncode))
    return p.stdout


def files(repo, base, ref):
    ref = "refs/pull/%s/head" % ref if ref.isdigit() else ref
    mb = git(repo, "merge-base", base, ref).strip()
    return set(git(repo, "diff", "--name-only", "--no-renames", mb, ref).split("\n")) - {""}


def _plan_path(p):
    n = posixpath.normpath(p)
    if p.endswith("/") or n.startswith("/") or n == ".." or n.startswith("../") or n == ".":
        raise Fail("--plan needs repo-relative file paths, got %r" % p)
    return n


def overlap(repo, base, mine, other, plan=()):
    if not (mine or plan) or not other:
        raise Fail("need at least one --mine (or --plan) and one --other")
    plan = set(map(_plan_path, plan))
    a = plan.union(*(files(repo, base, r) for r in mine))
    b = set().union(*(files(repo, base, r) for r in other))
    return sorted(a & b)


def selftest():
    d = tempfile.mkdtemp(prefix="union_overlap_")

    def g(*a):
        subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                       check=True, capture_output=True)

    def commit_on(branch, name):
        g("checkout", "-q", "-b", branch, "main")
        open(os.path.join(d, name), "w").write(branch)
        g("add", name)
        g("commit", "-q", "-m", branch)

    g("init", "-q", "-b", "main")
    open(os.path.join(d, "base.txt"), "w").write("line one\nline two\nline three\nline four\n")
    g("add", "base.txt")
    g("commit", "-q", "-m", "base")
    commit_on("a", "shared.txt")
    commit_on("b", "shared.txt")
    commit_on("c", "own.txt")
    g("checkout", "-q", "-b", "r", "main")
    g("mv", "base.txt", "moved.txt")
    g("commit", "-q", "-m", "rename")
    g("checkout", "-q", "-b", "e", "main")
    open(os.path.join(d, "base.txt"), "a").write("edit\n")
    g("commit", "-q", "-am", "edit")
    assert overlap(d, "main", ["r"], ["e"]) == ["base.txt"], "rename failed open"
    assert overlap(d, "main", ["a"], ["b"]) == ["shared.txt"], "overlap missed"
    assert overlap(d, "main", ["a"], ["c"]) == [], "false overlap"
    for bad in (["nope"], ["99"]):
        try:
            overlap(d, "main", ["a"], bad)
            raise AssertionError("git error not surfaced")
        except Fail:
            pass
    assert main(["--repo", d, "--base", "main", "--mine", "a"]) == 2, "empty --other"
    assert main(["--repo", d, "--base", "main", "--other", "a"]) == 2, "empty --mine"
    assert main(["--repo", d, "--base", "nobase", "--mine", "a", "--other", "b"]) == 2, "bad --base"
    assert main(["--repo", os.path.join(d, "missing"), "--base", "main", "--mine", "a", "--other", "b"]) == 2, "non-repo dir"
    assert main(["--repo", d, "--base", "main", "--mine", "a", "--other", "b"]) == 1
    assert main(["--repo", d, "--base", "main", "--mine", "a", "--other", "c"]) == 0
    assert main(["--repo", d, "--base", "main", "--mine", "a", "--other", "nope"]) == 2
    print("union_overlap selftest: ok")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--mine", nargs="+", default=[])
    ap.add_argument("--other", nargs="+", default=[])
    ap.add_argument("--plan", nargs="+", default=[])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest() or 0
    try:
        hit = overlap(args.repo, args.base, args.mine, args.other, args.plan)
    except Fail as e:
        print("COULD_NOT_CHECK: %s" % e)
        return 2
    print("\n".join(hit[:50] + (["+%d more" % (len(hit) - 50)] if len(hit) > 50 else [])) if hit else "no overlap")
    return 1 if hit else 0


if __name__ == "__main__":
    sys.exit(main())
