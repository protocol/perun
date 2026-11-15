# Registers scripts/bench_tool_only.py with CI (see the "Per-PR tests" step in ci.yml); it SKIPs (exit 0) without the real scanners and gates recall in the real-hub job.
python3 scripts/bench_tool_only.py
