Read this when a finding claims that input reaches a sink, that a secret is live, that a dependency version is vulnerable, or that you are exposed through a dependency, or when the review ingests scanner output (SARIF, OSV JSON) or names a SAST engine. Split from `security-appsec.md` (its `Secrets` section is the "`Secrets` rule" cited below). Moved verbatim, except where a line now says "in security-appsec.md" instead of "above".

## Deterministic corroboration (cross-cutting) — an LLM claim rides on a proof it cannot generate

Running the project's wired scanners is already Phase 1 (`method.md`), and re-verifying a finding against source and
tests is already the fan-out discipline (`parallel-audit.md` §4–5). This adds the security-specific rule: for a class
of finding a **deterministic engine can *prove***, corroborate the LLM's claim against that proof or mark it
`unverified` — the review layers judgment on a proof no LLM reliably produces, it does not assert the proof.

- **Code-level SAST / quality engines** to run and read (tool-agnostic — the project's own wired one): **Semgrep** /
  OpenGrep (pattern + data-flow, autofix), **CodeQL** / GitHub code scanning (a query engine returning the source→sink
  path), **SonarQube** (quality gate + security *hotspots* — a hotspot is a triage signal, not a confirmed defect),
  **Snyk** (Code + Open Source), plus the ecosystem linters (`bandit`, `ruff`, `mypy`, `hadolint`).
- **The proof ↔ claim map** (corroborate, don't assert):
  - *"user input reaches this sink"* ↔ a **CodeQL taint / data-flow path** (source→sink); a claim with no path is
    `unverified`, not a finding.
  - *"this secret is real"* ↔ **TruffleHog** logging into the provider (Verified / Unverified / Unknown) — Unverified
    is not "clean" (the `Secrets` rule in security-appsec.md still holds: a committed secret is compromised).
  - *"this dependency version is vulnerable"* ↔ an **exact version↔CVE match** against machine-readable ranges
    (`osv-scanner` / Trivy / Grype — `dependency-currency-and-upgrades.md`), replacing the LLM's error-prone recall of
    affected ranges.
  - *"you're exposed because you depend on X"* ↔ **reachability** (Semgrep Supply Chain): a dep vuln matters only when
    code matches the vulnerable pattern — importing ≠ executing.
- **Ingestion:** pull deterministic findings through the standard interchange formats — **SARIF 2.1.0** (any scanner →
  code-scanning alerts) and **OSV JSON** (advisory data) — so the review reasons over a machine-readable proof, not a
  screen-scrape.
