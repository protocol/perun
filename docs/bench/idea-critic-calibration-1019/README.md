# idea-critic calibration bench (2026-10-19)

BLUF: the calibration edit to `idea-critic` (V1) did not measurably cut over-blocking on 24 fresh, public, preregistered cases. On the primary model, accuracy moved from 0.708 (pre-fix, V0) to 0.764 (V1), a paired difference of +0.056 with a 95% CI of [-0.014, 0.139]. That is a TIE under the frozen rule in `PREREG.md`. The harm guardrail held: V1 approved no bad decision (false-go 0.000). V1 still scores below no skill (0.917) and below the rival skill text (0.889), and both gaps exclude zero. The fix is a small step in the right direction on a small sample, not a calibrated critic: it still says NO-GO to 47% of the good decisions (V0: 58%).

## Result (primary model Qwen3.5-397B-A17B, 24 cases x 3 samples, thinking off)

| Arm | Accuracy [95% CI] | False-go [95% CI] | False-no-go | Invalid | Completion tokens per call |
|---|---|---|---|---|---|
| V0, pre-fix skill | 0.708 [0.542, 0.861] | 0.000 [0.000, 0.000] | 0.583 | 0 | 402 |
| V1, fixed skill | 0.764 [0.625, 0.903] | 0.000 [0.000, 0.000] | 0.472 | 0 | 418 |
| BASE, no skill | 0.917 [0.806, 1.000] | 0.000 [0.000, 0.000] | 0.167 | 0 | 334 |
| RIVAL, rival skill text | 0.889 [0.806, 0.958] | 0.056 [0.000, 0.139] | 0.167 | 0 | 401 |

Paired differences in accuracy (per-case bootstrap, 10,000 resamples):

- V1 minus V0: +0.056 [-0.014, 0.139]. Verdict by the frozen rule: **TIE** (guardrail holds, interval includes 0).
- V1 minus BASE: -0.153 [-0.264, -0.056]. V1 loses.
- V1 minus RIVAL: -0.125 [-0.236, -0.028]. V1 loses.

## Secondary model gpt-oss_120b (reasoning on; not part of the verdict)

| Arm | Accuracy [95% CI] | False-go | False-no-go | Invalid |
|---|---|---|---|---|
| V0 | 0.403 [0.250, 0.556] | 0.000 | 0.944 | 14 |
| V1 | 0.444 [0.306, 0.583] | 0.000 | 0.833 | 18 |
| BASE | 0.611 [0.444, 0.778] | 0.000 | 0.750 | 1 |
| RIVAL | 0.569 [0.375, 0.750] | 0.000 | 0.861 | 0 |

V1 minus V0: +0.042 [-0.083, 0.139]. V1 minus BASE: -0.167 [-0.278, -0.069]. V1 minus RIVAL: -0.125 [-0.250, 0.000]. Same direction as the primary model: a small, non-significant gain over V0 and a loss to no skill. Unparseable calls count as wrong. The sampled invalid V0 and V1 outputs end with the skill's own JSON report and no `DECISION:` line, so this is skill-format drift against the bench's last-line contract; it depresses the two skill arms (14 and 18 of 72 calls) and not the others.

## The shipped text is not exactly the tested V1 (post-hoc, not preregistered)

V1 as tested is 16,483 bytes; the repo caps a skill core at 16,000. The shipped `SKILL.md` (V1T, `prompts/skill_v1t.txt`, 15,985 bytes) is V1 with 498 bytes of non-decision prose removed (a chat-voice pointer and duplicated Verification bullets); the two calibration sentences are unchanged. V1T was run once on the same held-out cases, primary model only (`bench_postfix.py`, `postfix/`, outside the verdict):

| Arm | Accuracy [95% CI] | False-go | Paired accuracy vs V1T |
|---|---|---|---|
| V1T, shipped | 0.792 [0.667, 0.903] | 0.000 | |
| V1 | 0.764 | 0.000 | V1T minus V1 +0.028 [-0.056, 0.125] |
| V0 | 0.708 | 0.000 | V1T minus V0 +0.083 [-0.014, 0.194] |
| BASE | 0.917 | 0.000 | V1T minus BASE -0.125 [-0.236, -0.028] |

Same picture: the interval against V0 includes zero (a TIE if it had been the preregistered arm), and the shipped text still loses to no skill. One sample of three per case; do not read +0.083 as an effect.

## What was changed (V1)

Two sentences in `.claude/skills/idea-critic/SKILL.md`, identified by reading the failing outputs of the first outcome bench (`../idea-critic-outcome-1019`):

- Step 2: the claim must beat *do nothing*; a safer, smaller or staged alternative is a note unless it dominates on the stated facts (was: must beat all three options).
- Step 6: no fatal flaw means GO; a risk the proposal already names, a high price, an unproven market, key-person or one-way-door exposure and a missing pilot are not fatal alone and become the GO's kill criteria and leading metric; a wrongly blocked sound plan costs as much as a wrongly passed one.

## Design and honesty notes

- Held-out set: 24 cases (12 key `good`, 12 key `bad`), each with a public Wikipedia source and a verbatim evidence quote fetched 2026-10-19, names removed from the prompt. Written and hashed before the first V1 edit, disjoint from the 36 tune cases. Same genre and same author as the tune set, so this tests new cases, not a new domain or author.
- Preregistration: `PREREG.md` and `SHA256-frozen.txt` fixed the corpus, both skill texts, the driver and the scorer; the first line of `ledger.jsonl` is the `preregistered` event carrying the hash of `SHA256-frozen.txt`, written before any held-out call. An earlier held-out start was set aside unread because the ledger line was missing (disclosed in `PREREG.md`).
- Dev numbers (`dev/`) are on the tune set and are optimistic: three V1 wordings were tried there, V1 scored 0.676 and 0.639 on two samples against V0 0.574 and no-skill 0.694. They are not evidence. The wording kept was the best of the three on the tune set; the held-out result above shows the gain mostly did not carry over.
- Limits: 24 cases give wide intervals (a true effect of about +0.05 cannot be separated from zero); two non-Claude models served from one free endpoint, not the Claude host the skill ships for; models may partly recall famous outcomes; the key is a documented real-world result, not proof the decision was right at the time. The RIVAL arm is reference only.
- The 36-case first bench was not preregistered and is superseded by this directory as the gated evidence for idea-critic calibration.

## Reproduce

```
PCSS_ENV=/path/to/env-with-PCSS_KEY python3 bench_calibration.py heldout report Qwen3.5-397B-A17B
python3 ../../../scripts/test_idea_critic_calibration.py
```

`run MODEL` regenerates missing outputs (it skips existing ones); outputs are in `outputs/<model>/<arm>/`, call records in `ledger.jsonl`.
