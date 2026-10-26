#!/usr/bin/env python3
"""Planted-red tests: memory index size FAIL, stale handoff WARN (operating_selfcheck) and STALE line (handoff_inject)."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/agentic-delivery/scripts"))
import handoff_inject
import operating_selfcheck as sc

fails = []
total = 0


def case(name, ok):
    global total
    total += 1
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        fails.append(name)


with tempfile.TemporaryDirectory() as d:
    mem, none = Path(d, "MEMORY.md"), os.path.join(d, "none.md")
    mem.write_text("- a\n" * 150)
    case("memory-150-lines-ok", sc.memory_handoff_lines(d, str(mem)) == [])
    mem.write_text("- a\n" * 151)
    case("memory-151-lines-fails", any(x.startswith("memory-index: FAIL") for x in sc.memory_handoff_lines(d, str(mem))))
    mem.write_text("x" * (20 * 1024 + 1) + "\n")
    case("memory-over-20KB-fails", any(x.startswith("memory-index: FAIL") for x in sc.memory_handoff_lines(d, str(mem))))
    case("memory-absent-silent", sc.memory_handoff_lines(d, none) == [])

    os.mkdir(os.path.join(d, ".claude"))
    h = Path(d, ".claude", "handoff.md")
    h.write_text("next: ship\n")
    case("fresh-handoff-no-warn", sc.memory_handoff_lines(d, none) == [])
    case("fresh-handoff-no-stale-prefix", not handoff_inject.render(d, "compact").startswith("STALE"))
    old = time.time() - 6 * 86400
    os.utime(h, (old, old))
    case("6-day-handoff-warns", any(x.startswith("handoff: WARN") for x in sc.memory_handoff_lines(d, none)))
    out = handoff_inject.render(d, "compact")
    case("6-day-handoff-injected-with-stale-line", out.startswith("STALE:") and "next: ship" in out)

    case("status-stamp-absent-silent", not any(x.startswith("status-update") for x in sc.memory_handoff_lines(d, none)))
    os.mkdir(os.path.join(d, ".perun"))
    st = Path(d, ".perun", "last-status-update")
    st.write_text("x\n")
    case("status-stamp-fresh-silent", not any(x.startswith("status-update") for x in sc.memory_handoff_lines(d, none)))
    os.utime(st, (old, old))
    case("10-day-status-warns", any(x.startswith("status-update: WARN") for x in sc.memory_handoff_lines(d, none, time.time() + 4 * 86400)))

print(f"\n{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
