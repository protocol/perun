# Registers the affected-run receipt tests (run-ci-tests.sh --affected receipt, handback.py unverified-test-claim check) with CI (see the "Per-PR tests" step in ci.yml).
python3 scripts/test_affected_receipt.py
