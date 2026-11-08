#!/usr/bin/env bash
# Registers the dependency_currency.py TSV collapse tests: more than 3 not-checked rows sharing (file, ecosystem, note) print as one row; 3 or fewer, other notes, other files and --json (every row) unchanged. Offline (dep_row and osv_pass stubbed).
python3 scripts/test_dependency_currency_notrun_collapse.py
