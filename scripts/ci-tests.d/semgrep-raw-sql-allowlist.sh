# Bundled semgrep rules perun.js.raw-sql-concat and perun.py.raw-sql-format skip allow-listed values (Set/array membership check, literal-returning helper) and still report unchecked input (live when semgrep is installed, SKIP otherwise).
python3 scripts/test_semgrep_raw_sql_allowlist.py
