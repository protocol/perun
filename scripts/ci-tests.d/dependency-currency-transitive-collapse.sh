#!/usr/bin/env bash
# Registers the dependency_currency.py TSV transitive-npm collapse tests: more than 3 outdated rows from one npm lockfile whose names no sibling package.json declares directly print as one row; direct rows, 3 or fewer, no readable package.json, vulnerable rows and --json (every row) unchanged. Offline (dep_row and osv_pass stubbed).
python3 scripts/test_dependency_currency_transitive_collapse.py
