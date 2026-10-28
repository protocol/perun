### Added
- deep-code-review `scripts/dynamic_probe.py`: opt-in dynamic step for a locally running app (localhost or 127.0.0.1 only, never follows redirects). Probes malformed percent-encoding and oversized inputs (any 5xx is a finding), a burst on a named endpoint for missing rate limiting, security headers, and open redirect, and prints review_checks-shaped rows (finding, clean or not-checked). Routed from `full-audit.md` via the new `references/dynamic-probe.md`. Tests: `scripts/test_dynamic_probe.py`.
size-budget-raise: .claude/skills/deep-code-review/references/full-audit.md 6584→6757 route line to the dynamic probe step
size-budget-raise: .claude/skills/INDEX.md 14885→14993 dynamic_probe.py script row
size-budget-raise: .claude/skills/deep-code-review/INDEX.md 20406→20551 dynamic-probe.md reference row and script count
size-budget-raise: .claude/skills/deep-code-review/INDEX-scripts.md 5356→5498 dynamic_probe.py script row
size-budget-raise: .claude/skills/deep-code-review/references/full-map.md 18985→19020 route to dynamic-probe.md

size-budget-raise: .claude/skills/deep-code-review/references/full-map.md 18985→18997 routes dynamic-probe.md
