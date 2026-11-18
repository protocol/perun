# perun.llm.* in llm-context.yml (annotated ruleid/ok fixtures: system-prompt leakage CWE-200, unscoped vector reads CWE-639; live when semgrep is installed, SKIP otherwise).
python3 -I scripts/test_semgrep_llm_context.py
