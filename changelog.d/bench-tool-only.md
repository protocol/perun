### Added
- bench/tool-only: 11 seeded fictional CWE fixtures with clean twins and an answer key, scored by scripts/bench_tool_only.py (per-CWE and overall recall, false positives on the clean twins; fails below the frozen recall floor or above the frozen false-positive ceiling; SKIPs when semgrep, gitleaks or trivy is absent). Runs in the real-hub CI job after the tools install.
