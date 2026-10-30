# Bundled semgrep credential-compare rules: a typeof type check is never flagged as a hardcoded credential compare, a real name-vs-literal compare still is. Offline, regex level, no semgrep needed.
python3 scripts/test_semgrep_typeof_compare.py
