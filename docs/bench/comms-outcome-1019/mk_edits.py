#!/usr/bin/env python3
"""Writes prompts/E1..E5.txt: V0 plus up to three new rule bullets (inserted before 'Add nothing the source lacks'). Refuses to overwrite."""
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
V0 = (D / "prompts/V0.txt").read_text()
ANCHOR = "- **Add nothing the source lacks.**"
B = {
    1: "- **Name the options in the ask.** Line 1 names each option by what it is (\"hire temp paralegals, outsource, or delay\"), never by a bare letter, with the owner and the date the source gives.\n",
    2: "- **Key figure line.** When the source gives a deciding figure, one line `Key figure: <figure> <what it measures>` states it exactly as the source does, near the top.\n",
    3: "- **Keep the facts the decision rests on.** Every option keeps each figure the source gives for it (cost, time, risk); cut only details unrelated to the decision. A decision message may run to about 250 words.\n",
}
EDITS = {1: [1], 2: [2], 3: [3], 4: [1, 2], 5: [1, 2, 3]}
assert V0.count(ANCHOR) == 1
for n, parts in EDITS.items():
    p = D / f"prompts/E{n}.txt"
    if p.exists():
        sys.exit(f"{p} exists")
    p.write_text(V0.replace(ANCHOR, "".join(B[i] for i in parts) + ANCHOR))
