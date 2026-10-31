# Bundled semgrep rules perun.js.body-cap-after-buffer and perun.js.limiter-key-forwarded-header (templates/semgrep-taint/js.yml): annotated ruleid/ok fixtures (live when semgrep is installed, SKIP otherwise) plus offline structural pins and regex replays that still run where semgrep is absent.
python3 scripts/test_semgrep_taint_ext.py
