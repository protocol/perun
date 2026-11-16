# Registers the org_audit_driver --noise-re test and the --list-tools drift guard with CI.
python3 scripts/test_org_audit_noise_re.py
bash scripts/test-review-checks-list-tools.sh
