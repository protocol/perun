# The review_checks.sh scan-summary test passes on a host that sets REVIEW_SEMGREP_REGISTRY=0 (it unsets it before expecting `--config p/default`).
REVIEW_SEMGREP_REGISTRY=0 bash scripts/test-review-checks-scan-summary.sh
