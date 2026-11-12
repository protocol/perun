# Registers the low-context index tests with CI (see the "Per-PR tests" step in ci.yml).
set -e  # a bare `bash` run must stop at the first failing test, not report only the last one's status
python3 scripts/test_skill_index_entry.py
python3 scripts/test_index_pointer.py
