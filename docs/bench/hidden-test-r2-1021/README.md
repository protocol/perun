# hidden-test-r2-1021: bug-fix outcome with skill text as the system prompt

## Verdict of the preregistered check (r2): REVERT

`pilot/` holds the exploratory first run (the old `hidden-test-1021`, not preregistered) and a hard-split ablation. `confirm/` is the preregistered fresh-seed check (`PREREGISTERED.md`, `SHA256-frozen.txt`, `ledger.jsonl`, whose first line precedes every `confirm/` call). Pilot calls predate the freeze and are labelled exploratory; nothing in `pilot/` counts toward the verdict.

Ablation (`pilot/ablation/`, exploratory, hard split, 23 tickets, 6 fresh samples per arm; `perun-no-<block>` drops one top-level piece of the Perun arm):

| Arm | Pass rate [95% CI] | Prompt tokens per ticket | Minus Perun [95% CI] |
|---|---|---|---|
| none | 0.688 [0.543, 0.819] | 428 | |
| Perun (all four blocks) | 0.652 [0.522, 0.768] | 11,113 | |
| no delivery (agentic-delivery) | 0.688 [0.551, 0.812] | 5,174 | +0.036 [-0.065, +0.138] |
| no testing guidance | 0.667 [0.522, 0.804] | 7,608 | +0.014 [-0.080, +0.109] |
| no operating principles | 0.587 [0.435, 0.732] | 10,383 | -0.065 [-0.159, +0.022] |
| no definition of done | 0.580 [0.442, 0.717] | 10,602 | -0.072 [-0.152, 0.000] |
| no delivery and no testing (`perun-core`) | 0.688 [0.565, 0.804] | 1,669 | +0.036 [-0.051, +0.123] |

Reading: no block's removal significantly raises the pass rate. The delivery-process and testing-guidance blocks are the only ones whose removal moves the point estimate up; the operating principles and the definition of done carry the value (removing the definition of done is significantly below none, -0.109 [-0.210, -0.014]). The pilot's Perun minus none of -0.188 did not reproduce on these samples (-0.036, CI includes 0).

Preregistered check (`confirm/`, 3 samples per ticket and arm, API seed 20261021 plus the sample index, 567 calls):

| Split | none | Perun | perun-core | perun-core minus none [95% CI] | perun-core prompt tokens | superpowers prompt tokens (pilot) |
|---|---|---|---|---|---|---|
| hard (23) | 0.652 [0.478, 0.812] | 0.609 [0.464, 0.739] | 0.580 [0.406, 0.754] | -0.072 [-0.246, +0.101] | 1,669 | 5,265 |
| easy (40) | 0.883 [0.775, 0.975] | 0.892 [0.800, 0.967] | 0.917 [0.842, 0.975] | +0.033 [-0.008, +0.083] | 1,539 | 5,135 |

Keep rule: hard 0.580 >= 0.652 - 0.05 = 0.602 fails; easy and tokens hold. Result: REVERT, no skill change shipped. Every paired difference in `confirm/results.json` ties its CI with 0, so this is a failed non-inferiority threshold on a point estimate, not evidence that `perun-core` is worse. Exploratory pool of every hard sample across pilot, ablation and confirm (runs mixed; recompute with `python3 scripts/hidden_test_pool.py`: per-ticket mean over samples, paired percentile bootstrap, 10,000 resamples, seed 1, over 23 tickets; tested by `scripts/test_hidden_test_pool.py`): none 190/276 = 0.688, Perun 169/276 = 0.612, perun-core 135/207 = 0.652; Perun minus none -0.076 [-0.156, +0.004], perun-core minus none -0.036 [-0.122, +0.053]. The fixed arm was chosen from the ablation; the preregistered run is the only unselected test of it.

Disclosures for r2: the pilot's tickets, scorer and arm cut rules are unchanged (the driver gained the `perun-core` arm, the ablation arms, `--seed` and the path move; `HT_SKILLS` lets the driver read an old skill tree, and the pilot and r2 runs read the skill text at repo commit e7d8ef261 because the working tree this lane started in held newer skill files). The `perun` arm in `confirm/` is that same text (sha256 `a7536f3a...`, equal to the pilot's recorded hash). The API `seed` parameter may be ignored by the endpoint; no check was made that it makes samples reproducible. Driver edits and the freeze: `scripts/hidden_test_bench.py` was edited across this lane (git holds one commit, so there is no per-edit history). Evidence that no edit followed the freeze: the file's sha256 equals the one in `SHA256-frozen.txt`, its modification time (2026-10-21 03:44:39 +0200) precedes the `PREREGISTERED.md` and `SHA256-frozen.txt` times (03:45:50, 03:45:55) and ledger line 1 (`ts` 1792547169 = 01:46:09Z = 03:46:09 +0200), and the ledger records no confirm call before line 2. Modification times are filesystem metadata that can be reset, so this is consistent evidence rather than proof; a reviewer should re-run `scripts/bench_check.py`, which only checks the hashes. The ablation used `--samples 6` after a first 3-sample pass on the same out dir (samples 0 to 2, then 3 to 5); the first pass is included in the table, not selected.

Older text below describes the pilot run; its file names now live under `pilot/` and its default output dir is `pilot/`.

# hidden-test-1021 pilot: bug-fix outcome with skill text as the system prompt

Results table and verdicts: `docs/perun-vs-rivals.md`, section H14. Outcome: on the easy split (at ceiling) all five arms tie; on the hard split no skill text beats no skill text, and the full Perun text is significantly worse than none (-0.188, CI excludes 0).

## What it measures

Hidden-test pass rate of a model's corrected Python module, per arm, with a paired bootstrap CI against no skill text and against each rival, plus generated tokens per ticket. A loss or a tie is a valid result; this run has both.

- Corpus: `tickets/*.txt`, two splits in a plain format. `easy` (`part*.txt`, 40 tickets) was the first corpus and sits at a ceiling (none 0.867). `hard` (`hard*.txt`, 23 tickets) is stateful, ordering, multi-bug, dense-rule and misleading-symptom code in a single module (a rate limiter and token bucket, an undo stack, keyset pagination, a visibility-timeout queue, glob and CSV parsers, a nested-path setter, a stale-cache service with a misleading ticket, and similar). Each ticket has `### id`, then `--- ticket`, `--- src`, `--- fix`, `--- test`. The model is shown only the ticket text and the buggy `src`. `fix` is a reference solution used to prove each ticket is solvable (`validate`: every buggy source fails its hidden tests, every reference fix passes). Names are fictional; no real data.
- Arms differ only in the system prompt, which is one shared line plus the skill text: `none` (the line only); `perun` (`agentic-delivery/SKILL.md`, the deep-code-review "Operating principles" and "Definition of done" sections, and `references/testing-and-evals.md`); `perun-lean` (about 0.56k prompt tokens: the gate table header with only the G4 and G5 rows, the `UNVERIFIED` evidence rule and the two-failures-change-approach line from `agentic-delivery/SKILL.md`, plus operating principles 1, 2, 3 and 9; cut at run time from those same files by `perun_lean_text()`, which raises if the source text changes, so nothing is re-authored); `superpowers` (test-driven-development and systematic-debugging); `agent-skills` (test-driven-development and debugging-and-error-recovery). Rival texts are fetched at run time from GitHub at the commit recorded in `provenance.json` into a cache directory (default under the system temp dir) and are never committed.
- Model: Qwen3.5-397B-A17B on the free PCSS endpoint, non-thinking, temperature 0.7, 4,000-token output cap, 3 samples per ticket and arm (945 calls: 5 arms x 63 tickets x 3), one turn, no tools. No paid or `claude -p` call. The key is read from `PCSS_KEY` or the repo-root `.env` and is never printed or sent anywhere but the PCSS host; only the committed corpus and public skill text are sent.
- Scorer: the last non-test ```python block of the reply replaces `src` as `mod.py`; the ticket sample passes iff `pytest` passes every hidden test (20 s timeout, scrubbed environment, no key). A reply with no code block, an import of `os`, `sys`, `subprocess`, `shutil`, `socket`, `pathlib` and similar, or a call to `open`, `eval`, `exec` or `__import__` scores as a failure. Counts of no-code and truncated (4,000-token cap) replies per arm and split are in `results.json`; no run had an unsafe or timed-out reply. On the hard split truncation is a real share of the failures for superpowers (9 truncated of 69) and perun-lean (4 truncated, 3 no-code), and a long-winded reply that hits the cap counts as a failure for every arm alike.
- Statistics: each split is reported separately and never pooled for the verdict (the pooled line under Result is exploratory). Per-ticket score is the mean over the 3 samples; arm CI and paired-difference CI are 10,000-resample percentile bootstraps over tickets (seed 1); a win needs the lower bound above 0 (bounds are rounded to 9 places so float noise cannot turn a bound of exactly 0 into a win). There are 9 paired comparisons per split and no multiple-comparison correction, so one isolated significant pair deserves caution.

## Disclosures

- The corpus was written by the Perun side. Before any skill arm ran, one pilot of the `none` arm (1 sample per ticket, 31 of 40 passed) was read to find ambiguous hidden tests; three assertions the ticket text did not specify (leading zeros in `parse_int`, a `bool` quantity in `reserve`, a `bool` amount in `running_balance`) were removed (a wrong expectation in `truncate` had already been fixed by `validate` before the pilot). The pilot output is not committed. No skill-arm output was seen before the corpus was frozen; `provenance.json` carries a hash of the frozen tickets, sources and tests.
- The Perun arm composition was chosen once, before the first run, and not tuned. Perun has no dedicated debugging skill.
- `perun-lean` was designed after the easy-split results were seen (the coordinator asked for a cheaper Perun text because the full arm costs 10,983 prompt tokens). Its easy-split run is therefore post-hoc, and Perun carries little TDD or debugging prose, so the lean text is mostly the gate rows and principles rather than a debugging method. Its composition was fixed before its first call and not tuned afterwards.
- Hard split calibration. The goal was a `none` pass rate near 40 to 60 percent. 33 hard tickets were written; a pilot of the `none` arm only (2 samples each, 66 calls, 45 passed = 68%, not committed) was read to find tickets the baseline always solves. 10 of the 20 tickets `none` solved in both samples were dropped, chosen by `random.Random(1).sample` over the sorted ids (`h_calendar`, `h_dep_order`, `h_dict_diff`, `h_invoice_total`, `h_lease_lock`, `h_page_ranges`, `h_recurrence`, `h_reservations`, `h_semver_range`, `h_version_bump`), leaving 23. No skill-arm output was seen before this freeze, but the freeze used baseline results, which regress toward the mean on fresh samples: the final `none` rate on the hard split is 0.725, still above the 40 to 60 percent target, so the target was missed. Tickets were not tuned further after the skill arms ran.
- Not built: multi-file bugs and real threads. Hard tickets are single-module; ordering and concurrency are simulated with explicit clocks and call order. Results say nothing about cross-file debugging.
- A model failing with `finish_reason=length` (it narrates edge cases in comments until the 4,000-token cap) is scored as a failure; this penalises verbose prompts and replies, and is part of the measured outcome.
- One model, one turn, no tools: skills that prescribe running a failing test first could not do so here. Results do not transfer to agentic use.
- Easy split: 40 small tickets at a baseline of 0.867 leave little headroom and a CI half-width of about 6 to 8 points. Hard split: 23 tickets give a half-width of about 12 to 15 points on a single arm and 12 to 15 on a paired difference (Perun minus none is 14.5). Re-scoring the hard-split runs by failure type shows all 32 Perun failures are complete replies with a wrong fix (no missing code, timeout or syntax error), so the loss is not an extraction artifact.
- Completion tokens are the API's `completion_tokens` in non-thinking mode, so they exclude any hidden reasoning a thinking-mode run would add.

## Reproduce

```
python3 scripts/hidden_test_bench.py validate          # offline corpus check
python3 scripts/hidden_test_bench.py run               # (r2: default out is confirm/; pass --out pilot to extend the pilot) needs PCSS_KEY; resumes from runs.jsonl; add --split easy|hard|all, --arms, --samples/--jobs/--limit
python3 scripts/hidden_test_bench.py report            # offline; rewrites results.json and prints the tables
python3 scripts/test_hidden_test_bench.py              # scorer, corpus and report tests
```

Files: `runs.jsonl` (every sample: arm, ticket, pass, reason, tokens, full reply), `results.json` (aggregates and paired differences), `provenance.json` (model, rival commits and file hashes, Perun text hash, ticket hash). Replies are model output for the committed corpus; they are the audit trail for the pass flags. A rerun will differ in individual samples (temperature 0.7, server-side nondeterminism); the committed `runs.jsonl` and `results.json` are the record.

Repro note (2026-10-23): `scripts/hidden_test_bench.py` reads the live `deep-code-review/references/full-map.md` for the `perun` arm (Operating principles and Definition of done). That file was split into a core plus `full-map-principles.md` and `full-map-report.md`, so a fresh run on a current tree builds a smaller `perun` text (principles 1 to 3 and 9, Definition of done (b)). To reproduce this lane's arms, point `HT_SKILLS` at the skill tree of parent commit 465d12f38d6b75b74af4192e311619c97b354b99 (old `full-map.md`: 22122 bytes, sha256 78e77ea257564578c3df601c24d79e7c96390c2f2707fb35df36917051a72f27); the recorded runs read repo commit e7d8ef261.
