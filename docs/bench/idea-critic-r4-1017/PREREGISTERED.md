# Round 4 preregistration: idea-critic against its rival (written 2026-10-17, before any held-out scenario or arm generation)

Scope: the `idea-critic` skill only. Round 3 (`../exec-round3-1017`) reverted its candidate (0.487, lower bound not above 0.5). This round starts from the repo's current `SKILL.md` (v0), reads the round-3 loss reasons for a root cause, tests up to three one-spot edits on a tune split, and runs the best one once on a fresh held-out set. Only PCSS models are called. The method (generator, three judges, both orders, strict agreement, majority, bootstrap) is round 2/3's, reused unchanged through `../exec-1017/bench.py` and `bench2.py`; `bench4.py` only redirects the output directory and adds the privacy screen and the rival-once guard below.

## Root cause (read from the round-3 judge records, `../exec-round3-1017/judge4/idea-critic/`, plus the generations)

Reasons in the votes the rival won (14 of 40 for v0, 11 of 40 for the round-3 candidate), and three side-by-side generations:
1. The rival wins on a staged, capped first step: a stated dollar and week cap plus a pass bar that releases the rest ("if the pilot shows X, greenlight the remainder"). Perun's answers more often end in a go-if with several open conditions, or in a flat no-go. Judges call a flat no-go "less actionable" (round-3 candidate scenarios h24 and h29).
2. The rival's kill trigger is an operating ratio or threshold checked at a dated checkpoint inside the cap; Perun's is a post-launch or post-signature outcome that fires late, or one the plan as stated already trips.
3. Figure wording (error, math, arithmetic, recalculation) appears in 9 of the 14 v0 loss reasons and 9 of 11 candidate loss reasons; pilot, sprint, phase or cap wording appears in 11 of 14 and 9 of 11 (keyword counts over the winning-side reasons, so a lead, not a proof). The round-3 edit, a mandatory opening `Figures:` line and a forced `no-go as written`, left the figure losses unchanged (9 of 11) and did not move the result: in h24 the candidate's recompute was itself wrong (it read "1,200 additional" as a monthly claim), it led with that false alarm and a flat no-go, and lost to a capped pilot that unedited v0 also proposed (v0 did not lose h24). The rival also catches real slips Perun repeats (h17, h22, h37).
Conclusion: two gaps, the shape of the closing decision (cap, pass bar, in-cap checkpoint) and figure correctness with the arithmetic shown, not a mandatory line that can raise a false alarm. Candidates test each separately and together.

## Candidates (string substitutions on the current `SKILL.md`; built by `mk4.py` into `prompts/`; text as tested)

- `cA` (step 6 only): where the plan can be staged, the call is a capped first tranche (one hard cap on spend and weeks, plus the pass bar that releases the rest); the kill tripwire is observable, checked inside the cap, with value, checkpoint date and action, and is not already tripped by the plan as stated.
- `cB` (step 5 only): a figure mismatch is the first finding, with the corrected number and its arithmetic, and a figure that reconciles is not flagged. No required line.
- `cC`: `cA` plus `cB`.

## Selection (tune, n=10, selection only)

Scenarios 01-10 of the earlier `idea-critic` set (`../exec-1017/scenarios/idea-critic.json`), rival generations reused (made once). Arms v0, cA, cB, cC, same three-judge both-order strict-agreement majority. Choose the candidate with the highest tune win rate; ties go to the shorter edit (fewer bytes); if the best candidate is below v0 on tune, no candidate is taken forward and only the bench ships. The choice is appended to `PREREGISTERED-CHOICE.md` and hashed before any held-out generation.

## Held-out test (run once)

- 40 fresh scenarios, `scenarios4/idea-critic-h4.json` (ids h01-h40), written by `gpt-oss_120b` at temperature 0.9 with the unchanged writer briefs from 40 new fictional settings in `prompts/seeds4.txt`. The settings (and their company names) were checked by grep not to appear anywhere under `docs/bench/` outside this directory, so they are disjoint from every earlier set. A generated scenario is regenerated (up to four tries) when it is outside 100-280 words or when the repo's own privacy gate (`scripts/ci-gates.sh privacy`, committed and local banlists) hits it; this rule is fixed here and applied by the driver, so no scenario text is read or edited by hand.
- Each RIVAL answer is generated exactly once, before any arm runs (`bench4.py rival h4`); its sha256 is frozen in `RIVAL-sha256-h4.json` and `run` refuses to start if any rival file is missing or changed. Both arms are judged against these same files (this fixes the round-3 driver race).
- Arms: the chosen candidate and v0 (unedited current `SKILL.md`) on every scenario; the rival is `../exec-1017/prompts/rival_idea-critic.txt` run by the same generator.
- Generator Qwen3.5-397B-A17B (never a judge). Judges DeepSeek-V4-Flash, GLM-5.2 (thinking off), MiniMax-M2.5, each in BOTH orders; a judge's verdict counts only when both orders agree (else tie); the majority of three decides (else tie, 0.5).
- Score per scenario 1 / 0.5 / 0; bootstrap 10,000 resamples, seed 1, percentile, over scenarios. Slot-1 rate per judge is reported.
- Keep rule: keep the edit only if the 95% lower bound is above 0.5 AND the candidate's win rate is at least v0's on the same set. Otherwise revert the edit and ship the bench only.
- Known weaknesses: judges and generator are open models on one hosting cluster; the answer is a system-prompt-only arm (no references, tools or scripts); ties count 0.5 so lifts are mostly tie-to-win conversion; one run per arm; API nondeterminism near 0.01-0.1; tune at n=10 is a weak selector.
