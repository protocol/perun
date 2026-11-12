### Added
- Offline dependency-risk check (`dep_risk.py`, wired into `review_checks.sh`): typosquat-near names, git/URL and floating specs, and install scripts in new or changed dependencies.
- CodeQL route in `review_checks.sh` for Python and JavaScript/TypeScript (only when installed; `NOT CHECKED` otherwise); semgrep routing documented in `references/tool-hub.md`.
