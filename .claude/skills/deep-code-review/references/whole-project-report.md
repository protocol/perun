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
```

## Findings format

A security audit (`security-review-mode.md`) has a `## Findings` section with one finding per top-level list item: `[<class>] <repo-relative path>:<line> <severity>: <text>`. The path is the vulnerable handler or line, never a gate, helper or config used as evidence; give exactly one `path:line`, and put evidence cites after `evidence:` in the text or in other sections. Never cite a bare file name. A chain finding cites its end-state line as the primary and the other links after `evidence:`. Indented continuation lines, prose, and subsections whose heading names an attack path or chain are not linted.

Fixed class vocabulary: `missing-authn`, `missing-authz`, `object-access`, `ssrf`, `tls-off`, `outbound-timeout`, `secret-in-url`, `secret-in-log`, `hardcoded-secret` (credentials or tokens in source), `csrf`, `cookie-flags`, `rate-limit`, `pii-in-log`, `pii-data` (personal data committed, stored in plaintext or sent to a third party), `prompt-injection` (including tool-call JSON built from input), `injection`, `xss`, `other`. Pick the closest class; use `other` only when none fits.

Example: `- [pii-data] src/api/users.py:42 high: serves SSNs and dates of birth unmasked. evidence: src/models.py:10`

## Rules the linter enforces

- `finding-no-class`: a Findings line lacks a vocabulary label or the `[class] path:line severity: text` shape. `finding-multi-cite`: a second cite before `evidence:`, or a `path:12,15` list, on one finding. Elsewhere `path:12,15,20` is accepted as lines of one path.
- All four sections above exist; every item has a status of `pass`, `fail` or `not-checked`.
- `pass` needs a check that ran: `tool:<name>` whose tool is not under NOT RUN, or `guided:<id>`. A guided pass also lists the files it examined and a backtick-quoted negative that appears in a cited file. Cited paths resolve inside `--root`, as `path` or `path:line[-line]` only.
- Every cited `path` or `path:line` exists under `--root`.
- More than 40% of items `not-checked` without a NOT RUN reason (a `tool:` basis whose tool has a reason under NOT RUN) fails.
- No safety claim ("no vulnerabilities", "is secure", "safe to deploy" and paraphrases; list in the script's `CLAIMS`). State what was checked, never that the project is safe. A zero count starts with its tool (`trivy: 0 findings in package-lock.json`).
- NOT RUN holds one `- <tool>: <reason>` line per tool that did not run, and nothing else; tools that ran go in the Basis column.
