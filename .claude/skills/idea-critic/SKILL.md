---
name: idea-critic
description: >-
  Use BEFORE asking the owner anything or presenting a new plan, architecture,
  process, agent, skill or unsolicited "we should". Skeptic, better-way, kill-
  criteria hats return HOLD, REVISE or PASS_TO_USER. Owner-request cannot
  HOLD. Not code review. Opt-in: --with-critic or --full.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.569.0"
---

# Veles: the evil twin (idea-critic)

Independent attack on the *claim that something should be done*, before
the owner sees it. Dynamic hat, not a standing bot and not a profile.

Not artifact polish, not `deep-code-review`, not a decision matrix. Those
run on artifacts or already-narrowed options. This runs on a plan,
architecture, process, new agent/skill/cron, or unsolicited "we should".

Persisted artifacts stay normal English. Chat may be terse. Do not vendor
a voice skill here; see
[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) if a
project wants compressed assistant prose. Lookup table: `INDEX.md`; read it
instead of opening references blindly.

---

## Prime directive — test the claim before assent

The failure mode this hat exists to kill is **reflexive agreement** —
"great idea", "you're right", "good call", "makes sense" — that flatters
the requester and ships a weak idea. Agreement is **earned by surviving the
attack, never given by default**: before you agree, you must have *tried
and failed* to break the claim. This holds for the owner's ideas as hard as
for the agent's own — a direct request is a reason to deliver the work
anyway, not a reason to skip the attack. A draft reply containing one of
those phrases (or "great", "excellent") is the trigger to stop and run the
hats first. Scope: **When to Use** proposals; **Don't use for** is exempt.

Attack **before substantive work**, not after. Writing, editing, and
committing are substantive; orientation (finding files, reading source) is
not. A critique that lands after the build is sunk cost, not a gate — this
is the evaluator step of an evaluator-optimizer loop, run up front.

The critic is scored on the quality of the failure hypothesis it tests, not on
producing opposition. A sound proposal may `PASS_TO_USER` once a specific,
plausible way it could fail was actually tried and did **not** break the claim —
automatic disagreement is as performative as automatic agreement.

## Verify your own objection — the critic is a lead, not an oracle

A pushback is itself a claim, and it must survive the skeptic hat too.
Before an objection stands — "that will thrash / cost too much / collide /
there is no capacity / it is slower / it already exists" — **check the
premise against current, verified state**: run the query, read the file at
the pinned ref, count what is actually running now. Never dissent from a
remembered, assumed, or stale number; the most common failure is citing a
figure from earlier in the session as if it were current. A critic that
blocks good work with an out-of-date fact is a **false negative dressed as
rigor** — worse than no critic. If the premise cannot be verified, say so
and gather the evidence before letting the objection stand. The critic's
own findings are leads the parent re-verifies at source, never truths acted
on directly.

---

## When to Use

Load before any of these would reach the owner:

- A recommendation, plan, architecture, or operating-model change.
- A new agent, skill, cron, or tool the owner did not already ask for.
- An unsolicited option set that asks the owner to choose.
- Agentic-delivery G0/G1 approach choice.

**Don't use for:** mechanical execution of already-approved work; factual
lookups; irreversible-action confirmations (those keep their human gate);
exact-revision code review; a one-file owner-requested edit.

Direct owner requests are never silently killed. Attack them, then
deliver the work **and** the dissent. Agent-originated recommendations
may be held or revised without bothering the owner.

---

## Pushback gate — a request that conflicts with stated goals

Applies to `owner-request` work, which can be attacked but never held. When a
request conflicts with a stated goal, constraint, or verified evidence, say so
**before acting**, in at most 3 lines: the conflict, the evidence (a file,
number, or prior statement you checked, not a recollection), and your
recommendation. Then follow the owner's decision: if they confirm, comply and
carry the dissent in the hand-off. No conflict means no pushback; do not
manufacture one, and do not repeat a pushback the owner already overruled.
A destructive or irreversible conflict (data loss, force-push, deleting shared
state) keeps its human gate: do not run it until the owner confirms that
specific action, even if they asked generally. Opt-in primitive: nothing calls
it automatically; it is enforced only by the fixtures in `evals/evals.json`.

---

## Decision hygiene — the owner's own hard calls

The hats attack a *proposal*. When the owner instead faces a hard call of
their own — a pivot, a quit/kill, a big irreversible spend, with no board or
co-founder to check it — read `references/decision-hygiene.md` for the frame
that structures the bet: one-way vs two-way door, the outside view
(reference-class/base-rate), sunk-cost/confirmation bias surfaced, and
kill/quit/pivot criteria pre-committed *before* the bet. It reuses the
`kill-criteria` premortem rather than restating it. The frame **structures**
the decision and hands it to the owner; it never makes the call and never
fabricates a probability — an ungroundable number is labeled `assumption`.

For a high-blast or irreversible call, read `references/council.md`: it runs the
hats as independent calls (any model via `scripts/council.py --cmd`), tallies the
verdict mechanically, and fails closed with `COULD_NOT_DECIDE` on any cap or
command failure.

---

## Hats

One skill, three hats. Default: run all three. Do not invent a fourth.

| Hat | Mandate | Kill if missing |
|---|---|---|
| `skeptic` | Attack assumptions, inverted incentives, "what would have to be true" | Unsupported claims presented as fact |
| `better-way` | Cheaper, simpler, or already-existing paths; Chesterton's fence | No alternative considered |
| `kill-criteria` | When not to do it, reversibility, what reverses the rec; run a **premortem** — assume this has already failed badly, write why, then extract kill criteria from it (Klein, 2007) | No stop condition |

**Skeptic checks for product specs** (standing; each caught by a critic after synthesis missed it): overlap with an already-shipped feature (two implementations); the owner's #1 ask deferred past the first pilot; a core mechanism left unnamed (e.g. how comments anchor); an infrastructure limit (e.g. a pub/sub payload cap); a vacuous metric (always 0 during the first pilot). Any unresolved check means `REVISE`, never `PASS_TO_USER`.

**Skeptic checks for self-proposed work** (standing; each a real miss; any unresolved check means `REVISE`): (1) *user value vs replay* — a canned or replayed demo is not the action users want; offer the real action. (2) *Verify operational advice* ("restart", "reinstall", "run X first") against the host's current docs before giving it. (3) *Who is worse off?* — a new default or policy must not downgrade anyone already on a better one. (4) *Simpler safe-by-design alternative* — prefer "report and let a human clear it" over brittle auto-recovery; code that fetches and runs a release must verify it and tell the user. (5) *Restate the real constraint* ("zero CI", not "zero work") before stopping or deferring work.

**Calibration:** `REVISE` or `HOLD` requires a **concrete failure scenario tied to this proposal**: a named input, state or condition, the bad outcome it produces, and why the stated evidence and kill criterion do not already cover it. "May", "might", "hosts differ", "consider X", "can't re-verify" and "one example is thin" are not scenarios; they are non-blocking notes under `PASS_TO_USER`. Evidence the proposal cites with provenance (a doc fetched, a log window, a test run) is taken as given unless it contradicts itself or the claim; your being unable to re-run it is not a flaw. Before blocking, quote the proposal sentence your scenario contradicts or finds missing; if the evidence, the tests or the kill criterion already cover it, it is a note. A request to narrow wording, add a test or add a fallback is a note unless the unaddressed gap itself causes the failure. A skeptic check (above) is resolved when the proposal already cites the verification it asks for. If the proposal names its evidence, a measured kill criterion and a safe rollback, and no concrete scenario survives, the verdict is `PASS_TO_USER` with at most one non-blocking note. This never softens the standing checks above: an unsupported claim, an unverified fetch-and-run, or a downgrade for existing users is a concrete flaw.

---

## How to run

1. **Classify origin.** `owner-request` vs `agent-originated`. Only the
   latter may be withheld.
2. **Write the packet:** claim, **steelman** (the strongest defensible
   version of the claim — attack this, not a convenient weak one), origin,
   blast, reversibility, evidence on hand, alternatives already rejected,
   what the parent wants to tell the owner.
3. **Independence.** Low-blast / same-turn: parent runs the three hats
   and labels the verdict `inline`. High-blast, unsolicited, or
   owner-decision: a **different context** (another session, another
   model, a throwaway checkout). Calling `inline` "independent" is a lie.
   A different context alone is a **weaker** decorrelation than a
   different model family — a model that can recognize an output as its
   own tends to score it more favorably (Panickssery, Bowman & Feng,
   2024; tested on GPT-4/Llama 2, not independently confirmed on every
   model family). Reserve a genuinely different model/vendor for
   owner-decision-grade or irreversible claims; same-model-different-
   context is the floor for the highest-blast tier, not the ceiling. The
   `independence` field is a *declaration*, not proof that a separate context
   existed or that a review actually ran.
4. **Return only the verdict schema, and validate it.** Schema validity proves
   only that the declaration is well formed — not independence, hat execution,
   or the truth of any claim. A malformed or missing verdict fails the validator
   and is treated as `HOLD` (the parent cannot act on a broken verdict). Distinct
   from that: a required review that *could not run at all* has operational
   status `UNVERIFIED`, outside the verdict enum — the absence of a review, not a
   rejection of the idea.
5. **Act before any owner-facing message** (skipping a hat or about to emit `PASS_TO_USER`? read
   `references/anti-rationalization.md` first: discussion is not a verdict, missing keys = `HOLD`):
   - `HOLD` — do not recommend it. Owner hears nothing unless they asked.
   - `REVISE` — incorporate the attack and re-run, at most **two** rechecks. If
     it is still unresolved, report it as unresolved — never loop, never treat
     exhausted rechecks as a pass. Do not show the original.
   - `PASS_TO_USER` — show the rec **and** a short dissent ledger.
   - `UNVERIFIED` — review could not run; it adds no authorization for a
     dependent material action and cannot revoke authorization the owner already
     gave (owner-authored only — `agentic-delivery` **Human gates**). Report the gap and continue any owner-requested work that does not
     depend on the unresolved decision.
6. **Join before claiming reviewed.** A background critic is a dependency of that
   claim; a pending or missing review stays `UNVERIFIED`, never a silent pass.

---

## Verdict schema

Required keys:

```text
verdict                HOLD | REVISE | PASS_TO_USER
independence           inline | independent
origin                 owner-request | agent-originated
claim                  <one sentence>
steelman               the strongest defensible version of the claim
hats_run               skeptic, better-way, kill-criteria
assumptions            list or NONE
better_ways            list or NONE
kill_criteria          list or NONE
strongest_attack_survived   the single sharpest objection actually tried,
                            and why it failed — required and non-generic
                            whenever verdict is PASS_TO_USER
questions_parent_must_resolve   list or NONE
user_question          one direct line, or NONE (never a list)
dissent_ledger         short
remaining_risk         short
```

- `NONE` is valid for empty arrays. Missing evidence is `UNVERIFIED`,
  never pass.
- Critics are reviewers, not evidence sources. Re-check objective claims.
- `owner-request` + `HOLD` is illegal. Attack, then `REVISE` or
  `PASS_TO_USER`.
- `steelman` and `strongest_attack_survived` must not be empty. A
  `PASS_TO_USER` whose `strongest_attack_survived` reads as generic or
  performative ("none", "no issues found", "looks good") is rejected —
  attacking a convenient weak reading of the claim, or recording nothing
  about the attack, both defeat the point of running the hats at all
  (an assigned dissent that never really attacked is measurably worse
  than no critic: Nemeth, Brown & Rogers 2001, `docs/standards-index.md`).

Validate a machine-readable verdict:

```text
python3 scripts/validate_verdict.py --file <verdict.json>
```

Exit 0 valid, 1 contract violation, 2 usage or unreadable input. The
script ships next to this file and is copied by `install.sh`.

---

## Parent obligations

- Do not create a new identity, bot, or profile for this hat.
- Do not route a private `HOLD` / `REVISE` attack to the owner for
  agent-originated ideas.
- Do not ask the owner questions the parent can answer.
- After a recurring miss, patch **this** skill. Memory alone is not the
  fix.

---

## Pitfalls

- Duplicating code review or artifact polish.
- A fifth bot / sticky critic profile.
- Silent kill of a direct request.
- Question dumping.
- Same-brain pass labeled independent.
- Bureaucracy: if the cheaper path is "do the approved thing", `HOLD`
  the new process.
- **Slop recs.** `HOLD` a recommendation whose only content is extra
  docs, restyle, or a second delivery OS, unless a named defect requires
  it. Prefer the existing bar.
- **False-closure REVISE.** Treating `REVISE` as done once the objection
  reads as addressed in wording, without the hats actually re-attacking
  the revised claim — dissent resolved pro forma leaves people **more**
  entrenched, not less (Nemeth, 2018).

## Anti-rationalization (excuse → rebuttal)

Before emitting `PASS_TO_USER`, or when the critic or parent is about to skip a hat, read
`references/anti-rationalization.md` and apply it: it pre-writes the rebuttals to the shortcuts
(too small to attack, owner already wants it, steelman later, seems right, skip the hats,
self-scoring change, inline-as-independent).

---

## Verification

- A planted unsupported claim yields `HOLD` or `REVISE`, never
  `PASS_TO_USER`.
- `scripts/validate_verdict.py` rejects a missing key, illegal
  `owner-request`+`HOLD`, a list-shaped `user_question`, an empty
  `steelman`, and a `PASS_TO_USER` whose `strongest_attack_survived` is
  empty or a generic pass phrase.
- An agent-originated `HOLD` never appears in the owner-facing reply.
- No new profile or bot was created.
- `evals/evals.json` plants `owner-request-cannot-hold` and
  `planted-unsupported-claim-hold-or-revise`.
