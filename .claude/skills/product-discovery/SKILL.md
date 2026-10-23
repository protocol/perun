---
name: product-discovery
description: >-
  Use when deciding whether something is worth building, what to build first,
  what not to build, or whether what shipped is working. Structures real-user
  evidence: Mom-Test interviews, riskiest-assumption gate, PMF survey, ICE.
  Never fabricates findings. Opt-in: --with-discovery.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.2.1"
---

# Product discovery

Structure the outside evidence that says whether to build, what to build first and whether what shipped works: method, not opinion. It designs the research the **user runs** and interprets what the user brings back. `idea-critic` attacks a claim you already hold from the inside; this gathers and reads outside evidence. Persisted artifacts stay normal English. Lookup table: `INDEX.md`.

## Hard rules

- **Never invent** interview findings, customer quotes, personas, market size / TAM, competitor facts, adoption numbers or a PMF verdict. A request for a finding or persona with no user data gets an **empty-slot template**: the slots the user must fill and how to obtain each, never a plausible-looking fill. A realistic example is the fabrication. Name the research to run (Mom Test or JTBD interviews) (evals.json `refuses-example-finding`).
- **A scoring table has blanks, not guesses.** ICE (Impact × Confidence × Ease) over RICE for a solo or small builder. Ship blank inputs and a how-to-obtain note per column; the user supplies the numbers, the skill does the arithmetic and orders the list. Never print a reach/impact/confidence number the user did not supply (`no-invented-scores`).
- **PMF is never declared from a conversation, demo or vibes.** It is an empirical threshold on the user's real data: the "very-disappointed" survey (verify the exact figure before asserting it) and a flattening retention cohort. Enthusiasm in a call is not a yes; no data means `UNVERIFIED` (`pmf-not-declared-from-chat`).
- **Riskiest assumption first.** Name the assumptions (desirability, viability, feasibility, usability), rank by impact × uncertainty, take the riskiest and define the cheapest test that could disconfirm it. If that test has not been run, refuse to build yet: name the assumption and the test, build after, not instead. At `prototype`/`mvp` this gate dominates (`riskiest-assumption-gate`).
- **Every ranked assumption gets a test row:** the assumption, its cheapest behavioral test (fake door, concierge or pre-sale, not a survey of intent), the metric, a numeric kill threshold ("drop the idea or pivot if fewer than N of M"), a sample size and a deadline, all fixed before the test runs. Propose each as a labelled starting value derived by arithmetic from figures the user gave, show the basis, add the go / narrow / drop rule, and say the user adjusts it. Leave a slot blank only when no figure was given to derive it from. A threshold is a decision rule, never a finding. A test with no kill threshold cannot fail, so it is not a test. Invent no result, market size or conversion benchmark (`assumption-test-has-numeric-kill-threshold`, `proposes-starting-threshold-from-given-figures`).
- **Route the unknowable.** Market size, competitor claims, legal/tax questions, anything the repo and the user do not hold go to real research, the owner or a licensed professional as a routed open question; never conclude it. Empty beats fabricated (`routes-unknowable-to-owner`).
- **Non-goals are recorded, stage-tied decisions** ("not X yet, because [reason]"), written beside goals and revisited at the next stage. Building on an untested assumption is a non-goal until the cheap test passes. A request touching one gets one line, "that is a non-goal for this stage because [reason] - reopen it?", not silent scope growth. It does not invent the product's strategy or set a non-goal the user did not choose (`non-goals-scope-defense`).
- **A "<product>-style X" ask names the reference's core loop as acceptance**, not a narrow agent-written "done when". Before closing, judge the result against the reference as a non-pilot user. The first pilot is a workflow the team itself runs; ship whatever that workflow already exposes and defer only what the pilot does not use (`reference-core-loop-acceptance`).
- **Interviews and experiments are the user's.** Design the guide (Mom Test: past specific behavior, never pitch; JTBD switch interview: the four forces) and interpret the user's real transcripts and results. It does not invent quotes or synthesize a persona from nothing, and never reports a result that was not measured.
- **Stage-aware** (`deep-code-review` `STAGE`). `prototype`: assumption gate and discovery dominate, hold polish and infra. `mvp`: first PMF read. `growth`: retention cohorts and prioritization drive the backlog. `mature`: discovery for new bets, not gold-plating the core.

## Excuse to rebuttal

- "Fill in a plausible persona to illustrate": it becomes evidence once read; give an empty-slot template.
- "Estimate the ICE numbers to move fast": invented inputs give a confidently wrong order; blanks plus how-to-obtain.
- "The demo felt great, call it PMF": no data, `UNVERIFIED`.
- "Give me the market size": outside the model; route to real research.
- "Add this adjacent feature too": if it is a stage non-goal, flag it and ask to reopen.

## Escalate: read this when

- `references/full-map.md`: you are designing interviews or experiments, writing a test row, reading PMF or prioritization, writing a spec that names a reference (three-input recipe), recording non-goals, or need the full anti-rationalization table, the standards list or the verification cases. It holds the full text of every rule above.
- `evals/evals.json`: you change this skill and need the planted cases (example finding, ICE, PMF from a call, build before the test, TAM, adjacent scope, reference-named ask, kill threshold).
- `scripts/discovery_check.py`: run this on a test-row, ICE, PMF or non-goal plan as JSON; it checks only rules quoted from this file.

Output structure follows `communication-structure` if installed.
