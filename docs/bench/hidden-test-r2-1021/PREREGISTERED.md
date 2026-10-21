# hidden-test-r2-1021: preregistration of the bug-fix route check

Written and frozen before any call of this confirmatory run. The exploratory pilot (not preregistered) is in `pilot/`: the first hidden-test bench run (`pilot/runs.jsonl`, 5 arms, easy and hard) and the hard-split ablation (`pilot/ablation/`, 7 arms, 6 samples). Nothing in `pilot/` counts toward the verdict below.

## Question

The pilot's first run had the full Perun text 0.188 below no skill text on the hard split. The ablation (fresh samples, same text) did not reproduce it (perun minus none -0.036, CI includes 0) and named no block whose removal significantly raises the pass rate; dropping the delivery-process and testing-guidance blocks together (`perun-core`) matched none (0.688 vs 0.688). This run tests, on fresh samples, whether routing a bug-fix task to that smaller text (deep-code-review "Operating principles" plus "Definition of done", about 1.7k prompt tokens) keeps the pass rate within tolerance of no skill text.

## Arms (system prompt = the shared base line plus the arm text; only the text differs)

- `none`: the base line only.
- `perun`: the old full Perun text as measured in the pilot, composed by `perun_text()` from `agentic-delivery/SKILL.md`, the deep-code-review "Operating principles" and "Definition of done" sections, and `references/testing-and-evals.md`, read from the skill tree at repo commit e7d8ef261f65047f4f9861a9120c563ffc47ba55 (blob ids `fbda54b0...`, `daba3aa8...`, `2bd06ef7...`). Text sha256 `a7536f3aaa36dbe04a3fe8ce7c1a900458be2b5d3c350e2cfa931ddbdb313497`, identical to the pilot's recorded hash.
- `perun-core` (the fixed arm): the same cut with the `delivery` and `testing` blocks dropped, so only "Operating principles" and "Definition of done". Frozen text: `arms/perun-core.txt`, sha256 `7cb4ed54924a64a7b1d3842c2e4324cdef3a18452314629923ad243a80aaf5b1`. Cut rule: `perun_text(("delivery", "testing"))` in the driver.

If the verdict is KEEP, the skill change is a routing row in `agentic-delivery/SKILL.md` "Task to entry" that sends a single-module bug fix to those two deep-code-review sections instead of the gates; `perun-core` is the text that route loads. The run measures that text, not the routing row's effect on whether an agent follows it.

## Run

- Model Qwen3.5-397B-A17B, PCSS free endpoint, non-thinking, temperature 0.7, 4,000-token cap, one turn, no tools. No paid call.
- Corpus: `tickets/*.txt` unchanged from the pilot (40 easy, 23 hard); both splits.
- 3 samples per ticket and arm; API seed `20261021 + sample index` (the pilot sent no seed); 567 calls. Output goes to `confirm/` (a fresh dir, no pilot output reused).
- Scorer, bootstrap and driver are the frozen `scripts/hidden_test_bench.py` (10,000-resample percentile bootstrap over tickets, seed 1).

## Keep rule (exact; point estimates of this run, per split, `perun-core` against `none`)

KEEP the skill change only if all three hold:

1. hard: pass rate of `perun-core` >= pass rate of `none` - 0.05;
2. easy: pass rate of `perun-core` >= pass rate of `none` - 0.03;
3. `perun-core` prompt tokens per ticket <= the superpowers arm's prompt tokens per ticket recorded in the pilot (hard 5,265, easy 5,135; the superpowers arm is not re-run).

Otherwise REVERT: no skill change ships and the result is recorded. This is a non-inferiority rule against no skill text; it cannot show an improvement over the old Perun text, which is reported as a paired difference for information only. A tie or a loss is a valid result and is reported as measured.

## Not changed after this freeze

The driver, `scripts/rival_eval.py` (key loader, bootstrap), the tickets with their hidden tests, `arms/perun-core.txt` and this file. Anything amended later must appear as a ledger event naming the file hash.
