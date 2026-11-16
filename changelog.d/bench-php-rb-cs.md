### Added
- bench/tool-only: first PHP, Ruby and C# pairs: PHP `unserialize` of a cookie, Ruby `YAML.load` of a request parameter (CWE-502) and C# `SqlCommand` string-concatenated SQL (CWE-89). The clean twins use `json_decode`, `YAML.safe_load` and a parameterized `SqlCommand` and add no false-positive rows.
- semgrep-taint/rb.yml: new rule perun.rb.yaml-load-params for `YAML.load`, `Psych.load` and the `unsafe_load` forms on a `params[...]` value. Test: scripts/test_semgrep_rb_yaml_load.py.
