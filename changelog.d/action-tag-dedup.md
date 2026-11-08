### Changed
- `review_checks.sh` drops a semgrep `github-actions-mutable-action-tag` row when zizmor reported `unpinned-uses` on the same file and line (one defect, one row); other lines and runs without zizmor keep the semgrep row.
