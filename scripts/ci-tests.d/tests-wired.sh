# Standing check (#1592): every scripts/test_*.py and scripts/test-*.sh is run by CI or listed with a reason. Offline.
bash scripts/test-tests-wired.sh
bash scripts/ci-gates.sh tests-wired --allowlist scripts/ci-test-allowlist.tsv .
