#!/usr/bin/env python3
"""handoff_inject.py — SessionStart hook (matchers compact|startup|clear): re-inject a short handoff.

WHY: auto-compact (`autoCompactWindow`) keeps a long session cheap, but a compaction summary can drop the plan.
Agents write `.claude/handoff.md` (state, open work, next step) as they go; this hook prints it after a compact,
startup or /clear so the next turn resumes from it instead of asking the owner to restart the session.
SessionStart plain stdout is added to the model's context.

Reads the newest regular file matching `.claude/handoff*.md` under $CLAUDE_PROJECT_DIR (else the cwd). Prints
at most 2048 bytes in total (a one-line header plus the head of the file, truncated on a character boundary).
Prints nothing when there is no file, it is empty or a symlink (fail closed: a link could point outside the repo),
or on any error; always exits 0.

Run `handoff_inject.py --selftest` to check it.
"""
import os
import sys
import tempfile
from pathlib import Path

CAP = 2048


def render(root):
    """The text to inject for the repo at `root`, or "" when there is no usable handoff."""
    files = [p for p in Path(root, ".claude").glob("handoff*.md") if p.is_file() and not p.is_symlink()]
    if not files:
        return ""
    p = max(files, key=lambda f: f.stat().st_mtime)
    head = f"Handoff from the previous context ({p.name}); resume from it, do not ask the owner to restart:\n"
    room = CAP - len(head.encode()) - 1  # 1 = trailing newline
    body = p.read_bytes()[:room].decode("utf-8", "ignore").strip()
    return head + body + "\n" if body else ""


def _selftest():
    ok = []
    with tempfile.TemporaryDirectory(prefix="handoff-") as d:
        ok.append(("absent-prints-nothing", render(d) == ""))
        os.mkdir(os.path.join(d, ".claude"))
        h = Path(d, ".claude", "handoff.md")
        h.write_text("next: run the tests\n")
        ok.append(("present-prints-it", "next: run the tests" in render(d)))
        newer = Path(d, ".claude", "handoff-b.md")
        newer.write_text("newer note\n")
        os.utime(h, (1, 1))
        ok.append(("newest-wins", "newer note" in render(d) and "run the tests" not in render(d)))
        newer.write_text("é" * 5000)
        ok.append(("capped-at-2KB", 0 < len(render(d).encode()) <= CAP))
        newer.write_text(" \n")
        ok.append(("blank-file-prints-nothing", "newer" not in render(d)))
    for n, g in ok:
        print(f"{'PASS' if g else 'FAIL'}  {n}")
    print(f"\nselftest: {sum(g for _, g in ok)}/{len(ok)} passed")
    return 0 if all(g for _, g in ok) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    try:
        sys.stdout.write(render(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    except Exception:
        pass  # fail open: a broken handoff must never block a session start
    sys.exit(0)
