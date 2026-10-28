# Registers scripts/test_hermetic_children.py and scripts/test_promote_by.py (hermetic child env, bg admission, promote-by ratchet).
python3 scripts/test_hermetic_children.py
python3 scripts/test_promote_by.py
python3 scripts/promote_by.py
python3 .claude/skills/agentic-delivery/scripts/bg_admit.py untrapped
