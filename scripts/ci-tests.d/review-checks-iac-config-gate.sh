# review_checks.sh: checkov and tflint never run a repo config-as-code (.checkov.yaml, .tflint.hcl, .tflint.d) without REVIEW_TEST_CMD; stub binaries.
bash scripts/test-review-checks-iac-config-gate.sh
