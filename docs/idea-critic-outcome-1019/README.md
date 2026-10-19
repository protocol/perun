# idea-critic outcome bench (2026-10-19)

BLUF: on 36 historically resolved go/no-go decisions, the idea-critic skill did **not** beat either comparison arm on decision accuracy. On the primary model it scored 0.574 against 0.824 for the rival skill text and 0.694 for no skill; the paired differences exclude zero in the rival's and baseline's favour. The harm guardrail held (0 false-go on both models), but the skill got there by saying NO-GO to most good decisions too (85% of good decisions on the primary model, 98% on the second, where an unparseable call counts as not-GO). This is the first bench of any Perun skill against an answer key rather than a judge's preference.

Note: this first bench was not preregistered, so it is kept outside `docs/bench/` and is not gated evidence. The preregistered, held-out replacement is `../bench/idea-critic-calibration-1019/`; its numbers supersede these.

## Question

Does the skill's call match what actually happened? Earlier rival benches (for example `../bench/idea-critic-r9-1018`) are pairwise-preference only: a judge model says which answer reads better. Nothing there says whether the advice would have helped. Here the key is a documented real-world result.

## Corpus (`corpus.json`)

- n = 36 decisions, 18 key `good` and 18 key `bad`, decision years 1955 to 2019.
- Each case is a proposal written as the information available before the decision (the proposal, the bull case and the known risks), with the company and product names removed so the model cannot simply recall the outcome. `bench_outcome.py check` and `scripts/test_idea_critic_outcome.py` fail if any listed name appears in a prompt or if outcome vocabulary ("write-down", "bankrupt", "failure" and similar) appears.
- Key: `good` means the decision was carried out and the documented result was a success (for example adoption, sales or a lasting franchise); `bad` means a documented failure, write-down, reversal or shutdown. Each case has `source_urls` (English Wikipedia articles) and an `evidence_quote` copied verbatim from the text fetched on 2026-10-19 through the MediaWiki API. The corpus builder asserted every quote is present in the fetched text.
- Candidates whose fetched source did not state an outcome (two acquisitions I first considered) were dropped, not kept on memory.

## Arms and task

Same user message for every arm: the proposal, a 350-word limit, no tools, and a last line that must be exactly `DECISION: GO` or `DECISION: NO-GO` (a "revise first" or "hold" counts as NO-GO).

| arm | system prompt |
|---|---|
| PERUN | `.claude/skills/idea-critic/SKILL.md` as of this commit (about 4.1k prompt tokens) |
| RIVAL | the rival skill text already used by the r9 bench, `../bench/exec-1017/prompts/rival_idea-critic.txt` (about 20k prompt tokens) |
| BASE | none |

3 samples per case and arm at temperature 0.7; a case's score is the mean over its 3 samples. An unparseable decision counts as wrong for every arm.

## Metrics

- Accuracy: decision matches the key (GO on `good`, NO-GO on `bad`).
- False-go rate (harm guardrail): GO on a `bad` case.
- False-no-go rate (cost of over-blocking): NO-GO on a `good` case.
- Tokens per call: prompt and completion tokens from the PCSS usage field (`ledger.jsonl`).
- Intervals: 10,000-resample percentile bootstrap over cases, seed 1, using `boot` from `scripts/rival_eval.py`. Paired differences are per-case PERUN minus other arm.

## Results

Primary model, Qwen3.5-397B-A17B (thinking off), `results-Qwen3.5-397B-A17B.json`:

| arm | accuracy [95% CI] | false-go (n=18) | false-no-go (n=18) | invalid | prompt / completion tokens per call |
|---|---|---|---|---|---|
| PERUN | 0.574 [0.426, 0.722] | 0.000 [0.000, 0.000] | 0.852 [0.722, 0.963] | 0 | 4125 / 402 |
| RIVAL | 0.824 [0.713, 0.926] | 0.000 [0.000, 0.000] | 0.352 [0.185, 0.537] | 0 | 20191 / 411 |
| BASE | 0.694 [0.546, 0.833] | 0.019 [0.000, 0.056] | 0.593 [0.370, 0.796] | 0 | 240 / 338 |

Paired accuracy: PERUN minus RIVAL -0.250 [-0.380, -0.130]; PERUN minus BASE -0.120 [-0.231, -0.019].

Second model, gpt-oss_120b (reasoning on, 6000-token budget), `results-gpt-oss_120b.json`:

| arm | accuracy [95% CI] | false-go (n=18) | false-no-go (n=18) | invalid | prompt / completion tokens per call |
|---|---|---|---|---|---|
| PERUN | 0.389 [0.250, 0.528] | 0.000 [0.000, 0.000] | 0.981 [0.944, 1.000] | 22 of 108 | 4084 / 1089 |
| RIVAL | 0.509 [0.352, 0.667] | 0.056 [0.000, 0.148] | 0.926 [0.796, 1.000] | 0 | 19569 / 531 |
| BASE | 0.509 [0.361, 0.657] | 0.093 [0.000, 0.204] | 0.833 [0.685, 0.963] | 5 of 108 | 288 / 610 |

Paired accuracy: PERUN minus RIVAL -0.120 [-0.213, -0.037]; PERUN minus BASE -0.120 [-0.231, -0.009]. PERUN's 22 invalid decisions (no final `DECISION:` line, counted wrong) lower its figure. Scored on valid decisions only (a post-hoc view, not the headline), accuracy is PERUN 0.488 (86 calls), RIVAL 0.509 (108), BASE 0.534 (103): near parity, with PERUN saying GO on only 2.2% of valid `good` calls against 7.4% (RIVAL) and 17.3% (BASE).

Reading: the skill's prime directive (attack before assent, no reflexive agreement) turns almost every proposal into a NO-GO. That is safe on `bad` cases and wrong on `good` ones. On this answer key, with a forced binary call, the rival text's softer stance and even the bare model were more accurate. On gpt-oss_120b all three arms mostly refuse, so differences there are small in absolute terms.

## Limits (read before quoting)

- Non-Claude host. Both generators are free PCSS models, not the Claude models the skill is meant to run on. The skill may behave differently on Claude; this bench says nothing about that.
- Hindsight and memorisation risk. Names are removed, but a large model may still recognise a famous case from its shape (an all-stock merger of a dial-up provider and a media conglomerate). The pre-decision text was written by one author from public knowledge and may carry unconscious framing. Accuracy on `good` cases in particular may reflect recall, not judgement. The leak applies to all three arms equally, so the comparison is fairer than the absolute level.
- Forced binary. The skill's native verdicts are HOLD, REVISE and PASS_TO_USER. Mapping REVISE to NO-GO penalises a skill whose designed output for a decent but flawed proposal is "revise". A three-way key would need a different corpus.
- Executed decisions only. Every case is a proposal that was carried out, so `good` means "did well", not "was better than the alternative". Counterfactuals are not in the key; cases where a company declined and later regretted it are absent.
- Survivorship and fame. Famous cases are over-represented; `good` outcomes lean toward large technology and media firms, partly because their results are the best documented. Each outcome is summarised from one encyclopedia source; some `good` keys (the code-hosting and messaging acquisitions) rest on usage growth, not disclosed profit.
- n = 36 cases (108 calls per arm and model), so intervals are wide; the false-go figure over 18 `bad` cases cannot distinguish 0 from a few percent.
- Single prompt wording, one temperature, one run per model; no tuning on this set. The rival text costs about 5x the skill in prompt tokens (about 20k against 4k).
- Sources are not re-fetched by the tests; the quotes were checked against the fetched text once, at build time.

## Reproduce

```
set -a; . ./.env; set +a; export PCSS_ENV=$PWD/.env   # PCSS_KEY only; never printed
python3 docs/idea-critic-outcome-1019/bench_outcome.py check
python3 docs/idea-critic-outcome-1019/bench_outcome.py run Qwen3.5-397B-A17B    # reuses stored outputs; regenerates missing ones
python3 docs/idea-critic-outcome-1019/bench_outcome.py report Qwen3.5-397B-A17B
python3 scripts/test_idea_critic_outcome.py
```

Files: `corpus.json` (cases, key, sources), `bench_outcome.py` (driver and report), `outputs/<model>/<arm>/<case>.<rep>.txt` (raw answers), `ledger.jsonl` (one line per call attempt: tag, model, seconds, error type, token usage; no key, no text; 1,004 `URLError` lines are Qwen attempts made while the network proxy was closed, retried later; one `IncompleteRead` retry for gpt-oss_120b), `results-<model>.json`.
Spend: $0 (PCSS). No Anthropic calls.
