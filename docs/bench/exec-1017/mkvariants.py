#!/usr/bin/env python3
"""Round 2 (see PREREGISTERED-ADDENDUM-2.md): build prompts/perun_<skill>_r2{a,b,c}.txt from the base text perun_<skill>_v0.txt.
Each variant rewrites the sentence or bullet where the skill decides what a requested call looks like (no new sections).
a = decision-memo contract; b = a + re-base an unrealistic stated assumption; c = b + a ledger built from stated figures only."""
import re
from pathlib import Path

P = Path(__file__).resolve().parent / "prompts"
REBASE = "Re-base a stated assumption that looks unrealistic to a conservative figure, decide on the corrected result and state the gap to the headline."
LEDGER = "Show money as a short ledger (budget, committed, remaining, buffer) built from stated figures only, anything else marked `assumed`."
CHOICES = "Decide every choice the requester listed (what first, what to defer, which option or vendor), never \"it depends\"."
TRIG = "a **halt trigger** and a **fallback trigger**, each as value, date and action, set where the plan as stated does not already trip it"


def cut(text, start, end):
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[:i], text[j:]


def ceo(t, extra):
    old = "It **routes and\ndecides**; it never re-implements what a specialist skill already does."
    assert old in t
    new = ("It **routes and decides**: asked for a call on a plan, it answers in one pass as a decision memo. The first line is the call and "
           "the one number it rests on; the requester's stated figures are recomputed next, opening with any that do not reconcile, as the "
           "corrected number. " + CHOICES + " Each failure mode is tied to a stated figure or date, each sign-off names its owner role, and it closes with "
           + TRIG + ". " + extra + " It routes to a specialist skill only for the part it cannot compute, and never re-implements what one already does.")
    return t.replace(old, new)


def idea(t, extra):
    a, b = cut(t, "Recompute the\n   requester's own figures", "and a review date.")
    new = ("Recompute the requester's own figures and dates first.\n6. **Close with ONE decision** (go, no-go or go-if: never a menu), led by the one number it "
           "rests on; open with any figure that does not reconcile, as the corrected number. " + CHOICES + " Tie each failure mode to a stated figure or date, "
           "name the owner of each sign-off, and give " + TRIG + ", plus the **leading metric** and a review date. " + extra)
    return a + new.rstrip() + b


def biz(t, extra):
    old = ("- **Apply, don't direct.** Present the math and a sensitivity range (\"at CAC X\n  and churn Y, payback is Z months\"); the pricing/spend **decision is the\n  user's**. Never \"you should charge $49.\"")
    assert old in t
    t = t.replace(old, "- **Apply, then recommend.** The decision is the user's, but a request for a call gets one: choose between their own options by the arithmetic and "
                       "give the sensitivity range that flips it (\"at CAC X and churn Y, payback is Z months\"). Never a price from outside their inputs "
                       "(\"you should charge $49\" with nothing behind it).")
    a, b = cut(t, "- **End Lane A with a decision aid", "fails the reader.")
    new = ("- **End Lane A with a decision memo, not bare math.** First line: the call and the one number it rests on. Then the recomputed figures, one compact line each, "
           "opening with any that do not reconcile, as the corrected number; the formula with the user's figures filled in and the one input that flips the answer "
           "(`break-even price = cost per seat ÷ (1 − target margin)`); thresholds named as rules of thumb the user accepts or replaces, never as facts about their market; "
           + TRIG + ", from the break-even; and a next step doable this week. " + CHOICES + " " + extra + " For Lane R, name the default action to hold until counsel confirms, "
           "the facts and documents to bring and which item is time-sensitive. An answer that only says \"it depends / ask a professional\" fails the reader.")
    return a + new.replace("  ", " ") + b


def pos(t, extra):
    a, b = cut(t, "### 4. Validate with real buyers", "never report a reaction that was not gathered.")
    new = ("### 4. Decide, then validate with real buyers\nAsked for a recommendation, commit to ONE segment and ONE headline from the user's own evidence and say why the others lose; "
           "recompute any stated win/loss, growth or share figure first and name a data error before building on it. The position is a hypothesis, committed not hedged "
           "(`[ASSUMED]` tags on the gaps). Write the falsification test as a number (buyers, threshold, date), tie the kill metric to the stated data at a level it does not "
           "already trip, and name the fallback position if it trips. " + extra + " Then the positioning is a hypothesis until real buyers in the segment react to it "
           "(message testing, sales conversations, landing-page signal): design the test, interpret the user's results, never report a reaction that was not gathered.")
    return a + new + b


FN = dict(**{"agentic-ceo": ceo, "idea-critic": idea, "business-ops": biz, "positioning": pos})
EXTRA = dict(a="", b=REBASE, c=REBASE + " " + LEDGER)
POS_C = REBASE + " Show the choice as a one-line evidence ledger (stated data point, what it supports)."

if __name__ == "__main__":
    for s, f in FN.items():
        base = (P / f"perun_{s}_v0.txt").read_text()
        for v, ex in EXTRA.items():
            ex = POS_C if (s == "positioning" and v == "c") else ex
            (P / f"perun_{s}_r2{v}.txt").write_text(f(base, ex))
            print(s, v, len((P / f"perun_{s}_r2{v}.txt").read_bytes()))
