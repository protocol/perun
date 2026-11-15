# Bundled semgrep rules in py.yml: ssrf abort allowlist guard, open-redirect relative-path/url_has_allowed_host_and_scheme guard, xxe-lxml (annotated ruleid/ok fixtures; live when semgrep is installed, SKIP otherwise).
python3 scripts/test_semgrep_py_guards.py
