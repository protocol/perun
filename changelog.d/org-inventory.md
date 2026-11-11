### Added
- org_inventory.py writes a dated TSV inventory of every repo in one or more orgs from the read-only API, reconciles added and removed repos against a previous run, and marks any repo without a fresh result file as NOT CHECKED; an API or scope error exits 2 and never yields zero repos.
