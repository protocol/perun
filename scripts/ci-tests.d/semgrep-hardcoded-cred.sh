# Registers the hardcoded-credential semgrep rules test: password/secret/token/api-key names and decoded Basic-auth values compared to literals are flagged; empty strings, env reads and test/fixture paths stay clean. Skipped without semgrep.
python3 scripts/test_semgrep_hardcoded_cred.py
