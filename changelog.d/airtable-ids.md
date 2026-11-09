### Fixed
- `review_checks.sh` no longer reports Airtable object IDs (`rec`/`app`/`tbl`/`fld`/`viw` + 14 alphanumerics) as `airtable-api-key` secrets: a global gitleaks allowlist, added to the tree, diff and history scans on gitleaks 8.25.1 or newer, drops them while a legacy `key` value still reports.
