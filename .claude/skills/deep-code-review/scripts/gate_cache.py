#!/usr/bin/env python3
"""gate_cache.py — one PASS cache, shared by every gate stage, keyed by the git tree.

WHY THIS EXISTS
---------------
The same suites ran at pre-commit, again at pre-push, again in a `precheck` script and a third time in the
merge-train gate: 2-15 minutes each, on a tree that had not changed since the first run. This script is the
one place a stage asks "has this exact tree already passed this exact suite?" before paying for it again.
Whichever stage reaches a tree first runs the suite; every later stage prints one line and skips.

USAGE
-----
  gate_cache.py run [--stage NAME] [--label TEXT] [--say TEXT] [--tree REV] [--base SHA --head SHA]
                    [--key TEXT] [--ignore GLOB] [--no-pipefail] (-c 'SHELL STRING' | -- ARGV...)

Runs the suite and exits with its status, unless a PASS for the same key is cached: then it prints
`cached PASS <tree> (<label>)`, runs nothing and exits 0. A PASS is recorded only after the suite exits 0.
A `-c` string runs under `bash` with `set -o pipefail` (a piped failure must never be cached as a PASS).
Wire it into any stage with the SAME command text in each stage (the text is part of the key):

  pre-commit   python3 .claude/skills/deep-code-review/scripts/gate_cache.py run --stage pre-commit -c 'make lint test-unit'
  pre-push     the shipped pre-push-verify.sh wraps DCR_PREPUSH_CMD (set DCR_PREPUSH_TREE_PURE=1, see below)
  train gate   train_land.sh (BASE_AUDIT_CMD) and merge_train.py (--verify-cmd) consult the same cache
  precheck     the same one-liner as pre-commit

THE KEY (all three parts, nothing else)
---------------------------------------
  tree         `git write-tree` of the index, proven to equal what is on disk (see below). `--tree REV` also
               demands that REV's tree equals it, so "the pushed commit's tree" can never silently be a
               different checkout.
  gate set     hash of every file in the active hooks dir (`core.hooksPath` honoured), of this script, of each
               path in $PERUN_GATE_FILES (os.pathsep-separated, for gate scripts that live outside the tree),
               and the literal $PERUN_GATE_SET_VERSION. Editing a hook or this script is a new gate set, so it
               misses every older entry. Scripts that ARE in the tree are covered by the tree SHA itself.
  config       hash of the command text, pipefail mode, `--base/--head` when given, `--key` and
               $PERUN_GATE_CACHE_KEY (an operator fingerprint, e.g. a toolchain version this script cannot see).
               A pipefail PASS also satisfies a `--no-pipefail` run of the same text (the stricter verdict), never
               the reverse.

TREE-PURE VS RANGE-AWARE. A cached PASS may be reused by any later stage only if the suite is a function of the
tree. By default a suite is treated as tree-pure. A suite that reads commit messages or the pushed range
(`BASE_SHA`/`HEAD_SHA`, e.g. `dcr-gates.sh`) is NOT: pass `--base`/`--head` so the range joins the key, and it
then shares only with a run over the same range (never with pre-commit, which has no range).

WHAT IS NEVER CACHED OR SKIPPED
-------------------------------
- A FAIL, a signal, or a command that could not start: only exit 0 is recorded.
- A dirty or ambiguous tree: unstaged edits, untracked files (bar `--ignore GLOB` paths the stage itself
  writes), an unmerged index, a sparse checkout (`core.sparseCheckout`), skip-worktree or assume-unchanged
  entries (`git ls-files -v` shows `S` or a lowercase tag), no git, or a failed `write-tree` all mean "cannot
  prove which tree passed", so the suite simply runs and the cache is neither read nor written.
- A run that changed tracked files or the index while it ran: the verdict belongs to a different tree.
- Anything older than 7 days: ignored on lookup, deleted on the next write.
Cache a suite for its verdict only: a skipped run also skips its side effects (build output, generated files,
fixtures), so never wrap a step that a later step needs for its artifacts.

STORE: `<git-common-dir>/perun-gate-cache/<sha256 of the key>`, one small JSON file each, written atomically.
Under `.git`, so it is local to the clone, shared by every linked worktree, and never a tracked file.
This cache is a local self-report. CI on the reviewed SHA stays the trusted gate.

OPT-OUT: `PERUN_GATE_CACHE=0` (or off/false/no) never reads or writes the cache; `PERUN_GATE_CACHE=refresh`
ignores existing entries but still records a fresh PASS. `gate_map.py` (sibling) lists which suites each
stage runs and flags the ones that run more than once per tree.

Exit status: the suite's own; 127 when it cannot start; 2 on a usage error.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time

MAX_AGE = 7 * 86400
DIR_NAME = "perun-gate-cache"
_SELF = os.path.abspath(__file__)  # absolute now, so a later chdir or `cwd=` cannot make the self-hash read "missing"


def _git(args: list, cwd: str | None = None) -> str | None:
    """Stripped stdout of `git <args>`; None on a non-zero exit or when git cannot run. Never raises.
    `--no-optional-locks`: a read here must never contend for the index lock a parent `git commit` holds."""
    try:
        p = subprocess.run(["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def mode() -> str:
    """`PERUN_GATE_CACHE`: `off` (0/off/false/no), `refresh` (skip lookups, still record) or `on`."""
    v = os.environ.get("PERUN_GATE_CACHE", "").strip().lower()
    return "off" if v in ("0", "off", "false", "no") else "refresh" if v == "refresh" else "on"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return _sha(fh.read())
    except OSError:
        return "missing"


def checked_out_tree(cwd: str | None = None, rev: str | None = None, ignore: tuple = ()) -> str | None:
    """The tree SHA that is both staged and on disk, else None ("cannot prove which tree is being tested").

    Requires: `git write-tree` succeeds (no unmerged entries), tracked files equal the index, no untracked
    non-ignored files (except paths matching an `ignore` fnmatch glob: files the stage itself writes, such as
    its own logs), no sparse checkout and no skip-worktree / assume-unchanged entries, and, when `rev` is given,
    `rev`'s tree equals the staged tree.
    """
    tree = _git(["write-tree"], cwd)
    if not tree:
        return None
    if rev is not None and _git(["rev-parse", "--verify", "-q", rev + "^{tree}"], cwd) != tree:
        return None
    if _git(["diff", "--quiet"], cwd) is None:
        return None
    # `diff --quiet` and the status checks cannot see files git was told to skip: a sparse checkout, skip-worktree
    # (`S`) or assume-unchanged (`h`, any lowercase tag) entries may differ on disk or be absent, so the staged tree
    # is not what was tested. Refuse to read or write the cache for such a checkout.
    if (_git(["config", "--get", "core.sparseCheckout"], cwd) or "").lower() in ("true", "1", "yes", "on"):
        return None
    tags = _git(["ls-files", "-v", "-z"], cwd)
    if tags is None or any(t[:1] == "S" or t[:1].islower() for t in tags.split("\0") if t):
        return None
    others = _git(["ls-files", "-z", "--others", "--exclude-standard", "--full-name", "--", ":/"], cwd)  # whole repo, not just cwd
    if others is None:
        return None
    for p in filter(None, others.split("\0")):
        if not any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch(os.path.basename(p), g) for g in ignore):
            return None
    return tree


def gate_set_version(cwd: str | None = None) -> str:
    """Hash of how the gates run, as distinct from the tree they run on (see the module doc, "gate set")."""
    base = cwd or os.getcwd()
    hooks: dict = {}
    hd = _git(["rev-parse", "--git-path", "hooks"], cwd)
    if hd:
        hd = os.path.join(base, hd)
        try:
            names = sorted(os.listdir(hd))
        except OSError:
            names = []
        hooks = {n: _file_sha(os.path.join(hd, n)) for n in names
                 if not n.endswith(".sample") and os.path.isfile(os.path.join(hd, n))}
    files = [f for f in os.environ.get("PERUN_GATE_FILES", "").split(os.pathsep) if f]
    return _sha(json.dumps({"self": _file_sha(_SELF), "hooks": hooks, "version": os.environ.get("PERUN_GATE_SET_VERSION", ""),
                            "files": {f: _file_sha(os.path.join(base, f)) for f in files}}, sort_keys=True).encode())


def config_hash(text: str, pipefail: bool = False, base: str | None = None, head: str | None = None, keys: tuple = ()) -> str:
    """Hash of the suite's own identity: command text, pipefail mode, optional pushed range, operator key text."""
    return _sha(json.dumps({"cmd": text, "pipefail": pipefail, "range": [base, head] if base or head else None,
                            "key": [k for k in (*keys, os.environ.get("PERUN_GATE_CACHE_KEY", "")) if k]}, sort_keys=True).encode())


def context(text: str, cwd: str | None = None, rev: str | None = None, pipefail: bool = False,
            base: str | None = None, head: str | None = None, keys: tuple = (), ignore: tuple = ()) -> dict | None:
    """The cache key parts plus the store path for `text` in `cwd`, or None when caching is off or unprovable."""
    if mode() == "off":
        return None
    tree = checked_out_tree(cwd, rev, ignore)
    common = _git(["rev-parse", "--git-common-dir"], cwd)
    if not tree or not common:
        return None
    gate_set, config = gate_set_version(cwd), config_hash(text, pipefail, base, head, keys)
    d = os.path.join(os.path.abspath(os.path.join(cwd or os.getcwd(), common)), DIR_NAME)

    def at(cfg):
        return os.path.join(d, _sha(f"1\0{tree}\0{gate_set}\0{cfg}".encode()))
    strict = config_hash(text, True, base, head, keys)
    # A pipefail PASS is the stricter verdict, so it also satisfies a run that does not use pipefail (never the reverse).
    alt = [] if pipefail else [(at(strict), strict)]
    return {"tree": tree, "gate_set": gate_set, "config": config, "dir": d, "path": at(config), "alt": alt}


def lookup(ctx: dict, now: float | None = None) -> bool:
    """True when a PASS for exactly this key is cached and at most 7 days old. Always False in `refresh` mode."""
    if mode() != "on":
        return False
    now = time.time() if now is None else now
    for path, config in [(ctx["path"], ctx["config"]), *ctx.get("alt", [])]:
        try:
            with open(path, encoding="utf-8") as fh:
                e = json.load(fh)
            ts = float(e["ts"])
            same = (e["tree"], e["gate_set"], e["config"]) == (ctx["tree"], ctx["gate_set"], config)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if same and 0 <= now - ts <= MAX_AGE:
            return True
    return False


def store(ctx: dict, label: str = "", stage: str = "", now: float | None = None) -> None:
    """Record a PASS (atomic write) and delete entries older than 7 days. Best effort: an I/O error is swallowed."""
    now = time.time() if now is None else now
    try:
        os.makedirs(ctx["dir"], exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=ctx["dir"], prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"tree": ctx["tree"], "gate_set": ctx["gate_set"], "config": ctx["config"], "label": label,
                       "stage": stage, "ts": now}, fh)
        os.replace(tmp, ctx["path"])
        for n in os.listdir(ctx["dir"]):
            p = os.path.join(ctx["dir"], n)
            if os.path.isfile(p) and now - os.path.getmtime(p) > MAX_AGE:
                os.remove(p)
    except OSError:
        pass


def run(argv: list, text: str, label: str = "", stage: str = "", rev: str | None = None, pipefail: bool = False,
        base: str | None = None, head: str | None = None, keys: tuple = (), cwd: str | None = None, say: str = "",
        ignore: tuple = ()) -> int:
    """Run `argv` (identified by `text`) unless its PASS is cached; record a PASS only when it exits 0.
    `say` is printed just before a real run (never on a cached PASS), so a hook keeps its own "running: ..." line."""
    label = label or " ".join(text.split())[:60]
    try:
        ctx = context(text, cwd, rev, pipefail, base, head, keys, ignore)
        hit = bool(ctx) and lookup(ctx)
    except Exception as e:  # the cache must never be the reason a suite does not run
        print(f"gate_cache: cache unavailable ({type(e).__name__}); running uncached", file=sys.stderr)
        ctx, hit = None, False
    if hit:
        print(f"cached PASS {ctx['tree']} ({label})")
        return 0
    if say:
        print(say, flush=True)
    try:
        rc = subprocess.call(argv, cwd=cwd)
    except OSError as e:
        print(f"gate_cache: cannot start {argv[0]}: {e}", file=sys.stderr)
        return 127
    if rc == 0 and ctx:
        if _git(["write-tree"], cwd) == ctx["tree"] and _git(["diff", "--quiet"], cwd) is not None:
            store(ctx, label, stage)
        else:
            print("gate_cache: tracked files changed while the suite ran; PASS not cached", file=sys.stderr)
    return rc


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gate_cache.py", description="Run a gate suite unless this tree already passed it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite through the cache")
    r.add_argument("--stage", default="", help="stage name, recorded in the entry (pre-commit, pre-push, train, ...)")
    r.add_argument("--label", help="short name shown in the one-line cached-PASS message")
    r.add_argument("--tree", dest="rev", help="REV whose tree must equal the checked-out tree (e.g. the pushed commit)")
    r.add_argument("--base", help="range-aware suite: pushed range base (joins the key)")
    r.add_argument("--head", help="range-aware suite: pushed range head (joins the key)")
    r.add_argument("--key", action="append", default=[], help="extra text folded into the config hash (repeatable)")
    r.add_argument("--no-pipefail", action="store_true",
                   help="run -c STRING without `set -o pipefail` (default: with it, so a piped failure is never cached as a PASS)")
    r.add_argument("--say", default="", help="line printed just before a real (uncached) run")
    r.add_argument("--ignore", action="append", default=[], metavar="GLOB",
                   help="untracked paths matching GLOB do not make the tree dirty (files this stage writes, e.g. its logs)")
    r.add_argument("-c", dest="shell", help="the suite as one bash string")
    r.add_argument("argv", nargs=argparse.REMAINDER, help="or the suite as argv after `--`")
    a = ap.parse_args(argv)
    rest = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
    if bool(a.shell) == bool(rest):
        ap.error("give the suite as exactly one of: -c STRING, or -- ARGV...")
    pipefail = bool(a.shell) and not a.no_pipefail  # an argv suite has no pipeline to mask a failure in
    if a.shell:
        cmd, text = ["bash", "-c", ("set -o pipefail; " if pipefail else "") + a.shell], a.shell
    else:
        cmd, text = rest, shlex.join(rest)
    return run(cmd, text, a.label or "", a.stage, a.rev, pipefail, a.base, a.head, tuple(a.key), say=a.say,
               ignore=tuple(a.ignore))


if __name__ == "__main__":
    sys.exit(main())
