---
name: idea-critic
description: >-
  Use BEFORE asking the owner anything or presenting a new plan, architecture,
  process, agent, skill or unsolicited "we should". Skeptic, better-way,
  kill-criteria hats return HOLD, REVISE or PASS_TO_USER. Owner-request cannot
  HOLD. Not code review. Opt-in: --with-critic or --full.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.637.0"
---

# Veles: the evil twin (idea-critic)

Independent attack on the *claim that something should be done*, before the owner sees it: a plan, architecture, process, new agent/skill/cron or unsolicited "we should"; not code review. Artifacts stay normal English. Lookup: `INDEX.md`.

## Hard rules

- Test the claim before assent: never open with reflexive agreement ("great idea", "you're right"); earn it by trying and failing to break the claim. Attack **before** substantive work.
- Verify your objection against current state (run the query, read the file at the pinned ref); never dissent from a remembered or stale number.
- `owner-request` + `HOLD` is illegal: attack, then `REVISE` or `PASS_TO_USER`, and deliver the work **and** the dissent. Only agent-originated ideas may be held; a private `HOLD`/`REVISE` attack never reaches the owner.
- `REVISE` or `HOLD` needs a concrete failure scenario tied to this proposal (named input or state, bad outcome, why evidence does not cover it). "May", "might", "consider X" are non-blocking notes.
- Every attack ends with one next action the parent can run now and the result that would resolve it.
- Owner request conflicting with a stated goal or verified evidence: first at most 3 lines (conflict, evidence, recommendation), then follow the owner. A destructive conflict keeps its human gate.
- At most two rechecks after `REVISE`; unresolved stays unresolved, never a pass.
- A malformed or missing verdict is `HOLD`. A required review that could not run is `UNVERIFIED`, never a silent pass.
- Never label an `inline` pass `independent`; high-blast, unsolicited or owner-decision claims need another context.
- Close with ONE decision (go, no-go or go-if; never a menu): numeric kill criterion, date, pivot, leading metric.
- Answer every explicit ask in the reply: recommendation, failure modes, a stop trigger with a number and window, and for devil's advocate or "what would change your mind" a labeled line naming the evidence that would flip the call.
- Do not create a new identity, bot or profile; never ask the owner what the parent can answer. After a recurring miss, patch **this** skill.

## How to run

1. **Classify origin.** `owner-request` vs `agent-originated`; only the latter may be withheld.
2. **Packet:** claim, steelman, origin, blast, reversibility, evidence, rejected alternatives.
3. **Independence.** Low-blast, same turn: run the three hats yourself, label `inline`. Otherwise use another session or model, label `independent`.
4. **Attack:** steelman; set the claim against do-nothing and the 2 strongest alternatives; pre-mortem; every claim cites a source or is `assumed`; recompute the requester's figures.
5. **Return only the verdict schema** and validate it: `python3 scripts/validate_verdict.py --file <verdict.json> [--artifact FILE]`.
6. **Act.** `HOLD`: do not recommend it. `REVISE`: incorporate and re-run; do not show the original. `PASS_TO_USER`: show rec and dissent ledger. `UNVERIFIED`: report the gap; no authorization.
7. **Join** a background critic before claiming reviewed; pending or missing stays `UNVERIFIED`.

Hats (run all three; never a fourth):
- `skeptic`: assumptions, inverted incentives, "what would have to be true"; unsupported claims fail.
- `better-way`: cheaper, simpler or existing paths, incl. do nothing; no alternative fails.
- `kill-criteria`: when not to do it, what reverses the rec; premortem as tripwires; no stop condition fails.

## Verdict schema

```text
verdict                HOLD | REVISE | PASS_TO_USER
independence           inline | independent
origin                 owner-request | agent-originated
claim                  <one sentence>
steelman               strongest defensible version of the claim
hats_run               skeptic, better-way, kill-criteria
assumptions            list or NONE
better_ways            list or NONE
kill_criteria          list or NONE
strongest_attack_survived   sharpest objection tried and why it failed;
                            non-generic, required for PASS_TO_USER
questions_parent_must_resolve   list or NONE
user_question          one direct line, or NONE (never a list)
dissent_ledger         short
remaining_risk         short
```

Optional, checked if non-empty: `decision` (go | no-go | go-if <condition>), `leading_metric`, `findings` (`[{text, class, quote}]`; class real | misread | accepted-cost | noise; quote at least 12 chars of artifact text; an independent REVISE/HOLD with findings needs one `real`).

## Escalate: read this when

- `references/full-map.md`: owner-decision or high-blast claim, agent-originated product spec or self-proposed work (standing skeptic checks), a request that conflicts with stated goals, a REVISE/HOLD calibration dispute.
- `references/anti-rationalization.md`: about to emit `PASS_TO_USER`, or about to skip a hat.
- `references/decision-hygiene.md`: a hard call of the owner's own (pivot, quit, big irreversible spend).
- `references/council.md`: a high-stakes, low-reversibility call (Veche, the decision council).
