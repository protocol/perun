### Changed
- `report_contract_lint.py` prints a final `FAIL: this report is not deliverable ...` line to stderr when it finds violations (stdout stays one violation per line). In `--done` mode it says the draft is deleted and to resend from `--part 1`, so a failed lint no longer reads as permission to deliver the draft anyway. Tests in `scripts/test_report_contract_lint.py`.
