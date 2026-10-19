# idea-critic V3 blocker test plus edge gate, preregistered held-out bench (2026-10-19)

BLUF: **LOSS by the frozen guardrail, nothing shipped.** V3 keeps V2's blocker/risk split and adds an edge gate: GO also needs a stated fact showing why this plan, from this proposer, can win (brand, size, money, being first or fear of falling behind do not count). On 30 fresh held-out cases it raised accuracy over the current skill from 0.567 to 0.678, paired **+0.111 [-0.000, 0.233]**, but it approved a bad decision in 3 of 45 calls (false-go 0.067) where the current skill approved none. The preregistered rule needs zero false GOs and a CI lower bound above 0; both fail, so the verdict is LOSS and `.claude/skills/idea-critic/SKILL.md` is unchanged. No skill at all (BASE) beats both prompts on these cases: 0.833, with 1 false GO in 45 calls.

## Result (Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off, 30 cases x 3 samples)

| Arm | Accuracy [95% CI] | False-go [95% CI] | False-no-go | Invalid | Completion tokens per call |
|---|---|---|---|---|---|
| V0, current skill | 0.567 [0.400, 0.733] | 0.000 [0.000, 0.000] | 0.867 | 0 | 405 |
| V3, blocker test plus edge gate | 0.678 [0.544, 0.800] | 0.067 [0.000, 0.178] | 0.578 | 0 | 445 |
| BASE, no skill | 0.833 [0.700, 0.944] | 0.022 [0.000, 0.067] | 0.311 | 0 | 332 |

Paired accuracy differences (per-case bootstrap, 10,000 resamples, seed 1):

- V3 minus V0: +0.111 [-0.000, 0.233]. The lower bound rounds to zero from below, so it is not above 0; the guardrail also fails (V3 false-go 0.067). The frozen `verdict()` returns **LOSS**.
- V3 minus BASE: -0.156 [-0.267, -0.056]. V3 is worse than no skill.

The three false GOs are two of three samples on `camera-glasses-2016` and one of three on `online-console-1998` (BASE also said GO once on that case). One `camera-glasses-2016` sample wrote `Edge: NONE` and still decided GO, so the model does not reliably follow its own gate.

## What was tested and why

V2 (`../idea-critic-v2-1019/`) cut the current skill's NO-GO on good decisions but let an occasional bad plan through: in each of its false GOs the model filed as a mere risk a fact the proposal states as already true and that removes the plan's own route to its upside. V3 (`prompts/skill_v3.txt`) changes only step 6 of V2: such a stated negative becomes a blocker, a missing term, clause, pilot or metric becomes a risk, and GO needs a named edge, written as an `Edge:` line next to `Blockers:` and `Risks:`. `PREREG.md` has the full diagnosis, all four dev wordings with their numbers, and the decision rule.

## Honesty notes

- Preregistration: `PREREG.md`, the corpus, the V0 and V3 skill texts, the driver and the shared scorer are hashed in `SHA256-frozen.txt`; the first line of `ledger.jsonl` is the `preregistered` event carrying the hash of that file, written before any held-out call. `shasum -a 256 -c SHA256-frozen.txt` passes. The held-out run was executed once with no failed calls.
- Dev (training) numbers are in `dev/` and are optimistic. Four wordings were tried on the 88 earlier cases; none reached zero false GOs while beating V0 (V3a 2, V3b 13, V3c 8, V3d 3 false GOs in 132 calls). V3d was frozen as V3, and `PREREG.md` stated before the run that a guardrail LOSS was the likely outcome (about 0.35 chance of no false GO in 45 calls at its dev rate).
- The held-out cases share no id or source URL with any earlier idea-critic set; `scripts/test_idea_critic_v3.py` checks this against the three earlier corpora and every English Wikipedia URL elsewhere in the repository.
- Limits: 30 cases give wide intervals; one non-Claude model, not the Claude host the skill ships for; cases are written by the same author in the same genre as the training set; models may partly recall famous outcomes; the key is a documented real-world result, not proof the decision was right at the time.

## What this means

V1 tied the current skill in an exploratory bench, and V2 and V3 have now lost their preregistered held-out runs on the guardrail; on each of the four Qwen sets (outcome, calibration, V2 and V3 held-out) no skill at all scored higher than every idea-critic version tested on it. Every wording that approves more good plans also lets some bad ones through at this sampling temperature; a zero-false-GO bar on 45 calls is not met by prompt wording alone. A next attempt should question the method, for example letting the skill hand ordinary go/no-go calls to the model's default judgment, rather than add more rules to step 6, and it needs a new held-out set; this one is spent.

## Reproduce

```
PCSS_ENV=/path/to/env-with-PCSS_KEY python3 bench_v3.py heldout report Qwen3.5-397B-A17B
python3 ../../../scripts/test_idea_critic_v3.py
```

`run MODEL` generates only missing outputs; outputs are in `outputs/<model>/<arm>/`, call records in `ledger.jsonl`. `bench_v3.py dev run|report MODEL` does the same for the dev split in `dev/`.
