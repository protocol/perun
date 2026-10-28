# Tool hub: routing to installed open-source security tools

Read this when a review should lean on external scanners via the tool hub (workflows, Python, Go, SBOM/lockfiles, IaC, Dockerfiles, MCP or skill configs), when `review_checks.sh` prints `NOT CHECKED:`, or before adding or opting in to a routed tool or skill.

Perun routes; it does not reimplement or vendor these tools. `scripts/review_checks.sh` holds one registry row per tool (`hub=` array: name, flags status, batch or per-file mode, file-match regex, license class, install hint) and reuses its existing timebox, heavy lease, exit-code and fail-closed JSON shape check (`sjson`). Findings are leads: verify each against the code.

## Rules every row obeys

- Missing tool: `NOT CHECKED: <tool> (install: <hint>)` on stderr, only when a changed file matches. A missing tool is never a clean result. Install hints are suggestions and were not verified.
- Wrong-shape or unparseable JSON, a crash, a timeout, or a tool-reported load or parse error (gosec `Golang errors`, checkov `parsing_errors`): `review_checks: not run: <tool> (<why>)`. Never read as clean, and not listed under "analyzers ran".
- Every NOT CHECKED or not-run case also lands in the stdout JSON as a row with `rule` `not-checked`, empty `file`, so an empty finding list cannot hide a tool that did not run.
- Flags status `verified` means the flags below were checked against the tool's official docs on 2026-10-27. `unverified` rows are skipped by default (one `NOT CHECKED` line), never run on a guess.
- License class `route-only`: never bundled or copied into this repo; run only when the user installed it. No tool is marked `bundle-ok` because licenses were not checked this session.
- Network: zizmor runs `--offline`; grype runs with `GRYPE_DB_AUTO_UPDATE=false` (no cached DB is a crash, so not-run); checkov runs `--skip-download`; gosec runs with `GOPROXY=off`, because loading `./...` packages may otherwise fetch Go modules (modules missing from the local cache then surface as `Golang errors` and read as not checked). osv-scanner stays behind `REVIEW_OSV=1`.
- Behind a TLS-breaking proxy, pre-seed the vuln DBs: `REVIEW_OSV_DB_DIR` (osv-scanner offline run; an empty dir prints the exact warm command and stays NOT CHECKED) and `REVIEW_TRIVY_CACHE` (trivy `--cache-dir`; a missing DB stays not-run and prints `trivy --cache-dir DIR image --download-db-only`). `--repo DIR` replaces a `cd DIR &&` chain. In `supply_chain_check.sh`, a package npm marks `dev` (or osv puts in a dev/build/test group) is noted `dev-only` and capped at moderate.
- Secrets and code snippets in tool output are never read into findings (bandit's `issue_text` is skipped too: its B105 text embeds the secret value).

## CLI tools (run by `review_checks.sh`)

| Tool | Covers | Command shape | Flags | Class |
|---|---|---|---|---|
| `zizmor` | GitHub Actions workflows | `zizmor --format=json --offline FILES`; exit 11-14 means findings | verified (usage docs, JSON shape, exit codes) | route-only |
| `bandit` | Python security | `bandit -q -f json --exit-zero FILES` | verified (man page); JSON shape checked strictly, not documented | route-only |
| `gosec` | Go security | `gosec -fmt=json -no-fail -out FILE ./...` (needs `go.mod`) | verified (README); JSON shape checked strictly, not documented | route-only |
| `grype` | SBOM files only (`sbom:`); lockfiles stay with osv-scanner and trivy, because `dir:` scans the whole tree and cannot be credited to one lockfile | `grype sbom:FILE -o json` | verified (CLI and config docs) | route-only |
| `checkov` | Terraform, compose files, Dockerfiles | `checkov -f FILE -o json --quiet --skip-download --soft-fail` | verified (CLI reference); JSON shape checked strictly, not documented | route-only |
| `hadolint` | Dockerfiles | `hadolint -f json --no-fail FILE` | verified (README); JSON shape checked strictly, not documented | route-only |
| `snyk-agent-scan` | MCP and skill configs | not run | unverified: docs show no offline mode (it calls the Agent Scan API and can start MCP servers) | route-only |

Already routed before the hub: gitleaks, osv-scanner, semgrep, trivy (see `method-situational.md`).

## Route-only skills (opt-in, never vendored)

| Skill | License note | Rule |
|---|---|---|
| trailofbits/skills | CC-BY-SA (unverified: the license text was not fetched) | Opt-in. Pin a commit. Run `snyk-agent-scan` (or read the skill by hand if that tool is unverified) before first use. Never copy into this repo. |
| openai/codex-security | not checked | Same. |
| anthropics/claude-code-security-review | not checked | Same. |

Pinned commit: none yet. The user records the commit they reviewed; an unpinned route is not run.

## Adding a tool

Add one `hub=` row, a `sjson` shape check and row mapper in `review_checks.sh`, a shim case in `scripts/test-review-checks-tool-hub.sh`, and a row above. Verify flags from the tool's `--help` or official docs first; if you cannot, mark it `unverified`.
