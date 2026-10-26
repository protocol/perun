### Fixed
- Scanner scripts degrade gracefully under the macOS agent sandbox: `supply_chain_check.sh` falls back to the OSV API when the osv-scanner CLI crashes (`osv: api-fallback`), `review_checks.sh` runs semgrep with a temp HOME and retries trivy secret-only when the misconfig bundle is unreachable. Every degraded run says so.
size-budget-raise: .claude/skills/deep-code-review/references/supply-chain-check.md 2688→3178 five-line sandbox-degradation section (fallbacks are announced, not silent)
