# Registers the per-wave secret-rule pins and the placeholder-precision pass that no CI step ran (#1592 audit). The 30 s+ test_secrets_heldout*_blind.py
# corpus re-scores are listed with their runtimes in scripts/ci-test-allowlist.tsv instead. Offline.
python3 scripts/test_secret_extra_rules.py
python3 scripts/test_secret_extra_rules_w10.py
python3 scripts/test_secret_extra_rules_w11.py
python3 scripts/test_secret_extra_rules_w12.py
python3 scripts/test_secret_extra_rules_w13.py
python3 scripts/test_secret_extra_rules_w14.py
python3 scripts/test_secret_extra_rules_w3.py
python3 scripts/test_secret_extra_rules_w4.py
python3 scripts/test_secret_extra_rules_w5.py
python3 scripts/test_secret_extra_rules_w6.py
python3 scripts/test_secret_extra_rules_w7.py
python3 scripts/test_secret_extra_rules_w8.py
python3 scripts/test_secret_extra_rules_w9.py
python3 scripts/test_secret_precision.py
