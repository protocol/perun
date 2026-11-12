# Application security depth — software supply chain (A03)

Read this when the target or diff adds or bumps a dependency, touches a lockfile or an install-time script, edits a CI workflow or a file a privileged pipeline executes, passes artifacts or caches between jobs, or ships a signed, attested, or SBOM-bearing artifact. Split from `security-appsec.md`, whose per-category core checks (access control, injection, secrets, input validation, SSRF) apply to every application review.

## A03:2025 — Software Supply Chain Failures (depth)

**How to detect**: lockfile present and honored (`package-lock.json`, `poetry.lock`, `go.sum`, `Cargo.lock`)?
Dependencies pinned (no floating `^`/`latest` for security-critical libs)? Any unmaintained/abandoned or typosquatted
package (name a character off from a popular one)? Any **slopsquat** risk — a *newly-added* dependency whose name an
LLM may have **hallucinated** (a plausible name that never existed until an attacker pre-registered it, which
name-proximity does **not** catch)? Verify a new dependency resolves to an **established** package (registry age,
download history, a real source repo / provenance), not merely that it isn't a typo of a popular one —
LLM-hallucinated package names are a **predictable** pre-registration target (a material share of AI-recommended
packages don't exist, and the *same* hallucinations recur across runs — package-hallucination study logged in
`docs/standards-index.md`). Cross-ref `dependency-currency-and-upgrades.md` (the release-age cooldown extends to
never-existed-until-now). Install-time scripts (`postinstall`) from untrusted packages? CI actions pinned to a
**commit SHA**, not a mutable tag (`@main`, `@v3`)? Is the build reproducible/hermetic? Is there dependency + image
scanning and an SBOM — and, if an SBOM ships, is it paired with a **VEX** whose `not_affected` entries each carry a
justification (see Fix)? **CI/CD trigger & token hygiene** — does a `pull_request_target` (or `workflow_run`) workflow
check out untrusted PR head code? GitHub's hardening guide: these triggers "expose the repository to security
compromises" and "must not explicitly check out untrusted code." Is untrusted `${{ github.event.* }}` interpolated
straight into a `run:` step (script injection — route it through an intermediate `env:` var)? **AI agent steps** (Claude Code, Codex, Gemini, Copilot actions or CLIs): does outsider-written issue, PR, comment or branch-name text reach the agent prompt while the job holds a write token or secrets, does a `pull_request_target`/`issue_comment` job check out the PR head beside an agent (its CLAUDE.md or AGENTS.md then steers it), is the sandbox or approval off, or is Bash allowed unrestricted? `scripts/agent_workflow_injection.py` (run by `review_checks.sh` as `agent-injection`) lists these as leads. Is `GITHUB_TOKEN` /
`permissions` read-only by default and escalated per job? **But `permissions:` scopes the *token*, not a *secret*.** A
repo- or org-level secret (`${{ secrets.PROD_DEPLOY_KEY }}`) has no per-job boundary — *any* job running in the
repository context can reference it, including a lint/test job that never deploys — so a production deploy credential
sits in reach of jobs that don't need it (OWASP CI/CD **CICD-SEC-05**, Insufficient PBAC: malicious code in a pipeline
node "can access secrets, access the underlying host and connect to any of the systems the pipeline in question has
access to"). Fix per **CICD-SEC-06** (Insufficient Credential Hygiene): "Ensure secrets that are used in CI/CD systems
are scoped in a manner that allows each pipeline and step to have access to only the secrets it requires" — bind prod
credentials to a protected deployment `environment:`, whose secrets only a job declaring that environment can read and
whose deploy is gated by an approval / wait / branch restriction, instead of leaving them readable workflow- or
repo-wide. A plain fork `pull_request` job already runs *without* repo secrets (GitHub withholds them — see
`infra-iac-containers.md`); the trigger that hands a secrets-bearing context to untrusted PR code is
`pull_request_target` (above), so keep prod credentials out of any job reachable that way. Distinct axes:
self-hosted-runner isolation/ephemerality (`infra-iac-containers.md`) bounds *where* a job runs and what residue it
harvests; the committed-secret / rotation checks under **Secrets** in `security-appsec.md` are secret-at-rest — this bounds which jobs
may *read* a live secret.
**Are the files a privileged/protected pipeline *executes* under the same enforced review gate as the workflow file**
— a `make` target, `scripts/*.sh`, a `Dockerfile`, `conftest.py`, `.pre-commit-config.yaml`, a `package.json` script?
Protecting only `.github/workflows/` stops an edit to the pipeline *config*, but the privileged job still runs
whatever those *referenced* files contain, so an attacker edits the referenced file (not the protected workflow) and
the pipeline runs their code with its privileges (OWASP CI/CD **CICD-SEC-04**, *Indirect* PPE — distinct from the
script-injection and `pull_request_target` checkout above, which poison the config or its inputs directly). The trust
boundary is the transitive closure of what the pipeline executes, not the workflow YAML alone — and CODEOWNERS on
those paths binds a merge only when branch protection enforces it (`docs-and-dx.md`). **Verification vs authenticity**
— is a released artifact **signed** (SLSA / sigstore), or only checksummed over the **same channel** it ships on?
(Producer-side signing depth — cosign/Sigstore, npm/PyPI provenance, GPG — is in `release-engineering.md`.) A
same-origin checksum defends against corruption and a CDN mishap, **not** a compromised origin, so it doesn't
neutralize the trust-on-first-use risk of a `curl | sh` install from that origin.

**Provenance is only as strong as its verification.** SLSA's own Build track separates *provenance exists* (**L1** —
trivial to forge, may be unsigned) from *signed provenance from a hosted builder* (**L2**) and a
*hardened, tamper-resistant build* (**L3**), so a bare "adopts SLSA" with **no level named** is unverified strength,
not the strong guarantee. The failure that reads as done but isn't: an artifact **generates** provenance / an SBOM,
but the **deploy or promotion step never checks it**. It must **verify the attestation before promoting** — the
attestation's **subject digest matches the artifact** being promoted (the spec's first check, or a validly-signed
attestation for a *different* artifact passes), its signature is valid, the
**signer / builder identity is one you trust**, and the recorded **canonical source repository** (and, where the
builder records it, the commit) matches what you expect — and **fail closed** on a missing or mismatched attestation,
not merely emit a file nothing downstream re-reads. This is the runtime-proven-gate lens (domain B) applied to the
supply chain, and the **same blocking-gate bar** already required for inbound package signatures
(`infra-iac-containers.md`): the outbound attestation of the thing you actually ship deserves the same enforcement.
**But attestation at promotion doesn't cover the handoffs *inside* the pipeline.** When a later job consumes an
earlier job's `upload-artifact`/`download-artifact` output, or restores a build **cache**, with no integrity check
between stages, a poisoned cache or a tampered inter-job artifact flows downstream even though the *final* artifact is
attested — the tampering entered *before* the thing that gets signed was built, so the pipeline faithfully attests
poisoned bytes (OWASP CI/CD **CICD-SEC-09**, distinct from the final-artifact attestation above). Validate integrity
at *each* stage handoff — pin/verify inter-job artifacts and cache keys so a restored input is checked before a
downstream stage consumes it, not only at the promotion step.

**🚩 grep**: `"postinstall"` in `package.json`, `uses: actions/*@main`, unpinned base images (`FROM node:latest`),
`curl … | bash` in build steps, dependencies added in a diff without a lockfile update, `pull_request_target` paired
with a checkout of the PR head, `${{ github.event.` inside a `run:` block, a workflow with no `permissions:` block or
`permissions: write-all`, an install path whose only integrity check is a checksum served from the same host as the
artifact. A privileged workflow whose `run:` invokes `make`, `bash scripts/…`, `docker build`, `pre-commit`, or a
`package.json` script whose target file is **not** under the same review/CODEOWNERS rule as `.github/workflows/`. A
job that `download-artifact`s a prior job's output or restores `actions/cache` and consumes it with no
digest/attestation check before the next stage. A job that references `${{ secrets.` with no `environment:` scoping it
— especially a prod/deploy credential, or a `pull_request_target` job that runs with repo/org secrets available while
exposed to untrusted PR code.

**Fix**: pin by hash, commit lockfiles, scan dependencies and images in CI, generate an SBOM (CycloneDX/SPDX), and
adopt provenance (SLSA) for released artifacts. Pair the SBOM with a **VEX** (Vulnerability Exploitability eXchange) —
a producer-issued, per-CVE exploitability assertion (`not_affected` **with a justification**, `affected`, `fixed`,
`under_investigation`) so a consumer can tell a real exposure from a component that merely *ships* the vulnerable code
on an unreachable path; it complements, never replaces, the SBOM (CISA VEX). For workflows: never check out untrusted
PR code under `pull_request_target`; set `permissions` to least privilege (read by default, escalate per job); pass
untrusted context through an `env:` var, never inline `${{ }}` in `run:`; sign released artifacts (a checksum is
integrity, not authenticity); put every file the privileged pipeline *executes* — build scripts, `Makefile`,
`Dockerfile`, hook/linter configs, `package.json` scripts — under the **same** enforced review/CODEOWNERS gate as the
workflow file; and verify the integrity of inter-job artifacts and restored caches at **each** stage handoff
(pin/attest them, check a digest before a downstream job consumes them), not only when the final artifact is signed at
promotion (OWASP CI/CD **CICD-SEC-04** / **CICD-SEC-09**). Scope secrets to the job that needs them — bind prod
credentials to a protected deployment `environment:` (its secrets readable only by a job that declares it, deploy
gated by an approval / wait / branch restriction), not a repo/org-wide secret every job can read, and keep them out of
`pull_request_target` or other jobs exposed to untrusted PR code (OWASP CI/CD **CICD-SEC-05** / **CICD-SEC-06**).
**Severity keys on reachability** — a weak install verification on the *sole documented install path for every user*
outranks the same weakness on an optional side channel. See `infra-iac-containers.md` and section K of `SKILL.md`.
