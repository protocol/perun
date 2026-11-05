### Added
- G1 API Top 10 pilot: `ownership_sibling_check.py` (API1) and `route_auth_map.py --privileged` (API5) now run in `review_checks.sh --full` as tools `ownership` (rule `ownership-sibling`) and `privileged-route` (rule `privileged-route`); API3 mass-assignment Semgrep rules; held-out records and the API status table under `docs/bench/g1-matrix/`. The third API10 detector (Semgrep `unsafe-api-consumption` and `tls-verify-off` rules) passed its held-out set, so API10 is labelled (a) pending audit. Tests in `scripts/test_g1_review_checks_rows.py` and `scripts/test_g1_api5_v2.py` and `scripts/test_g1_api10_{a,v2,v3}.py`.

size-budget-raise: .claude/skills/deep-code-review/references/security-appsec.md 28245→28602 API3 mass-assignment guidance
