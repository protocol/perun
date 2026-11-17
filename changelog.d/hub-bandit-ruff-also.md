### Changed
- review_checks.sh: the bandit row kept by the bandit/ruff-security twin collapse now carries the dropped ruff row as `also` (`ruff-security S603: message`). Rows hold no severity or CWE field, so nothing else is lost. A new table test checks that every Snnn/Bnnn number ruff and bandit both ship names the same check (no differing pair found, none excluded).
