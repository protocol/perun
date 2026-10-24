# Whole-app security review mode

Read this when the user asks for a security audit or security review of a whole app (not a diff). It is an orchestration layer: it says what to inventory, in what order to run the existing security references, how to chain their findings, and six gap checks they do not cover. Depth stays in `security-appsec.md` (and the `appsec-*.md` files it routes), `security-api.md`, `security-ai-agents.md`, `security-agent-skills.md`, `frontend-security.md`, `threat-modeling.md`, `appsec-supply.md` and `dependency-currency-and-upgrades.md`; this file links to them and never restates them. Sources are logged with fetch dates in `docs/standards-index.md`.

## 1. Whole-app mode: inventory first, then chains

1. **Entry inventory.** Build the entry-point table from `full-audit.md` section 1 (routes, actions, jobs, consumers, webhooks), then add the entries it omits for a security review: CLI and admin scripts, CI workflows and their triggers, agent tools and MCP servers, file-upload and import paths, third-party callbacks, and any host-platform integration that can deploy or read config.
2. **Asset inventory.** One row each: data store and its sensitive columns, every secret and where it is stored and read (env var, CI secret, secret manager, file), signing keys, session store, third-party accounts the app can act on, and the identities (human, service, CI, agent) that can reach each. Mark the crown jewels: what an attacker most wants (money movement, other users' data, deploy rights).
3. **Boundary pass.** Run `threat-modeling.md` over the inventory (data-flow table, per-boundary threats), then the matching domain files by archetype from `full-map.md`; do not re-derive their checklists here.
4. **Chain, do not just list.** After domain findings exist, build attack paths: write each finding as `precondition -> capability gained`, then join findings where one's gain satisfies another's precondition. Typical joins to test: an SSRF or file-read that reaches a secret store or cloud metadata; a low-privilege account plus an object-level auth gap; XSS or an open redirect plus a token in a URL; a CI trigger that runs untrusted code plus a write-scoped token; an agent that reads untrusted content plus a tool that sends data out or executes. Report the path as one finding at the severity of its end state, citing each link with `file:line`, and name the cheapest link to cut. A chain of Low findings that ends in a crown jewel is High.
5. **Close with the gaps below** (sections 2 to 6), then the standard report (`report-format.md`) with an attack-path section ahead of the flat list.

## 2. Host-platform breach and secret-rotation runbook

Use when a hosting platform the app runs on reports a breach, or when you cannot rule out that its stored configuration was read. Judgement, not a vendor script: follow the platform's own notice where it is more specific.

1. **Scope the exposure.** Treat every environment variable stored on the platform (all environments, preview and production, team-level and project-level) as exposed unless the platform's notice says otherwise, whatever "sensitive" or "hidden" flag it carries. Values built into a client bundle were public already.
2. **Cut footholds before rotating.** Revoke platform access tokens, deploy hooks, CI-to-platform tokens, unknown team members and installed integrations or OAuth apps; rotate the platform account credentials and require MFA. Rotating a secret while an attacker's token can still read the next one wastes the rotation.
3. **Rotate in blast-radius order, upstream credentials first** (anything that mints or unlocks other credentials): (a) cloud and CI credentials, container-registry and package-publish tokens; (b) database and cache credentials and connection strings; (c) session, JWT and cookie-signing secrets and encryption keys, planning for the forced sign-out or re-encryption this causes; (d) payment, email/SMS, storage and LLM provider keys; (e) webhook signing secrets and inbound-callback tokens, rotated on both sides together. Rotate, do not just re-set: the old value must stop working (revoke at the provider, not only in the platform).
4. **Redeploy** so running instances read the new values, and delete the old values from every environment and from CI.
5. **Verify.** For each secret: the old value is rejected by the provider (call it, expect 401 or 403), the new value works, and no copy remains in the repo, build logs, image layers or client bundle (secret scan, see `appsec-scan-tests.md`). Record the check per secret; an unchecked rotation is not done.
6. **Review logs for the exposure window**, from the earliest plausible date to the revocation time: the platform audit and deploy log (env-var reads or edits, new tokens, members, integrations, unexpected deployments); each provider's own access log for the rotated keys (calls from unfamiliar IPs, regions or user agents, new keys minted, data export, permission changes); database auth and query logs; cloud audit trail; the repo's push, workflow-edit and new-deploy-key events. Auditing must itself be tamper-resistant and timestamped (OWASP Secrets Management Cheat Sheet, section 2.6, and its section 9.2 revoke, rotate, audit sequence).
7. **If any log shows use of a stolen secret**, escalate to incident response and notification duties (`privacy-compliance.md`); rotation alone does not undo data already read.

## 3. CI/CD runner and OIDC trust

Run `appsec-supply.md` for SHA-pinned actions, untrusted-PR triggers, read-only `GITHUB_TOKEN`, secret scoping and provenance verification, and `infra-iac-containers.md` for runner isolation; a whole-app review adds only:

- **OIDC trust policy.** The cloud role's trust condition must pin the audience and a narrow `sub` (repository plus environment, branch or tag) and not a wildcard repository or owner; `permissions: id-token: write` only on the job that deploys. GitHub's docs require at least one condition so untrusted repositories cannot request tokens. Check that the role itself is least privilege: a perfect trust policy on an admin role is still a crown-jewel path.
- **Malicious producer.** Provenance that verifies still does not make the source benign: SLSA states it does not address producers who intentionally ship malicious software, so a dependency whose maintainer account was taken over passes provenance. Pair it with section 4.

## 4. Install-script and worm supply-chain checks

Worm-style package compromises spread through install-time code that runs with the installer's credentials (CI tokens, publish tokens, developer keys). Checks beyond `appsec-supply.md`:

- **Lifecycle scripts.** Enumerate lockfile dependencies that declare install-lifecycle scripts (base install-script and lockfile hygiene: `appsec-supply.md`); native-build packages that need them go on an explicit allowlist.
- **`--ignore-scripts`.** CI installs and any install that touches secrets use `npm ci --ignore-scripts` (or the package manager's equivalent config), with scripts then run only for allowlisted packages. Note npm's documented caveat: explicitly run scripts (`npm test`, `npm run`) still execute, just without their pre and post hooks.
- **Credential reach.** Install steps must not hold publish or deploy tokens: install in a job or step without secrets, publish in a later job. Look for tokens in `.npmrc`, environment and cached directories that an install script could read or exfiltrate.
- **Worm tells (reviewer judgement, not a sourced list).** A new install script in a patch release, a dependency diff that reads environment or token files or calls a new host, or code that edits other packages' manifests or workflow files. Apply the release-age cooldown in `dependency-currency-and-upgrades.md`.

## 5. Agent and MCP least privilege, tool poisoning

Depth is in `security-ai-agents.md` and `security-agent-skills.md`; the whole-app checks:

- **Capability inventory.** List every tool each agent or MCP server exposes and rate it read, write, execute, network-out or credential-bearing. Remove what the task does not need; split read-only from write tools; scope each token to the minimum (MCP's scope-minimization guidance: minimal initial scopes, incremental elevation, no wildcard or omnibus scopes).
- **Lethal trifecta.** Run the conjunction probe in `security-ai-agents.md` per agent, using the inventory above.
- **Tool poisoning.** Tool names, descriptions, annotations and results are model-visible input from the server author; the MCP spec requires clients to treat tool annotations as untrusted unless the server is trusted. Check: descriptions pinned or hashed at approval and re-approved on change (`listChanged` notifications are a re-review trigger); no instructions hidden in descriptions or schemas; a later tool cannot shadow or redefine an approved tool's name; results are validated before they reach the model.
- **Human in the loop.** Sensitive tool calls require confirmation showing the actual arguments; the MCP tools spec says clients should show tool inputs before calling and log tool usage for audit.
- **Local servers.** A locally launched MCP server runs with the client's privileges: show the exact command before first run, sandbox it with minimal file and network access, prefer `stdio` or an authenticated socket, and apply the token rules in `security-ai-agents.md`.
- **Config is code.** Agent and MCP config files in the repo (`.mcp.json`, agent settings, hooks) can execute commands; review changes to them like a CI workflow.

## 6. Dependency-advisory currency for runtime and framework

`dependency-currency-and-upgrades.md` covers the method; this check makes it a dated, evidence-backed line in the audit.

1. **Resolve exact versions** of the language runtime, framework and key middleware from lockfiles, container base images, CI matrix and platform runtime settings (they often disagree; the deployed one counts).
2. **Support status, advisories, KEV.** Run the end-of-life, advisory and CISA KEV method in `dependency-currency-and-upgrades.md` for each resolved version. The whole-app requirement: one dated evidence line per runtime and framework (source, fetch date), or `unverified`; never state a version is current or safe from recall.
3. **Platform-managed runtimes.** If the host picks the runtime version, record the setting and who controls it; a pinned old runtime on a managed platform is the app owner's finding.

## Definition of done (this mode)

Entry and asset inventories present; every chain names its links with `file:line` and the cheapest cut; sections 2 to 6 each either produce findings or state the evidence that they were checked and clean; every advisory or support-date claim carries a fetch date or `unverified`.
