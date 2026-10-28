### Changed
- agentic-delivery: `fitness_tick.py closable` now needs a real caller (a JSON hook/package entry, CI workflow, `.sh`, Makefile, or a loop entry whose line starts with the command), not a text mention. `baseline_guard.py` refuses a suspect baseline by default (`--normal` 5, `--max-load` 2 x cores; `--force` overrides). `wired_check.py` treats only explicit orphan/unused allowlist names, a `# orphan:` marker and an `allowlist:` key as an allowlist (bare words like "unused" no longer exempt a caller).
- agentic-delivery: the issue-dedupe hook, fitness check and flow-alarm doctrine now lives once in `references/flow-guards.md`; the other references link to it.

### Added
- agentic-delivery: `freeze_hook.py`, a fail-closed PreToolUse(Bash) hook in the operating-layer template that parses argv (global flags, wrappers, `bash -c`, `gh api .../merge`) and denies `git push` and `gh pr merge` while a freeze file exists; malformed input or an unreadable freeze state denies, a non-repo cwd allows. Quoting tricks, eval of variables and wrapper scripts remain a known ceiling.
