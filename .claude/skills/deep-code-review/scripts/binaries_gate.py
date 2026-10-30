#!/usr/bin/env python3
# rail: owner=deep-code-review, why=no git-tracked binary at a banned image/media/archive/build-output extension, review=2027-01-30
"""binaries_gate.py — no git-tracked file at a banned image/media/archive/
build-output extension.

WHY THIS EXISTS
----------------
Stops the committed-screenshot / generated-artifact bloat class: a PNG demo,
a zipped export, a compiled .pyc, dropped straight into git instead of an
artifact store or PR attachment. Extension-scoped, not size-scoped, so a
legitimately large TEXT fixture never trips it.

THIS IS THE ONE IMPLEMENTATION. This repo's own `scripts/ci-gates.sh binaries`
subcommand delegates to this file rather than keeping a second copy of the
scan logic — so this repo's CI and every project that installs the
`deep-code-review` skill and opts into `install.sh --with-gates` run the
identical check. Edit the check here; `ci-gates.sh` is a thin caller.

WHAT COUNTS
------------
Only git-TRACKED files (`git -C <root> ls-files -z`), matched case-insensitively
against a fixed extension list: png jpg jpeg gif webp bmp pdf zip tar gz tgz
mp4 mov woff woff2 exe dll so dylib class jar pyc pyo. A path is exempt iff it
appears verbatim (relative to `<root>`) in the allowlist file — one exact
path per line, blank lines and `#`-comments ignored. Default allowlist path is
`<root>/scripts/binaries-allowlist.tsv`; pass `--allowlist` to override (a
target repo can point it anywhere, e.g. a per-repo policy file it already
tracks).

STALE ENTRIES
-------------
An allowlist row is a reasoned exception to a *current* violation. Once the
file it names is fixed (deleted, renamed, or no longer at a banned extension)
the row is stale: it now exempts nothing, and the next PR that tightens this
gate goes red for a violation count that no longer matches reality (see
`references/gate-epistemology.md`, "a stale-allowlist-entry case"). This gate
FAILS on a stale row rather than silently accepting it, so the PR that fixes
the violation is forced to remove its own allowlist entry in the same change.

EXIT CODES (fail-closed)
-------------------------
  0  no un-allowlisted tracked file matched a banned extension, and every
     allowlist row still names a real, currently-tracked, banned-extension file.
  1  at least one un-allowlisted tracked file matched, and/or at least one
     allowlist row is stale (each named on stderr).
  2  the root is not a readable git repository (`git ls-files` failed) — the
     scan could not run at all, never a silent pass.

Never echoes file CONTENT, only tracked path names (same discipline as the
privacy gate) — a binary's bytes are never dumped into a log.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

OK = 0
FAIL = 1
ERROR = 2

# Same fixed, case-insensitive extension set as ci-gates.sh's `binaries`
# subcommand (images, media, fonts, archives, common compiled build output).
BANNED_EXTS = (
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "zip", "tar", "gz",
    "tgz", "mp4", "mov", "woff", "woff2", "exe", "dll", "so", "dylib",
    "class", "jar", "pyc", "pyo",
)


def _is_banned(path: str) -> bool:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext in BANNED_EXTS


def _load_allowlist(path: str) -> set[str]:
    allowed: set[str] = set()
    if not path or not os.path.isfile(path):
        return allowed
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#"):
                continue
            allowed.add(trimmed)
    return allowed


def run_gate(root: str, allowlist_path: str | None) -> tuple[int, list[str]]:
    """Scan `root`'s git-tracked files; return (exit_code, output_lines).

    Output lines are printed by the caller in order — BINARY TRACKED lines to
    stderr via the returned tuple's caller, everything else to stdout; see
    `main()` for the split. Kept as plain strings here (no I/O in this
    function) so `--selftest` can assert on them directly.
    """
    if not os.path.isdir(root):
        return ERROR, [f"binaries: root not found: {root} (fail closed)"]

    try:
        # `-z`: NUL-separated, never quoted. Without it git C-quotes any path
        # with non-ASCII bytes ("\303\251cran.png" plus a closing quote), so
        # the extension reads as `png"` and a banned file slips through.
        proc = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"],
            capture_output=True, check=False,
        )
    except OSError as exc:
        return ERROR, [f"binaries: git ls-files failed for {root} (fail closed): {exc}"]
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        return ERROR, [
            f"binaries: git ls-files failed for {root} "
            f"(fail closed; is it a git repo?): {detail}"
        ]

    # Invalid UTF-8 decodes with U+FFFD: the extension is still read, and such
    # a name can never match an allowlist row, so it fails closed, not open.
    tracked = sorted(
        name for name in proc.stdout.decode("utf-8", "replace").split("\0") if name
    )

    resolved_allowlist = allowlist_path
    if resolved_allowlist is None:
        default_path = os.path.join(root, "scripts", "binaries-allowlist.tsv")
        resolved_allowlist = default_path if os.path.isfile(default_path) else None
    allow_paths = _load_allowlist(resolved_allowlist) if resolved_allowlist else set()

    tracked_set = set(tracked)
    flagged: list[str] = []
    for f in tracked:
        if not _is_banned(f):
            continue
        if f in allow_paths:
            continue
        flagged.append(f)

    # A stale row: still listed, but the violation it named is gone (file
    # deleted, renamed, or no longer at a banned extension). Fixing the
    # violation without removing the row must not ship silently.
    stale = sorted(p for p in allow_paths if not (p in tracked_set and _is_banned(p)))

    lines: list[str] = []
    for f in flagged:
        lines.append(
            f"BINARY TRACKED: {f} (extension-banned; route to an artifact store, do not commit)"
        )
    for p in stale:
        lines.append(
            f"STALE ALLOWLIST ENTRY: {p} (no longer a tracked banned-extension file; "
            "remove this row from binaries-allowlist.tsv in the same change)"
        )
    if flagged or stale:
        lines.append(
            f"binaries: {len(flagged)} git-tracked file(s) at a banned extension, "
            f"{len(stale)} stale allowlist entr{'y' if len(stale) == 1 else 'ies'} (see paths above)"
        )
        return FAIL, lines

    lines.append(
        f"binaries: ok ({len(tracked)} tracked file(s) scanned, {len(allow_paths)} allowlisted)"
    )
    return OK, lines


# ---------------------------------------------------------------------------
# Selftest — planted RED/GREEN cases, no network, no fixture repo checked in.
# ---------------------------------------------------------------------------

def _sh(cwd: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _init_repo(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "a@example.com"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Test"], check=True)


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, rc: int, lines: list[str], want_rc: int, must_have: tuple[str, ...] = ()) -> None:
        joined = "\n".join(lines)
        ok = rc == want_rc and all(needle in joined for needle in must_have)
        if not ok:
            failures.append(f"{name}: rc={rc} (want {want_rc}); output={joined!r}")

    with tempfile.TemporaryDirectory() as tmp:
        # 1) clean tracked tree -> OK.
        clean = os.path.join(tmp, "clean")
        _init_repo(clean)
        with open(os.path.join(clean, "notes.txt"), "w") as fh:
            fh.write("hello world\n")
        _sh(clean, "add", "notes.txt")
        rc, lines = run_gate(clean, None)
        check("clean-tree-ok", rc, lines, OK)

        # 2) planted git-tracked demo.png, no allowlist -> FAIL, names it,
        #    points at an artifact store.
        fire = os.path.join(tmp, "fire")
        _init_repo(fire)
        with open(os.path.join(fire, "notes.txt"), "w") as fh:
            fh.write("hello world\n")
        with open(os.path.join(fire, "demo.png"), "w") as fh:
            fh.write("not a real png -- a planted demo binary artifact\n")
        _sh(fire, "add", "notes.txt", "demo.png")
        rc, lines = run_gate(fire, None)
        check(
            "planted-binary-fires", rc, lines, FAIL,
            must_have=("BINARY TRACKED: demo.png", "route to an artifact store"),
        )

        # 3) same tracked demo.png, but named in scripts/binaries-allowlist.tsv
        #    (default lookup path) -> OK, exempted.
        allow = os.path.join(tmp, "allow")
        _init_repo(allow)
        os.makedirs(os.path.join(allow, "scripts"), exist_ok=True)
        with open(os.path.join(allow, "notes.txt"), "w") as fh:
            fh.write("hello world\n")
        with open(os.path.join(allow, "demo.png"), "w") as fh:
            fh.write("not a real png -- a planted demo binary artifact\n")
        with open(os.path.join(allow, "scripts", "binaries-allowlist.tsv"), "w") as fh:
            fh.write("# fixture allowlist\ndemo.png\n")
        _sh(allow, "add", "notes.txt", "demo.png", "scripts/binaries-allowlist.tsv")
        rc, lines = run_gate(allow, None)
        check("allowlisted-path-exempt", rc, lines, OK)

        # 4) not a git repo -> ERROR (fail closed, never a silent pass).
        notrepo = os.path.join(tmp, "notrepo")
        os.makedirs(notrepo, exist_ok=True)
        rc, lines = run_gate(notrepo, None)
        check("not-a-repo-errors", rc, lines, ERROR)

        # 5) --allowlist override points elsewhere (not the default path) ->
        #    proves the flag actually changes which file is read.
        override = os.path.join(tmp, "override")
        _init_repo(override)
        with open(os.path.join(override, "demo.png"), "w") as fh:
            fh.write("not a real png\n")
        _sh(override, "add", "demo.png")
        custom_allow = os.path.join(tmp, "custom-allowlist.tsv")
        with open(custom_allow, "w") as fh:
            fh.write("demo.png\n")
        rc, lines = run_gate(override, custom_allow)
        check("custom-allowlist-path-used", rc, lines, OK)

        # 6) a tracked banned file with a NON-ASCII name -> FAIL. Without `-z`,
        #    git quotes such a path ("\303\251cran.png" with a trailing quote),
        #    so its extension reads as `png"` and the file slipped through.
        nonascii = os.path.join(tmp, "nonascii")
        _init_repo(nonascii)
        name = "\u00e9cran.png"
        with open(os.path.join(nonascii, name), "w") as fh:
            fh.write("not a real png\n")
        _sh(nonascii, "add", name)
        rc, lines = run_gate(nonascii, None)
        check("non-ascii-name-fires", rc, lines, FAIL, must_have=(f"BINARY TRACKED: {name}",))

        # 7) an allowlist row for demo.png, but the fix deleted demo.png (or
        #    renamed it away from a banned extension) without removing the
        #    row -> FAIL, names it stale, points at the allowlist file. This
        #    is the exact "fixed the violation, left the row" bug this gate
        #    exists to catch (issue: allowlist rows must be removed in the
        #    same change that fixes what they exempted).
        stale = os.path.join(tmp, "stale")
        _init_repo(stale)
        os.makedirs(os.path.join(stale, "scripts"), exist_ok=True)
        with open(os.path.join(stale, "notes.txt"), "w") as fh:
            fh.write("hello world\n")
        with open(os.path.join(stale, "scripts", "binaries-allowlist.tsv"), "w") as fh:
            fh.write("# fixture allowlist\ndemo.png\n")
        _sh(stale, "add", "notes.txt", "scripts/binaries-allowlist.tsv")
        rc, lines = run_gate(stale, None)
        check(
            "stale-allowlist-entry-fires", rc, lines, FAIL,
            must_have=("STALE ALLOWLIST ENTRY: demo.png", "remove this row"),
        )

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK: 7/7 cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="No git-tracked file at a banned image/media/archive/build-output extension."
    )
    parser.add_argument("root", nargs="?", help="repository root to scan")
    parser.add_argument(
        "--allowlist", default=None, metavar="FILE",
        help="path to an exact-path-per-line exemption file "
             "(default: <root>/scripts/binaries-allowlist.tsv if present)",
    )
    parser.add_argument("--selftest", action="store_true", help="run the built-in selftest and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.root:
        parser.error("root directory is required")
        return ERROR  # pragma: no cover — parser.error() already exits(2)

    code, lines = run_gate(args.root, args.allowlist)
    out = sys.stdout if code == OK else sys.stderr
    for line in lines:
        print(line, file=out)
    return code


if __name__ == "__main__":
    sys.exit(main())
