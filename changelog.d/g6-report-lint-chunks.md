### Changed
- Class label `object-access` is now `object-level-authz` in the report vocabulary and linter; a test pins every vocabulary label in `whole-project-report.md` to the linter's `CLASSES`.
- `report_contract_lint.py` no longer treats a backticked prose token such as `net/http` or `text/html` as a path citation unless it has a file extension, a `:line`/`#L` suffix, or a first path segment that exists under `--root`.
- `report_contract_lint.py --part` appends stdin to a temp draft keyed by the real path of `--root` and prints the line count; `--done` lints that draft and deletes it. Security-review mode step 5 keeps each heredoc under 8,000 chars because Claude Code's bash parser denies commands of about 10,000+ chars, and sends a longer draft as `--part` chunks.
- `report_contract_lint.py --part` must arrive in order from 1 (else exit 2, resend from part 1); the draft is refused unless owned by the caller and mode 0600, opened with `O_NOFOLLOW`; `--done` deletes it in a `finally`, and only `--done` prints the emit-verbatim line.

size-budget-raise: .claude/skills/deep-code-review/references/security-review-mode.md 12155→13449 step 5 chunked-heredoc rule for the length limit
size-budget-raise: .claude/skills/deep-code-review/references/whole-project-report.md 4167→4772 rename of the object-level-authz class label
