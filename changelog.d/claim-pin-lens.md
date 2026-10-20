### Added
- Claim-vs-code lens: every guarantee-bearing comment, docstring or UI string in the diff must name a test that forces the adversarial condition it denies (concurrent caller, retry after failure, cached key, bypass path); an unpinned guarantee is a finding, High when it protects privacy, consent, money or data. A claim whose named pinning test exists yields no finding. Field cause: 6 of 22 findings in one review were comments promising what the code did not keep. Depth is a bullet in `method-situational.md` (now triggered on any `DIFF`), cross-linked with `testing-situational.md`'s phantom-contract rule. A one-line required step is added to `method.md` Phase 1 (full path) and to `compact-mode.md` step 7 (quick path, self-contained so the "Read no other reference" rule holds). Evals: `claim-vs-code-unpinned-guarantee-comment` (finding) and `claim-vs-code-pinned-guarantee-no-finding` (no finding).

size-budget-raise: .claude/skills/deep-code-review/references/method.md 43291→43518 required-step pointer line
size-budget-raise: .claude/skills/deep-code-review/references/method-situational.md 41040→42802 claim-vs-code lens bullet and DIFF trigger
size-budget-raise: .claude/skills/deep-code-review/references/compact-mode.md 2146→2504 quick-path step 7
size-budget-raise: .claude/skills/deep-code-review/references/testing-situational.md 40355→40463 cross-link to the lens
