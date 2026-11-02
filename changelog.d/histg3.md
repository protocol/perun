### Changed
- `review_checks.sh --full` now also runs gitleaks over the last `REVIEW_HISTORY_MAX` commits of HEAD (default 1000; a shallow clone or a younger repo scans what it has), so a secret removed from the tree but still in history is reported as a `gitleaks-history` row. `REVIEW_HISTORY_MAX=0` turns it off and the NOT RUN list says "history not scanned". `--full-history`, `--history` and diff mode are unchanged.
size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 15637→15770 one sentence naming the bounded history pass under --full
