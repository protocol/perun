# Supply-chain check (OSS tools, one command)

**Read this when** gating a deploy on dependency advisories, hardening a repo's GitHub Actions, or adding code scanning
to a public repo. Companion to `dependency-currency-and-upgrades.md` (what to upgrade) and `appsec-supply.md` (what to look for).

## Run it

```bash
bash .claude/skills/deep-code-review/scripts/supply_chain_check.sh [--online] [--fail-on high] [--scorecard owner/repo] [DIR]
```

Exit codes, severity bands and the opt-in rules live in the script header (single copy). A skipped check is never a
silent pass: it prints `SKIPPED <tool>: <reason>` and the run exits 3 (INCOMPLETE) unless `--allow-skip`.

| Check | Tool | Network | Gate |
| --- | --- | --- | --- |
| Dependency advisories on lockfiles | `osv-scanner` | **Opt-in** (`--online`): queries `api.osv.dev` | fails at `--fail-on` (default `high`); prints counts and fixed versions |
| Workflow security (injection, unpinned or over-permissioned actions) | `zizmor` | none | any finding fails |
| Workflow syntax and shell | `actionlint` | none | any finding fails |
| Repo posture (branch protection, pinned deps, review) | `scorecard` (OpenSSF) | queries GitHub; `--scorecard owner/repo`, public repos | informational scores, no threshold |

Pre-deploy: `--online --fail-on high`; block the release on any non-zero exit. osv-scanner exit 128 (no package
sources found) is reported as a failure, not confirmed as "nothing to scan".

osv rows carry a reach tag: an npm package no source file imports prints `(reach: dev-only|transitive)`; only dev-only skips the gate unless `SUPPLY_CHAIN_STRICT=1` (transitive may be reached via a direct dependency); unknown reach is gated.

## Sandbox degradation

Under the macOS agent sandbox, `supply_chain_check.sh` retries a crashed `osv-scanner` CLI (Go TLS x509 -26276) via the
OSV API with curl (npm `package-lock.json`, pinned `requirements*.txt`) and prints `osv: api-fallback`. `review_checks.sh`
runs semgrep with `HOME`/`SEMGREP_USER_HOME` in a temp dir, and retries a failed trivy misconfig scan with
`--scanners secret`, printing `trivy: secret-only (misconfig bundle unreachable)`. Fallbacks are always announced.

## CodeQL template (copy into the target repo)

Not installed for you. Free on public repos; private repos need GitHub Code Security. Save as `.github/workflows/codeql.yml`,
set `language` to the repo's languages (`actions`, `javascript-typescript`, `python`, `go`, `java-kotlin`, `ruby`, `csharp`, `cpp`, `swift`, `rust`),
and pin each action to a full commit SHA before merging (run `zizmor` to confirm).

```yaml
name: CodeQL
on:
  push: {branches: [main]}
  pull_request: {branches: [main]}
  schedule: [{cron: "17 3 * * 1"}]
permissions: {contents: read}
jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions: {contents: read, security-events: write}
    strategy:
      fail-fast: false
      matrix: {language: [actions, javascript-typescript]}
    steps:
      - uses: actions/checkout@v4 # pin to a SHA
      - uses: github/codeql-action/init@v3 # pin to a SHA
        with: {languages: "${{ matrix.language }}", build-mode: none}
      - uses: github/codeql-action/analyze@v3 # pin to a SHA
        with: {category: "/language:${{ matrix.language }}"}
```

Unverified this session: tool flags and the CodeQL language list track upstream releases; run `<tool> --help` and the
CodeQL docs before relying on a flag.
