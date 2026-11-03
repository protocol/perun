### Changed
- `review_checks.sh` hides a hygiene tier by default: trivy LOW rows, hadolint info/style rows and a short list of low-value checkov ids (for example KSV-0125) no longer appear in the findings. `--hygiene` shows them again, and a stderr line counts the hidden rows.
