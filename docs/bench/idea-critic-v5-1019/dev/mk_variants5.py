#!/usr/bin/env python3
"""Writes the dev wordings dev/skill_<name>.txt from V4 (../../idea-critic-v4-1019/prompts/skill_v4.txt) by exact, asserted
replacements. Each adds one explicit kill-criteria check to step 6, before any go. Dev only: see PREREGISTERED.md for how
they were chosen."""
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
V4 = (D.parents[1] / "idea-critic-v4-1019/prompts/skill_v4.txt").read_text()

ANCHOR = "   line. If the plan\n   commits"

# a: the stop condition must work. The one likeliest killer gets a criterion; if the plan cannot stop at it, that is a blocker.
KC_A = """   line.
   **Kill check before any go.** Take the one risk most likely to sink the plan
   and write its kill criterion (observable, numeric threshold, date). Then ask:
   if it fires, can the plan as proposed stop there with the loss capped? If the
   proposal commits to full scale, an irreversible spend or a public launch
   before the criterion can be read, it has no working stop condition: that is a
   blocker, and the call is no-go as proposed.
   If the plan
   commits"""

# b: a named risk blocks only when all three hold.
KC_B = """   line.
   **Kill check before any go.** For each risk the proposal names, ask three
   questions. Does it concern the core claim (that buyers will pay, that it
   works, that the partner or regulator will accept it)? Do the proposal's own
   facts support that it will happen, not merely that it could? Is the
   commitment too large or too irreversible to stop once it is seen? Three yeses
   make that risk a blocker; fewer make it a kill criterion.
   If the plan
   commits"""

# c: every risk the proposal names is read against the proposal's own facts; facts that point toward it make it a blocker.
KC_C = """   line.
   **Kill check before any go.** List every risk the proposal itself names. For
   each, write the fact in the proposal that bears on it and whether that fact
   points toward it happening or away from it. Where the proposal's own facts
   point toward it (a price above what buyers pay, a cost the margin cannot
   cover, a feature the target users have said they do not want, a rival
   already doing the same for less), it is a blocker, not a risk. Where the
   facts are silent, it stays a risk and becomes a kill criterion.
   If the plan
   commits"""


FIRST = """   `First call: GO` or `First call: NO-GO` and one line of why. The steps below
   can turn a first-call GO into NO-GO only through a blocker (step 6); they
   never turn a first-call NO-GO into GO, and a risk, a missing cap, pilot or
"""

# d (round 2, written after round 1 showed the kill check never changed a decision: the first call decides): a first-call GO
# needs a stated edge, not only a real need.
FIRST_D = """   `First call: GO` or `First call: NO-GO` and one line of why. A GO needs a
   *stated edge*: a fact in the proposal (a cost, product, access, timing or
   evidence advantage) that makes this plan beat what buyers have today. A real
   need alone is not an edge; need without a stated edge is a NO-GO as proposed.
   The steps below can turn a first-call GO into NO-GO only through a blocker
   (step 6); they never turn a first-call NO-GO into GO, and a risk, a missing
   cap, pilot or
"""


def build(kc=None, first=None):
    t = V4
    if first:
        assert t.count(FIRST) == 1
        t = t.replace(FIRST, first)
    if kc:
        assert t.count(ANCHOR) == 1
        t = t.replace(ANCHOR, kc)
    return t


VARIANTS = {"v5a": lambda: build(KC_A), "v5b": lambda: build(KC_B), "v5c": lambda: build(KC_C),
            "v5d": lambda: build(first=FIRST_D), "v5e": lambda: build(KC_C, FIRST_D)}

if __name__ == "__main__":
    for n in sys.argv[1:]:
        (D / f"skill_{n}.txt").write_text(VARIANTS[n]())
