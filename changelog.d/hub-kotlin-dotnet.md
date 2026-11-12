### Added
- Tool hub: detekt (Kotlin, Apache-2.0) and security-code-scan (.NET Roslyn analyzer, LGPL-3.0) get explicit not-routed rows in tool-hub.md with their evidence, and a test shows stub binaries of both are never run. detekt's CLI source shows no network code but the analysis core was not read; security-code-scan runs inside a project build, not on changed files. Sources and license checks fetched 2026-11-12 are logged in docs/standards-index.md.

### Changed
- tool-hub.md: the devskim row now says its SARIF shape is stub-tested only, not verified.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 46217→47544 two not-routed rows with their evidence and the devskim wording fix
