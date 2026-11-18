### Added
- review_checks.sh runs pipefail_sigpipe.py on changed shell files: under `set -o pipefail`, a multi-write producer (git log/ls-files/diff, find, cat, grep, curl, jq, sort, ls) piped into `grep -q`/`-m`/`head` in a condition can die of SIGPIPE and read false; the check flags it as a lead (tool `pipefail-sigpipe`) with the `grep -q PAT <<<"$(producer)"` fix, and lang-shell.md names the class.

size-budget-raise: .claude/skills/deep-code-review/references/lang-shell.md 9885→10117 pipefail SIGPIPE bullet
