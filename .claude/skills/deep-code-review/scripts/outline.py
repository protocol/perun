#!/usr/bin/env python3
"""outline.py FILE... — cheap symbol map (line ranges) so a lane reads only the ranges it needs, not the whole file.

Purpose: print one line per symbol, `FILE:START-END kind name`, then read the wanted range with `sed -n 'START,ENDp' FILE`.
A map is a few hundred bytes where the file is tens of thousands; for a file you only need one symbol of, read the map first.
Backends, first that works: Python files use the stdlib `ast` (exact ranges, no dependency); other files use universal-ctags
when `ctags --version` says "Universal" (exact ranges); otherwise a plain regex outline (def/class/function/func/fn,
shell functions, markdown headings) whose END is the line before the next symbol at the same or a shallower indent (a
heuristic, a lead only). ast-grep and tree-sitter are not used: nothing here needs them and they add a hard dependency.
Edge cases: unreadable or binary file -> `FILE: unreadable` and exit 1; a Python syntax error falls back to the regex outline;
no symbols -> `FILE: no symbols`. Side effects: none (read-only; runs `ctags` only on the named files).
"""
import ast
import json
import re
import shutil
import subprocess
import sys

RX = re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?(?:(def|class|function|func|fn|interface|type)\s+([A-Za-z_$][\w$]*)|"
                r"([A-Za-z_][\w]*)\s*\(\)\s*\{|(#{1,6})\s+(\S.*))")


def py_symbols(src):
    out = []

    def walk(body, prefix=""):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(n, ast.ClassDef) else "def"
                start = min([n.lineno] + [d.lineno for d in n.decorator_list])
                out.append((start, n.end_lineno, kind, prefix + n.name))
                if kind == "class":
                    walk(n.body, n.name + ".")
    walk(ast.parse(src).body)
    return out


def ctags_symbols(path):
    p = subprocess.run(["ctags", "--output-format=json", "--fields=+ne", "-f", "-", path], capture_output=True, text=True, timeout=20)
    rows = [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]
    return [(r["line"], r.get("end", r["line"]), r.get("kind", "?"), r["name"]) for r in rows]


def regex_symbols(lines):
    heads = []
    for i, ln in enumerate(lines, 1):
        m = RX.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2) or ("fn" if m.group(4) else f"h{len(m.group(5))}"), m.group(3) or m.group(4) or m.group(6)))
    out = []
    for k, (i, ind, kind, name) in enumerate(heads):
        end = next((j - 1 for j, jind, *_ in heads[k + 1:] if jind <= ind), len(lines))
        out.append((i, end, kind, name.strip()))
    return out


def symbols(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith(".py"):
        try:
            return py_symbols(text)
        except SyntaxError:
            pass
    elif shutil.which("ctags"):
        try:
            if "Universal" in subprocess.run(["ctags", "--version"], capture_output=True, text=True, timeout=5).stdout:
                return ctags_symbols(path)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            pass
    return regex_symbols(text.splitlines())


def main(argv):
    rc = 0
    for path in argv:
        try:
            syms = sorted(symbols(path))
        except (OSError, UnicodeDecodeError):
            print(f"{path}: unreadable")
            rc = 1
            continue
        print("\n".join(f"{path}:{a}-{b} {k} {n}" for a, b, k, n in syms) if syms else f"{path}: no symbols")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__) or 2)
