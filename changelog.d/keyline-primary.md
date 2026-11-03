### Fixed
- `review_checks.sh` anchors zizmor rows on the SARIF Primary location (the offending line) instead of the first location, which could be a Related span such as the enclosing job. trivy and checkov rows are anchored on the offending key, and checkov `evaluated_keys` are split on `/` as well as `.`.
