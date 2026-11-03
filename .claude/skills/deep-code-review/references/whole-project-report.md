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

## Rules the linter enforces

- All four sections above exist; every item has a status of `pass`, `fail` or `not-checked`.
- `pass` needs a check that ran: `tool:<name>` whose tool is not under NOT RUN, or `guided:<id>`. A guided pass also lists the files it examined and a backtick-quoted negative that appears in a cited file. Cited paths resolve inside `--root`, as `path` or `path:line[-line]` only.
- Every cited `path` or `path:line` exists under `--root`.
- More than 40% of items `not-checked` without a NOT RUN reason (a `tool:` basis whose tool has a reason under NOT RUN) fails.
- No safety claim ("no vulnerabilities", "is secure", "safe to deploy" and paraphrases; list in the script's `CLAIMS`). State what was checked, never that the project is safe.
