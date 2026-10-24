### Added
- Whole-app security review mode: `references/security-review-mode.md` orchestrates the existing security references for a full app audit (inventory first, then chained findings) and adds gap checks for host-platform breach response, CI runner and OIDC trust, install-script supply-chain risk, agent and MCP least privilege, and dated dependency-advisory evidence.
- `review_checks.sh` can now run the optional gitleaks, osv-scanner and semgrep scanners when they are installed. Each is timeboxed and skipped when absent; gitleaks output is redacted, osv-scanner runs only on changed lockfiles, and semgrep runs only when `REVIEW_SEMGREP_CONFIG` names a local rules path.
size-budget-raise: .claude/skills/deep-code-review/SKILL.md 2785→2884 one routed line for the whole-app security review mode
size-budget-raise: .claude/skills/deep-code-review/INDEX.md 19091→19224 index row for the new security-review-mode reference
