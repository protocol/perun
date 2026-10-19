#!/usr/bin/env python3
"""Writes the dev wordings dev/skill_<name>.txt from V0 (the shipped skill text, ../../idea-critic-v2-1019/prompts/skill_v0.txt)
by exact, asserted replacements. Dev only: see PREREG.md for what each wording is and how it scored."""
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
V0 = (D.parents[1] / "idea-critic-v2-1019/prompts/skill_v0.txt").read_text()

# V2/V3 base: blocker test (the V3 blocker/risk lists, no edge gate), cheaper-alternative and north-star softening.
PRIME_OLD = "disagreement is as performative as automatic agreement."
PRIME_NEW = PRIME_OLD + """ Surviving means no
*blocker* (step 6) was found: open risks do not count against the claim, they
become its kill criteria."""
OPT_OLD = "reversibility. It must beat all three, not only the status quo."
OPT_NEW = """reversibility. It must beat do nothing. A cheaper, smaller, staged or
   safer alternative blocks only if it reaches the same upside on the stated
   facts; otherwise it shapes the first step, it does not stop the plan."""
FIT_OLD = "A sound idea that does not move the north star is a no or a later."
FIT_NEW = """A sound idea that does not move a *stated* north star is a no or a later;
   an assumed one never blocks."""
S6_OLD = "6. **Close with ONE decision** (go, no-go or go-if: never a menu). If the plan\n   commits"
S6_NEW = """6. **Close with ONE decision** (go, no-go or go-if: never a menu), from a
   **blocker test**. Sort every objection first. A *blocker* is a fact already
   in hand (stated in the proposal, or your recomputation of its own figures)
   that shows the plan fails as proposed: its numbers do not work, its own
   evidence contradicts its core claim, an alternative reaches the same upside
   cheaper, the stated facts already show the target users do not want it,
   or a negative the proposal states as already true (not *may* or *could*)
   that removes its own route to the upside and that the plan does not answer.
   A *risk* is anything that could go wrong but is not yet shown: unproven
   demand or category, no prior experience, a high price, strong incumbents,
   execution difficulty, the requester's own listed risks, a pre-mortem story,
   a one-way door, a missing term, clause, pilot or metric (add it yourself as
   a kill criterion). Risks never decide the call; they become the kill
   criteria. No blocker means **go** (go-if when a precondition can be met
   now); no-go needs a named blocker that survived your own skeptic check.
   Every bet worth making is uncertain: a sound plan wrongly blocked costs as
   much as a weak one wrongly passed. Write the sort before the decision: a
   `Blockers:` line (each with the fact it rests on, or NONE) and a `Risks:`
   line. If the plan
   commits"""
FIRST = """0. **First call, before any attack.** Read only the facts the proposal states
   and decide as an experienced operator who must answer today: write
   `First call: GO` or `First call: NO-GO` and one line of why. The steps below
   can turn a first-call GO into NO-GO only through a blocker (step 6); they
   never turn a first-call NO-GO into GO, and a risk, a missing cap, pilot or
   kill criterion, or a cheaper alternative never changes a first-call GO.
"""
STEP1 = "1. **Steelman, then attack.**"


def base():
    t = V0
    for old, new in ((PRIME_OLD, PRIME_NEW), (OPT_OLD, OPT_NEW), (FIT_OLD, FIT_NEW), (S6_OLD, S6_NEW)):
        assert t.count(old) == 1, old
        t = t.replace(old, new)
    return t


def v4a():
    t = base()
    assert t.count(STEP1) == 1
    return t.replace(STEP1, FIRST + STEP1)


TOP_OLD = "## Prime directive"
TOP_B = """## Decide like an operator, then attack

Reflexive agreement ships weak ideas; reflexive objection kills sound ones, and
both cost the same. This method adds an attack to your judgment; it does not
raise the bar above it. Read the proposal's stated facts and make the call a
sound operator would make today. Every finding below is a note for the dissent
ledger or a kill criterion unless it is a *blocker* (step 6). The absence of a
pilot, cap, metric or fallback is never a blocker: add it to the plan yourself.

---

"""


def v4b():
    t = v4a()
    assert t.count(TOP_OLD) == 1
    return t.replace(TOP_OLD, TOP_B + TOP_OLD)


FIRST_C = """0. **First call, before any attack.** Read only the facts the proposal states
   and decide as an experienced operator who must answer today: write
   `First call: GO` or `First call: NO-GO` and one line of why. Then test it
   against step 6: a first-call GO becomes NO-GO only through a blocker, and a
   first-call NO-GO stands only if it rests on a blocker. If it rests only on
   risks, a missing cap, pilot or kill criterion, or a cheaper alternative,
   change it to GO and carry those as kill criteria.
"""


def v4c():
    t = v4b()
    assert t.count(FIRST) == 1
    return t.replace(FIRST, FIRST_C)


VARIANTS = {"v4a": v4a, "v4b": v4b, "v4c": v4c}

if __name__ == "__main__":
    for n in sys.argv[1:]:
        (D / f"skill_{n}.txt").write_text(VARIANTS[n]())
