Executive-skill bench, 2026-10-17. Pre-registration: PREREGISTERED.md (frozen before any generation) and PREREGISTERED-ADDENDUM-1.md (GLM tiebreak thinking off, applied before the final baseline).

Result, held-out n=20, Perun win rate against the named rival (1 Perun, 0.5 tie, 0 rival), bootstrap 95% interval:
  skill              v0 (base)        v1 (after one edit round)   decision
  agentic-ceo        0.35 [0.15,0.55] 0.35 [0.15,0.55]            reverted
  idea-critic        0.30 [0.10,0.50] 0.35 [0.15,0.55]            reverted
  business-ops       0.50 [0.30,0.70] 0.60 [0.40,0.80]            reverted (lower bound not above 0.5)
  growth-analytics   0.55 [0.35,0.75] 0.75 [0.55,0.90]            kept (lower bound above 0.5)
  positioning        0.70 [0.50,0.90] 0.70 [0.50,0.90]            reverted (lower bound not above 0.5)
The tune split (n=10) baselines are in results-*-PERUN_v0-tune.json; edits were written from tune-split judge reasons only. Held-out reasons were not read before the keep decision.

Reproduce: `python3 -I bench.py run SKILL ARM SPLIT` then `report SKILL ARM SPLIT` (ARM PERUN_v0 or PERUN_v1; needs PCSS_KEY in the repo-root .env or PCSS_ENV). Generations, judge records and every call (tag, model, seconds, token usage, no text) are in outputs/, judge/ and ledger.jsonl.

Not committed: prompts/rival_positioning.txt. Its source is licensed CC BY-NC-SA 4.0, so only its hash is recorded (PREREGISTERED.md lists the two source-file hashes; the concatenated local file hashed c3ec16bc1ef570f2d7a897c0b461c07d5ff055db3297ac8a7558cf505ba08bb1). Fetch the two named SKILL.md files from the pinned tarball to re-run the positioning arm.

Caveats, all of which weaken the claim:
- Judges are open models from the same hosting cluster as the generator, not an independent human or a different vendor. DeepSeek-V4-Flash shows a strong first-position bias; the swapped second pass and the GLM tiebreak are there to absorb it.
- Re-judging identical generations moved win rates by about 0.1 (API nondeterminism). With n=20 a score of roughly 15 wins is needed to clear the bar, so 0.60 against 0.55 is within noise and the one kept result (0.55 to 0.75, lower bound exactly 0.55) is a thin pass from a single run.
- Both arms are system-prompt only: the rival's text and the skill's SKILL.md, with no references, scripts or tools. This understates Perun's references and overstates nothing for the rival, which also runs without tools.
- bench.py changed by one line after the freeze (addendum 1); hashes are in SHA256-frozen.txt and SHA256-after-addendum-1.txt.
- The kept growth-analytics SKILL.md carries one extra verification bullet and an eval id added after the v1 run (prompts/perun_growth-analytics_v1.txt is the text as tested, without that bullet). The four reverted edits are preserved only as prompts/perun_<skill>_v1.txt.
- Pre-edit, no Perun skill beat its rival on the bar. This bench does not support a claim that these skills beat their rivals; it supports one measured improvement and four honest non-improvements.

ROUND 2 (2026-10-17): agentic-ceo, idea-critic, business-ops, positioning. Procedure and amendments: PREREGISTERED-ADDENDUM-2.md (frozen set hashes in SHA256-round2-frozen.txt; bench2.py and addendum hashes after amendment 2a in SHA256-round2-amendment-2a.txt).
Method: three decision-memo variants per skill (prompts/perun_<skill>_r2{a,b,c}.txt, built by mkvariants.py), compared on the tune split; the best was run once on a NEW held-out set (scenarios2/, 20 scenarios per skill, ids h01-h20), with v0 on the same set as a reference. Judges: DeepSeek-V4-Flash, GLM-5.2 (thinking off), MiniMax-M2.5; every pair judged in BOTH orders by each judge; a judge's verdict counts only when both orders agree (else tie); the majority of the three decides (else tie, 0.5). Records: judge4/, results4-*.json. judge3/ and results2-* are a superseded single-order pass, not used for any decision.

Tune (n=10, selection only), win rate v0 / r2a / r2b / r2c: positioning 0.50 / 0.40 / 0.55 / 0.55; business-ops 0.40 / 0.70 / 0.55 / 0.50; idea-critic 0.35 / 0.60 / 0.55 / 0.30; agentic-ceo 0.65 / 0.50 / 0.70 / 0.65.

Held-out round 2 (n=20), Perun win rate against the rival, bootstrap 95% interval:
  skill          v0 (reference)       chosen variant           decision
  agentic-ceo    0.450 [0.325,0.575]  r2b 0.625 [0.475,0.750]  reverted (lower bound 0.475 not above 0.5)
  idea-critic    0.275 [0.150,0.400]  r2a 0.325 [0.200,0.475]  reverted
  business-ops   0.475 [0.300,0.625]  r2a 0.525 [0.375,0.675]  reverted
  positioning    0.475 [0.325,0.650]  r2b 0.500 [0.350,0.650]  reverted
No round-2 variant cleared the keep rule, so the four skill texts stay at the base text. Round-2 variants are preserved only as prompts/perun_<skill>_r2{a,b,c}.txt.

Slot-1 rate per judge over all its calls on the held-out runs (both orders, so an unbiased judge would sit near 0.5), ranges across the eight runs: DeepSeek-V4-Flash 0.525-0.725, GLM-5.2 0.600-0.825, MiniMax-M2.5 0.675-0.800. Every per-run value is in results4-<skill>-<arm>-<split>.json. All three judges prefer slot 1 on more than half of calls, which is why only both-order agreement counts as a win.

Round-2 caveats: agentic-ceo r2b (0.625 against v0 0.45 on the same set) is the one clear direction, but its lower bound is 0.475, so it is not kept and no claim is made that it beats the rival. Best-of-three on n=10 tune overfits, and the judges share the generator's hosting cluster. Rival wins found on tune (re-basing an unrealistic stated assumption, a ledger from stated figures, deciding each listed sub-choice, naming sign-off owners, separate halt and re-order triggers) were ported as text, but the judges did not reward them reliably, and the judges of both arms missed planted arithmetic slips. prompts/rival_positioning.txt was restored locally for the run and is again not committed.
