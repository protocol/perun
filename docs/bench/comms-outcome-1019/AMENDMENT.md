# Amendment A1 (2026-10-19), written after the 40 tune scenarios were generated and before any arm, reader or grader call

Finding: reading the first tune scenarios showed gold answers that held a figure or weekday the notes never state (a derived difference, or a number misquoted by the writer), which would grade a correct message as wrong in every arm. bench.py is frozen, so the fix is a separate audit.

- audit.py rejects a scenario whose gold decision, action, owner, deadline or number holds a numeric token or weekday absent from its notes (the same normalisation as the invented-figure guardrail). 4 of the 40 tune scenarios failed (tune03, tune04, tune20, tune22) and were dropped; 4 replacements were written with `audit.py tune --fill 40` under the same writer brief and checks, with a fresh seed and unused (kind, domain) pairs. Kind balance after the audit is pr 10, incident 9, exec 8, status 7, decision 6.
- The same audit (drop, then fill to n=30) is applied to the held-out scenarios before they are hashed and before any held-out arm call.
- No arm output, reader answer or grade existed when this amendment was made. audit.py, this file and scenarios_tune.json are appended to SHA256-frozen.txt with a ledger event before the first tune arm call.
