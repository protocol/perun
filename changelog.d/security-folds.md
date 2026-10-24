### Fixed
- `review_checks.sh` scanners now fail closed: malformed, empty, missing or wrong-shape scanner JSON, a semgrep `errors` array (partial scan) and crash exit codes from gitleaks, osv-scanner, semgrep, shellcheck, ruff, pyflakes, tsc and go vet print a `not run` line instead of reading as "no findings". Changed files reach the linters, gitleaks and osv-scanner as `./path` so a leading-dash filename is never read as an option, the gitleaks report is cleared before every run, and semgrep runs once per 200 changed files after `--`.
- `SKILL.md` routes the whole-app security review reference lazily ("read only", it routes the rest) instead of "first".
- size-budget-raise: .claude/skills/deep-code-review/SKILL.md 2884→2893 lazy whole-app security route wording
