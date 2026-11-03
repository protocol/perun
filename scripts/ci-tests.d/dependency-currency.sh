# Registers the dependency_currency.py tests: unit (npm, pip, go, maven, gradle, cargo and composer fixtures with decoys at latest, drift, Dockerfile and Actions pins, EOL with verified targets, vendored flag, KEV-first order, NOT RUN on unreachable hosts, range and pre-release rules; every HTTP call mocked) and the review_checks.sh dep-currency step (NOT RUN row with the proxy dead, no row without a manifest, missing script). Offline.
python3 scripts/test_dependency_currency.py
python3 scripts/test_dependency_currency_coverage.py
bash scripts/test-review-checks-dep-currency.sh
python3 scripts/test_dependency_currency_g5.py
python3 scripts/test_dependency_currency_g5b.py
python3 scripts/test_dependency_currency_g5c.py
