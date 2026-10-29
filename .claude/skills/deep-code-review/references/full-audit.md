# FULL-scope audit: entry-point table and surface-gated domains

Read this when the scope is `FULL` (never for `DIFF` or `FILE`). Two steps that make a whole-repo audit both cheaper
and sharper.

## 0. Run conditions (check before Phase 1)

- **Load the skill from the release checkout** (the repo or worktree you were told to audit with), never a stale global
  copy under `~/.claude/skills`; a lane that reads an older copy reports gaps already fixed.
- **No install, no tests.** To run tests without installing, reuse an existing `node_modules` read-only (symlink or
  `NODE_PATH`); if none exists, report "tests not run" with the reason. Never install on the target's behalf.
- **Target bans agent commits/pushes** (its `CLAUDE.md`/`AGENTS.md`): stage only, and hand the owner the exact
  commands; do not commit, push or bypass a hook.
- **No dependency scan is not clean.** `review_checks.sh` falls back to `npm audit`, `pnpm audit` or `pip-audit` when
  osv-scanner/trivy cannot reach their DB; if no scan ran, the dependency row reads "not checked", never "clean".
- **Lockfile-only dependency fix** (no `node_modules` written): `npm audit fix --package-lock-only --ignore-scripts`;
  for an advisory that needs a range bump, `npm install <pkg>@<range> --package-lock-only --ignore-scripts`; then
  re-run `npm audit --package-lock-only` to verify.
- **PR body: claim "CI will run X" only if a workflow in the repo runs X** (grep `.github/workflows`); otherwise ask
  reviewers to run the exact test command before merge.

## 1. Entry-point table

Before reading domain checklists, enumerate every externally triggerable entry point: server actions, HTTP routes,
background jobs and crons, queue consumers, and inbound webhooks (grep the framework's route and handler
conventions). One row each:

| Entry point | Auth | Rate limit | External calls | Timeout budget | Idempotency |
|---|---|---|---|---|---|

Fill each cell from code, not memory; an empty cell is a finding candidate ("none found" is a valid, cited value).
Rows without auth on a mutating path, without a rate limit on a costly or credential-checking path, with external
calls but no timeout, or retried without an idempotency key are the leads to verify first. The table is a fixed
Phase-1 artifact: build it before any domain pass, not as a by-product of one. For each path, sum the timeouts of its
sequential external calls and compare the total with the proxy or platform limit; a sum over the limit is a finding
even when every single timeout looks sane. The timeout column feeds the latency-budget probe in
`reliability-error-handling.md`.

## 2. Gate domains on a surface probe

Load an optional domain or reference only when a case-insensitive `grep -E` probe shows its surface exists, and record the probe and its
hit count as the evidence for either outcome (a zero-hit probe is the citation that makes the N/A row valid):

| Surface | Probe (examples) | Reference |
|---|---|---|
| Crypto | `crypto\.\|crypto/\|hashlib\|cryptography\|Fernet\|AES\|bcrypt\|argon2\|scrypt\|nacl\|jose\|jwt\|hmac` | `appsec-crypto.md` |
| Templates (SSTI) | `render_template_string\|Template\(\|jinja\|handlebars\|ejs\|pug\|mustache\|eval\(` | `appsec-ssti.md` |
| File handling | `multipart\|upload\|FormData\|writeFile\|fs\.write\|send_file\|path\.join\|open\(.*[\"']w` | `appsec-files.md` |
| Supply chain | `postinstall\|package-lock\|yarn\.lock\|poetry\.lock\|go\.sum\|Cargo\.lock\|requirements.*\.txt\|uses:` | `appsec-supply.md` |
| Accessibility | `<(img\|button\|input\|a\|div)\b\|aria-\|\.tsx\|\.jsx` | `frontend-a11y.md` |
| ML / models | `torch\|tensorflow\|sklearn\|scikit\|onnx\|safetensors\|transformers\|xgboost\|embedding` | `data-ml.md` |
| Billing | `stripe\|paddle\|braintree\|checkout\|lemonsqueezy\|chargebee\|subscription\|invoice\|meter` | `billing-correctness.md` |

No hit: record the probe and mark N/A; do not load the reference.

## 3. Whole-repo lenses (FULL only; each is a grep, not a read-everything pass)

Run a lens only when its trigger exists; record the grep and hit count either way.

- **Guard added later.** When a guard (auth check, tenant filter, soft-delete filter, validation) sits in an accessor
  or repository function, grep every other reader of the raw primitive (the table, model, query builder, cache key or
  file path); each one that bypasses the accessor is a finding. A guard in one reader proves nothing about its siblings.
- **Access matrix.** Build role x resource, and include the secondary read surfaces, which are the usual leak: comments,
  search or command palette, notifications, exports and downloads, counts and aggregates, autocomplete, and
  link-preview or share pages. Each cell is allow or deny with a code citation; guarding the primary page does not
  cover them.
- **External contract retry and replay.** For each outbound or inbound third-party call: a single-use token or nonce
  reused on a 429/5xx retry (the retry replays a consumed credential); a webhook redelivered after the handler's
  freshness window (a valid redelivery rejected as stale, or accepted twice); an idempotency key matched by prefix or
  truncated, so two distinct requests collide.
- **External query and API contract.** For every external query or call (warehouse SQL, third-party API), check each
  identifier (column, field, endpoint, parameter) against the live schema or the published contract, not against
  the code's own assumption. A catch or fallback that swallows the error turns a wrong identifier into silent
  empty data; flag it.
- **Switches and readiness.** A kill switch or feature flag must fail closed on an unknown, empty or misspelled value
  (grep the parse); a readiness or health check must reflect migration state, not just process liveness; a scheduled
  run and a manual run of the same job must take the same lock, not two.
- **Writer/reader data shape.** For each persisted JSON blob, metric or event key, list every writer and every reader
  (grep the key string); the shapes must agree (type, nesting, units, nullability, enum values). A reader that expects
  a field no writer emits, or a writer whose new field no reader handles, is a finding; the key list is the evidence.
- **Identity match.** For each lookup that matches a record by identity (user, tenant, device, token, account), list
  every branch that resolves it and the stored key set it compares against; each branch must compare the same bound
  key set, and a branch that matches on a strict subset (name only, no tenant) is a finding.
- **Mutation reachability.** For each library function that mutates state, list every entry point that reaches it
  (use the entry-point table) and the guard on each path; a mutation guarded on one route and open on another is a
  finding. Guard the function, not only the route.
- **Gate review.** Check each CI or release gate against `release-engineering.md` (Gate tooling and hooks: fallbacks
  that pass on missing input, could-not-check, seeded ratchets). A "100% tests pass" gate reports a pass rate, not
  coverage; check whether the tests exercise the changed code before trusting it.
- **Metric labels.** Numerator and denominator must count the same entity (`data-metrics.md`); a total must name its
  time window, and two totals with different windows must not sit side by side unlabeled.
- **Fix re-verification and findings ledger.** When re-checking a fix, re-run the grep for the whole defect class
  (`method.md`), not only the cited lines; a sibling site that survives means `still-open`. Emit each finding with
  id, status and evidence line in the `machine-report.md` ledger so the next run re-checks it automatically.
  On a FULL re-run, load the prior machine report in `code-review/` for the same target by default (`machine-report.md` section 3, no `PRIOR` flag needed) and
  emit `fixed` or `still-open` for every prior id before new hunting.

Opt-in dynamic step: read `dynamic-probe.md` when the app runs locally and static scanners found nothing (malformed-input 5xx, missing rate limit, headers, open redirect).
