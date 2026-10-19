# Registers scripts/test_check_rivals_outcome.py with CI (see the "Per-PR tests" step in ci.yml) and runs the gate on the committed doc.
python3 scripts/test_check_rivals_outcome.py
python3 scripts/check_rivals_outcome.py docs/perun-vs-rivals.md
