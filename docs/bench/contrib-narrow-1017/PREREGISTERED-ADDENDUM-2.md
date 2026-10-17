# Addendum 2 (tune finished; edit frozen before the held-out set was drawn)

Tune set (n = 10, never a verdict; every iteration regenerates all arms into a new results dir, so v0 differs between iterations by sampling noise alone: 0.40 against 0.25 for the same text):

| Iteration | Judge | Slot-1 rate | v0 win rate | Edit win rate | Paired diff [95% CI] |
|---|---|---|---|---|---|
| tune-it1 | GLM-5.1 | 0.475 | 0.4 | 0.35 | -0.05 [-0.3, 0.25] |
| tune-it1 | GLM-5.2 | 0.55 | 0.4 | 0.3 | -0.1 [-0.35, 0.1] |
| tune-it1 | gpt-oss_120b | 0.625 | 0.35 | 0.3 | -0.05 [-0.2, 0.1] |
| tune-it2 | GLM-5.1 | 0.475 | 0.25 | 0.6 | 0.35 [0.1, 0.6] |
| tune-it2 | GLM-5.2 | 0.5 | 0.35 | 0.45 | 0.1 [-0.35, 0.5] |
| tune-it2 | gpt-oss_120b | 0.744 | 0.2 | 0.45 | 0.25 [0.05, 0.45] |

Iteration 1 was the narrowed text without an "Answer shape" section; its provenance block leaked the invented source ("Acme Corp production") into advice-only answers. Iteration 2 added "Answer shape" and made the block a hand-off artifact only. Two iterations used; no further tuning. The frozen edit is `frozen/contribution.v1.md` (sha256 in `SHA256-amend.txt`). Held-out generation follows, with the rule in `PREREGISTERED.md` unchanged.
