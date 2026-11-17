### Changed
- review_checks.sh: the secret `[shape: ...]` hint reads `env-default` instead of `env-ref` when an env read (`os.environ`, `getenv`, `process.env`, `${...}`) shares its line with a quoted literal of 6+ characters other than the variable name, since a fallback default can be a real secret.
