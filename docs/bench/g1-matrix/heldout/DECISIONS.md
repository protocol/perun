# Decision: API5 after its first detector was dropped (11-05 04:32)

Council options:
- A: build a second detector, using `h5` as its dev set, then write a fresh blind set `h5b` and score it once.
- B: a guided step plus a blind ablation for status (b).
- C: label API5 status (c).
- D: take it to the owner now.

Votes and reasons:
- B is unlikely to pass. The stripped arm passed every b2 case for API1 and API10 at this case size.
- C is dishonest, because function-level authorization is in static scope.
- D is premature, because A is cheap, uses no paid spend, and can be reversed.
- Result: A. There was no split.

Twins on A:
- Failure: v2 could fit `h5`'s guard shapes and then miss `h5b`'s.
  - Mitigation: one attempt only. A fail goes to the owner, not to a third try.
  - The scope line stays frozen, so the scope can't be narrowed to fit the detector.
- Irreversibility: none. It is local work plus subagent tokens, and the sets are committed whatever the outcome.
- Hidden cost:
  - (1) Guard-reading logic grows `route_auth_map.py`. Mitigation: keep it under `--privileged` only, keep the default output cmp-identical, and pin it with seeded tests.
  - (2) Precision can be gamed by reporting less. Mitigation: state recall beside the label; the audit judges "well enough within its stated scope".
- Verdict: no unmitigable BLOCK, nothing irreversible, so no owner surface.

Order: after the API3 audit returns ACCEPT (a REJECT re-plans all four items first). Commit the amendment, then the v2 detector lane (dev = `h5` plus seeded tests, never reading `heldout-api5b-*`), then freeze it, then the `h5b` author lane, then score once.

# Decision: API10 after its first detector was dropped (11-05 05:20)

Council: the same options as API5 (A: a second detector with `h10` as its dev set plus a fresh `h10b` set scored once; B: guided or (b); C: (c); D: owner now).
- B: an earlier b2 round already showed API10 is not (b).
- C: dishonest. Data flow from a response into a sink is in static scope.
- D: premature, because A is cheap and reversible.
- Result: A. There was no split.

Twins on A:
- Failure: v2 might fit `h10`. The same mitigations as API5: one attempt, a frozen scope line, and a fail goes to the owner.
- Irreversibility: none.
- Hidden cost: the older `sqli`, `ssrf`, `command-injection` and `path-traversal` rules already fire on response data in some cases. If v2 adds response sources to those rules, the product would show the same finding twice. Mitigation: v2 keeps its own rule ids, and its seeded tests check that no case gets a duplicate report on one line from the older rules.
- Verdict: no unmitigable BLOCK and nothing irreversible, so the owner does not need to see this.

# Decision: the auditor is unavailable (11-05 05:36)

Finding: every call to the pre-declared auditor endpoint, on both of its models, returns HTTP 429 with the type `budget_exceeded` and a maximum budget of 0. The budget is spent; this is not a rate limit, so waiting does not clear it.

Council options:
- A: author `h5b` now, and `h10b` once API10's second detector is frozen, and score each once, before the API3 audit. Ask the owner for an auditor in the meantime.
- B: hold all held-out work until an auditor is available.
- C: take the whole plan to the owner now.

Votes and reasons:
- B stalls for an unknown time. The audit-first order above was chosen so that a REJECT on API3 would not waste new sets. A set written now stays valid under unchanged rules, and a re-plan can add a new one.
- C: the auditor needs the owner (spend or a key for another vendor), but the set work does not.
- Result: A, plus one owner question about the auditor. There was no split. This replaces the order in the two decisions above.

Twins on A:
- Failure: appending the amendment to `RULES.md` would change the API3 audit prompt, which embeds `RULES.md`. Mitigation: the amendment is its own file, `RULES-amend1.md`. After the commit, the API3 prompt is rebuilt and compared byte for byte with the attempt-1 prompt.
- Irreversibility: none. It is local commits and subagent tokens.
- Hidden cost: if API3 is later rejected, the re-plan may make `h5b` and `h10b` moot, at a cost of about two author lanes. Accepted.
- Verdict: no unmitigable BLOCK and nothing irreversible. Only the auditor gap goes to the owner.
