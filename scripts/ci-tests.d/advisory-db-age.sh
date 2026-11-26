# Registers the stale advisory DB age tests: provision_tools.sh --age and the audit_sweep.py ENVGAP classification of the not-checked row.
bash scripts/test-provision-advisory-age.sh
bash scripts/test-review-checks-advisory-age.sh
python3 scripts/test_audit_sweep_staledb.py
