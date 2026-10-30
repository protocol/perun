# Registers the scanner provisioning tests: provision_tools.sh + review_checks.sh offline caches, and the doctor "review scanners" row.
bash scripts/test-provision-tools.sh
python3 scripts/test_doctor_review_scanners.py
