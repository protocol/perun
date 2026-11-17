### Added
- bench/tool-only: JS prototype pollution (CWE-1321) and the first Java pairs, XXE via `DocumentBuilderFactory` (CWE-611) and `ObjectInputStream` deserialization (CWE-502). Each clean twin stays quiet, so the false-positive ceiling is unchanged.
- semgrep-taint/js.yml: new rule perun.js.prototype-pollution for a for-in loop that assigns `target[key] = ...` with no `__proto__` guard. Test: scripts/test_semgrep_js_proto_pollution.py.
