### Added
- `review_checks.sh --full` now also runs `cost_limit_map.py` (tool `cost-limit`, rule `missing-cost-limit`): an HTTP handler that calls an LLM or paid API, takes an upload, searches, exports, or lets the client choose an uncapped page size, with no rate or quota limit evidence in its file or package. Report-only lead; SKIPPED when the repo has no HTTP handler.
