# Pipeline optimizer: map the repeated runs, measure, then tune

Read this when a delivery pipeline is slow (a commit or push hook over about a minute, CI over about ten minutes, a long wait to merge), when someone proposes tuning one stage (faster runners, parallel test workers, caching, affected-test selection), or when you are asked to "make CI faster". `scripts/pipeline_profile.py` is the mechanism; this file is the procedure.

## BLUF

1. **Map first.** `pipeline_profile.py map` draws the suite x stage table (commit, push, precheck, ci, train). Every suite that runs at more than one stage is a duplicate. No stage is tuned before the map exists.
2. **Each blocking check runs once, at the latest gate that still blocks merge.** Duplicate removal ranks first in the catalogue. Tuning one stage speeds up one copy of N.
3. **Measure, price, decide, re-measure.** Rank the bottlenecks from numbers, price each fix from the profile, do the biggest saving per effort, and keep it only if the measured time drops.

The case this exists for (generalized): commits took up to 47 minutes. Commit and push hooks were cut to quick checks and the full suites ran once, at the merge gate, which still blocks on red. Commit time fell to about 30 seconds. Nothing else changed: no caching, no sharding. The earlier attempt tuned stages one at a time (faster runners, parallel workers, affected-test selection); each stage got faster and the repeated runs stayed. It never mapped which suite runs where, and it read "never weaken a gate" as "never move a check".

## Who owns it

The Conductor owns the loop as the COO function: lead time, queue and wait, the timebox, the one escalation. The Architect hat owns the technical fix as the CTO function: which fix, shard design, cache keys. Implementer lanes make the change and QA re-measures at the exact SHA. No new standing role (`roles.md`: hats, not headcount). `agentic-ceo` routes "the pipeline is slow" here instead of tuning a stage inline.

## Moving a check is not weakening it

A gate is **weakened** when a check that blocked merge stops blocking it: removed, made advisory (`continue-on-error`, `|| true`), narrowed to fewer cases, or no longer run on the SHA that merges. A check is **moved** when it runs at one later blocking gate instead of at several. A move is not a weakening when all four hold:

1. It still runs and blocks at one gate on the way to the default branch.
2. That gate is server-enforced (a required CI check, a merge queue, a train or integrator), not a hook. Git documents that a hook can be bypassed with `--no-verify` (`git-hooks`), so a hook is convenience, never the enforcement.
3. It runs on the SHA that merges, or on the union that merges.
4. A planted failure turns that gate red (`gate-epistemology.md` principle 4).

The earlier copies are then latency, not safety. `pipeline_profile.py map` flags a suite with no proven blocking copy and then advises dropping nothing. Blocking is proven, never assumed: a push-only workflow does not gate a PR, and a job or step with `continue-on-error` (any value but `false`) or an `if:` the script does not recognise counts as not enforced.

This agrees with `host-enforcement.md` *Cost discipline* (run every gate locally once before pushing, so CI is not the first place a red appears): "once" means one blocking run. Run the quick tier locally, in seconds. A full local run on top of CI pays off only above the break-even red rate that `profile` prints: local seconds divided by (CI seconds + queue wait), compared with the observed red rate.

## Anti-stall rules

1. **No fix without a profile.** A symptom ("the tests are slow") is not a profile. Nothing changes before `map` and `profile` exist.
2. **One hypothesis, one timebox.** One row of the ranked table is one hypothesis with a stated budget (default: two hours of work or two attempts). On expiry record the measured delta, even zero, and take the next row. After two equivalent failures change approach (`SKILL.md` *Failure*); never a third try.
3. **Report the measured delta at every step**, in one line: `fix=<id> metric=<m> before=<x> after=<y> n=<runs> surface=<local|CI> verdict=<KEEP|REVERT|UNVERIFIED>`. A step with no number is not progress.
4. **Escalate a blocker once.** A permission, sandbox, branch-protection or secret gap goes to the owner as ONE batched ask with the exact commands to run. Then continue with the next row that needs none of it. Do not retry the blocked step or route around the control (`SKILL.md` *Human gates*).
5. **A data gap is not a stop.** `profile` records an API rate limit and keeps what it has; resume with the same `--data` file, or measure locally (`time`, `suites --run`, `hooks --run`).

## Step 1: map (mandatory)

```
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py map
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py map --declare train='bash scripts/verify.sh'
```

It reads the commit and push hooks (`core.hooksPath`, `.githooks`, `.husky`, `.git/hooks`; a thin hook is its implementation), the workflows (`pull_request` and `push` are ci, `merge_group` is train, a tag-only push is a release and is skipped), and fenced commands under a "pre-commit" or "before you open a PR" heading in `CONTRIBUTING.md`, `README.md`, `AGENTS.md` and `CLAUDE.md` (precheck). A suite key is `script [subcommand|--selftest]` or `runner [subcommand]`, so one check run with different arguments still collides. Output: the table, every duplicate, and the gate to keep (the latest server-enforced stage; hooks and prechecks are bypassable). `--declare STAGE=CMD`, or `.perun/pipeline.json` (`{"stages": {"train": ["cmd"]}}`), adds a stage no file shows, such as a merge-train verify command.

A `gate_map` script is planned in the hook-cache lane and is not shipped in this release. When it exists in `scripts/`, run it first and treat any disagreement with `map` as a bug in one of them. Until then `map` is the map.

## Step 2: measure

```
pipeline_profile.py hooks --run        # real wall time of the commit and push hooks against HEAD (clean tree)
pipeline_profile.py suites --run       # time each duplicated suite once, at the stages to drop
GH_TOKEN=... pipeline_profile.py profile --data .pipeline-bundle.json --out before.json
```

It reports medians, and `n/a` when an input is missing, never a guess:

- Per-stage wall time on the critical path: commit hook, push hook, CI queue wait, CI execution, post-green wait (approval, merge train).
- The CI critical chain per run (the job that finished last, then the job that finished just before each started) and its steps ranked by median seconds.
- Push-to-merge lead time per merged PR (first push to merge, last push to merge) and cycles per PR (distinct head SHAs).
- Reruns (`run_attempt` above 1), flake suspects (a rerun that passed), red rate.
- CI seconds spent on re-runs forced by base updates (head commit "Merge branch ... into ..."), the cost a merge queue removes.
- Cache steps in the workflows and, only when job logs are supplied (`--logs DIR`), the hit rate counted from the `actions/cache` log lines.
- Duplicates in seconds: CI step seconds split over the step's commands, local seconds from the `time` rows, and the break-even red rate for keeping one local full run.

Then the ranked bottleneck table: seconds per cycle, seconds per merged PR (times cycles), and the share of first-push-to-merge.

When one step dominates (the profile prints `DOMINANT STEP`), a step is a suite of suites: time its internals before choosing a fix. Print a timestamp at each section of the script, pass the section seconds with `profile --sections FILE` (`{"<step>": {"<section>": seconds}}`, any one unit), and look for the same command repeated inside it. The stage map cannot show a repeat inside one script; the section timings can.

Data comes from the GitHub REST API (`/actions/runs`, `/actions/runs/{id}/jobs`, `/pulls`). Unauthenticated calls are capped at 60 an hour (`gh-rate-limit`); set `GH_TOKEN` or `GITHUB_TOKEN`. The token is sent as an unredirected header and never forwarded. Lead time here is first push to merge, a proxy for the first leg of the DORA change lead time (`dora`), which ends at production.

## Step 3: the catalogue (every saving computed from the profile)

Duplicate removal ranks first when it saves more than the noise floor (the larger of 1 s and 1% of the lead time). The rest rank by saving per relative effort (1, 2 or 4: ordinal, not hours). A fix that cannot be priced goes last and says what to measure. `fixes` prints `DECIDE: measure first` while a duplicated stage run is untimed: duplicates rank first once priced, so a stage fix chosen before that is a guess. `--accept-unmeasured` overrides it for a stage that cannot be timed.

| Fix | Saving per merged PR | Effort | Sources |
|---|---|---|---|
| `dedup` | seconds of every stage of a duplicated suite except the one kept, times cycles per PR | 1 | `swe-ci`, `fowler-ci` |
| `fail-fast` | red rate times the mean seconds saved by running the cheapest steps first in the red runs | 1 | `fowler-ci`, `gh-matrix` |
| `flake` | rerun attempts times the median run, over completed runs | 2 | `google-flaky`, `swe-ci` |
| `cache` | install, setup and build step seconds times the share of merges that left the lockfile unchanged (or the measured miss rate) | 1 | `gh-cache`, `actions-cache-src` |
| `affected` | per test-running CI step: step seconds times (1 minus how often a name-reference selector runs its test files); a monolithic test script is one file, so it gains only when no changed file name appears in it | 4 | `pts-paper`, `swe-ci` |
| `shard` | independent unit seconds (a step, or the timed sections of a dominant step, `--sections`) minus the longest-processing-time makespan over k jobs minus per-job setup (k = `--shards`, default 4: a public-repository Linux runner has 4 CPUs) | 2 | `gh-matrix`, `xdist`, `pw-shard`, `gh-hosted-runners`, `amdahl`, `cpm` |
| `queue` | mean CI seconds per PR spent on base-update re-runs | 2 | `gh-merge-queue` |
| `incremental` | lint, type and format step seconds times (1 minus the share of tracked files a merge changes) | 1 | `eslint-cache`, `ts-incremental`, `ruff-cache`, `mypy-daemon` |
| `move-local` | CI step seconds minus local wall seconds where the suite measured faster locally; needs an unbypassable gate elsewhere | 2 | `git-hooks`, `swe-ci` |
| `runner` | step seconds times (1 minus 1/min(core ratio, cpu/wall)); a serial step gains nothing | 1 | `gh-larger-runners`, `amdahl` |

Why duplicates come first: the critical path is the sum of the dependent stage times (`cpm`), and the improvement from optimizing one part is limited by the fraction of time that part is used (`amdahl`). A suite that runs four times is four parts, and tuning one removes at most a quarter. CI should keep quick, reliable tests early and slower ones later (`swe-ci`); the commit build is the one that "has to be done quickly" and a secondary build catches what it skips (`fowler-ci`).

## Step 4: decide and implement in lanes

Take the first row that clears the noise floor. State the hypothesis, the metric (`ci.exec_s.median`, `stages_s.push`, `lead.first_push_to_merge_s`) and the timebox before a lane starts. Implement in a worktree (`worktree-isolation.md`), one fix per lane so the delta is attributable. A change to a required check, branch protection or merge queue settings is owner-gated (`SKILL.md` *Human gates*): park it with the exact commands and continue.

## Step 5: re-measure and keep only a drop

```
pipeline_profile.py profile --data after-bundle.json --out after.json
pipeline_profile.py compare before.json after.json --metric ci.exec_s.median
```

Exit 0 is KEEP, 1 is REVERT, 2 is UNVERIFIED. KEEP needs the metric to fall by more than 5% and more than 1 second, with at least 3 measured runs behind each side. A local timing and a CI timing are different surfaces: name which one each number is, and never report a local speed-up as a CI one. A change whose time did not drop is reverted and the next row is taken.

## Worked example: this repository's own pipeline (2026-10-16)

Raw profiles, section timings and the before/after numbers are in `docs/bench/pipeline-1016/`.

- **Map.** 116 suites, 13 at more than one stage. The heaviest repeat is `scripts/test-ci-gates.sh`: a documented pre-PR step, run again by CI.
- **Profile** (30 PR runs, 23 measured). CI execution 12m46s median of a 14m38s first-push-to-merge; queue wait 2 s; post-green wait 23 s; 13% red; no reruns. One step, the gate helper self-tests, is 10m27s (82%) of CI execution, so CI wall time is almost all that one script.
- **Pricing.** `fixes` priced `shard` at 2m28s per PR (the step is one script, so only seven coarse units) and `affected` at 4m49s (effort 4, an upper bound that holds only if the monolith can be split), and printed `DOMINANT STEP ... Sharding is unpriced until its internals are timed`. Both prices assume the step is divisible; neither is evidence it is.
- **Drill-down.** Timing the script's 32 distinct sections (`--sections`, 2072 s on a serial run) put 64% of its time in the six sections that call the shipped gate runner, and the runner re-proves the same seven idempotent gate selftests (about 45 s) on every call. That is a duplicate run inside one stage; the stage map cannot see it, the section timings can.
- **Decision.** A selftest verdict stamp (`DCR_SELFTEST_STAMPS`, in `dcr-gates.sh`): each selftest passes once per run per script, and a failure is never stamped. The documented full-suite pre-PR step was dropped too (`CONTRIBUTING.md`): the profile showed it costs more than the CI run it could save. A sharding runner was built first and dropped: the runner-calling sections (64% of the time) share one installed runner and its fixtures, so a 4-way shard needs the script restructured, while the stamp removes the repeated work inside them.

## Sources

Fetched 2026-10-16; the quoted text and each URL are in `docs/standards-index.md`. The ids are the ones used above and in the script's catalogue.

| Id | URL | Used for |
|---|---|---|
| `gh-merge-queue` | https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue | A queue builds the merge group once and spares the author the update-and-wait cycle; needs the `merge_group` trigger |
| `gh-cache` | https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching | Cache miss creates the cache; 7-day eviction and the repository size limit |
| `actions-cache-src` | https://raw.githubusercontent.com/actions/cache/main/src/restoreImpl.ts | The log lines the hit rate is counted from |
| `gh-jobs-api` | https://docs.github.com/en/rest/actions/workflow-jobs | Job and step `started_at` / `completed_at` |
| `gh-runs-api` | https://docs.github.com/en/rest/actions/workflow-runs | `run_attempt`, `head_commit`, page size |
| `gh-rate-limit` | https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api | 60 requests an hour unauthenticated; 403 or 429 with `x-ratelimit-remaining` 0 |
| `gh-larger-runners` | https://docs.github.com/en/actions/concepts/runners/larger-runners | More RAM, CPU and disk |
| `gh-hosted-runners` | https://docs.github.com/en/actions/reference/runners/github-hosted-runners | Standard Linux runner: 4 CPUs and 16 GB on a public repository (2 and 8 GB on a private one); free on public repositories |
| `gh-matrix` | https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations | Matrix jobs; a failing job cancels the rest in progress |
| `fowler-ci` | https://martinfowler.com/articles/continuousIntegration.html | Commit build fast, secondary build for the rest, ten-minute guideline |
| `swe-ci` | https://abseil.io/resources/swe-book/html/ch23.html | Quick tests on presubmit, slower ones after; run only affected tests |
| `google-flaky` | https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html | Flaky definition, quarantine, one rerun |
| `xdist` | https://pytest-xdist.readthedocs.io/en/stable/distribution.html | Distributing tests to workers |
| `pw-shard` | https://playwright.dev/docs/test-sharding | Shards as separate CI jobs |
| `pts-paper` | https://arxiv.org/abs/1810.05286 | Selecting a test subset per change is a recognised lever |
| `eslint-cache` | https://eslint.org/docs/latest/use/command-line-interface | `--cache` processes only changed files |
| `ts-incremental` | https://www.typescriptlang.org/tsconfig/ | `incremental` saves the project graph between compilations |
| `ruff-cache` | https://docs.astral.sh/ruff/settings/ | `cache-dir` default |
| `mypy-daemon` | https://mypy.readthedocs.io/en/stable/mypy_daemon.html | Daemon reuses state between runs |
| `git-hooks` | https://git-scm.com/docs/githooks | pre-push and pre-commit; `--no-verify` bypasses |
| `dora` | https://dora.dev/guides/dora-metrics/ | Change lead time definition |
| `amdahl` | https://en.wikipedia.org/wiki/Amdahl%27s_law | Limit of optimizing one part |
| `cpm` | https://en.wikipedia.org/wiki/Critical_path_method | Critical path is the longest dependent chain |
