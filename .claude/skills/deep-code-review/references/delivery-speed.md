# Delivery speed — CI time, build time & review-cycle friction (domain K)

Read this when the review must say how fast a change reaches users: a CI workflow or hook chain's wall-clock, a build, bundle or image step, a test suite's runtime, or friction in the pull-request cycle (size, queue, re-review, flaky required checks). Measuring the flow and the bar for adopting a platform are in `release-engineering.md` (section "Measure the flow before adopting a platform or a second methodology"); runner-minute cost is `domain-k.md` and `ci_cost_lint.py`. This file is the **where the time goes** probe list.

## Order of work

Measure the loop (below); attribute the p95 to a stage; take the free fix, then the cheap fix, then a platform. Ordering cheap checks first and scoping the commit hook are in `release-engineering.md`; this file does not restate them. With no run history, report `UNMEASURED` rather than a guess.

## Measure first (proxies, not billing)

CI wall-clock and queue wait from the run history (field names from `gh run list --help`):

```
gh run list -w <workflow> -s success -L 100 --json attempt,createdAt,startedAt,updatedAt > runs.json
jq '[.[] | select(.attempt == 1) | ((.updatedAt|fromdateiso8601) - (.startedAt|fromdateiso8601))] | sort
    | {n: length, p50: .[length/2|floor], p95: .[length*0.95|floor]}' runs.json
```

Swap the subtraction for `startedAt - createdAt` to get queue wait. These are proxies: `updatedAt` is the last update, the `attempt == 1` filter keeps re-runs from skewing both numbers, a success-only sample hides what red runs cost, and parallel jobs add billable minutes the wall-clock does not show. Report p50 and p95, never the mean alone.

Pull-request cycle: `gh pr list --state merged -L 100 --json createdAt,mergedAt,additions,deletions,changedFiles,reviews` gives time-to-merge, size, and (from the first review's timestamp) first-review latency.

## CI wall-clock probes (read the workflow, then confirm against the timing)

- **No dependency cache.** A job that installs dependencies with no cache. GitHub's dependency-caching documentation (2026-10-16) says the `setup-*` actions for npm, Yarn, pnpm, pip, pipenv, Poetry, Gradle, Maven, RubyGems, Go and NuGet can create and restore dependency caches with minimal configuration; otherwise use `actions/cache` with an explicit key.
- **A cache that cannot hit.** The key has no lockfile hash (never refreshes) or includes something that changes every run (never hits). Restore keys are searched in order. A run can restore caches from its own branch, the default branch and, for a pull request, its base branch, but not from sibling or child branches: PR runs are warm only if the default branch writes the cache. The same page states that entries unused for 7 days are evicted and that the default limit is 10 GB per repository (stated values on 2026-10-16; they change, re-check), so a weekly job often starts cold.
- **Serial chains with no data dependency.** A job with `needs: [a]` that reads no output or artifact of `a` is a parallel candidate. Detect: for each `needs:`, look for `needs.<job>.outputs` or a download-artifact step.
- **The same expensive step in many jobs.** Checkout, install and build repeated in each of N jobs: build once, upload an artifact, reuse it.
- **Full-history checkout where history is not read.** `fetch-depth: 0` on jobs that never diff against history.
- **One slow job dominates.** When the p95 stage is a single test job, shard the suite (by file, or by recorded timing) before buying a bigger runner.
- **Retries that mask flakes.** A retry wrapper adds wall-clock on every flake and hides the rate. Count reruns and fix the top offenders (`testing-situational.md`, flaky tests).
- **Fixed sleeps.** `sleep N` waiting for a service: wait on a readiness signal (`testing-situational.md`).
- **Image builds.** Docker's build-cache documentation says a changed layer invalidates every layer after it, and its guidance puts expensive steps early and steps that change often late: copy the package manifest and lockfile, install, then copy the rest. `COPY . .` above the install reinstalls on every source edit. Also check for a `.dockerignore` and package-manager cache mounts. An ephemeral runner starts with an empty local layer cache, so confirm a cache import and export is configured before crediting the layer order.

## Build-time probes

- A compiled or bundled project rebuilt from scratch on every run with no incremental or remote cache: measure cold against warm before recommending anything (no number, no adoption: `release-engineering.md`).
- Monorepo builds and tests that always run everything: select by the import graph and fail closed to the full run when a file is unmapped (`release-engineering.md`, "Select affected tests by the import graph").
- A new heavy dependency or generated step: its install and build delta belongs in the PR; the bundle-size budget rule is in `concurrency-shared-state.md` (section "Measure before optimizing").
- Import-time work and re-export files that inflate startup and bundles: `code-structure.md`.

## Review-cycle friction (the target's process; the reviewer's own diff-size modes are in `method-situational.md`)

- **PR size.** Google's engineering practices say "100 lines is usually a reasonable size for a CL, and 1000 lines is usually too large", that file count matters (200 lines in one file may be fine, spread over 50 files usually too large), and that it is the reviewer's judgment. Use the repo's own size distribution from the measurement above, not a hard rule.
- **Review latency.** The same source puts the maximum time to respond to a review request at one business day and says slow review lowers team velocity. A median first-review latency far beyond that is a throughput finding.
- **Style nits that tooling should absorb.** If review history is mostly formatting and naming, the finding is the missing formatter or linter gate. Google's guidance: prefix optional preferences with "Nit:" and do not block on them.
- **Reviewer routing.** A `CODEOWNERS` catch-all owned by one overloaded team, no fallback reviewer, or more required approvals than the risk needs (`docs-and-dx.md`, repository hygiene).
- **Flaky or slow required checks.** A required check that fails at random or runs long taxes every PR. Time-to-green and rerun rate are the evidence.
- **Automated-reviewer noise.** A bot reviewer without a severity floor spends the human's attention, and the tools expose one: CodeRabbit labels comments Critical, Major, Minor, Trivial or Info; Greptile has a strictness setting of 1 to 3 (default 2); Copilot labels comments High, Medium or Low; Anthropic's code-review plugin drops issues below a confidence threshold (default 80) and filters pre-existing issues, issues linters catch, and pedantic nitpicks. A bot configured with no severity floor or confidence threshold is a finding; the team's own noise controls live in `review-config.md`.

## Rating

Medium or Low by default, calibrated by stage (a prototype does not need sharding). High when slowness stops a gate from running: a check people skip because it is too slow does not exist as a gate (principle 2 in `full-map.md`), or time-to-green exceeds what a hotfix can wait. Never outranks a correctness, security or data-loss finding.

**🚩 grep**: an install step with no cache; `needs:` with no `needs.*.outputs` or artifact use; `fetch-depth: 0` in a job that never runs `git log` or `git diff`; `retry` or `continue-on-error` around tests; `sleep ` in CI steps; `COPY . .` above a package install; no `.dockerignore`; a `CODEOWNERS` `*` line with one owner.
