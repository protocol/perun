# Registers scripts/test-rules-locale.sh with CI: `ci-gates.sh rules` answers the same under en_US.UTF-8 as under the C locale (see the "Per-PR tests" step in ci.yml).
bash scripts/test-rules-locale.sh
