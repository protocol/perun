# Registers the review_checks.sh hub cross-tool duplicate merge (bandit, ruff-security, semgrep, gosec on one file:line and CWE; highest severity kept), the secret-scanner likely-fixture demotions, and the bench ceiling ratchet (ceilings never raised vs origin/main).
bash scripts/test-review-checks-hub-crosstool.sh
bash scripts/test-bench-ceiling-ratchet.sh
bash scripts/test-bench-ceiling-ratchet-dup.sh
