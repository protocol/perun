#!/usr/bin/env python3
"""Round 4 variant builder (see PREREGISTERED.md). Writes prompts/perun_idea-critic_{v0,cA,cB,cC}.txt from the repo's current idea-critic SKILL.md
(v0 = SKILL.md unchanged; each candidate is a string substitution on it)."""
from pathlib import Path

H = Path(__file__).resolve().parent
S = (H.parents[2] / ".claude/skills/idea-critic/SKILL.md").read_text()
N = H / "prompts"

STEP5 = ("Recompute the\n   requester's own figures and dates (totals, timelines) before relying on them.")
STEP6 = ("(go, no-go or go-if: never a menu), its **kill\n   criteria** (observable tripwire, date, action when it fires), the")

CAP = ("(go, no-go or go-if: never a menu; where the plan can be staged, the call is a capped first tranche: one hard cap on spend and\n"
       "   weeks, and the pass bar that releases the rest), its **kill\n   criteria** (an observable tripwire checked inside the cap, with value,\n"
       "   checkpoint date and action when it fires, not already tripped by the plan as stated), the")
FIG = ("Recompute the\n   requester's own figures and dates (totals, timelines) before relying on them; a mismatch is the first finding,\n"
       "   with the corrected number and its arithmetic, and a figure that reconciles is not flagged.")


def sub(t, old, new):
    assert t.count(old) == 1, old
    return t.replace(old, new)


V = {"v0": S, "cA": sub(S, STEP6, CAP), "cB": sub(S, STEP5, FIG), "cC": sub(sub(S, STEP6, CAP), STEP5, FIG)}
N.mkdir(exist_ok=True)
for k, t in V.items():
    (N / f"perun_idea-critic_{k}.txt").write_text(t)
    print(k, len(t))
