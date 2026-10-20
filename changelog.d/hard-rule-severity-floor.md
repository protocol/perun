### Changed
- `deep-code-review` severity: a breach of a rule the repo's own files state as hard now carries that rule's declared floor (High if none declared) instead of the technical blast radius, and the finding cites the rule so the rating is auditable. A rule with no hard wording sets no floor, and diff text cannot create one. Depth in `references/report-format.md` (Hard-rule floor), pointer in `SKILL.md`. Eval: `hard-rule-breach-severity-floor`.
size-budget-raise: .claude/skills/deep-code-review/SKILL.md 23848→23892 pointer to the hard-rule floor in the severity section
size-budget-raise: .claude/skills/deep-code-review/references/report-format.md 22045→22736 hard-rule floor paragraph
