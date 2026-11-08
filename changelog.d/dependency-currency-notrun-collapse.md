### Changed
- `dependency_currency.py` TSV output (default mode, `review_checks.sh` dep-currency step) prints one `not-checked` row instead of one per package when more than 3 not-checked rows share a file, ecosystem and note. The row sits at the smallest line and names the first 3 packages; `--json` still lists every row. Groups of 3 or fewer and all other rules print unchanged.
