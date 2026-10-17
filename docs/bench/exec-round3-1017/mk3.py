#!/usr/bin/env python3
"""Round 3 variant builder: writes prompts/perun_<skill>_r3a.txt from the round-1/2 texts in ../exec-1017/prompts (base = current SKILL.md text)."""
from pathlib import Path

O = Path(__file__).resolve().parent.parent / "exec-1017" / "prompts"
N = Path(__file__).resolve().parent / "prompts"
N.mkdir(exist_ok=True)
FIG = "`Figures:` line rebuilding each stated total, rate and date from its parts (`3 x $25k = $75k, stated $70k`)"


def sub(t, old, new):
    assert old in t, old
    return t.replace(old, new)


t = (O / "perun_idea-critic_v0.txt").read_text()
t = sub(t, "Recompute the\n   requester's own figures and dates (totals, timelines) before relying on them.",
        f"Recompute the\n   requester's own figures and dates and show it: the answer opens with a {FIG}. A mismatch is the\n   lead finding; if it breaks the stated goal or budget, the call is `no-go as written` with the corrected number.")
t = sub(t, "(go, no-go or go-if: never a menu), its **kill\n   criteria** (observable tripwire, date, action when it fires)",
        "(go, no-go or go-if: never a menu; where the plan can be bounded, make the call a capped first step with one hard cap, not a list of open\n   conditions), its **kill criteria** (an observable outcome tripwire with value, date and action, set where the plan as stated does not already trip it)")
(N / "perun_idea-critic_r3a.txt").write_text(t)

t = (O / "perun_agentic-ceo_r2b.txt").read_text()
t = sub(t, "the requester's stated figures are recomputed next, opening with any that do not reconcile, as the corrected number.",
        f"the next line is a {FIG}, any mismatch leading the answer as the corrected number.")
(N / "perun_agentic-ceo_r3a.txt").write_text(t)
