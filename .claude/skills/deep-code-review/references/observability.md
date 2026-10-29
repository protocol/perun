# Observability, audit trails & recoverability

Read this when reviewing logging, metrics, traces, dashboards, alerting, audit
trails, or "could we tell this broke, reconstruct who did it, and restore what
was lost." Expands section M of `SKILL.md`; the security-event slice is A09 in
`security-appsec.md` (log the right events, tamper-resistant, alerted), and the
failure paths that *produce* these signals are section F /
`reliability-error-handling.md`.

---

## Detection procedure

1. **Pick the two or three flows that matter** (the paid pipeline, the login
   path, the checkout/write path). For each: if it broke silently at 3am, what
   fires? Trace the answer to a real alert rule, not a dashboard nobody opens.
2. **Read the log lines on the failure path**, not the happy path — that's where
   raw request/response objects get dumped.
3. **Enumerate metric emitters**; read label/tag arguments for unbounded values.
4. **Find the audit trail** for destructive and privilege-changing operations,
   and check who can edit or delete it.
5. **Find the backup config, then the restore evidence** — a backup with no
   documented, dated restore drill is untested.
6. **A claim of absence needs proof the window held the event.** "No errors at startup" from a log query whose default
   page holds only the last ~30 events is unverified. Show the anchor line that bounds the window (the boot line of
   the exact deployment ID), then filter by deployment or page with an explicit time window; old-container shutdown
   errors are not new-container errors. No anchor means `UNVERIFIED`, not "clean".

---

## Golden signals & alerting

- Cover **latency, traffic, errors, saturation** per critical service or job —
  plus, for batch/pipeline work, *freshness* (time since last successful run) and
  *volume* (records processed vs. expected). Average latency hides the outage;
  use percentiles (p50/p95/p99).
- **Saturation's alert line is a utilization *target below 100%*, not full.** Systems
  degrade before a resource reaches 100% utilization, so alert on a target (often ~70-80%,
  workload-dependent), not saturation itself; track utilization / saturation / errors per
  constrained resource. Alerting only at 100% (or on `load average`) misses the degradation window. (The target
  is a *cause* alert: pair it with a *symptom* alert, below.)
- **Alert on the symptom, not only the cause.** "CPU > 80%" without "checkout
  error rate > 1%" or "no successful run in 2× the schedule interval" means a
  frozen job or dependency outage pages nobody. Cause alerts are for diagnosis;
  symptom alerts are the contract with the user. Each alert names an owner and a
  next action — constantly-firing alerts train the team to ignore the page.
- **Distinguish transport/quota failure from a substantive negative result.** A
  429/402/timeout recorded as "no match" or "score 0" silently corrupts metrics
  and downstream data (`data-quality.md`). Health/readiness endpoints must check
  real dependencies, not `return 200`.
- **Instrument LLM / agent calls as first-class telemetry, not just the host service.** An LLM or
  agent feature shipped with only service-level latency/error signals is under-instrumented:
  capture per-call **token usage** (prompt/completion), **latency** and **cost**, the **model +
  version** (and, for LLM calls, a **prompt version tag or template hash** — so a quality regression
  is attributable to the *prompt* revision, not just a model bump; `testing-ai-evals.md`), the
  **outcome** (success / error / refusal / empty / tool-call), and a **trace**
  spanning the agent's tool calls, so a failing or token-burning agent is visible — but emit
  **structured telemetry: counts and metadata, never the raw prompt/response payload** (redact per
  *Logs & traces* below; token *counts* need no prompt text). The **OpenTelemetry GenAI semantic
  conventions** (`gen_ai.*`) name these signals — adopt the convention **names** for portability,
  but that spec was **moved to a separate GenAI semantic-conventions repository** (the
  `gen_ai.*` entries in the main registry are now marked *Deprecated*), so **pin no version and
  re-fetch the current source before citing**. A
  silent, un-traced agent that errors or burns tokens with no signal is the finding (cross-ref the
  cost-and-value lens in `performance-db-cost.md`).

---

### Alert and notification paths

Probe the code that sends alerts, digests, or notifications for three defects: (1) **batch N>1**: a message built or
dedup-keyed for one item that mis-handles a batch of several (only the first reported, or one failure hides the
rest); (2) **a send returning false**: the sender reports failure by return value (not by throwing) and the caller
ignores it, so the alert is silently lost; (3) **mark-before-send**: the "already alerted" flag is persisted before
the send is confirmed, so a failed send suppresses every retry. Mark after a confirmed send, or use an outbox.

## Logs & traces: secrets, PII, injection

- **Redact by default**: an allow-list of loggable fields beats a deny-list of
  forbidden ones — over-logging is itself a vulnerability (A09). Left-behind
  `print` debugging is its own finding.
- **Audit a redactor's patterns against the gitleaks default rules**, not the vendors its author
  remembered; usual gaps: `anthropic-api-key`, `anthropic-admin-api-key` (`sk-ant-` keys),
  `airtable-personnal-access-token` (sic), `airtable-api-key`. Prove it: log a fake of each shape, grep the sink.
- Common leaks: whole request/response objects, `Authorization`/`Cookie` headers,
  bodies on 4xx/5xx, DSN-style connection strings in errors, LLM prompts with
  user data, stack traces with locals, query params carrying tokens or emails,
  error-tracker breadcrumbs.
- **Spans carry the same risk**: span attributes, DB statements with inlined
  literals, HTTP instrumentation recording full URLs and headers. A 1%-sampled
  secret is still leaked, into a third-party store. Log/trace retention counts as personal-data retention
  (`privacy-compliance.md`).
- **Head-based trace sampling limits what you can conclude — mind coverage, variance, and
  tail percentiles.** A fixed-rate, *pre-outcome* (**head**) sampler decides keep/drop
  before it knows the trace errored or ran slow. A *uniform* sampler's error
  *proportion* is still an unbiased estimate; the real problems: **(a) coverage** — you cannot guarantee a *specific* error trace was kept ("you
  cannot ensure that all traces with an error within them are sampled with head sampling
  alone", OpenTelemetry), so tracing is unreliable for "pull up *this* incident's traces";
  **(b) variance** — at a low sample rate the error/slow counts in a short burn-rate window
  are tiny and noisy, under-reading an incident more often than not; **(c) tail estimation**
  — a thinned tail makes p99/p999 unstable and biased. An *adaptive / load-shedding* head
  sampler that drops more under load is worse: it correlates keep/drop with system state,
  biasing the rate exactly when it matters. Fix: use **tail sampling** (decide "considering
  all or most of the spans within the trace", OpenTelemetry) with a policy that always keeps
  error / high-latency traces, and compute rate & latency SLIs from **unsampled** counters /
  histograms (the SLO/burn-rate lens in `role-coverage.md`), not the sampled trace set.
  (Distinct from the privacy point above — a sampled leak is still a leak — and from analytics event reweighting in `data-metrics.md`.)
- **Log injection**: user-controlled strings must be emitted as structured
  fields, never concatenated into a line — embedded `\n`/`\r` lets an attacker
  forge entries and break the parser (CRLF/log-forging, CWE-117 — name only,
  verify before citing). Key-value logging avoids this by construction.
- Correlation/request id propagated across services and present on every line so
  an incident can be reassembled; log levels used meaningfully. A shared **log**
  correlation id is **not** the same guarantee as an unbroken **distributed trace** —
  every service can stamp the same id on its logs while each still starts a fresh root
  span, so logs reassemble by grep but the trace backend shows N disconnected
  fragments, hiding where latency went. Verify separately: follow one
  request's trace id through every hop **in the tracing backend**, and confirm **one**
  trace, not N. The break is almost always at a hop without auto-instrumentation — a
  **queue publish, a cron / background job, an async or thread handoff** — where trace
  context must be injected into the envelope by hand (W3C `traceparent`) instead of
  riding an instrumented HTTP client; a boundary that starts a fresh root span
  silently blinds the trace until an incident needs it.
- **Telemetry carries a stable resource identity, or per-cohort analysis silently
  merges.** Every emitted signal (log, metric, span) should stamp *which service,
  version, and instance* produced it and *which environment/tier* it belongs to — the
  OpenTelemetry resource attributes `service.name` / `service.version` /
  `service.instance.id` / `service.namespace` and `deployment.environment.name` (all
  **Stable**), or an equivalent version+environment dimension. Distinct from request
  identity above (*which request*; this is *which emitter*); without it two things this
  skill demands elsewhere quietly break. A **canary's named
  halt metric** (`release-engineering.md`) is uncomputable as canary-vs-baseline unless
  the telemetry is partitioned by `service.version` (or a cohort tag) — you cannot
  regress-check a signal you cannot split from the baseline's. And **multi-window
  burn-rate SLO math** (`role-coverage.md`, SRE lens) corrupts when environments
  collide in one backend (the **default**, not an edge case): the OTel spec
  states `deployment.environment.name` "does not affect the uniqueness constraints
  defined through the `service.namespace`, `service.name` and `service.instance.id`
  resource attributes," so `service.name=frontend` in production and in staging
  "MUST be considered to be identifying the same service," and staging errors land in
  the production SLO unless an environment/namespace dimension separates them. **Verify:**
  the pipeline sets a stable service+version+instance identity and an environment tag; a
  canary or per-environment dashboard reading an unpartitioned metric is measuring a blend.
- **Audit the logs a platform injects, not only your app's log statements.** A
  managed platform often runs an nginx / auth-proxy **sidecar** in front of each
  app that logs, on **every authenticated request**, per-request user PII and the full
  permission-scope list — an authz dump the app itself never writes — to the
  platform's **shared** log store, while the application container logs none of it,
  so a review scoped to the app's code misses it. Read the **runtime**
  logs as actually emitted (app **and** the injected proxy), flag per-request PII /
  token material / authz-scope dumps to the platform owner (drop or
  redact), and treat a shared platform log store as a data-egress surface
  for user PII.

**Grep leads (tune to language):** `log`/`logger`/`console.log`/`print` followed
by `req`, `request`, `body`, `headers`, `user`, `token`, `password`, `secret`,
`apiKey`, `authorization`; `JSON.stringify(` inside a log call; `%+v`/`repr()`
of a request or config struct; `setTag`/`setAttribute` with a raw payload.

---

## Metric cardinality bombs

- Never use unbounded values as label/tag values: user id, email, request id,
  UUID, full URL path with ids, raw error message, SQL text. Each combination is
  a new time series — how a metrics bill or the backend falls over.
- Bound the label space: templated route (`/users/:id`), error *class* not error
  text, tenant tier not tenant id. Per-entity detail belongs in a log or trace.

**Grep leads:** metric/counter calls whose tag map includes `id`, `uuid`, `path`,
`url`, `email`, `err.message`, or a string-interpolated name
(`counter("job." + name)`).

---

## Metric type & shape correctness

- **A histogram/percentile can look measured and still lie, two ways.** A
  **classic (fixed-bucket) histogram** needs a bucket boundary exactly *at*
  the SLO threshold for a fraction-under-threshold query
  (`rate(..._bucket{le="0.3"}[5m])`) to resolve — Prometheus: no matching
  bucket means "no result is returned at all"; if only some of the
  aggregated histograms (e.g. some replicas) have one, "an incomplete result
  is returned, but without any warning…" Native/exponential-bucket
  histograms interpolate around this and largely avoid this silent dropout
  (the interpolated estimate stays approximately accurate, not exact). Separately,
  `avg()`/`mean()` over a `quantile="0.95"`-labeled (Summary) or
  `_p9[0-9]`-suffixed series — pooling replicas or windows — is invalid:
  Prometheus, on the replica case, "averaging the quantiles yields
  statistically nonsensical values." The reason generalizes: a quantile
  isn't linear in the distribution, so pooling means summing the raw
  buckets and recomputing the quantile once, never averaging ones already
  computed. Distinct from the head-sampling bullet above — that one is
  about the trace *source*'s representativeness; this one assumes an
  already-unsampled histogram (that bullet's own fix) and shows the
  bucket/aggregation math can still lie.
- **Instrument-type mismatch reads clean and lies.** Prometheus: "if the
  value can go down, it is a gauge," and "you should never take a rate() of
  a gauge" — `rate()`/`increase()` automatically adjust for *any* counter
  reset (Prometheus: "Breaks in monotonicity … are automatically adjusted
  for"), on the built-in assumption a reset means a process restart; a
  "counter" zeroed by anything else — a manual or scheduled reset, a
  business-logic zero — still triggers that same adjustment, but the
  assumption no longer holds, so the reading right at each reset silently
  saws or mis-counts, no error thrown. (OpenTelemetry, **Development**-status) An
  `UpDownCounter` incremented and decremented under different attribute sets
  forks into two never-reconciled series — "those increments and decrements
  will end up as different timeseries," e.g. `active_requests` incremented
  at request-start, decremented at request-end with one extra attribute
  (`status_code`, known only at the end) added on the decrement.
- **A metric absent until first occurrence is a blind spot, not a zero.**
  Prometheus: such series are "difficult to deal with... export a default
  value such as 0 for any time series you know may exist in advance." Until
  then, a ratio built on it (`errors_total{type="x"} / requests_total`)
  returns no data, not 0 — easy to misdiagnose as "monitoring is broken" —
  and a deadman/absence health check can't tell "healthy and quiet" from
  "crashed and emitting nothing," both reading as no series. Distinct from
  the golden-signals bullet on a quota/transport failure miscategorized as a
  result — that's a wrong *value*; this is no series at all.
- **One unit per metric identity, never mixed.** Mixing seconds and
  milliseconds under one metric name corrupts `sum()`/`avg()` and can
  silently miscalibrate an alert threshold 1000x when the unit changes.
  Prometheus suffixes the unit into the name; OpenTelemetry keeps it out of
  the name (instrument metadata) — only "one unit, never mixed" is
  stack-agnostic; don't prescribe either naming convention as universal.

**Grep leads:** `rate(`/`increase(` applied to something not named
`*_total`/`*_count`; `avg(`/`mean(` wrapping a `quantile=`-labeled or
`_p9[0-9]`-suffixed series; a `Histogram`/`Summary` constructor with no
`buckets=`/`objectives` backing a stated SLO; a `Gauge`/`.set(`/`.dec(` call
on something named like a counter; an `UpDownCounter` `.add()` whose
attribute set differs between its increment and decrement call sites; an
error/outcome counter incremented only inside a conditional branch with no
unconditional zero-init at startup.

---

## Audit trail & repudiation

- Destructive, financial, permission, and configuration changes need an audit
  record answering **who, what, when, from where, old value → new value** — an
  UPDATE overwriting a row with no history can't answer "who changed this."
- **Append-only**: no UPDATE/DELETE grants for the application role on the audit
  table, or ship to a write-once/external sink. A trail the acting user (or the
  app's own service account) can rewrite gives no non-repudiation.
- Record the **acting principal, not just the affected subject**; capture
  impersonation/admin-on-behalf-of explicitly. A failed audit write must fail the
  operation or raise loudly, never a silent `catch` (cross-ref
  `reliability-error-handling.md`).
- **Non-repudiation cuts both ways.** The append-only trail above is a *security*
  goal — the system can prove who did what, protecting the operator. From the **data
  subject's** side it is LINDDUN's *Non-repudiation* privacy *threat*: an immutable,
  over-broad log can strip a whistleblower's or abuse-victim's ability to plausibly
  deny a presence or action. Scope what the trail captures **about subjects** (as
  opposed to operators) to what a genuine dispute needs — the minimization bar in
  `privacy-compliance.md`, not "log everything about everyone forever."

---

### Audit coverage: privileged mutations vs audit-helper callers

List every privileged mutation (role or permission change, deletes, exports, config or billing changes, impersonation,
secret rotation) and every caller of the audit helper (grep its name). The set difference is the finding list: a
privileged mutation with no audit call, or an audit call placed before the mutation can fail, or outside its
transaction. Record both lists as evidence.

## Backup & restore

- A backup that has never been restored is a hypothesis. Look for what is backed
  up (DB, object storage, secrets/config, IaC state), schedule, encryption,
  **off-instance/off-account copy**, retention, and a **dated restore drill**
  with a measured restore time.
- Stated RPO/RTO must reconcile with the backup interval and the drill's measured
  time; a mismatch is a finding. Restore is tested into a scratch environment,
  with a runbook followable by someone who didn't write it (`docs-and-dx.md`).
- Restoring an old snapshot can resurrect erased personal data — the erasure path
  must be re-applicable after a restore (cross-ref `privacy-compliance.md`).

---

**🚩 red flags**: no alert on the critical path; alerts only on causes; averages
only; health check that always returns 200; quota/transport failure counted as a
result; raw request/response/headers logged; secrets or PII in spans; user input
concatenated into log lines; unbounded metric labels; a latency SLO with no
histogram bucket at the objective threshold; a dashboard/alert averaging
pre-computed percentiles across instances; an alert or ratio denominator built
on a metric that only exists after first occurrence; destructive action with no
audit record; audit table the app can UPDATE/DELETE; stateful store with no
backup, no off-site copy, or no dated restore drill; a correlation/trace id
assumed to prove an unbroken trace with no verified context propagation across
service hops.
