# Dependency currency & safe upgrades

Read this when the target declares third-party dependencies (any
`package.json`/`requirements.txt`/`go.mod`/`Cargo.toml`/`pom.xml`/`Gemfile`/
`*.csproj`/base image/action), or when the review question is "are the
libraries up to date?" / "is it safe to bump these?". It expands sections **K**
(supply chain) and **H** (dependencies current) of `SKILL.md` with the
detection procedures and the **upgrade discipline** — how to reach latest-stable
*without* regressing working code. It is the currency-and-modernization half of
supply-chain review; the **integrity** half (pinning, lockfiles, typosquat,
`postinstall`, SHA-pinned actions, SBOM, provenance/SLSA) lives in A03 of
`appsec-supply.md` — cross-link, do not restate.

Standards this file tracks (verified URLs + dates in `docs/standards-index.md`):
OWASP Top 10:2025 **A03 Software Supply Chain Failures** (which absorbed the
former A06:2021 *Vulnerable and Outdated Components*), OpenSSF Scorecard, OSV
(osv.dev), Semantic Versioning, GitHub Dependabot, Renovate (`minimumReleaseAge`
cooldown), endoflife.date, CISA KEV (Known Exploited Vulnerabilities catalog),
FIRST EPSS (Exploit Prediction Scoring System), FIRST CVSS (Common Vulnerability
Scoring System — severity), package-hallucination / slopsquatting (Spracklen et
al., USENIX Security 2025).

> The two forces are in tension and the review must hold both. **Staleness is a
> security risk** — A03:2025 names software that is "vulnerable, unsupported, or
> out of date" and faults a project that does "not fix or upgrade the underlying
> platform, frameworks, and dependencies in a risk-based, timely fashion."
> **But "latest" is not automatically safe** — a fresh release can carry a
> breaking change (Semantic Versioning: a MAJOR bump *is* "incompatible API
> changes") or be outright malicious (a hijacked maintainer account, a poisoned
> new version). A03's own guidance is to "deliberately choose which version of a
> dependency you use and upgrade only when there is need." So the finding is
> never "bump everything to latest." It is "close the currency gap that carries
> risk, through a gate that proves nothing broke."

---

## 1 — Detect the currency gaps

Produce three lists, not one. "Behind latest" is the weakest signal; a
known-exploitable vulnerability on a reachable path is the strongest.

**A. Known-vulnerable versions (highest priority).** Run the ecosystem's audit
against the **committed lockfile**, not a fresh resolve, so you see what actually
ships:

| Ecosystem | Currency check | Known-vuln audit |
|---|---|---|
| npm/pnpm/yarn | `npm outdated` | `npm audit` / `osv-scanner` |
| PyPI | `pip list --outdated` | `pip-audit` / `osv-scanner` |
| Go | `go list -u -m all` | `govulncheck` (call-graph aware) |
| Rust | `cargo outdated` | `cargo audit` |
| Java/Maven | `versions:display-dependency-updates` | OWASP Dependency-Check |
| Ruby | `bundle outdated` | `bundler-audit` |
| Containers/base images | digest vs upstream tag | image scanner (Trivy/Grype) |

`osv-scanner` is ecosystem-agnostic: it reads a lockfile or SBOM and queries OSV,
which spans 40+ ecosystems — a good single cross-check when the repo mixes
stacks. Prefer a **call-graph-aware** scanner where one exists (`govulncheck`):
"the CVE is present" and "the vulnerable function is reachable" are different
severities (see §3).

**B. End-of-life / unmaintained / deprecated (the silent risk).** A package can
be on its own latest version and still be a liability because *there will be no
next version*:
- **Runtime/framework/DB EOL** — cross-check the platform's support timeline
  (e.g. endoflife.date) for the language runtime, framework, DB engine, and base
  image. An out-of-support runtime gets no security patches; that is a High even
  with zero current CVEs.
- **Abandoned library** — last release age, open-vs-closed issue ratio, archived
  repo, a `DEPRECATED` notice, or the registry's deprecation flag
  (`npm deprecate`, PyPI yank). OpenSSF Scorecard's **`Maintained`** check
  formalizes "active in the last 90 days"; its **`Vulnerabilities`** check (via
  OSV) and **`Dependency-Update-Tool`** check surface the rest.
- **Deprecated API within a current dep** — the dep is fine but you call a
  method it has marked for removal; the next major will break you. Grep for the
  library's own deprecation warnings in build/test logs.

**C. Merely behind latest-stable (currency debt).** Everything with a newer
stable release and no known vuln. Target **latest _stable_** — exclude
pre-release/alpha/beta/RC channels unless a specific fix is only there and the
risk is accepted by an owner. This list is real (it is how you *end up* in list A
later) but it is **not** a blocking finding on its own — rank it per §3 or it
becomes noise.

Report per-list, and state coverage honestly: "audited the committed lockfile;
transitive deps included" — an audit that only reads top-level manifests misses
where most CVEs live.

---

## 2 — The upgrade discipline (reach current without breaking working code)

This is the core of the request "bumping versions must follow thorough review
and test." Every bump is a change under review and gets the same net-positive
bar as any other (`full-map-principles.md` principle 4): it must not regress correctness,
tests, performance, or another axis.

1. **One dependency (or one cohesive group) per change.** A single-dep PR that
   goes red tells you exactly what broke; a 40-package sweep does not. Group only
   deps that *must* move together (a framework and its plugins). This dovetails
   with `SKILL.md` Phase 5's "split by risk surface" — a security patch rides its
   own small PR, never buried in a bulk bump. **At bulk scale**
   (`dependency-bulk-upgrades.md` §1), tier+ecosystem batching is the exception —
   never a security-advisory update (own fast-lane PR, §2.6) — and only if the
   batch reverts as one group.
2. **Size the risk by the version delta (Semantic Versioning).** PATCH =
   "backward compatible bug fixes", MINOR = "backward compatible" new
   functionality — low-risk, fast-track. MAJOR = "incompatible API changes" —
   *expect* breakage: read the migration guide, budget code changes, never
   auto-merge. Treat a `0.x` bump as potentially-major (semver pre-1.0 makes no
   compatibility promise). A dep that violates semver (breaking change in a
   "minor") is itself a finding against that dep.
3. **Read the changelog / release notes / migration guide before bumping**, not
   after the tests go red. This is the one human step even the automation assumes
   — Dependabot's own documented flow is "check that your tests pass, review the
   changelog and release notes." Look for: removed/renamed APIs, changed
   defaults, raised minimum runtime, transitive bumps, license change (cross-ref
   `SKILL.md` Q).
4. **Regenerate and commit the lockfile**, then **re-run the project's own
   one-command aggregate gate** (`SKILL.md` Phase 1) — full build, tests, lint,
   type-check, and the dependency/security scan — and confirm it is **green on
   the bumped tree**. An update is not mergeable until that gate passes on it;
   this is the skill's requirement, independent of whether a bot opened the PR.
   For a dep with thin coverage, add the missing test *before* the bump so
   "green" means something (`references/testing-and-evals.md`).
5. **Verify the new release is not itself the attack.** Currency and integrity
   collide here: pulling "latest" is exactly how a compromised version enters.
   Before trusting a jump — especially a large one or a just-published release —
   confirm provenance/signature and that the package is not typosquatted,
   **slopsquatted** (a hallucinated name an attacker pre-registered — verify a
   newly-added dep resolves to an *established* package with real history),
   or maintainer-hijacked (A03 in `appsec-supply.md`). The
   release-age cooldown below also catches a slopsquat name: it has no established
   history to clear the window. Do **not** auto-merge bot update PRs without
   this + the green gate.
   **Prefer a release-age cooldown**: refuse to resolve a version until it has
   been public for a set window (e.g. 7 days), so a compromised or broken
   just-published release is caught before it reaches you. Update bots support
   it (Renovate `minimumReleaseAge` — "Suppress branch/PR creation for X days";
   Dependabot and pnpm/npm expose an equivalent cooldown / `min-release-age`
   key — confirm the exact key per ecosystem). Exempt security-advisory updates
   from the cooldown so real CVE fixes still fast-track.
6. **Separate the two cadences.** Security patches (usually PATCH/MINOR, or a
   backport) fast-track on their own; feature/major upgrades are scheduled,
   migration-planned work. Conflating them either delays a fix or rushes a
   breaking change.
7. **Bounded and reversible.** A bump you cannot test
   safely in-repo (it touches a paid integration, prod data, or a
   hard-to-reproduce runtime) gets a canary/staging path first; a tested rollback
   — revert the lockfile to the pinned prior version — must always exist. Keep
   the lockfile the single source of truth and **pin after upgrading** (A03).
8. **EOL is a migration, not a bump.** When list §1B has no newer version to go
   to (runtime out of support, library archived), the fix is a planned
   replacement/migration surfaced as an owner decision, not a version number.

**Automate the treadmill, keep the gate.** An update bot (Dependabot, Renovate,
or equivalent) that opens one reviewable PR per update — Dependabot "raises a
pull request to update the manifest to the latest version" even when there is no
vulnerability — turns currency from a periodic manual audit into a steady stream
that each passes review + the aggregate gate. Recommend one where it is absent
(OpenSSF Scorecard's `Dependency-Update-Tool` check rewards it). The bot
*feeds* the gate and the changelog read, never replaces them.

---

## 3 — Severity discipline (do not turn currency into noise)

Rank a dependency finding by **exploitable consequence today**, like any
other (`full-map.md`). This stops a currency pass
burying a real Critical under a wall of "bump me":

- **Known-exploited (or high-CVSS) vulnerability, on a reachable code path** →
  Critical/High. Reachability matters: a vulnerable function you never call is
  lower than one on the request path — tag it `latent` with the trigger that
  would reach it rather than inflating or dismissing it.
- **EOL / unmaintained runtime or library carrying sensitive work** → High
  (no patch will ever come), even with no current CVE.
- **Known vuln but not reachable, or only in a dev/test/build-time dep** →
  Medium/Low; say why the blast radius is bounded.
- **Merely behind latest-stable, no known vuln** → Low or `Nit:` — "currency
  debt," non-blocking. Report it as a batch with the recommendation to adopt an
  update bot, **not** as N separate findings. Never let this class outrank a real
  defect. Branches too: `branch-and-merge-hygiene.md` §7.

**Determining "known-exploited" — name the instrument, don't guess.** A finding
that turns on "known-exploited" must name its source, per principle 2
(prefer the canonical instrument). CISA's **KEV** catalog is
"the authoritative source of vulnerabilities that have been exploited in the
wild" — a CVE listed there *is* known-exploited. FIRST's **EPSS** gives the
data-driven probability a CVE "will be exploited in the wild in the next 30
days." Read them **alongside** CVSS, not instead of it: KEV / EPSS answer *how
likely*, CVSS answers *how bad* (severity). But both bodies frame KEV and EPSS
as *inputs* to prioritization, so they **raise and rank, never lower the bar** —
a low EPSS, or a CVE's absence from KEV, does **not** disarm a reachable-path finding
(absence of exploitation evidence is not proof of safety, and EPSS is a 30-day
probability, not a verdict).

And never recommend a bump you have not shown is gate-green — a fix that breaks
the build is a regression (principle 4). If the gate was not run
on the bumped tree, mark the recommendation `unverified` and name what
would confirm it.

---

## 4 — Adding a new dependency is a governance decision, not an implementation detail

Sections 1–3 keep **existing** dependencies current; this covers **taking on a new one**. A
feature sometimes needs a capability the codebase lacks (client-side screenshot capture, a
charting or date-parse lib), and the tempting move is to `npm install` a package and ship. But a
new runtime dependency is a **long-term liability the maintainer carries, not a free import** — it
commits the project to a bundle-size / perf cost, a **supply-chain and security surface** (the
whole transitive tree, §1), a **license** obligation, and ongoing maintenance. That is an
**owner/maintainer decision**, not one an agent (or a feature PR) can unilaterally own.
- **Report "this needs a new dependency" as BLOCKED-ON-OWNER** — with the exact dep(s) / approach
  and the tradeoff (size, license, transitive surface, alternatives) — never a committed
  `npm install`.
- **First check for a lighter path** — an existing in-repo capability, an already-bundled lib, or
  a native platform API; often the new dep is avoidable.
- **Calibrate by weight, not reflex.** A tiny, ubiquitous, well-audited dep may be routine; a
  **heavy / novel / broad-surface / unmaintained** one is the owner's call. When unsure, ask.
- **Review lens:** a PR that adds a `package.json` (or `requirements.txt`, `go.mod`, …)
  dependency **alongside a feature** deserves explicit scrutiny — necessary, minimal, maintained,
  license-compatible, and **approved**?

This is the global *confirm before a lasting / shared-state commitment* rule applied to the
dependency manifest. (Governance is the decision to take it on; integrity, once approved, is
verified per §2.)

---

## 🚩 Red flags

- No lockfile, or a lockfile out of sync with the manifest (a bump landed without
  regenerating it) — cross-ref A03.
- No dependency/vulnerability scan wired into CI; audit run manually or never.
- No update-bot config (`dependabot.yml` / `renovate.json`) **and** a long tail
  of outdated deps — currency has no owner.
- A single mega "update all dependencies" commit with no per-dep test evidence —
  not the scoped tier+ecosystem batches in `dependency-bulk-upgrades.md` §1.
- An **agent- or feature-PR-added new runtime dependency with no recorded owner/maintainer
  decision** (heavy / novel / broad-surface especially) — adding a dep is a governance call (§4),
  not an implementation detail.
- Pinned to an **EOL** runtime/base image (`python:3.8`, `node:14`, an
  out-of-support framework LTS).
- A direct dep last released years ago / repo archived / registry-deprecated,
  still on a load-bearing path.
- Auto-merge enabled on bot PRs with no green-gate or provenance gate in front.
- No release-age cooldown on the update path — freshly-published versions are
  auto-resolved or auto-merged the day they ship, leaving no window for a
  compromised release to be caught (cross-ref A03).
- Chasing pre-release/`latest`-tag versions in production manifests.
- A "minor" bump that actually broke an API (the dep violates semver) — trust its
  version numbers less thereafter.

## Cross-references

- **A03 (`appsec-supply.md`)** — pinning, lockfile integrity, typosquat/
  dependency-confusion, `postinstall`, SHA-pinned actions, SBOM, provenance. The
  integrity half; this file is the currency half.
- **`SKILL.md` Phase 1** — the aggregate gate every bump must pass, and proving
  the gate can fail.
- **`references/testing-and-evals.md`** — add the pinning/regression test that
  makes "green after the bump" meaningful.
- **`SKILL.md` H / K** — this file is the depth behind "Dependencies current" and
  the supply-chain release checklist.
