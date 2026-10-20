# Registers scripts/test_partial_pass.py with CI (see the "Per-PR tests" step in ci.yml).
python3 scripts/test_partial_pass.py
python3 .claude/skills/agentic-delivery/scripts/partial_pass.py --selftest
