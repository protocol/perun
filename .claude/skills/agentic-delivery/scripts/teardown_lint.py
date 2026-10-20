#!/usr/bin/env python3
"""teardown_lint.py [FILE.sh ...] | --selftest -- flag shell scripts that can leave work running after they exit.

WHY: two dev servers outlived their deleted worktree by 30 minutes because the script that started them had no EXIT
trap, and a poll loop with no deadline kept running after its parent died. Rules (operating-discipline.md item 11b):
  1. a script that starts background work (`&` ending a command, `nohup`, `setsid`, `disown`) needs a
     `trap ... EXIT` somewhere in the file;
  2. every endless loop (`while :`, `while true`, `until ...`, `for ((;;))`) needs a bound inside the loop: a numeric
     test (`-gt/-ge/-lt/-le`, `(( a < b ))`) or `$SECONDS` / `date +%s` arithmetic, found between the loop line and its
     matching `done`. A word like "timeout" in an echo does not count: quoted text and comments (full-line or trailing
     ` # ...`) are ignored.
LIMITS (a heuristic, not a proof): rule 1 checks that a trap exists, not that it stops that process; loop and `done`
matching counts keywords per line and can be fooled by heredocs, `case` arms and `eval` strings; a loop that is bounded
only by its caller or by a command's own timeout needs `teardown-lint: allow`. Only `.sh` files are read; Python
and other languages are not linted. Escape: a `teardown-lint: allow` comment anywhere in the file. No FILE args:
lints every `*.sh` next to this script. Prints `file:line: message` per finding and exits 1 on any; reads files only.
"""
import re
import sys
from pathlib import Path

BG = re.compile(r"(?<![&>|0-9])&\s*(?:$|[;)}])|\b(?:nohup|setsid|disown)\b")
LOOP = re.compile(r"\b(?:while\s+(?::|true)(?!\w)|until\s)|\bfor\s*\(\(\s*;\s*;\s*\)\)")
OPENER = re.compile(r"\b(?:while|until|for)\b")
CLOSER = re.compile(r"\bdone\b")
TRAP = re.compile(r"\btrap\b.*\bEXIT\b")
BOUND = re.compile(r"-(?:gt|ge|lt|le)\b|\(\([^)]*[<>]|\bSECONDS\b|date\s+\+%s")
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
TRAILING = re.compile(r"(?:^|\s)#.*$")  # a trailing comment; `$#` and `${#x}` have no space before the #


def lint(path: Path) -> list[str]:
    text = path.read_text(errors="replace")
    if "teardown-lint: allow" in text:
        return []
    lines = [(i, TRAILING.sub("", QUOTED.sub('""', l))) for i, l in enumerate(text.splitlines(), 1) if not l.lstrip().startswith("#")]
    out = []
    bg = next((i for i, l in lines if BG.search(l)), 0)
    if bg and not any(TRAP.search(l) for _, l in lines):
        out.append(f"{path}:{bg}: starts background work but has no `trap ... EXIT` to stop it")
    for k, (i, l) in enumerate(lines):
        if not LOOP.search(l):
            continue
        depth, body = 0, []
        for _, m in lines[k:]:
            body.append(m)
            depth += len(OPENER.findall(m)) - len(CLOSER.findall(m))
            if depth <= 0:
                break
        if not any(BOUND.search(m) for m in body):
            out.append(f"{path}:{i}: endless loop with no numeric bound, $SECONDS or date +%s test inside it")
    return out


def selftest() -> int:
    import tempfile
    cases = {
        "bg_no_trap": ("sleep 99 &\n", 1),
        "bg_trap": ("sleep 99 &\ntrap 'kill $!' EXIT\n", 0),
        "bg_in_function": ("f(){ srv & }\n", 1),
        "redirect_not_bg": ("cmd 2>&1 && other &>/dev/null\n", 0),
        "loop_no_bound": ("while :; do sleep 1; done\n", 1),
        "loop_bound": ("n=3\nwhile :; do [ $n -le 0 ] && break; n=$((n-1)); done\n", 0),
        "loop_word_in_echo": ('while true; do echo "timeout deadline -gt"; sleep 1; done\n', 1),
        "loop_after_then": ("if x; then while true; do sleep 1; done; fi\n", 1),
        "loop_c_style": ("for ((;;)); do sleep 1; done\n", 1),
        "loop_seconds": ("while true; do (( SECONDS > 60 )) && break; sleep 1; done\n", 0),
        "bound_outside_loop": ("[ $n -gt 3 ]\nwhile :; do sleep 1; done\n", 1),
        "second_loop_unbounded": ("while :; do [ $n -le 0 ] && break; done\nwhile true; do sleep 1; done\n", 1),
        "trailing_comment_not_a_bound": ("while true; do sleep 1 # SECONDS\ndone\n", 1),
        "hash_in_expansion_kept": ("while :; do [ ${#x} -gt 3 ] && break; done\n", 0),
        "comment_ignored":("# sleep 99 &\n# while true\n", 0),
        "allowed": ("# teardown-lint: allow\nwhile true; do :; done\n", 0),
    }
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        for name, (src, want) in cases.items():
            p = Path(d) / f"{name}.sh"
            p.write_text(src)
            got = len(lint(p))
            if got != want:
                bad += 1
                print(f"FAIL {name}: want {want} findings, got {got}")
    print(f"teardown_lint selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    files = [Path(a) for a in argv] or sorted(Path(__file__).resolve().parent.glob("*.sh"))
    found = [m for f in files for m in lint(f)]
    print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
