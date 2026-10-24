# Registers the security-gates corpus regression and scorer drift check with CI. Offline.
python3 scripts/test_security_gates_corpus.py
python3 docs/bench/security-gates-1024/score.py >/dev/null
