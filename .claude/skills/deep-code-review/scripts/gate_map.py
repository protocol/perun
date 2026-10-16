#!/usr/bin/env python3
"""gate_map.py — read-only report: which suites each gate stage runs, and which run more than once per tree.

WHY THIS EXISTS: the same suites were wired into pre-commit, pre-push, a `precheck` script and the train gate
and each ran them again on an unchanged tree. Before `gate_cache.py` (the shared tree-keyed PASS cache) can
help, someone has to see the duplication. This script only reads: no file is written, no suite is run.

USAGE
-----
  gate_map.py [ROOT] [--stage NAME=PATH ...]

STAGES READ (ROOT defaults to the current directory):
  pre-commit  <hooks dir>/pre-commit, .githooks/pre-commit, .husky/pre-commit
  pre-push    <hooks dir>/pre-push, .githooks/pre-push, .husky/pre-push, and $DCR_PREPUSH_CMD
  precheck    scripts/precheck[.sh], script/precheck[.sh], bin/precheck[.sh]
  train       $VERIFY_CMD, $BASE_AUDIT_CMD, $BROWSER_CMD, $RATCHET_CMD
  any other   --stage NAME=PATH (repeatable; also adds to a stage above)
The hooks dir honours `core.hooksPath`. Shell scripts a stage file names by path (one level) are read as part of
that stage. A "suite" is a command line whose program is a known test/lint/build runner, or a script whose name
says test/lint/check/gate/verify/eval/audit/ratchet/build. Anything else is not guessed at: it is not listed.

EACH SUITE IS TAGGED `cached` or `uncached`: cached means it runs through gate_cache.py (an explicit
`gate_cache.py run`, the shipped pre-push-verify.sh for $DCR_PREPUSH_CMD, train_land.sh for $BASE_AUDIT_CMD,
merge_train.py for its --verify-cmd). A cached suite is `range-aware` when its key includes the pushed range
(`--base/--head`, or $DCR_PREPUSH_CMD without DCR_PREPUSH_TREE_PURE=1); a range-aware PASS is never shared
with a stage that has no range.

THEN, FOR EVERY COMMAND TEXT THAT APPEARS IN TWO OR MORE STAGES:
  SHARED     cached everywhere with the same scope: it runs once per tree, whichever stage reaches it first.
  DUPLICATE  it runs once per stage; the line says what to change (wrap the uncached stages, or set
             DCR_PREPUSH_TREE_PURE=1 when the scopes differ).
Exit status is always 0: this is a report, not a gate.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys

ALWAYS = {"pytest", "tox", "nox", "eslint", "tsc", "ruff", "mypy", "flake8", "black", "prettier", "jest", "vitest",
          "playwright", "rspec", "phpunit", "shellcheck", "bats"}
NEEDS_KW = {"npm", "pnpm", "yarn", "bun", "npx", "make", "cargo", "go", "rake", "mvn", "gradle", "dotnet"}
SCRIPTISH = {"bash", "sh", "zsh", "python", "python3", "node"}
NOISE = {"echo", "printf", "cat", "grep", "sed", "awk", "git", "die", "read", "test", "[", "[[", "export", "local", "readonly",
         "set", "unset", "return", "exit", "cd", "mkdir", "rm", "cp", "mv", "ln", "touch", "head", "tail", "sort", "wc",
         "tr", "cut", "find", "xargs", "type", "command", "which"}
KW = re.compile(r"test|lint|check|clippy|fmt|vet|verify|gate|audit|eval|ratchet|typecheck|build|\bci\b", re.I)
SCRIPT_PATH = re.compile(r"(?:\.\./|\./)?[\w.-]+(?:/[\w.-]+)+\.(?:sh|py)")
STAGE_FILES = {"pre-commit": [".githooks/pre-commit", ".husky/pre-commit"], "pre-push": [".githooks/pre-push", ".husky/pre-push"],
               "precheck": [f"{d}/precheck{e}" for d in ("scripts", "script", "bin") for e in ("", ".sh")]}
ENV = {"DCR_PREPUSH_CMD": ("pre-push", True), "VERIFY_CMD": ("train", False), "BASE_AUDIT_CMD": ("train", True),
       "BROWSER_CMD": ("train", False), "RATCHET_CMD": ("train", False)}


def norm(text: str) -> str:
    return " ".join(text.split())


def logical_lines(text: str) -> list:
    """Code lines with backslash continuations joined; blank lines and whole-line comments dropped."""
    out, cur = [], ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            cur += line[:-1] + " "
            continue
        out.append((cur + line).strip())
        cur = ""
    return [ln for ln in out + [cur.strip()] if ln and not ln.startswith("#")]


def segments(line: str) -> list:
    """Token lists, one per `;`/`&&`/`||`/`|` segment, quotes respected. An unparseable line yields none."""
    lex = shlex.shlex(line, posix=True, punctuation_chars=";&|")
    segs, cur = [], []
    try:
        for tok in lex:
            if set(tok) <= set(";&|"):
                segs.append(cur)
                cur = []
            else:
                cur.append(tok)
    except ValueError:
        return []
    return [s for s in segs + [cur] if s]


def literal(tok: str) -> bool:
    """A plain word: no whitespace, quote, `$`, `=` or other shell syntax. A variable is never guessed at."""
    return re.fullmatch(r"[\w@%+:,./~-]+", tok) is not None


def fmt(toks: list) -> str:
    """Display text for a command: shell-safe words stay bare (`$VAR` shown as written, it is a report, not a script)."""
    return " ".join(t if re.fullmatch(r"[\w@%+=:,./${}()-]+", t) else shlex.quote(t) for t in toks)


def suite_at(toks: list, first: bool) -> bool:
    """True when `toks` begins a test/lint/build suite. A script run by bare path counts only as a segment's first word."""
    if not literal(toks[0]):
        return False
    prog = os.path.basename(toks[0])
    if prog in ALWAYS:
        return True
    if prog in NEEDS_KW:
        return any(literal(t) and KW.search(t) for t in toks[1:3])
    if prog in SCRIPTISH:
        args = [t for t in toks[1:] if not t.startswith("-")]
        return bool(args) and literal(args[0]) and bool(KW.search(os.path.basename(args[0])))
    return first and "/" in toks[0] and bool(KW.search(prog))


def wrapped(rest: list) -> list:
    """The suite a `gate_cache.py run <rest>` call wraps: `[(text, True, range_aware)]`, or none when it names no suite."""
    opts = rest[:rest.index("--")] if "--" in rest else rest
    ranged = "--base" in opts or "--head" in opts
    if "-c" in opts and opts.index("-c") + 1 < len(opts):
        return [(norm(opts[opts.index("-c") + 1]), True, ranged)]
    if "--" in rest and rest[rest.index("--") + 1:]:
        return [(fmt(rest[rest.index("--") + 1:]), True, ranged)]
    return []


def occurrences(line: str, depth: int = 0) -> list:
    """`(command text, cached, range_aware)` for each suite on one logical line."""
    found = []
    for toks in segments(line):
        if os.path.basename(toks[0]) in NOISE:
            continue
        w = next((i for i, t in enumerate(toks) if os.path.basename(t) == "gate_cache.py" and toks[i + 1:i + 2] == ["run"]), None)
        if w is not None:  # an explicit cached call: the wrapped command is the suite, the wrapper is not
            found += wrapped(toks[w + 2:])
            continue
        skip = set()
        for i, t in enumerate(toks):
            if i in skip:
                continue
            if t == "--verify-cmd" and i + 1 < len(toks):  # merge_train.py: its gate consults gate_cache
                found.append((norm(toks[i + 1]), True, False))
                skip.add(i + 1)
                continue
            if depth < 2 and os.path.basename(t) in SCRIPTISH and toks[i + 1:i + 2] == ["-c"] and i + 2 < len(toks):
                found += occurrences(toks[i + 2], depth + 1)
                break
            if suite_at(toks[i:], i == 0):
                cut = next((j for j, w in enumerate(toks[i:]) if re.match(r"\d*[<>]", w)), len(toks) - i)
                found.append((fmt(toks[i:i + cut]), False, False))
                break
    return found


def hooks_dir(root: str) -> str:
    try:
        p = subprocess.run(["git", "-C", root, "rev-parse", "--git-path", "hooks"], capture_output=True, text=True, timeout=30)
        if p.returncode == 0 and p.stdout.strip():
            return os.path.join(root, p.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(root, ".git", "hooks")


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def stage_sources(root: str, extra: list) -> dict:
    """`{stage: [(label, text, is_env)]}`: the stage files that exist, scripts they name (one level), and env commands."""
    hd = hooks_dir(root)
    files = {"pre-commit": [os.path.join(hd, "pre-commit")], "pre-push": [os.path.join(hd, "pre-push")]}
    for stage, rel in STAGE_FILES.items():
        files[stage] = files.get(stage, []) + [os.path.join(root, r) for r in rel]
    for name, path in extra:
        files[name] = files.get(name, []) + [path]
    out: dict = {}
    for stage, paths in files.items():
        seen = []
        for p in paths:
            if os.path.isfile(p) and p not in seen:
                seen.append(p)
                for line in logical_lines(read(p)):
                    for cand in SCRIPT_PATH.findall(line)[:2]:
                        for base in (os.path.dirname(p), root):
                            q = os.path.normpath(os.path.join(base, cand))
                            if os.path.isfile(q) and q not in seen and len(seen) < 9:
                                seen.append(q)
                                break
        if seen:
            out.setdefault(stage, []).extend((os.path.relpath(p, root), read(p), False) for p in seen)
    for var, (stage, _) in ENV.items():
        if os.environ.get(var, "").strip():
            out.setdefault(stage, []).append((f"${var}", os.environ[var], True))
    return out


def build(root: str, extra: list) -> dict:
    """`{stage: [(command, cached, range_aware)]}` in file order, duplicates within a stage kept once."""
    pure = os.environ.get("DCR_PREPUSH_TREE_PURE") == "1"
    result: dict = {}
    for stage, srcs in stage_sources(root, extra).items():
        seen, rows = set(), []
        for label, text, is_env in srcs:
            var = label[1:] if is_env else ""
            if is_env and ENV[var][1]:  # shipped wiring caches the whole env string as one suite
                found = [(norm(text), True, var == "DCR_PREPUSH_CMD" and not pure)]
            elif is_env:
                found = occurrences(text) or [(norm(text), False, False)]
            else:
                found = [o for line in logical_lines(text) for o in occurrences(line)]
            for cmd, cached, ranged in found:
                if cmd not in seen:
                    seen.add(cmd)
                    rows.append((cmd, cached, ranged))
        result[stage] = rows
    return result


def report(root: str, extra: list) -> list:
    stages = build(root, extra)
    if not stages:
        return [f"gate_map: no gate stages found under {root} (looked for hooks, .husky, scripts/precheck, "
                "$DCR_PREPUSH_CMD, $VERIFY_CMD; add one with --stage NAME=PATH)"]
    lines, where = [], {}
    for stage, rows in stages.items():
        lines.append(f"{stage}:")
        for cmd, cached, ranged in rows:
            lines.append(f"  {'cached  ' if cached else 'uncached'}  {cmd}{'  [range-aware]' if ranged else ''}")
            where.setdefault(cmd, []).append((stage, cached, ranged))
    dups = {c: w for c, w in where.items() if len(w) > 1}
    lines.append("")
    if not dups:
        return lines + ["no command appears in more than one stage"]
    for cmd, w in dups.items():
        names = ", ".join(s for s, _, _ in w)
        unc = [s for s, cached, _ in w if not cached]
        if unc:
            lines.append(f"DUPLICATE  {cmd}  runs in {names}; uncached in {', '.join(unc)}: wrap it with gate_cache.py run")
        elif len({r for _, _, r in w}) > 1:
            lines.append(f"DUPLICATE  {cmd}  runs in {names}; scopes differ (range-aware vs tree): "
                         "set DCR_PREPUSH_TREE_PURE=1 if it is a function of the tree only")
        else:
            lines.append(f"SHARED     {cmd}  runs in {names}; cached everywhere, so once per tree")
    return lines


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report which suites each gate stage runs and which are duplicated.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--stage", action="append", default=[], metavar="NAME=PATH", help="add a stage file (repeatable)")
    a = ap.parse_args(argv)
    extra = []
    for s in a.stage:
        name, sep, path = s.partition("=")
        if not sep or not name or not path:
            ap.error(f"--stage wants NAME=PATH, got {s!r}")
        extra.append((name, os.path.join(a.root, path)))
    print("\n".join(report(os.path.abspath(a.root), extra)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
