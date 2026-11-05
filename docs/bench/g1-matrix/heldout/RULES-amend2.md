# G1 held-out rules, amendment 2

This amends `RULES.md` and `RULES-amend1.md`. It is committed before any `h10c` case exists and before the third API10 detector is frozen.

## Amendment 2 (2026-11-05)
- Amendment 1 sent a second API10 fail to the owner. The second detector (`93de177bb`) failed `h10b`: precision 0.625, recall 0.667. The owner delegated the decision to the decision council and the evil-twin check, which chose one third attempt. No threshold changes.
- `h10` and `h10b` are development sets from now on and no longer count as held out.
- One third detector is frozen and tagged (`g1-frozen/api10-v3`) before a new set, `h10c`, is first read. It is scored once on `h10c`, under `RULES.md` unchanged. The API10 scope line does not change.
- `h10c` is written by a fresh agent with the same seed as `h10b` (`RULES.md`, both amendments, the OWASP page and the scope line). That agent never sees `h10`, `h10b`, any result or any detector. Two authoring rules are added, because `h10b` had a negative that contained a positive shape: every negative must be clean in every respect, so it has no shape that any positive case is labelled for, and every positive case carries exactly one positive shape.
- If the third detector's precision on `h10c` is below 0.7, API10 stays unstatused and API:2023 fails G1 until the owner reopens it. There is no fourth attempt.
- API10 is audited only after a detector passes.
