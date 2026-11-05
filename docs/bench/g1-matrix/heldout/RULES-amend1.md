# G1 held-out rules, amendment 1

This amends `RULES.md`. It is a separate file so that `RULES.md`, which every audit prompt embeds, stays byte-identical for the API3 and API1 audits. When API5 or API10 is audited, its prompt adds this file after `RULES.md`.

## Amendment 1 (2026-11-05, committed before any `h5b` or `h10b` case exists)
- API5's first detector (`00550ed93`) is dropped: its precision on `h5` was 0.55. `h5` is now a development set for a second API5 detector and no longer counts as held out.
- API5 gets one more attempt. A second detector is frozen before a new set, `h5b`, is first read. It is scored once on `h5b`, under these rules unchanged. The API5 scope line does not change.
- `h5b` is written the same way as `h5`: by a fresh agent with the same seed (`RULES.md`, this amendment, the OWASP page and the scope line). That agent never sees `h5`, the results or any detector.
- If the second detector's precision on `h5b` is below 0.7, API5 goes to the owner for a decision. It does not become status (c), because function-level authorization is not out of static scope.
- API5 is audited only after one of its detectors passes.
- API10's first detector (`25e958e3a`) is dropped: its precision on `h10` was 0.667. The same route applies to it: `h10` becomes a development set, one second detector is frozen before a new set `h10b` is first read, it is scored once, a fail goes to the owner, and the API10 scope line does not change.
