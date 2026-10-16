# Registers the pipeline-optimizer tests with CI (see the "Per-PR tests" step in ci.yml).
python3 .claude/skills/agentic-delivery/scripts/pipeline_profile.py --selftest
python3 scripts/test_pipeline_profile.py
python3 scripts/test_pipeline_profile_failclosed.py
bash scripts/test-selftest-stamps.sh
