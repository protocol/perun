# Contributing

Thanks for improving the deep code-review skill. The engineering standards, the
definition of done, and the hard rules for this repository live in
**[`CLAUDE.md`](CLAUDE.md)** — it is the single source of truth and governs every
change. Read it first; the essentials are only summarized here.

## The essentials

- **One deliverable, one home.** The skill lives only in
  `.claude/skills/deep-code-review/`. Never create a second copy — `install.sh`
  copies *from* there.
- **No duplication.** `SKILL.md` holds the map and the concise checklists; each
  `references/*.md` holds the depth `SKILL.md` doesn't. Link, don't restate — and
  every reference must be routed from `SKILL.md`.
- **Verify before you cite.** Any standard, version, or date added to the skill or
  to `docs/standards-index.md` must come from a source you fetched, recorded with
  its URL and verification date. Never paste a remembered link.
- **Prose lessons carry a mechanism.** A commit that edits a skill's `SKILL.md` or
  `references/*.md` must also touch an eval, a skill script, or
  `scripts/test-ci-gates.sh`, or carry a `No-Mechanism-Reason:` trailer; a
  version-stamp-only `SKILL.md` bump is exempt. See the definition of done in
  `CLAUDE.md`.
- **No fabrication, no private data.** See `CLAUDE.md` for the hard confidentiality
  and no-fabrication rules; they apply to code, comments, docs, commits, and git
  history.

## Releasing without version collisions

Parallel lanes must not bump the version: each one claims "main + 1" and all but one collide.

- **Lane:** add `changelog.d/<slug>.md` (the body for the release heading: `### Added` plus bullets;
  put any `size-budget-raise:` marker here). Do not touch `VERSION`, `metadata.version`,
  `plugin.json` or the top of `CHANGELOG.md`. Run `bash scripts/land-release.sh --regen` before
  pushing so INDEX.md, `SHA256SUMS` and `size-budgets.tsv` match your tree. `bash scripts/ci-gates.sh fragments
  --config scripts/size-budgets.tsv changelog.d` checks the fragment's marker lines and headings (the pre-commit
  and pre-push hooks, land and CI run it), so a malformed fragment fails your commit instead of the release.
- **Land:** on the branch, run `bash scripts/land-release.sh`. Under a lock it merges `origin/main`
  (generated-file conflicts are regenerated, anything else aborts), stamps the next minor across the
  lockstep set, folds the fragments into `CHANGELOG.md`, regenerates, and commits. Push and merge as
  usual. A lane that lands second re-runs the same command: no hand rebump, no force-push.
- **PR body:** one `Closes #N` line per issue. `Closes #a, #b` closes only `#a`.
- **Check:** `bash scripts/test-land-release.sh` lands two fragment branches back-to-back.

## Before you open a PR

Run the same gates CI runs ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

```bash
bash scripts/test-ci-gates.sh
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/deep-code-review
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/agentic-delivery
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/idea-critic
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/communication-structure
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/contribution
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/product-discovery
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/agentic-ceo
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/growth-analytics
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/positioning
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/business-ops
bash scripts/ci-gates.sh routing --max-bytes 24000 .claude/skills/product-output-safety
bash scripts/ci-gates.sh version .
bash scripts/ci-gates.sh privacy --banlist .banlist.txt .
bash scripts/ci-gates.sh enumeration .
bash scripts/ci-gates.sh size --config scripts/size-budgets.tsv .
python3 scripts/eval_predicates.py --selftest
bash -n install.sh
```

Green gates, the definition of done in `CLAUDE.md` satisfied, and a one-line note
of what you verified in the PR body. Each skill `description` must be ≤1024
characters (Agent Skills spec).
