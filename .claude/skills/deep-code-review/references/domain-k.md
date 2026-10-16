# Domain K checklist

Read this when domain K (Build, CI/CD, supply chain & release) is applicable in Phase 2 — the coverage ledger marks it, or a DIFF quick-path touches it. Split from `domain-checklists.md`, whose preamble (the 🚩 convention and the language-grep pointer) applies here.

### K. Build, CI/CD, supply chain & release → `references/release-engineering.md`
Two halves: build/supply-chain (below) and the **release** half — feature-flag
lifecycle, canary/blue-green claims vs actual config, DORA-or-`UNMEASURED` —
`references/release-engineering.md`.
- One-command reproducible build; lockfiles committed and honored; CI gates
  merge on lint + format + type + tests + security/dependency scan.
- **A new or changed gate ships with its measured false-positive rate on HEAD**
  in the PR description (target ≤10%), not only a description of what it
  detects. Sound-looking detection logic can still fire mostly on non-defects
  in a real codebase: one observed run had a naive dead-export scan at 93%
  false positives, and a comment-density heuristic scored the best-documented
  files worst. A gate landed without that number is unproven.
- **Runner-minute cost of the workflow itself** (the staged fan-out remedy for
  an agent swarm's duplicate-CI shape lives in `references/parallel-audit.md`,
  not repeated here): a PR-triggered workflow needs `concurrency:` with a
  truthy `cancel-in-progress` so a superseded push stops burning instead of
  racing to finish; every job needs `timeout-minutes` (GitHub applies its own
  large default ceiling per job when it's unset — verify the current number
  before citing it as fixed); `push` to the default branch stacked with
  `pull_request` on the same workflow re-runs the same commits on merge only
  when required-status-checks are **strict** (branch must be up to date before
  merging) — non-strict repos can keep both; a `schedule:` cron firing more
  than once an hour, and an oversized `strategy.matrix` (job count grows
  combinatorially per added axis), both burn minutes without a reviewer ever
  seeing a duplicate run to object to; a workflow that only runs tests but
  triggers with no `paths`/`paths-ignore` filter still re-runs on a docs-only
  change (`.claude/skills/deep-code-review/scripts/ci_cost_lint.py` checks
  these deterministically — plus the docs-only-trigger heuristic as advisory —
  and `--gate` fails a PR on the blocking ones; `ci_cost_advisor.py` prices them and
  prints a local-first patch: a public repo on standard runners is free). The mandatory,
  universal minimum-cost profile (integration-branch CI ban, main-only hosted
  CI shape, self-hosted-runner isolation, merge-queue plan gate, spend/token
  backstops) is the canonical doctrine in
  `agentic-delivery/references/host-enforcement.md`'s "Minimum-cost CI & token
  profile" — not restated here.
- **No self-hosted runner on a developer machine** unless it is ephemeral and runs as a
  low-privilege account or VM; a persistent one runs every PR's code as that user
  (`infra-iac-containers.md`, CICD-SEC-7).
- Third-party CI actions **pinned to a commit SHA** (not `@main`/`@v3`), bumped
  by a bot that passes the same gates; secrets from the CI store, never echoed
  (`set -x` leaks). **Package-signature verification is blocking**; transitive-CVE
  audit is advisory. SBOM + build provenance (SLSA) for releases; rollbacks
  possible; **verify identifier ownership before deploy** (a slug/app-id another
  service owns gets silently clobbered).
- **Dependency currency & safe upgrades** → `references/dependency-currency-and-upgrades.md`.
  Are third-party deps, runtimes, and base images on a supported **latest-stable**
  version, with no known-vulnerable or EOL/unmaintained/deprecated components
  (audit the **committed lockfile**, transitive deps included)? And is upgrading
  *disciplined*: one dep/group at a time, changelog/migration read, risk sized by
  the **semver delta** (a MAJOR is a breaking change by definition), lockfile
  regenerated, the new release checked it isn't itself malicious (cross-ref A03),
  and the project's **own aggregate gate proven green on the bumped tree** before
  merge? Staleness is an A03 security risk; a blind jump to "latest" is how a
  breaking or hijacked version lands — the review closes the *risky* gap through
  the gate, it does not bump everything. Rank by exploitable consequence: a
  known-exploited CVE on a reachable path is Critical/High; merely-behind-latest
  with no vuln is Low/`Nit:` currency debt (batch it, recommend an update bot),
  never outranking a real defect.
- The **privacy/PII gate fails closed when its banned-terms input is missing**,
  scans the lines a branch adds (fork PRs included), and never echoes a match.
- 🚩 green CI that skips tests, secrets in CI logs, actions on a mutable tag, no
  dependency scan, non-reproducible build, deploy without ownership check, a
  known-vulnerable or **EOL** dependency/runtime/base image shipping, a single
  "update all dependencies" commit with no per-dep test evidence, no update-bot
  config (`dependabot.yml`/`renovate.json`) beside a long tail of outdated deps.
