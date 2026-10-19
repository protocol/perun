# idea-critic V2 blocker test, preregistered held-out bench (2026-10-19)

BLUF: **LOSS by the frozen guardrail, nothing shipped.** V2 sorts every objection into a blocker (a fact in hand that shows the plan fails) or a risk (anything not yet shown) and lets only blockers decide the call. On 28 fresh held-out cases it raised accuracy over the current skill from 0.607 to 0.762, paired **+0.155 [0.036, 0.286]**, but it approved one bad decision (1 of 42 calls, false-go 0.024) where the current skill approved none. The preregistered rule needs false-go not worse, so the verdict is LOSS and `.claude/skills/idea-critic/SKILL.md` is unchanged. The current skill still loses to no skill at all (0.607 against 0.821) by saying NO-GO to 79% of good decisions.

## Result (Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off, 28 cases x 3 samples)

| Arm | Accuracy [95% CI] | False-go [95% CI] | False-no-go | Invalid | Completion tokens per call |
|---|---|---|---|---|---|
| V0, current skill | 0.607 [0.452, 0.762] | 0.000 [0.000, 0.000] | 0.786 | 0 | 404 |
| V2, blocker test | 0.762 [0.631, 0.881] | 0.024 [0.000, 0.071] | 0.452 | 0 | 444 |
| BASE, no skill | 0.821 [0.690, 0.929] | 0.000 [0.000, 0.000] | 0.357 | 0 | 339 |

Paired accuracy differences (per-case bootstrap, 10,000 resamples, seed 1):

- V2 minus V0: +0.155 [0.036, 0.286]. The accuracy half of the WIN rule holds; the guardrail does not (V2 false-go 0.024 against V0 0.000), so the frozen `verdict()` returns **LOSS**.
- V2 minus BASE: -0.060 [-0.167, 0.036]. V2 does not beat no skill.

The one false-go is a single sample (1 of 3) on a bad case about buying a blogging platform; the other two V2 samples on that case said NO-GO.

## What was tested and why

The earlier exploratory benches (`../../idea-critic-outcome-1019/`, `../../idea-critic-calibration-1019/`) showed the skill saying NO-GO to most good decisions while approving no bad one. Reading those transcripts, the wrong NO-GOs cite a cheaper or staged alternative, an "unproven" claim, or a pre-mortem story: risks, not facts showing the plan fails. V2 (`prompts/skill_v2.txt`) adds a blocker test to step 6, makes step 2 block only on an alternative that reaches the same upside, makes only a stated north star able to block in step 3, and requires a written `Blockers:` / `Risks:` sort before the decision. `PREREG.md` has the full design, the two dev wordings and the decision rule.

## Honesty notes

- Preregistration: `PREREG.md`, the corpus, both skill texts, the driver and the shared scorer are hashed in `SHA256-frozen.txt`; the first line of `ledger.jsonl` is the `preregistered` event carrying the hash of that file, written before any held-out call. `shasum -a 256 -c SHA256-frozen.txt` passes. The held-out run was executed once with no failed calls.
- Dev (training) numbers are in `dev/` and are optimistic: V2a tied V0 (+0.028 [-0.028, 0.078]); V2b, the frozen V2, scored +0.133 [0.061, 0.211] but already broke the false-go guardrail on dev (2 of 90 calls). The guardrail was kept as written.
- **Overlap found after the run.** `PREREG.md` states that no held-out case shares a source page with the training cases. That is wrong for one case: `teen-social-phones-2010` (key `bad`) covers the same 2010 decision as the training case `social-phone-2010` in `../../idea-critic-calibration-1019/corpus.json`. It was missed before the freeze; the disjointness test in `scripts/test_idea_critic_v2.py` caught it after the run. Excluding it (27 cases) gives V0 0.593, V2 0.753, BASE 0.815 and V2 minus V0 +0.160 [0.037, 0.284]; the false-go is on a different case, so the verdict is LOSS either way. `scripts/test_idea_critic_v2.py` pins this as the only allowed overlap.
- Limits: 28 cases give wide intervals; one non-Claude model, not the Claude host the skill ships for; cases are written by the same author in the same genre as the training set; models may partly recall famous outcomes; the key is a documented real-world result, not proof the decision was right at the time.

## What this means

The over-blocking is real and a blocker/risk split cuts NO-GO on good decisions from 79% to 45% on held-out cases, but on both splits the split also lets an occasional bad plan through, and V2 still does not beat no skill. A next attempt should keep the split and add a check that catches a plan whose own evidence contradicts its core claim, then be tested on a new held-out set; this one is spent.

## Reproduce

```
PCSS_ENV=/path/to/env-with-PCSS_KEY python3 bench_v2.py heldout report Qwen3.5-397B-A17B
python3 ../../../scripts/test_idea_critic_v2.py
```

`run MODEL` generates only missing outputs; outputs are in `outputs/<model>/<arm>/`, call records in `ledger.jsonl`.
