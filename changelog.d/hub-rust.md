### Added
- `review_checks.sh` tool hub routes two Rust tools on a changed root `Cargo.lock`, each `NOT CHECKED` when missing and `not run` on a crash, empty or whitespace output, or wrong-shape JSON, with no network: `cargo-deny` (`--offline check bans licenses sources`, plus `advisories` only when `$CARGO_HOME/advisory-dbs` exists; needs `cargo`; error-level diagnostics become rows on `Cargo.lock`) and `cargo-audit` (`audit --no-fetch --stale --json` on a local `$CARGO_HOME/advisory-db` only, else `NOT CHECKED`). `references/tool-hub.md` replaces the two "not routed" decisions with these rows; sources are logged in `docs/standards-index.md`.
- size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 35282→37195 hub rows for cargo-deny and cargo-audit replacing the not-routed decisions

### Fixed
- `cargo-deny` rows skip text lines (the trailing `advisories ok, bans ok, ...` summary, log lines) and parse only `{` lines, so a clean run reads clean instead of `not run`; `cargo-audit` ignores bracketed stderr lines before its JSON and reads `not run` when `vulnerabilities.found` or `count` disagrees with the list.
