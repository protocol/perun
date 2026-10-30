#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=re-touching a recently fixed file needs a class-level artifact, review=2027-01-30
"""refix_gate.py — re-touching a recently-fixed file requires a class-level artifact.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
One private delivery audit (generalized; no identifiers kept) found 86% of
commits reworking earlier work, 26 files fixed ten or more times, and a median
of 22.5 hours between one fix of a file and the next. Each refix was locally
reasonable; the pattern was a bug class being patched one reported instance at
a time. `fix_class_gate.py` (deep-code-review) already forces a pinned test per
`fix:` commit. This gate targets the CHURN signal instead: a change range that
modifies a file which a `fix:` commit touched within the last N hours must
either add/modify a class-level artifact (a test or eval path matching
`--class-glob`) or carry a `Refix-Reason:` trailer saying why not.

HONESTY (read this before citing it)
-------------------------------------
This gate forces a class-level artifact to EXIST in a churning range. It
cannot judge whether that artifact covers the whole bug class, whether it
exercises the churning file at all, or whether the refix was avoidable. Those
stay the reviewer's job. The accurate claim is: "a re-touch of a recently
fixed file cannot land without a test/eval change or a stated reason."

DEFINITIONS
-----------
- Range: the net diff `merge-base(--base, --head)..--head` (three-dot
  semantics, renames split into delete + add so both paths count). Every path
  in that diff is a candidate "modified file".
- Prior fix: a non-merge commit reachable from `--base` whose subject matches
  fix_class_gate.py's `FIX_SUBJECT_RE` (Conventional Commits `fix` type),
  committed at most `--window-hours` before the committer time of `--head`.
  Commits inside the range itself are not prior fixes. The reference clock is
  the head commit's committer time (deterministic, re-runnable), not the wall
  clock; a fix committed after the head commit reports age 0. The walk reads
  all of `--base`'s history and filters by committer time in Python: git's
  `--since` stops the walk at the first commit older than the cutoff, so a
  base (or any commit) with an old committer date would hide newer fixes
  behind it.
- Class artifact: a path added, modified, or renamed-to in the range (never a
  delete) that matches one of the `--class-glob` patterns. Passing any
  `--class-glob` REPLACES the defaults, which are fix_class_gate.py's
  DEFAULT_TEST_GLOBS.
- Exemption: any commit in the range with a non-empty `Refix-Reason:` trailer
  exempts the whole range. A present-but-empty trailer does not.

ONE DEFINITION, NOT TWO: the fix-subject regex, the glob grammar, and the
default test globs are imported from the sibling deep-code-review skill's
`scripts/fix_class_gate.py` (install.sh always ships that skill next to this
one). If it cannot be found, this gate exits 2 rather than guess.

EXIT CODES (fail closed)
------------------------
  0  no file in the range was touched by a prior fix inside the window, or
     every such range carries a class artifact or a Refix-Reason trailer.
  1  at least one churned file and no class artifact or trailer; one
     `REFIX <path> prior-fix=<sha> age=<h>h` line per churned file.
  2  unresolvable input: not a git repo, unresolvable or all-zeros ref, no
     merge base, a git failure mid-walk, a non-positive window, or the
     sibling fix_class_gate.py missing.

USAGE
-----
  refix_gate.py --base REF --head REF [--window-hours 72] [--class-glob GLOB ...]
  refix_gate.py --selftest
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

# Loading the sibling module must not litter __pycache__ into a shipped,
# checksummed skill tree.
sys.dont_write_bytecode = True

OK, FAIL, ERROR = 0, 1, 2
ZERO_SHA = "0" * 40
DEFAULT_WINDOW_HOURS = 72.0

GitRunner = Callable[[list], str]


class GitError(RuntimeError):
    """A git invocation failed; the caller must fail closed."""


def load_fix_class_gate():
    """Import deep-code-review's `fix_class_gate.py` from the sibling skill dir.

    Returns the module, or None when the file is absent (callers exit 2). The
    path is `<skills-root>/deep-code-review/scripts/fix_class_gate.py`, i.e.
    the same host root this script was installed into. Side effect: none
    beyond the import (bytecode writing is disabled at module load).
    """
    path = Path(__file__).resolve().parents[2] / "deep-code-review" / "scripts" / "fix_class_gate.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("fix_class_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_git(repo: str = ".") -> GitRunner:
    """Return a runner that executes `git -C repo <args>` and raises GitError on non-zero exit."""
    def run(args: list) -> str:
        proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed (rc={proc.returncode})")
        return proc.stdout
    return run


def _resolve(git: GitRunner, ref: str) -> str | None:
    """Full commit SHA for `ref`, or None when it does not name a commit."""
    try:
        return git(["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"]).strip() or None
    except GitError:
        return None


def _range_paths(git: GitRunner, mb: str, head: str) -> list[tuple[str, str]]:
    """`[(status_letter, path), ...]` of the net diff mb..head, renames split (NUL-safe)."""
    tokens = git(["diff", "-z", "--name-status", "--no-renames", mb, head]).split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    return [(tokens[i][:1], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


def _refix_reason(git: GitRunner, mb: str, head: str) -> str:
    """Concatenated non-empty `Refix-Reason:` trailer values over the range ('' when none)."""
    out = git(["log", "--format=%(trailers:key=Refix-Reason,valueonly)", f"{mb}..{head}"])
    return out.strip()


def _prior_fixes(git: GitRunner, fcg, base: str, since: int) -> list[tuple[str, int, str]]:
    """`[(sha, committer_ts, subject), ...]` for non-merge fix commits reachable from base since `since`.

    No `--since` on the walk: git stops a `--since` walk at the first commit
    older than the cutoff, so one old-dated commit (e.g. a rebased or
    imported base) would hide every newer fix behind it. The full history is
    read and filtered here by committer timestamp instead.
    """
    out = git(["log", "--no-merges", "--format=%H%x1f%ct%x1f%s", base])
    fixes = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            raise GitError(f"unparseable log line: {line!r}")
        sha, ts, subject = parts
        if int(ts) >= since and fcg.FIX_SUBJECT_RE.match(subject):
            fixes.append((sha, int(ts), subject))
    return fixes


def _files_of(git: GitRunner, sha: str) -> list[str]:
    """Paths one commit touched (root commits included)."""
    out = git(["diff-tree", "-r", "--root", "--no-commit-id", "--name-only", "-z", sha])
    return [p for p in out.split("\0") if p]


def run_gate(git: GitRunner, base: str, head: str, window_hours: float,
             class_globs: tuple | None, fcg) -> tuple[int, list[str]]:
    """Evaluate one range; return (exit_code, printable lines). Pure over the injected git runner.

    Fail-closed ordering: module present, window sane, refs resolvable, merge
    base found; each checked before any verdict so a partial walk never turns
    into a pass.
    """
    if fcg is None:
        return ERROR, ["error: sibling deep-code-review/scripts/fix_class_gate.py not found (fail closed)"]
    if not window_hours > 0:
        return ERROR, [f"error: --window-hours must be > 0 (got {window_hours})"]
    if base == ZERO_SHA:
        return ERROR, ["error: --base is the all-zeros SHA; pass the PR base ref or a computed merge-base"]
    base_sha, head_sha = _resolve(git, base), _resolve(git, head)
    if base_sha is None:
        return ERROR, [f"error: --base {base!r} does not resolve to a commit"]
    if head_sha is None:
        return ERROR, [f"error: --head {head!r} does not resolve to a commit"]
    try:
        mb = git(["merge-base", base_sha, head_sha]).strip()
        if not mb:
            return ERROR, [f"error: no merge base between {base} and {head}"]
        changed = _range_paths(git, mb, head_sha)
        if not changed:
            return OK, ["refix_gate: ok (0 files changed in range)"]
        ref_ts = int(git(["log", "-1", "--format=%ct", head_sha]).strip())
        since = ref_ts - int(window_hours * 3600)
        latest: dict[str, tuple[str, int, str]] = {}
        for sha, ts, subject in _prior_fixes(git, fcg, base_sha, since):
            for path in _files_of(git, sha):
                if path not in latest or ts > latest[path][1]:
                    latest[path] = (sha, ts, subject)
        reason = _refix_reason(git, mb, head_sha)
    except (GitError, ValueError) as exc:
        return ERROR, [f"error: could not evaluate range {base}..{head}: {exc}"]

    paths = sorted({p for _, p in changed})
    churned = [p for p in paths if p in latest]
    if not churned:
        return OK, [f"refix_gate: ok ({len(paths)} file(s) in range, none touched by a fix within {window_hours:g}h)"]
    lines = []
    for p in churned:
        sha, ts, subject = latest[p]
        age = max(0, ref_ts - ts) / 3600
        lines.append(f"REFIX {p} prior-fix={sha[:7]} age={age:.1f}h ({subject})")
    compiled = fcg._compile_globs(tuple(class_globs) if class_globs else fcg.DEFAULT_TEST_GLOBS)
    artifacts = sorted(p for status, p in changed if status != "D" and fcg._matches_any(p, compiled))
    if artifacts:
        lines.append(f"refix_gate: ok ({len(churned)} churned file(s); class artifact present: {artifacts[0]})")
        return OK, lines
    if reason:
        lines.append(f"refix_gate: ok ({len(churned)} churned file(s); exempted by Refix-Reason trailer)")
        return OK, lines
    lines.append(
        f"refix_gate: FAILED ({len(churned)} file(s) re-touched within {window_hours:g}h of a fix; "
        "add a class-level test/eval matching --class-glob, or a Refix-Reason: trailer)"
    )
    return FAIL, lines


# --------------------------------------------------------------------------
# Selftest: offline fake-git fixtures (every branch) + one real throwaway repo.
# --------------------------------------------------------------------------

HOUR = 3600
T0 = 1_700_000_000  # fixed epoch for fixtures; no wall clock involved


def _fake_git(head_ts: int, fixes: list, changed: str, trailer: str = "",
              unresolvable: tuple = (), mb: str = "m" * 40) -> GitRunner:
    """Build a canned git runner. `fixes` = [(sha, ts, subject, [paths])]; `changed` = raw -z diff."""
    def run(args: list) -> str:
        cmd = args[0]
        if cmd == "rev-parse":
            ref = args[-1][: -len("^{commit}")]
            if ref in unresolvable:
                raise GitError(f"unknown revision {ref}")
            return (ref * 40)[:40] + "\n"
        if cmd == "merge-base":
            return mb + "\n"
        if cmd == "diff":
            return changed
        if cmd == "log" and args[1] == "-1":
            return f"{head_ts}\n"
        if cmd == "log" and args[1] == "--no-merges":
            # Every fix, old or new: the gate itself must apply the window.
            return "".join(f"{s}\x1f{t}\x1f{subj}\n" for s, t, subj, _ in fixes)
        if cmd == "log":
            return trailer + "\n"
        if cmd == "diff-tree":
            for s, _, _, paths in fixes:
                if s == args[-1]:
                    return "".join(p + "\0" for p in paths)
            raise GitError("unknown commit")
        raise GitError(f"unexpected git call {args}")
    return run


def _selftest() -> int:
    """Assert every verdict branch on offline fixtures, then once end to end on a real repo."""
    fcg = load_fix_class_gate()
    if fcg is None:
        print("SELFTEST FAILED: sibling fix_class_gate.py not found")
        return 1
    failures: list[str] = []
    ran = [0]
    head_ts = T0 + 100 * HOUR
    fix_a = ("a" * 40, head_ts - 5 * HOUR, "fix(parser): guard empty input", ["src/parser.py"])
    old_fix = ("b" * 40, head_ts - 200 * HOUR, "fix: old one", ["src/parser.py"])
    feat = ("c" * 40, head_ts - 2 * HOUR, "feat: not a fix", ["src/parser.py"])

    def case(label, git, want, must=(), must_not=(), window=72.0, globs=None, mod=fcg):
        ran[0] += 1
        rc, lines = run_gate(git, "base", "head", window, globs, mod)
        out = "\n".join(lines)
        if rc != want:
            failures.append(f"{label}: rc={rc} want {want}: {out}")
        failures.extend(f"{label}: missing {m!r}: {out}" for m in must if m not in out)
        failures.extend(f"{label}: must not contain {m!r}: {out}" for m in must_not if m in out)

    src_only = "M\0src/parser.py\0"
    # Planted violation: re-touch a file fixed 5h ago, no artifact, no trailer -> FIRES.
    case("refix-fires", _fake_git(head_ts, [fix_a], src_only), FAIL,
         must=("REFIX src/parser.py", "prior-fix=aaaaaaa", "age=5.0h"))
    case("class-artifact-passes", _fake_git(head_ts, [fix_a], src_only + "A\0tests/test_parser.py\0"), OK,
         must=("class artifact present: tests/test_parser.py",))
    case("deleted-test-is-not-artifact", _fake_git(head_ts, [fix_a], src_only + "D\0tests/test_parser.py\0"), FAIL)
    case("trailer-exempts", _fake_git(head_ts, [fix_a], src_only, trailer="flake fix, class test in #12"), OK,
         must=("Refix-Reason",))
    case("outside-window-passes", _fake_git(head_ts, [old_fix], src_only), OK, must_not=("REFIX",))
    case("non-fix-subject-ignored", _fake_git(head_ts, [feat], src_only), OK, must_not=("REFIX",))
    case("untouched-file-passes", _fake_git(head_ts, [fix_a], "M\0src/other.py\0"), OK, must_not=("REFIX",))
    case("custom-glob-replaces-defaults", _fake_git(head_ts, [fix_a], src_only + "M\0checks/c.txt\0"), OK,
         globs=["checks/*"])
    case("default-glob-misses-custom-path", _fake_git(head_ts, [fix_a], src_only + "M\0checks/c.txt\0"), FAIL)
    case("latest-prior-fix-named", _fake_git(head_ts, [old_fix, fix_a], src_only), FAIL,
         must=("prior-fix=aaaaaaa",), window=300)
    case("empty-range", _fake_git(head_ts, [fix_a], ""), OK, must=("0 files changed",))
    case("bad-base", _fake_git(head_ts, [fix_a], src_only, unresolvable=("base",)), ERROR)
    case("empty-merge-base", _fake_git(head_ts, [fix_a], src_only, mb=""), ERROR)
    case("bad-window", _fake_git(head_ts, [fix_a], src_only), ERROR, window=0)
    case("missing-sibling-module", _fake_git(head_ts, [fix_a], src_only), ERROR, mod=None)
    ran[0] += 1
    rc, _ = run_gate(_fake_git(head_ts, [], src_only), ZERO_SHA, "head", 72.0, None, fcg)
    if rc != ERROR:
        failures.append(f"zero-base: rc={rc} want {ERROR}")

    # End to end on a real throwaway repo through the CLI (git is local; no network).
    with tempfile.TemporaryDirectory(prefix="refix_gate_selftest_") as tmp:
        repo = Path(tmp)

        def sh(*a: str) -> str:
            return real_git(tmp)(list(a)).strip()

        sh("init", "-q")
        for k, v in (("user.name", "Jane Smith"), ("user.email", "jane@example.com"), ("commit.gpgsign", "false")):
            sh("config", k, v)

        def commit(msg: str, rel: str, body: str) -> str:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(body)
            sh("add", rel)
            sh("commit", "-q", "-m", msg)
            return sh("rev-parse", "HEAD")

        commit("chore: init", "src/a.py", "x = 1\n")
        base = commit("fix(a): clamp x", "src/a.py", "x = 2\n")
        head = commit("style(a): reformat", "src/a.py", "x  = 2\n")
        ran[0] += 2
        proc = subprocess.run([sys.executable, __file__, "--base", base, "--head", head],
                              cwd=tmp, capture_output=True, text=True)
        if proc.returncode != FAIL or "REFIX src/a.py" not in proc.stdout:
            failures.append(f"e2e-fires: rc={proc.returncode} out={proc.stdout}{proc.stderr}")
        head2 = commit("test(a): pin clamp class", "tests/test_a.py", "def test_a(): pass\n")
        proc = subprocess.run([sys.executable, __file__, "--base", base, "--head", head2],
                              cwd=tmp, capture_output=True, text=True)
        if proc.returncode != OK:
            failures.append(f"e2e-artifact: rc={proc.returncode} out={proc.stdout}{proc.stderr}")

    # A base whose committer date is OLDER than a fix behind it must not hide
    # that fix (git's `--since` walk stops at the first older-dated commit).
    with tempfile.TemporaryDirectory(prefix="refix_gate_selftest_olddate_") as tmp:
        repo = Path(tmp)
        sh = real_git(tmp)
        sh(["init", "-q"])
        for k, v in (("user.name", "Jane Smith"), ("user.email", "jane@example.com"), ("commit.gpgsign", "false")):
            sh(["config", k, v])

        def dated(msg: str, rel: str, body: str, when: str) -> str:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(body)
            sh(["add", rel])
            env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
            proc = subprocess.run(["git", "-C", tmp, "commit", "-q", "-m", msg], env=env,
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise GitError(proc.stderr.strip())
            return sh(["rev-parse", "HEAD"]).strip()

        dated("chore: init", "src/a.py", "x = 1\n", "2026-01-09T00:00:00Z")
        dated("fix(a): clamp x", "src/a.py", "x = 2\n", "2026-01-10T00:00:00Z")
        base = dated("chore: imported", "docs/n.txt", "n\n", "2001-01-01T00:00:00Z")
        head = dated("style(a): reformat", "src/a.py", "x  = 2\n", "2026-01-10T01:00:00Z")
        ran[0] += 1
        proc = subprocess.run([sys.executable, __file__, "--base", base, "--head", head],
                              cwd=tmp, capture_output=True, text=True)
        if proc.returncode != FAIL or "REFIX src/a.py" not in proc.stdout:
            failures.append(f"old-dated-base-hides-no-fix: rc={proc.returncode} out={proc.stdout}{proc.stderr}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST OK: refix_gate {ran[0]}/{ran[0]} cases passed")
    return 0


def main(argv: list | None = None) -> int:
    """CLI: `--selftest`, or `--base REF --head REF [--window-hours H] [--class-glob GLOB ...]`."""
    parser = argparse.ArgumentParser(description="Require a class-level test/eval artifact when a range "
                                     "re-touches a file a fix: commit touched within the window.")
    parser.add_argument("--base", help="range base ref (merge-base semantics)")
    parser.add_argument("--head", help="range head ref")
    parser.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_HOURS,
                        help="look-back window for prior fix commits, before the head commit (default 72)")
    parser.add_argument("--class-glob", action="append", dest="class_globs", metavar="GLOB",
                        help="class-artifact glob; repeatable; REPLACES the defaults (fix_class_gate's test globs)")
    parser.add_argument("--selftest", action="store_true", help="run the built-in selftest and exit")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.base or not args.head:
        parser.error("--base and --head are both required")
    code, lines = run_gate(real_git("."), args.base, args.head, args.window_hours,
                           args.class_globs, load_fix_class_gate())
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
