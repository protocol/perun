# Bundled semgrep logging rules perun.{js,py,go}.log-sensitive (CWE-532) and perun.{py,go}.log-injection (CWE-117): annotated ruleid/ok fixtures with a redacted/sanitized clean twin per rule (live when semgrep is installed, SKIP otherwise) plus offline metadata pins.
python3 -I scripts/test_semgrep_logging.py
