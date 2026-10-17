# Preregistration: agentic-delivery round 3, root-caused candidates, tune then held-out (2026-10-18)

Frozen with `SHA256-frozen.txt` and a timestamped `preregistered` line in `ledger.jsonl` before any ticket, plan or judge record of this round exists. All model calls go to the PCSS endpoint ($0, no paid call).

## Why

Round 2 (clean replication, 40 tickets) showed the unedited skill at 0.562 [0.487, 0.637] against Superpowers and the round-1 edit at +0.025 paired, lower bound -0.075: no shipped win. Round-2 judge records kept only the verdict, so the root cause was read from the plans of the two tickets Superpowers won outright and from word counts over all 40 plans per arm:

- Every `v0` and `ship` plan (40 of 40) uses the skill's internal gate numbers (G1, G4, G5, ...) and about half name the Conductor/Product Analyst hats; no Superpowers plan does. The plan is addressed to a requester, so the jargon is scaffolding they did not ask for, and the round-1 wording ("not role titles or gate numbers") did not stop it.
- The `v0` plan adds ceremony the ticket's facts do not call for (a CI-optimization lane that proposes skipping integration tests on a ticket that stresses a flawless fallback; a database migration lane on a ticket that only needs a serializer change, in a repo where a migration rollback is a four-hour restore) and defers each ambiguity to a "spec freeze" gate. The Superpowers plan narrows scope to avoid the irreversible step and rules on ambiguities.

These are posture and contract differences (what the plan is anchored on, how it treats irreversibility and open questions), not wording preferences. Three small candidate edits follow; each replaces the round-1 "Plan answers" paragraph at the same anchor, reuses round 1's behavior-neutral trims plus one more, and ends no larger than origin/main's `SKILL.md` (size budget respected, no raise).

## Candidates (`prompts/c1.txt`, `c2.txt`, `c3.txt`; `prompts/v0.txt` = origin/main `SKILL.md`)

- c1, constraints first: open from the ticket's binding facts, add no role, gate or sign-off the facts do not call for, never skip or weaken a check or approval to save time or cost, no hat names or G-numbers.
- c2, irreversibility and rollback: find what the ticket does not need but could break irreversibly and plan around it, give each lane an owner and start condition, date steps back from the deadline, rollback per layer with trigger and decider, costly CI once per candidate SHA.
- c3, rulings: settle each ambiguity with a ruling (choice, why, cost if wrong) instead of a question or spec-freeze gate, list only true human gates with who, by when and a safe default, no hat names or G-numbers.

## Design

- Tickets: 70 new tickets `h3-01`..`h3-70` from 70 new archetypes (`prompts/seeds.txt`; word Jaccard against all 96 prior archetypes at most 0.22, checked before this freeze). Written by Qwen3.5-397B-A17B with the round-0 writer brief. `h3-01`..`h3-10` are the tune split, `h3-11`..`h3-70` the held-out split. Disjoint from `delivery-1017`, `delivery-r1-1017` and `delivery-r2-1017` by id (namespace `h3-`) and by text: `prior/old_tickets.json` holds all 120 earlier tickets and `bench.py tickets` rejects and redraws (up to 6 times, before any plan exists) any new ticket whose title equals a prior title or whose word 4-gram Jaccard with any prior or earlier new ticket is at least 0.25. Output, judge and result directories are per split (`tune/`, `held/`). Tickets are frozen by a `tickets_frozen` ledger line before any plan is generated.
- Arms: `sp` = Superpowers text (`../delivery-1017/prompts/sp.txt`); `v0`; `c1`..`c3`. Generator Qwen3.5-397B-A17B, temperature 0.7, unseeded, 2500 max tokens, one plan per arm per ticket, round-0 generation task (600-word cap), no tools.
- Judge: prompt v2 from `scripts/rival_eval.py` (`JUDGE_SYSTEM`), imported unchanged; DeepSeek-V4-Flash with thinking, GLM-5.2, gpt-oss_120b, each in both orders; the generator is never a judge. Records are write-once and now also keep the judge's raw analysis.
- Tune (n=10, selection only, no claim): all five arms plans, each of `v0`, `c1`, `c2`, `c3` judged against `sp`. Selection metric `soft` = mean over every judge pick (10 tickets x 3 judges x 2 orders) of arm versus `sp`, because strict agreement leaves most of 10 tickets at 0.5. The candidate with the highest `soft` is the finalist (ties: the larger byte saving). If no candidate beats `v0` on `soft` the highest one still advances; the held-out decides. The selection is written to the ledger (`selected`) with its hash before any held-out plan is generated.
- Held-out (n=60, `h3-11`..`h3-70`): arms `sp`, `v0`, finalist only, generated after `selected`. Scoring: per judge, a ticket is a win or loss only if both orders agree, else 0.5; per ticket, a win or loss needs at least 2 of 3 judges, else 0.5. Win rate is the mean over 60 tickets; 95% CIs are percentile bootstrap over tickets (10000 resamples, seed 1). The paired difference is the bootstrap of per-ticket (finalist minus `v0`) majority scores. Judge slot-1 rates are reported as a health metric.

## Decision rules (fixed now)

1. SHIP the finalist's `SKILL.md` text (plus one eval and a `changelog.d` fragment) only if the paired finalist minus `v0` 95% CI lower bound is above 0. Otherwise `SKILL.md` stays at origin/main and only the bench is committed.
2. A superiority claim over Superpowers needs the finalist's win rate against `sp` to have a CI lower bound above 0.5. Without it no such claim is made, even if rule 1 ships.
3. Reported plainly whichever way it falls. No arm, ticket or judge record is dropped, edited or regenerated after seeing a result; a failed call (nothing written) may be re-run. The tune split and the candidates are not re-opened after `selected`.

## Caveats declared in advance

Generator sampling is unseeded; a re-run differs. Judges are position-biased (round 2 slot-1 rates 0.65 to 0.88), so many tickets stay 0.5 under strict agreement and power is limited even at n=60. A failed rule 1 means "not shown", not "shown harmful". Arms run without tools, so value in scripts or references is not measured. The candidate paragraph also carries the same behavior-neutral trims as round 1, so a finalist versus `v0` contrast includes them.
