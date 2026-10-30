# Tool hub: routing to installed open-source security tools

Read this when a review should lean on external scanners via the tool hub (workflows, Python, Go, SBOM/lockfiles, IaC, Dockerfiles, MCP or skill configs), when `review_checks.sh` prints `NOT CHECKED:`, or before adding or opting in to a routed tool or skill.

Perun routes; it does not reimplement or vendor these tools. `scripts/review_checks.sh` holds one registry row per tool (`hub=` array: name, flags status, batch or per-file mode, file-match regex, license class, install hint) and reuses its existing timebox, heavy lease, exit-code and fail-closed JSON shape check (`sjson`). Findings are leads: verify each against the code.

## Rules every row obeys

- Missing tool: `NOT CHECKED: <tool> (install: <hint>)` on stderr, only when a changed file matches. A missing tool is never a clean result. Install hints are suggestions and were not verified.
- Wrong-shape or unparseable JSON, a crash, a timeout, or a tool-reported load or parse error (gosec `Golang errors`, checkov `parsing_errors`): `review_checks: not run: <tool> (<why>)`. Never read as clean, and not listed under "analyzers ran".
- Every NOT CHECKED or not-run case also lands in the stdout JSON as a row with `rule` `not-checked`, empty `file`, so an empty finding list cannot hide a tool that did not run.
- `review_checks.sh --full` scans every tracked file (base = git's empty tree) instead of a diff; gitleaks then runs once over the working tree (`--no-git -s .`), not HEAD. gitleaks honours the repo's `.gitleaksignore` fingerprints as of BASE (HEAD under `--full`).
- Flags status `verified` means the flags below were checked against the tool's official docs on 2026-10-27. `unverified` rows are skipped by default (one `NOT CHECKED` line), never run on a guess.
- License class `route-only`: never bundled or copied into this repo; run only when the user installed it. No tool is marked `bundle-ok` because licenses were not checked this session.
- Network: zizmor runs `--offline`; grype runs with `GRYPE_DB_AUTO_UPDATE=false` (no cached DB is a crash, so not-run); checkov runs `--skip-download`; gosec runs with `GOPROXY=off`, because loading `./...` packages may otherwise fetch Go modules (modules missing from the local cache then surface as `Golang errors` and read as not checked). osv-scanner runs offline on a warm DB (no flag), online only with `REVIEW_OSV=1`, else not run.
- Behind a TLS-breaking proxy, pre-seed the vuln DBs (`provision_tools.sh --print` does it, see Provisioning): `REVIEW_OSV_DB_DIR` (osv-scanner offline run; an empty dir prints the exact warm command and stays NOT CHECKED; an exported `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` that already holds a seeded database is used the same way, and `REVIEW_OSV=1` still asks the API instead. A cache with no database is never used: with none, osv-scanner prints empty results, not an error, which would read as clean) and `REVIEW_TRIVY_CACHE` (trivy `--cache-dir`; a missing DB stays not-run and prints `trivy --cache-dir DIR image --download-db-only`). `--repo DIR` replaces a `cd DIR &&` chain. In `supply_chain_check.sh`, a package npm marks `dev` (or osv puts in a dev/build/test group) is noted `dev-only` and capped at moderate.
- A batch tool (explicit file list) that returns a row for a file outside that list means the paths did not line up and findings may be lost: `not run: <tool> (N of M rows named a file outside the scanned list; findings may be missing)`, never a clean (gosec is exempt: it scans `./...`). Paths are compared in the changed-file form, so a tool that echoes `./.github/...` still lands on `.github/...`.
- Secrets and code snippets in tool output are never read into findings (bandit's `issue_text` is skipped too: its B105 text embeds the secret value).

## Provisioning (tools or caches NOT RUN)

The agent sandbox denies installs and most network, so the owner provisions scanners once, outside it. `bash scripts/provision_tools.sh` lists missing binaries and cold caches (installs and writes nothing); `--print` emits the ONE line to paste yourself (`brew` and `pipx` installs, plus the cache warm-ups). `review_checks.sh` then uses warm caches offline with no flag: trivy's own cache dir (`--skip-db-update --offline-scan`), the osv-scanner offline DB (`--offline-vulnerabilities`; `REVIEW_OSV=1` still means the online API, an explicit `REVIEW_OSV_DB_DIR` wins), and a local semgrep `p/default` snapshot as `--config FILE` in place of the registry pack.

- osv-scanner v2.7.0 stores the DB as `DIR/osv-scalibr/ECOSYSTEM/all.zip`; its offline-mode docs say `osv-scanner/`. Both count as warm. A lockfile whose ecosystem has no DB stays not-run; osv-scanner's `no offline version` message names the fix, `--print DIR` (a DIR always re-downloads: another ecosystem's zip already counts as warm).
- Trivy's DB download fails when `~/.docker/config.json` names a `credsStore` helper that is not installed (seen on one host, not in the docs); the owner line sets `DOCKER_CONFIG` to an empty dir for it.
- `pipx` and `uv tool` install into `~/.local/bin`, which a sandboxed PATH may lack: `review_checks.sh` appends it (`DCR_USER_BIN` overrides, empty disables). `DCR_CACHE_ROOT` overrides the user cache dir. `scrub_env.sh` pins both, so CI tests do not depend on what the host has installed.
- Every run ends with `review_checks: ran X / wired Y scanners; not run: ...; partial: ...; fixable: ...` and records it in `<git-common-dir>/review-checks-last.json`. Wired = had work this run (shellcheck, ruff/pyflakes and `--history` gitleaks too, never fixable); `partial` = ran with a narrower scope (trivy `secret-only`, semgrep with errors or `bundled-only`: its `p/default` pack did not load, which a snapshot fixes). `perun_doctor.py` shows a WARN `review scanners` row while a wired tool had a fixable cause (osv-scanner's command names this repo as DIR) and INFO for a partial scope or an unfixable cause.

## CLI tools (run by `review_checks.sh`)

| Tool | Covers | Command shape | Flags | Class |
|---|---|---|---|---|
| `zizmor` | GitHub Actions workflows | `zizmor --format=json --offline FILES`; exit 11-14 means findings | verified (usage docs, JSON shape, exit codes) | route-only |
| `actionlint` | GitHub Actions workflows | `actionlint -format '{{json .}}' FILES`; exit 1 means findings (2 bad flag, 3 fatal) | verified (`actionlint -h` and a real run, 2026-10-30); JSON shape checked strictly | route-only |
| `bandit` | Python security | `bandit -q -f json --exit-zero FILES` | verified (man page); JSON shape checked strictly, not documented | route-only |
| `gosec` | Go security | `gosec -fmt=json -no-fail -out FILE ./...` (needs `go.mod`) | verified (README); JSON shape checked strictly, not documented | route-only |
| `grype` | SBOM files only (`sbom:`; a `.json` name with `sbom`, `bom`, `cdx` or `spdx` as a whole name part, so `app.cdx.json` but not `bomb.json`); lockfiles stay with osv-scanner and trivy, because `dir:` scans the whole tree and cannot be credited to one lockfile | `grype sbom:FILE -o json` | verified (CLI and config docs) | route-only |
| `checkov` | Terraform and Dockerfiles (compose files are not a checkov framework: not routed) | `checkov -f FILE -o json --quiet --skip-download --soft-fail`; a flat summary with no `results` and `parsing_errors` 0 (nothing applicable to check, e.g. variables-only Terraform) is a clean file | verified (CLI reference); JSON shape checked strictly, not documented | route-only |
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
