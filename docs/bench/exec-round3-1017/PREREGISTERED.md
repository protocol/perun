# Round 3 preregistration (written 2026-10-17, before any held-out arm generation or judging)

Scope: `agentic-ceo` and `idea-critic`, the two skills that did not clear the keep rule in `../exec-1017` (rounds 1 and 2). The method and judges are round 2's (see `../exec-1017/PREREGISTERED-ADDENDUM-2.md`); `bench3.py` here reuses `../exec-1017/bench.py` and `bench2.py` unchanged and only redirects the output directory. Only PCSS models are called; no Anthropic calls.

## Root cause (tune split only)

Read from the both-order tune judge records `../exec-1017/judge4/<skill>/PERUN_v0/` (reasons of the votes the rival won) and the tune generations:
- idea-critic: the rival wins when it catches a planted figure slip (a stated total that does not equal its parts) that Perun repeats as given, although the skill already says to recompute; it also wins with a capped first step and a tripwire that is not already tripped, where Perun gives a go-if with several open conditions. The base text asks for a recompute but nothing makes it appear on the page before the call.
- agentic-ceo: the rival wins on the concrete sub-choices (vendor, order), named sign-offs, a financial breakdown, and separate halt and re-order triggers. Round 2's variant `r2b` ported these and was the best direction (0.625 held-out, lower bound 0.475), so the candidate keeps it and adds the visible recompute.

## Candidates (one per skill; text in `prompts/`, built by `mk3.py`)

- idea-critic `r3a`: step 5 requires an opening `Figures:` line rebuilding each stated total, rate and date from its parts, a mismatch leading the answer; step 6 asks for a capped first step where the plan can be bounded and an outcome tripwire not already tripped.
- agentic-ceo `r3a`: round-2 `r2b` with the recompute made a visible `Figures:` line.

Tune (n=10, selection signal only, same both-order three-judge majority): idea-critic v0 0.35, r2a 0.60, r3a 0.60; agentic-ceo v0 0.65, r2b 0.70, r3a 0.75. Choice recorded here: `r3a` for both. For idea-critic, r2a tied r3a on tune and is 72 bytes shorter, but r2a already failed a held-out test (0.325 [0.200,0.475], round 2) and r3a is the new mechanism this round targets, so r3a is the candidate.

## Held-out test (run once)

- 40 fresh scenarios per skill (`scenarios3/<skill>-h3.json`, ids h01-h40) written by `gpt-oss_120b` from 40 new fictional settings (`prompts/seeds3.txt`, none used before; the second skill reads the same list rotated by 20) with the unchanged writer briefs. They were generated before this file and are unread; their hashes are in `SHA256-frozen.txt`, taken before any arm generation.
- Arms: `PERUN_r3a` and the rival (`../exec-1017/prompts/rival_<skill>.txt`) on every scenario; `PERUN_v0` (current SKILL.md text) also runs as a reference, not used for the keep decision except the clause below.
- Generator Qwen3.5-397B-A17B (never a judge). Judges DeepSeek-V4-Flash, GLM-5.2 (thinking off), MiniMax-M2.5, each in BOTH orders; a judge's verdict counts only when both orders agree (else tie); the majority of the three decides (else tie, 0.5).
- Score per scenario 1 / 0.5 / 0; bootstrap 10,000 resamples, seed 1, percentile, over scenarios.
- Keep rule: keep the edit only if the 95% lower bound is above 0.5 AND the win rate is at least `PERUN_v0` on the same set. Otherwise revert and ship the bench only. Every judge's slot-1 rate is reported (`slot1_rate` in `results4-*.json`).
- Known weaknesses: judges and generator share one hosting cluster; ties count 0.5, so most of any lift is tie-to-win conversion; one run per arm, with API nondeterminism near 0.1 at n=20.
