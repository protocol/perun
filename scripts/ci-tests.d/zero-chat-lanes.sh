# Registers the zero-chat-lanes tests with CI (see the "Per-PR tests" step in ci.yml).
python3 .claude/skills/agentic-delivery/scripts/subagent_start_inject.py --selftest
python3 scripts/test_zero_chat_lanes.py
