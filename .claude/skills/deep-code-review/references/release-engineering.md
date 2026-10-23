# Release engineering — feature flags, progressive delivery & DORA (domain K)

Read this when the target ships a feature-flag system, a canary or blue-green
deploy pipeline, a CI workflow that deploys, or a perf/leak gate whose local
runtime major may not match the deploy image — the **release** half of domain
K, sitting beside `dependency-currency-and-upgrades.md`'s **build/supply-chain**
half. `agentic-delivery`'s **Release** hat (`references/roles.md`, if that
overlay is installed) is the authoring-time discipline this file audits at
review time; this file stands alone for a plain review-only install with no
delivery overlay.

Before this file existed, a `FULL` review had no reference file behind domain
K's "release" promise at all — a permanently-on `// temporary` feature flag or
an undefined canary rollback produced zero findings, not because the target was
clean but because nothing in the skill looked.

---

## Feature-flag lifecycle

Not every flag is the same risk shape. Tag each by category before judging its
age (Fowler's four):

- **Release toggle** — hides incomplete/untested code on the path to
  production. Short-lived by design: "should generally not stick around much
  longer than a week or two." A release toggle older than that, with no removal
  date or tracking issue, is carrying-cost debt, not a feature.
- **Experiment toggle** — A/B or cohort routing. Lifetime tracks the
  experiment, not a fixed window; flag it only if the experiment itself looks
  abandoned (no metrics wired, no end date). **And the assignment code itself is reviewable, not
  just the readout:** bucketing must be a **deterministic hash of a stable randomization unit + an
  experiment salt** (`hash(unit + experimentKey) % 100`), never `Math.random()` / session-scoped /
  re-rolled per request, and the unit stays constant across a logged-out→logged-in transition; the
  **exposure event fires at the point the variant actually changes rendered behavior**, not at
  assignment or page load (logging exposure for units that never reach the branched code dilutes
  the effect); and a **sample-ratio-mismatch (SRM) guard** — observed group sizes vs the intended
  split — is wired. SRM is a **high-sensitivity signal that something in the assignment/exposure
  pipeline is broken** — a symptom with several causes (telemetry filtering, trigger/exposure
  misconfiguration, or the bucketing itself), not a pointer to one, and it in most cases
  invalidates the results outright (Fabijan et al., KDD 2019; Kohavi et al., *Trustworthy Online
  Controlled Experiments* — by name). **Concurrent experiments on the same surface must be
  isolated:** two experiments that both mutate the same UI or flow with no layering and no mutual
  exclusion **confound** each other's readouts (a unit lands in both), and per-experiment bucketing
  + SRM — which only check one experiment's own assignment — won't catch it. The assignment infra
  must put overlapping experiments in **orthogonal layers** (Google's overlapping-experiment
  infrastructure uses "orthogonal diversion criteria for experiments in different 'layers' so that
  each event ... can be assigned to multiple experiments") or **mutually exclude** experiments that
  touch the same surface; an ad-hoc second experiment bolted on with neither is a code-side finding.
  Read-side validity (peeking, always-valid bounds) stays in `growth-analytics`; interpreting the
  effect over time (**novelty/primacy**) and correcting across many metrics (**multiple-comparison /
  false-discovery**) are read-side statistical analysis too — not the code side covered here.
- **Ops toggle** — an operator kill-switch/degrade lever. Meant to be
  long-lived; the finding here is a *missing* one on a risky rollout, not an
  old one.
- **Permissioning toggle** — feature-by-segment (e.g. paying customers). Also
  long-lived by design; treat like any other authz surface (domain B) if it
  gates access rather than behavior.

**🚩**: a release-category flag with no removal date/issue, committed more than
two weeks ago (grep the flag's own git blame date, not "when I noticed it");
flags treated as inventory nobody counts — "savvy teams view feature toggles in
their codebase as inventory which comes with a carrying cost," and the classic
failure mode of stale toggle debt is a launched-and-forgotten switch nobody
dares remove.

**Flag evaluation (runtime), not just lifecycle:**
- **Pin the evaluated value once per logical request / transaction.** Re-evaluating the same flag
  mid-request — across async continuations, retries, or separate service calls in one operation —
  can render a **composite of both code paths** in a single response. This is a config-read
  *consistency* bug, not a data race (nothing is mutated — distinct from the check-then-act TOCTOU
  in `domain-g.md` / `concurrency-shared-state.md`). It is the **complement, not a
  contradiction,** of caching the flag *fetch* with a TTL (`performance-db-cost.md`): cache the
  fetch, but **pin the evaluated value** for the life of the request and pass it down rather than
  re-reading — the same shape as the lifetime-mismatch rule in `concurrency-shared-state.md`
  (thread a per-run value as a parameter).
- **Set the provider-unreachable default per flag category, and disambiguate "closed."** When the
  flag service is unreachable the code takes a default, and **fail-open is the bug for a risky or
  incomplete feature** exactly as a fail-open rate-limiter store is (`security-appsec.md` — the
  store-unreachable-defaults-open case). For a flag, "closed" is ambiguous: a **release toggle**
  closed = the *old code path* (safe), but an **ops kill-switch**'s safe default is *engaged*
  (feature degraded), not disengaged. Name the safe default **per category**, so an outage
  neither silently enables a half-built feature nor disables a safety lever.
- **A flag that swaps a production route's rendered content must render the same component tree the
  reviewed preview route was measured through.** The preview route is usually a standalone page built to
  iterate safely; splicing the same page component into a production route's flag-on branch is easy to do
  without carrying the shell/providers the standalone page always had (a layout wrapper, an auth/theme/global
  context) — nothing crashes, since a missing provider commonly reads as a wrong default rather than an
  error, and any review or screenshot taken through the preview route alone never sees the flagged path at
  all. Detect: with the flag on, diff the production route's rendered component tree against the preview
  route's, not just a screenshot of each (the **structure** axis, `rendered-parity.md`) — a visual match
  won't surface a missing provider whose effect isn't visible on screen. Verify live: render both routes with
  the flag on and confirm an identical component tree, not merely a similar look.

## Canary / blue-green — claims need config, not prose

A PR description or runbook claiming "canary rollout" or "blue-green deploy" is
a claim like any other (principle 1) — it needs a citable mechanism, not a
label:

- **Canary**: traffic actually split to a small subset first (random sample,
  internal users, or a named demographic), with a **named halt metric** and an
  automatic-rollback path on regression of that metric — not only an error-rate
  check; a real "immune system" watches a business metric too, since a broken
  feature can be 200-OK and still wrong. The halt metric must be **partitioned by
  the canary cohort** (`service.version` or an equivalent tag) — an unpartitioned
  metric blends canary and baseline traffic and can never regress-check
  (`observability.md`, telemetry resource identity).
- **Blue-green**: two environments actually provisioned, the idle one tested,
  and cutover is a **router flip** — find the router/traffic-split config, not
  just the runbook step that says "flip."
- **🚩**: "canary" or "blue-green" in a PR title/description/runbook with no
  matching router, load-balancer, feature-flag-percentage, or traffic-split
  config anywhere in the diff or the referenced infra — this is prose, not a
  mechanism, and it is exactly as verifiable-or-not as any other unproven claim
  this skill already refuses to accept at face value.

## Rollback — tested, not merely asserted

`agentic-delivery` G8 already requires "rollback proven"; the review-side check
is the same evidence bar applied to a target with no delivery overlay: name the
rollback mechanism (router flip back, flag off, previous image/tag redeploy),
and find where it was **exercised** (a runbook drill, a game-day note, a past
incident) — not only documented. A rollback path that has never been run is
`unverified`, the same as an SLI defined only in a doc (`role-coverage.md`).

## Resilience is exercised — chaos engineering

Reliability claims are verified the way rollback is (above): a **chaos-engineering** exercise
states a **steady-state hypothesis** ("checkout success stays above 99% if a cache node dies"),
injects the fault in a **blast-radius-limited** scope (one instance, one AZ, a dependency timeout —
in a controlled window, staging before prod), and confirms the hypothesis held. A DR / failover /
autoscaling path with **no exercise** — no game-day, no injected-failure drill, no past incident
that ran it — is `unverified`, not proven, exactly as the Rollback section above holds: a
documented runbook is a hypothesis until run.
Scope every experiment so a failed hypothesis cannot itself cause the outage it was testing for.
A game-day / drill also loses evidentiary value as the code drifts from what it validated: **date it**
like the backup-restore drill (`observability.md`), and flag one with **no re-run since a material
change to the exercised path** as **stale, not proof** — extending the Rollback section's exercise
bar to a recency bar, the "a green run is a sample, not a proof" discipline `testing-situational.md`
applies. Exercising the infra path is also not a substitute for a repo-owned regression test on the
fallback branch's output (`testing-and-evals.md`).

## DORA — measure it or say so

The DORA framework's own five metrics, in two categories, are the standard
vocabulary for whether the pipeline itself is healthy — **throughput** (change
lead time, deployment frequency, failed-deployment recovery time) and
**instability** (change fail rate, deployment rework rate — the share of
deployments that are unplanned but happen as a result of a production
incident). Do not compute a number from vibes:

- **Computable** — the repo/pipeline has the raw signal (deploy timestamps,
  commit-to-deploy linkage, incident/rollback records): compute it, cite the
  query or log source, `file:line` or command.
- **Not computable** — no CI-timestamp history, no incident log, no
  deploy-frequency record: report `UNMEASURED` (mirroring the skill's own
  `UNPRICED`/`UNVERIFIED` convention), never a fabricated number, and never a
  silent pass that reads as "fine."

Beyond delivery throughput, **developer productivity and experience are multi-dimensional** — the
**SPACE** and **DevEx** frames span satisfaction/well-being, performance, activity, communication,
and efficiency/flow, precisely because any single proxy (lines of code, commit or PR count, story
points) is gameable and misleads. A review that reduces "productivity" or "velocity" to one number
is the finding — the same false-precision bar as a composite score that sums heterogeneous
constructs (`data-scoring.md`). Name what a metric can and cannot support, and **route a
people-performance judgement to the owner** — never assert it from repo activity.

---

## Measure the flow before adopting a platform or a second methodology

The DORA metrics above say whether the pipeline is healthy; a second, cheaper set says where the
**iteration loop** hurts day to day — **time-to-green** (push → all checks pass), **queue / runner
wait**, and **rerun / flake rate**. These are **not** DORA metrics; apply the same p50/p95
discipline to them (an average hides the tail). Before adopting a build/merge platform (a merge
queue, a remote-cache or CI vendor) or a **second delivery methodology**, **measure the current
flow** on both sets, **attribute the p95 to a stage** (which job, which wait), and take the
**cheap fix first** — cache a step, shard a slow suite, cancel superseded runs, fix the top flaky
test. A tool bought before the bottleneck is measured usually moves a number you were not blocked
on.

- **The adoption bar is a question, not a vibe:** *"which measured metric does this platform move,
  and by how much?"* No number, no adoption — route the spend to the owner **with** the
  measurement (`agentic-delivery`'s Release gate when that overlay runs; the spend decision itself
  is the owner's, like the DORA *measure-it-or-say-so* rule above).
- **One delivery methodology per repo.** A second parallel process — a rival branching model or
  release ritual added "to go faster" — is coordination overhead priced as progress; a measured
  bottleneck justifies **switching** to a better one, never **running both**. Adopting a
  methodology is itself subject to the bar above.
- **Order a commit-hook / CI chain cheapest-decisive-check-first — a trivial-mistake retry must
  not pay the expensive tier.** A commit / pre-commit / pre-push hook or a CI pipeline that runs
  its slow, expensive tier (the full test suite, a container build, an integration stage) *before*
  a cheap, near-instant check (commit-message format, lint, a formatter, a banlist grep) charges
  the whole expensive cost on **every** retry of a mistake the cheap check would have caught in
  milliseconds — a mis-formatted commit message re-runs the entire suite each time the author
  re-types the message. Order the stages by cost, cheapest first, so the common cheap failure
  **fails fast** before the expensive tier ever starts. This is a **free re-ordering**, taken
  *before* the paid platform levers in the paragraph above (cache a step, shard the suite) — the
  same cheapest-decisive-first discipline as running the cheapest go/no-go query first in
  `data-freshness.md`, here spending CI minutes and developer wait instead of a query. Grep the hook
  / workflow definition (`.pre-commit-config.yaml`, `.husky/`, a `lefthook.yml`, a
  `.github/workflows/*.yml` job `needs:` graph or step order) and read whether a fast
  lint/format/message check gates the slow build/test tier or merely trails it.
- **Ordering the tiers cheapest-first is not sufficient when the expensive tier still runs in
  `pre-commit` at all — under concurrent lanes it can deadlock, not just waste minutes.** Even
  correctly ordered (cheap checks first, per the bullet above), a `pre-commit` stage that runs the
  **whole** test suite unconditionally — with no changed-path scoping, while sibling stages in the
  same chain (lint, type-check) do scope to changed files — blocks every `git commit` for the
  suite's full runtime, serializing concurrent agent/developer lanes competing for CPU. Worse: a
  workflow that requires a **follow-up** commit (a generated changelog fragment, a lockfile update)
  can deadlock outright — the second commit hangs in the same slow hook, so the PR stays red for the
  missing artifact while the very commit that would add it is stuck running the full suite, with no
  single commit able to escape quickly; a lane that responds by re-polling CI burns tool calls and
  tokens waiting on a result that cannot arrive until its own blocking commit finishes. **Fix:**
  scope `pre-commit` to a fast, changed-path subset (or an explicitly-marked fast tier) and run the
  full suite in **pre-push** or **CI**, where the added latency amortizes across a batch instead of
  taxing every commit. Distinct from the ordering fix above — reordering stages cheapest-first still
  pays the full cost on every commit once the cheap stage passes; this is about **which lifecycle
  stage** the expensive tier runs at, not its position within one stage. CI-side path-filtered
  staging is `parallel-audit.md`'s path→gate manifest (cross-referenced there, not restated here);
  this is the local-hook-lifecycle sibling of that same scoping discipline.

---

**🚩 grep**: `feature.?flag`/`FF_`/`toggle` definitions with no adjacent removal
date, ticket reference, or category comment; `canary`/`blue.?green`/`rollout` in
prose (PR body, runbook, `README`) with no matching weight/percentage/router
config in the diff; a rollback section in a runbook with no evidence it was ever
run (no drill note, no incident reference); a CI/CD workflow that deploys with
no deployment-frequency or lead-time signal anywhere (no tagged releases, no
deploy-event log) — DORA is structurally `UNMEASURED` for that pipeline, and
that absence is itself worth naming once, not per-PR.

## Signed releases — a consumer-verifiable signature, not just build provenance

Distinct from build provenance / attestation (SLSA), which `infra-iac-containers.md` covers as a **deploy-side**
gate the team verifies on its *own* pipeline: does the release process also **produce a signature a downstream
consumer can check**? A GitHub Release, package publish, or image push should ship a signature next to the
artifact — cosign / keyless Sigstore (`*.sigstore` / `*.sigstore.json`), `npm publish --provenance`, PyPI attestations (PEP 740, produced under Trusted Publishing), a GPG-signed tag or `*.asc` / `*.sig`, or a SLSA provenance file (`*.intoto.jsonl`) attached
as a release asset. OpenSSF Scorecard's Signed-Releases check is **"Risk: `High` (possibility of installing
malicious releases)"** and "tries to determine if the project cryptographically signs release artifacts"
("Signed releases attest to the provenance of the artifact"). A project can have SLSA build provenance
internally yet attach **no** consumer-verifiable signature to what it ships — that gap is the finding. (`appsec-supply.md` A03 poses the same producer-side question in one line — *is a released artifact signed, or only checksummed over the same channel it ships on?* — this section is its depth.)

- **Find the signature artifact next to the release**, and confirm the publish job actually runs the signing
  step — a documented "we sign our releases" with no signing step in the actual `release` / `publish` workflow
  is not signing. And presence is not validity — a signature a consumer cannot chain to a trusted key is
  the producer-side echo of "generated provenance is not verified provenance" (Scorecard's own check "does
  not verify the signatures").

- **A valid signature proves who signed, not where the build ran.** A GPG-signed tag or a cosign/Sigstore
  signature satisfies the check above even when the actual build, tag, and publish steps all ran on a
  maintainer's own laptop rather than a hosted build platform — the check observes the identity that signed,
  never the machine the artifact was built on. A stolen publish credential or a compromised workstation
  produces an artifact that still tags, signs, and verifies cleanly, because the compromise sits upstream of
  the cryptography the check re-derives. This is the producer-side half of the question `appsec-supply.md`
  poses on the verify side — its L1/L2/L3 build-provenance ladder (depth there, not restated here)
  presupposes an answer to *where the build ran*, which a bare signature check never asks. Before crediting a
  release with any level above the trivial-to-forge provenance-exists floor, confirm the publish/release job
  actually ran on hosted CI, or a recognized hosted-builder integration — GitHub Actions OIDC `npm publish
  --provenance`, PyPI Trusted Publishing — not a local `npm publish` / `twine upload` / manual `git tag` +
  upload, by reading the workflow run, not the signature.

**🚩**: a Release/publish with no signature, attestation, or provenance asset; a signing step present in docs
but absent from the workflow that ships the artifact; a signature present but not validatable against a
trusted key; a release credited with a build-provenance level despite no publish/release job in
`.github/workflows/` (or equivalent CI config) — just `RELEASING.md` / `CONTRIBUTING.md` or a `Makefile`
target a human runs by hand (`npm publish`, `twine upload`, `git tag -s` + manual asset upload).

## A perf/leak gate that boots the wrong runtime major diagnoses the wrong problem

A perf, load-test, or memory-leak gate that runs against the **local dev runtime**
instead of the **deploy image's** runtime produces a result for a system that isn't
what ships — a runtime major-version difference (Node, Python, JVM, …) between local
and the deploy image/`engines` field can change GC behavior, allocator defaults, or a
dependency's native binding enough to point a leak/perf diagnosis at the wrong cause
(one observed run: a local-vs-deploy runtime major mismatch cost one full wrong-diagnosis
cycle before the gate was re-pointed at the right runtime). **Read the runtime major from
the deploy artifact** (the container image's base tag, the platform's `engines`/runtime
config) and boot the gate on **that** major, not whatever happens to be on the developer's
machine or CI runner by default. **Check:** the gate's log prints the runtime version it
booted, and that version matches the deploy image/`engines` declaration — a mismatch fails
the gate before any perf/leak number is trusted. Cross-ref `method-situational.md`'s
containerized/serverless deploy-contract preflight (the broader "reproduce a gate-aimed
finding under the real deploy contract" rule this is one instance of) and
`concurrency-shared-state.md`'s "Load-test coverage and heap-leak gates" (the heap-slope
metric this runtime check must precede).

## Visual-parity suite: pinned capture settings, and confirm it actually runs at the merge gate

A visual-parity / screenshot-diff suite protects nothing when either of two gaps is open. First,
if the settings that produce a screenshot — viewport, device-pixel ratio, wait/settle timing, any
relevant feature flag (`templates/parity-capture.md`'s "Same state on both sides" table) — aren't
pinned identically across runs, score/diff drift between two runs is measurement noise, not a
real visual change, and gets misread as a false regression or false stability
(`rendered-parity.md`'s flag/option-set pinning rule covers the comparison-scope half of this;
this is the capture-mechanics half). Second — read the actual merge-gate configuration, never
assume — confirm the suite is wired into the check that blocks a merge, not merely available to
run by hand: opt-in, path-filtered out of the diff that touches visual code, or skipped for cost
is the same as absent at merge time, no matter how good its detectors are once invoked.

- **Find the workflow file and the branch-protection required-checks list**, and confirm the
  visual suite's job is both **present** in the workflow that runs on the PR's changed paths and
  **named** in the required-checks list — a suite that exists in `.github/workflows/` but isn't a
  required check merges around every time, same as one that never ran.
- **Run the suite twice with no code change and confirm a zero (or documented-tolerance) diff**
  before trusting it on a real PR — the pinned-settings half above, verified empirically.
- **A "passing" status on a visually-changing PR is unverified for visual parity** until both
  checks above are confirmed — say so explicitly rather than reporting a general green (this
  file's Signed-releases section poses the identical producer-side question — does the workflow
  that claims a property actually run it — for a different property; the check here is the same
  pattern, applied to visual parity).

**🚩**: a visual-parity/screenshot-diff job present in `.github/workflows/` but absent from
branch-protection's required-checks list; a visual suite path-filtered out of the very diff that
changes rendered UI; a "visual parity: passing" claim with no confirmation the job ran on this PR,
only that it exists somewhere in CI; two same-code runs of the suite producing a nonzero,
undocumented diff (unpinned capture settings, not a real change).

## Demo/sample-mode write isolation — one shared guard, not a per-call-site convention

A "sample data"/demo-mode/sandbox toggle meant to be read-only or write-isolated from the real
backing store is only as safe as its **weakest** write call site. Trusting each write path to
remember "check the mode flag, redirect to scratch" is a convention, not a guarantee — one write
path added later, or refactored, forgets the check and writes straight to the real store while
still labeled "just a demo." Because the failure only surfaces when someone actually uses demo
mode *and* later inspects the real store, it can go unnoticed for a long time, by which point real
data may already be polluted with demo content (or demo actions may have mutated real records).

- **Route every write through one shared write layer that itself checks the mode and
  redirects/blocks** — never trust each call site to remember the check. A direct
  client/ORM/API call made in a component or handler, bypassing the shared layer, is the finding
  regardless of how correct that one call site looks in isolation.
- **Verify:** a spy/instrumentation test asserts that, with demo mode active, zero write calls
  reach the real store's client across **every** write path in the app — not just the ones the
  author remembered to test. Enumerating write call sites and confirming each routes through the
  shared layer is the same caller-census discipline `appsec-design.md`'s shared-endpoint scoping
  check uses for authorization — applied here to a mode gate instead of a permission rule.

## A deploy 504 "another deploy in progress" is a wait, not a retry

A platform deploy that fails with a 504 saying another deploy is in progress usually clears by itself. Check the
deploy status (and what that other deploy is) before retrying; a blind retry can queue a duplicate or race the first
deploy. Separate it from a 504 that recurs at a fixed duration with a growing artifact, which is a size or timeout
problem, not contention.

## Cross-references

- `dependency-currency-and-upgrades.md` — the other half of domain K (build,
  supply chain, safe version bumps); this file never restates it.
- `merge-operations.md` — **merge trains** and the **red-base
  discharge** recipe: when the target is red and a green-base-required preflight
  blocks the fixes that would green it, the discharge is a merge train, not an
  `--admin` override. The merge mechanism lives there; this file never restates it.
- `agentic-delivery`'s `references/roles.md` **Release** section (if that
  overlay is installed) — the authoring-time counterpart: tag a flag's category
  and set its removal date **when it is added**, not only when a later review
  finds it stale.
- `role-coverage.md` **Platform / DevOps / SRE** lens — SLI/SLO/error-budget/
  burn-rate, the reliability contract a release ships into.
- `performance-db-cost.md` §"Schema & data migrations (safety)" — the deploy-time
  safety of the schema change a release ships: expand → migrate → contract, the
  lock/rewrite hazards, and a tested rollback. Release checks the rollout; that
  section checks the migration inside it, reviewed there even when the PR carries no
  query-performance change. This file never restates it.
- `docs/standards-index.md` — DORA, feature-toggle, canary, and blue-green
  citations with fetch dates.

## Gate tooling and hooks (read when reviewing a repo's own gate scripts, harnesses, hooks or caches)

- **Scrub the tool's own config.** A harness that runs a checker must clear that tool's own config and mode env vars
  (and config files found by upward search) before running; otherwise the operator's shell silently changes what the
  gate checks.
- **Gates fail closed.** Infra failure and empty evidence are "could not check" (`merge-operations.md`). A fallback
  that returns success on a missing input, path or file exclusions, and retried-until-green steps are the same hole.
- **One acceptance rule for cache and consumer.** The code that decides a cache entry is a hit and the code that
  consumes it must share one predicate (key, version, freshness, validity); two copies drift until the cache serves
  what the consumer would reject.
- **Gate integrity: a pass covers the scope it claims.** Four checks, each a case of the positive-control rule (`full-map.md`
  principle 2; planted-defect probe in `method.md`): a pass is evidence only for what the gate could see.
  1. *Scope = key = receipt = update path.* The scope a gate ran (full vs changed files, which suites, which
     platforms), the cache key it reads and writes, and the receipt it emits must name the same scope. A narrower run
     never writes a result under a wider key, or a later full-scope run reads the narrow pass as its own.
  2. *Populate and copy steps check status and write atomically.* A step that fills a cache, artifact or receipt
     checks the producer's exit status before storing, and writes atomically (`concurrency-shared-state.md`); a crash or failed
     producer otherwise leaves a partial entry that the next run accepts as a hit.
  3. *A scanner lists the tree it claims.* Diff the scanner's actual file list against the tree it says it covers; a
     path gap (an exclude glob, a hidden directory, an untracked or generated path, a depth limit) is a finding even
     when every listed file passes.
  4. *Opt-outs are explicit, named and logged.* Beyond **Gates fail closed** (this section): skipping a check takes a named flag
     or config entry that prints what it skipped, never a silent default.
- **Select affected tests by the import graph, fail closed.** Choosing tests from changed paths by name or directory
  misses indirect dependents; walk the import graph, and when the graph cannot be built or a changed file is
  unmapped, run the full suite instead of none.
- **Seed a safety net.** A ratchet or regression gate whose first run only records a baseline judges nothing; seed
  the baseline (or fail the first run) and test that a worse value trips it.
- **Data is argv, never shell text.** Pass branch names, titles, paths and other external data as separate argv
  elements; interpolating them into `bash -c` or `sh -c` strings is command injection and breaks on spaces.
- **Machine-wide lock for shared-state jobs.** Jobs that touch the same checkout, port, cache or database take one
  machine-wide lock that records its owner pid and reclaims a lock whose pid is dead; a per-process or per-run lock
  protects nothing, and a lock that never reclaims wedges after a crash.
- **Hooks verify against the artifact.** A hook or checker that accepts a claim ("tests pass", "reviewed") must read
  the real artifact or receipt (file, exit code, SHA it names) rather than the claim text; an explicit
  `not run (reason)` is allowed and recorded, silence is not.
- **Zero counts need proof the run finished.** Wherever a test-run log is parsed into pass/fail counts, "0 failures"
  counts only after the exit status is checked AND the runner's completeness marker (its summary line) is present; a
  SIGKILLed or truncated log holds only the kill line and parses to zero. Fix every sibling parser of such logs, found
  by the class re-grep in `method.md`, not just the one that bit.
