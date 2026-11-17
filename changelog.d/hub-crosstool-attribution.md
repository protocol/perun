### Fixed

- The cross-tool duplicate merge keeps each merged row's tool and rule in an `also` list, so per-tool attribution (bandit B602, ruff-security S602) survives; the real-hub test reads it. Test fixtures that matched gitleaks are built at runtime, and the three triaged fictional history hits are in `.gitleaksignore`.
