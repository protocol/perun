# Registers the test-path hint tests (review_checks.sh row hint, audit_sweep norm and grouping) with CI.
bash scripts/test-review-checks-test-path-hint.sh
python3 scripts/test_audit_sweep_test_path.py
