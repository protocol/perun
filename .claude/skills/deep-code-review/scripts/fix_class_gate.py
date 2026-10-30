#!/usr/bin/env python3
# rail: owner=deep-code-review, why=every fix commit must touch a pinned test or say why not, review=2027-01-30
"""fix_class_gate.py — every fix commit must touch a pinned test, or say why not.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
A bug gets "fixed" one reported case at a time — four, five, six commits in a
row, same shape, no regression test ever pinned — so the bug class keeps
resurfacing under a new input each time. This tool enforces one narrow,
mechanical precondition on every `fix:`-labeled commit in a range: it must add
or modify at least one path on a documented test surface, or it must carry a
`No-Test-Reason:` trailer explaining why it doesn't. Nothing more.

HONESTY (read this before wiring it into CI or citing it in a report)
-----------------------------------------------------------------------
This gate verifies ONLY that a fix commit touched a test-surface path or
declared why not. It does NOT and CANNOT verify that the test actually pins
the whole bug class rather than the one reported case — that a fix scoped to
an enumerated list is judged against that list, and a green test proves
non-regression of the named cases, not completeness against the rest of the
tree, stays the reviewer's job (see `references/method.md`, class-discipline
passage). Any claim that this tool "enforces whole-class fixes" is a
fabrication. The accurate claim is: it enforces a pinned test per fix.

MERGE COMMITS ARE NOT CHECKED IN DEFAULT MODE (known bypass). The default
(fix-subject) range walk uses `git rev-list --no-merges`, so every merge
commit is skipped — even one whose subject is `fix:`. A so-called evil merge
(a merge commit that carries its own code change beyond resolving the two
parents) can therefore introduce an untested fix and default mode will not
see it. If that matters for a repo, forbid code changes in merge commits by
policy/review, or squash/rebase instead of merging. Trigger mode (below) DOES
evaluate merge commits, by their own changes.

WHAT COUNTS AS A "FIX" COMMIT
------------------------------
The commit subject matches, case-sensitively on the literal `fix`:
    ^fix(\\([^)]*\\))?!?:
i.e. `fix:`, `fix(scope):`, `fix!:`, `fix(scope)!:`. This is Conventional
Commits' `fix` type, including its optional scope and breaking-change `!`.
It deliberately does NOT match `fixture:`, `fixes:`, or any subject where
`fix` is not immediately followed by `(`, `!`, or `:` — those are not the
Conventional Commits `fix` type and are silently ignored (not a failure).

WHAT COUNTS AS "TOUCHING A TEST SURFACE"
------------------------------------------
The commit's diff (`git diff-tree --name-status`) has at least one path that
is ADDED, MODIFIED, RENAMED, or COPIED (never a DELETE-only path — deleting a
test file is not adding coverage) whose new/current path matches one of the
`--test-glob` patterns. Glob syntax: `*` matches within one path segment,
`**` matches across segments (including zero), `?` matches one character.
Default globs (used only when `--test-glob` is never passed; passing any
`--test-glob` REPLACES the defaults, it does not add to them):
    tests/**  test/**  **/*_test.*  **/*.test.*  **/*.spec.*
    **/test_*.py  spec/**  **/evals/*.json

THE `No-Test-Reason` ESCAPE HATCH
------------------------------------
A fix commit with no test-surface touch still PASSES if its trailer block
carries `No-Test-Reason: <non-empty text>` (read via
`git log --format=%(trailers:key=No-Test-Reason,valueonly)`, so folded/
multi-line trailer values are honored the same way `git interpret-trailers`
would resolve them). A present-but-empty trailer (`No-Test-Reason:` with
nothing after it, or only whitespace) does NOT exempt the commit — the point
is a stated reason, not a magic keyword.

TRIGGER MODE (`--trigger-glob`, the lesson-to-mechanism gate)
----------------------------------------------------------------
Passing `--trigger-glob GLOB` (repeatable) switches WHICH commits are in
scope and WHICH trailer exempts them; everything else (test-surface
matching, fail-closed exits) is shared. In trigger mode a
commit is in scope iff it ADDS, MODIFIES, RENAMES, or COPIES a path matching
a trigger glob (deleting a trigger path alone does not trigger — removing
prose adds no lesson); its subject is ignored. Two refinements:
  - Merge commits are walked, and judged by their OWN changes: the diff from
    `git merge-tree --write-tree <p1> <p2>` (the clean automatic merge of
    the two parents) to the merge commit. A clean merge that adds nothing
    has no changes and is out of scope; an evil merge that adds prose is in
    scope. When that result is unavailable (git older than 2.38, a
    conflicted merge, an octopus merge, unrelated histories) the merge's
    diff against its FIRST parent is used instead — fail closed, a merge is
    never skipped. `merge-tree --write-tree` writes the merged tree into the
    object database (no ref, no worktree change).
  - A version-stamp-only edit is not a trigger: when every changed trigger
    path is a `SKILL.md` whose only changed lines (added and removed) are
    frontmatter `version:` lines (`version: "1.2.3"`), the commit files no
    lesson (a release bumps several stamps at once) and is out of scope. One
    changed line of anything else, or a `version:` line outside the
    frontmatter, keeps it in scope.
An in-scope commit passes iff
it also touches a `--test-glob` path that does NOT itself match a trigger
glob (a path on both lists never satisfies itself — otherwise a trigger edit
would be its own mechanism), or carries a non-empty `No-Mechanism-Reason:`
trailer (same empty-value rule as `No-Test-Reason`). The intended use: every
commit that files a lesson as prose (a SKILL.md or reference edit) must land
an executable mechanism beside it (an eval, a gate script, a selftest) or
state why not. Same honesty limit as above: it proves a mechanism path was
touched, never that the mechanism pins the lesson. Without `--trigger-glob`
the default mode (fix-subject trigger + `No-Test-Reason`) is unchanged.

EXIT CODES (fail-closed; every branch below is load-bearing)
---------------------------------------------------------------
  0  every in-scope commit (fix, or trigger in trigger mode) passed
     (touched a test surface or was exempted by a non-empty
     `No-Test-Reason` / `No-Mechanism-Reason` trailer), including the
     legitimately-empty case of zero commits in range. In default mode
     merge commits are never counted (see above), so a range whose only fix
     is a merge commit also exits 0; trigger mode counts them.
  1  at least one in-scope commit failed; each is printed as its own FAIL line.
  2  FAIL CLOSED — the range could not be evaluated at all, never a silent
     pass: not a git repository; an empty `--trigger-glob` (it would match
     nothing and pass silently); `--base`/`--head` unresolvable; `--base` is
     the all-zeros SHA (the value CI hands a brand-new branch push — pass the
     PR base ref or a computed merge-base instead); or the range itself
     could not be walked (a real git error, e.g. an unrelated/unreachable
     history). An empty-but-resolvable range (base and head are the same
     commit) is distinct from all of this and exits 0 with an explicit
     `0 commits in range` line.

USAGE
-----
  fix_class_gate.py --base <ref> --head <ref> [--test-glob GLOB ...]
                    [--trigger-glob GLOB ...]
  fix_class_gate.py --selftest
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OK = 0
FAIL = 1
ERROR = 2

ZERO_SHA = "0" * 40

# Conventional Commits `fix` type only: `fix`, `fix(scope)`, `fix!`,
# `fix(scope)!`, each followed by `:`. Case-sensitive on the literal `fix` so
# `Fix:`/`FIX:` (not Conventional Commits) are deliberately not matched.
FIX_SUBJECT_RE = re.compile(r"^fix(\([^)]*\))?!?:")

DEFAULT_TEST_GLOBS = (
    "tests/**",
    "test/**",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
    "**/test_*.py",
    "spec/**",
    "**/evals/*.json",
)


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Translate one glob pattern into a compiled full-match regex.

    `**/` matches zero or more leading path segments (so `**/*_test.*`
    matches both `bar_test.py` and `foo/bar_test.py`); a bare trailing `**`
    matches the rest of the path including `/` (so `tests/**` matches every
    path under `tests/`); a lone `*` matches within one segment; `?` matches
    one non-`/` character. Everything else is a literal, regex-escaped.
    """
    out = ["^"]
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*" and pattern[i:i + 2] == "**":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def _compile_globs(globs: tuple[str, ...]) -> list[re.Pattern]:
    """Compile a glob tuple once per run; called with either defaults or CLI globs."""
    return [_glob_to_regex(g) for g in globs]


def _matches_any(path: str, compiled_globs: list[re.Pattern]) -> bool:
    """True iff `path` (a git-relative, `/`-separated path) matches any compiled glob."""
    return any(rx.match(path) for rx in compiled_globs)


class GitError(RuntimeError):
    """A git invocation failed in a way the caller must fail closed on."""


def _run_git(repo: str, args: list[str]) -> str:
    """Run `git <args>` in `repo`; return stdout, or raise GitError with stderr on failure."""
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed (rc={proc.returncode})")
    return proc.stdout


def _is_git_repo(repo: str) -> bool:
    """True iff `repo` is inside a git work tree (never raises)."""
    proc = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _resolve_commit(repo: str, ref: str) -> str | None:
    """Resolve `ref` to a full commit SHA, or None if it does not resolve to a commit."""
    proc = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _list_range_shas(repo: str, base: str, head: str, include_merges: bool = False) -> list[str]:
    """Commit SHAs in `base..head`, oldest first; merges only when `include_merges`.

    Raises GitError on a real git failure.
    """
    args = ["rev-list", "--reverse", f"{base}..{head}"]
    if not include_merges:
        args.insert(1, "--no-merges")
    out = _run_git(repo, args)
    return [line for line in out.splitlines() if line.strip()]


def _parents(repo: str, sha: str) -> list[str]:
    """Parent SHAs of `sha` (empty for a root commit)."""
    return _run_git(repo, ["log", "-1", "--format=%P", sha]).split()


def _merge_diff_base(repo: str, parents: list[str]) -> str:
    """The revision a merge commit's OWN changes are measured from.

    For a two-parent merge, the tree `git merge-tree --write-tree` produces
    for a clean automatic merge of the parents: diffing the merge commit
    against it leaves only what the merge itself added (an evil merge). When
    that tree is unavailable (merge-tree missing or too old, the automatic
    merge conflicts, more than two parents, unrelated histories), return the
    FIRST parent instead, so the merge is judged on everything it brings in:
    fail closed, never skipped. Side effect: merge-tree writes the merged
    tree object into the object database (no ref or worktree change).
    """
    if len(parents) == 2:
        proc = subprocess.run(
            ["git", "-C", repo, "merge-tree", "--write-tree", parents[0], parents[1]],
            capture_output=True,
            text=True,
        )
        tree = proc.stdout.split("\n", 1)[0].strip()
        if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", tree):
            return tree
    return parents[0]


# A SKILL.md frontmatter version stamp, e.g. `  version: "1.436.0"`.
VERSION_STAMP_RE = re.compile(r'^\s*version:\s*"?[0-9][0-9A-Za-z.+-]*"?\s*$')
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _frontmatter_end(repo: str, rev: str, path: str) -> int:
    """1-based line number of the closing `---` of `rev:path`'s frontmatter, or 0 if none."""
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "blob", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    lines = proc.stdout.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return 0
    for i, line in enumerate(lines[1:], start=2):
        if line.rstrip() == "---":
            return i
    return 0


def _version_stamp_only(repo: str, old: str, new: str, path: str) -> bool:
    """True iff `path` is a SKILL.md whose only changes old->new are frontmatter `version:` lines.

    Reads a zero-context patch (`diff-tree -p -U0`, plumbing, so user diff
    config cannot reshape it) and requires every added and removed line to
    match VERSION_STAMP_RE and to sit inside that side's frontmatter. Any
    other changed line, a mode-only change, or a file without frontmatter
    returns False (the commit stays in scope — fail closed); a failing git
    call raises GitError, which the caller turns into exit 2.
    """
    if path.rsplit("/", 1)[-1] != "SKILL.md":
        return False
    patch = _run_git(repo, ["diff-tree", "-p", "-U0", "--no-color", "--no-ext-diff",
                            old, new, "--", path])
    old_end = _frontmatter_end(repo, old, path)
    new_end = _frontmatter_end(repo, new, path)
    changed = 0
    old_line = new_line = 0
    in_hunk = False
    for line in patch.split("\n"):
        m = _HUNK_RE.match(line)
        if m:
            in_hunk = True
            old_line, new_line = int(m.group(1)), int(m.group(3))
            continue
        if not in_hunk or not line or line.startswith("\\"):
            continue
        if line[0] == "-":
            if not (VERSION_STAMP_RE.match(line[1:]) and 1 < old_line < old_end):
                return False
            old_line += 1
            changed += 1
        elif line[0] == "+":
            if not (VERSION_STAMP_RE.match(line[1:]) and 1 < new_line < new_end):
                return False
            new_line += 1
            changed += 1
        else:
            return False
    return changed > 0


def _subject(repo: str, sha: str) -> str:
    """First line (subject) of `sha`'s commit message."""
    return _run_git(repo, ["log", "-1", "--format=%s", sha]).strip()


def _short_sha(repo: str, sha: str) -> str:
    """Git's own abbreviated form of `sha` (report-friendly, unique in this repo)."""
    return _run_git(repo, ["rev-parse", "--short", sha]).strip()


def _trailer_value(repo: str, sha: str, key: str) -> str:
    """Value of `sha`'s `key` trailer (`No-Test-Reason` or `No-Mechanism-Reason`), or `''` if absent/empty.

    `%(trailers:...,valueonly)` resolves folded (multi-line) trailer values the
    same way `git interpret-trailers` would, and yields `''` for both "trailer
    absent" and "trailer present with no value" — both are treated as
    not-exempting by the caller, which is the point: a bare keyword doesn't
    count as a stated reason.
    """
    out = _run_git(
        repo,
        ["log", "-1", f"--format=%(trailers:key={key},valueonly)", sha],
    )
    return out.strip()


def _changed_paths(repo: str, *revs: str) -> list[tuple[str, bool]]:
    """`[(path, counts_as_add_or_modify), ...]` touched by one non-merge commit, or between two revs.

    One rev: the commit's own diff against its parent. Two revs (old, new):
    the diff between them (used for a merge commit's own changes).

    Uses NUL-terminated `--name-status -z` output so paths with spaces or tabs
    never desync the parser. A rename/copy (`R`/`C`) counts its NEW path as
    modified (the old path is not separately reported — its removal alone
    would never satisfy "touches a test surface"). A delete-only path (`D`)
    is reported with `counts_as_add_or_modify=False`: removing a test file is
    never sufficient to pass this gate.
    """
    out = _run_git(
        repo,
        ["diff-tree", "-r", "--no-commit-id", "--name-status", "-z", *revs],
    )
    tokens = out.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    results: list[tuple[str, bool]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        i += 1
        code = status[0] if status else ""
        if code in ("R", "C"):
            i += 1  # old path, not reported on its own
            new_path = tokens[i]
            i += 1
            results.append((new_path, True))
        elif code == "D":
            path = tokens[i]
            i += 1
            results.append((path, False))
        else:
            path = tokens[i]
            i += 1
            results.append((path, True))
    return results


def run_gate(repo: str, base: str, head: str, test_globs: tuple[str, ...],
             trigger_globs: tuple[str, ...] = ()) -> tuple[int, list[str]]:
    """Evaluate `base..head` in `repo`; return (exit_code, printable lines).

    Empty `trigger_globs` = default mode (a `fix:` subject puts a commit in
    scope, `No-Test-Reason` exempts it; merges skipped). Non-empty = trigger
    mode (touching a trigger path puts it in scope unless every such touch is
    a SKILL.md frontmatter version stamp, merges are judged by their own
    changes, `No-Mechanism-Reason` exempts, and a test-surface path that also
    matches a trigger glob never counts).

    Fail-closed ordering: repo-ness, then the all-zeros sentinel, then ref
    resolution, then the range walk, are each checked before any commit is
    inspected — so an unresolvable input can never fall through to a 0/1
    verdict on a partial or wrong commit set.
    """
    lines: list[str] = []

    if not _is_git_repo(repo):
        return ERROR, [f"error: {repo!r} is not a git repository"]

    if base == ZERO_SHA:
        return ERROR, [
            "error: --base is the all-zeros SHA (git's placeholder for a new-branch "
            "push). This is not a usable diff base. Pass the pull request's declared "
            "base ref, or a computed `git merge-base` between the branches, instead."
        ]

    base_sha = _resolve_commit(repo, base)
    if base_sha is None:
        return ERROR, [f"error: --base {base!r} does not resolve to a commit"]
    head_sha = _resolve_commit(repo, head)
    if head_sha is None:
        return ERROR, [f"error: --head {head!r} does not resolve to a commit"]

    compiled_globs = _compile_globs(test_globs)
    compiled_triggers = _compile_globs(trigger_globs)
    trigger_mode = bool(compiled_triggers)

    try:
        shas = _list_range_shas(repo, base_sha, head_sha, include_merges=trigger_mode)
    except GitError as exc:
        return ERROR, [f"error: could not walk range {base}..{head}: {exc}"]

    if not shas:
        return OK, ["0 commits in range"]

    kind, key = ("trigger", "No-Mechanism-Reason") if trigger_mode else ("fix", "No-Test-Reason")
    fails: list[str] = []
    total = 0
    exempted = 0

    # Any git failure mid-walk (unreadable parents, diff, trailer) is a
    # fail-closed ERROR, never a partial verdict.
    try:
        for sha in shas:
            subject = _subject(repo, sha)
            if trigger_mode:
                parents = _parents(repo, sha)
                if len(parents) > 1:
                    old, new = _merge_diff_base(repo, parents), sha
                    changed = _changed_paths(repo, old, new)
                else:
                    old, new = (parents[0] if parents else ""), sha
                    changed = _changed_paths(repo, sha)
                triggered = [
                    path for path, counts in changed
                    if counts and _matches_any(path, compiled_triggers)
                ]
                # A commit whose every trigger-path change is a SKILL.md
                # frontmatter version stamp files no lesson (release bumps).
                in_scope = bool(triggered) and not (
                    old and all(_version_stamp_only(repo, old, new, p) for p in triggered)
                )
            else:
                in_scope = bool(FIX_SUBJECT_RE.match(subject))
                changed = _changed_paths(repo, sha) if in_scope else []
            if not in_scope:
                continue
            total += 1
            touched_test = any(
                counts
                and _matches_any(path, compiled_globs)
                and not _matches_any(path, compiled_triggers)
                for path, counts in changed
            )
            if touched_test:
                continue
            if _trailer_value(repo, sha, key):
                exempted += 1
                continue
            short = _short_sha(repo, sha)
            what = "trigger path touched, " if trigger_mode else ""
            fails.append(
                f"FAIL {short} {subject} — {what}no test surface touched and no {key} trailer"
            )
    except GitError as exc:
        return ERROR, [f"error: could not evaluate range {base}..{head}: {exc}"]

    lines.extend(fails)
    if fails:
        lines.append(
            f"fix_class_gate: FAILED ({total} {kind} commit(s) checked, "
            f"{len(fails)} failing, {exempted} exempted by trailer)"
        )
        return FAIL, lines

    lines.append(f"fix_class_gate: ok ({total} {kind} commit(s) checked, {exempted} exempted by trailer)")
    return OK, lines


# --------------------------------------------------------------------------
# Selftest
# --------------------------------------------------------------------------

_GIT_ENV_NAME = "Jane Smith"
_GIT_ENV_EMAIL = "jane@example.com"


def _sh(repo: Path, *args: str) -> str:
    """Run one git command in the selftest's throwaway repo; raise on failure."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _init_repo(repo: Path) -> None:
    """Create a throwaway git repo with placeholder identity and no gpg signing."""
    repo.mkdir(parents=True, exist_ok=True)
    _sh(repo, "init", "-q")
    _sh(repo, "config", "user.name", _GIT_ENV_NAME)
    _sh(repo, "config", "user.email", _GIT_ENV_EMAIL)
    _sh(repo, "config", "commit.gpgsign", "false")
    _sh(repo, "config", "tag.gpgsign", "false")


def _commit(repo: Path, message: str, files: dict[str, str], delete: list[str] | None = None) -> str:
    """Write/update `files`, delete `delete`, commit `message`; return the new commit's full SHA."""
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        _sh(repo, "add", rel)
    for rel in delete or []:
        _sh(repo, "rm", "-q", rel)
    _sh(repo, "commit", "-q", "-m", message)
    return _sh(repo, "rev-parse", "HEAD")


def _run_tool(repo: Path, base: str, head: str, globs: list[str] | None = None,
              triggers: list[str] | None = None) -> tuple[int, str]:
    """Invoke this module's own CLI via subprocess against `repo` (optional test/trigger globs)."""
    args = [sys.executable, __file__, "--base", base, "--head", head]
    for g in globs or []:
        args.extend(["--test-glob", g])
    for g in triggers or []:
        args.extend(["--trigger-glob", g])
    proc = subprocess.run(args, cwd=str(repo), capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def _selftest() -> int:
    """Build throwaway git repos and assert every mandatory case's exact (rc, evidence).

    Each case below is a real assertion against a real repo and a real
    subprocess invocation of this tool — not a unit test of an internal
    helper — so a future edit that quietly turns a fail-closed branch into a
    pass breaks this function loudly, printing which case broke and why.
    """
    failures: list[str] = []

    def check(label: str, rc: int, out: str, want_rc: int,
              must_have: tuple[str, ...] = (), must_not: tuple[str, ...] = ()) -> None:
        if rc != want_rc:
            failures.append(f"{label}: rc={rc}, want {want_rc} (output: {out!r})")
        for needle in must_have:
            if needle not in out:
                failures.append(f"{label}: output missing {needle!r} (output: {out!r})")
        for needle in must_not:
            if needle in out:
                failures.append(f"{label}: output must not contain {needle!r} (output: {out!r})")

    with tempfile.TemporaryDirectory(prefix="fix_class_gate_selftest_") as tmp:
        tmp_path = Path(tmp)

        # 1) fix without touching a test surface -> FAIL, names the commit.
        repo = tmp_path / "case_fix_no_test"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        head = _commit(repo, "fix: off-by-one in parser", {"src/a.py": "x = 2\n"})
        rc, out = _run_tool(repo, base, head)
        check("fix-no-test", rc, out, FAIL, must_have=("FAIL", head[:7]))

        # 2) fix touching a test file -> pass.
        repo = tmp_path / "case_fix_with_test"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        head = _commit(
            repo, "fix: off-by-one in parser",
            {"src/a.py": "x = 2\n", "tests/test_a.py": "def test_a(): assert True\n"},
        )
        rc, out = _run_tool(repo, base, head)
        check("fix-with-test", rc, out, OK, must_not=("FAIL",))

        # 3) fix with a non-empty No-Test-Reason trailer -> pass, counted exempted.
        repo = tmp_path / "case_fix_trailer_nonempty"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        _sh(repo, "add", ".")
        Path(repo / "src/a.py").write_text("x = 2\n")
        _sh(repo, "add", "src/a.py")
        _sh(repo, "commit", "-q", "-m",
            "fix: cannot repro locally\n\nNo-Test-Reason: requires prod-only race, tracked in ticket")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head)
        check("fix-trailer-nonempty", rc, out, OK, must_have=("1 exempted",), must_not=("FAIL",))

        # 4) fix with an EMPTY No-Test-Reason trailer -> FAIL (bare keyword doesn't exempt).
        repo = tmp_path / "case_fix_trailer_empty"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        Path(repo / "src/a.py").write_text("x = 2\n")
        _sh(repo, "add", "src/a.py")
        _sh(repo, "commit", "-q", "-m", "fix: cannot repro locally\n\nNo-Test-Reason:")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head)
        check("fix-trailer-empty", rc, out, FAIL, must_have=("FAIL",))

        # 5) feat: without a test -> pass (not a fix commit at all).
        repo = tmp_path / "case_feat_no_test"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        head = _commit(repo, "feat: add new widget", {"src/b.py": "y = 1\n"})
        rc, out = _run_tool(repo, base, head)
        check("feat-no-test", rc, out, OK, must_not=("FAIL",))

        # 6) fix(scope)!: recognized as a fix (fails without a test, proving recognition).
        repo = tmp_path / "case_fix_scope_bang"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        head = _commit(repo, "fix(api)!: break compatibility to correct types", {"src/a.py": "x = 2\n"})
        rc, out = _run_tool(repo, base, head)
        check("fix-scope-bang", rc, out, FAIL, must_have=("FAIL", head[:7]))

        # 7) fixture:/fixes subjects are NOT the fix type -> pass even without a test.
        repo = tmp_path / "case_not_fix_type"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        _commit(repo, "fixture: update golden fixtures", {"src/a.py": "x = 2\n"})
        head = _commit(repo, "fixes bug in parser prose", {"src/a.py": "x = 3\n"})
        rc, out = _run_tool(repo, base, head)
        check("not-fix-type", rc, out, OK, must_not=("FAIL",))

        # 8) fix that only DELETES a test file -> FAIL (deletion isn't coverage).
        repo = tmp_path / "case_fix_deletes_test"
        _init_repo(repo)
        base = _commit(
            repo, "chore: init",
            {"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a(): assert True\n"},
        )
        head = _commit(repo, "fix: remove flaky test", {}, delete=["tests/test_a.py"])
        rc, out = _run_tool(repo, base, head)
        check("fix-deletes-test", rc, out, FAIL, must_have=("FAIL",))

        # 9) merge commit skipped even if fix-labeled; only non-merge fix commits count.
        repo = tmp_path / "case_merge_skipped"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        _sh(repo, "checkout", "-q", "-b", "feature")
        _commit(repo, "chore: unrelated feature work", {"src/feature.py": "z = 1\n"})
        _sh(repo, "checkout", "-q", "-")
        _sh(repo, "merge", "--no-ff", "-m", "fix: integrate feature branch", "feature")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head)
        check("merge-skipped", rc, out, OK, must_have=("0 fix commit(s) checked",), must_not=("FAIL",))

        # 10) mixed range: one good fix + one bad fix -> FAIL naming only the bad one.
        repo = tmp_path / "case_mixed_range"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        good = _commit(
            repo, "fix: guard null input",
            {"src/a.py": "x = 2\n", "tests/test_a.py": "def test_a(): assert True\n"},
        )
        bad = _commit(repo, "fix: guard empty input", {"src/a.py": "x = 3\n"})
        rc, out = _run_tool(repo, base, bad)
        check("mixed-range", rc, out, FAIL, must_have=(bad[:7],), must_not=(good[:7],))

        # 11) unresolvable base -> ERROR (fail closed, never a silent pass).
        repo = tmp_path / "case_bad_base"
        _init_repo(repo)
        head = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        rc, out = _run_tool(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", head)
        check("bad-base", rc, out, ERROR)

        # 12) all-zeros base -> ERROR, tells the caller to use the PR base/merge-base.
        repo = tmp_path / "case_zero_base"
        _init_repo(repo)
        head = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        rc, out = _run_tool(repo, ZERO_SHA, head)
        check("zero-base", rc, out, ERROR, must_have=("merge-base",))

        # 13) empty range (base == head) -> OK, explicit "0 commits in range".
        repo = tmp_path / "case_empty_range"
        _init_repo(repo)
        only = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        rc, out = _run_tool(repo, only, only)
        check("empty-range", rc, out, OK, must_have=("0 commits in range",))

        # 14) custom --test-glob overrides (not adds to) the defaults.
        repo = tmp_path / "case_custom_glob"
        _init_repo(repo)
        base = _commit(repo, "chore: init", {"src/a.py": "x = 1\n"})
        head = _commit(
            repo, "fix: off-by-one in parser",
            {"src/a.py": "x = 2\n", "mytests/check.py": "def check(): assert True\n"},
        )
        rc_default, out_default = _run_tool(repo, base, head)
        check("custom-glob-default-fails", rc_default, out_default, FAIL, must_have=("FAIL",))
        rc_custom, out_custom = _run_tool(repo, base, head, globs=["mytests/**"])
        check("custom-glob-overrides", rc_custom, out_custom, OK, must_not=("FAIL",))

        # 15-22) trigger mode: a commit touching a trigger path must also touch a
        # test surface (that is not itself a trigger path) or carry a non-empty
        # No-Mechanism-Reason trailer; a non-trigger commit is out of scope.
        trig = ["skills/*/SKILL.md", "skills/*/references/*.md"]
        mech = ["skills/*/evals/evals.json", "skills/*/scripts/*"]

        def trig_repo(name: str) -> tuple[Path, str]:
            r = tmp_path / name
            _init_repo(r)
            return r, _commit(r, "chore: init", {"skills/a/SKILL.md": "v1\n"})

        repo, base = trig_repo("case_trigger_no_eval")
        head = _commit(repo, "docs: file a lesson", {"skills/a/references/r.md": "lesson\n"})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-no-eval", rc, out, FAIL,
              must_have=("FAIL", head[:7], "No-Mechanism-Reason", "1 trigger commit(s)"))

        repo, base = trig_repo("case_trigger_with_eval")
        head = _commit(repo, "feat: lesson plus eval",
                       {"skills/a/SKILL.md": "v2\n", "skills/a/evals/evals.json": "{}\n"})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-with-eval", rc, out, OK, must_have=("1 trigger commit(s)",), must_not=("FAIL",))

        repo, base = trig_repo("case_trigger_trailer")
        Path(repo / "skills/a/SKILL.md").write_text("v2\n")
        _sh(repo, "add", ".")
        _sh(repo, "commit", "-q", "-m",
            "docs: reword\n\nNo-Mechanism-Reason: wording only, no new rule")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-trailer", rc, out, OK, must_have=("1 exempted",), must_not=("FAIL",))

        repo, base = trig_repo("case_trigger_trailer_empty")
        Path(repo / "skills/a/SKILL.md").write_text("v2\n")
        _sh(repo, "add", ".")
        _sh(repo, "commit", "-q", "-m", "docs: reword\n\nNo-Mechanism-Reason:")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-trailer-empty", rc, out, FAIL, must_have=("FAIL",))

        # A fix: commit off the trigger paths is out of scope in trigger mode
        # (subject ignored): passes with no test and no trailer.
        repo, base = trig_repo("case_non_trigger")
        head = _commit(repo, "fix: runtime bug", {"src/a.py": "x = 2\n"})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("non-trigger", rc, out, OK, must_have=("0 trigger commit(s)",), must_not=("FAIL",))

        # A path on BOTH lists never satisfies itself: the trigger edit is not
        # its own mechanism even when a test glob also matches it.
        repo, base = trig_repo("case_trigger_self_match")
        head = _commit(repo, "docs: lesson", {"skills/a/SKILL.md": "v2\n"})
        rc, out = _run_tool(repo, base, head, globs=["skills/**"], triggers=trig)
        check("trigger-self-match", rc, out, FAIL, must_have=("FAIL",))

        # Deleting a trigger path alone files no lesson -> out of scope.
        repo, base = trig_repo("case_trigger_delete_only")
        _commit(repo, "docs: add ref", {"skills/a/references/r.md": "x\n",
                                        "skills/a/evals/evals.json": "{}\n"})
        head = _commit(repo, "docs: drop ref", {}, delete=["skills/a/references/r.md"])
        rc, out = _run_tool(repo, head + "~1", head, globs=mech, triggers=trig)
        check("trigger-delete-only", rc, out, OK, must_have=("0 trigger commit(s)",), must_not=("FAIL",))

        # An empty trigger glob would match nothing and pass silently -> ERROR.
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=[""])
        check("trigger-empty-glob", rc, out, ERROR, must_have=("must not be empty",))

        # 23-25) trigger mode walks merge commits and judges each by its OWN
        # changes (vs the clean automatic merge of its parents).
        def branch_off(r: Path) -> None:
            _sh(r, "checkout", "-q", "-b", "feature")

        # An evil merge: the merge commit itself adds prose, no mechanism -> FAIL.
        repo, base = trig_repo("case_trigger_evil_merge")
        branch_off(repo)
        _commit(repo, "chore: feature work", {"src/f.py": "f = 1\n"})
        _sh(repo, "checkout", "-q", "-")
        _commit(repo, "chore: mainline work", {"src/m.py": "m = 1\n"})
        _sh(repo, "merge", "--no-ff", "--no-commit", "feature")
        Path(repo / "skills/a/references/r.md").parent.mkdir(parents=True, exist_ok=True)
        Path(repo / "skills/a/references/r.md").write_text("lesson smuggled in a merge\n")
        _sh(repo, "add", "skills/a/references/r.md")
        _sh(repo, "commit", "-q", "-m", "merge feature")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-evil-merge", rc, out, FAIL,
              must_have=("FAIL", head[:7], "1 trigger commit(s)"))

        # A clean merge adds nothing of its own: only the feature commit (which
        # carries its eval) is judged, and the merge is out of scope -> OK.
        repo, base = trig_repo("case_trigger_clean_merge")
        branch_off(repo)
        _commit(repo, "feat: lesson plus eval",
                {"skills/a/SKILL.md": "v2\n", "skills/a/evals/evals.json": "{}\n"})
        _sh(repo, "checkout", "-q", "-")
        _commit(repo, "chore: mainline work", {"src/m.py": "m = 1\n"})
        _sh(repo, "merge", "--no-ff", "-q", "-m", "merge feature", "feature")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-clean-merge", rc, out, OK, must_have=("1 trigger commit(s)",), must_not=("FAIL",))

        # A conflicted merge has no clean automatic result: it falls back to
        # its diff against the first parent (fail closed, never skipped).
        repo, base = trig_repo("case_trigger_conflict_merge")
        branch_off(repo)
        _commit(repo, "docs: feature wording\n\nNo-Mechanism-Reason: fixture",
                {"skills/a/SKILL.md": "feature\n"})
        _sh(repo, "checkout", "-q", "-")
        _commit(repo, "docs: main wording\n\nNo-Mechanism-Reason: fixture",
                {"skills/a/SKILL.md": "main\n"})
        subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "feature"],
                       capture_output=True, text=True)
        Path(repo / "skills/a/SKILL.md").write_text("resolved with a new rule\n")
        _sh(repo, "add", "skills/a/SKILL.md")
        _sh(repo, "commit", "-q", "-m", "merge feature")
        head = _sh(repo, "rev-parse", "HEAD")
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-conflict-merge", rc, out, FAIL, must_have=("FAIL", head[:7], "2 exempted"))

        # 26-29) a SKILL.md frontmatter version-stamp-only edit is not a
        # trigger (releases bump several stamps); any other changed line is.
        fm = '---\nname: a\nmetadata:\n  version: "{v}"\n---\n# A\n\n{body}\n'

        def stamp_repo(name: str) -> tuple[Path, str]:
            r = tmp_path / name
            _init_repo(r)
            return r, _commit(r, "chore: init",
                              {"skills/a/SKILL.md": fm.format(v="1.0.0", body="rule"),
                               "skills/b/SKILL.md": fm.format(v="1.0.0", body="rule")})

        repo, base = stamp_repo("case_trigger_stamp_only")
        head = _commit(repo, "chore(release): 1.1.0",
                       {"skills/a/SKILL.md": fm.format(v="1.1.0", body="rule"),
                        "skills/b/SKILL.md": fm.format(v="1.1.0", body="rule")})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-stamp-only", rc, out, OK, must_have=("0 trigger commit(s)",), must_not=("FAIL",))

        repo, base = stamp_repo("case_trigger_stamp_plus_prose")
        head = _commit(repo, "chore(release): 1.1.0",
                       {"skills/a/SKILL.md": fm.format(v="1.1.0", body="rule"),
                        "skills/b/SKILL.md": fm.format(v="1.1.0", body="new rule")})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-stamp-plus-prose", rc, out, FAIL, must_have=("FAIL", head[:7]))

        # A `version:` line added to, or removed from, the body is prose.
        body_stamp = 'rule\nversion: "2.0.0"'
        repo, base = stamp_repo("case_trigger_stamp_added_in_body")
        head = _commit(repo, "docs: body stamp",
                       {"skills/a/SKILL.md": fm.format(v="1.0.0", body=body_stamp)})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-stamp-added-in-body", rc, out, FAIL, must_have=("FAIL", head[:7]))

        repo, _ = stamp_repo("case_trigger_stamp_removed_from_body")
        base = _commit(repo, "docs: body stamp\n\nNo-Mechanism-Reason: fixture",
                       {"skills/a/SKILL.md": fm.format(v="1.0.0", body=body_stamp)})
        head = _commit(repo, "docs: drop body stamp",
                       {"skills/a/SKILL.md": fm.format(v="1.0.0", body="rule")})
        rc, out = _run_tool(repo, base, head, globs=mech, triggers=trig)
        check("trigger-stamp-removed-from-body", rc, out, FAIL, must_have=("FAIL", head[:7]))

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK: 29/29 cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: `--selftest`, or `--base <ref> --head <ref> [--test-glob ...] [--trigger-glob ...]`."""
    parser = argparse.ArgumentParser(
        description=(
            "Enforce a pinned test per fix: every Conventional-Commits `fix:` commit in "
            "base..head must touch a test-surface path or declare a No-Test-Reason trailer."
        )
    )
    parser.add_argument("--base", help="range base ref (exclusive)")
    parser.add_argument("--head", help="range head ref (inclusive)")
    parser.add_argument(
        "--test-glob", action="append", dest="test_globs", metavar="GLOB",
        help="glob a test-surface path must match; repeatable; REPLACES the defaults when given",
    )
    parser.add_argument(
        "--trigger-glob", action="append", dest="trigger_globs", metavar="GLOB",
        help="trigger mode: a commit touching a matching path must also touch a test-surface "
             "path or carry a non-empty No-Mechanism-Reason trailer; repeatable",
    )
    parser.add_argument("--selftest", action="store_true", help="run the built-in selftest and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.base or not args.head:
        parser.error("--base and --head are both required")
        return ERROR  # pragma: no cover — parser.error() already exits(2)

    if any(not g.strip() for g in args.trigger_globs or ()):
        # An empty trigger glob matches no path: trigger mode would silently pass.
        parser.error("--trigger-glob must not be empty")
    globs = tuple(args.test_globs) if args.test_globs else DEFAULT_TEST_GLOBS
    code, lines = run_gate(".", args.base, args.head, globs, tuple(args.trigger_globs or ()))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
