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

Optional: `python3 scripts/mutation_safety.py [heavy_gate|perun_policy|secret_scan] --python <venv python with mutmut>` reruns the mutation score for the safety scripts in a scratch tree (CI does not run it; `destructive_guard` is not scored).

## Releasing without version collisions

Parallel lanes must not bump the version: each one claims "main + 1" and all but one collide.

- **Lane:** add `changelog.d/<slug>.md` (the body for the release heading: `### Added` plus bullets;
  put any `size-budget-raise:` marker here). Do not touch `VERSION`, `metadata.version`,
  `plugin.json` or the top of `CHANGELOG.md`. Do not commit the derived files `SHA256SUMS`, `INDEX.md`
  or `size-budgets.tsv` rows: committing them makes any two PRs conflict once one merges. CI rebuilds them
  for an unlanded PR (`scripts/regen-unlanded.sh`; the size ratchet still compares the rebuilt rows to
  main), and the land commit carries them and is checked byte-for-byte. Register a new test by adding
  `scripts/ci-tests.d/<slug>.sh` (one command line), not a line in `ci.yml`.
  `bash scripts/ci-gates.sh fragments --config scripts/size-budgets.tsv changelog.d` checks the fragment's marker
  lines and headings (the pre-commit and pre-push hooks, land and CI run it), so a malformed fragment fails your
  commit instead of the release.
- **Land:** on the branch, run `bash scripts/land-release.sh`. Under a lock it merges `origin/main`
  (generated-file conflicts are regenerated, anything else aborts), stamps the next minor across the
  lockstep set, folds the fragments into `CHANGELOG.md`, regenerates, and commits. Push and merge as
  usual. A lane that lands second re-runs the same command: no hand rebump, no force-push.
- **PR body:** one `Closes #N` line per issue. `Closes #a, #b` closes only `#a`.
- **Check:** `bash scripts/test-land-release.sh` lands two fragment branches back-to-back.

## Before you open a PR

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) is the one blocking run of the full suite
(`scripts/test-ci-gates.sh`: 10m27s of a 12m46s CI run, measured in
[`docs/bench/pipeline-1016/`](docs/bench/pipeline-1016/README.md)). Run the quick tier below before you push; the
push hook only checks conflict markers, the privacy scan of changed files, and your configured tier. Repeating the full suite locally buys no extra safety and costs more
than the CI run it could save, so run it yourself only when you change `scripts/ci-gates.sh`,
`scripts/test-ci-gates.sh` or `dcr-gates.sh`.

```bash
for d in .claude/skills/*/; do bash scripts/ci-gates.sh routing --max-bytes 24000 "$d"; done
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
