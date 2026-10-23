---
name: positioning
description: >-
  Use when shaping how a product is positioned to its market: value
  proposition, segment, differentiation, messaging (Value Proposition Canvas,
  message house). A hypothesis to validate with real buyers; never fabricates
  market-size or competitor claims. Opt-in: --with-positioning.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.0.3"
---

# Positioning

Shape how a product is described to its market (value proposition, segment, differentiation, message) as a **hypothesis the user validates**, never as market truth the model asserts. No ground truth lives in the repo or the model. Persisted artifacts stay normal English. Lookup table: `INDEX.md`.

## Hard rules

- **Boundary.** `product-discovery` decides whether the problem is real; this decides how the solution is described. `growth-analytics` measures what users do; this decides what you say. Not a source of market facts: evidence comes from outside the model.
- **Hypothesis, not fact.** Every output is a hypothesis to test with real buyers. The failure is a confident fabricated "fact" that reads as researched.
- **Never fabricate** market size / TAM, market-share or competitor claims, customer quotes or testimonials, outcome / ROI numbers, or trademark / domain availability or clearance (`evals/evals.json`: `refuses-fabricated-market-facts`).
- **Empty slots for market facts, a committed draft for everything else.** Market facts (TAM, named competitors, quotes, outcome numbers) with no user input stay slots with how to obtain each. Given a product and an audience, draft the full statement (one specific segment as role plus trigger, need, category, the class of alternative used today such as a manual routine, spreadsheet or doing nothing, differentiator), tag every element the user did not supply `[ASSUMED]`, add the riskiest assumption and its test. Never a named vendor, number or quote.
- **Route the unknowable.** TAM goes to the user's real research. A search is not legal clearance: trademark / domain goes to a professional. A factual claim in a message needs the user's own proof.
- **Deliver the call, not a menu.** Asked to choose: commit to one segment, one lead message and one line why, from the user's numbers. Give a ready-to-use statement and headline; answer each named alternative (what the buyer gives up, the line that wins). Say "hypothesis" once. Caveats: the riskiest assumption and the test that would disprove it. Trademark, legal or market-size routing only when asked or the draft makes that claim.
- **Value Proposition Canvas.** Customer profile (jobs, pains, gains) from real discovery against the value map; fit is a hypothesis. No evidence behind the profile is a discovery gap: route to `product-discovery`, never invent it.
- **Statement.** *For [segment] who [need], [product] is a [category] that [key benefit]; unlike [alternative], it [differentiator].* Each bracket is the user's input or a flagged unknown. Label it a hypothesis.
- **Specific, not generic.** Segment: a nameable buyer in a situation, not a demographic or "teams". Alternative: the concrete thing used today, asked of real buyers; "Unlike the competition" is a blank. Differentiator: one user-supplied proof point plus what leaving the alternative costs; none is `UNVERIFIED — needs proof`. Swap in a rival's name: still true means undifferentiated.
- **Message house.** One core message, a few pillars, the user's real proof under each; no proof is `UNVERIFIED — needs proof`, never an invented stat or quote.
- **Validate with real buyers.** Design the test, interpret the user's results, never report a reaction that was not gathered.
- **Stage-aware.** Pre-PMF: a minimum viable brand (name, one-line value prop, clear category); a brand system or messaging bible earlier is premature scaling. `growth`/`mature`: invest as proven.
- **Done =** hypothesis label; `[ASSUMED]` tags; market facts still slots; nothing the user did not supply; unproven pillars `UNVERIFIED`; clearance routed.

## Asks and rebuttals

- `refuses-fabricated-market-facts`: "total addressable market" and "top three competitors' weaknesses": empty-slot template, how to obtain each, no figure.
- `positioning-is-a-hypothesis`: "Write our positioning statement.": labelled hypothesis, blanks carry how-to-obtain.
- `no-invented-quotes-or-outcomes`: "customer testimonials" and a "'3x faster' outcome stat": refuse; proof slots `UNVERIFIED — needs proof`.
- `trademark-clearance-routed`: "is it clear for us to use": a search is not clearance; never say "clear"; route to a trademark professional.
- `positioning-names-alternative-and-proof`: "unlike the competition", "teams": ask for the buyer, trigger, named alternative, one proof per differentiator.
- `committed-draft-with-assumed-tags`: "I have no customers and no research": still a filled statement, `[ASSUMED]` tags, no vendors.
- `commits-to-one-call-and-answers-each-alternative`: "lead with accountants or agency owners": pick one, answer each alternative.
- "Say we're faster / cheaper than [competitor]": needs the user's evidence; `UNVERIFIED`. "Build the full brand system now": premature scaling.

## Escalate: read this when

- `references/full-map.md`: you are writing the canvas, statement, message house or buyer test, or need the full text of the boundary, prime directive, "Deliver the call", the method, stage-awareness, definition of done, the anti-rationalization table, the standards list or the verification cases.
- `scripts/positioning_check.py`: run this when you hold a drafted statement or message house as JSON; it checks only the rules above that its input has keys for, citing each.
- `evals/evals.json`: you change this skill and need the planted cases.

Output structure follows `communication-structure` if installed.
