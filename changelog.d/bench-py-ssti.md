### Added
- bench/tool-only: Python request-data deserialization (pickle, yaml), lxml XXE and server-side template injection pairs (CWE-502, CWE-611, CWE-1336). The SSTI twin compiles request data with jinja2 `Template`; the clean twin renders a literal template with the data as context and adds no false-positive rows.
- semgrep-taint/py.yml: new taint rule perun.py.ssti for request data or a parameter reaching `jinja2.Template`, `Template`, `.from_string` or `render_template_string`. Test: scripts/test_semgrep_py_ssti.py.
