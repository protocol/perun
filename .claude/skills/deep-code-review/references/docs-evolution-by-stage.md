# Documentation & information architecture by stage

Read this when the going-forward roadmap (`report-format.md`) must advise which
**documents** a project should have for its `STAGE`, or when the ask is "what
should I write down now?" This is the **which-docs-when** lens. The doc *types*
(Diátaxis, C4, ADR, README/AGENTS.md) and the stage-independent rules (the dated
`STATUS`/`HANDOFF` anti-pattern, single-source-of-truth, "a standards doc is
context, not enforcement") live in `docs-and-dx.md` (domain O) — do not duplicate
them. The stage model itself is in `full-map-principles.md` (Project stage).

## The spine: documents acquire normative force as the product matures
A document's job changes with stage, and that is what sets when to write it:
- **one-pager (persuade)** — a product/scope/vision one-pager or PR-FAQ. Job:
  decide whether to build at all; it names what is explicitly OUT of scope. Cheap,
  early, a forcing function *before* engineering.
- **design doc / RFC (decide)** — records a chosen path, the alternatives, and the
  trade-offs before code. Write it only when the design is genuinely ambiguous or
  several people must agree; skip it when the answer is obvious.
- **spec (contract)** — normative MUST/SHOULD wording is the marker that a doc is
  now a contract others build against; use those keywords sparingly, and pair each
  load-bearing MUST with the gate that enforces it (the domain-O rule).

## Trigger, not calendar
Each doc is called for by a condition, not a date: an ADR when a decision is
expensive to reverse (datastore, auth model, framework); a design doc when
ambiguity / consensus / senior-review / legacy questions say yes; an RFC when a
change is "substantial" enough that people must agree before code; a reference doc
when the API has external consumers; a tutorial only for a feature stable enough
to be worth maintaining (tutorials rot fastest).

## Per stage — write vs. explicitly-not-yet
| Stage | Write by default | NOT yet (cost if you do) |
|---|---|---|
| `prototype` | a one-pager (problem, who it's for, scope in/out, success signal); a minimal README (what it is + one-command run); a 10–20 line `AGENTS.md`/`CLAUDE.md` if an agent touches the repo | a full PRD, user-flow specs, an ADR log, the full Diátaxis tree — they document an unvalidated design and anchor you to it |
| `mvp` | README → BLUF + one-command setup; a C4 Context+Container sketch; the first ADRs (first hard-to-reverse decisions); a design doc only where contested; the first Diátaxis type (usually a how-to/quickstart) | exhaustive reference docs, tutorials for churning features, a heavyweight RFC process, MUST-level specs |
| `growth` | Diátaxis differentiates (how-to + reference as the API stabilizes; explanation for the non-obvious "why"); a lightweight RFC/pitch process; routine ADRs; a C4 Component diagram where earned; docs-as-code CI (link-check, doc↔code sync) | a full four-type tree for every module; tutorials you will not maintain; heavyweight governance |
| `mature` | the full Diátaxis set where the audience justifies it; normative specs, each paired with a gate; a comprehensive ADR log; SECURITY/CONTRIBUTING/CODEOWNERS; an agent-router index | new dated `STATUS`/`HANDOFF` snapshots (route to the `docs-and-dx.md` anti-pattern); duplicated facts (contradictory context is worse than a missing doc) |

## Agent-legibility: a router + routed depth
Make docs navigable for agents *and* humans with a two-tier shape — the repo's own
`SKILL.md → references/` pattern generalized to product docs: a **small,
always-loaded router** (README / `AGENTS.md` / an `llms.txt`-style index) that is
short and high-signal, plus **depth files it names with explicit "read this
when…" triggers**, pulled on demand. Two rules matter more for agents than for
humans: **stable, unique headings** (an agent retrieves by anchor/grep — a moved
or duplicated heading breaks the link) and **one fact in one place** (a duplicated
fact returns two answers → contradictory context). Keep context next to the code
it governs (nearest-file-wins).

## Standards (by name; verify a URL before adding one to `docs/standards-index.md`)
Diátaxis (and its incremental "one cell at a time" adoption); the C4 model;
Architecture Decision Records; RFC 2119 requirement keywords (used sparingly);
docs-as-code; `AGENTS.md`; `llms.txt`; minimum-viable-documentation; the PR-FAQ /
working-backwards one-pager; the lightweight pitch (problem / appetite / solution /
rabbit-holes / no-gos). Named leads; fetch and log a source before citing a
version-specific detail (repo convention).

Cross-references: the going-forward roadmap this feeds (`report-format.md`); doc
types + the stage-independent rules (`docs-and-dx.md`, domain O); the stage model
(`full-map-principles.md`, Project stage).
