# Infrastructure & architecture evolution by stage

Read this when the going-forward roadmap (`report-format.md`) must advise how a
project's **infrastructure and architecture** should evolve for its `STAGE`, or
when the ask is "how should I structure my infra / deploy / architecture now?" or
"should this become its own package or a separate repo?"
This is the **when-to-add** lens. The **how-to-secure / what-to-check** for infra
that already exists lives in `infra-iac-containers.md` (domain L) — do not
duplicate it. The stage model itself is in `full-map-principles.md` (Project stage).

## The rule: infrastructure is earned, not provisioned up front
Start with the simplest thing that ships — one well-modularized deployable on
boring, managed technology, in one environment — and add each layer only when a
concrete, observable signal shows the current setup is now the bottleneck or the
risk. This is the consensus of the monolith-first, YAGNI, and "choose boring
technology" (spend few innovation tokens) schools and of evolutionary-architecture
practice. The owner's instinct — no separate dev/staging/prod while prototyping,
harden as it matures — is correct.

## The floor that never relaxes (state this first)
Before any stage-based deferral: **security, secret management, authentication on
anything exposed, and backups with a tested restore for any real data are NOT
deferrable, even at `prototype`.** This mirrors the `SKILL.md` stage guardrail
(security / secret / data-loss findings never relax by stage). Everything below is
*operational scaffolding* (CI depth, environment separation, containers,
orchestration, IaC, tracing, feature-flag platforms) — never that floor.

## Per stage — build vs. explicitly-not-yet
| Stage | Appropriate | Explicitly NOT yet (cost if you do) |
|---|---|---|
| `prototype` | one monolith; one environment (local / a single cheap host or PaaS); version control; a managed datastore; config in env vars | dev/staging/prod separation, CI/CD, containers, k8s, IaC, microservices, observability stacks, feature-flag platforms — YAGNI on a thing you may discard |
| `mvp` | still a monolith with deliberate internal modularity; one prod env (+ a preview if a bad deploy is now felt); **basic CI** (build+test on push); automated deploy; managed services; basic monitoring (errors + availability); backups with tested restore | microservices, k8s, multi-region, full IaC rigor, distributed tracing, a feature-flag platform, scale/perf headroom |
| `growth` | CI/CD with tests as a merge gate; a staging env mirroring prod; **IaC**; containers; richer **observability**; feature flags; **SLOs + error budget**; delivery metrics as a signal; fitness functions | k8s unless operational load truly exceeds PaaS+containers; microservices unless the monolith is genuinely too complex AND seams are stable; multi-region unless a reliability commitment demands it |
| `mature` | full CI/CD with progressive delivery; mature observability + on-call; IaC as source of truth; orchestration only if many services / high scale justify it; service extraction at stable seams; DR / multi-region per the reliability commitment | net-new scope creep; stale feature-flag inventory (retire flags — they have a carrying cost) |

## The trigger for each step (evidence, not cargo-cult)
| Step | Observable trigger that justifies it |
|---|---|
| basic CI (build+test) | a second contributor, or a regression reaching users / breaking `main` |
| automated / push-button deploy | deploys are manual, slow, or feared |
| separate staging ↔ prod | real users now feel a bad deploy |
| managed service (vs self-host) | the default; self-host only when a managed option provably cannot meet a documented constraint |
| containers | "works on my machine" drift; need a reproducible artifact |
| infrastructure as code | a second environment to keep in sync; config drift / snowflake servers; an audit need |
| observability (beyond error counts) | you cannot answer "why is it slow/failing" from logs; users report outages before you detect them |
| feature flags | long-lived branches block release cadence; need to decouple deploy from release, canary, or hold a kill-switch (then manage flags as inventory) |
| orchestration (k8s) | you already have rapid provisioning + monitoring + rapid deploy AND are hand-managing enough services/hosts to cross the complexity threshold — below that it is premium with no payoff |
| microservices / service extraction | the monolith is genuinely too complex to manage AND the boundaries are stable AND the prerequisites above exist; then peel from the edges |
| internal package → separate repo | a part has an **independent change cadence AND distinct external consumers AND its own release + ownership**; until then carve an **internal package** (a named import boundary) inside the one repo — cheaper and reversible |
| SLOs + error budget | users now have reliability expectations you must trade against release speed |

**Splitting is earned like the rest.** A repo split is org/deploy structure, not a substitute for
a module boundary — carve the internal package first, or the split just relocates the tangle
across repos. Co-evolving artifacts (schema ↔ validator ↔ types ↔ docs) stay **co-located**;
spread across repos with no parity guard they silently drift (domain H).

## What the review CANNOT decide from the repo (route to the owner)
Repo-observable signals set the *read*; these business/ops facts set the *mandate*,
and the repo does not hold them: a real SLA / reliability commitment; the
regulatory regime and data classification; revenue / outage exposure; funding
runway vs. infra carrying cost; team & hiring trajectory (the real trigger for
service extraction); customer concentration / risk appetite. Propose the
stage-appropriate step and name the observable signal behind it; **route anything
gated on these six to the owner** rather than mandating the build.

## Standards (by name; verify a URL before adding one to `docs/standards-index.md`)
Monolith-first, modular monolith, YAGNI, microservice-premium and microservice-prerequisites,
infrastructure-as-code, continuous delivery, feature toggles (Fowler);
choose-boring-technology / innovation tokens (McKinley); the Twelve-Factor App;
DORA delivery metrics (the set and names have been revised — check the current
source before citing specific metric names or benchmark tiers); Google SRE SLOs
and error budgets; evolutionary architecture and fitness functions. These are
named leads; a skill that cites a version or number must fetch and log the source
first (repo convention).

### Deploy-readiness checks

- **Measure peak build memory against the builder's declared quota.** A change that adds a boot hook or a dependency can raise a container build's peak RSS enough to cross a builder memory quota, and the build then fails without a clear error. **Detect:** a deploy-readiness check that never records peak build RSS. **Fix:** measure it (for example `/usr/bin/time -l` on macOS or `-v` on Linux) and compare to the quota with headroom.
- **An optional secret is unsettable if the deploy platform only renders input fields for variables marked REQUIRED.** An app that declares a feature-gating secret optional can leave the feature silently dark in production, with no error. **Detect:** every optional env var that gates a user-visible feature. **Fix:** mark it required, or confirm the platform has a real path to set optional secrets; verify a human can set it through the platform's own UI, not only that the local `.env` supports it.

Cross-references: the going-forward roadmap this feeds (`report-format.md`);
how-to-secure existing infra (`infra-iac-containers.md`, domain L); the SLI/SLO
lens (`role-coverage.md`, Platform/SRE); the stage model (`full-map-principles.md`, Project
stage).
