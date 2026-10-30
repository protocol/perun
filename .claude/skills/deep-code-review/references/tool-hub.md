# Tool hub: routing to installed open-source security tools

Read this when a review should lean on external scanners via the tool hub (workflows, Python, Go, SBOM/lockfiles, IaC, Dockerfiles, MCP or skill configs), when `review_checks.sh` prints `NOT CHECKED:`, or before adding or opting in to a routed tool or skill, or to time a command against its base or smoke-load a running app (Perf tools).

Perun routes; it does not reimplement or vendor these tools. `scripts/review_checks.sh` holds one registry row per tool (`hub=` array: name, flags status, batch or per-file mode, file-match regex, license class, install hint) and reuses its existing timebox, heavy lease, exit-code and fail-closed JSON shape check (`sjson`). Findings are leads: verify each against the code.

## Rules every row obeys

- Missing tool: `NOT CHECKED: <tool> (install: <hint>)` on stderr, only when a changed file matches. A missing tool is never a clean result. Install hints are suggestions and were not verified.
- Wrong-shape or unparseable JSON, a crash, a timeout, or a tool-reported load or parse error (gosec `Golang errors`, checkov `parsing_errors`): `review_checks: not run: <tool> (<why>)`. Never read as clean, and not listed under "analyzers ran".
- Every NOT CHECKED or not-run case also lands in the stdout JSON as a row with `rule` `not-checked`, empty `file`, so an empty finding list cannot hide a tool that did not run.
- `review_checks.sh --full` scans every tracked file (base = git's empty tree) instead of a diff; gitleaks then runs once over the working tree (`--no-git -s .`), not HEAD. gitleaks honours the repo's `.gitleaksignore` fingerprints as of BASE (HEAD under `--full`).
- Flags status `verified` means the flags below were checked against the tool's official docs on 2026-10-27. `unverified` rows are skipped by default (one `NOT CHECKED` line), never run on a guess.
- License class `route-only`: never bundled or copied into this repo; run only when the user installed it. No tool is marked `bundle-ok` because licenses were not checked this session.
- Network: zizmor runs `--offline`; grype runs with `GRYPE_DB_AUTO_UPDATE=false` and `GRYPE_CHECK_FOR_APP_UPDATE=false` (no cached DB is a crash, so not-run); checkov runs `--skip-download` and `CKV_SKIP_PACKAGE_UPDATE_CHECK=true`; gosec runs with `GOPROXY=off`, because loading `./...` packages may otherwise fetch Go modules (modules missing from the local cache then surface as `Golang errors` and read as not checked). osv-scanner runs offline on a warm DB (no flag), online only with `REVIEW_OSV=1`, else not run. trivy (not a hub tool) runs with `TRIVY_DISABLE_TELEMETRY=true`. Env vars, not flags, so an older tool ignores them; each was a denied host (check.trivy.dev, toolbox-data.anchore.io, pypi.org) under a network-denying sandbox (trivy 0.76.1, grype 0.121.0, checkov 3.3.30, 2026-10-30). guarddog 3.2.0 (no offline flag) refreshes its top-package lists from github.com, hugovk.github.io and packages.ecosyste.ms at startup (seen under a dead proxy), so it runs with `GUARDDOG_TOP_PACKAGES_CACHE_LOCATION` pointing at fresh stub lists, which a local scan never reads; the `--no-sandbox` retry, which drops guarddog's own network block, also sets a dead proxy.
- Behind a TLS-breaking proxy, pre-seed the vuln DBs (`provision_tools.sh --print` does it, see Provisioning): `REVIEW_OSV_DB_DIR` (osv-scanner offline run; an empty dir prints the exact warm command and stays NOT CHECKED; an exported `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` that already holds a seeded database is used the same way, and `REVIEW_OSV=1` still asks the API instead. A cache with no database is never used: with none, osv-scanner prints empty results, not an error, which would read as clean) and `REVIEW_TRIVY_CACHE` (trivy `--cache-dir`; a missing DB stays not-run and prints `trivy --cache-dir DIR image --download-db-only`). `--repo DIR` replaces a `cd DIR &&` chain. In `supply_chain_check.sh`, a package npm marks `dev` (or osv puts in a dev/build/test group) is noted `dev-only` and capped at moderate.
- A batch tool (explicit file list) that returns a row for a file outside that list means the paths did not line up and findings may be lost: `not run: <tool> (N of M rows named a file outside the scanned list; findings may be missing)`, never a clean (gosec is exempt: it scans `./...`). Paths are compared in the changed-file form, so a tool that echoes `./.github/...` still lands on `.github/...`.
- Secrets and code snippets in tool output are never read into findings (bandit's `issue_text` is skipped too: its B105 text embeds the secret value; trufflehog runs with `--sarif` because its default and `--json` output print the secret, as Raw, RawV2, Redacted and SecretParts in JSON).
- trufflehog follows gitleaks' noise rules but not its suppressions (checked on trufflehog 3.99.7, 2026-10-30). With no repo `.gitleaks.toml`, the gitleaks template's skip paths are dropped from its file list and counted on stderr (`trufflehog template skipped N changed file(s)`), because its own `--exclude-paths` is ignored for files named on the command line. `.gitleaksignore` fingerprints and `.gitleaks-allow` hashes do not apply to it; an inline `trufflehog:ignore` comment on the finding's line does, and a change can add one, so read an added comment as a lead. A failed 200-file call (one unreadable file fails the whole call and prints nothing) is retried file by file: passing files keep their rows, a file that still fails is a `not-checked` row naming it (the tool is `partial`), and when none of the first three retried files passes it is `not run`.

## Provisioning (tools or caches NOT RUN)

The agent sandbox denies installs and most network, so the owner provisions scanners once, outside it. `bash scripts/provision_tools.sh` lists missing binaries and cold caches (installs and writes nothing); `--print` emits the ONE line to paste yourself (`brew` and `pipx` installs, plus the cache warm-ups). `review_checks.sh` then uses warm caches offline with no flag: trivy's own cache dir (`--skip-db-update --offline-scan`), the osv-scanner offline DB (`--offline-vulnerabilities`; `REVIEW_OSV=1` still means the online API, an explicit `REVIEW_OSV_DB_DIR` wins), and a local semgrep `p/default` snapshot as `--config FILE` in place of the registry pack.

- osv-scanner v2.7.0 stores the DB as `DIR/osv-scalibr/ECOSYSTEM/all.zip`; its offline-mode docs say `osv-scanner/`. Both count as warm. A lockfile whose ecosystem has no DB stays not-run; osv-scanner's `no offline version` message names the fix, `--print DIR` (a DIR always re-downloads: another ecosystem's zip already counts as warm).
- Trivy's DB download fails when `~/.docker/config.json` names a `credsStore` helper that is not installed (seen on one host, not in the docs); the owner line sets `DOCKER_CONFIG` to an empty dir for it.
- `pipx` and `uv tool` install into `~/.local/bin`, which a sandboxed PATH may lack: `review_checks.sh` appends it (`DCR_USER_BIN` overrides, empty disables). `DCR_CACHE_ROOT` overrides the user cache dir. `scrub_env.sh` pins both, so CI tests do not depend on what the host has installed.
- Every run ends with `review_checks: ran X / wired Y scanners; not run: ...; partial: ...; fixable: ...` and records it in `<git-common-dir>/review-checks-last.json`. Wired = had work this run (shellcheck, ruff/pyflakes and `--history` gitleaks too, never fixable); `partial` = ran with a narrower scope (trivy `secret-only`, trufflehog with files it could not scan, semgrep with errors or `bundled-only`: its `p/default` pack did not load, which a snapshot fixes). `perun_doctor.py` shows a WARN `review scanners` row while a wired tool had a fixable cause (osv-scanner's command names this repo as DIR) and INFO for a partial scope or an unfixable cause.

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
| `guarddog` | npm packages a changed `package-lock.json` newly adds (name@version absent from the merge-base lock; a bump counts) and that are installed under `node_modules` at the locked version (the installed `package.json` says so); `hasInstallScript` ones first, then at most 25 and about 300 s in all (`REVIEW_GUARDDOG_BUDGET`), the rest named in a `not-checked` row; not under `--full`; not a `hub=` row | `guarddog npm scan --output-format json DIR` on existing in-repo dirs only (it fetches a non-directory argument as a registry name), only when `guarddog --version` says 3.x; `--no-sandbox` (behind a dead proxy) only after its sandbox fails to start (nested); never `verify`; leads: `threat-*` rules only, each tagged `[heuristic]`; a rule that errors is a `not-checked` row and the other rules' hits stay; a newly added lock entry with `hasInstallScript` is a `package-lock` lead of its own | verified (`--help`, 3.2.0 source, real run 2026-10-30); the install-hook rules (`threat-npm-preinstall-script`, `threat-process-hooks`) match `*/package.json`, a nested one, so a package's own root `package.json` hook is never flagged | route-only |
| `snyk-agent-scan` | MCP and skill configs | not run | unverified: docs show no offline mode (it calls the Agent Scan API and can start MCP servers) | route-only |
| `semgrep` bundled rule `perun.gha.actor-allowlist-from-vars` | workflows and `action.yml`: an actor check (`github.actor`, `github.triggering_actor`, `GITHUB_ACTOR`) fed by `vars.NAME`, a list anyone with write access can edit | none of its own: `templates/semgrep-taint/gha.yml` loads with the other bundled rules, and only when the repo has no semgrep rules of its own | a rule, not a tool flag; a `[heuristic]` lead that names the fix; GitHub docs verified 2026-10-30 | own rule |

Already routed before the hub: gitleaks, trufflehog, osv-scanner, semgrep, trivy (see `method-situational.md`).

pinact (`pinact run`) is the fixer for unpinned-action findings; it needs the GitHub API, so never in offline runs.

## Perf tools (own scripts, not run by `review_checks.sh`)

| Tool | Covers | Command shape | Flags | Class |
|---|---|---|---|---|
| `hyperfine` | Wall-clock A/B of one command, base tree vs current tree | `bash scripts/perf_compare.sh [--runs N] [--base REF] [--json FILE] -- CMD...` | verified (`hyperfine --help`, 2.0.0, 2026-10-30); the JSON export is read strictly (`schema_version` 2, seconds) | route-only |
| `k6` | Load smoke of a running app on loopback or `APP_PENTEST_ALLOW` | `bash scripts/app_pentest.sh --load [--vus N] [--secs N] URL`; rules in `app-pentest.md` | verified (`k6 run --help`, v2.3.0, 2026-10-30); the `--new-machine-readable-summary` JSON is read strictly (version 1.x) | route-only |

`perf_compare.sh` runs CMD in a detached worktree of BASE (default: the merge-base with `origin/main`; checked out with git hooks off) and in the current tree, uncommitted edits included, under `hyperfine --warmup 1 --runs N` (N from 2 to 9999, default 10). Untracked files are not in the base, so CMD must build or fetch what it needs, and it must exit 0 in both trees.

- One stdout line: `perf_compare: base X ms (sd Y, n=N) | current X ms (sd Y, n=N) | ratio R.RRx | VERDICT | json=PATH`. VERDICT is `within noise (ranges overlap)` when the means differ by no more than the two sds added up, else `slower` or `faster` plus `(ranges do not overlap)`. The sd is run spread, not a standard error, so "conservative" covers run spread only: base runs fully before current, so drift between blocks can read as `slower` or `faster`. "within noise" makes no claim, it does not say "equal". The raw export is copied to `--json FILE` (default `<git-common-dir>/perf-compare-last.json`).
- Exit 0 verdict printed; 1 hyperfine missing (`NOT CHECKED: hyperfine (install: brew install hyperfine)` on stderr, never a clean result) or the run failed (checkout, CMD or an unsupported export); 2 refused usage. The worktree is removed on exit and on HUP, INT or TERM.
- `heavy_gate.py` holds a run while the machine is busy. Start it on an idle machine and repeat: one verdict is a lead.

## Route-only skills (opt-in, never vendored)

| Skill | License note | Rule |
|---|---|---|
| trailofbits/skills | CC-BY-SA (unverified: the license text was not fetched) | Opt-in. Pin a commit. Run `snyk-agent-scan` (or read the skill by hand if that tool is unverified) before first use. Never copy into this repo. |
| openai/codex-security | not checked | Same. |
| anthropics/claude-code-security-review | not checked | Same. |

Pinned commit: none yet. The user records the commit they reviewed; an unpinned route is not run.

## Adding a tool

Add one `hub=` row, a `sjson` shape check and row mapper in `review_checks.sh`, a shim case in `scripts/test-review-checks-tool-hub.sh`, and a row above. Verify flags from the tool's `--help` or official docs first; if you cannot, mark it `unverified`.
