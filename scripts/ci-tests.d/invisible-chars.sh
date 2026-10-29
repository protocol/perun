# Registers the invisible_chars.py tests: unit (hidden-unicode and control-char rows, caps, binary skips, stdin CLI) and review_checks.sh step (NUL, ESC, RLO rows; clean and binary files skipped). Offline.
python3 scripts/test_invisible_chars.py
bash scripts/test-review-checks-invisible-chars.sh
