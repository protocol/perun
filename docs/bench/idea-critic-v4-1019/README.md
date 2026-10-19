# idea-critic V4 (decide first, then attack), preregistered held-out bench (2026-10-19)

BLUF: **LOSS by the frozen guardrail, nothing shipped.** V4 puts the model's own call first (`First call: GO|NO-GO`) and lets the attack flip it only through a named blocker. On 30 fresh held-out cases it cut false-NO-GO on good decisions from 0.911 (current skill, V0) to 0.378 and raised accuracy from 0.544 to 0.778, paired **+0.233 [0.078, 0.400]**, so the CI condition of the keep rule is met. But V4 approved a bad decision in 3 of 45 calls (false-go 0.067) where V0 approved none, and the preregistered rule needs exactly zero. The verdict is LOSS and `.claude/skills/idea-critic/SKILL.md` is unchanged.

## Result (Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off, 30 cases x 3 samples)

| Arm | Accuracy [95% CI] | False-go [95% CI] | False-no-go | Invalid | Completion tokens per call |
|---|---|---|---|---|---|
| V0, current skill | 0.544 [0.378, 0.722] | 0.000 [0.000, 0.000] | 0.911 | 0 | 408 |
| V4, decide first then attack | 0.778 [0.633, 0.911] | 0.067 [0.000, 0.178] | 0.378 | 0 | 477 |
| BASE, no skill | 0.644 [0.478, 0.800] | 0.000 [0.000, 0.000] | 0.711 | 0 | 331 |

Paired differences (per-case bootstrap, 10,000 resamples, seed 1):

- V4 minus V0 accuracy: +0.233 [0.078, 0.400]. Lower bound above 0, but the false-GO guard fails, so the frozen `verdict()` returns **LOSS**.
- V4 minus BASE accuracy: +0.133 [0.011, 0.278]. V4's false-go minus BASE's (descriptive only, does not decide): +0.067 [0.000, 0.178].

The three false GOs: `business-computer-1980` (2 of 3 samples) and `small-luxury-1981` (1 of 3). No other bad-decision call was approved by any arm. V4's first call equalled its final decision in all 90 calls (28 good GO, 17 good NO-GO, 3 bad GO, 42 bad NO-GO), so, as in dev, the attack steps never changed a decision; V4 is the model's gut call, now protected from the skill's blocking bias, with the attack and kill criteria appended.

## What was tested and why

V0's false-NO-GO comes from the skill's own framing: its attack steps produce generic objections (price, unproven demand, a cheaper or staged alternative, a missing kill criterion) and the model then treats them as the verdict. V2 and V3 edited step 6 and lost their held-out runs on the guardrail. V4 changes the order: a first call before any attack, a preamble saying the attack adds to judgment and never raises the bar above it, a blocker definition (a fact in hand that shows the plan fails; risks, missing pilots, caps or metrics and cheaper alternatives that do not reach the same upside are not blockers), step 2 reduced to "must beat do nothing", and step 3 limited to a stated north star. `PREREG.md` has the diagnosis, all three dev wordings with their numbers (v4a, v4b, v4c; v4b frozen as V4) and the decision rule.

## Honesty notes

- Preregistration: `PREREG.md`, the corpus, the V0 and V4 skill texts, the driver, the shared scorer and `prior-v3-ids.json` are hashed in `SHA256-frozen.txt`; the first line of `ledger.jsonl` is the `preregistered` event carrying the hash of that file, written before any held-out call. `shasum -a 256 -c SHA256-frozen.txt` passes. The held-out run was executed once with no failed calls. `PREREG.md` predicted the guard was the likelier failure, and it was.
- Dev numbers in `dev/` are optimistic: three wordings were tried on 88 earlier cases (V4 accuracy 0.773 against V0 0.621, with 1 false GO in 132 calls); the V3 held-out set is spent and was not used as dev.
- The held-out cases share no id or source URL with any earlier idea-critic set, including V3's; `scripts/test_idea_critic_v4.py` checks this.
- Do not read the BASE row as the earlier benches' BASE: here no skill scored false-no-go 0.711, against 0.311 on V3's set, so this set is harder for the unskilled model than V3's, and V4's gain over BASE is specific to this set. The same-set comparison is the valid one.
- Limits: 30 cases give wide intervals; one non-Claude model, not the Claude host the skill ships for; cases are written by the same author in the same genre as the training sets; models may partly recall famous outcomes; the key is a documented real-world result, not proof the decision was right at the time. The frozen rule counts the three false GOs; no case was excluded after the run.

## What this means

On this fresh set V4 beats both the current skill and no skill on accuracy with a CI that excludes zero, and it fails only the zero-false-GO bar (3 of 45 calls). A zero-false-GO guardrail over 45 calls is a very tight rule for a model that, with no skill, itself approves about 1 to 2% of bad decisions on earlier sets; whether to relax it is an owner decision, not one this bench can make; BASE made 0 of 45 false GOs on this set, so a rule of no worse than BASE would fail here as well. Any next attempt needs a new held-out set; this one is spent.

## Reproduce

```
PCSS_ENV=/path/to/env-with-PCSS_KEY python3 bench_v4.py heldout report Qwen3.5-397B-A17B
python3 ../../../scripts/test_idea_critic_v4.py
```

`run MODEL` generates only missing outputs; outputs are in `outputs/<model>/<arm>/`, call records in `ledger.jsonl`. `V4_VARIANT=<name> bench_v4.py dev run|report MODEL` does the same for a dev wording in `dev/<name>/`; `dev/mk_variants.py` rebuilds the dev texts from V0.
