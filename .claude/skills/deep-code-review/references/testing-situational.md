# Testing — situational checks

Read this when `testing-and-evals.md` routes here: a doc-comment promises a fallback or several behaviors, a conflict resolution landed, property tests, fuzz targets, or a coverage figure carry the assurance, an equality assert hangs or times out, a test shells a real binary, the suite has flaky tests, retries, or fixed sleeps, a spawned job sends an alert, N sibling checks are copy-pasted, a store has interchangeable backends, a fix rests on one green run, a gate needs gitignored data, a diff loosens an assert-absent test, a lint gate is scoped to changed files or compares a warning count/cap, a test reads a live system probe (memory, load average, clock, git log), or a load/swarm/soak test harness reports a failure or a throughput/success count. Split from `testing-and-evals.md`; its taxonomy and core smells apply first, and bare "above" / "below" point within this file.

## Test smells that fire only on a matching target

- **Before you write that fallback test, confirm the fallback *exists*: a doc-comment can enumerate a branch the body never implements — so there is no code for a dead-code or coverage tool to flag.** `testing-and-evals.md`'s test-the-failure bullet assumes the fallback is present and merely unexercised; the sharper defect is a docstring that promises resolution/degradation steps in sequence ("matches exactly, else falls back to a fuzzy/alias match, else gives up"; "on timeout, retries against the replica") when the body implements only the first step and unconditionally returns the not-found/error result otherwise. The described branch has **no code path at all — only its description exists** — which makes it invisible to exactly the tools a reviewer trusts: a dead-code or lint pass sees **no unreachable statement** (there is no branch to flag), and coverage stays **green** (there is no line to leave uncovered).
  Fixtures never expose it either, because the primary path satisfies every already-normalized value the suite and today's production data happen to carry; the gap only bites when a real user or a new data source supplies the more natural input the fallback was *documented* to handle, and a resolvable reference then silently degrades (to unlinked text, a hard error, an unhandled timeout) with no signal. Only reading the doc **against** the code catches it.
  Detection is mechanical: for every exported symbol whose doc-comment names more than one behavior / fallback / error, list each promised branch, grep the body for a corresponding code path, and confirm a test **forces its triggering condition** — a promised branch with neither code nor test is the finding (trying to write that forcing test is itself what surfaces the absence: there is nothing to make it pass). Report it even when today's data can only ever reach the primary path — "currently unreached" is a property of today's fixtures, not of the code's correctness — at reduced severity, but state plainly whether it is reachable now (same latent-but-reported discipline as `data-quality.md`'s bare-id merge rule).
  Fix by implementing the branch (with the forcing test above) **or** by correcting the comment to claim only what the code does; the doc fix is cheap and is **never skipped even when the real fix is deferred**, because an inaccurate contract comment actively misleads the next caller — who relies on it *without* re-reading the implementation — into depending on behavior that isn't there, which is worse than no comment. This is **not** the stale-comment case (a comment that was once true and drifted — e.g. a suppression/allowlist entry's justification that has gone stale; `method-situational.md`'s carried-forward-justification rule) — it was never true — and **not** `security-ai-agents.md`'s asserted-but-unenforced safety property (there the code exists at the call site and a lower layer drops it; here there is no code for the promised branch at all); it is the source-doc-comment, test-limbed specialization of `docs-and-dx.md`'s "reconcile load-bearing claims against the code." A claim whose code exists but whose guarantee no test pins is `method-situational.md`'s claim-vs-code lens.
- **A passing type-check / compile is a *partial* gate — after a conflict
  resolution on a long-behind branch, run the full suite.** A clean compile proves
  the tree type-checks, not that it still *behaves* as pinned. A three-way merge can
  be type-correct yet wrong: the branch pins a behavior with a test asserting a
  specific behavior (an emitted event name, a serialized field, a default value) the other
  side refactored away; the resolution compiles against the new shape while a
  behaviorally-pinned test still asserts the old one — the type checker never sees
  it, the suite does (and the longer the branch was behind, the likelier). Classify
  a type-check / compile pass as **necessary, never sufficient**; run the behavioral
  + regression suite after a conflict resolution before declaring it correct. When a
  pinned test breaks under the resolution, treat it as a signal to re-examine the
  resolution — **not** a cue to delete or "update" the test to match the merged code
  (it may pin behavior the other side still depends on).
- **A changed-files-scoped lint's zero output is not "zero findings" — it can mean the
  lint never ran on the file that matters.** A lint configured to run only on files a diff
  touches reports nothing for a type-aware/cross-file rule that fires in an **unchanged**
  caller of a changed symbol (a signature change surfaces a type error three call sites
  away, none of them in the diff). Reading that empty output as "clean" and citing an
  already-near-cap warning budget as "pre-existing, nothing to do" is the trap — two
  observed lanes did exactly this, and a **full-scope** lint run (not changed-files-only)
  found the real count higher by several warnings, entirely in unchanged callers. **Never
  raise a lint/warning cap in a feature change** to make a partial-scope run pass — compare
  **full-scope lint count on the branch against full-scope lint count on the base**, and let
  the diff-scoped run be a fast pre-check only, never the number a cap decision is made on.
  **Check:** the cap file is unchanged, and `full-lint(branch) <= full-lint(base)`.
- **A property test whose generator encodes the invariant it checks is
  tautological.** If the input generator is built from the same rule the assertion
  verifies, it can never produce the case that violates it — the test passes
  vacuously and guards nothing. The generator must sample the input space
  **independently of the property's *conclusion*** — constraining it to the property's
  **precondition** (only sorted inputs for a sort property, only valid emails for a
  formatting property) is legitimate and often necessary; the smell is specifically a
  generator built from the same rule the **assertion** checks, so the violating case can
  never be generated and the test passes vacuously (the property-test sibling of the mocked-into-a-tautology
  integration smell in `testing-and-evals.md`).
- **A deep-equality assertion on a large or *cyclic* object graph can *hang* the runner
  instead of failing fast.** Passing a big, deeply-connected, or self-referential object as
  the `actual` value of an equality assert (`assert.deepEqual`, `expect(node).toEqual(...)`,
  an `assertEqual(node, expected, msg)` with the whole live node as the first arg) makes most
  assertion libraries **deep-traverse and pretty-print** that value to build the failure diff —
  and on a large or circular graph that formatting step blows the test-runner's per-test
  timeout, so a check that *should* fail in a millisecond instead **times out** with no usable
  diff and reads as a slow/flaky suite rather than the real assertion failure. The trap is
  worst exactly when the assert is *meant* to fail (the value is wrong), because the failure
  path **is** the expensive-formatting path — a passing run never triggers it, so it slips
  every green CI. Assert on a **small scalar drawn from** the object — an `id`, a `length`, a
  status flag, a bounded serialized projection — never the live node itself; if structure must
  be compared, snapshot a **bounded, acyclic** projection. (A cyclic graph also throws
  `TypeError: Converting circular structure to JSON` under a naive `JSON.stringify` expectation
  — a louder symptom of the same "don't hand a live object graph to a formatter" root cause.)
  Distinct from `testing-and-evals.md`'s meaningful-assertions bullet: that asserts too *little*; this asserts on too
  *much*, and the whole cost lands on the failure path where no green run exercises it.
- **Mutation testing when a coverage number is doing the assurance work.**
  Line/branch coverage shows what *ran*, not whether a test would *catch a fault*
  in it (`pitest.org`); a suite can hit a high percentage and assert almost
  nothing. When load-bearing logic leans on a coverage figure as its assurance,
  measure the **product suite's** fault-detection with **mutation testing**
  (distinct from self-testing a *gate* against a planted defect, `testing-and-evals.md` — this
  scores the shipped tests, not the checker): seed small faults and read the
  **mutation score** (percentage of mutants killed). A **surviving mutant is a
  finding in this method's own shape** — a `file:line` plus the exact behaviour no
  test asserts (a High-confidence weak-assertion finding, not a style nit); triage
  survivors on critical paths first. Name the technique + the CI operator (e.g.
  Stryker's `thresholds.break` — it exits non-zero below a set score, but
  **defaults to `null` = never fails the build**, so it fail-closes only once you
  *set* it (the `high`/`low` thresholds default to 80/60 and merely colour the
  report — a decorative gate if mistaken for one; cross-ref the fail-open severity
  axis); choose the break value per repo, do not import a number) rather than a
  single tool; representative engines are **Stryker** (JS/TS) and **PIT** (JVM),
  plus per-language equivalents. **Bound it to the highest-stakes modules** — a
  mutation run scales with suite size × mutant count, so a repo-wide mandate is an
  over-ask.
- **Continuous, coverage-guided fuzzing as CI infrastructure — not a one-off property
  test.** The taxonomy in `testing-and-evals.md` lists property/fuzz as a *shape*; the assurance that finds
  *new* bugs is a **coverage-guided fuzzer run continuously** (OSS-Fuzz / ClusterFuzzLite,
  `go test -fuzz`, `cargo fuzz` / libFuzzer, Atheris), mutating inputs against live
  coverage feedback so it keeps finding crashes indefinitely — a different assurance than
  a hand-written property test that exercises its own corpus once. OpenSSF Scorecard's
  Fuzzing check (**"Risk: `Medium` (possible vulnerabilities in code)"**) reasons that
  "Regular fuzzing is important to detect vulnerabilities that may be exploited by others,
  especially since attackers can also use fuzzing to find the same flaws." (Scorecard also credits non-coverage-guided property-testing libraries — fast-check, QuickCheck/Hedgehog, proper, FsCheck — so a passing Scorecard Fuzzing score alone is not evidence of *continuous coverage-guided* fuzzing; apply the wired-to-CI + crash-corpus bar below regardless of the score.) The review
  question is not "is there a fuzz target" but **is it wired to a job that runs on a
  schedule / in CI, and does a crash reach a human** — findings triaged into a committed
  **crash corpus that becomes regression tests**, not a log nobody reads. A fuzz target
  defined in-repo but attached to no fuzzing job or service is **decorative** — the same
  "a gate must be proven to run" bar mutation testing (above) and gate self-tests (`testing-and-evals.md`) are held to.
  Scope it (like mutation testing above) to the highest-stakes parsers / decoders /
  deserializers / protocol boundaries, where input reaches attacker-controlled bytes.
- **A test that shells a real external binary must probe it for functional success
  and skip loudly on any failure — not merely check the binary is on `PATH`.** CI is
  "present but different/broken," not "absent": a bare presence check (`which chrome`,
  `command -v ffmpeg`) only proves the binary **exists** — it never executes it; the test
  then invokes it for real — a headless browser, `git`, `ffmpeg`, a database CLI —
  and that invocation can fail for reasons a presence check never sees. A
  headless-Chromium binary running as root in a container commonly needs its
  sandbox set up explicitly (a non-root container user, or an explicit launch flag)
  or the launch crashes before it renders anything; a `git commit` depends on a
  resolvable `user.email`/`user.name` and can fail outright rather than silently
  falling back — verified directly in a scratch repo: forcing the identity to an
  explicit empty string (`git -c user.email= -c user.name= commit`) raises `fatal:
  empty ident name (for <>) not allowed`, exit 128, while the same repo and command
  with a real identity supplied inline (`git -c user.email=… -c user.name=…`) exits
  0 regardless of the runner's ambient config. Two requirements: (1) gate on a
  **functional smoke** — the binary actually produced the artifact or exited 0 on a
  trivial real invocation — giving a required *binary* the same discipline
  `testing-and-evals.md` gives a required *input*: **skip loudly** with the captured
  failure, never a silent pass; (2) the test **supplies its own required launch
  configuration** explicitly rather than inheriting the runner's ambient defaults —
  `git -c user.email=… -c user.name=…` against its **own temp repo**, an explicit
  launch flag for a browser harness rather than assuming the CI image happens to
  have the sandbox pre-configured. Distinct from the
  network/DNS/clock/tmpdir hermeticity in `testing-and-evals.md` (the test's *own* execution
  environment), the test-double-fidelity rule there (a **mock** drifting from a
  **live service**'s contract — this is a **real binary**, present, behaving
  differently under CI), and the verification-gate cannot-check rule
  (`reliability-error-handling.md` — governs how a gate **reports** its own harness
  crashing at setup; this governs the test's **probe**, so the crash is caught by a
  functional check and prevented by explicit config up front rather than merely
  reported after the fact).
- **A test that reads the real machine (RAM/swap, load average) or replays real recent git
  history is a fleet-wide flake generator, not a CI-hermeticity edge case.** Two distinct
  unpinned-input shapes recur: (1) a test that asserts on `sysctl`/`/proc/meminfo`-style
  live memory or load-average reads — the value is whatever the runner happens to have free
  *right now*, different on every machine and every run, and a threshold tuned on one box
  fails on a busier one; (2) a test that samples "the latest N commits" from the real git
  log and replays them — the sample silently changes as the branch moves, so the same test
  name exercises different inputs run to run. Both produced real failures (one observed
  spread: 5 union failures across 2 unrelated changes, traced back to these two shapes).
  **Mock the system probe** (inject a fake memory/load reader) rather than reading the real
  machine, and **pin the sample** — an explicit list of commit ids, not "the last N" — so a
  moving branch can't change what a test exercises. **Check:** flag an unmocked
  memory/`sysctl`/load-average call and an unpinned "latest N commits" git-log sample inside
  a test file. A real wall-clock or timezone read (`Date.now()`, `datetime.now()`, `time.Now()`, shell `date`) with no fake clock in the file is the same shape, red at the next week rollover: `agentic-delivery/scripts/clock_lint.py` flags it, and the future-clock run in `agentic-delivery/references/verification-handback.md` exposes it. It also prints an advisory for a test asserting day/week-relative text ("No demos yet this week") with no fixed clock; the fix is `page.clock.setFixedTime` (silences the advisory only; it does not fix the runner's own clock reads), `useFakeTimers` plus `setSystemTime`, or `freeze_time`. The same script flags timing bets in Python tests (`time.sleep(N)` then an assert, `timeout=` of 5 s or less, `assert elapsed < N`).
- **A test service owned by one gate run breaks every concurrent run on the machine.** A fixture database that a gate run starts if absent and kills on exit is shut down under the other runs by whichever finishes first, and the resulting connection errors (for example Postgres `57P03`, "the database system is shutting down") read as flaky tests. When lanes share a machine, start shared test services detached, or ref-count them so only the last user stops them. Finding: a gate that stops a service it did not exclusively start. Test: two overlapping runs both pass when the first exits early.

- **Evidence gate accept-predicate audit.** For each gate that accepts free text or a URL as evidence (a
  justification, an image, a receipt), state what the predicate verifies. A form-only predicate (length, regex,
  URL syntax, presence) is a finding quoting the exact bypass input. The gate's own test needs at least three
  adversarial inputs: a short justification, an unreachable URL, an artifact bound to a different commit.

- **A chronically flaky test is quarantined and fixed, not retried until green.** A test that
  passes and fails on the same code is a real signal (a race, an order/time/network dependence,
  a leaked fixture) — a blanket **retry-until-green** in CI masks it, manufactures false
  confidence, and once the team learns to re-run red a *genuine* regression hides in the noise.
  Move a known-flaky test to a **non-blocking quarantine** with a named owner (not a placeholder such as "unassigned") and an expiry date that the gate reading the quarantine list fails on (an unowned or expired entry is a finding, not a permanent dumping ground), and fix the underlying nondeterminism (pin the
  clock/seed, remove the shared state, await the real condition instead of `sleep`). A standing
  CI retry count `> 0` used to paper over flakes — rather than a bounded retry on a genuinely
  external flake with the rate tracked — is the finding.
- **Reproduce a suspected flake under CPU throttling before calling it a flake.** "Flaky" is a conclusion, not an
  observation: rerun the failing test under load it can lose to, e.g. an 8x CPU throttle through the browser
  devtools protocol for a UI test, or a stress load (`stress-ng`, parallel busy loops) for any other. A failure that
  reproduces on demand is a deterministic bug with a trigger, not noise; a failure that never reproduces under
  throttling stays unexplained and is not closed. Typical root causes: a **readiness race** (the test acts before the
  app or service is ready), **hydration before click** (the click lands on server-rendered markup before the handlers
  attach), and **layout shift** (the target moves between locating it and acting on it). Fix by awaiting the real
  condition, never by retrying.
- **A fixed-duration `sleep(N)`-then-assert is a timing bet a busy CI lane loses — assert the
  observable readiness signal, not wall-clock duration.** The wait assumes N ms always suffices;
  under multi-lane CI (several jobs contending for the same host's CPU) the identical operation
  that finishes in 50ms alone can take 600ms starved, so a 500ms wait flakes only under load —
  never locally, where nothing contends — and reads as environment noise rather than a timing bug
  in the test itself. Poll for the actual condition (an emitted event, a changed node, a resolved
  promise) with a generous upper bound; never assert against a fixed sleep. Distinct from the
  chronically-flaky-test bullet above — that is the *triage* once a test is already known-flaky
  (quarantine + fix root cause, one clause of which is this same await-not-sleep fix); this names
  the CI-contention *trigger* so the test is authored correctly the first time.
- **A tiny fixed deadline in a test is the same bet: it passes idle and fails under load.** A 1 ms
  deadline or timeout assertion holds on a quiet machine and flakes on a busy runner. Give time-dependent
  tests a deadline in the hundreds of milliseconds, or inject a clock so the test controls time and never
  waits on it.
- **Testing an outbound alert/webhook from a spawned job needs async spawn + a
  localhost listener.** The natural test — run a scheduled/unattended job to a
  failure and assert its alert fired with a privacy-safe body — deadlocks under
  `spawnSync`: the blocking call freezes the test's event loop, so an in-process
  `http.createServer` can't accept the child's POST *during* the run and the
  request is never captured. Use async `child_process.spawn` (await `close`) so the
  loop services child and listener concurrently; collect requests into an array and
  assert after close. Keep it localhost (`127.0.0.1:0`, random port — no external
  traffic) and assert the body carries only aggregate/privacy-safe fields (terminal
  state, exit code, failed step *names*), **not** the failing command's output.
  Pairs with domain W's liveness-alert requirement — the alert must exist; this
  proves it fires, correctly and safely.
- **When one check is copy-pasted per sibling field/type, diff the copies' *guard
  conditions*, not just their overall shape.** A reconciliation or diff check — compare an
  authored/declared value against a derived/computed one and flag disagreement — is often
  written **separately for each of N sibling fields or entity types** (one block per column,
  per resource kind, per metric), the N blocks near-identical but for the field they name.
  Read one at a time, every block looks internally consistent and plausible, so the review
  waves each through. The bug that hides here is a **dropped edge-case guard in exactly one
  copy** — an `if (authored == null) continue`, a "skip legacy rows", a rounding/tolerance
  clause, a "both sides present" precondition — that the *other* copies keep and this one lost
  (a bad merge, a hand-edit, a copy taken before the guard was added). It leaves **no idiom to
  grep** (the copies differ by design, by field name) and no single copy reads as wrong; it is
  visible only **relative to its siblings**. Detection: line the N copies up and **diff their
  guard/branch conditions against each other**, treating the set as mutually cross-checking —
  the copy with one fewer guard clause than the rest is the finding. Fix: collapse the N copies
  into **one parameterized check** (the no-duplication cure — then there is one guard set, not
  N to keep in sync); if they must stay separate, restore the missing guard and add a test that
  pins the shared precondition across all of them. Distinct from the outward/inward completeness
  sweeps in `method-diff.md` (those propagate or verify **one fix** across the tree or within the
  fixed file, greppable by a shared idiom; this cross-diffs **N pre-existing parallel copies**
  whose only shared signal is their *structure*, driven by no fix), from the coherence test
  in `testing-and-evals.md` (which runs one fixture through mirrored paths asserting *identical* output —
  inapplicable when each copy targets a different field), and from the sentinel-sibling
  comparator in `lang-js-ts.md` (value-set completeness inside **one** function;
  this is guard-set parity across **N** functions).
- **A store with interchangeable backends fails on the one the tests never instantiate — and a
  faithful fake cannot catch it.** When one interface has several implementations chosen at runtime
  (an in-memory/file store for dev/CI, a SQL database in prod), a field added to the model must be
  threaded through **every** backend's write/read/serialize path. The trap is that this is *not* a
  drifting double: the in-memory store keeps the whole object, so it retains the new field for free
  and has **no place for the omission to live**, while the SQL backend carries a failure surface the
  fake's mechanics don't possess at all — a hand-written `INSERT`/`UPDATE` column list (or a
  migration, or a DTO mapping) with no compile-time tie to the model type, so the field is silently
  dropped on the production path while every test stays green. The check a reviewer skips: **a green
  run proves nothing until you read which implementation the harness instantiated** — that lives in
  the test config, not the diff, and if it's the fast fake, the SQL path was never run. Detection:
  grep the SQL backend's `INSERT`/`UPDATE`/`SET` (and any history/mirror sync) for the new column — a
  field present in the type but absent from an `UPDATE`'s `SET` is the signature — and round-trip the
  new field create→edit→read-back through the **production** backend, not the default fake (the
  both-paths coherence test in `testing-and-evals.md`), or derive the column list from the type so it can't drift.
  Distinct from the test-double-fidelity rule in the taxonomy (a double whose *returned shape* is
  wrong; here the fake is behaviorally correct, just more permissive than the real store) and from
  `data-quality.md` §6's dual-registered-entity rule (which store *owns* a field across two co-existing
  stores; this is one write through one of two implementations of the same store).
- **A load/swarm test harness's own failure needs classifying before it's filed as a product bug.** A
  harness simulating many concurrent users/agents has its own failure modes (client-pool exhaustion, a
  concurrency bug in the harness, a resource the harness itself contends on) that produce a signal
  indistinguishable from a real one without digging — treating every hiccup as a product bug wastes
  investigation time, but assuming every load-test failure is "just the harness" can bury a real
  concurrency bug that only shows up under load. Before filing: (a) check the actual backing store/API
  directly for the state the failure implies — was data really corrupted/lost, or did the harness only
  report a timeout on its own client — and (b) run a second, decorrelated pass (different harness
  process, different timing) to see if it reproduces independently of the first run's conditions. Split
  "not a real bug" further, since each bucket needs a different fix: **acked but missing** (app returned
  success, record genuinely absent from the store — the one real bug class); **stored but not shown**
  (the record IS in the store; a read path — cache, denormalized view, UI query — isn't surfacing it, a
  read-side bug); **harness misread** (record correctly stored and readable; the harness's own check
  looked at the wrong key/shard or read before an intended delay, a test bug); **never acked** (the write
  never reached the app successfully — rejected, timed out, dropped in transit — an environment/harness
  issue). Record which bucket applies, and re-run the decorrelated pass with that classification, before
  scoping any fix — collapsing 2-4 into one "harness-artifact" verdict risks sending the fix to the wrong
  layer (e.g. patching the write path for what's actually a stale-cache read bug).
- **A load/soak/swarm harness that doesn't authenticate its writes, or checks the store only once,
  reports numbers that aren't real — in both directions.** A harness hammering an app with simulated
  writes (votes, submissions, orders) and counting "succeeded" by HTTP response alone hides two failure
  modes invisible from its own summary: simulated clients hitting an endpoint **unauthenticated** (no
  session/token) that the backend accepts or silently no-ops before storage — a false success reported as
  throughput; and an end-of-run existence recheck that reads the store **once, immediately, with no
  retry** — so a real write with any replication lag or async fan-out reads as "missing" and is
  miscounted as a failure, a false failure. Both trace to the same root: the harness trusted a
  transport-level signal (a response code, one immediate read) as a proxy for the durable, queryable
  outcome that actually matters. Fix: route every simulated write through the same auth path a real
  client uses; add a per-write (or batched) acknowledgment check against the actual store, not just "the
  call didn't error"; make the end-of-run reconciliation retry-with-backoff before declaring a
  discrepancy; and emit a **dispatched-action count broken out by kind** as a first-class harness output
  — a category showing zero dispatched actions is almost always a harness bug (a filter, a wrong
  fixture, a broken generator), not a true zero in the system under test, and a harness that doesn't
  report per-kind dispatched counts can't be told apart from one that silently generated none of that
  kind at all. Test the harness itself against a fake backend that silently drops unauthenticated writes
  and delays visibility of real writes by a short window: it must report the dropped writes as failures
  for the right reason (auth, not "unknown"), must not misreport the delayed-visibility writes as lost,
  and must emit a non-zero dispatched count for every category driven.
- **A single-process throughput ceiling measured on a shared, unrecorded host, with a client
  timeout shorter than the server's real response time, produces a number nobody can trust.**
  Three confounds hide inside a load-generator's own summary output: (1) a competing process on
  the same host (a file/search indexer, a virus scanner, another test suite, a backup job)
  consumes a large, variable share of CPU/disk during the run, so the measured number reflects
  contention with that process rather than the service's real ceiling; (2) the run recorded no
  system load average / CPU / IO alongside the throughput number, so nothing after the fact can
  tell a low number caused by the service apart from one caused by a noisy neighbor; (3) the
  load-generation client's **own** request timeout is shorter than the server's real (slower but
  successful) response time for some requests, and those get counted as client-side timeouts
  folded into the same failure bucket as genuine server-side 5xx errors — conflating "the client
  gave up waiting" with "the server broke," opposite conclusions about where the bottleneck sits.
  **Detect:** a throughput/benchmark result with no recorded load-average/CPU/IO for the run
  window, no stated check that the host was otherwise idle, or a single "failure" count that
  doesn't separate client-timeout from connection-error from server-error-code. **Fix:** confirm
  the host is quiet (or explicitly report concurrent load as a caveat) before trusting a number;
  set the client's timeout comfortably above the slowest acceptable successful response; break
  failures down by cause. **Test:** **Free memory decides whether a perf number can be trusted:** at about 235 MB free, the same commit swung an RSS slope 34 times past its budget. Before any perf run or bisect, measure the noise floor by running the same commit twice, and refuse to run below a free-memory threshold. **Confirm a suspected regression before bisecting:** compare baseline against head, interleaved, with N of at least 3, and bisect only if the gap exceeds the measured noise floor. run the identical, unchanged service twice — once with a
  synthetic background CPU load competing, once without — and confirm the two runs report visibly
  different load-average readings alongside their throughput, so a review rejects an unqualified
  "before/after" throughput comparison whenever the load readings differ; separately, drive a
  deliberately slow-but-successful server response through a client configured with a shorter
  timeout and confirm it's reported under a distinct client-timeout category, never merged with
  true server errors.

## A green run is a sample, not a proof, when the trigger is nondeterministic or the run is too costly to repeat

Some fixes can't be validated in one session: a **nondeterministic trigger** (a browser
degradation that appears ~1 run in N), or a validation run so long (~20 min each) that one pass
is not proof. Shipping such a fix on a **single green run is a false "done"** — the failure
recurs later, far from the change. **Distinguish "validated" from "happened to pass once,"** and
label accordingly.
- **Ship the part you *can* validate** — e.g. crash-recovery for a *reproducible* mid-pass browser
  death, validated by catching a real crash and re-running the pass on a fresh browser.
- **Name the part you can't** as a **Known-limitation** in the PR body, with a concrete proposed
  follow-up (e.g. a per-pass timeout routed into the existing discard-and-retry path) — explicitly
  deferred because its trigger is nondeterministic and unvalidatable in one lane. A **named
  residual is honest; a silent one ships a false "done."**
- **Don't let "while I'm here" scope-creep** bolt an **unproven** refactor onto an
  otherwise-validated PR — it re-buries the validated change under unvalidated risk; make it a
  separate, properly-validated change.
- **Symmetric with the placebo.** The same judgment that refuses an *unvalidatable* fix also
  refuses one **proven not to work** (a "lower the concurrency" change that still crashed). Ship
  only what you've shown to hold; everything else is a named residual or a separate change.

This *ran-green-but-once* residual and a *deferred / never-run* gate (`parallel-audit.md`'s "an
unrun matrix is `unverified`, not a pass") resolve the same way — **name the residual, never a
silent pass** (`full-map.md` principle 2: an absence is evidence only after a positive control fires);
they differ only in cause — here the gate ran green *once*, there it never ran.

## A gate's committed fixture is part of its contract — a clean-clone gate must be satisfiable without the gitignored data

A gate that asserts real-data-shaped output — required copy, a populated section, a field's
presence — is honest on a clean clone only if the **committed fixture** can produce what it
checks. If the sample fixture omits the fields the assertion needs (they live only in the real,
gitignored bundle), the gate is **red on a clean clone by construction**: green for anyone
working from a populated checkout, red for everyone on a fresh clone/worktree, while the repo's
own "green `verify` from a clean clone" Definition-of-Done claim is quietly false.

The committed fixture is part of the gate's contract. Resolve it one of two ways:
- **Enrich the fixture** so it exercises every field/section the gate asserts (a clean clone can
  render every required-copy check), or
- **Scope the real-data-only assertions to a real-bundle run**, and on the clean-clone run assert
  only what the fixture can produce.

Verify by running the gate from a **truly clean clone** (no gitignored data present), not from
your populated tree: red there means the fixture or the assertion scope is wrong, and any "green
from a clean clone" claim stays `unverified` until it holds — the resolving artifact is the clean
run, not the convenient one (`full-map.md` principle 3). **Signal:** when several contributors
independently hit the *same* gate failure and each "fixes" it by copying the real gitignored data
into their checkout, the defect is the fixture/gate contract, not their environments — the
workaround masks a standing Definition-of-Done violation.

## A negative-assertion (assert-absent) test is a ratified constraint — never loosen it to ship a conflicting feature

A test that asserts something is **absent** — `assert.doesNotMatch(brief, /ProgressBar/)`, "no
attainment %", "no dashed drop-target" — encodes a **deliberate, often-ratified design
constraint**: *this surface must not show X.* When a new feature request conflicts with one
("add progress bars" vs a Brief that pins **no** `ProgressBar`), an agent faces a fork:
- **Wrong:** delete or loosen the guardrail to make the feature pass — the code-review equivalent
  of pulling the smoke detector. It **silently reverses a ratified decision** and removes the very
  record that decision left behind.
- **Right:** read the negative test as **evidence the constraint is intentional** — ship only the
  part that doesn't violate it, and report the conflicting part as **BLOCKED-ON-OWNER** (they can
  split / reopen, or loosen the test themselves, explicitly). (Observed: a lane asked for a live
  OKR dashboard added the honest **coverage** stat but **not** an attainment-% meter, because a
  guardrail test pinned the omit-percentage contract — a test-layer enforcement of *show coverage, not
  a grade* in `ux-dataviz.md`.)
- **Review lens:** a diff that **loosens or removes an assertion — especially an absence
  assertion — while adding a feature** is a red flag: check whether it silently reverses a
  recorded decision. Changing a ratified constraint is an **explicit, owner-visible** decision (its
  own reasoned commit), never a side effect of a feature PR. Distinct from the retired-coverage
  case in `testing-ui.md` (a spec dropped because its surface became *unreachable*, owed a named gap): here the
  surface is reachable and the constraint is **still intended** — the test is not stale, it is
  load-bearing.

## A structural test anchored to a named neighbour breaks on that neighbour's rename, not on its own regression

A test that slices a sequence of steps/sections/phases by name — "everything between marker `X` and
marker `Y`" — is really testing **its own boundary**, and naming the *next* structural element after
it (`Y`, a sibling step's own name) makes that boundary depend on a name the test doesn't own. One
observed break: a step's structural test named its **sibling's** marker as the slice's end, and
renaming that unrelated sibling — no change to the step under test — broke the test. **Rule:** slice
from a marker's own start to the **next** marker generically (positionally — "the next heading",
"the next `## ` boundary" — not by that neighbour's literal name), never by a specific neighbour's
name. **Pass condition to check for:** renaming any *other* step/section keeps the test green;
renaming or removing the step actually under test is the only thing that should break it.

## A new test is "ready" only after repeat passes on fresh state, ships apart from unrelated changes, and never gets "fixed" by retargeting at a legacy surface

Three ways a new or repaired test hurts other people's work. Flag each in a diff review:
- **One green run is not "ready."** A new test that passed once and merged inside a larger batch fails
  intermittently on unrelated PRs later, and the flake costs more to diagnose than it would have before
  merge. Require a fixed repeat count (for example 3 of 3) on cold/fresh state as evidence, and treat a "ready"
  claim backed by a single run as unverified. A test that is flaky on that bar ships in its own PR with the
  flake tracked as a known issue, never bundled with unrelated functional changes.
- **A fix that changes which page, route or URL a failing spec targets is a finding.** Pointing a spec that
  failed against a rebuilt surface back at the old surface (still reachable behind a flag or route) turns the
  suite green by deleting the coverage, and the real defect in the new surface stays invisible. If the new
  surface genuinely is not ready for that check, mark the spec with an explicit skip/fixme that links a tracked
  issue describing the gap. A retarget with no linked issue is reported.
- **A test that asserts "some live record exercises branch X" rots when the data improves.** After a data
  cleanup fills every gap, the test fails with no code change. Build the case from a real entity (take a real
  record and clear the field) so the branch stays covered whatever state the data is in.

- **A comparison of two implementations needs a fixed protocol, not ad-hoc timing.** Same machine and data, a verified quiet window (load checked first), runs back-to-back, median of 3, and the CPU/RAM load level reported beside each number so a reader can tell a clean comparison from a noisy one. For user-facing latency, add a protocol-level load ramp plus a few real-browser runs; a server-side synthetic benchmark alone is not enough.

- **A completeness self-test ("every table/route/key is classified") needs its matcher run on a near-miss input.** A pattern like `[a-z_]+` silently drops names with a digit or capital, so the very item the test exists to catch is skipped and the test stays green. Feed the matcher one near-miss name (with a digit, a capital, a hyphen) and assert it is seen; an exact-match test should fail loudly on anything it cannot classify.

## Every test runner needs a per-test timeout

A runner with no per-test timeout lets one hung test block pushes and merge trains for hours (it happened twice in one project). Set a per-test timeout on every runner (unit, integration, end-to-end), well above the slowest healthy test, so a hang fails fast with a name instead of stalling the gate.

- **Split a test file every lane appends to.** A single hotspot spec that each parallel lane edits turns every merge into a textual conflict and serializes the train. Split it into per-feature spec files so lanes touch disjoint files. **Check:** list the files touched by recent merged PRs; one spec file in most of them is the hotspot.
