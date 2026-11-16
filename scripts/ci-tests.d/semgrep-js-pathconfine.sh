# Bundled semgrep JS path-traversal rule: a startsWith prefix guard that returns clears the checked path; an unguarded path, a guard on another variable and a nested return still report. Needs semgrep; offline pin always runs.
python3 scripts/test_semgrep_js_pathconfine.py
