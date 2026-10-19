# Pipeline optimizer: measurement record (2026-10-16)

**BLUF.** The profile of this repository's own pipeline put 82% of CI execution (10m27s of 12m46s) in one step, `bash scripts/test-ci-gates.sh`. Timing its sections showed the cause: every call of the shipped gate runner re-proved the same seven idempotent gate selftests, about 45 s per call. A selftest verdict stamp (`DCR_SELFTEST_STAMPS`) removes the repeats. Measured locally: the full gate-helper suite went from 2092 s to 1421 s wall (-32%) and from 971 s to 564 s CPU (-42%). **The CI number has not been re-measured yet**: it needs one merge and one new profile (commands below). Until then the CI saving is a projection, not a result.

## Surfaces (what each number is)

| Number | Surface | Measured or projected |
|---|---|---|
| CI execution 12m46s median, queue 2 s, lead time 14m38s | GitHub Actions runs of `ci.yml`, 30 runs, 23 measured (7 cancelled or skipped) | Measured (`before-profile.json`) |
| `test-ci-gates.sh` 10m27s, 82% of CI execution | the same runs, step "Gate helper self-tests" | Measured |
| 32 section timings, 2072 s | one serial local run, this sandbox | Measured (`sections-before.json`) |
| Full suite 2092 s to 1421 s wall, 971 s to 564 s CPU | local serial runs, same sandbox, same tree except the stamp change | Measured (`local-timings.tsv`), load varied between runs |
| Runner micro A/B, see below | local, real `dcr-gates.sh`, 3 interleaved pairs | Measured |
| CI step after the change | GitHub Actions | **Projected, not measured** |

A local timing is never a CI timing. The local gain is a lower bound: in this sandbox `serial_gate.py --selftest` fails (it needs `ps`), a failure is never stamped, so that selftest still re-runs on every call here.

## Profile before (`before-profile.json`)

| Stage (median) | Seconds |
|---|---|
| local push hook | 16.0 (n=4: 17.0, 14.9, 14.5, 17.6) |
| CI queue wait | 2.0 |
| CI execution | 766 (12m46s) |
| post-green wait | 23 |
| first push to merge | 878 (14m38s, 19 PRs, 1.0 cycles per PR) |

Red rate 13%, reruns 0, no cache step. Ranked bottlenecks: `gates / Gate helper self-tests` 10m27s (71% of lead time), `Live eval harness and review scorer tests` 1m40s, `Shipped script self-tests` 41.5 s, then everything under 25 s.

Suite x stage map: 116 suites, 13 at more than one stage (heaviest: `scripts/test-ci-gates.sh` at precheck and CI). The duplicate removal the catalogue ranks first is worth 13.7 s per PR once priced, and the documented pre-PR full run never pays off locally (local wall exceeds CI plus queue). `CONTRIBUTING.md` no longer asks for it; the quick tier stays.

## Why a stamp, not sharding

`fixes` priced `shard` at 2m28s and `affected` at 4m49s, both assuming the step is divisible, and printed that the dominant step is unpriced until its internals are timed. The section timings (`sections-before.json`):

| Sections | Seconds | Share |
|---|---|---|
| six sections that call the gate runner (opt-in delivery gates 722, reaper lint 157, AppSec supply pins 142, closes lint 137, install with gates 84, lesson ratchet 77) | 1319 | 64% |
| the tail (`update-installed.sh` to the end: per-feature tests, one of about 400 s) | 704 | 34% |
| 25 other sections | under 50 | 2% |

Local timing of the seven selftests the runner runs at every start: `fix_class_gate` 13.9 s, `parity_differ` 4.0 s, `serial_gate` 27.4 s (fails in this sandbox), the other four under 1 s each: about 45 s per call, repeated across every call.

Alternatives considered (evil twin):

| Option | Why it lost |
|---|---|
| Shard `test-ci-gates.sh` over jobs | The heaviest sections share one installed runner and fixtures; a safe split restructures the script. A runner was built and dropped. |
| Skip the selftests with a flag in the suite | Hides the gate selftest from the one place that must prove it; the stamp keeps every selftest and runs it once per script version. |
| Bigger runner | `runner` prices a serial step at about zero (cpu/wall near 1). |
| Cache between CI runs | The stamp key is the script content hash, but a cross-run cache would make a selftest vouch for a script it never ran against; per-run scope only. |

Safety properties kept: only a PASS is stamped, a failure is never cached, the stamp key is `git hash-object --no-filters` of the script (raw bytes, so an eol-only edit re-runs) plus `python3 -V` plus its basename, and the stamp directory must be a real directory we own with mode 700 (created that way; one throwaway directory per run, never shared) or it is ignored and every selftest runs. `scripts/test-selftest-stamps.sh` has eleven cases; three were red before the stamp existed and five more before this hardening.

## Runner micro A/B (deep-code-review gates only, 3 interleaved pairs, wall seconds)

| Pair | 1 call, no stamps | 3 calls, stamps | 3 calls, no stamps | stamped / unstamped (3 calls) |
|---|---|---|---|---|
| 1 | 28.6 | 31.8 | 83.6 | 0.38 |
| 2 | 27.0 | 27.7 | 67.7 | 0.41 |
| 3 | 12.2 | 12.7 | 46.2 | 0.27 |

Three stamped calls cost about one unstamped call. The absolute seconds differ per pair because machine load differed (30 to 140); the ratio is the comparable number.

## Full-suite runs (serial, same sandbox)

| Run | Wall | CPU |
|---|---|---|
| before | 2092.4 s | 971.2 s |
| before, earlier replay | 2083.7 s | 881.1 s |
| after (stamps) | 1420.5 s | 563.9 s |
| after (stamps), rebased tree, quieter machine | 869.3 s | 383.8 s |

Both runs exit 1 for the same reason: this sandbox cannot run `ps`, so `serial_gate.py --selftest` fails and the opt-in delivery, reaper lint, priority, focus and tracker-hygiene cases that call the runner fail identically on a pristine `origin/main`. The rows carry `ok=1` in `local-timings.tsv` for that reason (a completed run with known failures). Those cases are not caused by this change and not fixed by it. The last run (rebased tree): 279 passed, 9 failed: those 8 plus the real-config size-ratchet case, which fails only until the commit carries the `size-budget-raise` lines for the four grown files. The 869 s run is not comparable with the 1421 s and 2092 s runs (machine load differed and the tree was rebased onto a newer `origin/main`); only the ratios inside one controlled pair, like the runner A/B above, are.

## Decision record and kill criteria

Decision: keep the stamp and the dropped pre-PR full run. Kill criteria, either one reverts: (1) over the first 5 merged PRs after this lands, `compare before.json after.json --metric ci.exec_s.median` does not report a drop of more than 5%, or the step "Gate helper self-tests" does not fall by at least 30%; (2) the red rate rises above 13% by more than 10 points over the same 5 PRs (the dropped local full run was hiding failures CI now finds late).

## Reproduce

```
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py profile --repo protocol/perun --workflow ci.yml --offline --data bundle.json --sections docs/bench/pipeline-1016/sections-before.json --log docs/bench/pipeline-1016/local-timings.tsv --out docs/bench/pipeline-1016/before-profile.json
```

The raw API bundle is not committed (it holds commit messages and branch names); `before-profile.json` is the derived, identifier-free result. To re-collect after the merge (needs `GH_TOKEN`; unauthenticated calls are 60 an hour and a shared address may already be exhausted):

```
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py profile --repo protocol/perun --workflow ci.yml --runs 30 --data after-bundle.json --out after.json
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py compare docs/bench/pipeline-1016/before-profile.json after.json --metric ci.exec_s.median --stage-only
```

`--stage-only` is needed because `before-profile.json` predates the delivery-outcome fields (`lead.merged_per_day`); without it the compare is UNVERIFIED ("outcome not measured"). The KEEP it gives is labelled stage-only: it says nothing about push-to-merge lead time.

Exit 0 is KEEP, 1 is REVERT, 2 is UNVERIFIED (too few samples).

## Limits

- Not measured: the CI step after the change, lead time after the change, the red-rate effect of dropping the local full run.
- The 13% red rate rests on 23 measured runs (3 red).
- The first profile used 19 merged PRs; the median lead time moves with the mix of PR sizes.
- Next ranked cost after the stamp: the suite tail (704 s), led by one per-feature test of about 400 s; three tests run twice in CI (once in the monolith, once as their own step), each below the 1% noise floor.
