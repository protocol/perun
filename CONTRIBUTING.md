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
  `scripts/ci-tests.d/<slug>.sh` (one command line), not a line in `ci.yml`. CI splits the registrations over the
  parallel `perpr` legs by recorded seconds (`scripts/ci-durations.tsv`: the longest test goes first, to the least-loaded leg; a
  test with no row counts as the median, so adding one needs no table edit; `*.bg.sh` ones go round-robin;
  `SHARD=i/N bash scripts/ci-tests-shard.sh` lists leg i's of the N legs), so a test must not rely on another registration having run first.
  `bash scripts/run-ci-tests.sh --affected` runs only the registered tests a changed file can reach (the pre-push default),
  so run it before pushing instead of just your own new test.
  `bash scripts/ci-gates.sh fragments --config scripts/size-budgets.tsv changelog.d` checks the fragment's marker
  lines and headings (the pre-commit and pre-push hooks, land and CI run it), so a malformed fragment fails your
  commit instead of the release.
- **Test-time table:** refresh `scripts/ci-durations.tsv` when the slowest `perpr` leg's `Per-PR tests` step is more than 20%
  over the fastest on a PR run (until then a new test counts as the median, so only the balance drifts). Save the job log of
  every `perpr` leg as `leg1.log` ... `legN.log` (`gh api repos/<owner>/<repo>/actions/jobs/<job id>/logs`; the job id is in
  the job's URL on the run page), rebuild the rows (the seconds between consecutive `== <registration>` lines, rounded, at least 1)
  and put them under the table's header with its run id and date updated:

  ```bash
  awk 'FNR == 1 { p = "" } $2 == "==" && $3 ~ /^scripts\/ci-tests\.d\// { t = substr($1, 12, 2) * 3600 + substr($1, 15, 2) * 60 + substr($1, 18); d = t - q; if (d < 0) d += 86400; if (p != "") print p "\t" (d < 1.5 ? 1 : int(d + 0.5)); p = ($3 ~ /\.bg\.sh$/ ? "" : $3); q = t }' leg*.log | LC_ALL=C sort
  ```
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
push hook only checks conflict markers, the privacy scan of changed files, that every commit email is a noreply form (`git config user.email <id>+<user>@users.noreply.github.com`), and your configured tier. Repeating the full suite locally buys no extra safety and costs more
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
