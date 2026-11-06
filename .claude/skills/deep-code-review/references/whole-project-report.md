Read this when writing a whole-project security audit report, or when `scripts/report_contract_lint.py` rejects one.

# Whole-project security report: contract and template

A report that claims coverage must say what ran and what did not. `scripts/report_contract_lint.py REPORT.md --root REPO` checks the contract below and exits 1 with one line per violation.

## Template

```markdown
# Security audit: <project>

## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| <standard item> | pass / fail / not-checked | tool:<name> or guided:<eval id> | <path:line>, ... | `<quoted code that handles the risk>` |

## NOT CHECKED
- <item>: <why>

## NOT RUN
- <tool>: <reason>

## Static vs runtime
Needs a running system: deployed config, WAF, runtime authz, vault, infra outside the repo.

## Dependencies
<lockfile and advisory results, or what could not be read>

## Route inventory
- <METHOD> <path> <repo-relative file>:<line> auth=<none|...> rate-limit=<yes|no> csrf=<none|token|origin|samesite|n/a>
```

## Findings format

A security audit (`security-review-mode.md`) has a `## Findings` section with one finding per top-level list item: `[<class>] <repo-relative path>:<line> <severity>: <text>`. The path is the vulnerable handler or line, never a gate, helper or config used as evidence; give exactly one `path:line`, and put evidence cites after `evidence:` in the text or in other sections. Never cite a bare file name. A chain finding cites its end-state line as the primary and the other links after `evidence:`. Indented continuation lines, prose, and subsections whose heading names an attack path or chain are not linted.

One finding per vulnerable site, never a group or a range: each state-changing cookie-session handler without a CSRF defence (`csrf`, anchored on the line that commits the change, not the signature), each session-cookie set call missing a flag (`cookie-flags`, including a cookie that sets HttpOnly but not Secure or SameSite), each unauthenticated handler (`missing-authn`). `missing-authn`, `missing-authz` and `object-level-authz` anchor on the route's declaration line (the line `route_auth_map.py --all` prints), not the read or write inside the body; the commit-line anchor is `csrf` only. A GET that sets a cookie is not `csrf`. Each `pii-data` row of `review_checks.sh --full` (tool `pii-data`: a plaintext national id literal, an unencrypted national-id column, raw email or phone sent to an analytics host) is one `pii-data` finding at its line. The per-standard Files cell and the primary `path:line` list vulnerable sites only: a gate, middleware, interceptor, filter, helper or token table you read as evidence goes after `evidence:`, and a route a verified global gate covers is not `missing-authn`. Each `csrf-cookie` row from `review_checks.sh --full` is a lead: verify it, then file it at its own line. Each `missing-attempt-limit` or `missing-cost-limit` row of `review_checks.sh --full` is a lead: verify it, then file one `rate-limit` finding at its own line.

Fixed class vocabulary: `missing-authn`, `missing-authz`, `object-level-authz`, `ssrf`, `tls-off`, `outbound-timeout`, `secret-in-url`, `secret-in-log`, `hardcoded-secret` (credentials or tokens in source), `csrf`, `cookie-flags`, `rate-limit`, `pii-in-log`, `pii-data` (personal data committed, stored in plaintext or sent to a third party), `prompt-injection` (including tool-call JSON built from input), `injection`, `xss`, `other`. Pick the closest class; use `other` only when none fits.

Cite the sink: for `ssrf`, `tls-off`, `outbound-timeout` and `secret-in-url` the outbound call, URL or TLS option; for `secret-in-log` and `pii-in-log` the log call; for `cookie-flags` the cookie set. The lint fails a cite whose line +-2 shows no sink (`finding-not-on-sink`). One finding per issue: do not re-cite it at the route or a helper. `rate-limit` cites the line doing the brute-forceable check or costly work (credential, PIN or OTP compare; SMS or LLM call; export build), not the route declaration or signature, and only for brute-forceable or costly endpoints (login, PIN, OTP, SMS, LLM, bulk export); not when a limiter already wraps the route (reviewer guidance: the lint does not check this anchor). `csrf`: SameSite Lax or Strict blocks a cross-site POST but not a state-changing GET. Never cite a token generator or a limiter definition. A `pii-in-log` line that logs a key, token, secret or password is `secret-in-log`; one with an outbound call and no log call is `pii-data` (`class-mismatch`).

Example: `- [pii-data] src/api/users.py:42 high: serves SSNs and dates of birth unmasked. evidence: src/models.py:10`

## Rules the linter enforces

- `finding-no-class`: a Findings line lacks a vocabulary label or the `[class] path:line severity: text` shape. `finding-multi-cite`: a second cite before `evidence:`, or a `path:12,15` list, on one finding. Elsewhere `path:12,15,20` is accepted as lines of one path.
- All four sections above exist; every item has a status of `pass`, `fail` or `not-checked`.
- `pass` needs a check that ran: `tool:<name>` whose tool is not under NOT RUN, or `guided:<id>`. A guided pass also lists the files it examined and a backtick-quoted negative that appears in a cited file. Cited paths resolve inside `--root`, as `path` or `path:line[-line]` only.
- Every cited `path` or `path:line` exists under `--root`; cite the repo-relative path; a bare file name such as `app.py:9` resolves only for a file at the repo root, in prose or backticks (`bad-citation`).
- `missing-route-inventory`: no `## Route inventory` section. List one route or handler per line, never grouped (not "POST /a, /b"), each at its own declaration `file:line`; fill it from `route_auth_map.py --all` where it supports the stack, else grep. `inventory-no-cite`: a list line there without exactly one repo-relative `path:line` that exists under `--root` (only tokens with a file extension count as cites, so `host:8080` does not). An empty section fails `missing-route-inventory` unless it holds an explicit `- none` line. `inventory-not-list`: a non-blank line in the section that is not a list item.
- `inventory-no-csrf`: an inventory row with METHOD POST, PUT, PATCH or DELETE and an `auth=` value naming a cookie or session has no `csrf=<value>` field.
- `csrf-unfiled`: such a row has `csrf=none` and no `- [csrf]` Findings line either names the row's route path or cites the row's file at a line from the row's line up to the next inventory row of that file.
- More than 40% of items `not-checked` without a NOT RUN reason (a `tool:` basis whose tool has a reason under NOT RUN) fails.
- No safety claim ("no vulnerabilities", "is secure", "safe to deploy" and paraphrases; list in the script's `CLAIMS`). State what was checked, never that the project is safe. A zero count starts with its tool (`trivy: 0 findings in package-lock.json`).
- NOT RUN holds one `- <tool>: <reason>` line per tool that did not run, and nothing else; tools that ran go in the Basis column.
