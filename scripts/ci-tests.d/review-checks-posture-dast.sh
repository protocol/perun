# review_checks.sh posture and DAST routes: opengrep as the SAST fallback when semgrep is absent; opt-in scorecard (REVIEW_SCORECARD=1, GITHUB_TOKEN) and nuclei plus ZAP baseline (REVIEW_DAST_URL, localhost only unless REVIEW_DAST_ALLOW_REMOTE=1), with stub binaries on a hermetic PATH.
bash scripts/test-review-checks-posture-dast.sh
