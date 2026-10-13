### Changed
- idea-critic: moved the Anti-rationalization (excuse → rebuttal) table out of `SKILL.md` into the routed `references/anti-rationalization.md` (same content, read before `PASS_TO_USER` or when skipping a hat). `SKILL.md` drops from 16,320 to 15,474 bytes, under consumers' ~4,000-token (chars/4) core cap.
- Size gate: every `.claude/skills/*/SKILL.md` must now be at most 16,000 bytes. Only `agentic-delivery` and `deep-code-review` (over the cap today) are allowlisted, frozen at their current byte budgets (may shrink, never grow). Planted-RED self-test added.
