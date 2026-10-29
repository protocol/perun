# Registers the invisible_chars.py hardening tests: locale files and flag emoji, binary and UTF-16 handling, fixture and ESC paths, 2 MB/200-row/flush limits, newline-only paths and file-name scan, audit_skills parity; review_checks.sh vendored-dir skips, [likely-fixture] tag, missing-script and timeout rows. Offline.
python3 scripts/test_invisible_chars_hardening.py
bash scripts/test-review-checks-invisible-chars-hardening.sh
