### Fixed
- `veche.py --criteria` accepts the flag more than once. `--criteria a:3 --criteria b:2` used to keep only the last criterion without warning, so the weighted decision scored on the wrong criteria. Repeats now join into one list, and every criterion reaches the record. New test: `scripts/test_veche_criteria_repeat.py`.
