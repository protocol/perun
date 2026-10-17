# Preregistration: business-ops candidate e, confirmatory test (2026-10-18)

Written and hashed (SHA256-frozen.txt, ledger.jsonl event `prereg_frozen`) before any seed, scenario or arm generation and before any judge call. Every model call goes to the PCSS endpoint ($0); no `claude -p`, no paid API, public data only. Code derived from `docs/bench/bizops-call-1017`.

## Question and disclosure

Candidate e ("lead with the call", `../bizops-call-1017/prompts/perun_business-ops_e.txt`, sha256 d0f49e79...) scored paired e minus v0 +0.083, 95% CI [-0.025, 0.183] at n=60 in `../bizops-call-1017`: underpowered, not a loss. This is ONE confirmatory test of the SAME frozen e text (no rewording, no new candidates) on a larger fresh set.

Disclosure: this is a second test of e after a near-miss, so the false-positive risk is higher than a first test at the same threshold. A ship decision here is evidence, not proof; a failure ends the e line (no third try on this text without a new owner decision).

## Arms

- v0: the unedited `.claude/skills/business-ops/SKILL.md` at base commit 2ddbde82 (origin/main), sha256 daa7139a... (copied to `prompts/perun_business-ops_v0.txt`, identical to the earlier rounds' v0).
- e: `prompts/perun_business-ops_e.txt`, byte-identical to `../bizops-call-1017/prompts/perun_business-ops_e.txt` (sha256 d0f49e7943588903319bd2643516bbd5db2170fd253007e12e45d653fd692178).
- Rival: `prompts/rival_business-ops.txt`, same vendored text as `../bizops-call-1017` (sha256 b0318f64..., MIT, notice in `LICENSE.rival.txt`). Its answer is generated once per scenario and shared by both Perun arms.

## Scenarios

n=150 fresh held-out, ids `c150-001` to `c150-150`, own `outputs/` and `judge/` directories. 150 one-line settings are drawn by Qwen3.5-397B-A17B (3 calls of 50, temperature 0.9) with the harness examples and every earlier business-ops round's settings listed as "do not repeat"; each is expanded to a scenario by the blind writer (temperature 0.7, 10 per call) from the standing brief `scripts/eval-fixtures/rival/business-ops/brief.txt`, unedited, none dropped. `bench.py check` must report clean before any arm runs: no id clash, no identical prompt, and no 6-word-shingle overlap above 0.3 with any earlier business-ops set (harness sets, every `docs/bench` business-ops scenario file including `bizops-call-1017`) or inside this set. A failing writer output is redrawn as a whole batch, never edited; if `check` fails on the frozen set, offending scenarios are reported and the whole set is redrawn once, never edited.

## Generation, judging, scoring

- Generator for every arm: Qwen3.5-397B-A17B, thinking off, temperature 0.3, no tools, harness `GEN_TASK` wrapper, system prompt = the arm text. Writer and generator never judge.
- Judge: `scripts/rival_eval.py` judge v2 (neutral three-letter labels, reason-first), cascade GLM-5.1, then GLM-5.2, then gpt-oss_120b; the first judge whose slot-1 rate over every verdict lies in 0.4-0.6 scores both arms; none healthy means no verdict. Both orders per pair; a scenario scores 1 (Perun wins both), 0 (rival wins both), else 0.5; an order with no usable verdict counts 0.5 and is reported.
- Win rate = mean scenario score. CI: percentile bootstrap, 10,000 resamples, seed 1, over scenarios. Paired difference = mean of (e - v0) per scenario, same bootstrap.

## Decision rule

SHIP e (apply it to `.claude/skills/business-ops/SKILL.md` with one eval and a changelog fragment) only if the paired (e - v0) 95% bootstrap CI lower bound is above 0. Superiority over the rival is claimed only if e's own win-rate CI lower bound is above 0.5. Otherwise ship only this bench and its record. No re-runs, no judge swaps, no scenario edits after any result is seen. The ledger (`ledger.jsonl`) is append-only: events `prereg_frozen`, `seeds_drawn`, `scenarios_frozen`, `gen`, `judge`, `paired`.

## Caveats declared in advance

Open models on one cluster, not the models users run; both arms system-prompt only (no references or scripts). Sampling is unseeded; earlier re-judges moved about 0.1. The rival is a pricing skill answering legal, tax and regulatory questions it was not written for, and the judge rewards substantive decisive answers, so a win measures answer-first helpfulness, not safety. e loosens "route, never conclude" by design (the owner decision); the no-fabrication floor stays and any shipped eval and changelog state the loosening plainly.
