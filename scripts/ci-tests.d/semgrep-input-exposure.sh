# Bundled semgrep rules in templates/semgrep-taint/input-exposure.yml (CWE-20 unvalidated size or quantity in JS, CWE-200 traceback, exception text or secret fields in a Python response): annotated ruleid/ok fixtures plus vulnerable, mutant and fixed class seeds. Live when semgrep is installed; with CI=true a missing semgrep fails.
python3 scripts/test_semgrep_input_exposure.py
