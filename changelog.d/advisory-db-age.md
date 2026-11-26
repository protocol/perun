### Changed

- An offline osv-scanner or trivy advisory database older than `REVIEW_ADVISORY_MAX_AGE_DAYS` (default 7; a non-integer value warns and falls back to 7) now yields a `NOT CHECKED` row that names its age and the refresh command, instead of a clean pass. A database whose age cannot be read yields an "of known age" row. `audit_sweep.py` classifies both rows as ENVGAP (not-provisioned), not a blocking GAP, so the weekly forced `--full` rescan no longer reads as checked against stale advisories.
- `provision_tools.sh` gains `--age trivy|osv DIR` (whole days; the oldest osv zip at any depth sets the osv age) and `--cache trivy-dir|trivy-cmd`. trivy now scans the same directory that is age-checked, and the trivy refresh hint matches the `provision_tools.sh` warm command.
- Corrected the `FULL_EVERY` comment and docstring in `audit_sweep.py`.
